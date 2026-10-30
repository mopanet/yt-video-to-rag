# Design

## Context

See proposal.md (Why) for motivation and the four specs for required behavior.

- **Repo**: an empty Node scaffold — Biome, `node:test`, `scripts/affected-tests.mjs`
  (import-based affected-test selection), CI in `.github/workflows/gates.yml`. The workflow docs
  and the host tooling call `npm run preflight | gates | gates:dev`.
- **Dev machine**: devcontainer on a cloud VM — 4 vCPU (AMD EPYC), 7.6 GB RAM, no GPU. `uv` is
  installed; system Python 3.11, uv-managed 3.12 works.
- **Measured on 2026-10-23 from this machine**:
  - yt-dlp lists a channel (`@hubermanlab/videos`, flat playlist) fine, but per-video
    extraction fails with "Sign in to confirm you're not a bot"; `youtube-transcript-api` fails
    with `RequestBlocked` (cloud IP). yt-dlp also warns that no JavaScript runtime is enabled
    (only deno is enabled by default; node is installed here).
  - Embedding spike (8 English passages, 8 Hungarian questions, fastembed/ONNX on 4 threads):
    `intfloat/multilingual-e5-large` → 8/8 correct at rank 1, ~1.2 s per ~400-token passage,
    2.24 GB; `Qwen/Qwen3-Embedding-0.6B-Q` → 6/8, ~2.2 s per passage.
  - sqlite-vec 0.1.9 loads in uv's Python 3.12 (SQLite 3.53, FTS5 enabled).

## Goals / Non-Goals

**Goals:**
- A pure core (URL parsing, caption selection and parsing, chunking, fusion, formatting,
  redaction) behind thin adapters (yt-dlp, embedder, SQLite, CLI, MCP), so every scenario is
  testable offline with fixtures and a fake embedder.
- Exactly one test needs the real model: the cross-language retrieval scenario.

**Non-Goals:**
- Throughput work (parallel downloads, GPU, embedding batch tuning), async ingest, progress bars.
- A Python API for third parties; the CLI and MCP are the only interfaces.

## Decisions

### D1 — Python toolchain behind the existing npm entry points
uv project, `src/` layout, `requires-python >= 3.11`, `.python-version` = 3.12. Ruff (lint and
format), pytest, pytest-cov. `package.json` stays as a thin task runner:

```
check           uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
format          uv run ruff check --fix ... && uv run ruff format ...
test            uv run pytest
test:cov        uv run pytest --cov=video_to_rag --cov-report=term-missing
check:affected  uv run python scripts/affected_tests.py --lint
test:affected   uv run python scripts/affected_tests.py --run
gates:dev, gates, preflight, secrets    unchanged composition
```

`scripts/affected_tests.py` ports the JS helper with the same contract: change set = unstaged +
staged + untracked, `AFFECTED_SCOPE=branch` / `BASE_BRANCH` as before; a changed
`tests/**/test_*.py` selects itself, a changed `src/video_to_rag/a/b.py` selects every test whose
`import` / `from` statements (parsed with `ast`) name `video_to_rag.a.b` directly; `--lint` runs
Ruff on the changed `.py` files only.

*Why npm stays*: `.dev/guide.md`, `CLAUDE.md`, the host's `new-feature` and the permission
allowlist all call `npm run …`; keeping the entry points means no process change.
*Alternatives*: Makefile/justfile (breaks those references); pytest-testmon (stateful
coverage DB, awkward across worktrees, different semantics from the documented import rule).

CI: `astral-sh/setup-uv`, `uv sync --frozen`, Biome install dropped, OpenSpec and gitleaks kept.
Tests marked `model` (they download 2.2 GB) are excluded in CI with `-m "not model"`; locally
`npm test` runs them.

### D2 — Module layout (seams = test boundaries)

```
src/video_to_rag/
  cli.py          argparse: ingest | search | mcp, --data-dir, exit codes
  urls.py         YouTube URL -> video id; rejects channel/playlist/non-YouTube   (pure)
  youtube.py      yt-dlp adapter: metadata + caption download, network options, error mapping
  captions.py     track selection + json3 -> segments                             (pure)
  chunking.py     segments -> passages, token-bounded, overlapping                (pure)
  embedding.py    Embedder protocol; E5 implementation (fastembed)
  library.py      SQLite schema, open/create, atomic upsert, model check, queries
  search.py       hybrid retrieval, RRF fusion, hit formatting
  mcp_server.py   MCPServer, `search` tool, client instructions
  redact.py       credential masking for every outgoing message                   (pure)
```

