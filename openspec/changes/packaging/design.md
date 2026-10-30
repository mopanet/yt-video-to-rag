# Design

## Context

See proposal.md for why. Today's state, checked on `feat/video-search-skeleton`:

- `pyproject.toml` already declares the console script `video-to-rag = "video_to_rag.cli:main"`
  and the `uv_build` backend; `uv build --wheel` succeeds and produces a pure-Python wheel
  (`video_to_rag-0.0.0-py3-none-any.whl`). Version is `0.0.0`; there is no `--version` option.
- The library path (`platformdirs.user_data_dir`) and the model cache
  (`platformdirs.user_cache_dir("video-to-rag")/models`) already resolve per user, so an installed
  copy keeps its data across upgrades and outside any container.
- A search on a missing library never touches the model, and the MCP server loads the model only
  on the first search of a non-empty library, so install checks can run without the 2.2 GB model.
- uv 0.11 `uv tool install` has no lock-file option: an installed tool resolves its dependencies
  from the package metadata at install time, not from `uv.lock`.
- The repository has no GitHub remote. A full-history gitleaks scan (46 commits) is clean; the only
  committed cookie file is the fake test fixture.

## Goals / Non-Goals

**Goals:**
- One install command and one upgrade command a user can trust, proven by a test that installs the
  built package the same way a user does.
- An MCP configuration that works from any MCP client on the user's machine.

**Non-Goals:**
- Reproducible installs pinned to `uv.lock` (an install deliberately takes the newest compatible
  dependencies, above all the newest yt-dlp).
- A release pipeline (automatic tagging, GitHub releases, PyPI upload).

## Decisions

### D1 — Install from the GitHub repository, not PyPI
`uv tool install git+https://github.com/mopanet/yt-video-to-rag` installs the latest `main`;
`…/video-to-rag@v0.1.0` installs a release tag. `pipx install git+…` works the same way (it is a
standard wheel) and gets one line in the README.
Every documented install command names `--python 3.12`, the Python the tests run on: without it uv
takes whatever Python it finds or the newest it can download, and on Python 3.15 the install
fails (checked: onnxruntime 1.31 publishes wheels up to `cp314` only, and has no sdist).
*Alternatives:* PyPI (needs an account, name reservation and a publishing flow, which is real work for
a tool with one user so far: later, if ever); `uvx --from git+…` as the MCP command (resolves on
every cold start and needs the network to start the server, so the README mentions it only as a way
to try the tool without installing).

### D2 — One version source: `pyproject.toml`
`--version` uses argparse's version action with the version read from the installed package's
metadata (`importlib.metadata.version("video-to-rag")`). This works the same in a checkout
(`uv run` installs the project into `.venv`) and in an installed tool. `main()` already returns the
exit code of argparse's `SystemExit`, so `--version` exits 0 without further handling.
`package.json` keeps its `0.0.0`: it is a private task runner and never published.
*Alternatives:* a hard-coded `__version__` (a second place to bump); versions from git tags
(needs another build backend, since `uv_build` has no dynamic versions).

### D3 — Upper bounds where a release could break us, none on yt-dlp
Because installs resolve fresh (Context), the dependencies get upper bounds at the next breaking
boundary: `fastembed <0.10` (0.x: minor releases may break), `mcp <3`, `numpy <3`,
`platformdirs <5`, `sqlite-vec <0.2`. The lower bounds stay as they are. `yt-dlp` stays
unbounded, because YouTube breaks old yt-dlp releases and the fix is always "upgrade yt-dlp". The
current lock already satisfies these bounds; re-locking changes nothing else.
*Alternatives:* no bounds (a fresh install can break the day a dependency ships a major release);
exact pins (stale yt-dlp, which is worse than the risk the pins avoid).

