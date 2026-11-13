"""Shared test helpers (imported by test modules; pytest puts `tests/` on sys.path)."""

import hashlib
import io
import json
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

import numpy as np

FIXTURES = Path(__file__).parent / "fixtures"
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def project_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


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


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL; records how it was configured and what it fetched."""

    def __init__(self, params, info, captions, error):
        self.params, self._info, self._captions, self._error = params, info, captions, error
        self.extracted, self.opened = [], []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        self.extracted.append((url, download))
        if self._error:
            raise self._error
        return self._info

    def urlopen(self, url):
        self.opened.append(url)
        return io.BytesIO(json.dumps(self._captions).encode())


class FakeYDLFactory:
    """A `ydl_factory` for the YouTube adapter that hands out FakeYDL instances."""

    def __init__(self, info=None, captions=None, error=None):
        self.info = info or load_fixture("info_manual_and_auto.json")
        self.captions = captions or load_fixture("captions_manual.json3")
        self.error = error
        self.instances: list[FakeYDL] = []

    def __call__(self, params):
        ydl = FakeYDL(params, self.info, self.captions, self.error)
        self.instances.append(ydl)
        return ydl

    @property
    def params(self):
        return self.instances[-1].params


def which_all(name):
    return f"/usr/bin/{name}"
