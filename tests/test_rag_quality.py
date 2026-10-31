"""Tests for structure-aware chunking, hybrid re-ranking, relevance gating and document management."""

import io

import pymupdf
import pytest
from fastapi.testclient import TestClient

from src.backend.main import app
from src.backend.rag.pipeline import DocumentRAGPipeline
from src.backend.rag.rerank import rerank, similarity_from_l2, terms
from src.backend.rag.structure import Block, extract_blocks, is_heading, structure_chunks

client = TestClient(app)

SECTIONS = [
    ("Employee Handbook", 20, None),
    ("1. Working hours", 14, "Our standard working week is 40 hours, Monday to Friday. Core hours are 10:00 to 16:00."),
    ("2. Remote work", 14, "Employees may work remotely up to three days per week. Home equipment is reimbursed."),
    ("3. Leave", 14, "Full-time staff receive 25 days of paid annual leave plus public holidays."),
    ("4. Sick leave", 14, "Notify your manager before 10:00. A doctor's note is required after three days of absence."),
    ("5. Expenses", 14, "Economy is standard for flights under six hours; business class needs director approval."),
]


def handbook_pdf() -> bytes:
    doc = pymupdf.open()
    page, y = doc.new_page(), 60
    for i, (heading, size, body) in enumerate(SECTIONS):
        if i == 3:  # sections 3-5 on page 2
            page, y = doc.new_page(), 60
        page.insert_text((50, y), heading, fontsize=size)
        y += 30
        if body:
            used = page.insert_textbox(pymupdf.Rect(50, y, 545, y + 120), body, fontsize=10)
            y += (120 - used) + 20
    data = doc.write()
    doc.close()
    return data


@pytest.fixture
def handbook(tmp_path):
    path = tmp_path / "handbook.pdf"
    path.write_bytes(handbook_pdf())
    rag = DocumentRAGPipeline(persist_dir=str(tmp_path / "chroma"), collection_name="quality_docs")
    rag.ingest_pdf(str(path), user_id="u1")
    return rag


# ---------------------------------------------------------------- chunking


def test_chunks_follow_sections_and_keep_their_heading(handbook):
    stored = handbook.collection.get(include=["documents", "metadatas"])
    sections = [m.get("section") for m in stored["metadatas"]]
    assert sections == ["1. Working hours", "2. Remote work", "3. Leave", "4. Sick leave", "5. Expenses"]
    expenses = stored["documents"][sections.index("5. Expenses")]
    assert expenses.startswith("5. Expenses") and "business class" in expenses
    assert [m["page_number"] for m in stored["metadatas"]] == [1, 1, 2, 2, 2]


def test_heading_detection_and_long_paragraph_splitting():
    body = Block(page=1, text="Plain paragraph text that ends with a full stop.", size=10, bold=False)
    assert not is_heading(body, 10)
    assert is_heading(Block(page=1, text="Results", size=14, bold=False), 10)
    assert is_heading(Block(page=1, text="Summary of findings", size=10, bold=True), 10)

    long_para = Block(page=1, text=" ".join(f"Sentence number {i} is here." for i in range(80)), size=10, bold=False)
    chunks = structure_chunks([Block(1, "Intro", 14, False), long_para], max_chars=300)
    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)
    assert all(c.heading == "Intro" for c in chunks)


def test_extract_blocks_reads_font_sizes():
    doc = pymupdf.open(stream=handbook_pdf(), filetype="pdf")
    blocks = extract_blocks(doc)
    assert blocks[0].text == "Employee Handbook" and blocks[0].size == pytest.approx(20, abs=0.5)


# ---------------------------------------------------------------- re-ranking


def test_rerank_blends_similarity_with_keyword_coverage_and_gates():
    candidates = [
        {"content": "Business class requires director approval.", "distance": 0.9},   # relevant
        {"content": "Our office has a lovely garden.", "distance": 1.95},                # unrelated
        {"content": "Approval for business class flights: ask a director.", "distance": 1.7},  # keywords only
    ]
    ranked = rerank("who approves business class flights", candidates, limit=5)
    assert [c["content"][:8] for c in ranked] == ["Business", "Approval"]
    assert all(0 <= c["score"] <= 1 for c in ranked)
    assert len(rerank("who approves business class flights", candidates, limit=5, gate=False)) == 3


def test_term_normalisation_and_distance_conversion():
    assert terms("What are the flights?") == {"flight"}
    assert similarity_from_l2(0) == 1 and similarity_from_l2(2) == 0 and similarity_from_l2(None) == 0


def test_retrieval_finds_the_right_section_and_rejects_unrelated_questions(handbook):
    top = handbook.retrieve("who approves business class flights", limit=2, user_id="u1")
    assert top[0]["section"] == "5. Expenses"
    assert handbook.retrieve("doctor note when sick", limit=1, user_id="u1")[0]["section"] == "4. Sick leave"
    for question in ("What is the capital of France?", "recipe for chocolate cake"):
        assert handbook.retrieve(question, limit=3, user_id="u1") == []


def test_attachment_scoped_search_skips_the_gate(handbook):
    results = handbook.retrieve("what is this about?", limit=3, user_id="u1", document_names=["handbook.pdf"])
    assert {r["page_number"] for r in results} >= {1, 2}  # the whole document, not just its first passages


# ---------------------------------------------------------------- management


def test_list_and_delete_documents_via_api():
    files = {"file": ("handbook.pdf", io.BytesIO(handbook_pdf()), "application/pdf")}
    client.post("/api/v1/documents/upload", params={"user_id": "mgr"}, files=files)

    listing = client.get("/api/v1/documents", params={"user_id": "mgr"}).json()
    [doc] = listing["documents"]
    assert doc["document_name"] == "handbook.pdf" and doc["pages"] == 2 and doc["chunks"] == 5
    assert doc["uploaded_at"]

    url = f"/api/v1/documents/{doc['document_id']}"
    assert client.delete(url, params={"user_id": "someone-else"}).status_code == 404
    assert client.delete(url, params={"user_id": "mgr"}).status_code == 200
    assert client.get("/api/v1/documents", params={"user_id": "mgr"}).json() == {
        "success": True, "total_chunks": 0, "documents": []
    }


def test_classifier_path_says_when_documents_dont_cover_the_question(monkeypatch):
    from unittest.mock import patch

    files = {"file": ("handbook.pdf", io.BytesIO(handbook_pdf()), "application/pdf")}
    client.post("/api/v1/documents/upload", params={"user_id": "gate"}, files=files)
    with patch("src.backend.llm.client.LLMClient.generate_response") as llm:
        question = "What does the document say about the capital of France?"
        data = client.post("/api/v1/chat", json={"message": question, "user_id": "gate"}).json()
    # The answer itself needed no model call; the only call is the new chat's title
    assert all(
        c.kwargs["message"][0]["content"].startswith("Write a short title") for c in llm.call_args_list
    )
    assert data["intent"] == "DOCUMENT"
    assert "couldn't find anything about that in your documents" in data["response"]
