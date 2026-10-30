import hashlib
import logging
import sqlite3

import pytest
from helpers import FIXTURES, FakeEmbedder, FakeYDLFactory, load_fixture, which_all

from video_to_rag.captions import (
    NoCaptions,
    Segment,
    Transcript,
    select_track,
    video_from_info,
)
from video_to_rag.cli import main
from video_to_rag.library import HOME_ENV, Library
from video_to_rag.youtube import Blocked, Unavailable, YouTube

URL = "https://www.youtube.com/watch?v=abc123DEF45&t=90s&list=PL123"
BLOCKED = Blocked("YouTube blocked the request ... --cookies-from-browser ... VIDEO_TO_RAG_PROXY")
COOKIES = str(FIXTURES / "netscape_cookies.txt")
BOTH_COOKIE_OPTIONS = ["--cookies-from-browser", "firefox", "--cookies", COOKIES]


def two_hour_transcript(info_name="info_auto_only.json"):
    info = load_fixture(info_name)
    segments = [
        Segment(start=i * 5.0, end=(i + 1) * 5.0, text=f"sentence number {i} about focus and sleep")
        for i in range(1440)
    ]
    return Transcript(video=video_from_info(info, select_track(info)), segments=segments)


class FakeYouTube:
    """Stands in for the YouTube adapter; `result` is a Transcript or an exception to raise."""

    def __init__(self, result):
        self.result = result
        self.networks, self.fetched = [], []

    def __call__(self, network):
        self.networks.append(network)
        return self

    def fetch(self, video_id):
        self.fetched.append(video_id)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def run(args, tmp_path, youtube, embedder=None, environ=None):
    argv = ["--data-dir", str(tmp_path), *args]
    return main(argv, environ=environ or {}, youtube=youtube, embedder=embedder or FakeEmbedder())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def filled(tmp_path):
    """A library that already holds one video, plus its digest."""
    other = two_hour_transcript("info_manual_and_auto.json")
    assert run(["ingest", "https://youtu.be/abc123DEF45"], tmp_path, FakeYouTube(other)) == 0
    path = tmp_path / "library.sqlite3"
    return path, digest(path)


# --- Ingest summary / video metadata -----------------------------------------------------


def test_ingest_summary(tmp_path, capsys):
    youtube = FakeYouTube(two_hour_transcript())
    assert run(["ingest", URL], tmp_path, youtube) == 0
    assert youtube.fetched == ["abc123DEF45"]  # only the video, never the playlist
    out = capsys.readouterr().out
    library = Library.open_readonly(tmp_path / "library.sqlite3", FakeEmbedder.model_name)
    stored = library.passage_count("auto0nly_EN")
    assert stored > 100
    for expected in (
        "Using Cold Exposure for Health",
        "Huberman Lab",
        f"{stored} passages",
        "auto",
        "en",
        str(tmp_path / "library.sqlite3"),
    ):
        assert expected in out


def test_ingest_metadata_on_every_hit(tmp_path):
    assert run(["ingest", URL], tmp_path, FakeYouTube(two_hour_transcript())) == 0
    library = Library.open_readonly(tmp_path / "library.sqlite3", FakeEmbedder.model_name)
    hits = library.hits(library.fts('"focus"', 50))
    assert hits
    assert {(h.title, h.channel_name, h.published) for h in hits} == {
        ("Using Cold Exposure for Health", "Huberman Lab", "2023-10-02")
    }


def test_ingest_same_video_twice_stores_it_once(tmp_path):
    youtube = FakeYouTube(two_hour_transcript())
    assert run(["ingest", URL], tmp_path, youtube) == 0
    library = Library.open_readonly(tmp_path / "library.sqlite3", FakeEmbedder.model_name)
    first = library.passage_count("auto0nly_EN")
    library.close()
    assert run(["ingest", URL], tmp_path, youtube) == 0
    library = Library.open_readonly(tmp_path / "library.sqlite3", FakeEmbedder.model_name)
    assert library.passage_count("auto0nly_EN") == first
    assert library.video_count() == 1


# --- Failures leave the library unchanged ------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            NoCaptions(
                "the video has no captions in its spoken language (en); "
                "speech-to-text is not available yet"
            ),
            "no captions",
        ),
        (BLOCKED, "blocked"),
        (Unavailable("the video is unavailable: Private video. Sign in if ..."), "Private video"),
    ],
    ids=["no-captions", "blocked", "private"],
)
def test_ingest_failure_leaves_library_unchanged(filled, tmp_path, capsys, error, expected):
    path, before = filled
    capsys.readouterr()
    assert run(["ingest", URL], tmp_path, FakeYouTube(error)) == 1
    assert expected in capsys.readouterr().err
    assert digest(path) == before


