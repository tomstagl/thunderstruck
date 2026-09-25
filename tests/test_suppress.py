"""#19 AC-13: profile [[suppress]] rules drop matching detector hits before
scoring and bundling, always with a reason, and always visibly."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import _common as c

RULE = {"detector": "S06-ts-single-queue-no-priority", "path": "src/sync/*.ts",
        "reason": "the scheduler is single-tenant (replicas: 1)"}


def test_double_star_crosses_directories_and_single_star_does_not():
    rx = c.path_glob_to_re("src/**/batch/*.java")
    assert rx.match("src/main/java/a/batch/X.java")
    assert rx.match("src/batch/X.java")
    assert not rx.match("src/batch/sub/X.java")
    assert not c.path_glob_to_re("src/*.ts").match("src/a/b.ts")


def test_rule_without_a_reason_is_ignored_with_a_warning():
    rules, warnings = c.load_suppressions({"suppress": [{"detector": "S16", "path": "*.java"}]})
    assert rules == []
    assert len(warnings) == 1 and "has no reason" in warnings[0]


def test_malformed_rules_are_warned_about_never_fatal():
    rules, warnings = c.load_suppressions({"suppress": [
        "not a table", {"path": "*.ts", "reason": "r"}, {"detector": "S06", "reason": "r"},
        {"detector": "S06", "path": "*.ts", "reason": "  "}, dict(RULE)]})
    assert [r.detector for r in rules] == ["S06-ts-single-queue-no-priority"]
    assert len(warnings) == 4


def test_no_profile_section_means_no_rules():
    assert c.load_suppressions({}) == ([], [])
    rules, warnings = c.load_suppressions({"suppress": {"detector": "x"}})
    assert rules == [] and warnings


def test_a_rule_matches_by_detector_or_pattern_id():
    rules, _ = c.load_suppressions({"suppress": [
        {"detector": "S06", "path": "src/**", "reason": "r"}]})
    hit = {"detector_id": "S06-ts-single-queue-no-priority", "pattern_id": "S06",
           "file": "src/sync/scheduler.ts"}
    assert rules[0].matches(hit["detector_id"], hit["pattern_id"], hit["file"])
    assert not rules[0].matches("S07-ts-x", "S07", hit["file"])
    assert not rules[0].matches(hit["detector_id"], "S06", "lib/scheduler.ts")


def _run(script: str, repo: Path, plugin_root: Path, *extra: str):
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / script),
                           "--repo", str(repo), *extra], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_suppressed_hits_never_rank_and_are_listed(scanned_copy, plugin_root):
    (scanned_copy / c.PROFILE_FILENAME).write_text(
        "[[suppress]]\n"
        f'detector = "{RULE["detector"]}"\npath = "{RULE["path"]}"\nreason = "{RULE["reason"]}"\n'
        "\n[[suppress]]\n"
        'detector = "S01"\npath = "**/*.ts"\n')
    _run("signals.py", scanned_copy, plugin_root, "--top", "8", "--since", "24m")
    data = json.loads((scanned_copy / ".thunderstruck" / "hotspots.json").read_text())

    sched = next(h for h in data["hotspots"] if h["file"] == "src/sync/scheduler.ts")
    assert "S06" not in {h["pattern_id"] for h in sched["detector_hits"]}
    assert "S06" not in sched["stability"]["patterns"]
    assert data["suppressed"] == [dict(RULE, hits=1)]
    assert any("has no reason" in w for w in data["warnings"])

    _run("report.py", scanned_copy, plugin_root)
    report = (scanned_copy / ".thunderstruck" / "report.md").read_text()
    assert "Suppressed leads" in report
    assert RULE["reason"] in report


def test_calibrate_ignores_suppressions(scanned_copy, plugin_root):
    (scanned_copy / c.PROFILE_FILENAME).write_text(
        '[[suppress]]\ndetector = "S06"\npath = "**"\nreason = "everything"\n')
    proc = subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "calibrate.py"), "--repo",
         str(scanned_copy), "--lang", "typescript", "--patterns", "S06"],
        capture_output=True, text=True)
    assert proc.returncode == 0
    assert "S06-ts-single-queue-no-priority\tsrc/sync/scheduler.ts:1" in proc.stdout
