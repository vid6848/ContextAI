"""Tests for LLM client integration, reliability, retry with backoff, and fallback handling."""

from unittest.mock import MagicMock, patch
import pytest
import litellm

from src.backend.llm.client import (
    LLMClient,
    LLMServiceUnavailableError,
    is_transient_error,
    normalize_model_name,
)


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

    assert call_kwargs["model"] == "anthropic/claude-3-5-sonnet-20241022"
    assert call_kwargs["api_key"] == "test-anthropic-key"
    messages = call_kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "GENERAL" in messages[0]["content"]
    assert "ContextAI" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Hello there"


def test_normalize_model_name():
    """Verify model names are normalized with provider prefixes correctly."""
    assert normalize_model_name("gemini-3.5-flash-lite") == "gemini/gemini-3.5-flash-lite"
    assert normalize_model_name("gemini/gemini-3.5-flash-lite") == "gemini/gemini-3.5-flash-lite"
    assert normalize_model_name("claude-3-5-sonnet-20241022") == "anthropic/claude-3-5-sonnet-20241022"
    assert normalize_model_name("custom-model") == "custom-model"


def test_is_transient_error_detection():
    """Verify transient vs non-transient error classification."""
    # Transient: 503, 429, timeouts
    svc_unavailable = litellm.ServiceUnavailableError("503 UNAVAILABLE", "gemini/gemini-3.5-flash-lite", "gemini")
    rate_limit = litellm.RateLimitError("429 Rate limit", "gemini/gemini-3.5-flash-lite", "gemini")
    generic_503 = Exception("503 Service Unavailable: This model is currently experiencing high demand.")
    
    assert is_transient_error(svc_unavailable) is True
    assert is_transient_error(rate_limit) is True
    assert is_transient_error(generic_503) is True

    # Non-transient: Auth, bad request, not found, ValueError
    auth_err = litellm.AuthenticationError("401 Invalid API Key", "gemini/gemini-3.5-flash-lite", "gemini")
    bad_req = litellm.BadRequestError("400 Bad Request", "gemini/gemini-3.5-flash-lite", "gemini")
    val_err = ValueError("API key missing")

    assert is_transient_error(auth_err) is False
    assert is_transient_error(bad_req) is False
    assert is_transient_error(val_err) is False


@patch("src.backend.llm.client.time.sleep")
@patch("src.backend.llm.client.litellm.completion")
def test_llm_client_successful_retry(mock_completion, mock_sleep):
    """Verify LLMClient retries on transient 503 and returns on subsequent success."""
    err_503 = litellm.ServiceUnavailableError("503 UNAVAILABLE", "gemini/gemini-3.5-flash-lite", "gemini")
    success_resp = MagicMock()
    success_resp.choices = [MagicMock(message=MagicMock(content="Success after retry."))]

    # 1st call fails, 2nd call succeeds
    mock_completion.side_effect = [err_503, success_resp]

    client = LLMClient(
        model_name="gemini-3.5-flash-lite",
        fallback_model_name="",
        api_key="test-gemini-key",
        max_retries=2,
        base_delay=0.01,
    )
    result = client.generate_response(message="Test query")

    assert result == "Success after retry."
    assert mock_completion.call_count == 2
    assert mock_sleep.call_count == 1


@patch("src.backend.llm.client.time.sleep")
@patch("src.backend.llm.client.litellm.completion")
def test_llm_client_final_failure_after_retries(mock_completion, mock_sleep):
    """Verify LLMClient exhausts bounded retries and raises LLMServiceUnavailableError cleanly."""
    err_503 = litellm.ServiceUnavailableError(
        "503 UNAVAILABLE: Model is experiencing high demand",
        "gemini/gemini-3.5-flash-lite",
        "gemini",
    )
    mock_completion.side_effect = err_503

    # Client without fallback model
    client = LLMClient(
        model_name="gemini-3.5-flash-lite",
        fallback_model_name="",
        api_key="test-gemini-key",
        max_retries=2,
        base_delay=0.01,
    )

    with pytest.raises(LLMServiceUnavailableError) as exc_info:
        client.generate_response(message="Test query")

    assert "Gemini is temporarily unavailable. Please try again in a moment." in str(exc_info.value)
    # 1 initial attempt + 2 retries = 3 calls
    assert mock_completion.call_count == 3
    assert mock_sleep.call_count == 2


