# Proposal

## Why

video-to-rag only runs from a development checkout today (`uv run` inside the repository, in the
devcontainer), so its library lives inside the container and is lost when the container is
rebuilt. The user wants it as a public GitHub project that they install by hand on their own
machine, where the library persists in the per-user data directory and their Personal OS (running
on the same machine) can use it as an MCP server. This pulls the packaging and GitHub-repository
part of the original slice 4 forward; nothing else from slice 4 comes with it.

## What Changes

- **Installable command-line tool**: `uv tool install git+https://github.com/<owner>/video-to-rag`
  (latest `main`) or `…@v0.1.0` (a release tag) puts `video-to-rag` on the user's `PATH` with
  `ingest`, `search` and `mcp`, without a checkout. The package metadata already declares the
  console script; this change makes it a tested, documented promise.
- **`video-to-rag --version`** prints the installed version, so the user can tell what they run and
  whether an upgrade happened.
- **First release, 0.1.0**: the version in `pyproject.toml`, a `CHANGELOG.md` entry covering what
  slice 1 delivered plus installation, and a `v0.1.0` git tag after the merge.
- **Dependency bounds for installs**: an installed tool resolves its dependencies fresh, not from
  `uv.lock`, so the libraries whose next major (or, for 0.x, minor) release could break us get an
  upper bound. `yt-dlp` deliberately stays unbounded: it has to follow YouTube's changes.
- **Install smoke test** (local full gate and CI): build the package, install it into an isolated
  tool environment exactly as a user would, and check `--version`, `--help`, a search on an empty
  library, and an MCP client connecting to the installed `video-to-rag mcp` and seeing the
  `search` tool. None of this downloads the embedding model.
- **User-facing README**: what the tool does, requirements (uv; deno or node for YouTube),
  install, upgrade, uninstall (and which data and cache directories stay behind), everyday use,
  and registering the MCP server in any MCP client (generic JSON configuration, plus the Claude
  Code command). The development workflow moves below it.
- **Public GitHub repository**: the user creates it; the code is pushed only after the
  pre-publication checks pass and the user approves going public (GATE 2). The first pull request
  also proves that `.github/workflows/gates.yml` runs green (moved here from slice 1).

### Out of scope

- Publishing to PyPI (installation is from the GitHub repository only).
- The rest of slice 4: config file, re-index on an embedding-model change, export.
- Wiring the MCP server into the Personal OS: the user does that; this change documents how.
- Windows support and CI on macOS: Linux is tested, macOS is expected to work but untested.

## Capabilities

### New Capabilities

- `installation`: how video-to-rag is installed, identified by version, upgraded and removed as a
  standalone command-line tool, and how an installed copy serves an MCP client.

### Modified Capabilities

None. (The slice-1 capabilities are not yet archived into `openspec/specs/`; their behavior does
not change.)

## Impact

- **Code**: `src/video_to_rag/cli.py` (`--version`), `pyproject.toml` (version 0.1.0, dependency
  upper bounds, project URLs and author), `uv.lock` (re-locked), new install smoke test and a
  pytest marker for it, `package.json` / CI only if the marker needs wiring.
- **Docs**: `README.md` restructured for users first; `CHANGELOG.md` 0.1.0 entry.
- **Systems**: a new public GitHub repository (created by the user; a repo-scoped token for the
  container via `pat-set`); CI runs on its pull requests.
- **Order**: builds on `feat/video-search-skeleton`, which must be finished and merged into `main`
  first; this branch is then rebased onto `main`.