def test_ingest_captions_without_speech(tmp_path, capsys):
    info = load_fixture("info_auto_only.json")
    silent = Transcript(video=video_from_info(info, select_track(info)), segments=[])
    assert run(["ingest", URL], tmp_path, FakeYouTube(silent)) == 1
    assert "no speech" in capsys.readouterr().err
    assert not (tmp_path / "library.sqlite3").exists()


def test_ingest_failure_creates_no_library(tmp_path):
    assert run(["ingest", URL], tmp_path, FakeYouTube(BLOCKED)) == 1
    assert not (tmp_path / "library.sqlite3").exists()


def test_ingest_storage_failure_on_first_ingest_removes_the_new_file(tmp_path, monkeypatch):
    def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr(Library, "_insert_passage", broken)
    assert run(["ingest", URL], tmp_path, FakeYouTube(two_hour_transcript())) == 1
    assert not list(tmp_path.glob("library.sqlite3*"))


def test_ingest_first_ingest_failure_keeps_unrelated_sibling_files(tmp_path, monkeypatch):
    backup = tmp_path / "library.sqlite3.bak"  # e.g. an old library moved aside
    backup.write_bytes(b"user backup")

    def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr(Library, "_insert_passage", broken)
    assert run(["ingest", URL], tmp_path, FakeYouTube(two_hour_transcript())) == 1
    assert not (tmp_path / "library.sqlite3").exists()
    assert backup.read_bytes() == b"user backup"


@pytest.mark.parametrize(
    "error", [OSError("disk full"), KeyboardInterrupt()], ids=["disk", "ctrl-c"]
)
def test_ingest_storage_failure_on_reingest_keeps_the_library(
    filled, tmp_path, monkeypatch, capsys, error
):
    path, before = filled
    capsys.readouterr()

    def broken(*args):
        raise error

    monkeypatch.setattr(Library, "_insert_passage", broken)
    again = two_hour_transcript("info_manual_and_auto.json")
    assert run(["ingest", "https://youtu.be/abc123DEF45"], tmp_path, FakeYouTube(again)) == 1
    assert digest(path) == before
    if isinstance(error, KeyboardInterrupt):
        assert "interrupted" in capsys.readouterr().err


def test_ingest_database_error_is_a_clean_failure(filled, tmp_path, monkeypatch, capsys):
    path, before = filled
    capsys.readouterr()

    def locked(*args):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(Library, "store", locked)
    assert run(["ingest", URL], tmp_path, FakeYouTube(two_hour_transcript())) == 1
    err = capsys.readouterr().err
    assert "database is locked" in err and "Traceback" not in err
    assert digest(path) == before


def test_ingest_model_mismatch_refused_before_any_request(filled, tmp_path, capsys):
    path, before = filled

    class OtherEmbedder(FakeEmbedder):
        model_name = "other/model-y"

    youtube = FakeYouTube(two_hour_transcript())
    assert run(["ingest", URL], tmp_path, youtube, embedder=OtherEmbedder()) == 1
    err = capsys.readouterr().err
    assert FakeEmbedder.model_name in err and "other/model-y" in err
    assert youtube.networks == []
    assert digest(path) == before


# --- Usage errors: no network request ----------------------------------------------------


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["ingest", "https://www.youtube.com/@hubermanlab"], "channel ingest is not available yet"),
        (["ingest", "https://example.com/video"], "not a YouTube video URL"),
        (["ingest", URL, *BOTH_COOKIE_OPTIONS], "not allowed"),
        (["ingest", URL, "--proxy", "http://proxy.example:8080"], "unrecognized arguments"),
    ],
    ids=["channel-url", "not-youtube", "conflicting-cookies", "proxy-option"],
)
def test_ingest_usage_error_makes_no_request(tmp_path, capsys, args, expected):
    youtube = FakeYouTube(two_hour_transcript())
    code = run(args, tmp_path, youtube)
    assert code == 2
    assert expected in capsys.readouterr().err
    assert youtube.networks == []
    assert not (tmp_path / "library.sqlite3").exists()


def test_ingest_invalid_proxy_is_a_usage_error_before_any_request(tmp_path, capsys):
    youtube = FakeYouTube(two_hour_transcript())
    environ = {"VIDEO_TO_RAG_PROXY": "alice:s3cret@proxy.example:8080"}
    assert run(["ingest", URL], tmp_path, youtube, environ=environ) == 2
    err = capsys.readouterr().err
    assert "VIDEO_TO_RAG_PROXY" in err and "scheme://host:port" in err
    assert "s3cret" not in err
    assert youtube.networks == []
    assert not (tmp_path / "library.sqlite3").exists()


