"""ChromaDB semantic long-term memory store for ContextAI."""

import os
import uuid
from typing import Any
import chromadb
from src.backend.core.config import settings


class ChromaMemoryStore:
    """Persistent semantic memory store powered by ChromaDB."""

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
        meta = {"user_id": user_id}
        if metadata:
            meta.update(metadata)

        self.collection.add(
            documents=[memory],
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

        if self.collection.count() == 0:
            return []

        where_filter = {"user_id": user_id} if user_id else None

        results = self.collection.query(
            query_texts=[query],
            n_results=min(limit, self.collection.count()),
            where=where_filter,
        )

        memories: list[dict[str, Any]] = []
        if results and results.get("documents") and results["documents"][0]:
            docs = results["documents"][0]
            metas = results.get("metadatas", [[]])[0]
            ids = results.get("ids", [[]])[0]
            distances = results.get("distances", [[]])[0] if results.get("distances") else [None] * len(docs)

            for doc, meta, mid, dist in zip(docs, metas, ids, distances):
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

    def delete_user_memories(self, user_id: str) -> None:
        """Delete all memories associated with a specific user."""
        if self.collection is None:
            self.initialize()
        if self.collection.count() > 0:
            try:
                self.collection.delete(where={"user_id": user_id})
            except Exception:
                pass
