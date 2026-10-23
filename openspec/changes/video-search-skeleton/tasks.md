# Tasks

Every spec scenario gets a failing test first (RED), then the minimal code to pass it (GREEN).
Iterate with `npm run gates:dev`; the full `npm run gates` runs once at the end (group 10).

## 1. Python toolchain (commit: `chore:`)

- [x] 1.1 Create `pyproject.toml` (uv, `src/` layout, package `video_to_rag`, console script
  `video-to-rag`, `requires-python >= 3.11`, deps `yt-dlp[default]`, `fastembed`, `sqlite-vec`,
  `mcp`, `platformdirs`; dev deps `pytest`, `pytest-cov`, `ruff`; pytest marker `model`), add
  `.python-version` (3.12) and `uv.lock`; verify `uv sync` succeeds and `uv run video-to-rag --help` prints usage
- [x] 1.2 Port `scripts/affected-tests.mjs` to `scripts/affected_tests.py` (same change-set rules,
  `ast`-based direct-import mapping, `--run` → pytest, `--lint` → Ruff on changed `.py` files);
  test-first in `tests/test_affected_tests.py` against a temporary git repo; verify those tests pass
- [x] 1.3 Rewire `package.json` scripts per design D1, delete `biome.json`,
  `scripts/affected-tests.mjs` and `test/setup.test.js`, extend `.gitignore` (`.venv/`,
  `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `*.sqlite3`); verify
  `npm run gates` is green on the empty package
- [ ] 1.4 Update `.github/workflows/gates.yml` (setup-uv, `uv sync --frozen`, Biome removed,
  `-m "not model"`); verify the CI run on the PR is green
- [x] 1.5 Update the toolchain lines in `.dev/guide.md`, `.dev/CONTRIBUTING.md` and `README.md`
  (node:test/Biome → pytest/Ruff, commands unchanged); verify `grep -rn "node:test\|Biome\|biome" .dev README.md` finds no stale mention

## 2. Video URL input (`urls.py`)

- [x] 2.1 Tests first for spec *Single video URL input* (watch URL with extra params, short link,
  `shorts/` and `live/` forms, channel URL rejected, playlist-only URL rejected, non-YouTube URL);
  implement URL → video id; verify `uv run pytest tests/test_urls.py` passes

## 3. Captions (`captions.py`)

- [x] 3.1 Build synthetic fixtures in `tests/fixtures/` (yt-dlp info dicts with `subtitles` /
  `automatic_captions` incl. `-orig` and translated tracks; json3 files with `[Music]`, `aAppend`
  events and overlapping ASR timings); verify fixtures load in a smoke test
- [x] 3.2 Tests first for spec *Caption track selection* (manual preferred, automatic fallback,
  no translated track, spoken language missing from metadata) and *No usable captions*; implement
  selection per design D4; verify `uv run pytest tests/test_captions.py -k select` passes
- [x] 3.3 Tests first for spec *Timestamped transcript segments* (annotations stripped, empty
  segments dropped, end clamped to next start); implement json3 parsing; verify
  `uv run pytest tests/test_captions.py -k parse` passes

## 4. YouTube access and credential hygiene (`redact.py`, `youtube.py`)

- [x] 4.1 Tests first for `redact()` (user:pass masked, URLs without credentials untouched,
  several URLs in one message); implement; verify `uv run pytest tests/test_redact.py` passes
- [x] 4.2 Tests first for spec *Network access modes* (direct, browser cookies, cookie file,
  proxy from `VIDEO_TO_RAG_PROXY`) asserting the options handed to an injected `YoutubeDL`
  factory, and that the proxy is not accepted as a CLI argument; implement the adapter (design D3);
  verify `uv run pytest tests/test_youtube.py -k mode` passes
- [x] 4.3 Tests first for spec *Actionable block error* (direct; with cookies → expiry hint),
  *Unavailable video* (private) and *Proxy failure message is masked*, using recorded error
  strings; implement the error mapping (design D12); verify `uv run pytest tests/test_youtube.py -k error` passes
- [x] 4.4 Tests first for spec *JavaScript runtime warning* (deno preferred, node fallback, none →
  warning and still attempts); check the installed yt-dlp's option for enabling a runtime and
  implement detection; verify `uv run pytest tests/test_youtube.py -k runtime` passes

## 5. Chunking (`chunking.py`)

- [x] 5.1 Tests first for spec *Timestamped passages* (coverage and order, boundaries are segment
  boundaries, neighbouring passages overlap) with a word-count tokenizer; implement design D5;
  verify `uv run pytest tests/test_chunking.py` passes
- [x] 5.2 Tests first for spec *Passage size bound* (oversized segment split at word boundaries,
  no word lost, times kept); implement; verify `uv run pytest tests/test_chunking.py -k oversized` passes

## 6. Embeddings (`embedding.py`)

- [x] 6.1 Define the `Embedder` protocol and a deterministic `FakeEmbedder` test helper; verify
  the fake returns stable, normalized vectors in `tests/test_embedding.py`
- [x] 6.2 Implement the E5 embedder (fastembed, `query: ` / `passage: ` prefixes, cache under
  the user cache dir, notice before the first download, model tokenizer exposed as `count_tokens`);
  `@pytest.mark.model` test that every passage from a long fixture stays within 512 model tokens;
  verify `uv run pytest -m model tests/test_embedding.py` passes

## 7. Library (`library.py`)

- [ ] 7.1 Tests first for spec *Library location* (default, `VIDEO_TO_RAG_HOME`, `--data-dir`
  wins); implement path resolution with platformdirs; verify `uv run pytest tests/test_library.py -k location` passes
- [ ] 7.2 Tests first for spec *Shared multi-channel library* and *Idempotent and atomic ingest*
  (same video twice; failure injected before commit keeps the old passages); implement the schema
  and atomic upsert (design D7); verify `uv run pytest tests/test_library.py -k "upsert or atomic or channel"` passes
- [ ] 7.3 Tests first for spec *Embedding model bookkeeping* (mismatch refused, library
  unchanged) and read-only opening that never creates the file; implement; verify
  `uv run pytest tests/test_library.py -k "model or readonly"` passes

## 8. Ingest command (`cli.py ingest`)

- [ ] 8.1 Tests first for the ingest pipeline with a fake YouTube adapter and `FakeEmbedder`:
  spec *Ingest summary*, *Video metadata*, *Video without captions* / *Blocked* / *Private video*
  leave the library unchanged with exit 1, channel URL and conflicting cookie options exit
  non-zero, *No cookies in the library* (scan library bytes); implement `video-to-rag ingest`;
  verify `uv run pytest tests/test_cli_ingest.py` passes
- [ ] 8.2 Add a short "Try it (development)" section to `README.md` (ingest a video, the network
  modes, where the library lives); verify the commands in it match `video-to-rag ingest --help`

## 9. Search (`search.py`, `cli.py search`)

- [ ] 9.1 Tests first for spec *Several phrasings of one question*, *Exact-term matching*,
  *Channel filter*, *Result limit* with `FakeEmbedder`; implement hybrid retrieval with RRF and
  safe FTS query building (design D8); verify `uv run pytest tests/test_search.py` passes
- [ ] 9.2 Tests first for spec *Search hit content* (link `?t=` floor, `m:ss` / `h:mm:ss`,
  verbatim text, language) and *Empty library* (no file created, exit 0); implement formatting;
  verify `uv run pytest tests/test_search.py -k "hit or empty"` passes
- [ ] 9.3 `@pytest.mark.model` test for spec *Hungarian question, English passages* with the
  real E5 model over an English fixture library; verify `uv run pytest -m model tests/test_search_model.py` passes
- [ ] 9.4 Tests first for spec *Search command* output; implement `video-to-rag search`; extend
  the README section with a search example; verify `uv run pytest tests/test_cli_search.py` passes

## 10. MCP server (`mcp_server.py`, `cli.py mcp`)

- [ ] 10.1 Tests first (in-process MCP client session) for spec *Stdio MCP server* (exactly one
  tool `search`; stdout carries only protocol messages) and *Search tool* (successful call,
  invalid input keeps the server alive, empty library); implement with FastMCP; verify
  `uv run pytest tests/test_mcp_server.py` passes
- [ ] 10.2 Tests first for spec *Answering instructions for the client* and *Attribution
  discipline* (instructions contain each rule); write the instructions; verify
  `uv run pytest tests/test_mcp_server.py -k instructions` passes
- [ ] 10.3 Tests first for spec *Read-only and offline from YouTube* (library hash unchanged
  after many calls; YouTube adapter patched to fail if touched); verify
  `uv run pytest tests/test_mcp_server.py -k readonly` passes
- [ ] 10.4 Document the dev MCP registration (`claude mcp add video-to-rag -- uv run --directory <repo> video-to-rag mcp`)
  in the README section; verify `claude mcp list` shows the server connected in this container

## 11. Integration

- [ ] 11.1 Run the full `npm run gates` (lint, all tests including `model`, gitleaks,
  `openspec validate --all`); verify everything is green
- [ ] 11.2 Live end-to-end check, run by the user in the Verify phase (home connection, or
  `--cookies-from-browser` / `VIDEO_TO_RAG_PROXY` on the server): ingest one Huberman Lab
  episode, then ask in Claude Code in Hungarian; verify the answer is Hungarian, cites
  timestamped `youtu.be` links and quotes the English original
- [ ] 11.3 After 11.2 succeeds, replace the synthetic fixtures with a trimmed real `yt-dlp -J`
  dump and json3 file (and confirm the `-orig` track convention); verify the test suite still passes

## Workflow follow-up

- AI review for T2: `/review` + `/codex`, then `/cso` (cookie and proxy handling is the security surface).
- `/ship`: PR to `main`; CHANGELOG and version at release time, not in this slice.
- `/opsx:archive` after merge, so the four specs land in `openspec/specs/`.
