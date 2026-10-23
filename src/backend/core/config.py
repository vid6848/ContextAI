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