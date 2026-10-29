# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-29

### Added
- `video-to-rag ingest <video-url>`: one YouTube video's captions in the spoken language
  (uploader-made first, then automatic, never machine-translated) become timestamped passages,
  embedded locally (multilingual-e5-large) and stored in one SQLite library. Re-ingesting a video
  replaces it.
- Network modes for ingest: direct, `--cookies-from-browser`, `--cookies` and the
  `VIDEO_TO_RAG_PROXY` proxy. Credentials are never stored or shown; a YouTube bot check gives an
  error that names the remedies.
- `video-to-rag search`: hybrid search (multilingual vectors + full text) in any language, with
  a channel filter and a limit. Every hit has title, channel, date, time range, a timestamped
  `youtu.be` link and the original passage text.
- `video-to-rag mcp`: a stdio MCP server with one tool, `search`. Read-only, never contacts
  YouTube, and tells the client to answer with timestamped citations and the original quotes.
- Installation as a command-line tool from the GitHub repository (`uv tool install`), and
  `video-to-rag --version`.
