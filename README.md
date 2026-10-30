# video-to-rag

Ask YouTube videos questions in any language; answers cite the exact passage and moment.

video-to-rag turns a video's captions into a local, searchable library of timestamped passages.
Search it from the command line, or let an MCP client such as Claude Code or Claude Desktop answer
your question from those passages, with a `youtu.be` link to the exact moment and the speaker's
original words. Everything runs on your machine: no API key, no LLM inside the tool. Nothing leaves
the machine except the YouTube requests and, once, the embedding model download.

Version 0.1.0 ingests one video at a time; channels and playlists are not supported yet.

## Responsible use

video-to-rag is for your own, personal research. YouTube's Terms of Service allow downloading only
through YouTube's own features, so fetching captions with yt-dlp goes against them: YouTube may
block the address or the account it sees (see the separate-account advice under network modes).
The captions remain their creators' work: keep your library to yourself, do not publish it or
build a service on it, and quote only short passages when you share an answer. Copyright rules
differ by country; this is not legal advice.

## Requirements

- Linux (tested) or macOS (expected to work, not tested yet)
- about 2.5 GB of disk for the embedding model, downloaded once on the first ingest
- about 2.5 GB of free memory (RAM plus swap) to ingest: the loaded model takes ~1.6 GB, embedding
  adds the rest. An ingest that ends with `Killed` ran out of memory; add swap or free some RAM.
  The MCP server keeps the model loaded after its first search, ~1.6 GB for as long as it runs.
- uv and a JavaScript runtime (`deno` or `node`); the install steps below set them up

## Install

1. **uv**, the Python package manager (it installs a suitable Python by itself):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   Then open a new terminal (or run `source $HOME/.local/bin/env`) so that `uv` is on `PATH`.
   macOS with Homebrew: `brew install uv`; other ways are in
   [uv's installation guide](https://docs.astral.sh/uv/getting-started/installation/).

2. **A JavaScript runtime**, which yt-dlp needs to read YouTube: `deno` (preferred) or `node`, on
   `PATH`. Skip this step if `deno --version` or `node --version` already works; otherwise:

   ```bash
   curl -fsSL https://deno.land/install.sh | sh   # needs unzip (Debian/Ubuntu: sudo apt install unzip)
   ```

   The installer asks whether to add deno to your `PATH`: answer yes. macOS: `brew install deno`.

3. **video-to-rag**:

   ```bash
   uv tool install --python 3.12 git+https://github.com/mopanet/yt-video-to-rag          # latest main
   uv tool install --python 3.12 git+https://github.com/mopanet/yt-video-to-rag@v0.1.0   # a release
   ```

4. **Check** it in a new terminal:

   ```bash
   video-to-rag --version   # video-to-rag 0.1.0
   deno --version           # or: node --version
   ```

   If the shell cannot find `video-to-rag`, run `uv tool update-shell` once and open a new
   terminal again.

`--python 3.12` is the tested Python; uv downloads it if your machine lacks it. Python 3.11 to
3.14 should work as well (every dependency publishes packages for them), 3.15 does not yet:
onnxruntime has no package for it.

`pipx install --python python3.12 git+https://github.com/mopanet/yt-video-to-rag` works as well. To
try it without installing:
`uvx --python 3.12 --from git+https://github.com/mopanet/yt-video-to-rag video-to-rag --help`.

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

#### Cookies that keep working

YouTube replaces the cookies of an open YouTube tab every so often as a security measure, and a
file exported from that tab stops working (the error then ends with "Cookies were sent, so they
may be expired"). Export them from a session that is never opened again
([yt-dlp's method](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)):

1. Open a new private (incognito) window and log in to YouTube, preferably with a separate Google
   account.
2. In the same tab, open `https://www.youtube.com/robots.txt`. This must be the only private tab.
3. Export the `youtube.com` cookies with a cookies.txt extension, such as
   [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   for Chrome or [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) for
   Firefox (allow it in private windows), then **close the private window**. yt-dlp's own
   `--cookies-from-browser … --cookies …` export does not work here: it reads the regular browser
   profile, not the private session.
4. Keep the file where only you can read it, and delete the export from the downloads folder:

   ```bash
   mkdir -p ~/.config/video-to-rag && chmod 700 ~/.config/video-to-rag
   mv ~/Downloads/<exported file>.txt ~/.config/video-to-rag/cookies.txt
   chmod 600 ~/.config/video-to-rag/cookies.txt
   video-to-rag ingest "https://www.youtube.com/watch?v=<video-id>" --cookies ~/.config/video-to-rag/cookies.txt
   ```

   For a server, create the directory there the same way, copy the file over with
   `scp <exported file>.txt <user>@<server>:~/.config/video-to-rag/cookies.txt`, and run
   `chmod 600` on it there.

When the bot check stays even with freshly exported cookies, YouTube is blocking the machine's
address: route the requests through a proxy with `VIDEO_TO_RAG_PROXY`.

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
- Run `ingest` and the MCP server as the same user: the library and the model cache live in that
  user's home directory (see below), so a client started as another user (for example `root`
  versus your own account) finds an empty library and no model.
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
`uv tool install --force --python 3.12 git+https://github.com/mopanet/yt-video-to-rag@<tag>`.

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