Tests: `tests/fixtures/` holds trimmed yt-dlp info dicts and json3 caption files. They are
**synthetic** (built from yt-dlp's documented fields) because YouTube blocks extraction from this
machine. `FakeEmbedder` produces deterministic hashed bag-of-words vectors for plumbing tests;
the real E5 model is used only by `@pytest.mark.model` tests.

### D3 — yt-dlp through its Python API, one network stack
`yt_dlp.YoutubeDL` with `skip_download`, `noplaylist`, and — per mode — `cookiesfrombrowser`,
`cookiefile`, `proxy`. Caption files are fetched with `ydl.urlopen`, so they go through the same
session, cookies and proxy. No subprocess and no argv: credentials never appear in a command line
or in `ps`. Dependency: `yt-dlp[default]`, which pulls in the YouTube JS-challenge solver.
JavaScript runtime: `deno`, then `node` found via `shutil.which` is enabled in the yt-dlp options;
none → the warning from the spec.
*Alternative*: `youtube-transcript-api` — a second network stack, equally blocked from cloud IPs,
and no metadata.

### D4 — Caption track selection and parsing
- Spoken language = `info["language"]` reduced to its base code (`en-US` → `en`). If missing,
  the language of the speech-recognition source track, which yt-dlp lists in
  `automatic_captions` under a `<lang>-orig` key.
- Manual: a `subtitles` entry whose base code equals the spoken language (`live_chat` ignored).
  Automatic: `automatic_captions["<lang>-orig"]`, else `automatic_captions["<lang>"]`. All other
  `automatic_captions` entries are machine translations and are never used.
- Format `json3`: each event has `tStartMs`, `dDurationMs`, `segs[].utf8`. Events without `segs`
  and `aAppend` line-break events are skipped; text is joined, `[...]` annotations stripped,
  whitespace collapsed, empty segments dropped. End = min(start + duration, next start), because
  ASR events overlap in time.

### D5 — Chunking bounded by real tokens
Greedy over segments: close a passage when it spans ≥ 60 s or holds ≥ 320 tokens; never exceed
480 tokens (E5's limit is 512, including the `passage: ` prefix). Overlap: the next passage starts
with the trailing segments covering the last ≥ 10 s (at least one segment). A single segment over
480 tokens is split at word boundaries, keeping its times. Tokens are counted by an injected
`count_tokens` — the model's own tokenizer in production, a word count in tests.
*Why tokens, not words*: Hungarian or German text uses ~1.5–2× more tokens per word than English;
a word cap would silently truncate non-English passages.

### D6 — Embeddings: fastembed + `intfloat/multilingual-e5-large`
ONNX Runtime on CPU, 1024 dimensions, L2-normalized. We add the `query: ` / `passage: ` prefixes
ourselves via `embed()` (as in the spike). Model cache: `platformdirs.user_cache_dir("video-to-rag")/models`
(fastembed's default is a temp dir, which would re-download after a reboot). The first ingest
prints a notice before the ~2.2 GB download.
*This replaces the `bge-m3` default floated during exploration*: fastembed has no dense bge-m3;
running bge-m3 needs PyTorch (multi-GB, CUDA wheels by default on Linux), which is heavy for a
`uvx` install, and e5-large scored 8/8 in the spike.
*Alternatives*: Qwen3-Embedding-0.6B (6/8, slower); multilingual MiniLM (faster, weaker).
*Throughput*: ~90 passages for a 2-hour episode ≈ 2 min on this VM; a channel the size of
Huberman Lab (~20k passages) ≈ 7 h on 4 vCPU — one-time, resumable from slice 2 on.

### D7 — Library: one SQLite file
`<data-dir>/library.sqlite3`, WAL mode, `schema_version = 1`.

```
meta(key PK, value)            schema_version, embedding_model, embedding_dim
channels(id PK, name)
videos(id PK, channel_id -> channels, title, published 'YYYY-MM-DD', duration_s,
       language, caption_kind 'manual'|'auto', ingested_at)
passages(id INTEGER PK, video_id -> videos, seq, start_s REAL, end_s REAL, text)
passages_fts   FTS5(text), rowid = passages.id, tokenize 'unicode61 remove_diacritics 2'
passages_vec   vec0(embedding float[1024] distance_metric=cosine, channel_id text), rowid = passages.id
```

- **Atomic upsert**: network and embedding work happen first, outside any transaction; then one
  `BEGIN IMMEDIATE` deletes the video's old rows (passages, FTS, vec), upserts channel and video,
  inserts the new rows and commits. An interruption before the commit rolls back, so the
  previous version stays intact.
- **Read-only opening** (`file:…?mode=ro`) for `search` and the MCP server: they cannot modify
  the library or create it.
- **Model check** compares `meta.embedding_model` with the tool's model before any read or write.
- **Channel filter** uses the vec0 metadata column (`channel_id IN (...)` inside the KNN query;
  a channel name can match several channel ids).
  Fallback if it misbehaves: brute-force `vec_distance_cosine` over a filtered join, which is
  fast enough at this scale.

### D8 — Hybrid retrieval with Reciprocal Rank Fusion
Each query runs (a) a vector KNN, top 50, on `query: <q>`, and (b) an FTS5 BM25 search, top 50.
For (b) the query is tokenized by us and each token quoted and OR-joined, so user text is never
interpreted as FTS syntax. Tokens found in more than half of all passages are left out of (b):
their BM25 IDF is ≤ 0 (FTS5 clamps it to ~0), so they carry no evidence, yet every match would
still take a rank. All lists are fused with RRF, `score = Σ 1 / (60 + rank)`, then
de-duplicated by passage id and cut to `limit`.
*Found during implementation*: without that filter the cross-language scenario failed — the
Hungarian article "a" matched the English word "a", and its noise-only BM25 list outranked the
clear vector winner in the fusion.
*Why RRF*: BM25 and cosine scores are not comparable; rank fusion needs no calibration or
tuning. *Alternative*: a weighted score sum — needs per-corpus tuning.

### D9 — CLI behavior
argparse subcommands; global `--data-dir`. Exit codes: 0 success (including "library empty"),
1 runtime failure (blocked, unavailable, no captions, model mismatch), 2 usage error. Progress
and errors go to stderr, results to stdout. Times: `m:ss` under one hour, `h:mm:ss` from one
hour; link `t` = floor(start).

### D10 — MCP server
The official `mcp` Python SDK (`MCPServer`, FastMCP's successor in mcp 2.x), stdio transport. Tool
`search(queries: list[str], channel: str | None = None, limit: int = 8)` returns structured hits
plus a text rendering. The instructions are a constant in `mcp_server.py`, written in English
(the client answers in the user's language anyway). The embedder loads lazily on the first call
(~14 s measured) and stays loaded. Logging is configured to stderr before the server starts.
Dev registration: `claude mcp add video-to-rag -- uv run --directory <repo> video-to-rag mcp`
(the `uvx` form comes with packaging in slice 4).

### D11 — Credential hygiene
- The proxy is read only from `VIDEO_TO_RAG_PROXY`.
- Cookies are read by yt-dlp itself from the browser or file; our code never touches their
  values and never logs the yt-dlp options dict.
- `redact()` masks `scheme://user:pass@host` → `scheme://***@host` and is applied to every
  exception message we print, and as a filter on our logger.

### D12 — Error mapping
yt-dlp `DownloadError` text containing "confirm you" plus "not a bot" (either apostrophe) maps
to *Blocked*, with an extra cookie-expiry hint when cookies were used. "Private video", "Video
unavailable", "members-only" or "removed" map to *Unavailable*, keeping YouTube's reason.
Anything else is a generic error with the redacted message.

## Risks / Trade-offs

- [Synthetic fixtures may not match real yt-dlp output] → built only from documented fields; the
  first live end-to-end run (home connection, cookies or proxy) validates them, and a task
  replaces them with a real `yt-dlp -J` dump at that point.
- [The `<lang>-orig` convention for the ASR source track is unverified from here] → same
  live-run check; the fallback `automatic_captions["<lang>"]` still picks a usable track.
- [YouTube changes break yt-dlp] → minimum version pinned; upgrading is one
  `uv lock --upgrade-package yt-dlp`; unknown errors still yield a readable, redacted message.
- [yt-dlp writes refreshed cookies back to the `--cookies` file] → standard yt-dlp behavior on
  the user's own file; documented, nothing is copied elsewhere.
- [Cookie mode can get a Google account flagged] → the block error and the README recommend a
  separate account.
- [~7 h CPU embedding for a large channel] → one-time; resume in slice 2; GPU later.
- [Changing the embedding model needs a full re-embed] → the model is recorded and a mismatch
  is refused; a re-index command comes later.
- [Auto-captions lack punctuation and mishear names] → hybrid search tolerates it; quotes are
  shown verbatim, so the user sees the source quality.
- [sqlite-vec is pre-1.0] → isolated in `library.py`, with the brute-force fallback ready.

## Migration Plan

Greenfield: no user data exists. The toolchain switch is one commit; rollback = revert. The
library carries `schema_version = 1` so later slices can migrate it.

## Open Questions

- The exact yt-dlp Python-API option for enabling node as the JavaScript runtime; checked
  against the installed version during implementation, no design impact.
