"""Tests for LLM-extracted long-term memory and the memories API."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.backend.agent.graph import get_default_vector_store
from src.backend.core.config import settings
from src.backend.main import app
from src.backend.memory.extractor import _parse_operations, update_long_term_memory, worth_checking
from src.backend.memory.vector_store import ChromaMemoryStore

client = TestClient(app)


def llm_returning(operations):
    llm = MagicMock()
    llm.generate_response.return_value = json.dumps({"operations": operations})
    return llm


@pytest.fixture
def store(tmp_path):
    return ChromaMemoryStore(persist_dir=str(tmp_path / "mem"), collection_name="extract_mem")


def test_prefilter_skips_messages_that_are_not_about_the_user():
    assert not worth_checking("What's the weather in Tokyo?")
    assert not worth_checking("hi")
    assert worth_checking("I moved to Berlin last month")
    assert worth_checking("Please forget where I work")


def test_parse_operations_tolerates_code_fences_and_garbage():
    fenced = '```json\n{"operations": [{"op": "add", "fact": "x"}]}\n```'
    assert _parse_operations(fenced) == [{"op": "add", "fact": "x"}]
    assert _parse_operations("not json") == []
    assert _parse_operations('{"operations": "nope"}') == []


def test_adds_new_facts_and_skips_irrelevant_messages(store):
    llm = llm_returning([{"op": "add", "fact": "Prefers answers with Python examples"}])
    changes = update_long_term_memory(llm, store, "u1", "I prefer answers with Python examples please")
    assert [(c["op"], c["fact"]) for c in changes] == [("add", "Prefers answers with Python examples")]
    assert [m["fact"] for m in store.list_memories("u1")] == ["Prefers answers with Python examples"]

    llm.generate_response.reset_mock()
    assert update_long_term_memory(llm, store, "u1", "What's 2+2?") == []
    llm.generate_response.assert_not_called()


def test_updates_and_deletes_existing_memories_and_shows_them_to_the_model(store):
    pune = store.add_memory("Lives in Pune", "u2")
    job = store.add_memory("Works at Acme", "u2")
    llm = llm_returning([
        {"op": "update", "id": pune, "fact": "Lives in Berlin (moved from Pune)"},
        {"op": "delete", "id": job},
    ])
    changes = update_long_term_memory(llm, store, "u2", "I moved to Berlin, and forget where I work")

    assert {(c["op"], c["fact"]) for c in changes} == {
        ("update", "Lives in Berlin (moved from Pune)"), ("delete", "Works at Acme")
    }
    assert [m["fact"] for m in store.list_memories("u2")] == ["Lives in Berlin (moved from Pune)"]
    prompt = llm.generate_response.call_args.kwargs["message"][1]["content"]
    assert f"[{pune}] Lives in Pune" in prompt


def test_ignores_unknown_ids_duplicates_and_other_users_memories(store):
    existing = store.add_memory("Has a dog named Miso", "u3")
    other = store.add_memory("Lives in Lima", "someone-else")
    llm = llm_returning([
        {"op": "add", "fact": "Has a dog named Miso"},            # duplicate
        {"op": "update", "id": other, "fact": "hijack"},           # not shown to the model / not theirs
        {"op": "delete", "id": "mem_doesnotexist"},
    ])
    assert update_long_term_memory(llm, store, "u3", "My dog Miso is great") == []
    assert [m["id"] for m in store.list_memories("u3")] == [existing]
    assert store.list_memories("someone-else")[0]["fact"] == "Lives in Lima"


def test_extraction_failures_never_break_a_turn(store):
    llm = MagicMock()
    llm.generate_response.side_effect = RuntimeError("quota")
    assert update_long_term_memory(llm, store, "u4", "I am vegetarian") == []


def test_stream_emits_memory_event_and_saves_it_on_the_reply(monkeypatch):
    monkeypatch.setattr(settings, "memory_mode", "llm")

    def fake_generate(message=None, **_):
        system = message[0]["content"] if isinstance(message, list) else ""
        if system.startswith("You maintain the long-term memory"):
            return json.dumps({"operations": [{"op": "add", "fact": "Is allergic to peanuts"}]})
        return "Peanut allergy note"  # chat title

    with patch("src.backend.llm.client.LLMClient.stream_response", return_value=iter(["Got it."])), \
         patch("src.backend.llm.client.LLMClient.generate_response", side_effect=fake_generate):
        events = []
        payload = {"message": "I am allergic to peanuts", "user_id": "m1"}
        with client.stream("POST", "/api/v1/chat/stream", json=payload) as r:
            name = None
            for line in r.iter_lines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    events.append((name, json.loads(line[6:])))

    memory = next(d for n, d in events if n == "memory")
    assert [c["fact"] for c in memory["changes"]] == ["Is allergic to peanuts"]
    cid = events[0][1]["conversation_id"]
    saved = client.get(f"/api/v1/conversations/{cid}/messages", params={"user_id": "m1"}).json()["messages"]
    assert saved[1]["metadata"]["memory"][0]["fact"] == "Is allergic to peanuts"
    assert [m["fact"] for m in get_default_vector_store().list_memories("m1")] == ["Is allergic to peanuts"]


def test_memories_api_crud_and_ownership():
    added = client.post("/api/v1/memories", params={"user_id": "m2"}, json={"fact": "Prefers metric units"}).json()
    url = f"/api/v1/memories/{added['id']}"

    listed = client.get("/api/v1/memories", params={"user_id": "m2"}).json()["memories"]
    assert [(m["fact"], m["source"]) for m in listed] == [("Prefers metric units", "manual")]

    assert client.patch(url, params={"user_id": "intruder"}, json={"fact": "x"}).status_code == 404
    new_fact = {"fact": "Prefers metric units and 24h time"}
    assert client.patch(url, params={"user_id": "m2"}, json=new_fact).status_code == 200
    assert client.get("/api/v1/memories", params={"user_id": "m2"}).json()["memories"][0]["fact"].endswith("24h time")

    assert client.delete(url, params={"user_id": "intruder"}).status_code == 404
    assert client.delete(url, params={"user_id": "m2"}).status_code == 200
    client.post("/api/v1/memories", params={"user_id": "m2"}, json={"fact": "Has two cats"})
    assert client.delete("/api/v1/memories", params={"user_id": "m2"}).status_code == 200
    assert client.get("/api/v1/memories", params={"user_id": "m2"}).json()["memories"] == []
    assert client.post("/api/v1/memories", params={"user_id": "m2"}, json={"fact": ""}).status_code == 422


def test_new_chat_title_and_memory_share_one_utility_call(monkeypatch):
    """Cost: a new chat about the user needs 1 side call (title + memory), not 2."""
    monkeypatch.setattr(settings, "memory_mode", "llm")
    combined = json.dumps({"title": "Moving to Berlin", "operations": [{"op": "add", "fact": "Lives in Berlin"}]})
    with patch("src.backend.llm.client.LLMClient.stream_response", return_value=iter(["Congrats!"])), \
         patch("src.backend.llm.client.LLMClient.generate_response", return_value=combined) as side:
        payload = {"message": "I just moved to Berlin with my partner last week", "user_id": "m3"}
        with client.stream("POST", "/api/v1/chat/stream", json=payload) as r:
            body = "".join(r.iter_text())

    assert side.call_count == 1
    system = side.call_args.kwargs["message"][0]["content"]
    assert system.startswith("You maintain the long-term memory") and '"title"' in system
    assert '"title": "Moving to Berlin"' in body and "Lives in Berlin" in body


def test_short_impersonal_first_message_needs_no_side_call(monkeypatch):
    monkeypatch.setattr(settings, "memory_mode", "llm")
    with patch("src.backend.llm.client.LLMClient.stream_response", return_value=iter(["18°C"])), \
         patch("src.backend.llm.client.LLMClient.generate_response") as side:
        with client.stream("POST", "/api/v1/chat/stream", json={"message": "Weather in Tokyo?", "user_id": "m4"}) as r:
            "".join(r.iter_text())
    side.assert_not_called()


def test_side_tasks_use_a_separate_utility_model(monkeypatch):
    from src.backend.agent.graph import get_default_utility_llm

    monkeypatch.setattr(settings, "utility_model_name", "")
    llm = get_default_utility_llm()
    assert llm.model_name.endswith(settings.fallback_model_name)
    assert llm.fallback_model_name.endswith(settings.model_name)
