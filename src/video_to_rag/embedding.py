"""Embedder protocol and the local E5 implementation (fastembed, ONNX Runtime on CPU)."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
import platformdirs

from .redact import logger

MODEL_NAME = "intfloat/multilingual-e5-large"
MODEL_DIM = 1024
MODEL_CACHE_ENTRY = "models--Qdrant--multilingual-e5-large-onnx"  # fastembed's HF-hub layout


@runtime_checkable
class Embedder(Protocol):
    model_name: str
    dim: int

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray: ...

    def count_tokens(self, text: str) -> int: ...


def model_cache_dir() -> Path:
    """Persistent model cache (fastembed's default is a temp dir, lost on reboot)."""
    return Path(platformdirs.user_cache_dir("video-to-rag")) / "models"


def _normalized(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class E5Embedder:
    """multilingual-e5-large with `query: ` / `passage: ` prefixes; loads lazily, stays loaded."""

    model_name = MODEL_NAME
    dim = MODEL_DIM

    def __init__(self, cache_dir: Path | None = None):
        self._cache_dir = cache_dir or model_cache_dir()
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            if not (self._cache_dir / MODEL_CACHE_ENTRY).is_dir():
                logger.info(
                    "first run: downloading the embedding model %s (~2.2 GB) to %s; "
                    "this happens once",
                    MODEL_NAME,
                    self._cache_dir,
                )
            self._model = TextEmbedding(MODEL_NAME, cache_dir=str(self._cache_dir), lazy_load=True)
        return self._model

    def _embed(self, prefix: str, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = np.array(list(self._load().embed([prefix + t for t in texts])), np.float32)
        return _normalized(vectors)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed("query: ", texts)

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed("passage: ", texts)

    def count_tokens(self, text: str) -> int:
        """Model tokens incl. special tokens; the tokenizer caps at 512, still above our bound."""
        return self._load().token_count(text)
