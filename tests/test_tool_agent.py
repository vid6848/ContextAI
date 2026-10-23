"""Tests for LLM function calling: multi-tool chaining, hybrid routing, citations and cards."""

import copy
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.backend.core.config import settings
from src.backend.main import app

client = TestClient(app)

WEATHER = {"success": True, "location": "Pune, IN", "temperature": 29, "description": "haze"}
CRYPTO = {"success": True, "coin": "ethereum", "price_usd": 2405.1, "change_24h_percent": 0.8}


def call(id_, name, **args):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class ScriptedModel:
    """Stands in for LLMClient.chat_round: plays one scripted reply per round and records what it saw."""

    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.seen = []  # (messages, tools) per round

    def __call__(self, messages, tools=None, cancel_event=None):
        self.seen.append((copy.deepcopy(messages), tools))
        reply = self.rounds.pop(0)
        if isinstance(reply, str):
            for word in reply.split(" "):
                yield ("token", word + " ")
            yield ("message", {"role": "assistant", "content": reply})
        else:
            yield ("message", {"role": "assistant", "content": None, "tool_calls": reply})


def stream(payload):
    events = []
    with client.stream("POST", "/api/v1/chat/stream", json=payload) as resp:
        name = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[6:])))
    return events


def done_of(events):
    return next(d for n, d in events if n == "done")


def final_steps(events):
    """Last state of every step, in first-seen order."""
    steps = {}
    for n, d in events:
        if n == "step":
            steps[d["id"]] = d
    return list(steps.values())


@pytest.fixture
def llm_mode(monkeypatch):
    monkeypatch.setattr(settings, "router_mode", "llm")


@patch("src.backend.tools.crypto.CryptoTool.get_price", return_value=CRYPTO)
@patch("src.backend.tools.weather.WeatherTool.get_weather", return_value=WEATHER)
def test_model_chains_parallel_tools_then_answers(mock_weather, mock_crypto, llm_mode):
    model = ScriptedModel(
        [call("c1", "get_weather", city="Pune"), call("c2", "get_crypto_price", coin="eth")],
        "It's 29°C and hazy in Pune, and ETH is at $2,405.",
    )
    with patch("src.backend.llm.client.LLMClient.chat_round", side_effect=model):
        events = stream({"message": "Weather in Pune and the ETH price?", "user_id": "ag1"})

    mock_weather.assert_called_once_with("Pune")
    mock_crypto.assert_called_once_with("eth")

    steps = final_steps(events)
    labels = [s["label"] for s in steps]
    assert labels[1].startswith("Letting the model choose tools")
    assert "Decided to use OpenWeather and CoinGecko" in labels
    tool_ids = [s["id"] for s in steps if s["id"].startswith("tool:")]
    assert tool_ids == ["tool:get_weather:0.0", "tool:get_crypto_price:0.1"]
    assert all(s["status"] == "done" for s in steps)

    text = "".join(d["text"] for n, d in events if n == "token")
    assert text.strip() == "It's 29°C and hazy in Pune, and ETH is at $2,405."

    done = done_of(events)
    assert done["tools_used"] == ["get_weather", "get_crypto_price"]
    assert [c["tool"] for c in done["cards"]] == ["weather", "crypto"]

    # Round 2 received the assistant's tool calls and both results, matched by id
    round2_messages, round2_tools = model.seen[1]
    tool_msgs = [m for m in round2_messages if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2"]
    assert json.loads(tool_msgs[0]["content"])["location"] == "Pune, IN"
    assert round2_tools  # tools still offered until the round limit

    # Cards and steps persist with the answer
    cid = events[0][1]["conversation_id"]
    saved = client.get(f"/api/v1/conversations/{cid}/messages", params={"user_id": "ag1"}).json()["messages"]
    assert [c["tool"] for c in saved[1]["metadata"]["cards"]] == ["weather", "crypto"]


@patch("src.backend.tools.web_search.TavilySearchTool.search")
def test_sources_are_numbered_across_tool_calls(mock_search, llm_mode):
    import io

    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "Our refund policy allows returns within 30 days.")
    files = {"file": ("policy.pdf", io.BytesIO(doc.write()), "application/pdf")}
    client.post("/api/v1/documents/upload", params={"user_id": "ag2"}, files=files)

    mock_search.return_value = {"success": True, "results": [
        {"title": "Consumer law", "url": "https://law.example/returns", "content": "Shops must accept returns..."},
        {"title": "Guide", "url": "https://guide.example", "content": "Typical windows are 14-30 days."},
    ]}
    model = ScriptedModel(
        [call("a", "search_documents", query="refund policy"), call("b", "web_search", query="return law")],
        "Your policy allows 30 days [1], which matches common practice [3].",
    )
    with patch("src.backend.llm.client.LLMClient.chat_round", side_effect=model):
        events = stream({"message": "Is our refund window normal?", "user_id": "ag2"})

    sources = done_of(events)["sources"]
    assert [(s["n"], s["kind"]) for s in sources] == [(1, "document"), (2, "web"), (3, "web")]
    assert sources[0]["document"] == "policy.pdf"
    # The model saw the same numbers it was told to cite
    tool_msgs = [m for m in model.seen[1][0] if m["role"] == "tool"]
    assert json.loads(tool_msgs[0]["content"])["passages"][0]["n"] == 1
    assert [r["n"] for r in json.loads(tool_msgs[1]["content"])["results"]] == [2, 3]
    # Web results carry today's date so stale "upcoming" articles aren't taken at face value
    assert json.loads(tool_msgs[1]["content"])["today"]