# --- Network options reach the adapter; credentials stay out of the library -------------


def test_ingest_passes_network_options(tmp_path):
    youtube = FakeYouTube(two_hour_transcript())
    environ = {"VIDEO_TO_RAG_PROXY": "http://proxy.example:8080"}
    args = ["ingest", URL, "--cookies-from-browser", "firefox"]
    assert run(args, tmp_path, youtube, environ=environ) == 0
    [network] = youtube.networks
    assert network.cookies_from_browser == ("firefox", None)
    assert network.proxy == "http://proxy.example:8080"


def test_ingest_no_cookies_in_the_library(tmp_path):
    info = load_fixture("info_manual_and_auto.json")
    cookie = "SID=s3cr3tSidValue; HSID=AbCdEfHsidValue"
    # yt-dlp puts the session's cookies into the info dict it returns.
    info["formats"] = [{"format_id": "251", "url": "https://rr1.example/v", "cookies": cookie}]
    info["http_headers"] = {"Cookie": cookie}
    factory = FakeYDLFactory(info=info)

    def youtube(network):
        return YouTube(network, ydl_factory=factory, which=which_all)

    args = ["ingest", URL, "--cookies-from-browser", "firefox"]
    assert run(args, tmp_path, youtube) == 0
    assert factory.params["cookiesfrombrowser"] == ("firefox", None, None, None)
    stored = b"".join(p.read_bytes() for p in tmp_path.glob("library.sqlite3*"))
    for secret in (b"s3cr3tSidValue", b"AbCdEfHsidValue", b"HSID", b"SID="):
        assert secret not in stored


def test_ingest_never_shows_cookies_or_proxy_credentials(tmp_path, capsys, caplog, monkeypatch):
    monkeypatch.setattr("video_to_rag.cli._configure_logging", lambda: None)  # keep DEBUG
    info = load_fixture("info_manual_and_auto.json")
    info["http_headers"] = {"Cookie": "SID=s3cr3tSidValue"}
    factory = FakeYDLFactory(info=info)

    class ChattyFactory:
        """yt-dlp warns with the proxy URL in its message, as it does on retries."""

        def __call__(self, params):
            params["logger"].warning("retrying through http://alice:s3cret@proxy.example:8080")
            params["logger"].error("giving up on http://alice:s3cret@proxy.example:8080")
            return factory(params)

    def youtube(network):
        return YouTube(network, ydl_factory=ChattyFactory(), which=which_all)

    environ = {"VIDEO_TO_RAG_PROXY": "http://alice:s3cret@proxy.example:8080"}
    with caplog.at_level(logging.DEBUG, logger="video_to_rag"):
        code = run(["ingest", URL, "--cookies", COOKIES], tmp_path, youtube, environ=environ)
    assert code == 0
    shown = capsys.readouterr()
    everything = shown.out + shown.err + caplog.text
    assert "retrying through" in everything  # the warning itself is shown, masked
    for secret in ("s3cr3tSidValue", "FAKE_SID_VALUE", "alice", "s3cret"):
        assert secret not in everything
    for option in ("cookiefile", "noplaylist"):  # the options dict is never logged
        assert option not in everything


# --- Library location through the command ------------------------------------------------


def test_ingest_default_location(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    code = main(
        ["ingest", URL],
        environ={},
        youtube=FakeYouTube(two_hour_transcript()),
        embedder=FakeEmbedder(),
    )
    assert code == 0
    assert (tmp_path / ".local" / "share" / "video-to-rag" / "library.sqlite3").is_file()


def test_ingest_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    env_dir = tmp_path / "srv" / "vtr"
    code = main(
        ["ingest", URL],
        environ={HOME_ENV: str(env_dir)},
        youtube=FakeYouTube(two_hour_transcript()),
        embedder=FakeEmbedder(),
    )
    assert code == 0
    assert (env_dir / "library.sqlite3").is_file()
    assert not (tmp_path / "home").exists()


def test_ingest_option_beats_environment(tmp_path):
    env_dir = tmp_path / "srv" / "vtr"
    lib_dir = tmp_path / "lib"
    code = main(
        ["ingest", URL, "--data-dir", str(lib_dir)],
        environ={HOME_ENV: str(env_dir)},
        youtube=FakeYouTube(two_hour_transcript()),
        embedder=FakeEmbedder(),
    )
    assert code == 0
    assert (lib_dir / "library.sqlite3").is_file()
    assert not env_dir.exists()
