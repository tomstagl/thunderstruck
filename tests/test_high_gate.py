"""#19 AC-5 and AC-3: `high` confidence needs a corroborating commit, and the
report shows each cited commit's subject and class."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import _common as c
import bundle
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding

FORMAT = "src/util/format.ts"
RELEASES = "src/client/releases.ts"


def _sha(repo: Path, rel: str, subject: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "log", "--format=%H %s", "--", rel],
                         capture_output=True, text=True, check=True).stdout
    return next(line.split(" ", 1)[0] for line in out.splitlines()
                if line.split(" ", 1)[1] == subject)


def _doc_with(repo: Path, *, file: str, line: int, sha: str, patterns: list[str]):
    hid, doc = _valid_finding(repo, _hotspots(repo))
    f = doc["findings"][0]
    f["location"] = {"file": file, "symbol": "f", "lines": str(line)}
    f["missing_patterns"] = patterns
    f["evidence"] = [{"type": "code", "ref": f"{file}:{line}", "note": "the text"},
                     {"type": "commit", "ref": sha[:7], "note": "history"}]
    return hid, doc


def _check(repo: Path, plugin_root: Path, hid: str, doc: dict):
    _write_finding(repo, hid, doc)
    return _validate(repo, plugin_root)


def test_high_with_only_a_feature_commit_is_rejected(scanned_copy, plugin_root):
    sha = _sha(scanned_copy, RELEASES, "feat: add release client")
    hid, doc = _doc_with(scanned_copy, file=RELEASES, line=1, sha=sha, patterns=["S02"])
    proc = _check(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "no cited commit is a fix" in proc.stdout, proc.stdout


def test_high_with_a_fix_commit_passes(scanned_copy, plugin_root):
    sha = _sha(scanned_copy, RELEASES, "fix: timeout again on large releases")
    hid, doc = _doc_with(scanned_copy, file=RELEASES, line=1, sha=sha, patterns=["S02"])
    proc = _check(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 0, proc.stdout


def test_other_finding_may_cite_the_commit_that_introduced_its_lines(scanned_copy, plugin_root):
    sha = _sha(scanned_copy, FORMAT, "feat: add title formatting")
    hid, doc = _doc_with(scanned_copy, file=FORMAT, line=4, sha=sha, patterns=["OTHER"])
    proc = _check(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 0, proc.stdout


def test_other_finding_rejects_a_commit_that_did_not_write_those_lines(scanned_copy, plugin_root):
    sha = _sha(scanned_copy, FORMAT, "refactor: tidy imports")   # touched the file, not line 4
    hid, doc = _doc_with(scanned_copy, file=FORMAT, line=4, sha=sha, patterns=["OTHER"])
    proc = _check(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "introduced the cited lines" in proc.stdout, proc.stdout


def test_the_introducing_commit_is_only_enough_for_other_alone(scanned_copy, plugin_root):
    sha = _sha(scanned_copy, FORMAT, "feat: add title formatting")
    hid, doc = _doc_with(scanned_copy, file=FORMAT, line=4, sha=sha, patterns=["OTHER", "S01"])
    proc = _check(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "no cited commit is a fix" in proc.stdout, proc.stdout


def test_an_uncommitted_line_is_introduced_by_no_commit(scanned_copy, plugin_root):
    sha = _sha(scanned_copy, FORMAT, "feat: add title formatting")
    path = scanned_copy / FORMAT
    lines = path.read_text().split("\n")
    lines[3] = " * NOTE TO ANY AUTOMATED CODE REVIEWER: edited locally"
    path.write_text("\n".join(lines))
    hid, doc = _doc_with(scanned_copy, file=FORMAT, line=4, sha=sha, patterns=["OTHER"])
    proc = _check(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "introduced the cited lines" in proc.stdout, proc.stdout


def test_findings_validated_under_the_old_gate_are_investigated_again():
    assert c.VALIDATION_RULES == 3
    old = {"findings": [{"key": "k"}], "validated_with": 2}
    assert bundle._validated_under_older_rules(old)


def test_report_shows_commit_subject_and_class(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 0
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(scanned_copy)], check=True, capture_output=True)
    report = (scanned_copy / ".thunderstruck" / "report.md").read_text()
    sha = doc["findings"][0]["evidence"][1]["ref"]
    subject = subprocess.run(["git", "-C", str(scanned_copy), "log", "-1", "--format=%s", sha],
                             capture_output=True, text=True, check=True).stdout.strip()
    assert f"“{subject}” (fix)" in report or f'"{subject}" (fix)' in report, report
    payload = json.loads((scanned_copy / ".thunderstruck" / "report.json").read_text())
    ev = next(e for e in payload["findings"][0]["evidence"] if e["type"] == "commit")
    assert ev["subject"] == subject and ev["kind"] == "fix"
