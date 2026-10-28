"""Langfuse tracing: one trace per chat turn, a span per agent step and a generation per model call.

Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set; every helper is then a no-op, so callers
never need to check. Spans nest through OpenTelemetry's context, which LangGraph carries into the
threads its nodes run on.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from src.backend.core.config import settings

logger = logging.getLogger(__name__)

_client: Any = None
_configured = False


class _NoOp:
    """Stands in for an observation when tracing is off."""

    trace_id = None

    def update(self, **_: Any) -> "_NoOp":
        return self

    def end(self) -> None:
        pass


NOOP = _NoOp()


def configure(client: Any = None) -> None:
    """Use this Langfuse client (tests pass one with an in-memory exporter); None re-reads the settings."""
    global _client, _configured
    _client, _configured = client, client is not None


def client() -> Any:
    """The Langfuse client, created on first use, or None when tracing isn't configured."""
    global _client, _configured
    if not _configured:
        _configured = True
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            from langfuse import Langfuse

            _client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                base_url=settings.langfuse_host,
                environment=settings.app_env,
            )
    return _client


@contextmanager
def _observe(**kwargs: Any) -> Iterator[Any]:
    lf = client()
    if lf is None:
        yield NOOP
        return
    with lf.start_as_current_observation(**kwargs) as observation:
        yield observation


@contextmanager
def turn(user_id: str, conversation_id: str | None, message: str) -> Iterator[Any]:
    """Root of a chat turn's trace, grouped by conversation (session) and user."""
    lf = client()
    if lf is None:
        yield NOOP
        return
    from langfuse import propagate_attributes

    with propagate_attributes(user_id=user_id, session_id=conversation_id, trace_name="chat"):
        with lf.start_as_current_observation(name="chat", as_type="agent", input=message) as root:
            yield root


def span(name: str, kind: str = "span", input: Any = None) -> Any:
    """An agent step; kind is "tool" for tool calls, "retriever" for searches, else "span"."""
    return _observe(name=name, as_type=kind, input=input)


def generation(name: str, model: str, messages: list[Any]) -> Any:
    """Start one model call; finish it with end_generation().

    Not a context manager: streamed calls are generators, and OpenTelemetry context held open across a
    yield can't be detached cleanly when the consumer stops early.
    """
    lf = client()
    if lf is None:
        return NOOP
    return lf.start_observation(name=name, as_type="generation", model=model, input=messages)


def end_generation(observation: Any, model: str, response: Any = None, error: Exception | None = None) -> None:
    """Attach output and token usage from a Completion (streams: rebuilt with assemble), or the error,
    then close the observation. Langfuse prices the call from the model name and usage."""
    if observation is NOOP:
        return
    try:
        if error is not None:
            observation.update(level="ERROR", status_message=f"{type(error).__name__}: {error}"[:500])
        elif response is not None:
            details: dict[str, Any] = {"model": model, "output": response.message}
            if usage := response.usage:
                details["usage_details"] = {
                    "input": usage.get("prompt_tokens") or 0, "output": usage.get("completion_tokens") or 0,
                }
            observation.update(**details)
        observation.end()
    except Exception:
        logger.debug("Couldn't record a generation", exc_info=True)  # tracing must never break an answer


def end_stream(observation: Any, model: str, chunks: list[Any], messages: list[Any]) -> None:
    """end_generation() for a stream, rebuilding the full response from its chunks only when tracing."""
    if observation is NOOP:
        return
    from src.backend.llm.client import assemble

    try:
        built = assemble(chunks) if chunks else None
    except Exception:
        built = None
    end_generation(observation, model, built)


def current_trace_id() -> str | None:
    lf = client()
    return lf.get_current_trace_id() if lf is not None else None


def score_feedback(trace_id: str | None, rating: str | None) -> None:
    """Record 👍 (1) / 👎 (0) on the answer's trace. Clearing feedback keeps the last score."""
    lf = client()
    if lf is None or not trace_id or rating is None:
        return
    try:
        lf.create_score(
            name="user-feedback", value=1 if rating == "up" else 0, trace_id=trace_id, data_type="BOOLEAN",
            score_id=f"{trace_id}-feedback",  # same id: changing the vote updates the score
        )
    except Exception:
        logger.warning("Couldn't send feedback to Langfuse", exc_info=True)


def flush() -> None:
    if _client is not None:
        _client.flush()
