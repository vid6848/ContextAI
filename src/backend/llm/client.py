"""LiteLLM client wrapper for Claude and supported models."""

from typing import Any
import litellm
from src.backend.core.config import settings


class LLMClient:
    """Client wrapper for LiteLLM completion calls to Claude."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model_name = model_name or settings.model_name
        self.api_key = api_key if api_key is not None else settings.anthropic_api_key

    def generate_response(
        self,
        message: str | list[dict[str, str]],
        intent: str = "GENERAL",
        **kwargs: Any,
    ) -> str:
        """Call Claude via LiteLLM to generate a response given message and intent."""
        if isinstance(message, list):
            messages = message
        else:
            system_prompt = (
                "You are the reasoning and response layer of ContextAI, a personal AI assistant. "
                f"The intent classifier has already classified the user's request as: '{intent}'. "
                "Provide a helpful, accurate, and concise response tailored to this intent."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(message)},
            ]

        call_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            **kwargs,
        }
        if self.api_key:
            call_kwargs["api_key"] = self.api_key

        response = litellm.completion(**call_kwargs)
        content = response.choices[0].message.content
        return content or ""