@patch("src.backend.tools.calculator.CalculatorTool.evaluate", return_value={"success": True, "result": 4})
def test_round_limit_forces_an_answer(_calc, llm_mode, monkeypatch):
    monkeypatch.setattr(settings, "max_tool_rounds", 2)
    model = ScriptedModel(
        [call("1", "calculator", expression="2+2")],
        [call("2", "calculator", expression="2+2")],
        "It's 4.",
    )
    with patch("src.backend.llm.client.LLMClient.chat_round", side_effect=model):
        events = stream({"message": "add two and two, carefully", "user_id": "ag3"})

    assert [tools is not None for _, tools in model.seen] == [True, True, False]
    assert done_of(events)["tools_used"] == ["calculator", "calculator"]


@patch("src.backend.tools.crypto.CryptoTool.get_price", return_value={"success": False, "error": "Rate limited."})
def test_failed_tool_is_an_error_step_and_the_model_still_answers(_crypto, llm_mode):
    model = ScriptedModel([call("x", "get_crypto_price", coin="bitcoin")], "I couldn't fetch the price right now.")
    with patch("src.backend.llm.client.LLMClient.chat_round", side_effect=model):
        events = stream({"message": "bitcoin price?", "user_id": "ag4"})

    tool_step = next(s for s in final_steps(events) if s["id"].startswith("tool:"))
    assert tool_step["status"] == "error"
    assert "Rate limited" in tool_step["label"]
    assert done_of(events)["cards"] == []


def test_direct_answer_without_tools(llm_mode):
    model = ScriptedModel("Hello! How can I help?")
    with patch("src.backend.llm.client.LLMClient.chat_round", side_effect=model):
        events = stream({"message": "hi there", "user_id": "ag5"})
    plan = next(s for s in final_steps(events) if s["id"] == "plan:0")
    assert plan["label"] == "Answering directly"
    assert done_of(events)["tools_used"] == []


def test_history_and_memories_reach_the_model_as_chat_messages(llm_mode):
    with patch("src.backend.llm.client.LLMClient.chat_round", side_effect=ScriptedModel("Noted.")):
        first = stream({"message": "My name is Asha and I live in Pune", "user_id": "ag6"})
    cid = first[0][1]["conversation_id"]

    model = ScriptedModel("You're Asha.")
    with patch("src.backend.llm.client.LLMClient.chat_round", side_effect=model):
        stream({"message": "What's my name?", "user_id": "ag6", "conversation_id": cid})

    messages = model.seen[0][0]
    assert messages[0]["role"] == "system" and "Asha" in messages[0]["content"]  # long-term memory
    assert [m["role"] for m in messages[1:]] == ["user", "assistant", "user"]
    assert messages[1]["content"] == "My name is Asha and I live in Pune"


def test_hybrid_uses_classifier_when_confident(monkeypatch):
    monkeypatch.setattr(settings, "router_mode", "hybrid")
    monkeypatch.setattr(settings, "hybrid_confidence_threshold", 0.0)
    with patch("src.backend.llm.client.LLMClient.chat_round") as chat_round, \
         patch("src.backend.llm.client.LLMClient.stream_response", return_value=iter(["ok"])):
        events = stream({"message": "hello", "user_id": "ag7"})
    chat_round.assert_not_called()
    assert not any(s["id"].startswith("plan:") for s in final_steps(events))


def test_hybrid_hands_low_confidence_to_the_model(monkeypatch):
    monkeypatch.setattr(settings, "router_mode", "hybrid")
    monkeypatch.setattr(settings, "hybrid_confidence_threshold", 1.01)
    model = ScriptedModel("Sure.")
    with patch("src.backend.llm.client.LLMClient.chat_round", side_effect=model):
        events = stream({"message": "hello", "user_id": "ag8"})
    assert len(model.seen) == 1
    assert any(s["id"] == "plan:0" for s in final_steps(events))
