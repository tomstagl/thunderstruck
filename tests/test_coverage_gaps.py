"""#19 AC-1 and AC-2: the report says what it did not look at, and the coverage
table shows how many leads were read and confirmed, not only how many fired."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from build_fixture import isolated_git_env
from test_pipeline import _valid_finding, _validate, _write_finding

LINUX = sys.platform.startswith("linux")


def _git(repo: Path, *args: str) -> str:
    env = isolated_git_env()
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=env).stdout


def _run(plugin_root: Path, script: str, repo: Path, *extra: str) -> None:
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / script),
                           "--repo", str(repo), *extra], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.fixture
def planted(scanned_copy: Path, plugin_root: Path) -> Path:
    (scanned_copy / "mobile").mkdir()
    (scanned_copy / "mobile" / "App.kt").write_text("fun main() {}\n")
    (scanned_copy / "db" / "migrations").mkdir(parents=True)
    (scanned_copy / "db" / "migrations" / "001.py").write_text("up = 1\n")
    if LINUX:
        os.symlink("../client/api.ts", scanned_copy / "src" / "util" / "api-link.ts")
    _git(scanned_copy, "add", "-A", "mobile", "db", "src")
    _git(scanned_copy, "commit", "-q", "-m", "chore: plant files")
    _run(plugin_root, "signals.py", scanned_copy, "--top", "8", "--since", "24m")
    return scanned_copy


def _data(repo: Path) -> dict:
    return json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())


def test_every_tracked_file_lands_in_exactly_one_bucket(planted):
    gaps = _data(planted)["coverage_gaps"]
    tracked = len(_git(planted, "ls-files", "-z").split("\0")) - 1
    assert gaps["tracked"] == tracked
    assert gaps["unsupported"][".kt"] == 1
    assert gaps["excluded"]["migration"] == 1
    assert gaps["tracked"] == (gaps["considered"] + gaps["unchanged"] + gaps["not_citable"]
                               + sum(gaps["excluded"].values())
                               + sum(gaps["unsupported"].values()))
    assert gaps["considered"] == _data(planted)["counts"]["files_considered"]
    if LINUX:
        assert gaps["not_citable"] == 1, "a tracked symlink is not citable"
    assert list(gaps["excluded"]) == sorted(gaps["excluded"])


def test_unsupported_languages_are_named_in_a_warning(planted):
    warnings = _data(planted)["warnings"]
    assert any(w.startswith("1 Kotlin files (.kt) were not scanned") for w in warnings), warnings


def test_unsupported_extensions_fold_past_eight(tmp_path, scanned_copy, plugin_root):
    for n in range(10):
        (scanned_copy / f"f{n}.x{n}").write_text("x\n")
    _git(scanned_copy, "add", "-A", ".")
    _git(scanned_copy, "commit", "-q", "-m", "chore: many kinds")
    _run(plugin_root, "signals.py", scanned_copy, "--top", "8", "--since", "24m")
    unsupported = _data(scanned_copy)["coverage_gaps"]["unsupported"]
    assert len(unsupported) <= 9 and "other" in unsupported


def test_report_has_a_not_scanned_section(planted, plugin_root):
    _run(plugin_root, "report.py", planted)
    report = (planted / ".thunderstruck" / "report.md").read_text()
    section = report.split("## Not scanned", 1)[1].split("\n## ", 1)[0]
    assert "`.kt`" in section and "migration" in section
    assert report.index("## Not scanned") < report.index("## Pattern coverage")


def test_coverage_table_shows_leads_read_and_confirmed(scanned_copy, plugin_root):
    data = _data(scanned_copy)
    releases = next(h for h in data["hotspots"] if h["file"] == "src/client/releases.ts")
    s02 = next(h for h in releases["detector_hits"] if h["pattern_id"] == "S02")
    hid, doc = _valid_finding(scanned_copy, data)
    doc["findings"][0]["evidence"] = [e for e in doc["findings"][0]["evidence"]
                                      if e["type"] != "detector"]
    doc["findings"][0]["evidence"].append({"type": "detector", "ref": s02["ref"], "note": "x"})
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    _run(plugin_root, "report.py", scanned_copy)
    report = (scanned_copy / ".thunderstruck" / "report.md").read_text()
    assert ("| ID | Pattern | Tier | Files with an unconfirmed lead | Leads read "
            "| Leads confirmed | Findings |") in report
    assert "does not mean the pattern is present" in report
    row = next(ln for ln in report.splitlines() if ln.startswith("| `S02`"))
    files = data["pattern_coverage"]["S02"]["files"]
    assert row.split("|")[4].strip() == str(files - 1), "the confirmed file is not unconfirmed"
    payload = json.loads((scanned_copy / ".thunderstruck" / "report.json").read_text())
    # only hotspots an investigator read count; the rest have no findings file
    # and are Incomplete
    read = sum(1 for h in data["hotspots"] if h["id"] == hid
               for hit in h["detector_hits"] if hit["pattern_id"] == "S02")
    assert payload["lead_precision"]["S02"] == {"read": read, "confirmed": 1}
