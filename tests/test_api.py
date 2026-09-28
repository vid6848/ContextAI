from unittest.mock import patch
from fastapi.testclient import TestClient
from src.backend.main import app

client = TestClient(app)


def test_health_check():
    """Verify health endpoint response."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "ContextAI"}


@patch("src.backend.llm.client.LLMClient.generate_response")
def test_chat_endpoint_valid_response_structure(mock_generate):
    """Verify chat endpoint returns the expected response structure with mocked Claude."""
    mock_generate.return_value = "Mocked Claude response for weather."

    response = client.post("/api/v1/chat", json={"message": "What is the weather forecast for tomorrow?"})
    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "What is the weather forecast for tomorrow?"
    assert data["intent"] == "WEATHER"
    assert isinstance(data["confidence"], float)
    assert 0.0 <= data["confidence"] <= 1.0
    assert data["response"] == "Mocked Claude response for weather."


@patch("src.backend.llm.client.LLMClient.generate_response")
def test_chat_placeholder_endpoint_compatibility(mock_generate):
    """Verify backward compatibility of chat contract."""
    mock_generate.return_value = "Hello! How can I help you today?"

    response = client.post("/api/v1/chat", json={"message": "Hello ContextAI"})
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "intent" in data
    assert "confidence" in data
    assert "message" in data


def test_chat_endpoint_validation_missing_message():
    """Verify chat endpoint returns 422 when required message field is missing."""
    response = client.post("/api/v1/chat", json={})
    assert response.status_code == 422


def test_chat_endpoint_validation_empty_message():
    """Verify chat endpoint returns 422 when message is empty."""
    response = client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_endpoint_validation_invalid_type():
    """Verify chat endpoint returns 422 when message is of invalid type."""
    response = client.post("/api/v1/chat", json={"message": None})
    assert response.status_code == 422


@patch("src.backend.llm.client.LLMClient.generate_response")
def test_chat_endpoint_llm_unavailable_returns_503(mock_generate):
    """Verify chat endpoint returns HTTP 503 with clean detail when LLM service is unavailable."""
    from src.backend.llm.client import LLMServiceUnavailableError
    mock_generate.side_effect = LLMServiceUnavailableError(
        "Gemini is temporarily unavailable. Please try again in a moment."
    )

    response = client.post("/api/v1/chat", json={"message": "Hello"})
    assert response.status_code == 503
    data = response.json()
    assert "Gemini is temporarily unavailable" in data["detail"]


