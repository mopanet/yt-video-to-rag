"""Command-line entry point: `video-to-rag ingest | search | mcp`.

Exit codes: 0 success, 1 runtime failure, 2 usage error. Progress and errors go to stderr,
results to stdout.
"""

import argparse
import logging
import os
import sys
from collections.abc import Callable, Mapping

from .captions import NoCaptions
from .chunking import chunk
from .embedding import E5Embedder, Embedder
from .library import Library, LibraryError, library_path
from .redact import logger, redact
from .urls import InvalidUrl, UnsupportedUrl, video_id
from .youtube import Network, YouTube, YouTubeError, add_network_arguments, network_from

EXIT_OK, EXIT_FAILURE, EXIT_USAGE = 0, 1, 2


class _Stderr(logging.Handler):
    """Writes to whatever sys.stderr is at the time (it may be swapped, e.g. under test)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            print(self.format(record), file=sys.stderr, flush=True)
        except Exception:
            self.handleError(record)


def _configure_logging() -> None:
    if not any(isinstance(h, _Stderr) for h in logger.handlers):
        handler = _Stderr()
        handler.setFormatter(logging.Formatter("video-to-rag: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _fail(message: str, code: int = EXIT_FAILURE) -> int:
    print(f"video-to-rag: error: {redact(message)}", file=sys.stderr)
    return code


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir",
        metavar="DIR",
        default=argparse.SUPPRESS,
        help="library directory (default: $VIDEO_TO_RAG_HOME, else the per-user data directory)",
    )
    parser = argparse.ArgumentParser(
        prog="video-to-rag",
        description="Turn YouTube captions into a searchable, citable passage library.",
        parents=[common],
    )
    commands = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    ingest = commands.add_parser(
        "ingest",
        parents=[common],
        help="add one video's captions to the library",
        description="Fetch one YouTube video's metadata and captions (in the spoken language, "
        "never machine-translated), split them into timestamped passages, embed them locally "
        "and store them in the library. Re-ingesting a video replaces it.",
        epilog="Network: direct by default. Set VIDEO_TO_RAG_PROXY (e.g. "
        "http://user:pass@host:port) to send every YouTube request through a proxy; the proxy "
        "is never accepted as an option.",
    )
    ingest.add_argument("url", help="a YouTube video URL (watch?v=, youtu.be/, shorts/, live/)")
    add_network_arguments(ingest)
    return parser


def _ingest(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    youtube: Callable[[Network], YouTube],
    embedder: Embedder,
) -> int:
    vid = video_id(args.url)
    path = library_path(getattr(args, "data_dir", None), environ)
    existing = Library.open_readonly(path, embedder.model_name)  # fail fast on a model mismatch
    if existing:
        existing.close()

    logger.info("fetching metadata and captions of %s", vid)
    transcript = youtube(network_from(args, environ)).fetch(vid)
    video = transcript.video
    passages = chunk(transcript.segments, embedder.count_tokens)
    if not passages:
        raise NoCaptions("the video's captions contain no speech")
    logger.info("embedding %d passages of %r", len(passages), video.title)
    vectors = embedder.embed_passages([p.text for p in passages])

    created = not path.exists()
    try:
        library = Library.open_for_write(path, embedder.model_name, embedder.dim)
        try:
            library.store(video, passages, vectors)
        finally:
            library.close()
    except BaseException:
        if created:  # a failed first ingest leaves no library behind
            for leftover in path.parent.glob(f"{path.name}*"):
                leftover.unlink(missing_ok=True)
        raise

    print(f'Ingested "{video.title}" — {video.channel_name}')
    print(f"  {len(passages)} passages, captions: {video.caption_kind} ({video.language})")
    print(f"  library: {path}")
    return EXIT_OK


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    youtube: Callable[[Network], YouTube] | None = None,
    embedder: Embedder | None = None,
) -> int:
    environ = os.environ if environ is None else environ
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_:
        return int(exit_.code or 0)
    _configure_logging()

    try:
        if args.command == "ingest":
            return _ingest(args, environ, youtube or YouTube, embedder or E5Embedder())
    except (InvalidUrl, UnsupportedUrl) as error:
        parser.print_usage(sys.stderr)
        return _fail(str(error), EXIT_USAGE)
    except (YouTubeError, NoCaptions, LibraryError) as error:
        return _fail(str(error))
    except OSError as error:
        return _fail(f"{type(error).__name__}: {error}")
    except KeyboardInterrupt:
        return _fail("interrupted; the library was left as it was")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
