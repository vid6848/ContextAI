"""Questions about uploaded PDFs: whole documents, pages, follow-ups, scans and awkward files."""

import io
from unittest.mock import MagicMock, patch

import pymupdf
import pytest
from fastapi.testclient import TestClient

from src.backend.agent.graph import documents_prompt
from src.backend.agent.toolbox import MAX_RESULT_CHARS, ToolBox
from src.backend.llm.client import _iter_chunks
from src.backend.main import app
from src.backend.memory.sql_db import SQLiteManager
from src.backend.rag.ocr import _blocks, ocr_pages, pages_needing_ocr
from src.backend.rag.pipeline import DocumentRAGPipeline
from src.backend.rag.query import LAST_PAGE, is_overview, requested_pages, spread
from src.backend.rag.structure import extract_blocks

client = TestClient(app)


def book(path, pages=30):
    doc = pymupdf.open()
    for i in range(1, pages + 1):
        doc.new_page().insert_text((50, 72), f"Section {i}. This page {i} covers unique subject number {i} in detail.")
    doc.save(path)
    doc.close()
    return str(path)


def scan(path, pages=1):
    source = pymupdf.open()
    source.new_page().insert_text((50, 72), "scanned words", fontsize=30)
    image = source[0].get_pixmap(dpi=72).tobytes("jpeg")
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_image(page.rect, stream=image)
    doc.save(path)
    doc.close()
    return str(path)


@pytest.fixture
def rag(tmp_path):
    return DocumentRAGPipeline(persist_dir=str(tmp_path / "chroma"), collection_name="questions")


@pytest.mark.parametrize("question, pages", [
    ("what does page 3 say", [3]),
    ("summarize pages 2-4", [2, 3, 4]),
    ("page 2 and 5", [2, 5]),
    ("what's on the first page", [1]),
    ("the 3rd page", [3]),
    ("what's on the last page", [LAST_PAGE]),
    ("what is the refund policy", None),
])
def test_requested_pages(question, pages):
    assert requested_pages(question) == pages


@pytest.mark.parametrize("question", [
    "summarize this", "Summarize this document.", "give me the main points of the file", "what is this about",
    "tldr", "key takeaways", "who wrote this paper", "translate this to Hindi", "quiz me on this",
    "make a table of the main findings", "compare the two documents",
])
def test_whole_document_questions(question):
    assert is_overview(question)


@pytest.mark.parametrize("question", [
    "summarize the refund policy", "what is the notice period", "how many sick days do I get",
])
def test_topic_questions_stay_semantic(question):
    assert not is_overview(question)


def test_a_file_name_counts_as_the_document():
    assert is_overview("summary of acme handbook 2026", ["acme_handbook_2026.pdf"])


def test_spread_reaches_start_and_end_of_every_document():
    passages = [{"document_name": n, "page_number": i, "chunk_index": i} for n in "ab" for i in range(100)]
    chosen = spread(passages, 20)
    assert len(chosen) == 20
    for name in "ab":
        pages = [p["page_number"] for p in chosen if p["document_name"] == name]
        assert pages[0] == 0 and pages[-1] == 99


def test_summary_covers_the_whole_long_document(rag, tmp_path):
    rag.ingest_pdf(book(tmp_path / "long.pdf"), user_id="u", document_name="long.pdf")
    pages = {c["page_number"] for c in rag.retrieve("summarize this", user_id="u", document_names=["long.pdf"])}
    assert {1, 30} <= pages and len(pages) >= 20


def test_page_question_reads_that_page(rag, tmp_path):
    rag.ingest_pdf(book(tmp_path / "long.pdf"), user_id="u", document_name="long.pdf")
    assert {c["page_number"] for c in rag.retrieve("what does page 17 say", user_id="u")} == {17}
    assert {c["page_number"] for c in rag.retrieve("the last page", user_id="u")} == {30}
    assert rag.retrieve("what's on page 500", user_id="u", document_names=["long.pdf"])  # falls back to a search


