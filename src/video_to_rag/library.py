"""The local library: one SQLite file with channels, videos, passages, vectors and full text.

Writers open it with `open_for_write` (creates it on first use); search and the MCP server use
`open_readonly`, which can neither modify nor create it. Both refuse a library built with a
different embedding model before touching anything.
"""

import os
import sqlite3
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import platformdirs
import sqlite_vec

from .captions import Video
from .chunking import Passage

HOME_ENV = "VIDEO_TO_RAG_HOME"
FILE_NAME = "library.sqlite3"
SQLITE_SUFFIXES = ("", "-wal", "-shm", "-journal")  # the files SQLite keeps for one database
SCHEMA_VERSION = "1"
WAL_SWITCH_SECONDS = 5.0  # as long as sqlite3's default busy timeout


class LibraryError(Exception):
    pass


class ModelMismatch(LibraryError):
    pass


@dataclass(frozen=True)
class Hit:
    passage_id: int
    video_id: str
    title: str
    channel_id: str
    channel_name: str
    published: str | None
    start: float
    end: float
    text: str
    language: str


def library_path(data_dir: str | None, environ: Mapping[str, str] = os.environ) -> Path:
    """`--data-dir` beats VIDEO_TO_RAG_HOME beats the OS per-user data directory."""
    if data_dir:
        base = Path(data_dir).expanduser()
    elif environ.get(HOME_ENV):
        base = Path(environ[HOME_ENV]).expanduser()
    else:
        base = Path(platformdirs.user_data_dir("video-to-rag"))
    return base / FILE_NAME


def _schema(dim: int) -> str:
    return f"""
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE channels(id TEXT PRIMARY KEY, name TEXT NOT NULL);
    CREATE TABLE videos(
        id TEXT PRIMARY KEY,
        channel_id TEXT NOT NULL REFERENCES channels(id),
        title TEXT NOT NULL,
        published TEXT,
        duration_s REAL,
        language TEXT NOT NULL,
        caption_kind TEXT NOT NULL CHECK (caption_kind IN ('manual', 'auto')),
        ingested_at TEXT NOT NULL
    );
    CREATE TABLE passages(
        id INTEGER PRIMARY KEY,
        video_id TEXT NOT NULL REFERENCES videos(id),
        seq INTEGER NOT NULL,
        start_s REAL NOT NULL,
        end_s REAL NOT NULL,
        text TEXT NOT NULL,
        UNIQUE (video_id, seq)
    );
    CREATE VIRTUAL TABLE passages_fts USING fts5(text, tokenize='unicode61 remove_diacritics 2');
    CREATE VIRTUAL TABLE passages_vec USING vec0(
        embedding float[{dim}] distance_metric=cosine,
        channel_id text
    );
    """


