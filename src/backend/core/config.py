from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    backend_api_url: str = "http://localhost:8000"

    model_name: str = "claude-3-5-sonnet-20241022"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    sqlite_db_path: str = "./data/contextai.db"
    chroma_persist_dir: str = "./data/chroma"

    # External Tool API Keys
    openweather_api_key: str = ""
    tavily_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

