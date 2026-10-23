"""Shared test helpers (imported by test modules; pytest puts `tests/` on sys.path)."""

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeEmbedder:
    """Deterministic hashed bag-of-words vectors: shared words -> similar vectors, no model."""

    model_name = "fake/hashed-bag-of-words"

    def __init__(self, dim: int = 64):
        self.dim = dim

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        for word in re.findall(r"\w+", text.lower()):
            h = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "little")
            vector[h % self.dim] += 1.0 if (h >> 32) & 1 else -1.0
        norm = np.linalg.norm(vector)
        if norm == 0:
            vector[0] = 1.0
            return vector
        return vector / norm

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        return np.array([self._vector(t) for t in texts], dtype=np.float32).reshape(-1, self.dim)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts)

    def embed_passages(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts)

    def count_tokens(self, text: str) -> int:
        return len(text.split())
