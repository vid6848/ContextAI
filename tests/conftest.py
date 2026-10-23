"""Pytest configuration and test isolation fixtures.

Set TEST_DATABASE_URL to a Postgres database with pgvector to run the whole suite against Postgres
(as CI does); otherwise the stores use SQLite and ChromaDB in a temporary directory.
"""

import os

import pytest

from src.backend.agent import graph
from src.backend.api import routes
from src.backend.core.config import settings
from src.backend.core.rate_limit import limiter
from src.backend.db import Database


@pytest.fixture(autouse=True)
def isolate_test_storage(tmp_path, monkeypatch):
    """Isolate SQLite database and ChromaDB storage in a temporary directory per test."""
    test_db = str(tmp_path / "test_contextai.db")
    test_chroma = str(tmp_path / "test_chroma")

    monkeypatch.setattr(settings, "sqlite_db_path", test_db)
    monkeypatch.setattr(settings, "chroma_persist_dir", test_chroma)
    pg_url = os.environ.get("TEST_DATABASE_URL", "")
    monkeypatch.setattr(settings, "database_url", pg_url)
    if pg_url:
        with Database(pg_url).connect() as conn:
            conn.execute(
                "TRUNCATE conversations, conversation_history, reminders, push_subscriptions, memories, "
                "document_chunks RESTART IDENTITY CASCADE"
            )
    # Never call real LLM/tool APIs from tests, even if a developer's .env provides keys
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "openweather_api_key", "")
    monkeypatch.setattr(settings, "tavily_api_key", "")
    # Most tests exercise the deterministic classifier path; test_tool_agent.py covers LLM routing
    monkeypatch.setattr(settings, "router_mode", "classifier")
    # Verbatim first-person memories; test_memory_extraction.py covers the LLM extractor
    monkeypatch.setattr(settings, "memory_mode", "heuristic")

    # Reset singletons so they bind to the temporary test storage
    graph._default_sql_manager = None
    graph._default_llm_client = None
    graph._default_utility_llm = None
    graph._default_router = None
    graph._default_reminder_manager = None
    graph._default_vector_store = None
    graph._default_calculator_tool = None
    graph._default_weather_tool = None
    graph._default_crypto_tool = None
    graph._default_tavily_tool = None
    graph._default_rag_pipeline = None
    routes._compiled_agent = None
    routes._default_reminder_manager = None
    routes._push_service = None
    limiter.reset()

    yield

    # Clean up singletons after test
    graph._default_sql_manager = None
    graph._default_llm_client = None
    graph._default_vector_store = None
    graph._default_calculator_tool = None
    graph._default_weather_tool = None
    graph._default_crypto_tool = None
    graph._default_tavily_tool = None
    graph._default_rag_pipeline = None
    routes._compiled_agent = None
    routes._default_reminder_manager = None
