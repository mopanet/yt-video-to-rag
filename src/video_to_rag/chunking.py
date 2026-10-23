"""Segments -> timestamped passages, bounded by real model tokens and overlapping (pure).

Greedy over segments: a passage closes once it spans >= 60 s or holds >= 320 tokens, and never
exceeds 480 tokens (E5's input limit is 512, including the `passage: ` prefix). The next passage
starts with the trailing segments that cover the last >= 10 s (at least one segment, as long as
the bound allows). A single segment over the bound is split at word boundaries, each part keeping
the segment's times. `count_tokens` is the model's own tokenizer in production.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .captions import Segment

MAX_SECONDS = 60.0
TARGET_TOKENS = 320
MAX_TOKENS = 480
OVERLAP_SECONDS = 10.0

CountTokens = Callable[[str], int]


@dataclass(frozen=True)
class Passage:
    seq: int
    start: float
    end: float
    text: str


def _join(units: Sequence[Segment]) -> str:
    return " ".join(u.text for u in units)


def _split(segment: Segment, count_tokens: CountTokens, max_tokens: int) -> list[Segment]:
    if count_tokens(segment.text) <= max_tokens:
        return [segment]
    parts: list[list[str]] = [[]]
    for word in segment.text.split():
        if parts[-1] and count_tokens(" ".join([*parts[-1], word])) > max_tokens:
            parts.append([])
        parts[-1].append(word)
    return [Segment(segment.start, segment.end, " ".join(p)) for p in parts]


def _overlap_start(
    units: Sequence[Segment], first: int, last: int, count_tokens: CountTokens, max_tokens: int
) -> int:
    """Index the next passage starts at: the tail covering the last OVERLAP_SECONDS."""
    k = last
    while k - 1 > first and units[last].end - units[k].start < OVERLAP_SECONDS:
        k -= 1
    k = max(k, first + 1)  # always make progress
    while k <= last and count_tokens(_join(units[k : last + 2])) > max_tokens:
        k += 1  # the tail plus the next segment must still fit the bound
    return k


def chunk(
    segments: Sequence[Segment], count_tokens: CountTokens, *, max_tokens: int = MAX_TOKENS
) -> list[Passage]:
    units = [part for s in segments for part in _split(s, count_tokens, max_tokens)]
    passages: list[Passage] = []
    first = 0
    while first < len(units):
        last = first
        tokens = count_tokens(units[first].text)
        while last + 1 < len(units):
            if units[last].end - units[first].start >= MAX_SECONDS or tokens >= TARGET_TOKENS:
                break
            candidate = count_tokens(_join(units[first : last + 2]))
            if candidate > max_tokens:
                break
            last, tokens = last + 1, candidate
        group = units[first : last + 1]
        passages.append(Passage(len(passages), group[0].start, group[-1].end, _join(group)))
        if last + 1 >= len(units):
            break
        first = _overlap_start(units, first, last, count_tokens, max_tokens)
    return passages
