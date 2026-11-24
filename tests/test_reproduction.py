"""#103: a reproduction is recorded by a script, and the script runs nothing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c
import reproduction

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "reproduction.py"
KEY = "k" * 16


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "sync.py").write_text("def sync():\n    pass\n")
    (repo / "tests" / "test_sync.py").write_text("def test_sync():\n    assert False\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    out = repo / c.OUTPUT_DIRNAME
    out.mkdir()
    (out / "report.json").write_text(json.dumps({
        "schema": c.REPORT_SCHEMA_VERSION,
        "findings": [{"id": "FR-001", "key": KEY, "location": {"file": "src/sync.py"},
                      "content_hash": c.sha256_file(repo / "src" / "sync.py")}],
        "refuted": []}))
    return repo


def _record(repo: Path, **kw):
    args = {"key": KEY, "status": "fails_as_predicted", "test": "tests/test_sync.py",
            "command": "pytest tests/test_sync.py -q", **kw}
    return reproduction.record(repo, args["key"], args["status"], args["test"], args["command"])


@pytest.mark.parametrize("status", ["fails_as_predicted", "passes", "blocked"])
def test_each_status_is_recorded(repo, status):
    rec = _record(repo, status=status)
    stored = json.loads((repo / ".thunderstruck" / "reproductions" / f"{KEY}.json").read_text())
    assert stored == rec
    assert stored["schema"] == reproduction.SCHEMA == "thunderstruck.reproduction/v1"
    assert stored["status"] == status
    assert stored["key"] == KEY


def test_the_hash_the_head_and_the_finding_hash_are_stored(repo):
    rec = _record(repo)
    assert rec["test"] == {"path": "tests/test_sync.py",
                           "sha256": c.sha256_file(repo / "tests" / "test_sync.py")}
    assert rec["head"] == _git(repo, "rev-parse", "HEAD")
    assert rec["finding_hash"] == c.sha256_file(repo / "src" / "sync.py")
    assert rec["command"] == "pytest tests/test_sync.py -q"
    assert rec["recorded_at"].endswith("+00:00")


def test_a_new_run_replaces_the_record(repo):
    _record(repo, status="passes")
    _record(repo, status="blocked")
    files = sorted((repo / ".thunderstruck" / "reproductions").iterdir())
    assert [p.name for p in files] == [f"{KEY}.json"]
    assert json.loads(files[0].read_text())["status"] == "blocked"


@pytest.mark.parametrize("change, why", [
    ({"key": "nope"}, "not a finding"),
    ({"status": "fixed"}, "status"),
    ({"test": "../outside.py"}, "climbs out"),
    ({"test": "/etc/passwd"}, "absolute"),
    ({"test": "tests/missing.py"}, "missing"),
    ({"test": "tests"}, "not a regular file"),
    ({"command": "x" * 301}, "300"),
    ({"command": ""}, "command"),
])
def test_refusals(repo, change, why):
    with pytest.raises(c.ThunderstruckError, match=why):
        _record(repo, **change)
    assert not (repo / ".thunderstruck" / "reproductions").exists()


def test_a_symlinked_test_is_refused(repo):
    (repo / "tests" / "link.py").symlink_to(repo / "tests" / "test_sync.py")
    with pytest.raises(c.ThunderstruckError, match="symbolic link"):
        _record(repo, test="tests/link.py")


def test_a_test_behind_a_symlinked_directory_is_refused(repo, tmp_path):
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "t.py").write_text("x = 1\n")
    (repo / "outside").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(c.ThunderstruckError, match="symbolic link"):
        _record(repo, test="outside/t.py")


def test_no_report_is_refused(repo):
    (repo / ".thunderstruck" / "report.json").unlink()
    with pytest.raises(c.ThunderstruckError, match="report.json"):
        _record(repo)


def test_the_cli_records_and_shows(repo):
    proc = subprocess.run([sys.executable, str(SCRIPT), "record", "--repo", str(repo), "--key", KEY,
                           "--status", "passes", "--test", "tests/test_sync.py",
                           "--command", "pytest -q"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    shown = subprocess.run([sys.executable, str(SCRIPT), "show", "--repo", str(repo), "--key", KEY],
                           capture_output=True, text=True)
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout)["status"] == "passes"


def test_the_cli_refuses_with_exit_1_and_the_reason(repo):
    proc = subprocess.run([sys.executable, str(SCRIPT), "record", "--repo", str(repo), "--key", "nope",
                           "--status", "passes", "--test", "tests/test_sync.py",
                           "--command", "pytest -q"], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "not a finding" in proc.stderr
    shown = subprocess.run([sys.executable, str(SCRIPT), "show", "--repo", str(repo), "--key", "nope"],
                           capture_output=True, text=True)
    assert shown.returncode == 1
    assert "no reproduction recorded" in shown.stderr


def test_an_unwritable_directory_is_exit_1_with_the_reason(repo):
    (repo / ".thunderstruck" / "reproductions").write_text("a file, not a directory")
    proc = subprocess.run([sys.executable, str(SCRIPT), "record", "--repo", str(repo), "--key", KEY,
                           "--status", "passes", "--test", "tests/test_sync.py",
                           "--command", "pytest -q"], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "cannot write" in proc.stderr


def test_recording_never_runs_the_test_or_imports_the_repository(repo, tmp_path):
    """Spec §5: a trapped test file and conftest.py would leave a sentinel if run or imported."""
    sentinels = tmp_path / "sentinels"
    sentinels.mkdir()
    for rel in ("tests/conftest.py", "tests/test_sync.py", "conftest.py", "sitecustomize.py"):
        (repo / rel).write_text(f"import pathlib; pathlib.Path({str(sentinels)!r}, {rel!r}.replace('/', '_')).touch()\n")
    proc = subprocess.run([sys.executable, str(SCRIPT), "record", "--repo", str(repo), "--key", KEY,
                           "--status", "fails_as_predicted", "--test", "tests/test_sync.py",
                           "--command", "pytest tests/test_sync.py -q"],
                          capture_output=True, text=True, cwd=str(repo))
    assert proc.returncode == 0, proc.stderr
    assert sorted(p.name for p in sentinels.iterdir()) == []
