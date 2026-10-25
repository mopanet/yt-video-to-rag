"""yt-dlp adapter: metadata + caption download, network options, error mapping.

One `YoutubeDL` session per fetch carries the cookies and the proxy for every request (metadata
and caption file alike). yt-dlp is driven through its Python API, so credentials never appear
on a command line, and its options dict is never logged.
"""

import argparse
import contextlib
import io
import json
import re
import shutil
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from yt_dlp.cookies import SUPPORTED_BROWSERS, YoutubeDLCookieJar
from yt_dlp.utils import YoutubeDLError

from .captions import Transcript, parse_json3, select_track, video_from_info
from .redact import logger, redact

PROXY_ENV = "VIDEO_TO_RAG_PROXY"
JS_RUNTIMES = ("deno", "node")  # in order of preference
UNAVAILABLE_MARKERS = (
    "private video",
    "video unavailable",
    "members-only",
    "members only",
    "removed",
)
PREFIX_RE = re.compile(r"^(?:ERROR:\s*)?(?:\[\w+\]\s*)?(?:[\w-]{11}:\s*)?")

BLOCKED_MESSAGE = (
    'YouTube blocked the request with its bot check ("Sign in to confirm you\'re not a bot"). '
    "This typically happens from cloud or VPN addresses. Remedies: --cookies-from-browser "
    "<browser>[:<profile>] (a browser profile logged in to YouTube; a separate Google account is "
    "recommended), --cookies <file> (a Netscape-format cookie file), or set VIDEO_TO_RAG_PROXY "
    "to a proxy URL."
)
EXPIRED_HINT = (
    " Cookies were sent, so they may be expired: export fresh cookies from a logged-in browser, "
    "or use VIDEO_TO_RAG_PROXY."
)


class YouTubeError(Exception):
    """A YouTube request failed; the message is already redacted."""


class Blocked(YouTubeError):
    """YouTube answered with its bot check."""


class Unavailable(YouTubeError):
    """The video is private, deleted, members-only or otherwise unavailable."""


@dataclass(frozen=True)
class Network:
    cookies_from_browser: tuple[str, str | None] | None = None  # (browser, profile)
    cookie_file: str | None = None
    proxy: str | None = None  # only ever from VIDEO_TO_RAG_PROXY

    @property
    def uses_cookies(self) -> bool:
        return bool(self.cookies_from_browser or self.cookie_file)


def _browser(value: str) -> tuple[str, str | None]:
    name, _, profile = value.partition(":")
    name = name.strip().lower()
    if name not in SUPPORTED_BROWSERS:
        raise argparse.ArgumentTypeError(
            f"unsupported browser {name!r}; supported: {', '.join(sorted(SUPPORTED_BROWSERS))}"
        )
    return name, profile.strip() or None


def _cookie_problem(text: str) -> str | None:
    """Why yt-dlp could not load this cookie file, or None. Never quotes the file.

    yt-dlp prints every line it skips, cookie value included, straight to stderr, and the
    standard library puts a rejected line into its error message; so the file is checked here,
    with yt-dlp's own loader and its output swallowed, before yt-dlp ever sees it.
    """
    bad = [
        n
        for n, line in enumerate(text.splitlines(), start=1)
        if (entry := line.removeprefix("#HttpOnly_")).strip()
        and not entry.startswith("#")
        and len(entry.split("\t")) != 7
    ]
    if bad:
        return f"line {', '.join(map(str, bad[:5]))} is not 7 tab-separated fields"
    swallowed = io.StringIO()
    try:
        with contextlib.redirect_stderr(swallowed), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            YoutubeDLCookieJar(io.StringIO(text)).load()
    except Exception:
        return "its entries are not valid cookie-file entries"
    if swallowed.getvalue():
        return "some of its entries are not valid cookie-file entries"
    return None


def _cookie_file(value: str) -> str:
    try:
        text = Path(value).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise argparse.ArgumentTypeError(f"cookie file not found: {value}") from None
    except (OSError, UnicodeDecodeError):
        raise argparse.ArgumentTypeError(f"cookie file not readable as text: {value}") from None
    if problem := _cookie_problem(text):
        raise argparse.ArgumentTypeError(
            f"{value} is not a Netscape-format cookie file: {problem} "
            "(its contents are never shown)"
        )
    return value


