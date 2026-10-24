"""YouTube URL -> video id. Channel and playlist URLs are rejected for now (pure)."""

import re
from urllib.parse import parse_qs, urlsplit

VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")  # used with fullmatch: `$` accepts a final "\n"
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
PATH_FORMS = ("shorts", "live")
CHANNEL_FORMS = ("channel", "c", "user", "playlist")


class InvalidUrl(ValueError):
    """Not a YouTube video URL (a usage error)."""


class UnsupportedUrl(ValueError):
    """A YouTube URL this version does not ingest (channel or playlist)."""


def video_id(url: str) -> str:
    """The 11-character video id of a single-video YouTube URL; extra parameters are ignored."""
    text = url.strip()
    if "://" not in text:
        text = f"https://{text}"
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]

    if host in SHORT_HOSTS:
        candidate = segments[0] if segments else ""
    elif host in YOUTUBE_HOSTS:
        query = parse_qs(parts.query)
        if segments == ["watch"] and "v" in query:
            candidate = query["v"][0]
        elif len(segments) >= 2 and segments[0] in PATH_FORMS:
            candidate = segments[1]
        elif (segments and (segments[0].startswith("@") or segments[0] in CHANNEL_FORMS)) or (
            "list" in query
        ):
            raise UnsupportedUrl(
                f"{url.strip()} is a channel or playlist URL; channel ingest is not available yet "
                "— pass the URL of a single video"
            )
        else:
            candidate = ""
    else:
        candidate = ""

    if not VIDEO_ID_RE.fullmatch(candidate):
        raise InvalidUrl(f"not a YouTube video URL: {url.strip()!r}")
    return candidate
