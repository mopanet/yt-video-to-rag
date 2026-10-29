# Tasks

Every spec scenario gets a test first (RED where the behavior is new), then the minimal code to
pass it (GREEN). Iterate with `npm run gates:dev`; the full `npm run gates` runs once in group 6.

## 1. Base

- [x] 1.1 Keep `feat/packaging` stacked on `feat/video-search-skeleton` (design D7: slice 1 is
  merged through its own pull request after the user's review, never locally); verify
  `git merge-base --is-ancestor feat/video-search-skeleton HEAD` succeeds

## 2. Install smoke test (`tests/test_installation.py`)

- [x] 2.1 Register the `install` pytest marker in `pyproject.toml`; write the session fixture of
  design D4 (wheel built into a temp dir, `uv tool install` with temp `UV_TOOL_DIR` /
  `UV_TOOL_BIN_DIR`, empty temp `XDG_DATA_HOME` / `XDG_CACHE_HOME`, working directory outside the
  repo) and the tests for spec *Standalone installation* (help lists the three commands; empty
  search outside the repo exits 0 with the empty-library message, creates no library file and
  leaves the model cache empty); verify `uv run pytest -m install` passes, also with
  `UV_LOCKED=1` set as CI sets it
- [x] 2.2 Tests for spec *Installed MCP server* (an `mcp` client from the project environment starts
  the installed `video-to-rag mcp --data-dir <empty dir>`, lists exactly `search`, and the model
  cache is still empty afterwards); verify `uv run pytest -m install -k mcp` passes

## 3. Version (`cli.py`, `pyproject.toml`)

- [x] 3.1 Tests first for spec *Version reporting*: in-process `main(["--version"])` prints
  `video-to-rag <version from pyproject.toml>` and returns 0 with no library or model cache entry
  created, and the installed binary prints the same; verify they fail (RED), implement design D2,
  verify `uv run pytest tests/test_cli_version.py` and `uv run pytest -m install -k version` pass
- [x] 3.2 Set the version to `0.1.0` in `pyproject.toml` and re-lock; verify
  `uv run video-to-rag --version` prints `video-to-rag 0.1.0` and the version tests still pass

## 4. Dependency bounds (`pyproject.toml`, `uv.lock`)

- [x] 4.1 Add the upper bounds of design D3 (yt-dlp stays unbounded) and run `uv lock`; verify the
  lock diff changes no resolved version and `uv run pytest -m install` still passes

## 5. User documentation (`README.md`, `CHANGELOG.md`)

- [x] 5.1 Check how `uv tool upgrade` treats a git install against the installed uv, using a
  `git+file://` install of this repository in a temp tool dir (unpinned → picks up a new commit;
  tag-pinned → needs `uv tool install --force …@<new tag>`); verify the behavior that the README
  will state is the observed one
- [x] 5.2 Restructure `README.md` per design D6 (what, requirements, install, use, data
  locations, upgrade, uninstall, development) with `<owner>` in the URLs; verify every documented
  option exists in `video-to-rag <command> --help`, and that the install, `--version`, upgrade
  and uninstall commands, run against a local build in a temp tool dir, behave as written
- [x] 5.3 Add the MCP client section per design D5 (generic JSON with the absolute command path,
  Claude Code command, ingest-first and cold-start notes); verify the JSON parses and its command
  and args are exactly what the smoke test in 2.2 starts
- [x] 5.4 Add the `0.1.0` entry to `CHANGELOG.md` (slice-1 features plus installation, date set
  at tagging); verify it follows the Keep a Changelog layout already in the file

## 6. Integration (before GATE 2)

- [ ] 6.1 Run the full `npm run gates` (lint, all tests including `model` and `install`, gitleaks,
  `openspec validate --all`); verify everything is green
- [ ] 6.2 Pre-publication review: `/review` + `/codex`, then `/cso` including every tracked file
  checked for personal data, plus `gitleaks git` over the full history; verify no open finding
  and report the result for GATE 2

## 7. Publication (after GATE 2: the user approves, creates the public repository, runs `pat-set`)

- [ ] 7.1 Replace `<owner>` in `README.md`, add `authors` and `[project.urls]` (repository,
  issues, changelog) to `pyproject.toml`; verify the built wheel's metadata lists the URLs
- [ ] 7.2 Push `main`, `feat/video-search-skeleton` and this branch; open pull request 1
  (`feat/video-search-skeleton` → `main`) and pull request 2 (this branch →
  `feat/video-search-skeleton`); verify CI (`gates.yml`) is green on both, the first CI runs of
  the project
- [ ] 7.3 After the user's review merges pull request 1, retarget pull request 2 to `main`, merge
  it, set the release date in `CHANGELOG.md`, tag `v0.1.0` on `main` and push the tag; verify that
  `uv tool install git+https://github.com/<owner>/video-to-rag@v0.1.0` into a temp tool dir
  prints `video-to-rag 0.1.0` for `--version`

## Workflow follow-up

- Verify phase (the user): install by hand on the host with the README's command, run one ingest,
  register the MCP server in the Personal OS and ask a question there.
- `/codex` may not start in the devcontainer (its sandbox fails there); if so, the review report
  says so instead of skipping silently.
- `/opsx:archive` after the merge, so `installation` lands in `openspec/specs/`.
