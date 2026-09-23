"""run_command is the only place thunderstruck executes a user's command.
It must never hang, never read the terminal, and never involve a shell."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

import context

FAKE = Path(__file__).resolve().parent / "fixtures" / "fake_catalog.py"
MAIN = "component:default/fixture-app"
ARGV = [sys.executable, str(FAKE), "{entity_ref}"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    import os
    for var in [v for v in os.environ if v.startswith("FAKE_CATALOG_")]:
        monkeypatch.delenv(var)


def test_prints_entity_json(tmp_path):
    got = context.run_command(ARGV, MAIN, 10, tmp_path)
    assert got.error is None
    assert got.doc["metadata"]["name"] == "fixture-app"
    assert '"fixture-app"' in got.raw


def test_entity_ref_is_one_argument_and_no_shell_runs(tmp_path, monkeypatch):
    marker = tmp_path / "calls.txt"
    monkeypatch.setenv("FAKE_CATALOG_MARKER", str(marker))
    context.run_command(ARGV, "component:default/a;touch pwned", 10, tmp_path)
    assert marker.read_text().strip() == "component:default/a;touch pwned"
    assert not (tmp_path / "pwned").exists()


@pytest.mark.parametrize("var,expected", [
    ("FAKE_CATALOG_FAIL_REFS", "exited 3"),
    ("FAKE_CATALOG_BADJSON_REFS", "did not print JSON"),
])
def test_failures_become_errors(tmp_path, monkeypatch, var, expected):
    monkeypatch.setenv(var, MAIN)
    got = context.run_command(ARGV, MAIN, 10, tmp_path)
    assert got.doc is None and expected in got.error


def test_non_object_json_is_an_error(tmp_path):
    got = context.run_command([sys.executable, "-c", "print('[1, 2]')"], MAIN, 10, tmp_path)
    assert "not an object" in got.error


def test_missing_binary_is_an_error(tmp_path):
    got = context.run_command(["definitely-not-a-real-cli-xyz", "{entity_ref}"],
                              MAIN, 10, tmp_path)
    assert "could not start" in got.error


def test_timeout_returns_promptly(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_TIMEOUT_REFS", MAIN)
    start = time.monotonic()
    got = context.run_command(ARGV, MAIN, 1, tmp_path)
    assert "timed out" in got.error
    assert time.monotonic() - start < 5


def test_timeout_kills_helpers_that_hold_stdout(tmp_path, monkeypatch):
    """A login helper that inherits stdout would keep communicate() waiting
    long after the CLI itself was killed."""
    monkeypatch.setenv("FAKE_CATALOG_GRANDCHILD_REFS", MAIN)
    start = time.monotonic()
    got = context.run_command(ARGV, MAIN, 1, tmp_path)
    assert "timed out" in got.error
    assert time.monotonic() - start < 5


def test_stdin_is_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_READ_STDIN", "1")
    start = time.monotonic()
    got = context.run_command(ARGV, MAIN, 10, tmp_path)
    assert got.error is None and time.monotonic() - start < 5


def test_exhausted_budget_runs_nothing(tmp_path, monkeypatch):
    marker = tmp_path / "calls.txt"
    monkeypatch.setenv("FAKE_CATALOG_MARKER", str(marker))
    got = context.run_command(ARGV, MAIN, 0, tmp_path)
    assert got.error == context.BUDGET_EXHAUSTED and not marker.exists()


def test_preflight_mode_checks_the_exit_code_only(tmp_path, monkeypatch):
    pre = [sys.executable, str(FAKE), "--preflight"]
    assert context.run_command(pre, MAIN, 10, tmp_path, want_json=False).error is None
    monkeypatch.setenv("FAKE_CATALOG_AUTH", "expired")
    assert "exited 1" in context.run_command(pre, MAIN, 10, tmp_path, want_json=False).error


def test_errors_name_the_command_not_its_path(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_FAIL_REFS", MAIN)
    got = context.run_command(ARGV, MAIN, 10, tmp_path)
    assert str(Path(sys.executable).parent) not in got.error
