"""Document RAG pipeline for PDF text extraction, chunking, and ChromaDB vector retrieval."""

import hashlib
import logging
import os
from datetime import UTC, datetime
from typing import Any

import chromadb
import pymupdf

from src.backend.core.config import settings
from src.backend.rag.rerank import rerank
from src.backend.rag.structure import chunk_document_text, extract_blocks, structure_chunks

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
        chunk_size: int = 900,
        chunk_overlap: int = 0,
        user_id: str | None = None,
        document_name: str | None = None,
    ) -> dict[str, Any]:
        """Extract a PDF with PyMuPDF, chunk it along headings and paragraphs, and store it in ChromaDB.

        chunk_size is the maximum characters per chunk; chunk_overlap is kept for API compatibility (chunks
        carry their section heading instead of overlapping). Chunks are tagged with user_id so retrieval can
        be scoped per user, and ids derive from the file's content hash so re-uploading replaces, not duplicates.
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

            uploaded_at = datetime.now(UTC).isoformat()
            for chunk_idx, chunk in enumerate(structure_chunks(extract_blocks(pdf_doc), max_chars=chunk_size)):
                metadata: dict[str, Any] = {
                    "document_name": doc_name,
                    "document_id": document_id,
                    "page_number": chunk.page,
                    "chunk_index": chunk_idx,
                    "total_pages": total_pages,
                    "uploaded_at": uploaded_at,
                }
                if chunk.heading:
                    metadata["section"] = chunk.heading
                if user_id:
                    metadata["user_id"] = user_id
                documents_to_add.append(chunk_document_text(chunk))
                metadatas_to_add.append(metadata)
                ids_to_add.append(f"{id_prefix}_c{chunk_idx}")

            pdf_doc.close()

            if documents_to_add:
                self._upsert(ids_to_add, documents_to_add, metadatas_to_add)

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

        # Over-fetch candidates, then re-rank with keyword coverage and drop unrelated passages
        chunks = self._candidates(query, min(max(limit * 4, 12), total), user_id, document_names)
        # When the user attached specific files, "summarize this" must still return their passages
        return rerank(query, chunks, limit, gate=not document_names)

    # ---- storage primitives (overridden by the Postgres/pgvector store) ----

    def _upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        self.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)

    def _candidates(
        self, query: str, n: int, user_id: str | None, document_names: list[str] | None
    ) -> list[dict[str, Any]]:
        """Nearest chunks with squared-L2 distance over unit vectors (what rerank expects)."""
        results = self.collection.query(query_texts=[query], n_results=n, where=self._where(user_id, document_names))
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
                    "section": meta.get("section"),
                })
        return chunks

    def list_documents(self, user_id: str) -> list[dict[str, Any]]:
        """The user's documents with page and passage counts, newest first."""
        if self.collection is None:
            self.initialize()
        rows = self.collection.get(where={"user_id": user_id}, include=["metadatas"])["metadatas"] or []
        docs: dict[str, dict[str, Any]] = {}
        for meta in rows:
            doc = docs.setdefault(meta.get("document_id", ""), {
                "document_id": meta.get("document_id", ""),
                "document_name": meta.get("document_name", "Document"),
                "pages": meta.get("total_pages") or 0,
                "chunks": 0,
                "uploaded_at": meta.get("uploaded_at"),
            })
            doc["chunks"] += 1
            doc["pages"] = max(doc["pages"], meta.get("total_pages") or meta.get("page_number") or 0)
        return sorted(docs.values(), key=lambda d: d.get("uploaded_at") or "", reverse=True)

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        """Move a guest's documents to their account. Returns how many passages moved."""
        if self.collection is None:
            self.initialize()
        rows = self.collection.get(where={"user_id": old_user_id}, include=["metadatas"])
        if rows["ids"]:
            metas = [{**(m or {}), "user_id": new_user_id} for m in rows["metadatas"]]
            self.collection.update(ids=rows["ids"], metadatas=metas)
        return len(rows["ids"])

    def delete_document(self, user_id: str, document_id: str) -> int:
        """Delete one of the user's documents. Returns the number of passages removed (0 if not found)."""
        if self.collection is None:
            self.initialize()
        where = {"$and": [{"user_id": user_id}, {"document_id": document_id}]}
        ids = self.collection.get(where=where, include=[])["ids"]
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def format_context(self, chunks: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        """Number retrieved chunks for the LLM and return matching citation sources.

        Passage [n] in the context is source n, which carries the exact excerpt so the UI can show
        what each inline [n] citation refers to.
        """
        if not chunks:
            return "", []

        context_lines: list[str] = []
        sources: list[dict[str, Any]] = []
        for n, chunk in enumerate(chunks, start=1):
            doc_name = chunk.get("document_name", "Document")
            page_num = chunk.get("page_number", 1)
            content = chunk.get("content", "")
            context_lines.append(f"[{n}] {doc_name}, page {page_num}\n{content}")
            source = {"n": n, "kind": "document", "document": doc_name, "page": page_num, "excerpt": content}
            if chunk.get("section"):
                source["section"] = chunk["section"]
            sources.append(source)

        return "\n\n".join(context_lines), sources

    def clear(self) -> None:
        """Clear all indexed document chunks."""
        if self.collection is not None and self.client is not None:
            try:
                self.client.delete_collection(self.collection_name)
                self.initialize()
            except Exception:
                pass
