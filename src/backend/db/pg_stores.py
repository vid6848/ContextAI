"""pgvector-backed long-term memory and document stores (used when DATABASE_URL points at Postgres).

They expose the same methods as the ChromaDB stores, so the agent and API don't know which is in use.
Distances are reported as squared L2 over unit vectors (2 * cosine distance), matching Chroma's.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from src.backend.db import Database
from src.backend.db.embeddings import embed, to_pgvector
from src.backend.rag.pipeline import DocumentRAGPipeline


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PgMemoryStore:
    """Long-term memories: one row per fact, with its embedding."""

    def __init__(self, database_url: str) -> None:
        self.db = Database(database_url)

    def add_memory(
        self, memory: str, user_id: str, metadata: dict[str, Any] | None = None, memory_id: str | None = None
    ) -> str:
        mid = memory_id or f"mem_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (id, user_id, fact, embedding, source, created_at, updated_at)
                VALUES (?, ?, ?, ?::vector, ?, ?, ?)
                """,
                (mid, user_id, memory, to_pgvector(embed([memory])[0]),
                 (metadata or {}).get("source", "chat"), now, now),
            )
        return mid

    def search_memories(self, query: str, user_id: str | None = None, limit: int = 4) -> list[dict[str, Any]]:
        vec = to_pgvector(embed([query])[0])
        sql = "SELECT id, fact, user_id, source, 2 * (embedding <=> ?::vector) AS distance FROM memories"
        params: list[Any] = [vec]
        if user_id:
            sql += " WHERE user_id = ?"
            params.append(user_id)
        sql += " ORDER BY embedding <=> ?::vector LIMIT ?"
        params += [vec, limit]
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {"id": r["id"], "memory": r["fact"], "metadata": {"user_id": r["user_id"], "source": r["source"]},
             "distance": float(r["distance"])}
            for r in rows
        ]

    def get_relevant_memories(self, query: str, user_id: str, limit: int = 4) -> list[str]:
        return [m["memory"] for m in self.search_memories(query, user_id=user_id, limit=limit)]

    def similarity_search(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        return self.search_memories(query, limit=k)

    def list_memories(self, user_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, fact, source, created_at, updated_at FROM memories WHERE user_id = ? "
                "ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return rows

    def update_memory(self, memory_id: str, user_id: str, fact: str) -> bool:
        with self.db.connect() as conn:
            return conn.execute(
                "UPDATE memories SET fact = ?, embedding = ?::vector, updated_at = ? WHERE id = ? AND user_id = ?",
                (fact, to_pgvector(embed([fact])[0]), _now(), memory_id, user_id),
            ).rowcount > 0

    def delete_memory(self, memory_id: str, user_id: str) -> bool:
        with self.db.connect() as conn:
            return conn.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id)).rowcount > 0

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        with self.db.connect() as conn:
            return conn.execute(
                "UPDATE memories SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id)
            ).rowcount

    def delete_user_memories(self, user_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))


class PgDocumentRAGPipeline(DocumentRAGPipeline):
    """Same PDF parsing, structure-aware chunking and re-ranking as the Chroma pipeline; pgvector storage."""

    def __init__(self, database_url: str) -> None:  # noqa: D107 - storage differs, ingestion is inherited
        self.db = Database(database_url)
        self.collection = None
        self.client = None
        self.collection_name = "document_chunks"

    def initialize(self) -> None:
        """Nothing to open: the schema is applied with the connection pool."""

    @staticmethod
    def _filter(user_id: str | None, document_names: list[str] | None) -> tuple[str, list[Any]]:
        clauses, params = [], []
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if document_names:
            clauses.append("document_name = ANY(?)")
            params.append(list(document_names))
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def count(self, user_id: str | None = None, document_names: list[str] | None = None) -> int:
        where, params = self._filter(user_id, document_names)
        with self.db.connect() as conn:
            return int(conn.execute(f"SELECT count(*) AS n FROM document_chunks{where}", params).fetchone()["n"])

    def _upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        vectors = embed(documents)
        with self.db.connect() as conn:
            for cid, text, meta, vec in zip(ids, documents, metadatas, vectors, strict=True):
                conn.execute(
                    """
                    INSERT INTO document_chunks (id, user_id, document_id, document_name, page_number, chunk_index,
                                                 section, total_pages, uploaded_at, content, embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::vector)
                    ON CONFLICT (id) DO UPDATE SET content = excluded.content, embedding = excluded.embedding,
                        section = excluded.section, document_name = excluded.document_name
                    """,
                    (cid, meta.get("user_id"), meta["document_id"], meta["document_name"], meta["page_number"],
                     meta["chunk_index"], meta.get("section"), meta.get("total_pages"), meta.get("uploaded_at"),
                     text, to_pgvector(vec)),
                )

    def _candidates(
        self, query: str, n: int, user_id: str | None, document_names: list[str] | None
    ) -> list[dict[str, Any]]:
        where, params = self._filter(user_id, document_names)
        vec = to_pgvector(embed([query])[0])
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, content, document_name, page_number, section, 2 * (embedding <=> ?::vector) AS distance
                FROM document_chunks{where} ORDER BY embedding <=> ?::vector LIMIT ?
                """,
                [vec, *params, vec, n],
            ).fetchall()
        return [
            {"content": r["content"], "document_name": r["document_name"], "page_number": r["page_number"],
             "chunk_id": r["id"], "distance": float(r["distance"]), "section": r["section"]}
            for r in rows
        ]

    def _passages(self, user_id: str | None, document_names: list[str] | None) -> list[dict[str, Any]]:
        where, params = self._filter(user_id, document_names)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, content, document_name, page_number, chunk_index, section
                FROM document_chunks{where} ORDER BY document_name, chunk_index
                """,
                params,
            ).fetchall()
        return [
            {"content": r["content"], "document_name": r["document_name"], "page_number": r["page_number"],
             "chunk_id": r["id"], "chunk_index": r["chunk_index"], "section": r["section"]}
            for r in rows
        ]

    def list_documents(self, user_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            return conn.execute(
                """
                SELECT document_id, min(document_name) AS document_name,
                       max(coalesce(total_pages, page_number)) AS pages, count(*) AS chunks,
                       max(uploaded_at) AS uploaded_at
                FROM document_chunks WHERE user_id = ? GROUP BY document_id ORDER BY max(uploaded_at) DESC
                """,
                (user_id,),
            ).fetchall()

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        with self.db.connect() as conn:
            return conn.execute(
                "UPDATE document_chunks SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id)
            ).rowcount

    def delete_document(self, user_id: str, document_id: str) -> int:
        with self.db.connect() as conn:
            return conn.execute(
                "DELETE FROM document_chunks WHERE user_id = ? AND document_id = ?", (user_id, document_id)
            ).rowcount

    def clear(self) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM document_chunks")
