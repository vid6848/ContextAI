"""Pytest configuration and test isolation fixtures."""

import pytest
from src.backend.core.config import settings
from src.backend.agent import graph
from src.backend.api import routes


@pytest.fixture(autouse=True)
def isolate_test_storage(tmp_path, monkeypatch):
    """Isolate SQLite database and ChromaDB storage in a temporary directory per test."""
    test_db = str(tmp_path / "test_contextai.db")
    test_chroma = str(tmp_path / "test_chroma")

    monkeypatch.setattr(settings, "sqlite_db_path", test_db)
    monkeypatch.setattr(settings, "chroma_persist_dir", test_chroma)

    # Reset singletons so they bind to the temporary test storage
    graph._default_sql_manager = None
    graph._default_vector_store = None
    graph._default_calculator_tool = None
    graph._default_weather_tool = None
    graph._default_crypto_tool = None
    graph._default_tavily_tool = None
    graph._default_rag_pipeline = None
    routes._compiled_agent = None

    yield

    # Clean up singletons after test
    graph._default_sql_manager = None
    graph._default_vector_store = None
    graph._default_calculator_tool = None
    graph._default_weather_tool = None
    graph._default_crypto_tool = None
    graph._default_tavily_tool = None
    graph._default_rag_pipeline = None
    routes._compiled_agent = None
