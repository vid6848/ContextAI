"""Tests for Document RAG Pipeline using PyMuPDF and ChromaDB."""

import pytest
import pymupdf
from src.backend.rag.pipeline import DocumentRAGPipeline, chunk_text


def _create_sample_pdf(file_path: str) -> None:
    """Helper to generate a multi-page test PDF with PyMuPDF."""
    doc = pymupdf.open()

    # Page 1
    page1 = doc.new_page()
    page1.insert_text(
        (50, 50),
        "ContextAI Architecture Overview. "
        "ContextAI is an intelligent personal assistant that unifies short-term SQLite memory "
        "and long-term ChromaDB semantic storage for context-aware conversations.",
    )

    # Page 2
    page2 = doc.new_page()
    page2.insert_text(
        (50, 50),
        "Document Retrieval Augmented Generation. "
        "The RAG module utilizes PyMuPDF for accurate text extraction from local PDF files. "
        "Extracted chunks are embedded and indexed into ChromaDB for high-precision semantic search.",
    )

    doc.save(file_path)
    doc.close()


def test_chunk_text_splitting():
    """Verify chunk_text splits long text while respecting chunk size and overlap."""
    sample_text = "Word " * 200  # 1000 characters
    chunks = chunk_text(sample_text, chunk_size=300, chunk_overlap=50)

    assert len(chunks) > 1
    assert all(len(c) <= 350 for c in chunks)
    assert all(len(c) > 0 for c in chunks)

    # Edge cases
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    assert len(chunk_text("Short text", chunk_size=100)) == 1


def test_pdf_extraction_ingestion_and_chroma_insertion(tmp_path):
    """Verify PDF ingestion, text extraction with PyMuPDF, and storage in ChromaDB."""
    pdf_path = str(tmp_path / "sample_manual.pdf")
    _create_sample_pdf(pdf_path)

    chroma_dir = str(tmp_path / "rag_chroma")
    rag = DocumentRAGPipeline(persist_dir=chroma_dir, collection_name="test_docs")

    ingest_result = rag.ingest_pdf(pdf_path, chunk_size=300, chunk_overlap=30)

    assert ingest_result["success"]
    assert ingest_result["document_name"] == "sample_manual.pdf"
    assert ingest_result["total_pages"] == 2
    assert ingest_result["total_chunks"] >= 2
    assert rag.count() >= 2


def test_rag_semantic_retrieval_and_metadata(tmp_path):
    """Verify semantic retrieval returns relevant chunks with document name and page number metadata."""
    pdf_path = str(tmp_path / "system_guide.pdf")
    _create_sample_pdf(pdf_path)

    chroma_dir = str(tmp_path / "rag_search_chroma")
    rag = DocumentRAGPipeline(persist_dir=chroma_dir, collection_name="test_docs_search")
    rag.ingest_pdf(pdf_path, chunk_size=400, chunk_overlap=40)

    # Query matching content specifically on page 2 (RAG / PyMuPDF)
    results = rag.retrieve("How does the RAG module extract text?", limit=2)

    assert len(results) > 0
    top_chunk = results[0]
    assert "PyMuPDF" in top_chunk["content"] or "extraction" in top_chunk["content"]
    assert top_chunk["document_name"] == "system_guide.pdf"
    assert top_chunk["page_number"] in (1, 2)
    assert "chunk_id" in top_chunk

    # Test context formatting
    context_str, sources = rag.format_context(results)
    assert "[Source: system_guide.pdf, Page:" in context_str
    assert len(sources) > 0
    assert sources[0]["document"] == "system_guide.pdf"


def test_rag_no_document_case(tmp_path):
    """Verify RAG pipeline handles the case when no documents have been indexed."""
    chroma_dir = str(tmp_path / "empty_rag")
    rag = DocumentRAGPipeline(persist_dir=chroma_dir, collection_name="empty_docs")

    assert rag.count() == 0
    results = rag.retrieve("Explain the architecture")
    assert results == []

    context_str, sources = rag.format_context(results)
    assert context_str == ""
    assert sources == []


def test_rag_file_not_found(tmp_path):
    """Verify FileNotFoundError is raised when target PDF does not exist."""
    chroma_dir = str(tmp_path / "error_rag")
    rag = DocumentRAGPipeline(persist_dir=chroma_dir, collection_name="err_docs")

    with pytest.raises(FileNotFoundError):
        rag.ingest_pdf(str(tmp_path / "non_existent.pdf"))
