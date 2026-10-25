"""Embedder protocol and the local E5 implementation (fastembed, ONNX Runtime on CPU)."""

import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
import platformdirs

from .redact import logger, redact

MODEL_NAME = "intfloat/multilingual-e5-large"
MODEL_DIM = 1024
MODEL_CACHE_ENTRY = "models--Qdrant--multilingual-e5-large-onnx"  # fastembed's HF-hub layout
# Texts per ONNX run. fastembed's default (256) pads a whole long video into one run, and its
# memory grows with that; 16 keeps a 3-hour ingest near 2 GB at the same speed on CPU.
EMBED_BATCH = 16


class EmbeddingUnavailable(Exception):
    """The embedding model could not be downloaded or loaded."""


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
    """multilingual-e5-large with `query: ` / `passage: ` prefixes; loads lazily, stays loaded.

    Thread-safe: the MCP server runs each tool call in its own thread. One lock covers the load
    and every model call, since fastembed also builds its ONNX session lazily without a lock;
    serialising costs nothing on CPU, where one session already uses every core.
    """

    model_name = MODEL_NAME
    dim = MODEL_DIM

    def __init__(self, cache_dir: Path | None = None):
        self._cache_dir = cache_dir or model_cache_dir()
        self._model = None
        self._lock = threading.Lock()

    def _unavailable(self, error: Exception) -> EmbeddingUnavailable:
        return EmbeddingUnavailable(
            f"the embedding model {MODEL_NAME} could not be loaded "
            f"({type(error).__name__}: {redact(str(error))}). It needs about 2.2 GB of disk "
            f"under {self._cache_dir} and, the first time, access to huggingface.co"
        )

    def _load(self):
        """The model; call with the lock held."""
        if self._model is None:
            from fastembed import TextEmbedding

            if not (self._cache_dir / MODEL_CACHE_ENTRY).is_dir():
                logger.info(
                    "first run: downloading the embedding model %s (~2.2 GB) to %s; "
                    "this happens once",
                    MODEL_NAME,
                    self._cache_dir,
                )
            try:
                self._model = TextEmbedding(
                    MODEL_NAME, cache_dir=str(self._cache_dir), lazy_load=True
                )
            except Exception as error:
                raise self._unavailable(error) from error
        return self._model

    def _embed(self, prefix: str, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        prefixed = [prefix + t for t in texts]
        with self._lock:
            model = self._load()
            try:
                vectors = list(model.embed(prefixed, batch_size=EMBED_BATCH))
            except Exception as error:  # e.g. the ONNX session cannot be built from the cache
                raise self._unavailable(error) from error
        return _normalized(np.array(vectors, np.float32))

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed("query: ", texts)

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed("passage: ", texts)

    def count_tokens(self, text: str) -> int:
        """Model tokens incl. special tokens; the tokenizer caps at 512, still above our bound."""
        with self._lock:
            return self._load().token_count(text)
