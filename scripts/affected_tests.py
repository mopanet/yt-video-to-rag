#!/usr/bin/env python3
"""Print the test files affected by the current change set.

Powers `npm run gates:dev`, so day-to-day work runs ONLY the relevant tests. The full
suite (coverage, build) runs at the integration merge into the base branch, not per slice.

Change set (default): staged + unstaged + untracked files. Set AFFECTED_SCOPE=branch to
also include everything committed on this branch since the merge-base with the base
branch (BASE_BRANCH, then dev, then main; `origin/<b>` before the local `<b>`).

Mapping (import-based): a changed test file (tests/**/test_*.py) selects itself; a changed
`src/video_to_rag/a/b.py` selects every test that imports `video_to_rag.a.b` DIRECTLY
(no transitive closure; the full suite covers the deep blast radius); a changed test helper
(`tests/helpers.py`, imported as `helpers`) selects the tests that import it; a changed
`scripts/x.py` selects `tests/test_x.py`; a change to shared test setup (`tests/conftest.py`,
`tests/fixtures/`) or to the dependencies (`pyproject.toml`, `uv.lock`, `package.json`)
selects every test.

Usage: affected_tests.py          print affected test paths, one per line
       affected_tests.py --run    run `pytest` on them (exit 0 when none)
       affected_tests.py --lint   run `ruff check` + `ruff format --check` on changed .py files
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath

BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
EVERY_TEST = ("tests/conftest.py", "pyproject.toml", "uv.lock", "package.json")


def is_test_path(path: str) -> bool:
    p = PurePosixPath(path)
    return p.parts[:1] == ("tests",) and p.name.startswith("test_") and p.suffix == ".py"


def selects_every_test(path: str) -> bool:
    """Shared test setup and the dependencies can break any test."""
    return path in EVERY_TEST or path.startswith("tests/fixtures/")


def module_name(path: str) -> str | None:
    """Map `src/video_to_rag/a/b.py` to `video_to_rag.a.b`, and a test helper such as
    `tests/helpers.py` to `helpers` (pytest puts tests/ on sys.path); None otherwise."""
    p = PurePosixPath(path)
    if p.suffix != ".py":
        return None
    if p.parent == PurePosixPath("tests") and not is_test_path(path) and p.stem != "conftest":
        return p.stem
    if p.parts[:2] != ("src", "video_to_rag"):
        return None
    parts = list(p.with_suffix("").parts[1:])
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def script_test(path: str) -> str | None:
    """`scripts/x.py` -> `tests/test_x.py` (its test loads it by path, not by import)."""
    p = PurePosixPath(path)
    if p.parent == PurePosixPath("scripts") and p.suffix == ".py":
        return f"tests/test_{p.name}"
    return None


def imported_modules(source: str) -> set[str]:
    """Absolute module names a source imports (whole tree, so function-local imports count).

    `from a import b` yields both `a` and `a.b`, since `b` may be a submodule.
    Unparseable source yields an empty set.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def affected_tests(
    changed: Iterable[str],
    tests: Iterable[str],
    read: Callable[[str], str | None],
) -> list[str]:
    """Sorted test paths affected by `changed`. `read(path)` returns source or None if missing."""
    changed, tests = set(changed), set(tests)
    if any(selects_every_test(c) for c in changed):
        return sorted(t for t in tests if read(t) is not None)
    affected = {c for c in changed if is_test_path(c) and read(c) is not None}
    affected |= {t for c in changed if (t := script_test(c)) in tests and read(t) is not None}
    changed_modules = {m for c in changed if (m := module_name(c))}
    for test in set(tests) - affected:
        source = read(test)
        if source is not None and imported_modules(source) & changed_modules:
            affected.add(test)
    return sorted(affected)


def _git(root: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, OSError):
        return ""
    return result.stdout


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _merge_base(root: str) -> str:
    candidates = [os.environ.get("BASE_BRANCH"), "dev", "main"]
    for branch in candidates:
        if not branch or not BRANCH_RE.match(branch):
            continue
        for ref in (f"origin/{branch}", branch):
            base = _git(root, "merge-base", "HEAD", ref).strip()
            if base:
                return base
    return ""


def changed_files(root: str) -> set[str]:
    outputs = [
        _git(root, "diff", "--name-only"),
        _git(root, "diff", "--name-only", "--cached"),
        _git(root, "ls-files", "--others", "--exclude-standard"),
    ]
    if os.environ.get("AFFECTED_SCOPE") == "branch" and (base := _merge_base(root)):
        outputs.append(_git(root, "diff", "--name-only", f"{base}...HEAD"))
    return {path for out in outputs for path in _lines(out)}


def main(argv: list[str]) -> int:
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    ).stdout.strip()
    changed = changed_files(root)

    if "--lint" in argv:
        files = sorted(c for c in changed if c.endswith(".py") and (Path(root) / c).is_file())
        if not files:
            print("affected-tests: no changed files to lint", file=sys.stderr)
            return 0
        check = subprocess.run(["uv", "run", "ruff", "check", *files], cwd=root)
        fmt = subprocess.run(["uv", "run", "ruff", "format", "--check", *files], cwd=root)
        return check.returncode or fmt.returncode

    def read(path: str) -> str | None:
        try:
            return (Path(root) / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    tests = [t for t in _lines(_git(root, "ls-files", "tests")) if is_test_path(t)]
    files = affected_tests(changed, tests, read)

    if "--run" in argv:
        if not files:
            print("affected-tests: no affected tests — nothing to run", file=sys.stderr)
            return 0
        print(f"affected-tests: running {len(files)} test file(s)", file=sys.stderr)
        return subprocess.run(["uv", "run", "pytest", *files], cwd=root).returncode

    for f in files:
        print(f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
