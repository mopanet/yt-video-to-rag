"""Specs *Standalone installation*, *Version reporting* and *Installed MCP server*, run against
the package built from this repository and installed the way a user installs it.

Needs network access to PyPI (about a minute on a cold uv cache); deselect it with
`-m "not install"` when offline.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from helpers import project_version
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

REPO = Path(__file__).resolve().parents[1]
PYTHON = "3.12"  # the Python the README's install command names
BUILD_TIMEOUT = 600  # seconds; a stalled PyPI download must fail the test, not hang CI
# A user's shell has none of these; under `uv run` / CI they would leak into the install.
NOT_INHERITED = ("VIRTUAL_ENV", "UV_LOCKED", "UV_FROZEN", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH")

pytestmark = pytest.mark.install


@dataclass
class Installed:
    binary: Path
    work: Path  # working directory outside the repository
    env: dict[str, str]  # empty per-user data and cache directories
    cache: Path

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(self.binary), *args],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def cached_files(self) -> list[Path]:
        return [p for p in self.cache.rglob("*") if p.is_file()]


@pytest.fixture(scope="session")
def installed(tmp_path_factory) -> Installed:
    root = tmp_path_factory.mktemp("installed")
    base = {k: v for k, v in os.environ.items() if k not in NOT_INHERITED}
    uv = shutil.which("uv")
    assert uv, "the install test needs uv on PATH"

    dist = root / "dist"
    build = [uv, "build", "--wheel", "--out-dir", str(dist)]
    subprocess.run(build, cwd=REPO, env=base, check=True, timeout=BUILD_TIMEOUT)
    (wheel,) = dist.glob("*.whl")
    tools = {**base, "UV_TOOL_DIR": str(root / "tools"), "UV_TOOL_BIN_DIR": str(root / "bin")}
    install = [uv, "tool", "install", "--python", PYTHON, str(wheel)]
    subprocess.run(install, cwd=root, env=tools, check=True, timeout=BUILD_TIMEOUT)

    work, data, cache = root / "work", root / "data", root / "cache"
    for directory in (work, data, cache):
        directory.mkdir()
    env = {**base, "XDG_DATA_HOME": str(data), "XDG_CACHE_HOME": str(cache)}
    return Installed(root / "bin" / "video-to-rag", work, env, cache)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --- Standalone installation -------------------------------------------------------------


def test_commands_of_the_installed_tool(installed):
    result = installed.run("--help")
    assert result.returncode == 0, result.stderr
    for command in ("ingest", "search", "mcp"):
        assert command in result.stdout


def test_installed_search_outside_the_repository(installed, tmp_path):
    result = installed.run("search", "focus", "--data-dir", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "library is empty" in result.stdout
    assert "video-to-rag ingest" in result.stdout
    assert list(tmp_path.iterdir()) == []
    assert installed.cached_files() == []


# --- Version reporting -------------------------------------------------------------------


def test_version_of_the_installed_package(installed):
    result = installed.run("--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"video-to-rag {project_version()}\n"


# --- Installed MCP server ----------------------------------------------------------------


@pytest.mark.anyio
async def test_client_connects_to_the_installed_mcp_server(installed, tmp_path):
    server = StdioServerParameters(
        command=str(installed.binary),
        args=["mcp", "--data-dir", str(tmp_path)],
        env=installed.env,
        cwd=installed.work,
    )
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    assert [t.name for t in tools] == ["search"]
    assert installed.cached_files() == []  # startup and listing load no model
