from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_name: str = "gemini-3.5-flash-lite"
    fallback_model_name: str = "gemini-3.1-flash-lite"
    # Side tasks (chat titles, memory extraction) run on this model so they don't spend the chat
    # model's per-minute quota; empty means use the fallback model
    utility_model_name: str = ""
    gemini_api_key: str = ""

    # Postgres (e.g. Supabase) connection string. When set, chats, reminders, memories and documents live
    # there (pgvector for embeddings); when empty, SQLite + ChromaDB under ./data are used.
    database_url: str = ""
    sqlite_db_path: str = "./data/contextai.db"
    chroma_persist_dir: str = "./data/chroma"

    openweather_api_key: str = ""
    tavily_api_key: str = ""

    # Tool routing: "hybrid" uses the TF-IDF classifier when it's confident and lets the LLM choose
    # (and chain) tools otherwise; "llm" always uses function calling; "classifier" never does.
    router_mode: Literal["hybrid", "llm", "classifier"] = "hybrid"
    # Minimum MiniLM similarity for the fast path (both classifiers must also agree); see evals/route_eval.py
    hybrid_confidence_threshold: float = 0.35
    max_tool_rounds: int = 4

    # Long-term memory: "llm" extracts and reconciles facts after each reply; "heuristic" stores
    # first-person messages verbatim (the original behaviour, kept for offline use and tests)
    memory_mode: Literal["llm", "heuristic"] = "llm"

    # Web Push for reminders. Keys are generated into the data dir when empty; set them in production
    # so browser subscriptions survive redeploys. vapid_contact must be a mailto: or https: URL.
    push_enabled: bool = True
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_contact: str = "mailto:admin@contextai.local"

    # Sign-in (Supabase Auth). The URL and publishable key are public (they ship to the browser);
    # tokens are verified against the project's JWKS, so no secret is needed. Empty = guests only.
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    auth_required: bool = False  # True: no guest mode

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