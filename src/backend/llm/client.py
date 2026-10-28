"""Gemini chat client with retry and fallback resilience."""

import json
import logging
import random
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import requests

from src.backend.core import tracing
from src.backend.core.config import settings

logger = logging.getLogger(__name__)

# Gemini's OpenAI-compatible API: the same request and stream format LiteLLM produced, without loading
# LiteLLM (~190 MB once imported, more than a third of a 512 MB instance)
GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
REQUEST_TIMEOUT = (10, 120)  # connect, read (between streamed chunks)


class LLMServiceUnavailableError(Exception):
    """Raised when LLM service remains unavailable after bounded retries and fallback attempts."""

    pass


class LLMAPIError(Exception):
    """An error response from the model API, with its HTTP status (0 when the request never got one)."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"{status_code} {message}" if status_code else message)
        self.status_code = status_code


@dataclass
class Completion:
    """A finished model reply: the assistant message (OpenAI format, tool calls included) and token usage."""

    message: dict[str, Any]
    usage: dict[str, int] | None = None

    @property
    def content(self) -> str:
        return self.message.get("content") or ""


def normalize_model_name(name: str) -> str:
    """Normalize model string with provider prefix if needed."""
    if not name:
        return name
    if "/" in name:
        return name
    if name.startswith("gemini"):
        return f"gemini/{name}"
    if name.startswith("claude"):
        return f"anthropic/{name}"
    return name


def _api_error(resp: requests.Response) -> LLMAPIError:
    try:
        body = resp.json()
        body = body[0] if isinstance(body, list) and body else body
        detail = body.get("error", {}).get("message") or resp.reason
    except (ValueError, AttributeError):
        detail = resp.reason or "request failed"
    return LLMAPIError(resp.status_code, str(detail)[:500])


def completion(
    model: str,
    messages: list[dict[str, Any]],
    api_key: str | None,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Any:
    """One chat completion. Returns a Completion, or with stream=True an iterator of raw chunk dicts."""
    provider, _, bare_model = model.rpartition("/")
    if provider not in ("", "gemini"):
        raise ValueError(f"Unsupported model provider '{provider}'. Only Gemini models are supported.")
    body: dict[str, Any] = {"model": bare_model, "messages": messages, **kwargs}
    if tools:
        body["tools"] = tools
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    try:
        resp = requests.post(
            GEMINI_OPENAI_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            stream=stream,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout as exc:
        raise LLMAPIError(0, "timed out") from exc
    except requests.RequestException as exc:
        raise LLMAPIError(0, f"connection error: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        err = _api_error(resp)
        resp.close()
        raise err
    if stream:
        return _iter_chunks(resp)
    data = resp.json()
    data = data[0] if isinstance(data, list) else data
    message = (data.get("choices") or [{}])[0].get("message") or {"role": "assistant", "content": ""}
    return Completion(message=message, usage=data.get("usage"))


def _iter_chunks(resp: requests.Response) -> Iterator[dict[str, Any]]:
    """Parse a server-sent event stream of completion chunks."""
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                return
            chunk = json.loads(payload)
            if "error" in chunk:
                err = chunk["error"]
                raise LLMAPIError(int(err.get("code") or 0), str(err.get("message", "stream error"))[:500])
            yield chunk
    except requests.RequestException as exc:
        raise LLMAPIError(0, f"connection error: {type(exc).__name__}") from exc
    finally:
        resp.close()


def delta_text(chunk: dict[str, Any]) -> str | None:
    choices = chunk.get("choices") or []
    return (choices[0].get("delta") or {}).get("content") if choices else None


def assemble(chunks: list[dict[str, Any]]) -> Completion:
    """Rebuild the full assistant message (text and tool calls) and usage from streamed chunks.

    Gemini sends each tool call whole, sometimes without an index, plus an extra_content thought signature
    that must be sent back unchanged on the next round, so everything but the argument text is kept as is.
    """
    text: list[str] = []
    calls: list[dict[str, Any]] = []
    by_index: dict[int, dict[str, Any]] = {}
    usage = None
    for chunk in chunks:
        usage = chunk.get("usage") or usage
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                text.append(delta["content"])
            for tc in delta.get("tool_calls") or []:
                index = tc.get("index")
                call = by_index.get(index) if index is not None else None
                if call is None and (index is not None or tc.get("id") or not calls):
                    call = {"type": "function", "function": {"name": "", "arguments": ""}}
                    calls.append(call)
                    if index is not None:
                        by_index[index] = call
                elif call is None:
                    call = calls[-1]
                for key, value in tc.items():
                    if key == "function":
                        fn = call["function"]
                        fn["name"] = fn["name"] or value.get("name") or ""
                        fn["arguments"] += value.get("arguments") or ""
                    elif key != "index" and value is not None:
                        call[key] = value
    message: dict[str, Any] = {"role": "assistant", "content": "".join(text)}
    if calls:
        message["tool_calls"] = calls
    return Completion(message=message, usage=usage)


def is_transient_error(exc: Exception) -> bool:
    """Determine whether an error is transient (e.g. 503, rate limit, timeout) and safe to retry."""
    # Never retry authentication, permission, or malformed request errors
    if isinstance(exc, ValueError):
        return False

    status_code = getattr(exc, "status_code", None)
    if status_code in (400, 401, 403, 404):
        return False
    if status_code in (429, 500, 502, 503, 504):
        return True

    err_str = str(exc).lower()
    # Check for authentication / authorization phrases
    if any(
        term in err_str
        for term in [
            "api key",
            "unauthorized",
            "permission",
            "invalid argument",
            "bad request",
            "not found",
        ]
    ):
        return False

    transient_indicators = [
        "503",
        "unavailable",
        "high demand",
        "overloaded",
        "rate limit",
        "resource exhausted",
        "temporarily unavailable",
        "connection error",
        "timeout",
        "timed out",
    ]
    return any(term in err_str for term in transient_indicators)


class LLMClient:
    """Client for Gemini completion calls with bounded retries and fallback."""

    def __init__(
        self,
        model_name: str | None = None,
        fallback_model_name: str | None = None,
        api_key: str | None = None,
        max_retries: int = 2,
        base_delay: float = 0.5,
    ) -> None:
        raw_model = model_name or settings.model_name
        self.model_name = normalize_model_name(raw_model)

        raw_fallback = (
            fallback_model_name
            if fallback_model_name is not None
            else getattr(settings, "fallback_model_name", None)
        )
        self.fallback_model_name = (
            normalize_model_name(raw_fallback) if raw_fallback else None
        )

        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.max_retries = max_retries
        self.base_delay = base_delay

    def _call_model_with_retries(
        self,
        target_model: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Call the model with bounded exponential backoff and jitter."""
        call_kwargs: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "api_key": self.api_key,
            **kwargs,
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            generation = tracing.generation("completion", target_model, messages)
            try:
                response = completion(**call_kwargs)
                tracing.end_generation(generation, target_model, response)
                return response.content
            except Exception as exc:
                tracing.end_generation(generation, target_model, error=exc)
                last_error = exc
                if not is_transient_error(exc) or attempt >= self.max_retries:
                    # Non-transient or exhausted maximum retries
                    raise exc

                # Exponential backoff with jitter: delay * (2^attempt) + jitter
                delay = (self.base_delay * (2 ** attempt)) + random.uniform(0.05, 0.25)
                logger.warning(
                    "Transient error calling %s (attempt %d/%d): %s. Retrying in %.2fs...",
                    target_model,
                    attempt + 1,
                    self.max_retries + 1,
                    type(exc).__name__,
                    delay,
                )
                time.sleep(delay)

        if last_error:
            raise last_error
        return ""

    def _require_api_key(self) -> None:
        if not self.api_key:
            logger.error("GEMINI_API_KEY is not configured.")
            raise ValueError(
                "LLM API key is not configured. "
                "Please set GEMINI_API_KEY in your .env file."
            )

    @staticmethod
    def build_messages(
        message: str | list[dict[str, str]],
        intent: str = "GENERAL",
        context: Any = None,
    ) -> list[dict[str, str]]:
        """Build the chat message list (system prompt + user message) sent to the model."""
        if isinstance(message, list):
            return message
        else:
            system_prompt = (
                "You are the reasoning and response layer of ContextAI, "
                "a personal AI assistant. "
                f"The intent classifier has already classified the user's "
                f"request as: '{intent}'. "
                "Provide a helpful, accurate, and concise response "
                "tailored to this intent."
            )

            if context:
                system_prompt += (
                    f"\n\nContext information (conversation history and memories):"
                    f"\n{context}\n"
                    "Use this context only as background information "
                    "and do not invent memories."
                )

            return [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(message)},
            ]

    def generate_response(
        self,
        message: str | list[dict[str, str]],
        intent: str = "GENERAL",
        context: Any = None,
        **kwargs: Any,
    ) -> str:
        """Call the model with transient retry logic and fallback model support."""
        self._require_api_key()
        messages = self.build_messages(message, intent, context)

        # 1. Attempt primary model with retries
        try:
            return self._call_model_with_retries(self.model_name, messages, **kwargs)
        except Exception as primary_exc:
            if not is_transient_error(primary_exc):
                # Never retry or fallback on auth, invalid key, or malformed requests
                raise primary_exc

            logger.warning(
                "Primary model %s failed after retries with transient error: %s",
                self.model_name,
                type(primary_exc).__name__,
            )

            # 2. Attempt fallback model if configured and distinct from primary
            if self.fallback_model_name and self.fallback_model_name != self.model_name:
                logger.info(
                    "Attempting fallback model %s...",
                    self.fallback_model_name,
                )
                try:
                    return self._call_model_with_retries(
                        self.fallback_model_name, messages, **kwargs
                    )
                except Exception as fallback_exc:
                    if not is_transient_error(fallback_exc):
                        raise fallback_exc
                    logger.error(
                        "Fallback model %s also failed with transient error: %s",
                        self.fallback_model_name,
                        type(fallback_exc).__name__,
                    )
                    raise LLMServiceUnavailableError(
                        "Gemini is temporarily unavailable. Please try again in a moment."
                    ) from fallback_exc

            # If no fallback or fallback equals primary
            raise LLMServiceUnavailableError(
                "Gemini is temporarily unavailable. Please try again in a moment."
            ) from primary_exc

    def stream_response(
        self,
        message: str | list[dict[str, str]],
        intent: str = "GENERAL",
        context: Any = None,
        cancel_event: threading.Event | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Yield response text deltas as the model produces them.

        Transient failures are retried (then the fallback model is tried) only before the first token,
        so a caller never sees a partially streamed answer restart. Setting cancel_event stops the
        stream early; whatever was produced so far has already been yielded.
        """
        self._require_api_key()
        messages = self.build_messages(message, intent, context)

        models = [self.model_name]
        if self.fallback_model_name and self.fallback_model_name != self.model_name:
            models.append(self.fallback_model_name)

        last_error: Exception | None = None
        for model in models:
            for attempt in range(self.max_retries + 1):
                started = False
                chunks: list[Any] = []
                generation = tracing.generation("answer", model, messages)
                try:
                    stream = completion(model=model, messages=messages, api_key=self.api_key, stream=True, **kwargs)
                    for chunk in stream:
                        if cancel_event is not None and cancel_event.is_set():
                            break
                        chunks.append(chunk)
                        if delta := delta_text(chunk):
                            started = True
                            yield delta
                    tracing.end_stream(generation, model, chunks, messages)
                    return
                except GeneratorExit:
                    tracing.end_stream(generation, model, chunks, messages)
                    raise
                except Exception as exc:
                    tracing.end_generation(generation, model, error=exc)
                    if started or not is_transient_error(exc):
                        raise
                    last_error = exc
                    if attempt < self.max_retries:
                        delay = (self.base_delay * (2 ** attempt)) + random.uniform(0.05, 0.25)
                        logger.warning(
                            "Transient error streaming %s (attempt %d/%d): %s. Retrying in %.2fs...",
                            model, attempt + 1, self.max_retries + 1, type(exc).__name__, delay,
                        )
                        time.sleep(delay)
            logger.warning("Model %s unavailable for streaming: %s", model, type(last_error).__name__)

        raise LLMServiceUnavailableError(
            "The AI model is temporarily unavailable. Please try again in a moment."
        ) from last_error

    def chat_round(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Iterator[tuple[str, Any]]:
        """One model turn with optional function calling, streamed.

        Yields ("token", text) for answer text as it arrives, then exactly one ("message", dict): the full
        assistant message, including any tool_calls, ready to append to `messages` for the next round.
        Retries and fallback apply only before the first token, as in stream_response.
        """
        self._require_api_key()
        models = [self.model_name]
        if self.fallback_model_name and self.fallback_model_name != self.model_name:
            models.append(self.fallback_model_name)

        last_error: Exception | None = None
        for model in models:
            for attempt in range(self.max_retries + 1):
                started = False
                chunks: list[Any] = []
                generation = tracing.generation("agent round", model, messages)
                try:
                    kwargs: dict[str, Any] = {"model": model, "messages": messages, "api_key": self.api_key,
                                              "stream": True}
                    if tools:
                        kwargs["tools"] = tools
                    for chunk in completion(**kwargs):
                        if cancel_event is not None and cancel_event.is_set():
                            break
                        chunks.append(chunk)
                        if delta := delta_text(chunk):
                            started = True
                            yield ("token", delta)
                    built = assemble(chunks)
                    tracing.end_generation(generation, model, built)
                    generation = tracing.NOOP  # ended; an early stop below mustn't end it again
                    yield ("message", built.message)
                    return
                except GeneratorExit:
                    tracing.end_stream(generation, model, chunks, messages)
                    raise
                except Exception as exc:
                    tracing.end_generation(generation, model, error=exc)
                    if started or not is_transient_error(exc):
                        raise
                    last_error = exc
                    if attempt < self.max_retries:
                        delay = (self.base_delay * (2 ** attempt)) + random.uniform(0.05, 0.25)
                        logger.warning("Transient error in chat round with %s: %s", model, type(exc).__name__)
                        time.sleep(delay)
            logger.warning("Model %s unavailable for chat round: %s", model, type(last_error).__name__)

        raise LLMServiceUnavailableError(
            "The AI model is temporarily unavailable. Please try again in a moment."
        ) from last_error