def add_network_arguments(parser: argparse.ArgumentParser) -> None:
    """The cookie options (mutually exclusive). The proxy is deliberately not an option."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER[:PROFILE]",
        type=_browser,
        help="send the YouTube cookies of that browser profile (e.g. firefox, chrome:Default)",
    )
    group.add_argument(
        "--cookies",
        metavar="FILE",
        type=_cookie_file,
        help="send the cookies from a Netscape-format cookie file",
    )


def network_from(args: argparse.Namespace, environ: Mapping[str, str]) -> Network:
    return Network(
        cookies_from_browser=args.cookies_from_browser,
        cookie_file=args.cookies,
        proxy=(environ.get(PROXY_ENV) or "").strip() or None,
    )


class _YtDlpLogger:
    """Routes yt-dlp's messages through our redacting logger; its errors come back as exceptions."""

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        logger.warning("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        logger.debug("yt-dlp: %s", msg)


def _default_factory() -> Callable[[dict], object]:
    from yt_dlp import YoutubeDL

    return YoutubeDL


class YouTube:
    def __init__(
        self,
        network: Network,
        *,
        ydl_factory: Callable[[dict], object] | None = None,
        which: Callable[[str], str | None] = shutil.which,
    ):
        self.network = network
        self._factory = ydl_factory
        self._which = which

    def _params(self) -> dict:
        params = {
            "quiet": True,
            "noprogress": True,
            "skip_download": True,
            "noplaylist": True,
            # A single-file format, so yt-dlp does not warn about ffmpeg for a merge that never
            # happens. Never set ignore_no_formats_error: it turns the bot check, "Private video"
            # and the other playability errors into warnings.
            "format": "bestaudio/best",
            "logger": _YtDlpLogger(),
        }
        runtime = next(((n, p) for n in JS_RUNTIMES if (p := self._which(n))), None)
        if runtime:
            params["js_runtimes"] = {runtime[0]: {"path": runtime[1]}}
        else:
            logger.warning(
                "warning: no JavaScript runtime found on PATH; YouTube access needs deno "
                "(preferred) or node. Trying anyway."
            )
        if self.network.cookies_from_browser:
            browser, profile = self.network.cookies_from_browser
            params["cookiesfrombrowser"] = (browser, profile, None, None)
        if self.network.cookie_file:
            # An in-memory copy: yt-dlp saves the jar back on close, which would rewrite the
            # user's credential file (and fail on a read-only one).
            params["cookiefile"] = io.StringIO(
                Path(self.network.cookie_file).read_text(encoding="utf-8")
            )
        if self.network.proxy:
            params["proxy"] = self.network.proxy
        return params

    def fetch(self, video_id: str) -> Transcript:
        """Metadata and the spoken-language captions of one video (raises NoCaptions)."""
        factory = self._factory or _default_factory()
        try:
            with factory(self._params()) as ydl:
                url = f"https://www.youtube.com/watch?v={video_id}"
                info = ydl.extract_info(url, download=False)
                track = select_track(info)
                with ydl.urlopen(track.url) as response:
                    data = json.loads(response.read())
        except YoutubeDLError as error:
            raise self._map_error(str(error)) from None
        except ValueError:
            raise YouTubeError("YouTube returned captions that could not be read") from None
        return Transcript(video=video_from_info(info, track), segments=parse_json3(data))

    def _map_error(self, text: str) -> YouTubeError:
        reason = redact(PREFIX_RE.sub("", text.strip()))
        lowered = reason.lower()
        if "confirm you" in lowered and "not a bot" in lowered:
            return Blocked(BLOCKED_MESSAGE + (EXPIRED_HINT if self.network.uses_cookies else ""))
        if any(marker in lowered for marker in UNAVAILABLE_MARKERS):
            return Unavailable(f"the video is unavailable: {reason}")
        via = f" (via proxy {redact(self.network.proxy)})" if self.network.proxy else ""
        return YouTubeError(f"YouTube request failed: {reason}{via}")
