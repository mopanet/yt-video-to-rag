import pytest

from video_to_rag.captions import Segment
from video_to_rag.chunking import MAX_TOKENS, Passage, chunk


def words(text: str) -> int:
    return len(text.split())


def transcript(n: int, seconds: float = 5.0, words_per_segment: int = 12) -> list[Segment]:
    return [
        Segment(
            start=i * seconds,
            end=(i + 1) * seconds,
            text=" ".join(f"s{i:03d}w{w:02d}" for w in range(words_per_segment)),
        )
        for i in range(n)
    ]


# --- Timestamped passages ----------------------------------------------------------------


def test_whole_transcript_covered_in_order():
    segments = transcript(200)
    passages = chunk(segments, words)
    assert len(passages) > 1
    assert [p.seq for p in passages] == list(range(len(passages)))
    assert [p.start for p in passages] == sorted(p.start for p in passages)
    joined = " ".join(p.text for p in passages)
    for segment in segments:
        assert segment.text in joined
    positions = [joined.index(s.text) for s in segments]
    assert positions == sorted(positions)


def test_passage_boundaries_are_segment_boundaries():
    segments = [
        Segment(600.0, 620.0, "one"),
        Segment(620.0, 640.0, "two"),
        Segment(640.0, 659.9, "three"),
        Segment(659.9, 671.4, "four"),
        Segment(671.4, 690.0, "five"),
    ]
    first = chunk(segments, words)[0]
    assert first == Passage(seq=0, start=600.0, end=671.4, text="one two three four")


def test_neighbouring_passages_overlap():
    segments = transcript(200)
    passages = chunk(segments, words)
    for before, after in zip(passages, passages[1:], strict=False):
        last = next(s for s in segments if s.end == before.end)
        first_of_after = next(s for s in segments if s.start == after.start)
        assert after.start <= last.start
        assert after.text.startswith(first_of_after.text)
        assert last.text in after.text
        assert before.end - after.start >= 10  # the overlap covers at least the last 10 s


def test_neighbouring_passages_overlap_after_long_segments():
    # Each segment alone spans more than MAX_SECONDS, so every passage closes after it; the
    # next passage must still start with it.
    segments = transcript(4, seconds=70.0, words_per_segment=3)
    passages = chunk(segments, words)
    assert len(passages) > 1
    for before, after in zip(passages, passages[1:], strict=False):
        last = next(s for s in segments if s.end == before.end)
        assert after.start == last.start and after.text.startswith(last.text)
    assert passages[-1].end == segments[-1].end


def test_no_overlap_only_where_two_segments_exceed_the_bound():
    segments = transcript(4, seconds=20.0, words_per_segment=250)  # 2 x 250 > 480
    passages = chunk(segments, words)
    assert [p.text for p in passages] == [s.text for s in segments]


def test_passage_closes_at_target_tokens_and_never_exceeds_the_bound():
    segments = transcript(40, seconds=1.0, words_per_segment=100)
    passages = chunk(segments, words)
    assert all(words(p.text) <= MAX_TOKENS for p in passages)
    assert words(passages[0].text) == 400  # 300 < 320 tokens, so a fourth segment still fits


def test_single_segment_transcript():
    segments = [Segment(1.0, 3.5, "hello there")]
    assert chunk(segments, words) == [Passage(seq=0, start=1.0, end=3.5, text="hello there")]


def test_empty_transcript():
    assert chunk([], words) == []


# --- Passage size bound ------------------------------------------------------------------


def test_oversized_segment_split_at_word_boundaries():
    giant = Segment(100.0, 160.0, " ".join(f"w{i:04d}" for i in range(1000)))
    segments = [Segment(95.0, 100.0, "before it"), giant, Segment(160.0, 165.0, "after it")]
    passages = chunk(segments, words)

    assert all(words(p.text) <= MAX_TOKENS for p in passages)
    stored = " ".join(p.text for p in passages).split()
    for word in giant.text.split():
        assert word in stored
    giant_parts = [p for p in passages if "w0500" in p.text or "w0999" in p.text]
    assert all(p.start <= 100.0 and p.end >= 160.0 for p in giant_parts)


def test_oversized_segment_without_spaces_is_cut_within_the_bound():
    # A script written without spaces (or a long URL) is one "word" over the bound.
    text = "字" * 1000
    passages = chunk([Segment(10.0, 20.0, text)], len, max_tokens=480)
    assert len(passages) == 3
    assert all(len(p.text) <= 480 for p in passages)
    assert all((p.start, p.end) == (10.0, 20.0) for p in passages)
    assert "".join(p.text for p in passages) == text


@pytest.mark.parametrize("limit", [5, 7, 480])
def test_oversized_segment_parts_keep_times_and_every_word(limit):
    text = " ".join(f"x{i}" for i in range(3 * limit + 1))
    passages = chunk([Segment(10.0, 20.0, text)], words, max_tokens=limit)
    assert len(passages) >= 3
    assert all(words(p.text) <= limit for p in passages)
    assert all((p.start, p.end) == (10.0, 20.0) for p in passages)
    assert " ".join(p.text for p in passages).split() == text.split()
