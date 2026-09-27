"""Tests for LLM client integration."""

from unittest.mock import MagicMock, patch
from src.backend.llm.client import LLMClient


@patch("src.backend.llm.client.litellm.completion")
def test_llm_client_generate_response_mocked(mock_completion):
    """Verify LLMClient calls litellm with expected system prompt and returns content."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Hello! I am Claude."))]
    mock_completion.return_value = mock_response

    client = LLMClient(model_name="claude-3-5-sonnet-20241022", api_key="test-anthropic-key")
    result = client.generate_response(message="Hello there", intent="GENERAL")

    assert result == "Hello! I am Claude."
    mock_completion.assert_called_once()
    call_kwargs = mock_completion.call_args.kwargs

    assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
    assert call_kwargs["api_key"] == "test-anthropic-key"
    messages = call_kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "GENERAL" in messages[0]["content"]
    assert "ContextAI" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Hello there"
