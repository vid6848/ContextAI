"""LiteLLM client wrapper for Gemini and supported models with retry and fallback resilience."""

import logging
import random
import threading
import time
from collections.abc import Iterator
from typing import Any

import litellm

from src.backend.core.config import settings

logger = logging.getLogger(__name__)


class LLMServiceUnavailableError(Exception):
    """Raised when LLM service remains unavailable after bounded retries and fallback attempts."""

    pass


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


def is_transient_error(exc: Exception) -> bool:
    """Determine whether an error is transient (e.g. 503, rate limit, timeout) and safe to retry."""
    # Never retry authentication, permission, or malformed request errors
    if isinstance(
        exc,
        (
            ValueError,
            litellm.AuthenticationError,
            litellm.PermissionDeniedError,
            litellm.BadRequestError,
            litellm.NotFoundError,
        ),
    ):
        return False

    status_code = getattr(exc, "status_code", None)
    if status_code in (400, 401, 403, 404):
        return False
    if status_code in (429, 502, 503, 504):
        return True

    if isinstance(
        exc,
        (
            litellm.ServiceUnavailableError,
            litellm.RateLimitError,
            litellm.APIConnectionError,
        ),
    ):
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
    """Client wrapper for LiteLLM completion calls to Gemini with bounded retries and fallback."""

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
        """Call litellm.completion with bounded exponential backoff and jitter."""
        call_kwargs: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "api_key": self.api_key,
            **kwargs,
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = litellm.completion(**call_kwargs)
                content = response.choices[0].message.content
                return content or ""
            except Exception as exc:
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
        """Call the model via LiteLLM with transient retry logic and fallback model support."""
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
                try:
                    stream = litellm.completion(
                        model=model, messages=messages, api_key=self.api_key, stream=True, **kwargs
                    )
                    for chunk in stream:
                        if cancel_event is not None and cancel_event.is_set():
                            return
                        delta = chunk.choices[0].delta.content if chunk.choices else None
                        if delta:
                            started = True
                            yield delta
                    return
                except Exception as exc:
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
