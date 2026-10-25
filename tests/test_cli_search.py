import hashlib
import re

import pytest
from helpers import FakeEmbedder

from video_to_rag.captions import Video
from video_to_rag.chunking import Passage
from video_to_rag.cli import main
from video_to_rag.embedding import EmbeddingUnavailable
from video_to_rag.library import Library

TEXTS = [
    "to improve focus at work, limit your visual field and work in ninety minute blocks",
    "focus also improves after a short walk outside in the morning",
    "caffeine delays the afternoon crash when you wait ninety minutes after waking",
    "deliberate cold exposure raises dopamine for hours",
    "morning sunlight helps you fall asleep and improves focus the next day",
]


@pytest.fixture
def filled(tmp_path):
    embedder = FakeEmbedder()
    path = tmp_path / "library.sqlite3"
    library = Library.open_for_write(path, embedder.model_name, embedder.dim)
    video = Video(
        "abc123DEF45", "Focus Toolkit", "UC_A", "Huberman Lab", "2024-03-11", 7200, "en", "auto"
    )
    passages = [Passage(i, 1800.0 + i * 50, 1860.0 + i * 50, t) for i, t in enumerate(TEXTS)]
    library.store(video, passages, embedder.embed_passages(TEXTS))
    library.close()
    return path


def run(tmp_path, *args, embedder=None):
    argv = ["--data-dir", str(tmp_path), "search", *args]
    return main(argv, environ={}, embedder=embedder or FakeEmbedder())


def test_command_line_search(filled, tmp_path, capsys):
    assert run(tmp_path, "how to improve focus", "--limit", "3") == 0
    out = capsys.readouterr().out
    blocks = re.split(r"\n\n(?=\d+\. )", out.strip())
    assert [b.split(".", 1)[0] for b in blocks] == ["1", "2", "3"]
    for block in blocks:
        assert "Focus Toolkit — Huberman Lab (2024-03-11)" in block
        assert re.search(r"\d+:\d\d–\d+:\d\d  https://youtu\.be/abc123DEF45\?t=\d+  \[en\]", block)
        assert any(text in block for text in TEXTS)


def test_search_several_queries_and_channel(filled, tmp_path, capsys):
    args = ["hogyan javítsam a fókuszomat", "how to improve focus", "--channel", "HUBERMAN LAB"]
    assert run(tmp_path, *args) == 0
    assert "1. Focus Toolkit" in capsys.readouterr().out


def test_search_unknown_channel(filled, tmp_path, capsys):
    assert run(tmp_path, "focus", "--channel", "Nobody") == 0
    assert "no ingested channel matches 'Nobody'" in capsys.readouterr().out


class Untouchable(FakeEmbedder):
    def embed_queries(self, texts):
        raise AssertionError("an empty library must not load the model")


def test_search_before_any_ingest(tmp_path, capsys):
    data_dir = tmp_path / "data"
    code = main(
        ["search", "focus", "--data-dir", str(data_dir)], environ={}, embedder=Untouchable()
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "library is empty" in out and "video-to-rag ingest <video-url>" in out
    assert not data_dir.exists()


@pytest.mark.parametrize(
    "args", [["  "], ["a", "b", "c", "d", "e", "f"], ["focus", "--limit", "0"]]
)
def test_search_invalid_input_is_a_usage_error(filled, tmp_path, capsys, args):
    assert run(tmp_path, *args) == 2
    assert re.search(r"one to five non-blank|limit", capsys.readouterr().err)


def test_search_model_unavailable_is_a_clean_failure(filled, tmp_path, capsys):
    class Offline(FakeEmbedder):
        def embed_queries(self, texts):
            raise EmbeddingUnavailable("the embedding model could not be loaded (offline)")

    assert run(tmp_path, "focus", embedder=Offline()) == 1
    err = capsys.readouterr().err
    assert "could not be loaded" in err and "Traceback" not in err


def test_search_model_mismatch(filled, tmp_path, capsys):
    before = hashlib.sha256(filled.read_bytes()).hexdigest()

    class OtherEmbedder(FakeEmbedder):
        model_name = "other/model-y"

    assert run(tmp_path, "focus", embedder=OtherEmbedder()) == 1
    err = capsys.readouterr().err
    assert FakeEmbedder.model_name in err and "other/model-y" in err
    assert hashlib.sha256(filled.read_bytes()).hexdigest() == before
