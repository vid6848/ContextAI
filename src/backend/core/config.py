from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_name: str = "gemini-3.5-flash-lite"
    fallback_model_name: str = "gemini-3.1-flash-lite"
    gemini_api_key: str = ""

    sqlite_db_path: str = "./data/contextai.db"
    chroma_persist_dir: str = "./data/chroma"

    openweather_api_key: str = ""
    tavily_api_key: str = ""

    # Tool routing: "hybrid" uses the TF-IDF classifier when it's confident and lets the LLM choose
    # (and chain) tools otherwise; "llm" always uses function calling; "classifier" never does.
    router_mode: Literal["hybrid", "llm", "classifier"] = "hybrid"
    hybrid_confidence_threshold: float = 0.8
    max_tool_rounds: int = 4

    # Long-term memory: "llm" extracts and reconciles facts after each reply; "heuristic" stores
    # first-person messages verbatim (the original behaviour, kept for offline use and tests)
    memory_mode: Literal["llm", "heuristic"] = "llm"

    # Abuse protection (per client IP, per minute) and upload size cap
    rate_limit_chat_per_minute: int = 20
    rate_limit_upload_per_minute: int = 5
    max_upload_mb: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()