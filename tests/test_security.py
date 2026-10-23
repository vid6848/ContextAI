"""Tests for user isolation, rate limiting, upload limits and error hygiene."""

import io
from unittest.mock import patch

import pymupdf
import requests
from fastapi.testclient import TestClient

from src.backend.agent.graph import get_default_vector_store
from src.backend.core.config import settings
from src.backend.main import app
from src.backend.tools.weather import WeatherTool

client = TestClient(app)


def _pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), text)
    data = doc.write()
    doc.close()
    return data


@patch("src.backend.llm.client.LLMClient.generate_response", return_value="ok")
def test_chat_is_rate_limited_per_client(_mock, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_chat_per_minute", 2)
    for _ in range(2):
        assert client.post("/api/v1/chat", json={"message": "hi"}).status_code == 200
    blocked = client.post("/api/v1/chat", json={"message": "hi"})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


def test_upload_rejects_oversized_files(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    files = {"file": ("big.pdf", io.BytesIO(_pdf_bytes("x")), "application/pdf")}
    assert client.post("/api/v1/documents/upload", files=files).status_code == 413


def test_upload_rejects_non_pdf_content_with_pdf_extension():
    files = {"file": ("fake.pdf", io.BytesIO(b"MZ\x90\x00 not a pdf"), "application/pdf")}
    resp = client.post("/api/v1/documents/upload", files=files)
    assert resp.status_code == 400
    assert "not a valid PDF" in resp.json()["detail"]


def test_uploaded_documents_are_private_to_their_user():
    files = {"file": ("notes.pdf", io.BytesIO(_pdf_bytes("Alice's private notes")), "application/pdf")}
    resp = client.post("/api/v1/documents/upload", params={"user_id": "alice"}, files=files)
    assert resp.status_code == 200
    assert resp.json()["document_name"] == "notes.pdf"

    assert client.get("/api/v1/documents", params={"user_id": "alice"}).json()["total_chunks"] >= 1
    assert client.get("/api/v1/documents", params={"user_id": "bob"}).json()["total_chunks"] == 0


def test_invalid_user_ids_are_rejected():
    assert client.get("/api/v1/conversations", params={"user_id": "a' OR 1=1 --"}).status_code == 422
    assert client.post("/api/v1/chat", json={"message": "hi", "user_id": "x" * 65}).status_code == 422


def test_clear_memory_also_removes_long_term_memories():
    store = get_default_vector_store()
    store.add_memory("I am allergic to peanuts", user_id="carol")
    store.add_memory("I love hiking", user_id="dave")

    assert client.post("/api/v1/memory/clear", json={"user_id": "carol"}).status_code == 200
    assert store.get_relevant_memories("allergies", user_id="carol") == []
    assert store.get_relevant_memories("hobbies", user_id="dave") == ["I love hiking"]


@patch("src.backend.llm.client.LLMClient.generate_response")
def test_unexpected_errors_do_not_leak_details(mock_generate):
    mock_generate.side_effect = RuntimeError("upstream said: key=sk-SECRET123 at /internal/path")
    resp = client.post("/api/v1/chat", json={"message": "hello there"})
    assert resp.status_code == 502
    assert "SECRET123" not in resp.text
    assert "/internal/path" not in resp.text


@patch("src.backend.tools.weather.requests.get")
def test_tool_network_errors_do_not_leak_api_keys(mock_get, monkeypatch):
    monkeypatch.setattr(settings, "openweather_api_key", "OWKEY123")
    mock_get.side_effect = requests.ConnectionError("Max retries exceeded with url: /weather?q=Pune&appid=OWKEY123")
    result = WeatherTool().get_weather("Pune")
    assert result["success"] is False
    assert "OWKEY123" not in result["error"]
