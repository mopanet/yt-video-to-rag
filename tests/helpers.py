"""Shared test helpers (imported by test modules; pytest puts `tests/` on sys.path)."""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