def test_nothing_attached_means_the_newest_document(rag, tmp_path):
    with patch("src.backend.rag.pipeline.datetime") as clock:
        clock.now.return_value.isoformat.return_value = "2026-01-01"
        rag.ingest_pdf(book(tmp_path / "old.pdf", 2), user_id="u", document_name="old.pdf")
        clock.now.return_value.isoformat.return_value = "2026-06-01"
        rag.ingest_pdf(book(tmp_path / "new.pdf", 3), user_id="u", document_name="new.pdf")
    assert {c["document_name"] for c in rag.retrieve("summarize my document", user_id="u")} == {"new.pdf"}


def test_page_question_uses_the_newest_document_that_has_the_page(rag, tmp_path):
    with patch("src.backend.rag.pipeline.datetime") as clock:
        clock.now.return_value.isoformat.return_value = "2026-01-01"
        rag.ingest_pdf(book(tmp_path / "long.pdf"), user_id="u", document_name="long.pdf")
        clock.now.return_value.isoformat.return_value = "2026-06-01"
        rag.ingest_pdf(book(tmp_path / "short.pdf", 1), user_id="u", document_name="short.pdf")
    found = rag.retrieve("what does page 25 say", user_id="u")
    assert {(c["document_name"], c["page_number"]) for c in found} == {("long.pdf", 25)}


def test_several_documents_each_get_their_share(rag, tmp_path):
    rag.ingest_pdf(book(tmp_path / "a.pdf"), user_id="u", document_name="a.pdf")
    rag.ingest_pdf(book(tmp_path / "b.pdf", 5), user_id="u", document_name="b.pdf")
    found = rag.retrieve("subject number 3", limit=6, user_id="u", document_names=["a.pdf", "b.pdf"])
    assert {c["document_name"] for c in found} == {"a.pdf", "b.pdf"}


def test_new_file_under_the_same_name_replaces_the_old_one(rag, tmp_path):
    rag.ingest_pdf(book(tmp_path / "v1.pdf", 2), user_id="u", document_name="lease.pdf")
    rag.ingest_pdf(book(tmp_path / "v2.pdf", 3), user_id="u", document_name="lease.pdf")
    documents = rag.list_documents("u")
    assert len(documents) == 1 and documents[0]["pages"] == 3


def test_scanned_pages_are_found_and_read(rag, tmp_path):
    path = scan(tmp_path / "scan.pdf", 2)
    pdf = pymupdf.open(path)
    assert pages_needing_ocr(pdf, extract_blocks(pdf)) == [1, 2]
    reply = "[[PAGE 1]]\nThe rent is 26000 rupees.\n\n[[PAGE 2]]\nThe deposit is 3 months."
    with patch("src.backend.rag.pipeline.ocr_pages", return_value=_blocks(reply, [1, 2])):
        result = rag.ingest_pdf(path, user_id="u", document_name="scan.pdf")
    assert result["success"] and result["scanned_pages"] == 2
    assert {c["page_number"] for c in rag.retrieve("page 2", user_id="u")} == {2}


def test_text_pages_are_not_sent_to_ocr(tmp_path):
    pdf = pymupdf.open(book(tmp_path / "text.pdf", 2))
    assert pages_needing_ocr(pdf, extract_blocks(pdf)) == []


def test_ocr_keeps_going_after_a_failed_batch(tmp_path):
    pdf = pymupdf.open(scan(tmp_path / "scan.pdf", 5))
    with (
        patch("src.backend.rag.ocr.settings") as settings,
        patch("src.backend.rag.ocr._transcribe", side_effect=[RuntimeError("quota"), "[[PAGE 5]]\nLast page text"]),
    ):
        settings.gemini_api_key = "k"
        blocks = ocr_pages(pdf, [1, 2, 3, 4, 5])
    assert [b.page for b in blocks] == [5]


def test_unreadable_scan_is_refused_not_silently_empty(rag, tmp_path):
    with patch("src.backend.rag.pipeline.ocr_pages", return_value=[]):
        result = rag.ingest_pdf(scan(tmp_path / "scan.pdf"), user_id="u")
    assert not result["success"] and "readable text" in result["error"]


def _upload(name, content):
    return client.post(
        "/api/v1/documents/upload", params={"user_id": "uploader"},
        files={"file": (name, io.BytesIO(content), "application/pdf")},
    )


