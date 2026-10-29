"""Spec *Version reporting*, in-process (test_installation.py checks the installed binary)."""

import tomllib
from pathlib import Path

from video_to_rag.cli import main

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def project_version() -> str:
    return tomllib.loads(PYPROJECT.read_text())["project"]["version"]


def test_version_of_the_package(capsys):
    assert main(["--version"], environ={}) == 0
    assert capsys.readouterr().out == f"video-to-rag {project_version()}\n"


def test_version_with_nothing_set_up(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert main(["--version"], environ={"VIDEO_TO_RAG_HOME": str(tmp_path / "library")}) == 0
    assert list(tmp_path.iterdir()) == []
