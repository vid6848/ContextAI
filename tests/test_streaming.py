"""Tests for token streaming, live agent steps, cancellation, and edit/regenerate."""

import json
import threading
from unittest.mock import MagicMock, patch

import litellm
import pytest
from fastapi.testclient import TestClient

from src.backend.agent.graph import get_agent_app, get_default_sql_manager
from src.backend.llm.client import LLMClient, LLMServiceUnavailableError
from src.backend.main import app

client = TestClient(app)
MODEL = "gemini/gemini-3.5-flash-lite"


def _chunk(text: str) -> MagicMock:
    return MagicMock(choices=[MagicMock(delta=MagicMock(content=text))])


def _stream(payload: dict) -> list[tuple[str, dict]]:
    """POST to the SSE endpoint and parse it into (event, data) pairs."""
    events = []
    with client.stream("POST", "/api/v1/chat/stream", json=payload) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        event = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[len("data: "):])))
    return events


# ---------------------------------------------------------------- LLM client streaming


@patch("src.backend.llm.client.time.sleep")
@patch("src.backend.llm.client.litellm.completion")
def test_stream_retries_transient_errors_before_first_token(mock_completion, _sleep):
    err_503 = litellm.ServiceUnavailableError("503 UNAVAILABLE", MODEL, "gemini")
    mock_completion.side_effect = [err_503, iter([_chunk("Hel"), _chunk("lo")])]

    llm = LLMClient(model_name="gemini-3.5-flash-lite", fallback_model_name="", api_key="k", base_delay=0.01)
    assert list(llm.stream_response("hi")) == ["Hel", "lo"]
    assert mock_completion.call_args.kwargs["stream"] is True


@patch("src.backend.llm.client.litellm.completion")
def test_stream_does_not_retry_after_tokens_were_sent(mock_completion):
    def broken_stream():
        yield _chunk("Partial")
        raise litellm.ServiceUnavailableError("503 UNAVAILABLE", MODEL, "gemini")

    mock_completion.return_value = broken_stream()
    llm = LLMClient(model_name="gemini-3.5-flash-lite", fallback_model_name="", api_key="k")
    received = []
    with pytest.raises(litellm.ServiceUnavailableError):
        for delta in llm.stream_response("hi"):
            received.append(delta)
    assert received == ["Partial"]
    assert mock_completion.call_count == 1


@patch("src.backend.llm.client.time.sleep")
@patch("src.backend.llm.client.litellm.completion")
def test_stream_raises_service_unavailable_after_retries_and_fallback(mock_completion, _sleep):
    mock_completion.side_effect = litellm.ServiceUnavailableError("503 UNAVAILABLE", MODEL, "gemini")
    llm = LLMClient(
        model_name="gemini-3.5-flash-lite", fallback_model_name="gemini-3.1-flash-lite", api_key="k", max_retries=1
    )
    with pytest.raises(LLMServiceUnavailableError):
        list(llm.stream_response("hi"))
    assert mock_completion.call_count == 4  # 2 attempts x 2 models


@patch("src.backend.llm.client.litellm.completion")
def test_stream_stops_when_cancelled(mock_completion):
    cancel = threading.Event()
    mock_completion.return_value = iter([_chunk("one "), _chunk("two "), _chunk("three")])
    llm = LLMClient(model_name="gemini-3.5-flash-lite", api_key="k")

    received = []
    for delta in llm.stream_response("count", cancel_event=cancel):
        received.append(delta)
        cancel.set()
    assert received == ["one "]


# ---------------------------------------------------------------- SSE endpoint


@patch("src.backend.llm.client.LLMClient.stream_response")
def test_stream_endpoint_emits_meta_steps_tokens_done(mock_stream):
    mock_stream.return_value = iter(["Hello", " there", "!"])

    events = _stream({"message": "Hello ContextAI", "user_id": "s1"})
    names = [name for name, _ in events]

    assert names[0] == "meta"
    assert names[-1] in {"done", "title"}
    assert "step" in names and "token" in names
    assert names.index("step") < names.index("token")

    text = "".join(data["text"] for name, data in events if name == "token")
    assert text == "Hello there!"

    steps = [data for name, data in events if name == "step"]
    assert {"memory", "intent"} <= {s["id"] for s in steps}
    finished = [s for s in steps if s["status"] == "done"]
    assert all(isinstance(s["duration_ms"], int) for s in finished)

    done = next(data for name, data in events if name == "done")
    conversation_id = events[0][1]["conversation_id"]
    history = client.get(f"/api/v1/conversations/{conversation_id}/messages", params={"user_id": "s1"}).json()
    saved = history["messages"]
    assert [m["id"] for m in saved] == [done["user_message_id"], done["assistant_message_id"]]
    assert saved[1]["message"] == "Hello there!"
    assert {s["id"] for s in saved[1]["metadata"]["steps"]} >= {"memory", "intent"}