def _connect(target: str, uri: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(target, uri=uri, isolation_level=None)  # we BEGIN/COMMIT ourselves
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _placeholders(values: Sequence) -> str:
    return ",".join("?" * len(values))


class Library:
    def __init__(self, conn: sqlite3.Connection, path: Path):
        self.conn = conn
        self.path = path
        self.created = False  # this connection created the schema
        self._inode = path.stat().st_ino

    # --- opening -------------------------------------------------------------------------

    @classmethod
    def open_for_write(cls, path: Path, model_name: str, dim: int) -> "Library":
        path.parent.mkdir(parents=True, exist_ok=True)
        library = cls(_connect(str(path)), path)
        try:
            library._ensure_wal()
            library.created = library._create_if_missing(model_name, dim)
            if not library.created:
                library._check(model_name)
            library.conn.execute("PRAGMA foreign_keys = ON")
        except BaseException:
            library.close()
            raise
        return library

    @classmethod
    def open_readonly(cls, path: Path, model_name: str) -> "Library | None":
        """None when the library does not exist yet; never creates it."""
        if not path.is_file():
            return None
        library = cls(_connect(f"{path.resolve().as_uri()}?mode=ro", uri=True), path)
        try:
            if not library._has_schema():
                library.close()
                return None
            library._check(model_name)
        except BaseException:
            library.close()
            raise
        return library

    def close(self) -> None:
        self.conn.close()

    def _has_schema(self) -> bool:
        sql = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
        return self.conn.execute(sql).fetchone() is not None

    def meta(self) -> dict[str, str]:
        return dict(self.conn.execute("SELECT key, value FROM meta"))

    def _check(self, model_name: str) -> None:
        meta = self.meta()
        if meta.get("schema_version") != SCHEMA_VERSION:
            raise LibraryError(
                f"{self.path} has schema version {meta.get('schema_version')}; "
                f"this version of video-to-rag reads version {SCHEMA_VERSION}"
            )
        if meta.get("embedding_model") != model_name:
            raise ModelMismatch(
                f"the library at {self.path} was built with the embedding model "
                f"{meta.get('embedding_model')}, but this version of video-to-rag uses "
                f"{model_name}; re-indexing is not available yet, so the library was left unchanged"
            )

    def _create_if_missing(self, model_name: str, dim: int) -> bool:
        """Create the schema unless it exists; True when this call created it.

        The check runs under the write lock, so two first ingests never both create it.
        """
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            if self._has_schema():
                self.conn.execute("ROLLBACK")
                return False
            # One statement at a time: executescript() would COMMIT the open transaction.
            for statement in filter(str.strip, _schema(dim).split(";")):
                self.conn.execute(statement)
            self.conn.executemany(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                [
                    ("schema_version", SCHEMA_VERSION),
                    ("embedding_model", model_name),
                    ("embedding_dim", str(dim)),
                ],
            )
            self.conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise
        return True

    def _ensure_wal(self) -> None:
        """Switch to WAL (persistent). The switch needs an exclusive lock and SQLite does not
        wait for it, so a concurrent first ingest would fail at once: retry for a bounded time."""
        deadline = time.monotonic() + WAL_SWITCH_SECONDS
        while self.conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            try:
                self.conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as error:
                if "locked" not in str(error) or time.monotonic() > deadline:
                    raise
                time.sleep(0.05)

    def _rollback(self) -> None:
        # SQLite may already have rolled back (e.g. on SQLITE_FULL); a second ROLLBACK would
        # raise and hide the original error.
        if self.conn.in_transaction:
            self.conn.execute("ROLLBACK")

    def _ensure_same_file(self) -> None:
        """Under the write lock: the file this connection writes is still the library."""
        try:
            same = self.path.stat().st_ino == self._inode
        except FileNotFoundError:
            same = False
        if not same:
            raise LibraryError(
                f"{self.path} was removed while this ingest ran (another first ingest failed and "
                "discarded it); run the ingest again"
            )

    def discard_if_new_and_empty(self) -> bool:
        """After a failed first ingest: delete the library if this connection created it and it
        holds no video. Only SQLite's own files are deleted. Closes the library either way.

        The check and the deletion run under the write lock; an ingest waiting for that lock
        then finds its file gone (see `_ensure_same_file`) instead of writing into it.
        """
        discarded = False
        try:
            if self.created:
                self.conn.execute("BEGIN IMMEDIATE")
                if self.video_count() == 0:
                    for suffix in SQLITE_SUFFIXES:
                        Path(f"{self.path}{suffix}").unlink(missing_ok=True)
                    discarded = True
                self._rollback()
        except (sqlite3.Error, OSError):
            pass  # keep the library; the caller reports the original failure
        finally:
            self.close()
        return discarded

    # --- writing -------------------------------------------------------------------------

    def store(self, video: Video, passages: Sequence[Passage], vectors: np.ndarray) -> None:
        """Replace the video and its passages in one transaction: all of it or nothing."""
        if len(passages) != len(vectors):
            raise ValueError(f"{len(passages)} passages but {len(vectors)} vectors")
        now = datetime.now(UTC).isoformat(timespec="seconds")
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            self._ensure_same_file()
            old = [
                r[0]
                for r in conn.execute("SELECT id FROM passages WHERE video_id = ?", (video.id,))
            ]
            if old:
                marks = _placeholders(old)
                conn.execute(f"DELETE FROM passages_fts WHERE rowid IN ({marks})", old)
                conn.execute(f"DELETE FROM passages_vec WHERE rowid IN ({marks})", old)
                conn.execute("DELETE FROM passages WHERE video_id = ?", (video.id,))
            conn.execute(
                "INSERT INTO channels(id, name) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
                (video.channel_id, video.channel_name),
            )
            conn.execute(
                "INSERT INTO videos(id, channel_id, title, published, duration_s, language, "
                "caption_kind, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET channel_id = excluded.channel_id, "
                "title = excluded.title, published = excluded.published, "
                "duration_s = excluded.duration_s, language = excluded.language, "
                "caption_kind = excluded.caption_kind, ingested_at = excluded.ingested_at",
                (
                    video.id,
                    video.channel_id,
                    video.title,
                    video.published,
                    video.duration_s,
                    video.language,
                    video.caption_kind,
                    now,
                ),
            )
            for passage, vector in zip(passages, vectors, strict=True):
                self._insert_passage(video, passage, vector)
            conn.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def _insert_passage(self, video: Video, passage: Passage, vector: np.ndarray) -> None:
        cursor = self.conn.execute(
            "INSERT INTO passages(video_id, seq, start_s, end_s, text) VALUES (?, ?, ?, ?, ?)",
            (video.id, passage.seq, passage.start, passage.end, passage.text),
        )
        rowid = cursor.lastrowid
        self.conn.execute(
            "INSERT INTO passages_fts(rowid, text) VALUES (?, ?)", (rowid, passage.text)
        )
        self.conn.execute(
            "INSERT INTO passages_vec(rowid, embedding, channel_id) VALUES (?, ?, ?)",
            (rowid, np.asarray(vector, dtype=np.float32).tobytes(), video.channel_id),
        )

    # --- reading -------------------------------------------------------------------------

    def video_count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM videos").fetchone()[0]

    def passage_count(self, video_id: str | None = None) -> int:
        """Passages of one video, or of the whole library."""
        if video_id is None:
            return self.conn.execute("SELECT count(*) FROM passages").fetchone()[0]
        sql = "SELECT count(*) FROM passages WHERE video_id = ?"
        return self.conn.execute(sql, (video_id,)).fetchone()[0]

    def document_frequency(self, token: str) -> int:
        """How many passages contain `token`, as the full-text index tokenizes it."""
        sql = "SELECT count(*) FROM passages_fts WHERE passages_fts MATCH ?"
        return self.conn.execute(sql, (f'"{token}"',)).fetchone()[0]

    def channel_ids_matching(self, name_or_id: str) -> list[str]:
        """Channels whose name matches case-insensitively, or whose id matches exactly."""
        wanted = name_or_id.strip().casefold()
        return [
            cid
            for cid, name in self.conn.execute("SELECT id, name FROM channels ORDER BY id")
            if cid == name_or_id.strip() or name.casefold() == wanted
        ]

    def knn(
        self, vector: np.ndarray, k: int, channel_ids: Sequence[str] | None = None
    ) -> list[tuple[int, float]]:
        sql = "SELECT rowid, distance FROM passages_vec WHERE embedding MATCH ? AND k = ?"
        params: list = [np.asarray(vector, dtype=np.float32).tobytes(), k]
        if channel_ids:
            sql += f" AND channel_id IN ({_placeholders(channel_ids)})"
            params += list(channel_ids)
        return list(self.conn.execute(sql + " ORDER BY distance", params))

    def fts(self, match: str, k: int, channel_ids: Sequence[str] | None = None) -> list[int]:
        """Passage ids for an FTS5 MATCH expression, best BM25 rank first."""
        sql = "SELECT f.rowid FROM passages_fts f"
        params: list = [match]
        where = "passages_fts MATCH ?"
        if channel_ids:
            sql += " JOIN passages p ON p.id = f.rowid JOIN videos v ON v.id = p.video_id"
            where += f" AND v.channel_id IN ({_placeholders(channel_ids)})"
            params += list(channel_ids)
        sql += f" WHERE {where} ORDER BY f.rank LIMIT ?"
        return [r[0] for r in self.conn.execute(sql, [*params, k])]

    def hits(self, passage_ids: Sequence[int]) -> list[Hit]:
        """Full hit records, in the order of `passage_ids`."""
        if not passage_ids:
            return []
        rows = self.conn.execute(
            "SELECT p.id, v.id, v.title, c.id, c.name, v.published, p.start_s, p.end_s, p.text, "
            "v.language FROM passages p JOIN videos v ON v.id = p.video_id "
            f"JOIN channels c ON c.id = v.channel_id WHERE p.id IN ({_placeholders(passage_ids)})",
            list(passage_ids),
        )
        by_id = {row[0]: Hit(*row) for row in rows}
        return [by_id[pid] for pid in passage_ids if pid in by_id]
