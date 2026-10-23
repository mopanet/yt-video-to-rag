import argparse
import logging

import pytest
from helpers import FakeYDLFactory as Factory
from helpers import load_fixture, which_all
from yt_dlp.utils import DownloadError

from video_to_rag.captions import NoCaptions
from video_to_rag.youtube import (
    Blocked,
    Network,
    Unavailable,
    YouTube,
    YouTubeError,
    add_network_arguments,
    network_from,
)

VIDEO = "abc123DEF45"
BOT_CHECK = (
    f"ERROR: [youtube] {VIDEO}: Sign in to confirm you’re not a bot. Use --cookies-from-browser"
    " or --cookies for the authentication. See  https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i"
    "-pass-cookies-to-yt-dlp  for how to manually pass cookies."
)


def fetch(network=None, which=which_all, **factory_kwargs):
    factory = Factory(**factory_kwargs)
    transcript = YouTube(network or Network(), ydl_factory=factory, which=which).fetch(VIDEO)
    return factory, transcript


def parse(argv, environ=None):
    parser = argparse.ArgumentParser()
    add_network_arguments(parser)
    return network_from(parser.parse_args(argv), environ or {})


# --- Network access modes ----------------------------------------------------------------


def test_mode_direct_by_default():
    factory, transcript = fetch(parse([]))
    params = factory.params
    assert params["skip_download"] is True
    assert params["noplaylist"] is True
    assert not {"cookiefile", "cookiesfrombrowser", "proxy"} & params.keys()
    assert factory.instances[0].extracted == [(f"https://www.youtube.com/watch?v={VIDEO}", False)]
    assert transcript.video.id == VIDEO
    assert transcript.segments


def test_mode_browser_cookies():
    factory, _ = fetch(parse(["--cookies-from-browser", "firefox"]))
    assert factory.params["cookiesfrombrowser"] == ("firefox", None, None, None)


def test_mode_browser_cookies_with_profile():
    factory, _ = fetch(parse(["--cookies-from-browser", "Chrome:Profile 1"]))
    assert factory.params["cookiesfrombrowser"] == ("chrome", "Profile 1", None, None)


