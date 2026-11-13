import pytest
from helpers import load_fixture

from video_to_rag.captions import (
    CaptionTrack,
    NoCaptions,
    Segment,
    Video,
    parse_json3,
    select_track,
    video_from_info,
)


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


def test_select_never_a_translation_when_metadata_names_another_language():
    # The metadata says English, but the speech recognition ran on Hungarian: the "en"
    # automatic track is a machine translation of it (tlang=en) and must not be used.
    base = "https://www.youtube.com/api/timedtext?v=magyarVid01&kind=asr&lang=hu"
    info = {
        "id": "magyarVid01",
        "language": "en",
        "subtitles": {},
        "automatic_captions": {
            "hu-orig": [{"ext": "json3", "url": f"{base}&fmt=json3"}],
            "hu": [{"ext": "json3", "url": f"{base}&fmt=json3"}],
            "en": [{"ext": "json3", "url": f"{base}&tlang=en&fmt=json3"}],
        },
    }
    with pytest.raises(NoCaptions):
        select_track(info)


def test_select_without_orig_key_still_refuses_a_translated_url():
    info = load_fixture("info_auto_only.json")
    del info["automatic_captions"]["en-orig"]
    for fmt in info["automatic_captions"]["en"]:
        fmt["url"] += "&tlang=en"
    with pytest.raises(NoCaptions):
        select_track(info)


@pytest.mark.parametrize("language", [None, "pt", "pt-BR"])
def test_select_regional_speech_recognition_track(language):
    base = "https://www.youtube.com/api/timedtext?v=brasil00001&kind=asr&lang=pt-BR"
    info = {
        "id": "brasil00001",
        "language": language,
        "subtitles": {},
        "automatic_captions": {
            "pt-BR-orig": [{"ext": "json3", "url": f"{base}&fmt=json3"}],
            "pt-BR": [{"ext": "json3", "url": f"{base}&fmt=json3"}],
            "en": [{"ext": "json3", "url": f"{base}&tlang=en&fmt=json3"}],
        },
    }
    assert select_track(info) == CaptionTrack(language="pt", kind="auto", url=f"{base}&fmt=json3")


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


def test_parse_drops_unpaired_surrogates():
    # JSON can carry "\ud800"; such text breaks the tokenizer, SQLite and printing alike.
    event = {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "hello \ud800world"}]}
    assert parse_json3({"events": [event]}) == [Segment(start=0.0, end=1.0, text="hello world")]


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


# --- Video metadata ----------------------------------------------------------------------


def test_metadata_from_info():
    info = load_fixture("info_auto_only.json")
    assert video_from_info(info, select_track(info)) == Video(
        id="auto0nly_EN",
        title="Using Cold Exposure for Health",
        channel_id="UC2D2CMWXMOVWx7giW1n3LIg",
        channel_name="Huberman Lab",
        published="2023-10-02",
        duration_s=9011,
        language="en",
        caption_kind="auto",
    )


def test_metadata_falls_back_to_uploader_and_timestamp():
    info = load_fixture("info_manual_and_auto.json")
    for key in ("channel", "channel_id", "upload_date"):
        del info[key]
    info.update(uploader_id="@hubermanlab", timestamp=1710115200)  # 2024-03-11 00:00 UTC
    video = video_from_info(info, select_track(info))
    assert (video.channel_name, video.channel_id) == ("Andrew Huberman", "@hubermanlab")
    assert video.published == "2024-03-11"
