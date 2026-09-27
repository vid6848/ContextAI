"""Tests for SQLite conversation memory and ChromaDB semantic memory layers."""

from unittest.mock import MagicMock
import pytest
from src.backend.memory.sql_db import SQLiteManager
from src.backend.memory.vector_store import ChromaMemoryStore
from src.backend.agent.graph import get_agent_app, is_user_specific_memory


def test_sqlite_init_db(tmp_path):
    """Verify SQLite database initialization and table schema."""
    db_file = str(tmp_path / "init_test.db")
    manager = SQLiteManager(db_path=db_file)

    with manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_history';")
        table = cursor.fetchone()
        assert table is not None
        assert table["name"] == "conversation_history"

        # Check table columns
        cursor.execute("PRAGMA table_info(conversation_history);")
        columns = {col["name"]: col["type"] for col in cursor.fetchall()}
        assert "id" in columns
        assert "user_id" in columns
        assert "role" in columns
        assert "message" in columns
        assert "timestamp" in columns


def test_sqlite_save_and_retrieve_messages(tmp_path):
    """Verify saving and retrieving messages in chronological order."""
    db_file = str(tmp_path / "crud_test.db")
    manager = SQLiteManager(db_path=db_file)

    msg1_id = manager.save_message(user_id="user_123", role="user", message="Hello, ContextAI!")
    msg2_id = manager.save_message(user_id="user_123", role="assistant", message="Hello! How can I help?")

    assert msg1_id > 0
    assert msg2_id > msg1_id

    history = manager.get_recent_messages(user_id="user_123", limit=10)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["message"] == "Hello, ContextAI!"
    assert history[1]["role"] == "assistant"
    assert history[1]["message"] == "Hello! How can I help?"
    assert history[0]["timestamp"] is not None


def test_sqlite_user_history_isolation(tmp_path):
    """Verify user-specific history isolation and clear_history."""
    db_file = str(tmp_path / "isolation_test.db")
    manager = SQLiteManager(db_path=db_file)

    manager.save_message(user_id="alice", role="user", message="Alice's private secret")
    manager.save_message(user_id="bob", role="user", message="Bob's public comment")

    alice_history = manager.get_recent_messages(user_id="alice")
    bob_history = manager.get_recent_messages(user_id="bob")

    assert len(alice_history) == 1
    assert alice_history[0]["message"] == "Alice's private secret"

    assert len(bob_history) == 1
    assert bob_history[0]["message"] == "Bob's public comment"

    # Clear Alice's history and ensure Bob is unaffected
    manager.clear_history(user_id="alice")
    assert len(manager.get_recent_messages(user_id="alice")) == 0
    assert len(manager.get_recent_messages(user_id="bob")) == 1


def test_chromadb_memory_insertion(tmp_path):
    """Verify adding long-term memory into ChromaDB."""
    chroma_dir = str(tmp_path / "chroma_test")
    store = ChromaMemoryStore(persist_dir=chroma_dir, collection_name="test_mem")

    mem_id = store.add_memory(
        memory="User prefers dark theme and Python",
        user_id="alice",
        metadata={"category": "preferences"},
    )

    assert mem_id.startswith("mem_")
    assert store.collection.count() == 1


def test_chromadb_semantic_memory_retrieval(tmp_path):
    """Verify semantic search and user isolation in ChromaDB."""
    chroma_dir = str(tmp_path / "chroma_search_test")
    store = ChromaMemoryStore(persist_dir=chroma_dir, collection_name="test_mem")

    store.add_memory(memory="User lives in Seattle and works on machine learning", user_id="alice")
    store.add_memory(memory="User loves hiking in the Pacific Northwest mountains", user_id="alice")
    store.add_memory(memory="User is a graphic designer based in Chicago", user_id="bob")

    # Semantic search for Alice's career
    alice_career = store.get_relevant_memories(query="Where does the user work or career?", user_id="alice", limit=2)
    assert len(alice_career) > 0
    assert any("machine learning" in mem for mem in alice_career)

    # Bob's query should not return Alice's memories
    bob_results = store.get_relevant_memories(query="Where do I live?", user_id="bob", limit=2)
    assert len(bob_results) == 1
    assert "Chicago" in bob_results[0]
    assert "Seattle" not in bob_results[0]


