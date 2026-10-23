import pytest
from helpers import FakeEmbedder

from video_to_rag.captions import Video
from video_to_rag.chunking import Passage
from video_to_rag.library import Library
from video_to_rag.search import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    InvalidQuery,
    format_time,
    fts_query,
    render_text,
    rrf,
    search,
)

EMBEDDER = FakeEmbedder()
HUBERMAN = ("UC2D2CMWXMOVWx7giW1n3LIg", "Huberman Lab")
OTHER = ("UCother00000000000000000", "Other Channel")


def video(video_id, channel=HUBERMAN, title=None, language="en"):
    return Video(
        id=video_id,
        title=title or f"Episode {video_id}",
        channel_id=channel[0],
        channel_name=channel[1],
        published="2024-03-11",
        duration_s=7200,
        language=language,
        caption_kind="auto",
    )


def add(library, v, texts, start=0.0):
    passages = [
        Passage(seq=i, start=start + i * 50.0, end=start + i * 50.0 + 60, text=t)
        for i, t in enumerate(texts)
    ]
    library.store(v, passages, EMBEDDER.embed_passages(texts))


@pytest.fixture
def library(tmp_path):
    lib = Library.open_for_write(tmp_path / "library.sqlite3", EMBEDDER.model_name, EMBEDDER.dim)
    yield lib
    lib.close()


TOPICS = [
    "to improve focus at work, limit your visual field and work in ninety minute blocks",
    "caffeine delays the afternoon crash when you wait ninety minutes after waking",
    "deliberate cold exposure raises dopamine for hours",
    "morning sunlight sets the circadian clock and helps you fall asleep at night",
    "zone two cardio exercise improves mitochondrial health",
]


# --- Several phrasings / exact terms / channel filter / limit ----------------------------


def test_several_phrasings_fused_into_one_list_without_duplicates(library):
    add(library, video("vid00000001"), TOPICS)
    result = search(library, EMBEDDER, ["hogyan javítsam a fókuszomat", "how to improve focus"])
    ids = [h.passage_id for h in result.hits]
    assert ids and len(ids) == len(set(ids))
    assert result.hits[0].text == TOPICS[0]


@pytest.mark.parametrize(
    "queries",
    [[], ["a", "b", "c", "d", "e", "f"], ["focus", "   "], [""]],
    ids=["none", "six", "whitespace", "empty"],
)
def test_too_many_or_blank_queries_rejected(library, queries):
    with pytest.raises(InvalidQuery, match="one to five non-blank"):
        search(library, EMBEDDER, queries)


def test_exact_term_matching_rare_term(library):
    filler = [f"protocol number {i} for better sleep and recovery" for i in range(40)]
    add(library, video("vid00000001"), filler)
    add(library, video("vid00000002"), [*TOPICS, "the NSDR session lasts twenty minutes"])
    result = search(library, EMBEDDER, ["NSDR protocol"])
    assert "NSDR" in " ".join(h.text for h in result.hits[:3])


def test_channel_filter_by_name(library):
    add(library, video("vid00000001", HUBERMAN), TOPICS)
    add(library, video("vid00000002", OTHER), TOPICS)
    result = search(library, EMBEDDER, ["focus"], channel="huberman lab")
    assert result.hits
    assert {h.channel for h in result.hits} == {"Huberman Lab"}


def test_channel_filter_by_id(library):
    add(library, video("vid00000001", HUBERMAN), TOPICS)
    add(library, video("vid00000002", OTHER), TOPICS)
    result = search(library, EMBEDDER, ["focus"], channel=OTHER[0])
    assert {h.channel for h in result.hits} == {"Other Channel"}


def test_channel_filter_unknown(library):
    add(library, video("vid00000001"), TOPICS)
    result = search(library, EMBEDDER, ["focus"], channel="Nobody")
    assert result.hits == []
    assert "no ingested channel matches" in result.message.lower()
    assert "Nobody" in result.message


def test_result_limit_default_and_cap(library):
    for v in range(10):
        add(library, video(f"vid{v:08d}"), [f"focus tip {v}-{i}" for i in range(100)])
    assert len(search(library, EMBEDDER, ["focus"]).hits) == DEFAULT_LIMIT == 8
    assert len(search(library, EMBEDDER, ["focus"], limit=50).hits) == MAX_LIMIT == 20
    assert len(search(library, EMBEDDER, ["focus"], limit=3).hits) == 3