def test_mode_cookie_file(tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    factory, _ = fetch(parse(["--cookies", str(cookies)]))
    assert factory.params["cookiefile"] == str(cookies)


def test_mode_proxy_from_environment_covers_every_request():
    network = parse([], {"VIDEO_TO_RAG_PROXY": "http://proxy.example:8080"})
    factory, _ = fetch(network)
    assert len(factory.instances) == 1  # metadata and captions share one configured session
    ydl = factory.instances[0]
    assert ydl.params["proxy"] == "http://proxy.example:8080"
    assert ydl.extracted and ydl.opened


def test_mode_blank_proxy_variable_means_direct():
    assert parse([], {"VIDEO_TO_RAG_PROXY": "  "}).proxy is None


def test_mode_proxy_is_not_a_command_line_argument(capsys):
    with pytest.raises(SystemExit) as exc:
        parse(["--proxy", "http://proxy.example:8080"])
    assert exc.value.code == 2


def test_mode_conflicting_cookie_options(tmp_path, capsys):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    with pytest.raises(SystemExit) as exc:
        parse(["--cookies-from-browser", "firefox", "--cookies", str(cookies)])
    assert exc.value.code == 2
    assert "not allowed with" in capsys.readouterr().err


def test_mode_unsupported_browser(capsys):
    with pytest.raises(SystemExit) as exc:
        parse(["--cookies-from-browser", "netscape-navigator"])
    assert exc.value.code == 2
    assert "firefox" in capsys.readouterr().err


def test_mode_missing_cookie_file(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        parse(["--cookies", str(tmp_path / "nope.txt")])
    assert exc.value.code == 2


def test_mode_options_never_logged(caplog):
    network = parse([], {"VIDEO_TO_RAG_PROXY": "http://alice:s3cret@proxy.example:8080"})
    with caplog.at_level(logging.DEBUG):
        fetch(network)
    assert "s3cret" not in caplog.text


# --- Errors ------------------------------------------------------------------------------


def test_error_blocked_on_direct_connection():
    with pytest.raises(Blocked) as exc:
        fetch(error=DownloadError(BOT_CHECK))
    message = str(exc.value)
    assert "blocked" in message
    assert "cloud" in message and "VPN" in message
    for remedy in ("--cookies-from-browser", "--cookies", "VIDEO_TO_RAG_PROXY"):
        assert remedy in message
    assert "expired" not in message


def test_error_blocked_straight_apostrophe():
    with pytest.raises(Blocked):
        fetch(error=DownloadError(BOT_CHECK.replace("’", "'")))


def test_error_blocked_although_cookies_were_sent(tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    with pytest.raises(Blocked) as exc:
        fetch(parse(["--cookies", str(cookies)]), error=DownloadError(BOT_CHECK))
    message = str(exc.value)
    assert "expired" in message
    assert "fresh cookies" in message
    assert "VIDEO_TO_RAG_PROXY" in message


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("Private video. Sign in if you've been granted access to this video", "Private video"),
        ("Video unavailable. This video has been removed by the uploader", "removed"),
        (
            "Join this channel to get access to members-only content like this video",
            "members-only",
        ),
    ],
)
def test_error_unavailable_video_keeps_youtube_reason(reason, expected):
    with pytest.raises(Unavailable) as exc:
        fetch(error=DownloadError(f"ERROR: [youtube] {VIDEO}: {reason}"))
    message = str(exc.value)
    assert "unavailable" in message
    assert expected in message
    assert "ERROR:" not in message


def test_error_proxy_failure_message_is_masked():
    proxy = "http://alice:s3cret@proxy.example:8080"
    network = parse([], {"VIDEO_TO_RAG_PROXY": proxy})
    error = DownloadError(
        f"ERROR: [youtube] {VIDEO}: Unable to download API page: ('Unable to connect to proxy', "
        f"ConnectionRefusedError(111, 'Connection refused')) (caused by ProxyError({proxy!r}))"
    )
    with pytest.raises(YouTubeError) as exc:
        fetch(network, error=error)
    message = str(exc.value)
    assert "http://***@proxy.example:8080" in message
    assert "alice" not in message and "s3cret" not in message


def test_error_unknown_is_generic_and_masked():
    error = DownloadError("ERROR: something odd at socks5://bob:hunter2@10.0.0.1:1080")
    with pytest.raises(YouTubeError) as exc:
        fetch(error=error)
    assert type(exc.value) is YouTubeError
    assert "hunter2" not in str(exc.value)


def test_error_no_captions_propagates():
    with pytest.raises(NoCaptions):
        fetch(info=load_fixture("info_no_captions.json"))


def test_error_ytdlp_warnings_are_masked(caplog):
    proxy = "http://alice:s3cret@proxy.example:8080"

    class WarningFactory(Factory):
        def __call__(self, params):
            params["logger"].warning(f"retrying through {proxy}")
            return super().__call__(params)

    factory = WarningFactory()
    with caplog.at_level(logging.WARNING):
        YouTube(Network(proxy=proxy), ydl_factory=factory, which=which_all).fetch(VIDEO)
    assert "http://***@proxy.example:8080" in caplog.text
    assert "s3cret" not in caplog.text


# --- JavaScript runtime ------------------------------------------------------------------


def test_runtime_deno_preferred():
    factory, _ = fetch(which=which_all)
    assert factory.params["js_runtimes"] == {"deno": {"path": "/usr/bin/deno"}}


def test_runtime_node_fallback():
    factory, _ = fetch(which=lambda name: "/usr/local/bin/node" if name == "node" else None)
    assert factory.params["js_runtimes"] == {"node": {"path": "/usr/local/bin/node"}}


def test_runtime_missing_warns_and_still_attempts(caplog):
    with caplog.at_level(logging.WARNING):
        factory, transcript = fetch(which=lambda name: None)
    assert "deno" in caplog.text and "node" in caplog.text
    assert "js_runtimes" not in factory.params
    assert factory.instances[0].extracted
    assert transcript.segments
