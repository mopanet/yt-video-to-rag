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
`uv tool install git+https://github.com/<owner>/video-to-rag` installs the latest `main`;
`…/video-to-rag@v0.1.0` installs a release tag. `pipx install git+…` works the same way (it is a
standard wheel) and gets one line in the README.
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
temporary directory (the user's real tools are never touched), `XDG_DATA_HOME` and `XDG_CACHE_HOME`
pointed at empty temporary directories, and the working directory outside the repository. It then
runs the installed binary for each scenario in `specs/installation/spec.md`. For the MCP scenarios
it uses the `mcp` client from the project's own environment to start the installed
`video-to-rag mcp` over stdio. The expected version is read from `pyproject.toml`, so the test
stays valid after every version bump.
The module needs network access to PyPI and takes about a minute on a cold uv cache. It runs in
the full gate (`npm test`, so locally and in CI). The `install` marker exists so it can be
deselected deliberately (`-m "not install"`) when offline. `gates:dev` selects it only when its own
file or the dependency files change, which is when packaging can break.
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
1. `feat/video-search-skeleton` is finished and merged into local `main`; this branch is rebased
   onto it.
2. Build, then the full gate, `/review` + `/codex`, then `/cso`, including a review of every tracked
   file for personal data (secrets are already covered by gitleaks over the full history).
3. **GATE 2**: the user approves publishing, creates the empty public repository, and gives the
   container a repo-scoped token (`pat-set video-to-rag` on the host).
4. Push `main`, open the pull request for this branch, CI green (this is also the first CI run),
   merge, tag `v0.1.0` on `main`, push the tag.
5. The user installs by hand on their machine and registers the MCP server in the Personal OS
   (the Verify phase).

## Risks / Trade-offs

- [A fresh install picks up a dependency release that was never tested] → upper bounds (D3); the
  smoke test resolves fresh on every pull request; a user can install a release tag.
- [YouTube breaks the yt-dlp a user installed months ago] → yt-dlp unbounded; the README upgrade
  section says this is the first fix to try.
- [The smoke test needs the network and adds about a minute] → only in the full gate and CI, uv
  cache keeps repeat runs short, `-m "not install"` when offline.
- [The Python floor (`>=3.11`) is tested only by chance] → the smoke test uses whichever Python uv
  picks (3.11 in the devcontainer, 3.12 on the CI runner); a dedicated 3.11 job is left for when a
  user needs it.
- [Process files (`.claude/`, `.agents/`, `.dev/`, `openspec/`) become public] → they are part of
  how the project is built and are meant to be shareable; the `/cso` file review in D7 confirms
  that nothing personal is in them before GATE 2.
- [`uv tool upgrade` behaves differently for git installs than documented] → checked during the
  build against the installed uv before the README states it.

## Open Questions

- The GitHub owner and repository name: they fill in the URLs in the README and in
  `[project.urls]`, and are settled when the user creates the repository (D7 step 3). Until then
  the README uses `<owner>`.