@patch("src.backend.llm.client.time.sleep")
@patch("src.backend.llm.client.litellm.completion")
def test_llm_client_final_failure_after_retries_and_fallback(mock_completion, mock_sleep):
    """Verify both primary and fallback models exhaust bounded retries before failing."""
    err_503 = litellm.ServiceUnavailableError(
        "503 UNAVAILABLE: Model is experiencing high demand",
        "gemini/gemini-3.5-flash-lite",
        "gemini",
    )
    mock_completion.side_effect = err_503

    client = LLMClient(
        model_name="gemini-3.5-flash-lite",
        fallback_model_name="gemini-3.1-flash-lite",
        api_key="test-gemini-key",
        max_retries=2,
        base_delay=0.01,
    )

    with pytest.raises(LLMServiceUnavailableError) as exc_info:
        client.generate_response(message="Test query")

    assert "Gemini is temporarily unavailable. Please try again in a moment." in str(exc_info.value)
    # 3 calls on primary + 3 calls on fallback = 6 calls total
    assert mock_completion.call_count == 6
    assert mock_sleep.call_count == 4


@patch("src.backend.llm.client.time.sleep")
@patch("src.backend.llm.client.litellm.completion")
def test_llm_client_fallback_model_success(mock_completion, mock_sleep):
    """Verify that when primary model fails after retries, fallback model is invoked and succeeds."""
    err_503 = litellm.ServiceUnavailableError(
        "503 UNAVAILABLE",
        "gemini/gemini-3.5-flash-lite",
        "gemini",
    )
    fallback_resp = MagicMock()
    fallback_resp.choices = [MagicMock(message=MagicMock(content="Response from fallback model."))]

    # Primary model fails 3 times (initial + 2 retries), then fallback succeeds on 1st attempt
    mock_completion.side_effect = [err_503, err_503, err_503, fallback_resp]

    client = LLMClient(
        model_name="gemini-3.5-flash-lite",
        fallback_model_name="gemini-3.1-flash-lite",
        api_key="test-gemini-key",
        max_retries=2,
        base_delay=0.01,
    )

    result = client.generate_response(message="Test query")

    assert result == "Response from fallback model."
    assert mock_completion.call_count == 4

    # Verify 4th call used the fallback model
    last_call_kwargs = mock_completion.call_args_list[-1].kwargs
    assert last_call_kwargs["model"] == "gemini/gemini-3.1-flash-lite"


@patch("src.backend.llm.client.litellm.completion")
def test_llm_client_auth_error_not_retried(mock_completion):
    """Verify authentication errors fail immediately without retrying."""
    auth_err = litellm.AuthenticationError("401 Invalid API key", "gemini/gemini-3.5-flash-lite", "gemini")
    mock_completion.side_effect = auth_err

    client = LLMClient(
        model_name="gemini-3.5-flash-lite",
        fallback_model_name="gemini-3.1-flash-lite",
        api_key="bad-key",
        max_retries=2,
    )

    with pytest.raises(litellm.AuthenticationError):
        client.generate_response(message="Test query")

    # MUST be called only once — no retries for auth errors
    assert mock_completion.call_count == 1


@patch("src.backend.llm.client.litellm.completion")
def test_llm_client_missing_key_raises_without_calling_api(mock_completion):
    """Verify missing API key raises ValueError immediately."""
    client = LLMClient(
        model_name="gemini-3.5-flash-lite",
        api_key="",
    )

    with pytest.raises(ValueError) as exc_info:
        client.generate_response(message="Test query")

    assert "LLM API key is not configured" in str(exc_info.value)
    mock_completion.assert_not_called()