@patch("src.backend.tools.weather.WeatherTool.run")
@patch("src.backend.llm.client.LLMClient.stream_response")
def test_stream_endpoint_reports_tool_step_with_input_and_output(mock_stream, mock_weather):
    mock_stream.return_value = iter(["It is sunny."])
    mock_weather.return_value = {"success": True, "city": "Tokyo", "temperature": 21}

    events = _stream({"message": "What is the weather in Tokyo?", "user_id": "s2"})
    tool_steps = [d for n, d in events if n == "step" and d["id"] == "tool:weather"]

    assert [s["status"] for s in tool_steps] == ["running", "done"]
    assert tool_steps[-1]["label"] == "Used OpenWeather"
    assert tool_steps[-1]["detail"]["output"]["city"] == "Tokyo"
    assert next(d for n, d in events if n == "done")["tool_used"] == "weather"


@patch("src.backend.llm.client.LLMClient.stream_response")
def test_stream_endpoint_reports_errors_as_events(mock_stream):
    mock_stream.side_effect = LLMServiceUnavailableError("down")
    events = _stream({"message": "Hello ContextAI", "user_id": "s3"})
    assert events[-1][0] == "error"
    assert "temporarily unavailable" in events[-1][1]["detail"]


def test_cancelled_generation_saves_partial_answer():
    """Stop button: the graph stops reading tokens and saves what was generated, marked as stopped."""
    cancel = threading.Event()

    def fake_stream(cancel_event=None, **_):
        yield "Partial answer"
        cancel_event.set()  # the user pressed Stop; a real client stops on the next chunk

    llm = MagicMock()
    llm.stream_response.side_effect = fake_stream
    agent = get_agent_app(llm_client=llm)
    sql = get_default_sql_manager()
    conversation = sql.create_conversation(user_id="s4")

    final = None
    for mode, chunk in agent.stream(
        {"message": "Tell me a long story", "user_id": "s4", "conversation_id": conversation["id"]},
        stream_mode=["custom", "values"],
        config={"configurable": {"stream": True, "cancel_event": cancel}},
    ):
        if mode == "values":
            final = chunk

    assert final["stopped"] is True
    saved = sql.get_conversation_messages(conversation["id"], "s4")
    assert saved[-1]["message"] == "Partial answer"
    assert saved[-1]["metadata"]["stopped"] is True


# ---------------------------------------------------------------- edit / regenerate


@patch("src.backend.llm.client.LLMClient.generate_response")
def test_regenerate_and_edit_replace_the_tail_of_the_conversation(mock_generate):
    mock_generate.side_effect = ["Answer 1", "Answer 2", "Answer 2 (regenerated)", "Answer to edited"]
    first = client.post("/api/v1/chat", json={"message": "Question one", "user_id": "s5"}).json()
    cid = first["conversation_id"]
    second = client.post("/api/v1/chat", json={"message": "Question two", "user_id": "s5", "conversation_id": cid})
    second = second.json()

    # Regenerate the last answer: resend the same text, replacing from its user message
    client.post(
        "/api/v1/chat",
        json={
            "message": "Question two",
            "user_id": "s5",
            "conversation_id": cid,
            "replace_from_message_id": second["user_message_id"],
        },
    )
    # Edit the first question: everything after it is discarded
    client.post(
        "/api/v1/chat",
        json={
            "message": "Question one, edited",
            "user_id": "s5",
            "conversation_id": cid,
            "replace_from_message_id": first["user_message_id"],
        },
    )

    messages = client.get(f"/api/v1/conversations/{cid}/messages", params={"user_id": "s5"}).json()["messages"]
    assert [m["message"] for m in messages] == ["Question one, edited", "Answer to edited"]