### D4 — Install smoke test as a pytest module with an `install` marker
`tests/test_installation.py` builds the wheel (`uv build --wheel`) into a temporary directory once
per session and installs it with `uv tool install`, with `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` in that
temporary directory (the user's real tools are never touched), `--python 3.12` as in the README,
`XDG_DATA_HOME` and `XDG_CACHE_HOME`
pointed at empty temporary directories, and the working directory outside the repository. It then
runs the installed binary for each scenario in `specs/installation/spec.md`. For the MCP scenarios
it uses the `mcp` client from the project's own environment to start the installed
`video-to-rag mcp` over stdio. The expected version is read from `pyproject.toml`, so the test
stays valid after every version bump.
The module needs network access to PyPI and takes about a minute on a cold uv cache. It runs in
the full gate (`npm test`, so locally and in CI). The `install` marker exists so it can be
deselected deliberately (`-m "not install"`) when offline. The build and install steps have a
10-minute timeout, so a stalled download fails the test instead of hanging CI. `gates:dev`
selects it only when its own file, the shared test helpers or the dependency files change, which
is when packaging can break.
*Alternatives:* a shell step in CI only (cannot be run locally the same way, and cannot go RED
first); building in the test process with `pip` (not what users run).

### D5 — MCP configuration that does not depend on the client's PATH
The README gives a generic stdio configuration with the absolute path of the installed command,
because desktop apps and background agents often do not inherit the login shell's `PATH`
(`~/.local/bin`). `command -v video-to-rag` (or `uv tool dir --bin`) shows the path:

```json
{ "mcpServers": { "video-to-rag": { "command": "/home/<you>/.local/bin/video-to-rag", "args": ["mcp"] } } }
```

It also gives the Claude Code form (`claude mcp add --scope user video-to-rag -- video-to-rag mcp`)
and two operating notes: run one `ingest` before the first MCP search, so that the 2.2 GB model
is downloaded by the CLI and not inside a tool call that the client would time out; and the first
search after a server start takes up to ~15 s while the model loads.

### D6 — README for users first, one copy of every instruction
Order: what it does → requirements (uv; deno or node for YouTube) → install → use (ingest,
network modes, search) → MCP clients → where data lives → upgrade → uninstall → development. The
existing "Try it (development)" content becomes the "use" section, written with the installed
`video-to-rag …` command, plus one line that in a checkout every command is `uv run video-to-rag …`.
Uninstall says that `uv tool uninstall video-to-rag` leaves the library and the model cache, and
names both directories.

### D7 — Publication is the go-live, so GATE 2 comes before the first push
The repository is public from its first push, and that cannot be taken back. Order:
1. This branch stays stacked on `feat/video-search-skeleton`. Slice 1 is not merged into `main`
   locally: the user reviews it as the first pull request on GitHub (the Verify phase), and the
   packaging pull request targets that branch until then.
2. Build, then the full gate, `/review` + `/codex`, then `/cso`, including a review of every tracked
   file for personal data (secrets are already covered by gitleaks over the full history).
3. **GATE 2**: the user approves publishing, creates the empty public repository, and gives the
   container a repo-scoped token (`pat-set video-to-rag` on the host).
4. Push `main` and both branches; open pull request 1 (slice 1 → `main`) and pull request 2
   (packaging → slice 1's branch); CI green on both (the project's first CI runs).
5. The user installs by hand from the packaging branch
   (`uv tool install git+https://github.com/mopanet/yt-video-to-rag@feat/packaging`), registers the
   MCP server in the Personal OS and reviews both pull requests (the Verify phase).
6. After pull request 1 is merged, pull request 2 is retargeted to `main` and merged; `v0.1.0` is
   tagged on `main` and pushed.

## Risks / Trade-offs

- [A fresh install picks up a dependency release that was never tested] → upper bounds (D3); the
  smoke test resolves fresh on every pull request; a user can install a release tag.
- [YouTube breaks the yt-dlp a user installed months ago] → yt-dlp unbounded; the README upgrade
  section says this is the first fix to try.
- [The smoke test needs the network and adds about a minute] → only in the full gate and CI, uv
  cache keeps repeat runs short, `-m "not install"` when offline.
- [Only Python 3.12 is tested, while `requires-python` says `>=3.11`] → the README names 3.12 in
  every install command and says 3.15 does not work yet; a test matrix over 3.11–3.14 is left for
  when a user needs another version. `requires-python` gets no upper bound, so a future
  onnxruntime with `cp315` wheels works without a release of ours.
- [Process files (`.claude/`, `.agents/`, `.dev/`, `openspec/`) become public] → they are part of
  how the project is built and are meant to be shareable; the `/cso` file review in D7 confirms
  that nothing personal is in them before GATE 2.
- [`uv tool upgrade` behaves differently for git installs than documented] → checked during the
  build against the installed uv before the README states it.

## Open Questions

- Settled at GATE 2 (2026-10-30): the repository is `mopanet/yt-video-to-rag`. The distribution,
  the command and the data directories keep the name `video-to-rag`; only the install URLs carry
  the repository name.
