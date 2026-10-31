"""pgvector store tests. They run only when TEST_DATABASE_URL points at Postgres (CI does this)."""

import os

import pytest

from src.backend.core.config import settings

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")


@pytest.fixture
def stores():
    from src.backend.db.pg_stores import PgDocumentRAGPipeline, PgMemoryStore

    return PgMemoryStore(settings.database_url), PgDocumentRAGPipeline(settings.database_url)


def test_memory_search_ranks_by_meaning_and_scopes_to_user(stores):
    memories, _ = stores
    memories.add_memory("Lives in Berlin", "u1")
    memories.add_memory("Is allergic to peanuts", "u1")
    memories.add_memory("Lives in Lima", "u2")

    top = memories.search_memories("which city is home?", user_id="u1", limit=2)
    assert top[0]["memory"] == "Lives in Berlin"
    assert all(m["metadata"]["user_id"] == "u1" for m in top)
    assert 0 <= top[0]["distance"] < top[1]["distance"] <= 4  # squared L2 over unit vectors, like Chroma


def test_memory_update_reembeds_and_ownership_is_enforced(stores):
    memories, _ = stores
    mid = memories.add_memory("Lives in Pune", "u1")
    assert not memories.update_memory(mid, "intruder", "hijacked")
    assert memories.update_memory(mid, "u1", "Works as a pastry chef")
    assert memories.search_memories("baking job", user_id="u1", limit=1)[0]["id"] == mid
    [row] = memories.list_memories("u1")
    assert row["updated_at"].endswith("+00:00")  # UTC ISO strings, same as SQLite
    assert not memories.delete_memory(mid, "intruder") and memories.delete_memory(mid, "u1")


def test_documents_ingest_retrieve_gate_list_delete(stores, tmp_path):
    from tests.test_rag_quality import handbook_pdf

    _, docs = stores
    path = tmp_path / "handbook.pdf"
    path.write_bytes(handbook_pdf())
    assert docs.ingest_pdf(str(path), user_id="u1")["total_chunks"] == 5
    docs.ingest_pdf(str(path), user_id="u1")  # re-upload replaces, not duplicates
    passages = docs._passages("u1", None)  # whole-document questions read these in order
    assert [p["chunk_index"] for p in passages] == sorted(p["chunk_index"] for p in passages)
    assert passages and {"content", "document_name", "page_number", "section"} <= set(passages[0])
    assert docs.retrieve("summarize this", user_id="u1", document_names=[passages[0]["document_name"]])

    assert docs.count("u1") == 5 and docs.count("u2") == 0
    assert docs.retrieve("who approves business class flights", limit=2, user_id="u1")[0]["section"] == "5. Expenses"
    assert docs.retrieve("recipe for chocolate cake", limit=3, user_id="u1") == []
    assert len(docs.retrieve("what is this about?", user_id="u1", document_names=["handbook.pdf"])) == 5

    [listed] = docs.list_documents("u1")
    assert (listed["document_name"], listed["pages"], listed["chunks"]) == ("handbook.pdf", 2, 5)
    assert docs.delete_document("u2", listed["document_id"]) == 0
    assert docs.delete_document("u1", listed["document_id"]) == 5 and docs.count("u1") == 0
