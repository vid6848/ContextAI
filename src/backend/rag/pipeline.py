"""Document RAG pipeline for PDF text extraction, chunking, and ChromaDB vector retrieval."""

import hashlib
import logging
import os
from typing import Any

import chromadb
import pymupdf

from src.backend.core.config import settings

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks while respecting word boundaries."""
    cleaned = text.strip()
    if not cleaned:
        return []

    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = start + chunk_size
        if end >= len(cleaned):
            chunk = cleaned[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # Look for the last space within the window to avoid cutting words
        last_space = cleaned.rfind(" ", start, end)
        if last_space > start:
            end = last_space

        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = max(start + 1, end - chunk_overlap)

    return chunks


class DocumentRAGPipeline:
    """PDF document ingestion and semantic retrieval using PyMuPDF and ChromaDB."""

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str = "document_rag",
    ) -> None:
        self.persist_dir = persist_dir if persist_dir is not None else settings.chroma_persist_dir
        self.collection_name = collection_name
        self.client: chromadb.ClientAPI | None = None
        self.collection: Any = None
        self._ensure_dir()
        self.initialize()

    def _ensure_dir(self) -> None:
        """Ensure ChromaDB persistence directory exists."""
        if self.persist_dir:
            os.makedirs(os.path.abspath(self.persist_dir), exist_ok=True)

    def initialize(self) -> None:
        """Initialize ChromaDB client and retrieve or create dedicated document collection."""
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "ContextAI PDF document RAG knowledgebase"},
        )

    @staticmethod
    def _where(user_id: str | None, document_names: list[str] | None = None) -> dict[str, Any] | None:
        """Chroma metadata filter for a user's chunks, optionally limited to specific documents."""
        clauses: list[dict[str, Any]] = []
        if user_id:
            clauses.append({"user_id": user_id})
        if document_names:
            clauses.append({"document_name": {"$in": list(document_names)}})
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def count(self, user_id: str | None = None, document_names: list[str] | None = None) -> int:
        """Return number of indexed chunks, optionally only those owned by user_id (and named documents)."""
        if self.collection is None:
            self.initialize()
        where = self._where(user_id, document_names)
        if where is None:
            return self.collection.count()
        return len(self.collection.get(where=where, include=[])["ids"])

    def ingest_pdf(
        self,
        file_path: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        user_id: str | None = None,
        document_name: str | None = None,
    ) -> dict[str, Any]:
        """Extract text from a PDF file with PyMuPDF, chunk it, and store with metadata in ChromaDB.

        Chunks are tagged with user_id (when given) so retrieval can be scoped per user, and ids are
        derived from the file's content hash so re-uploading the same PDF replaces rather than duplicates.
        """
        if self.collection is None:
            self.initialize()

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found at: {file_path}")

        doc_name = document_name or os.path.basename(file_path)
        with open(file_path, "rb") as fh:
            document_id = hashlib.sha256(fh.read()).hexdigest()[:16]
        id_prefix = f"{user_id or 'shared'}_{document_id}"
        documents_to_add: list[str] = []
        metadatas_to_add: list[dict[str, Any]] = []
        ids_to_add: list[str] = []

        try:
            pdf_doc = pymupdf.open(file_path)
            total_pages = len(pdf_doc)

            for page_idx in range(total_pages):
                page = pdf_doc[page_idx]
                page_num = page_idx + 1
                page_text = page.get_text() or ""
                page_text = page_text.strip()
                if not page_text:
                    continue

                page_chunks = chunk_text(page_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                for chunk_idx, chunk in enumerate(page_chunks):
                    metadata: dict[str, Any] = {
                        "document_name": doc_name,
                        "document_id": document_id,
                        "page_number": page_num,
                        "chunk_index": chunk_idx,
                    }
                    if user_id:
                        metadata["user_id"] = user_id
                    documents_to_add.append(chunk)
                    metadatas_to_add.append(metadata)
                    ids_to_add.append(f"{id_prefix}_p{page_num}_c{chunk_idx}")

            pdf_doc.close()

            if documents_to_add:
                self.collection.upsert(
                    documents=documents_to_add,
                    metadatas=metadatas_to_add,
                    ids=ids_to_add,
                )

            return {
                "success": True,
                "document_name": doc_name,
                "total_pages": total_pages,
                "total_chunks": len(documents_to_add),
            }
        except Exception:
            logger.exception("Failed to ingest PDF %s", doc_name)
            return {
                "success": False,
                "document_name": doc_name,
                "error": "Failed to read this PDF. It may be corrupted, encrypted, or image-only.",
            }

    def retrieve(
        self,
        query: str,
        limit: int = 4,
        user_id: str | None = None,
        document_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over indexed chunks, restricted to user_id's documents (and named ones) when given."""
        if self.collection is None:
            self.initialize()

        total = self.count(user_id, document_names)
        if total == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(limit, total),
            where=self._where(user_id, document_names),
        )

        chunks: list[dict[str, Any]] = []
        if results and results.get("documents") and results["documents"][0]:
            docs = results["documents"][0]
            metas = results.get("metadatas", [[]])[0]
            ids = results.get("ids", [[]])[0]
            distances = results.get("distances", [[]])[0] if results.get("distances") else [None] * len(docs)

            for doc, meta, mid, dist in zip(docs, metas, ids, distances, strict=False):
                chunks.append({
                    "content": doc,
                    "document_name": meta.get("document_name", "Unknown"),
                    "page_number": meta.get("page_number", 1),
                    "chunk_id": mid,
                    "distance": dist,
                })
        return chunks

    def format_context(self, chunks: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        """Format retrieved chunks into context string for LLM and extract unique sources."""
        if not chunks:
            return "", []

        context_lines: list[str] = []
        sources: list[dict[str, Any]] = []
        seen_sources = set()

        for chunk in chunks:
            doc_name = chunk.get("document_name", "Document")
            page_num = chunk.get("page_number", 1)
            content = chunk.get("content", "")

            source_key = (doc_name, page_num)
            if source_key not in seen_sources:
                seen_sources.add(source_key)
                sources.append({"document": doc_name, "page": page_num})

            context_lines.append(f"[Source: {doc_name}, Page: {page_num}]\n{content}")

        formatted_context = "\n\n".join(context_lines)
        return formatted_context, sources

    def clear(self) -> None:
        """Clear all indexed document chunks."""
        if self.collection is not None and self.client is not None:
            try:
                self.client.delete_collection(self.collection_name)
                self.initialize()
            except Exception:
                pass
