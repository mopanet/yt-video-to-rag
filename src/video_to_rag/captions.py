"""Caption track selection, video metadata and json3 -> timestamped segments (pure)."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

ANNOTATION_RE = re.compile(r"\[[^\]]*\]")
WHITESPACE_RE = re.compile(r"\s+")
ORIG_SUFFIX = "-orig"


@dataclass(frozen=True)
class CaptionTrack:
    language: str  # base code of the spoken language, e.g. "en"
    kind: str  # "manual" | "auto"
    url: str  # json3 download URL


@dataclass(frozen=True)
class Segment:
    start: float  # seconds
    end: float
    text: str


@dataclass(frozen=True)
class Video:
    id: str
    title: str
    channel_id: str
    channel_name: str
    published: str | None  # YYYY-MM-DD
    duration_s: float | None
    language: str
    caption_kind: str


@dataclass(frozen=True)
class Transcript:
    video: Video
    segments: list[Segment]


class NoCaptions(Exception):
    """The video has no caption track in its spoken language."""


def _published(info: dict) -> str | None:
    if (date := info.get("upload_date")) and len(date) == 8:
        return f"{date[:4]}-{date[4:6]}-{date[6:]}"
    if (ts := info.get("timestamp")) is not None:
        return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")
    return None


def video_from_info(info: dict, track: CaptionTrack) -> Video:
    return Video(
        id=info["id"],
        title=info.get("title") or info["id"],
        channel_id=info.get("channel_id") or info.get("uploader_id") or "",
        channel_name=info.get("channel") or info.get("uploader") or "",
        published=_published(info),
        duration_s=info.get("duration"),
        language=track.language,
        caption_kind=track.kind,
    )


def base_language(code: str | None) -> str | None:
    if not code:
        return None
    return re.split(r"[-_]", code, maxsplit=1)[0].lower() or None


def spoken_language(info: dict) -> str | None:
    """The metadata's language, else the language of the speech-recognition source track."""
    if lang := base_language(info.get("language")):
        return lang
    for key in info.get("automatic_captions") or {}:
        if key.endswith(ORIG_SUFFIX):
            return base_language(key.removesuffix(ORIG_SUFFIX))
    return None


def _json3_url(formats: list[dict] | None) -> str | None:
    """The track's json3 URL, unless it is a machine translation (`tlang=`)."""
    url = next((f["url"] for f in formats or [] if f.get("ext") == "json3" and f.get("url")), None)
    return None if url is None or "tlang" in parse_qs(urlsplit(url).query) else url


def select_track(info: dict) -> CaptionTrack:
    """Uploader-provided track in the spoken language, else its speech-recognition track.

    Every other automatic track is a machine translation and is never used.
    """
    lang = spoken_language(info)
    if lang:
        manual = info.get("subtitles") or {}
        keys = sorted(k for k in manual if k != "live_chat" and base_language(k) == lang)
        keys.sort(key=lambda k: k != lang)  # an exact code beats a regional variant
        for key in keys:
            if url := _json3_url(manual[key]):
                return CaptionTrack(language=lang, kind="manual", url=url)
        auto = info.get("automatic_captions") or {}
        # With an `-orig` (speech-recognition source) key present, every other key is a
        # translation of it, even one named after the metadata's language.
        origs = [key for key in auto if key.endswith(ORIG_SUFFIX)]
        if origs:  # e.g. "en-orig", or a regional "pt-BR-orig"
            keys = sorted(k for k in origs if base_language(k.removesuffix(ORIG_SUFFIX)) == lang)
        else:
            keys = [lang]
        for key in keys:
            if url := _json3_url(auto.get(key)):
                return CaptionTrack(language=lang, kind="auto", url=url)
    raise NoCaptions(
        f"the video has no captions in its spoken language ({lang or 'unknown'}); "
        "speech-to-text is not available yet"
    )


def _clean(text: str) -> str:
    return WHITESPACE_RE.sub(" ", ANNOTATION_RE.sub(" ", text)).strip()


def parse_json3(data: dict) -> list[Segment]:
    """json3 events -> segments; annotations stripped, empty ones dropped.

    End = min(start + duration, next start), because speech-recognition events overlap in time.
    """
    raw: list[tuple[float, float | None, str]] = []
    for event in data.get("events", []):
        if "segs" not in event or event.get("aAppend"):
            continue
        text = _clean("".join(seg.get("utf8", "") for seg in event["segs"]))
        if not text:
            continue
        start = event["tStartMs"] / 1000
        duration = event.get("dDurationMs")
        raw.append((start, start + duration / 1000 if duration is not None else None, text))

    segments = []
    for i, (start, end, text) in enumerate(raw):
        next_start = raw[i + 1][0] if i + 1 < len(raw) else None
        if end is None:
            end = next_start if next_start is not None else start
        elif next_start is not None:
            end = min(end, next_start)
        segments.append(Segment(start=start, end=end, text=text))
    return segments