def test_langgraph_memory_retrieval_and_context_injection(tmp_path):
    """Verify LangGraph retrieve_memory node injects history and memories into LLM call."""
    db_file = str(tmp_path / "lg_test.db")
    chroma_dir = str(tmp_path / "lg_chroma")

    sql_mgr = SQLiteManager(db_path=db_file)
    vector_store = ChromaMemoryStore(persist_dir=chroma_dir, collection_name="lg_mem")

    # Seed conversation history
    sql_mgr.save_message(user_id="user_alpha", role="user", message="I like science fiction books.")
    sql_mgr.save_message(user_id="user_alpha", role="assistant", message="Noted, sci-fi is great!")

    # Seed semantic long-term memory
    vector_store.add_memory(
        memory="User's favorite author is Philip K. Dick",
        user_id="user_alpha",
    )

    mock_llm_client = MagicMock()
    mock_llm_client.generate_response.return_value = "I recommend Do Androids Dream of Electric Sheep?"

    app = get_agent_app(
        llm_client=mock_llm_client,
        sql_manager=sql_mgr,
        vector_store=vector_store,
    )

    state_input = {
        "message": "Can you recommend a good book?",
        "user_id": "user_alpha",
    }
    result = app.invoke(state_input)

    # Verify state contains retrieved memories
    assert len(result["conversation_history"]) == 2
    assert len(result["semantic_memories"]) > 0
    assert "Philip K. Dick" in result["semantic_memories"][0]

    # Verify LLM was called with context containing both history and memories
    mock_llm_client.generate_response.assert_called_once()
    call_kwargs = mock_llm_client.generate_response.call_args.kwargs
    assert "context" in call_kwargs
    context_str = call_kwargs["context"]
    assert "Relevant Long-Term Memories:" in context_str
    assert "Philip K. Dick" in context_str
    assert "Recent Conversation History:" in context_str
    assert "I like science fiction books." in context_str


def test_langgraph_saving_conversation_history_and_selective_memory(tmp_path):
    """Verify LangGraph saves user and assistant messages to SQLite and selective facts to ChromaDB."""
    db_file = str(tmp_path / "lg_save_test.db")
    chroma_dir = str(tmp_path / "lg_save_chroma")

    sql_mgr = SQLiteManager(db_path=db_file)
    vector_store = ChromaMemoryStore(persist_dir=chroma_dir, collection_name="lg_save_mem")

    mock_llm = MagicMock()
    mock_llm.generate_response.return_value = "Nice to meet you, Charlie!"

    app = get_agent_app(
        llm_client=mock_llm,
        sql_manager=sql_mgr,
        vector_store=vector_store,
    )

    # 1. Message with user-specific info ("my name is Charlie...")
    app.invoke({"message": "My name is Charlie and I like vanilla ice cream", "user_id": "charlie"})

    # Check SQLite
    history = sql_mgr.get_recent_messages(user_id="charlie")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["message"] == "My name is Charlie and I like vanilla ice cream"
    assert history[1]["role"] == "assistant"
    assert history[1]["message"] == "Nice to meet you, Charlie!"

    # Check ChromaDB: should be saved because it contains personal facts
    assert vector_store.collection.count() == 1
    mems = vector_store.get_relevant_memories("What ice cream?", user_id="charlie")
    assert len(mems) == 1
    assert "vanilla ice cream" in mems[0]

    # 2. Trivial message ("What time is it in Tokyo?")
    mock_llm.generate_response.return_value = "It is 2 PM in Tokyo."
    app.invoke({"message": "What is the weather in Tokyo?", "user_id": "charlie"})

    # SQLite now has 4 messages
    history_after = sql_mgr.get_recent_messages(user_id="charlie")
    assert len(history_after) == 4

    # ChromaDB count should still be 1 (trivial weather question was NOT saved to long-term memory)
    assert vector_store.collection.count() == 1


def test_is_user_specific_memory_heuristics():
    """Verify deterministic memory classifier heuristics."""
    assert is_user_specific_memory("My name is Alice and I am a software engineer")
    assert is_user_specific_memory("I like dark roast coffee every morning")
    assert is_user_specific_memory("Please remember that my dog is named Sparky")
    assert is_user_specific_memory("I prefer typescript over python")
    assert is_user_specific_memory("I live in New York City")

    # Trivial / generic queries
    assert not is_user_specific_memory("What is the weather forecast for tomorrow?")
    assert not is_user_specific_memory("How are you doing today?")
    assert not is_user_specific_memory("Tell me a funny joke")
    assert not is_user_specific_memory("Thanks a lot")
    assert not is_user_specific_memory("Hello ContextAI")
