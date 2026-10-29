# video-to-rag

Ask YouTube videos questions in any language; answers cite the exact passage and moment.

video-to-rag turns a video's captions into a local, searchable library of timestamped passages.
Search it from the command line, or let an MCP client such as Claude Code or Claude Desktop answer
your question from those passages, with a `youtu.be` link to the exact moment and the speaker's
original words. Everything runs on your machine: no API key, no LLM inside the tool. Nothing leaves
the machine except the YouTube requests and, once, the embedding model download.

Version 0.1.0 ingests one video at a time; channels and playlists are not supported yet.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs a suitable Python
  by itself)
- a JavaScript runtime on `PATH` for YouTube: `deno` (preferred) or `node`
- about 2.5 GB of disk for the embedding model, downloaded once on the first ingest
- Linux (tested) or macOS (expected to work, not tested yet)

## Install

```bash
uv tool install --python 3.12 git+https://github.com/<owner>/video-to-rag          # latest main
uv tool install --python 3.12 git+https://github.com/<owner>/video-to-rag@v0.1.0   # a release
video-to-rag --version
```

`--python 3.12` is the tested Python; uv downloads it if your machine lacks it. Python 3.11 to
3.14 should work as well (every dependency publishes packages for them), 3.15 does not yet:
onnxruntime has no package for it.

If the shell cannot find `video-to-rag`, run `uv tool update-shell` once and open a new terminal.
`pipx install --python python3.12 git+https://github.com/<owner>/video-to-rag` works as well. To
try it without installing:
`uvx --python 3.12 --from git+https://github.com/<owner>/video-to-rag video-to-rag --help`.

## Use

### Add a video

```bash
video-to-rag ingest "https://www.youtube.com/watch?v=<video-id>"
```

Ingest takes a single video URL (`watch?v=`, `youtu.be/`, `shorts/`, `live/`); channel and
playlist URLs are not supported yet. It uses the captions in the spoken language (uploader-made
first, then automatic, never machine-translated) and replaces the video if it is already in the
library. The first ingest downloads the ~2.2 GB embedding model from huggingface.co.

**Network modes** — direct by default (the usual `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`
variables are ignored; a proxy is only ever `VIDEO_TO_RAG_PROXY`). When YouTube answers "Sign in
to confirm you're not a bot" (typical from cloud or VPN addresses):
- `--cookies-from-browser firefox` (or `chrome:Default`, …) — the cookies of a browser profile
  that is logged in to YouTube. Use a separate Google account: cookie use can get an account
  flagged.
- `--cookies ~/.config/video-to-rag/cookies.txt` — a Netscape-format cookie file. Keep it private
  and out of every git repository: it is a logged-in session. It is only read, never modified,
  and a malformed file is refused without showing its contents.
- `VIDEO_TO_RAG_PROXY=http://host:port` in the environment — every YouTube request goes through
  that proxy (credentials go in the URL, `http://user:password@host:port`, with reserved
  characters percent-encoded, e.g. `/` as `%2F`; they are masked in every message). The proxy is
  never a command-line option.

### Search

Ask in any language; giving the question also in the videos' language helps. Every hit carries
title, channel, date, time range, a timestamped `youtu.be` link and the passage in its original
language:

```bash
video-to-rag search "hogyan javíthatom a fókuszomat?" "how can I improve my focus?" --limit 3
video-to-rag search "NSDR protocol" --channel "Huberman Lab"
```

`--channel` takes a channel name (any case) or id; `--limit` defaults to 8 and is capped at 20.

## Ask from an MCP client

`video-to-rag mcp` is a stdio MCP server with one tool, `search`. It opens the library read-only
and never contacts YouTube; the client searches and writes the answer, in your language, with
numbered, timestamped citations and the original quotes.

Any MCP client — use the absolute path of the command, because desktop apps and background agents
often do not see your shell's `PATH` (`command -v video-to-rag` prints it):

```json
{
  "mcpServers": {
    "video-to-rag": {
      "command": "/home/<you>/.local/bin/video-to-rag",
      "args": ["mcp"]
    }
  }
}
```

Claude Code:

```bash
claude mcp add --scope user video-to-rag -- video-to-rag mcp
claude mcp list   # video-to-rag: ... ✓ Connected
```

- Ingest at least one video before the first question: that also downloads the embedding model,
  which would take far too long inside a tool call.
- The first search after the server starts loads the model (a few seconds, up to ~15 s cold);
  later ones are fast.
- To serve another library, add `--data-dir <dir>` to the arguments, or set `VIDEO_TO_RAG_HOME`
  in the server's environment (`"env": {...}` in the JSON, `-e VIDEO_TO_RAG_HOME=<dir>` for
  `claude mcp add`).

## Where your data lives

| What | Linux | macOS |
|------|-------|-------|
| Library (`library.sqlite3`) | `~/.local/share/video-to-rag/` | `~/Library/Application Support/video-to-rag/` |
| Embedding model | `~/.cache/video-to-rag/models/` | `~/Library/Caches/video-to-rag/models/` |

`VIDEO_TO_RAG_HOME=<dir>` moves the library, and `--data-dir <dir>` overrides both. The library
holds the passages, their vectors and the video metadata — never cookies or proxy credentials.

## Upgrade

```bash
uv tool upgrade video-to-rag
```

This fetches the latest commit of the branch you installed from and the newest compatible
dependencies, including yt-dlp — the first thing to try when YouTube downloads start failing.
An install pinned to a release stays on it; move to another release with
`uv tool install --force --python 3.12 git+https://github.com/<owner>/video-to-rag@<tag>`.

## Uninstall

```bash
uv tool uninstall video-to-rag
```

This removes the command. The library and the model stay; delete the two directories above to
remove them too.

## Development

Built with a risk-tiered, two-gate agentic workflow (gstack + OpenSpec for large changes + TDD).
See `.dev/guide.md` for the full process (the root `CLAUDE.md` imports it). Engineering
source-of-truth: `openspec/`.

Every task is tiered by risk: **T0** (trivial — just do it), **T1** (small feature — short plan,
you approve at **GATE 1**, build with tests, one review, PR) or **T2** (large/risky — full
OpenSpec loop with TDD, triple review and a **GATE 2** go-live approval). You never run
npm/git/tests by hand.

Toolchain: Python 3.12 via uv, pytest, Ruff; the npm scripts are the task runner. In a checkout,
`uv sync` once, then every command above runs as `uv run video-to-rag …`.

```bash
npm test          # run the scenario tests (pytest)
npm run gates     # Ruff check + test + secret-scan + openspec validate
```

`npm test` includes the `install` tests, which build the package and install it the way the
Install section does; they need PyPI access (offline: `uv run pytest -m "not install"`).

Start a slice — T1 (default): just describe it; T2 (large/risky):
```text
/opsx:propose "<your idea>"
```

## License

MIT — see [LICENSE](LICENSE).
