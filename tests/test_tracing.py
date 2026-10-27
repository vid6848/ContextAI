"""Tests for Langfuse tracing: a chat turn becomes one trace, and 👍/👎 become scores on it."""

import functools
import json
from unittest.mock import MagicMock
from uuid import uuid4

import litellm
import pytest
from fastapi.testclient import TestClient
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.backend.core import tracing
from src.backend.core.config import settings
from src.backend.main import app

client = TestClient(app)


@pytest.fixture
def traced(monkeypatch):
    """Tracing on, spans kept in memory, and LiteLLM answering with a canned (but real) response."""
    exporter = InMemorySpanExporter()
    langfuse = Langfuse(
        public_key=f"pk-lf-{uuid4().hex}",  # Langfuse shares one exporter per key
        secret_key="sk-lf-test", base_url="http://localhost:9",
        span_exporter=exporter, tracer_provider=TracerProvider(),
    )
    monkeypatch.setattr(langfuse, "create_score", MagicMock())
    tracing.configure(langfuse)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(litellm, "completion", functools.partial(litellm.completion, mock_response="15 × 4 = 60."))
    yield langfuse, exporter
    tracing.configure(None)


def _chat_stream(payload: dict) -> dict:
    with client.stream("POST", "/api/v1/chat/stream", json=payload) as resp:
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]
    events = [json.loads(line[len("data: "):]) for line in lines]
    return next(e for e in events if "assistant_message_id" in e) | {"conversation_id": events[0]["conversation_id"]}


def test_a_turn_is_one_trace_with_steps_tools_and_the_model_call(traced):
    langfuse, exporter = traced
    done = _chat_stream({"message": "calculate 15 * 4", "user_id": "tracer"})
    langfuse.flush()
    spans = {s.name: s for s in exporter.get_finished_spans()}

    assert {"chat", "memory", "intent", "tool:calculator", "answer"} <= spans.keys()
    assert len({s.context.trace_id for s in spans.values()}) == 1  # nested, not scattered traces
    attrs = lambda name: spans[name].attributes  # noqa: E731
    assert attrs("chat")["session.id"] == done["conversation_id"] and attrs("chat")["user.id"] == "tracer"
    assert attrs("tool:calculator")["langfuse.observation.type"] == "tool"
    assert attrs("answer")["langfuse.observation.type"] == "generation"
    assert json.loads(attrs("answer")["langfuse.observation.usage_details"])["output"] > 0


def test_feedback_becomes_a_score_on_the_answer_trace(traced):
    langfuse, exporter = traced
    done = _chat_stream({"message": "calculate 15 * 4", "user_id": "rater"})
    langfuse.flush()
    trace_id = format(next(s for s in exporter.get_finished_spans() if s.name == "chat").context.trace_id, "032x")

    url = f"/api/v1/conversations/{done['conversation_id']}/messages/{done['assistant_message_id']}/feedback"
    assert client.put(url, params={"user_id": "rater"}, json={"rating": "down"}).status_code == 200
    score = langfuse.create_score.call_args.kwargs
    assert score["trace_id"] == trace_id and score["value"] == 0 and score["name"] == "user-feedback"


def test_tracing_is_off_without_keys():
    assert tracing.client() is None
    with tracing.turn("u", "c", "hi") as trace, tracing.span("step") as step:
        assert trace.trace_id is None and step.update(output=1) is step
    tracing.score_feedback("abc", "up")  # no client, no error