def test_password_protected_pdf_says_so(tmp_path):
    path = book(tmp_path / "plain.pdf", 1)
    pymupdf.open(path).save(tmp_path / "locked.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    response = _upload("locked.pdf", (tmp_path / "locked.pdf").read_bytes())
    assert response.status_code == 422 and "password" in response.json()["detail"]


def test_header_after_leading_junk_is_accepted(tmp_path):
    content = b"\n\n  " + open(book(tmp_path / "plain.pdf", 1), "rb").read()
    assert _upload("junk.pdf", content).status_code == 200


def test_very_long_file_name_still_works_as_an_attachment(tmp_path):
    response = _upload("x" * 300 + ".pdf", open(book(tmp_path / "plain.pdf", 1), "rb").read())
    assert response.status_code == 200
    name = response.json()["document_name"]
    assert len(name) <= 255 and name.endswith(".pdf")


def test_follow_ups_stay_on_the_attached_files(tmp_path):
    sql = SQLiteManager(db_path=str(tmp_path / "chat.db"))
    conversation = sql.create_conversation("u", "chat")["id"]
    sql.save_message("u", "user", "summarize", conversation_id=conversation, metadata={"attachments": ["a.pdf"]})
    sql.save_message("u", "assistant", "done", conversation_id=conversation, metadata={"tool_used": "document_rag"})
    sql.save_message("u", "user", "and the notice period?", conversation_id=conversation)
    assert sql.latest_attachments(conversation, "u") == ["a.pdf"]
    assert sql.latest_attachments(conversation, "someone-else") == []


def _box(rag, **kwargs):
    return ToolBox(
        calculator=MagicMock(), weather=MagicMock(), crypto=MagicMock(), web=MagicMock(), rag=rag,
        reminders=MagicMock(), user_id="u", **kwargs,
    )


def test_agent_search_stays_in_scope_and_keeps_numbers_across_calls(rag, tmp_path):
    rag.ingest_pdf(book(tmp_path / "a.pdf"), user_id="u", document_name="a.pdf")
    rag.ingest_pdf(book(tmp_path / "b.pdf"), user_id="u", document_name="b.pdf")
    box = _box(rag, documents=["a.pdf"])
    first, for_model = box.run("search_documents", {"query": "summarize this"})
    assert {p["document"] for p in first["passages"]} == {"a.pdf"}
    assert len(for_model) < MAX_RESULT_CHARS and for_model.endswith("}")  # never a cut-off JSON

    count = len(box.sources)
    again, _ = box.run("search_documents", {"query": "summarize this"})
    assert len(box.sources) == count  # the same passages keep their citation numbers
    assert [p["n"] for p in again["passages"]] == [p["n"] for p in first["passages"]]


def test_agent_can_name_a_document_and_list_them(rag, tmp_path):
    rag.ingest_pdf(book(tmp_path / "a.pdf", 2), user_id="u", document_name="contract.pdf")
    rag.ingest_pdf(book(tmp_path / "b.pdf", 3), user_id="u", document_name="invoice.pdf")
    box = _box(rag)
    found = box.run("search_documents", {"query": "page 1", "document": "Invoice"})[0]
    assert {p["document"] for p in found["passages"]} == {"invoice.pdf"}
    listed = box.run("list_documents", {})[0]["documents"]
    assert {d["name"]: d["pages"] for d in listed} == {"contract.pdf": 2, "invoice.pdf": 3}


def test_model_is_told_which_files_exist():
    documents = [{"document_name": "a.pdf", "pages": 3}]
    prompt = documents_prompt(documents, ["a.pdf"])
    assert "a.pdf (3 pages)" in prompt and "This chat is about a.pdf" in prompt
    assert documents_prompt([], []) == ""


def test_stream_survives_unicode_line_separators_in_text():
    """Non-English output can hold U+2028, which str.splitlines() treats as a line break."""
    payload = '{"choices":[{"delta":{"content":"नमस्ते दुनिया"}}]}'.encode()
    response = MagicMock()
    response.iter_lines.return_value = [b"data: " + payload, b"", b"data: [DONE]"]
    assert [c["choices"][0]["delta"]["content"] for c in _iter_chunks(response)] == ["नमस्ते दुनिया"]
