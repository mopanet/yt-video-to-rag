import pytest
from helpers import load_fixture

from video_to_rag.captions import CaptionTrack, NoCaptions, Segment, parse_json3, select_track


def json3_url(info, container, key):
    return next(f["url"] for f in info[container][key] if f["ext"] == "json3")


# --- Caption track selection -------------------------------------------------------------


def test_select_manual_track_preferred():
    info = load_fixture("info_manual_and_auto.json")
    assert select_track(info) == CaptionTrack(
        language="en", kind="manual", url=json3_url(info, "subtitles", "en")
    )


def test_select_automatic_track_as_fallback_never_a_translation():
    info = load_fixture("info_auto_only.json")
    track = select_track(info)
    assert track == CaptionTrack(
        language="en", kind="auto", url=json3_url(info, "automatic_captions", "en-orig")
    )
    assert "tlang=" not in track.url


def test_select_automatic_track_without_orig_key():
    info = load_fixture("info_auto_only.json")
    del info["automatic_captions"]["en-orig"]
    track = select_track(info)
    assert track == CaptionTrack(
        language="en", kind="auto", url=json3_url(info, "automatic_captions", "en")
    )


def test_select_spoken_language_missing_from_metadata():
    info = load_fixture("info_no_language.json")
    assert select_track(info) == CaptionTrack(
        language="de", kind="auto", url=json3_url(info, "automatic_captions", "de-orig")
    )


def test_select_manual_track_matches_regional_variant():
    info = load_fixture("info_manual_and_auto.json")
    info["subtitles"]["en-GB"] = info["subtitles"].pop("en")
    track = select_track(info)
    assert (track.language, track.kind) == ("en", "manual")


def test_select_ignores_live_chat():
    info = load_fixture("info_auto_only.json")
    info["subtitles"] = load_fixture("info_manual_and_auto.json")["subtitles"]
    del info["subtitles"]["en"]
    assert select_track(info).kind == "auto"


def test_select_no_track_in_spoken_language():
    info = load_fixture("info_no_captions.json")
    with pytest.raises(NoCaptions, match="no captions") as exc:
        select_track(info)
    assert "speech-to-text is not available yet" in str(exc.value)


def test_select_no_language_and_no_recognition_track():
    info = load_fixture("info_no_captions.json")
    info["language"] = None
    with pytest.raises(NoCaptions):
        select_track(info)


def test_select_track_without_json3_format_is_unusable():
    info = load_fixture("info_auto_only.json")
    for key in ("en-orig", "en"):
        for fmt in info["automatic_captions"][key]:
            fmt["ext"] = "vtt"
    with pytest.raises(NoCaptions):
        select_track(info)


# --- Timestamped transcript segments -----------------------------------------------------


def test_parse_annotations_removed_and_empty_segments_dropped():
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 3000, "segs": [{"utf8": "[Music]"}]},
            {
                "tStartMs": 3000,
                "dDurationMs": 2500,
                "segs": [{"utf8": "[Applause] so let's begin"}],
            },
        ]
    }
    assert parse_json3(data) == [Segment(start=3.0, end=5.5, text="so let's begin")]


def test_parse_asr_events_end_clamped_to_next_start():
    segments = parse_json3(load_fixture("captions_asr.json3"))
    assert [s.text for s in segments] == [
        "so let's begin",
        "welcome to the Huberman Lab podcast",
        "where we discuss science",
        "and science-based tools",
        "for everyday life",
    ]
    assert [(s.start, s.end) for s in segments] == pytest.approx(
        [(4.0, 6.16), (6.16, 8.88), (8.88, 13.28), (13.28, 16.88), (17.0, 20.1)]
    )


def test_parse_manual_captions_join_lines():
    segments = parse_json3(load_fixture("captions_manual.json3"))
    assert segments[1] == Segment(
        start=4.5, end=8.6, text="where we discuss science and science-based tools"
    )
    assert len(segments) == 4


def test_parse_event_without_duration_ends_at_next_start():
    data = {
        "events": [
            {"tStartMs": 1000, "segs": [{"utf8": "one"}]},
            {"tStartMs": 2500, "dDurationMs": 500, "segs": [{"utf8": "two"}]},
        ]
    }
    assert parse_json3(data) == [Segment(1.0, 2.5, "one"), Segment(2.5, 3.0, "two")]
