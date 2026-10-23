"""Hybrid retrieval (multilingual vectors + full text) with RRF fusion, and hit formatting.

Shared by the `search` command and the MCP server. Each query runs a vector KNN (top 50) and an
FTS5 BM25 search (top 50); all lists are fused with Reciprocal Rank Fusion,
`score = sum(1 / (60 + rank))`, de-duplicated by passage and cut to the limit. BM25 and cosine
scores are not comparable; rank fusion needs no calibration.
"""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .embedding import Embedder
from .library import Hit, Library

DEFAULT_LIMIT = 8
MAX_LIMIT = 20
MAX_QUERIES = 5
CANDIDATES = 50
RRF_K = 60
TOKEN_RE = re.compile(r"\w+")
EMPTY_MESSAGE = "The library is empty. Fill it with: video-to-rag ingest <video-url>"


class InvalidQuery(ValueError):
    pass


@dataclass(frozen=True)
class SearchHit:
    passage_id: int
    video_id: str
    title: str
    channel: str
    published: str | None  # YYYY-MM-DD
    start: str  # m:ss, or h:mm:ss from one hour
    end: str
    time_range: str
    link: str  # https://youtu.be/<id>?t=<start in whole seconds>
    language: str
    text: str  # verbatim, in its original language


@dataclass(frozen=True)
class SearchResult:
    hits: list[SearchHit]
    message: str | None = None  # why there are no hits, when that is not obvious


def format_time(seconds: float) -> str:
    total = math.floor(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def fts_query(text: str, keep: Callable[[str], bool] = lambda token: True) -> str | None:
    """Our own tokenization, each token quoted and OR-joined: user text is never FTS syntax."""
    tokens = [t for t in dict.fromkeys(TOKEN_RE.findall(text)) if keep(t)]
    return " OR ".join(f'"{t}"' for t in tokens) if tokens else None


def _informative(library: Library) -> Callable[[str], bool]:
    """Drop tokens found in more than half of all passages.

    Their BM25 IDF is <= 0 (FTS5 clamps it to ~0), so they carry no evidence, yet every match
    would still take a rank and RRF rewards rank alone: across languages a stray "a" (an article
    in both Hungarian and English) would outrank a clear vector winner.
    """
    total = library.passage_count()
    cache: dict[str, bool] = {}

    def keep(token: str) -> bool:
        if token not in cache:
            cache[token] = 2 * library.document_frequency(token) <= total
        return cache[token]

    return keep


def rrf(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[int]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, passage_id in enumerate(ranking, start=1):
            scores[passage_id] = scores.get(passage_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda pid: -scores[pid])  # stable: ties keep first appearance


def validate_queries(queries: Sequence[str]) -> list[str]:
    cleaned = [q.strip() for q in queries if isinstance(q, str)]
    if not 1 <= len(queries) <= MAX_QUERIES or len(cleaned) != len(queries) or not all(cleaned):
        raise InvalidQuery("give one to five non-blank queries")  # MAX_QUERIES
    return cleaned


def validate_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1:
        raise InvalidQuery(f"limit must be between 1 and {MAX_LIMIT}")
    return min(limit, MAX_LIMIT)


def _hit(hit: Hit) -> SearchHit:
    start, end = format_time(hit.start), format_time(hit.end)
    return SearchHit(
        passage_id=hit.passage_id,
        video_id=hit.video_id,
        title=hit.title,
        channel=hit.channel_name,
        published=hit.published,
        start=start,
        end=end,
        time_range=f"{start}–{end}",
        link=f"https://youtu.be/{hit.video_id}?t={math.floor(hit.start)}",
        language=hit.language,
        text=hit.text,
    )


def search(
    library: Library | None,
    embedder: Embedder,
    queries: Sequence[str],
    *,
    channel: str | None = None,
    limit: int | None = None,
) -> SearchResult:
    """`library` is None when it does not exist yet. The model is only used for a non-empty one."""
    queries = validate_queries(queries)
    limit = validate_limit(limit)
    if library is None or library.video_count() == 0:
        return SearchResult([], EMPTY_MESSAGE)

    channel_ids = None
    if channel is not None and channel.strip():
        channel_ids = library.channel_ids_matching(channel)
        if not channel_ids:
            return SearchResult([], f"No hits: no ingested channel matches {channel.strip()!r}.")

    rankings: list[list[int]] = []
    keep = _informative(library)
    for query, vector in zip(queries, embedder.embed_queries(queries), strict=True):
        rankings.append([pid for pid, _ in library.knn(vector, CANDIDATES, channel_ids)])
        if match := fts_query(query, keep):
            rankings.append(library.fts(match, CANDIDATES, channel_ids))
    ids = rrf(rankings)[:limit]
    return SearchResult([_hit(h) for h in library.hits(ids)])


def render_text(result: SearchResult) -> str:
    """Numbered, human-readable hits (the CLI output and the MCP text rendering)."""
    if not result.hits:
        return result.message or "No matching passages."
    blocks = [
        f"{n}. {h.title} — {h.channel} ({h.published or 'date unknown'})\n"
        f"   {h.time_range}  {h.link}  [{h.language}]\n"
        f"   {h.text}"
        for n, h in enumerate(result.hits, start=1)
    ]
    return "\n\n".join(blocks)