@pytest.mark.parametrize("limit", [0, -1])
def test_result_limit_below_one_rejected(library, limit):
    with pytest.raises(InvalidQuery, match="limit"):
        search(library, EMBEDDER, ["focus"], limit=limit)


def test_fts_query_never_passes_user_syntax_through():
    assert fts_query('focus AND "sleep" NEAR(x*') == '"focus" OR "AND" OR "sleep" OR "NEAR" OR "x"'
    assert fts_query("?! --") is None


@pytest.mark.parametrize("text", ['"', "NEAR(", "a:b", "*", "AND OR NOT", "fókusz^2"])
def test_search_with_fts_syntax_does_not_fail(library, text):
    add(library, video("vid00000001"), TOPICS)
    search(library, EMBEDDER, [text])


def test_exact_term_ignores_tokens_found_in_most_passages(library, monkeypatch):
    # "a" is a Hungarian article and an English word: across languages it is pure noise.
    common = ["a cold plunge", "a short walk", "a nap", "a long run", "a quiet room"]
    add(library, video("vid00000001"), [*TOPICS[:3], *common])
    matches = []
    original = Library.fts

    def spy(self, match, k, channel_ids=None):
        matches.append(match)
        return original(self, match, k, channel_ids)

    monkeypatch.setattr(Library, "fts", spy)
    search(library, EMBEDDER, ["a fókuszomat", "a"])
    assert matches == ['"fókuszomat"']  # "a" (in 5 of 8 passages) dropped; query 2 has no FTS


def test_rrf_fuses_and_deduplicates():
    assert rrf([[1, 2, 3], [3, 1]]) == [1, 3, 2]


# --- Search hit content ------------------------------------------------------------------


def test_hit_timestamped_link_and_time_range(library):
    passage = Passage(seq=0, start=1834.6, end=1912.0, text="focus needs visual attention")
    library.store(video("abc123DEF45"), [passage], EMBEDDER.embed_passages([passage.text]))
    [hit] = search(library, EMBEDDER, ["focus"]).hits
    assert hit.link == "https://youtu.be/abc123DEF45?t=1834"
    assert (hit.start, hit.end) == ("30:34", "31:52")
    assert hit.time_range == "30:34–31:52"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0:00"),
        (59.9, "0:59"),
        (61, "1:01"),
        (3599, "59:59"),
        (3600, "1:00:00"),
        (3725.4, "1:02:05"),
    ],
)
def test_hit_time_format(seconds, expected):
    assert format_time(seconds) == expected


def test_hit_original_text_kept(library):
    english = "To improve focus, look at a point on the wall for thirty to sixty seconds."
    add(library, video("vid00000001", title="Focus Toolkit"), [english])
    [hit] = search(library, EMBEDDER, ["Hogyan tudom javítani a fókuszomat?"]).hits
    assert hit.text == english
    assert hit.language == "en"
    assert (hit.title, hit.channel, hit.published) == (
        "Focus Toolkit",
        "Huberman Lab",
        "2024-03-11",
    )


def test_hit_text_rendering_carries_every_field(library):
    add(library, video("vid00000001", title="Focus Toolkit"), TOPICS[:2])
    text = render_text(search(library, EMBEDDER, ["focus"], limit=2))
    assert text.startswith("1. Focus Toolkit — Huberman Lab (2024-03-11)")
    assert "2. Focus Toolkit" in text
    for expected in ("0:00–1:00", "https://youtu.be/vid00000001?t=0", "[en]", TOPICS[0]):
        assert expected in text


# --- Empty library -----------------------------------------------------------------------


class Untouchable(FakeEmbedder):
    def embed_queries(self, texts):
        raise AssertionError("an empty library must not load the model")


def test_empty_library_missing(tmp_path):
    result = search(None, Untouchable(), ["focus"])
    assert result.hits == []
    assert "library is empty" in result.message
    assert "video-to-rag ingest <video-url>" in result.message


def test_empty_library_without_videos(library):
    result = search(library, Untouchable(), ["focus"])
    assert result.hits == [] and "library is empty" in result.message
