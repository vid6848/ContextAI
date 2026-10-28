"""ChromaDB semantic long-term memory store for ContextAI."""

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import chromadb

from src.backend.core.config import settings
from src.backend.db.embeddings import embed


class ChromaMemoryStore:
    """Persistent semantic memory store powered by ChromaDB.

    Vectors come from the shared embedder: Chroma would otherwise load its own, full-size copy of the model.
    """

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str = "context_memory",
    ) -> None:
        self.persist_dir = persist_dir if persist_dir is not None else settings.chroma_persist_dir
        self.collection_name = collection_name
        self.client: chromadb.ClientAPI | None = None
        self.collection: Any = None
        self._ensure_dir()
        self.initialize()

    def _ensure_dir(self) -> None:
        """Ensure parent directory exists for Chroma persistence."""
        if self.persist_dir:
            os.makedirs(os.path.abspath(self.persist_dir), exist_ok=True)

    def initialize(self) -> None:
        """Initialize ChromaDB persistent client and retrieve or create the memory collection."""
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "ContextAI semantic long-term memories"},
        )

    def add_memory(
        self,
        memory: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
        memory_id: str | None = None,
    ) -> str:
        """Add a single long-term memory associated with a user_id."""
        if self.collection is None:
            self.initialize()

        mid = memory_id or f"mem_{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat()
        meta = {"user_id": user_id, "created_at": now, "updated_at": now}
        if metadata:
            meta.update(metadata)

        self.collection.add(
            documents=[memory],
            embeddings=embed([memory]),
            metadatas=[meta],
            ids=[mid],
        )
        return mid

    def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """Add multiple documents/memories into the vector store."""
        if self.collection is None:
            self.initialize()

        if ids is None:
            ids = [f"mem_{uuid.uuid4().hex[:12]}" for _ in documents]
        if metadatas is None:
            metadatas = [{} for _ in documents]

        self.collection.add(
            documents=documents,
            embeddings=embed(documents),
            metadatas=metadatas,
            ids=ids,
        )
        return ids

    def search_memories(
        self,
        query: str,
        user_id: str | None = None,
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        """Search memories semantically with optional user_id filtering."""
        if self.collection is None:
            self.initialize()

        where_filter = {"user_id": user_id} if user_id else None
        available = (
            len(self.collection.get(where=where_filter, include=[])["ids"]) if where_filter else self.collection.count()
        )
        if available == 0:
            return []

        results = self.collection.query(
            query_embeddings=embed([query]),
            n_results=min(limit, available),
            where=where_filter,
        )

        memories: list[dict[str, Any]] = []
        if results and results.get("documents") and results["documents"][0]:
            docs = results["documents"][0]
            metas = results.get("metadatas", [[]])[0]
            ids = results.get("ids", [[]])[0]
            distances = results.get("distances", [[]])[0] if results.get("distances") else [None] * len(docs)

            for doc, meta, mid, dist in zip(docs, metas, ids, distances, strict=False):
                memories.append({
                    "id": mid,
                    "memory": doc,
                    "metadata": meta,
                    "distance": dist,
                })
        return memories

    def get_relevant_memories(
        self,
        query: str,
        user_id: str,
        limit: int = 4,
    ) -> list[str]:
        """Return the most relevant memory text strings for a given user and query."""
        results = self.search_memories(query=query, user_id=user_id, limit=limit)
        return [item["memory"] for item in results]

    def similarity_search(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        """Compatibility method for vector similarity search."""
        return self.search_memories(query=query, limit=k)

    def list_memories(self, user_id: str) -> list[dict[str, Any]]:
        """All of a user's memories, most recently updated first."""
        if self.collection is None:
            self.initialize()
        rows = self.collection.get(where={"user_id": user_id}, include=["documents", "metadatas"])
        items = [
            {
                "id": mid,
                "fact": doc,
                "source": (meta or {}).get("source", "chat"),
                "created_at": (meta or {}).get("created_at"),
                "updated_at": (meta or {}).get("updated_at"),
            }
            for mid, doc, meta in zip(rows["ids"], rows["documents"], rows["metadatas"], strict=False)
        ]
        return sorted(items, key=lambda m: m.get("updated_at") or "", reverse=True)

    def _owned(self, memory_id: str, user_id: str) -> dict[str, Any] | None:
        rows = self.collection.get(ids=[memory_id], include=["metadatas"])
        if not rows["ids"] or (rows["metadatas"][0] or {}).get("user_id") != user_id:
            return None
        return rows["metadatas"][0]

    def update_memory(self, memory_id: str, user_id: str, fact: str) -> bool:
        """Rewrite one of the user's memories. False if it doesn't exist or belongs to someone else."""
        if self.collection is None:
            self.initialize()
        meta = self._owned(memory_id, user_id)
        if meta is None:
            return False
        meta = {**meta, "updated_at": datetime.now(UTC).isoformat()}
        self.collection.update(ids=[memory_id], documents=[fact], embeddings=embed([fact]), metadatas=[meta])
        return True

    def delete_memory(self, memory_id: str, user_id: str) -> bool:
        """Delete one of the user's memories. False if it doesn't exist or belongs to someone else."""
        if self.collection is None:
            self.initialize()
        if self._owned(memory_id, user_id) is None:
            return False
        self.collection.delete(ids=[memory_id])
        return True

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        if self.collection is None:
            self.initialize()
        rows = self.collection.get(where={"user_id": old_user_id}, include=["metadatas"])
        if rows["ids"]:
            metas = [{**(m or {}), "user_id": new_user_id} for m in rows["metadatas"]]
            self.collection.update(ids=rows["ids"], metadatas=metas)
        return len(rows["ids"])

    def delete_user_memories(self, user_id: str) -> None:
        """Delete all memories associated with a specific user."""
        if self.collection is None:
            self.initialize()
        if self.collection.count() > 0:
            try:
                self.collection.delete(where={"user_id": user_id})
            except Exception:
                pass
