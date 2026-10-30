"""Tests for scripts/affected_tests.py (the helper behind `npm run gates:dev`)."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "affected_tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


at = _load()


# ---- module_name -------------------------------------------------------------


def test_module_name_maps_a_source_file():
    assert at.module_name("src/video_to_rag/a/b.py") == "video_to_rag.a.b"


def test_module_name_maps_a_package_init_to_the_package():
    assert at.module_name("src/video_to_rag/a/__init__.py") == "video_to_rag.a"
    assert at.module_name("src/video_to_rag/__init__.py") == "video_to_rag"


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_x.py",
        "scripts/affected_tests.py",
        "src/video_to_rag/data.json",
        "src/other/x.py",
    ],
)
def test_module_name_ignores_non_package_files(path):
    assert at.module_name(path) is None


# ---- imported_modules --------------------------------------------------------


def test_imported_modules_covers_import_and_from_forms():
    source = (
        "import video_to_rag.a.b\nfrom video_to_rag.a import c\nfrom video_to_rag.d.e import f\n"
    )
    mods = at.imported_modules(source)
    assert {"video_to_rag.a.b", "video_to_rag.a.c", "video_to_rag.d.e"} <= mods


def test_imported_modules_sees_imports_inside_functions():
    source = "def f():\n    from video_to_rag.lazy import thing\n"
    assert "video_to_rag.lazy" in at.imported_modules(source)


def test_imported_modules_skips_relative_imports():
    assert at.imported_modules("from . import x\nfrom .y import z\n") == set()


def test_imported_modules_returns_empty_for_unparseable_source():
    assert at.imported_modules("def broken(:\n") == set()


# ---- affected_tests ----------------------------------------------------------


def _reader(files):
    return lambda path: files.get(path)


def test_affected_tests_selects_tests_importing_a_changed_module_directly():
    files = {
        "tests/test_foo.py": "from video_to_rag import foo\n",
        "tests/test_bar.py": "import video_to_rag.bar\n",
    }
    result = at.affected_tests(["src/video_to_rag/foo.py"], list(files), _reader(files))
    assert result == ["tests/test_foo.py"]


def test_affected_tests_matches_package_init_imports():
    files = {"tests/test_a.py": "from video_to_rag.a import x\n"}
    result = at.affected_tests(["src/video_to_rag/a/__init__.py"], list(files), _reader(files))
    assert result == ["tests/test_a.py"]


def test_affected_tests_is_not_transitive():
    files = {"tests/test_top.py": "import video_to_rag.top\n"}
    # top may import foo, but the test only imports top: changing foo does not select it.
    result = at.affected_tests(["src/video_to_rag/foo.py"], list(files), _reader(files))
    assert result == []


def test_affected_tests_selects_a_changed_test_that_exists():
    files = {"tests/test_new.py": "x = 1\n"}
    result = at.affected_tests(["tests/test_new.py"], [], _reader(files))
    assert result == ["tests/test_new.py"]


def test_affected_tests_skips_a_deleted_changed_test():
    result = at.affected_tests(["tests/test_gone.py"], [], _reader({}))
    assert result == []


def test_affected_tests_skips_unparseable_and_missing_tests():
    files = {"tests/test_bad.py": "def broken(:\n"}
    tests = ["tests/test_bad.py", "tests/test_missing.py"]
    result = at.affected_tests(["src/video_to_rag/foo.py"], tests, _reader(files))
    assert result == []


def test_affected_tests_selects_tests_using_a_changed_helper():
    files = {
        "tests/test_a.py": "from helpers import FakeEmbedder\n",
        "tests/test_b.py": "x = 1\n",
        "tests/helpers.py": "class FakeEmbedder: ...\n",
    }
    result = at.affected_tests(
        ["tests/helpers.py"], ["tests/test_a.py", "tests/test_b.py"], _reader(files)
    )
    assert result == ["tests/test_a.py"]


@pytest.mark.parametrize(
    "changed",
    [
        "tests/conftest.py",
        "tests/fixtures/info_x.json",
        "pyproject.toml",
        "uv.lock",
        "package.json",
    ],
)
def test_affected_tests_runs_everything_for_shared_setup_and_dependencies(changed):
    files = {"tests/test_a.py": "import video_to_rag.a\n", "tests/test_b.py": "x = 1\n"}
    assert at.affected_tests([changed], list(files), _reader(files)) == sorted(files)


def test_affected_tests_selects_the_test_of_a_changed_script():
    files = {"tests/test_affected_tests.py": "SCRIPT = 'scripts/affected_tests.py'\n"}
    result = at.affected_tests(["scripts/affected_tests.py"], list(files), _reader(files))
    assert result == ["tests/test_affected_tests.py"]


def test_affected_tests_output_is_sorted_and_deduplicated():
    files = {
        "tests/test_b.py": "import video_to_rag.foo\n",
        "tests/test_a.py": "import video_to_rag.foo\n",
    }
    changed = ["src/video_to_rag/foo.py", "tests/test_b.py"]
    result = at.affected_tests(changed, ["tests/test_b.py", "tests/test_a.py"], _reader(files))
    assert result == ["tests/test_a.py", "tests/test_b.py"]


# ---- end to end in a temporary git repo --------------------------------------


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _write(repo, rel, text):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _write(tmp_path, "src/video_to_rag/__init__.py", "")
    _write(tmp_path, "src/video_to_rag/foo.py", "X = 1\n")
    _write(tmp_path, "tests/test_foo.py", "from video_to_rag import foo\n")
    _write(tmp_path, "tests/test_other.py", "import video_to_rag\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def _run(repo, *args, **env):
    full_env = {k: v for k, v in os.environ.items() if k not in ("AFFECTED_SCOPE", "BASE_BRANCH")}
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        env=full_env,
        capture_output=True,
        text=True,
    )


def test_e2e_modified_source_selects_only_its_test(repo):
    _write(repo, "src/video_to_rag/foo.py", "X = 2\n")
    result = _run(repo)
    assert result.returncode == 0
    assert result.stdout == "tests/test_foo.py\n"


def test_e2e_clean_tree_selects_nothing(repo):
    assert _run(repo).stdout == ""


def test_e2e_untracked_test_selects_itself(repo):
    _write(repo, "tests/test_brand_new.py", "def test_ok():\n    assert True\n")
    assert _run(repo).stdout == "tests/test_brand_new.py\n"


def test_e2e_branch_scope_picks_up_committed_changes(repo):
    _git(repo, "checkout", "-b", "feat/x")
    _write(repo, "src/video_to_rag/foo.py", "X = 3\n")
    _git(repo, "commit", "-am", "change foo")
    assert _run(repo).stdout == ""
    assert _run(repo, AFFECTED_SCOPE="branch").stdout == "tests/test_foo.py\n"


def test_e2e_run_with_nothing_affected_exits_zero(repo):
    result = _run(repo, "--run")
    assert result.returncode == 0
    assert "affected-tests: no affected tests — nothing to run" in result.stderr


def test_e2e_lint_with_no_changes_exits_zero(repo):
    result = _run(repo, "--lint")
    assert result.returncode == 0
    assert "affected-tests: no changed files to lint" in result.stderr
