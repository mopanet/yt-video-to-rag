# video-to-rag

Built with the risk-tiered, two-gate agentic workflow (gstack + OpenSpec for large changes + TDD).
See `.dev/guide.md` for the full process (the root `CLAUDE.md` imports it). Engineering
source-of-truth: `openspec/`.

## How development works
Every task is tiered by risk: **T0** (trivial — just do it), **T1** (small feature — short plan,
you approve at **GATE 1**, build with tests, one review, PR) or **T2** (large/risky — full
OpenSpec loop with TDD, triple review and a **GATE 2** go-live approval). You never run
npm/git/tests by hand.

Toolchain: Python 3.12 via [uv](https://docs.astral.sh/uv/), pytest, Ruff; the npm scripts are
the task runner.

```bash
npm test          # run the scenario tests (pytest)
npm run gates     # Ruff check + test + secret-scan + openspec validate
```

Start a slice — T1 (default): just describe it; T2 (large/risky):
```text
/opsx:propose "<your idea>"
```

## Try it (development)
Needs [uv](https://docs.astral.sh/uv/) and a JavaScript runtime on `PATH` for YouTube
(`deno` preferred, `node` works). Nothing leaves the machine except the YouTube requests and,
once, the ~2.2 GB embedding model download from huggingface.co (cached under
`~/.cache/video-to-rag/models`).

```bash
uv sync
uv run video-to-rag ingest "https://www.youtube.com/watch?v=<video-id>"
```

Ingest takes a single video URL (`watch?v=`, `youtu.be/`, `shorts/`, `live/`); channel and
playlist URLs are not supported yet. It uses the captions in the spoken language (uploader-made
first, then automatic) and replaces the video if it is already in the library.

**Network modes** — direct by default. When YouTube answers "Sign in to confirm you're not a bot"
(typical from cloud or VPN addresses):
- `--cookies-from-browser firefox` (or `chrome:Default`, …) — the cookies of a browser profile
  that is logged in to YouTube. Use a separate Google account: cookie use can get an account
  flagged.
- `--cookies cookies.txt` — a Netscape-format cookie file. It is only read, never modified, and
  a malformed file is refused without showing its contents.
- `VIDEO_TO_RAG_PROXY=http://host:port` in the environment — every YouTube request goes through
  that proxy (credentials go in the URL, `http://user:password@host:port`, with reserved
  characters percent-encoded, e.g. `/` as `%2F`; they are masked in every message). The proxy is
  never a command-line option.

**Search** — ask in any language; giving the question also in the videos' language helps.
Every hit carries title, channel, date, time range, a timestamped `youtu.be` link and the passage
in its original language:

```bash
uv run video-to-rag search "hogyan javíthatom a fókuszomat?" "how can I improve my focus?" --limit 3
uv run video-to-rag search "NSDR protocol" --channel "Huberman Lab"
```

`--channel` takes a channel name (any case) or id; `--limit` defaults to 8 and is capped at 20.

**Ask Claude (MCP)** — register the stdio server once, then ask in Claude Code in any language;
Claude searches the library and answers with numbered, timestamped citations and the original
quotes:

```bash
claude mcp add video-to-rag -- uv run --directory /path/to/video-to-rag video-to-rag mcp
claude mcp list   # video-to-rag: ... ✓ Connected
```

The server offers one tool, `search`, opens the library read-only and never contacts YouTube.
The first search loads the embedding model (a few seconds, up to ~15 s cold); later ones are
fast. Append
`--data-dir <dir>` (or set `VIDEO_TO_RAG_HOME` with `claude mcp add -e`) to serve another library.

**Where the library lives** — one SQLite file, `library.sqlite3`, in
`~/.local/share/video-to-rag/` on Linux (the OS per-user data directory elsewhere).
`VIDEO_TO_RAG_HOME=<dir>` overrides the directory and `--data-dir <dir>` overrides both.
