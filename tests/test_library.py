import hashlib
import sqlite3

import pytest
from helpers import FakeEmbedder

from video_to_rag.captions import Video
from video_to_rag.chunking import Passage
from video_to_rag.library import (
    HOME_ENV,
    Library,
    ModelMismatch,
    library_path,
)

EMBEDDER = FakeEmbedder()


def video(video_id="abc123DEF45", channel=("UC_A", "Huberman Lab"), title="Focus episode"):
    return Video(
        id=video_id,
        title=title,
        channel_id=channel[0],
        channel_name=channel[1],
        published="2024-03-11",
        duration_s=7342,
        language="en",
        caption_kind="auto",
    )


def passages(*texts):
    return [Passage(seq=i, start=i * 50.0, end=i * 50.0 + 60, text=t) for i, t in enumerate(texts)]


def store(library, v, ps):
    library.store(v, ps, EMBEDDER.embed_passages([p.text for p in ps]))


def open_rw(path, embedder=EMBEDDER):
    return Library.open_for_write(path, embedder.model_name, embedder.dim)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count(library, table):
    return library.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


# --- Library location --------------------------------------------------------------------


def test_location_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    environ = {"HOME": str(tmp_path)}
    expected = tmp_path / ".local" / "share" / "video-to-rag" / "library.sqlite3"
    assert library_path(None, environ) == expected


def test_location_environment_override(tmp_path):
    environ = {HOME_ENV: str(tmp_path / "srv" / "vtr")}
    assert library_path(None, environ) == tmp_path / "srv" / "vtr" / "library.sqlite3"


def test_location_option_beats_environment(tmp_path):
    env_dir = tmp_path / "srv" / "vtr"
    path = library_path(str(tmp_path / "lib"), {HOME_ENV: str(env_dir)})
    assert path == tmp_path / "lib" / "library.sqlite3"
    open_rw(path).close()
    assert path.is_file()
    assert not env_dir.exists()


# --- Shared multi-channel library / idempotent and atomic ingest -------------------------


def test_channel_two_channels_side_by_side(tmp_path):
    library = open_rw(tmp_path / "library.sqlite3")
    store(library, video("vidA0000001", ("UC_A", "Channel A")), passages("alpha talk"))
    store(library, video("vidB0000001", ("UC_B", "Channel B")), passages("beta talk"))
    hits = library.hits(library.fts('"talk"', 10))
    assert {(h.video_id, h.channel_name) for h in hits} == {
        ("vidA0000001", "Channel A"),
        ("vidB0000001", "Channel B"),
    }


def test_upsert_same_video_twice_keeps_passages_once(tmp_path):
    library = open_rw(tmp_path / "library.sqlite3")
    store(library, video(), passages("one", "two", "three"))
    store(library, video(title="Focus episode (re-upload)"), passages("one", "two", "three"))
    for table in ("passages", "passages_fts", "passages_vec"):
        assert count(library, table) == 3
    assert count(library, "videos") == 1
    hits = library.hits(library.fts('"one" OR "two" OR "three"', 10))
    assert sorted(h.text for h in hits) == ["one", "three", "two"]
    assert {h.title for h in hits} == {"Focus episode (re-upload)"}


def test_upsert_fewer_passages_removes_the_rest(tmp_path):
    library = open_rw(tmp_path / "library.sqlite3")
    store(library, video(), passages("one", "two", "three"))
    store(library, video(), passages("only"))
    for table in ("passages", "passages_fts", "passages_vec"):
        assert count(library, table) == 1


def test_atomic_interrupted_reingest_keeps_old_passages(tmp_path, monkeypatch):
    path = tmp_path / "library.sqlite3"
    library = open_rw(path)
    store(library, video(), passages("cold exposure raises dopamine", "sleep matters"))

    original = Library._insert_passage
    calls = []

    def interrupted(self, *args):
        calls.append(args)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return original(self, *args)

    monkeypatch.setattr(Library, "_insert_passage", interrupted)
    with pytest.raises(KeyboardInterrupt):
        store(library, video(title="new"), passages("replacement one", "replacement two"))
    monkeypatch.undo()
    library.close()

    library = Library.open_readonly(path, EMBEDDER.model_name)
    hits = library.hits(library.fts('"dopamine"', 10))
    assert [h.title for h in hits] == ["Focus episode"]
    vector = EMBEDDER.embed_queries(["sleep matters"])[0]
    assert library.hits([pid for pid, _ in library.knn(vector, 5)])[0].text == "sleep matters"
    assert count(library, "passages") == 2


def test_store_rejects_mismatched_vectors(tmp_path):
    library = open_rw(tmp_path / "library.sqlite3")
    with pytest.raises(ValueError):
        library.store(video(), passages("a", "b"), EMBEDDER.embed_passages(["a"]))


# --- Embedding model bookkeeping / read-only opening ------------------------------------


class OtherEmbedder(FakeEmbedder):
    model_name = "other/model-y"


def test_model_recorded(tmp_path):
    library = open_rw(tmp_path / "library.sqlite3")
    assert library.meta() == {
        "schema_version": "1",
        "embedding_model": EMBEDDER.model_name,
        "embedding_dim": str(EMBEDDER.dim),
    }


def test_model_mismatch_refused_for_writing(tmp_path):
    path = tmp_path / "library.sqlite3"
    library = open_rw(path)
    store(library, video(), passages("one"))
    library.close()
    before = digest(path)
    with pytest.raises(ModelMismatch) as exc:
        open_rw(path, OtherEmbedder())
    assert EMBEDDER.model_name in str(exc.value) and "other/model-y" in str(exc.value)
    assert digest(path) == before


def test_model_mismatch_refused_for_reading(tmp_path):
    path = tmp_path / "library.sqlite3"
    open_rw(path).close()
    with pytest.raises(ModelMismatch, match="other/model-y"):
        Library.open_readonly(path, "other/model-y")


def test_readonly_open_never_creates_the_library(tmp_path):
    path = tmp_path / "data" / "library.sqlite3"
    assert Library.open_readonly(path, EMBEDDER.model_name) is None
    assert not (tmp_path / "data").exists()


def test_readonly_open_cannot_write(tmp_path):
    path = tmp_path / "library.sqlite3"
    open_rw(path).close()
    library = Library.open_readonly(path, EMBEDDER.model_name)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        library.conn.execute("DELETE FROM videos")