@patch("src.backend.llm.client.LLMClient.generate_response", return_value="ok")
def test_replace_rejects_unknown_or_assistant_messages(_mock):
    first = client.post("/api/v1/chat", json={"message": "Hello", "user_id": "s6"}).json()
    cid = first["conversation_id"]

    for bad_id in (999999, first["assistant_message_id"]):
        resp = client.post(
            "/api/v1/chat",
            json={"message": "x", "user_id": "s6", "conversation_id": cid, "replace_from_message_id": bad_id},
        )
        assert resp.status_code == 404

    resp = client.post("/api/v1/chat", json={"message": "x", "user_id": "s6", "replace_from_message_id": 1})
    assert resp.status_code == 400


@patch("src.backend.llm.client.LLMClient.generate_response")
@patch("src.backend.llm.client.LLMClient.stream_response")
def test_new_chat_gets_llm_title_after_first_answer(mock_stream, mock_generate):
    mock_stream.return_value = iter(["Paris is lovely in spring."])
    mock_generate.return_value = '"Planning a spring trip to Paris."\n'

    events = _stream({"message": "When should I visit Paris?", "user_id": "t1"})
    assert events[-1] == ("title", {"title": "Planning a spring trip to Paris"})

    cid = events[0][1]["conversation_id"]
    listed = client.get("/api/v1/conversations", params={"user_id": "t1"}).json()["conversations"]
    assert listed[0]["id"] == cid and listed[0]["title"] == "Planning a spring trip to Paris"

    # Follow-up turns in an existing chat don't retitle it
    mock_stream.return_value = iter(["Sure."])
    events = _stream({"message": "And Rome?", "user_id": "t1", "conversation_id": cid})
    assert "title" not in [name for name, _ in events]


@patch("src.backend.llm.client.LLMClient.generate_response", side_effect=RuntimeError("quota"))
@patch("src.backend.llm.client.LLMClient.stream_response")
def test_title_failure_keeps_provisional_title(mock_stream, _mock_generate):
    mock_stream.return_value = iter(["ok"])
    events = _stream({"message": "Hello there friend", "user_id": "t2"})
    assert events[-1][0] == "done"
    listed = client.get("/api/v1/conversations", params={"user_id": "t2"}).json()["conversations"]
    assert listed[0]["title"] == "Hello there friend"


@patch("src.backend.tools.crypto.CryptoTool.run")
@patch("src.backend.llm.client.LLMClient.stream_response")
def test_failed_tool_is_reported_as_error_step(mock_stream, mock_crypto):
    mock_stream.return_value = iter(["Sorry, prices are unavailable."])
    mock_crypto.return_value = {"success": False, "error": "Crypto price service is unreachable right now."}

    events = _stream({"message": "What is the price of bitcoin?", "user_id": "s7"})
    final = [d for n, d in events if n == "step" and d["id"] == "tool:crypto"][-1]
    assert final["status"] == "error"
    assert "unreachable" in final["label"]
    assert "failed" not in final


@patch("src.backend.llm.client.LLMClient.stream_response")
def test_attachments_route_to_and_scope_document_search(mock_stream):
    import io

    import pymupdf

    def pdf(text):
        doc = pymupdf.open()
        doc.new_page().insert_text((50, 50), text)
        data = doc.write()
        doc.close()
        return io.BytesIO(data)

    for name, text in [("menu.pdf", "The cafe menu lists espresso and croissants."),
                       ("lease.pdf", "The lease term is twelve months starting in March.")]:
        files = {"file": (name, pdf(text), "application/pdf")}
        assert client.post("/api/v1/documents/upload", params={"user_id": "att"}, files=files).status_code == 200

    mock_stream.return_value = iter(["It covers the lease."])
    # A vague request that the classifier alone wouldn't route to documents
    events = _stream({"message": "what is this about?", "user_id": "att", "attachments": ["lease.pdf"]})

    intent = [d for n, d in events if n == "step" and d["id"] == "intent"][-1]
    assert intent["label"] == "Routed to your attached file"
    done = next(d for n, d in events if n == "done")
    assert done["intent"] == "DOCUMENT"
    assert {s["document"] for s in done["sources"]} == {"lease.pdf"}

    cid = events[0][1]["conversation_id"]
    saved = client.get(f"/api/v1/conversations/{cid}/messages", params={"user_id": "att"}).json()["messages"]
    assert saved[0]["metadata"] == {"attachments": ["lease.pdf"]}


def test_attachment_list_is_validated():
    resp = client.post("/api/v1/chat", json={"message": "hi", "attachments": [f"f{i}.pdf" for i in range(6)]})
    assert resp.status_code == 422
