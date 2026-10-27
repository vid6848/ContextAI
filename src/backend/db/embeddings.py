"""One shared sentence-embedding model (all-MiniLM-L6-v2 via ONNX, 384-d), used by every vector feature."""

import ctypes
import os
import sys
import threading
from functools import cached_property
from typing import Any

import numpy as np

_embedder: Any = None
_lock = threading.Lock()


def _lean_minilm() -> Any:
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    class LeanMiniLM(ONNXMiniLM_L6_V2):
        """Chroma's MiniLM with the same weights and vectors, sized for a 512 MB instance.

        Chroma pads every text to 256 tokens and lets ONNX keep a growing memory arena; together that
        peaked near 700 MB for 96 short sentences. Here each batch is padded only to its longest text
        (mean pooling ignores padding, so the vectors are unchanged) and the arena is off.
        """

        @cached_property
        def tokenizer(self) -> Any:
            tokenizer = super().tokenizer
            tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")  # to the longest text in the batch
            return tokenizer

        @cached_property
        def model(self) -> Any:
            options = self.ort.SessionOptions()
            options.log_severity_level = 3
            options.enable_cpu_mem_arena = False
            options.enable_mem_pattern = False
            # One thread: hosts like Render report the machine's many cores while granting a fraction of
            # one, and every extra ONNX thread keeps its own buffers
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            path = os.path.join(self.DOWNLOAD_PATH, self.EXTRACTED_FOLDER_NAME, "model.onnx")
            return self.ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])

        def _forward(self, documents: list[str], batch_size: int = 8) -> np.ndarray:
            vectors = []
            for i in range(0, len(documents), batch_size):
                encoded = self.tokenizer.encode_batch(documents[i : i + batch_size])
                ids = np.array([e.ids for e in encoded], dtype=np.int64)
                mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
                hidden = self.model.run(
                    None, {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
                )[0]
                weights = mask[..., None].astype(np.float32)
                pooled = (hidden * weights).sum(1) / np.clip(weights.sum(1), 1e-9, None)
                vectors.append(self._normalize(pooled).astype(np.float32))
            return np.concatenate(vectors) if vectors else np.zeros((0, 384), dtype=np.float32)

    return LeanMiniLM()


def get_embedder() -> Any:
    """Chroma's "default" embedding function, loaded once per process (~90 MB) and shared.

    Chroma's own DefaultEmbeddingFunction builds a new ONNX session on every call; this keeps its name,
    so collections created with it open unchanged, but holds a single lean session.
    """
    global _embedder
    with _lock:
        if _embedder is None:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            class SharedEmbedder(DefaultEmbeddingFunction):
                def __init__(self) -> None:
                    self.model = _lean_minilm()

                def __call__(self, input: Any) -> Any:
                    return self.model(input)

            _embedder = SharedEmbedder()
        return _embedder


def release_memory() -> None:
    """Hand freed heap back to the OS (glibc keeps it otherwise), so a spike doesn't stay counted."""
    if sys.platform.startswith("linux"):
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except OSError:
            pass


def embed(texts: list[str]) -> list[list[float]]:
    return [list(map(float, v)) for v in get_embedder()(texts)]


def to_pgvector(values: list[float]) -> str:
    """Text form of a vector; passed with a ::vector cast so no driver adapter is needed."""
    return "[" + ",".join(f"{x:.7g}" for x in values) + "]"
