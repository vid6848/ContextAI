"""Tests for server-side conversations and per-conversation history."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.backend.main import app
from src.backend.memory.sql_db import SQLiteManager

client = TestClient(app)


def test_conversation_crud_and_user_isolation():
    """Create, list, rename and delete conversations; other users cannot see or touch them."""
    created = client.post("/api/v1/conversations", json={"user_id": "alice"}).json()
    assert created["title"] == "New conversation"

    listed = client.get("/api/v1/conversations", params={"user_id": "alice"}).json()["conversations"]
    assert [c["id"] for c in listed] == [created["id"]]
    assert client.get("/api/v1/conversations", params={"user_id": "bob"}).json()["conversations"] == []

    path = f"/api/v1/conversations/{created['id']}"
    assert client.patch(path, params={"user_id": "bob"}, json={"title": "Hijack"}).status_code == 404
    assert client.patch(path, params={"user_id": "alice"}, json={"title": "Trip plans"}).status_code == 200
    assert client.get(f"{path}/messages", params={"user_id": "alice"}).json()["conversation"]["title"] == "Trip plans"

    assert client.delete(path, params={"user_id": "bob"}).status_code == 404
    assert client.delete(path, params={"user_id": "alice"}).status_code == 200
    assert client.get(f"{path}/messages", params={"user_id": "alice"}).status_code == 404


@patch("src.backend.llm.client.LLMClient.generate_response")
def test_chat_creates_conversation_and_persists_messages(mock_generate):
    """A chat without conversation_id creates one, titled from the message, with both turns stored."""
    mock_generate.return_value = "Hi there!"

    data = client.post("/api/v1/chat", json={"message": "Hello ContextAI, plan my week", "user_id": "u1"}).json()
    conversation_id = data["conversation_id"]

    history = client.get(f"/api/v1/conversations/{conversation_id}/messages", params={"user_id": "u1"}).json()
    assert history["conversation"]["title"] == "Hello ContextAI, plan my week"
    assert [(m["role"], m["message"]) for m in history["messages"]] == [
        ("user", "Hello ContextAI, plan my week"),
        ("assistant", "Hi there!"),
    ]
    assert history["messages"][1]["metadata"]["intent"]


@patch("src.backend.llm.client.LLMClient.generate_response")
def test_new_conversation_does_not_see_other_conversation_history(mock_generate):
    """Regression: a new chat must not receive messages from a previous chat as context."""
    mock_generate.return_value = "Noted."
    first = client.post("/api/v1/chat", json={"message": "My secret codeword is pineapple", "user_id": "u2"}).json()

    client.post("/api/v1/chat", json={"message": "What did I just tell you?", "user_id": "u2"})
    context = mock_generate.call_args.kwargs.get("context") or ""
    assert "pineapple" not in context.split("Recent Conversation History:")[-1]

    client.post(
        "/api/v1/chat",
        json={"message": "What did I just tell you?", "user_id": "u2", "conversation_id": first["conversation_id"]},
    )
    assert "pineapple" in mock_generate.call_args.kwargs["context"]


def test_chat_with_unknown_conversation_returns_404():
    response = client.post(
        "/api/v1/chat", json={"message": "hello", "user_id": "u3", "conversation_id": "does-not-exist"}
    )
    assert response.status_code == 404


def test_legacy_database_is_migrated(tmp_path):
    """Databases created before conversations existed gain the new columns without losing rows."""
    import sqlite3

    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE conversation_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, "
            "role TEXT NOT NULL, message TEXT NOT NULL, timestamp TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO conversation_history (user_id, role, message, timestamp) VALUES ('a', 'user', 'old', 't')"
        )

    manager = SQLiteManager(db_path=str(db))
    assert manager.get_recent_messages(user_id="a")[0]["message"] == "old"
    conversation = manager.create_conversation(user_id="a")
    manager.save_message(user_id="a", role="user", message="new", conversation_id=conversation["id"])
    assert [m["message"] for m in manager.get_conversation_messages(conversation["id"], "a")] == ["new"]
