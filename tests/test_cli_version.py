"""Spec *Version reporting*, in-process (test_installation.py checks the installed binary)."""

from importlib.metadata import PackageNotFoundError

from helpers import FakeEmbedder, project_version

from video_to_rag import cli
from video_to_rag.cli import main


def test_version_of_the_package(capsys):
    assert main(["--version"], environ={}) == 0
    assert capsys.readouterr().out == f"video-to-rag {project_version()}\n"


def test_version_with_nothing_set_up(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert main(["--version"], environ={"VIDEO_TO_RAG_HOME": str(tmp_path / "library")}) == 0
    assert list(tmp_path.iterdir()) == []


def test_source_tree_without_package_metadata(tmp_path, monkeypatch, capsys):
    """Run from a bare source tree, the version is unknown but every command still works."""

    def not_installed(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(cli, "version", not_installed)
    assert main(["--version"], environ={}) == 0
    assert capsys.readouterr().out == "video-to-rag unknown (not installed)\n"
    argv = ["--data-dir", str(tmp_path), "search", "focus"]
    assert main(argv, environ={}, embedder=FakeEmbedder()) == 0
    assert "library is empty" in capsys.readouterr().out
