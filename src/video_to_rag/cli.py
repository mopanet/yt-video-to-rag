"""Command-line entry point: `video-to-rag ingest | search | mcp`."""

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-to-rag",
        description="Turn YouTube captions into a searchable, citable passage library.",
    )
    parser.add_subparsers(dest="command", metavar="<command>")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
