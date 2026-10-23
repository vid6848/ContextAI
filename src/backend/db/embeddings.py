"""One shared sentence-embedding model (all-MiniLM-L6-v2 via ONNX, 384-d), used by every vector feature."""

import threading
from typing import Any

_embedder: Any = None
_lock = threading.Lock()


def get_embedder() -> Any:
    """Chroma's default embedding function: loaded once per process (~90 MB) and shared."""
    global _embedder
    with _lock:
        if _embedder is None:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            _embedder = DefaultEmbeddingFunction()
        return _embedder


def embed(texts: list[str]) -> list[list[float]]:
    return [list(map(float, v)) for v in get_embedder()(texts)]


def to_pgvector(values: list[float]) -> str:
    """Text form of a vector; passed with a ::vector cast so no driver adapter is needed."""
    return "[" + ",".join(f"{x:.7g}" for x in values) + "]"
