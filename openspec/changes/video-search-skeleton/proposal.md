# Proposal

## Why

The knowledge in long-form YouTube channels (e.g. Huberman Lab: hundreds of 2–3 hour episodes)
is practically unsearchable, and only in the speaker's language. We want to ask a question in any
language ("Huberman szerint hogyan javíthatom a fókuszomat?") and get an answer grounded in the
exact passage and moment of the video. The repo is an empty scaffold today. This first slice
proves the riskiest path end to end on a single video: captions become a timestamped,
multilingual passage index that Claude can query over MCP. The scaffold's toolchain is
Node-only, while every building block of this project (yt-dlp, local ONNX embeddings, later
Whisper) is Python-native.

## What Changes

- **Toolchain switch to Python** (uv, Ruff, pytest). `npm run preflight | gates | gates:dev`
  stay as the entry points so the documented workflow keeps working; the affected-tests helper,
  CI and the toolchain mentions in the dev docs follow.
- **`video-to-rag ingest <video-url>`**: fetch one YouTube video's metadata and captions
  (manual over auto-generated, in the spoken language, never machine-translated), split them into
  timestamped passages, embed them locally, and store them in the library.
- **Three network modes for ingest**: direct (default), browser cookies
  (`--cookies-from-browser`), cookie file (`--cookies`), and proxy (from the
  `VIDEO_TO_RAG_PROXY` environment variable). Credentials are never stored or logged. A YouTube
  bot check produces an actionable error that names the cookie and proxy options.
- **One shared local library**: a single SQLite file in the OS user-data directory (overridable)
  holding channels, videos, passages, vectors and a full-text index. Re-ingesting a video
  replaces it instead of duplicating it; the library records which embedding model built it.
- **`video-to-rag search <query>...`**: hybrid search (multilingual vectors + full text), optional
  channel filter; every hit carries title, channel, date, a timestamped `youtu.be` link and the
  original passage text.
- **MCP server `video-to-rag mcp`** (stdio) with one tool, `search`, and server instructions that
  tell the client to search in both the user's and the videos' language, answer in the user's
  language, and cite every claim with the timestamped link and the original quote.
- **No LLM and no API key** anywhere in the tool; the MCP client writes the answer.

### Out of scope (later slices)

- Whole-channel ingest, video→channel resolution, filtering (short / off-topic / duplicate),
  resume and incremental runs (slice 2). A channel or playlist URL is rejected for now.
- Whisper fallback (slice 3). A video without captions is reported and skipped.
- MCP tools `list_channels` and `get_passage` (slice 2).
- Config file, re-index on embedding-model change, export, packaging (`uvx`), README and the
  GitHub repository (slice 4). GPU acceleration.

## Capabilities

### New Capabilities

- `transcript-acquisition`: getting a timestamped transcript and its metadata for a YouTube video
  — caption-track selection, network access modes, credential handling, block and error reporting.
- `transcript-library`: the local library — location, passage chunking with timestamps,
  persistence, idempotent re-ingest, embedding-model bookkeeping.
- `passage-search`: multilingual hybrid retrieval over the library and the shape of a search hit
  (shared by the CLI and the MCP server).
- `mcp-server`: the MCP tool surface and the instructions it gives the client for answering with
  citations.

### Modified Capabilities

None (no existing specs).

## Impact

- **Code**: new `src/video_to_rag/` package and `tests/`; `pyproject.toml`, `uv.lock`,
  `.python-version`. Removed: `biome.json`, `test/setup.test.js`, `scripts/affected-tests.mjs`
  (replaced by a Python equivalent). Updated: `package.json` scripts,
  `.github/workflows/gates.yml`, `.gitignore`, toolchain lines in `.dev/guide.md`,
  `.dev/CONTRIBUTING.md` and `README.md`.
- **Dependencies**: yt-dlp (with its YouTube JS-challenge solver), fastembed (ONNX Runtime, no
  PyTorch), sqlite-vec, mcp, platformdirs; dev: pytest, pytest-cov, ruff. yt-dlp needs a
  JavaScript runtime (deno or node) on `PATH` for YouTube.
- **External services at runtime**: youtube.com (ingest only); huggingface.co once, for the
  ~2.2 GB embedding model. Nothing else leaves the machine.
- **Data**: the library lives outside the repo; no downloaded content is ever committed.
- **Security surface**: user-supplied cookies and proxy credentials pass through the tool →
  `/cso` review in this slice.
- **Verification constraint**: YouTube blocks caption requests from this dev server (verified
  2026-10-23: "Sign in to confirm you're not a bot"). Automated tests run on recorded fixtures;
  the end-to-end check against live YouTube needs a home connection, cookies or a proxy.
