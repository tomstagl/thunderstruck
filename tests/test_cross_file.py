"""#19 AC-4: a finding is filed under every file it cites as code evidence, so
the guardrail warns on the file that carries the defect and the report does
not call that file clean."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import _common as c
from test_guardrail import run_hook
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding

RELEASES = "src/client/releases.ts"
WRAPPER = "src/client/retry-wrapper.ts"


def _fix_sha(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%H",
                           "--grep=^fix:", "--", RELEASES],
                          capture_output=True, text=True, check=True).stdout.strip()


def _scan_with_cross_file_finding(repo: Path, plugin_root: Path) -> dict:
    data = _hotspots(repo)
    by_file = {h["file"]: h["id"] for h in data["hotspots"]}
    hid, doc = _valid_finding(repo, data)
    f = doc["findings"][0]
    f["location"] = {"file": RELEASES, "symbol": "fetchRelease", "lines": "1-5"}
    f["evidence"] = [
        {"type": "code", "ref": f"{RELEASES}:11", "note": "loop around withRetry"},
        {"type": "code", "ref": f"./{WRAPPER}:1", "note": "the inner retry layer"},
        {"type": "commit", "ref": _fix_sha(repo), "note": "fix history"}]
    doc["hotspot_id"], doc["file"] = by_file[RELEASES], RELEASES
    _write_finding(repo, by_file[RELEASES], doc)
    _write_finding(repo, by_file[WRAPPER], {"hotspot_id": by_file[WRAPPER], "findings": [],
                                            "notes": "wrapper looks fine on its own"})
    proc = _validate(repo, plugin_root)
    assert proc.returncode == 0, proc.stdout
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(repo)], check=True, capture_output=True)
    return by_file


def test_index_files_the_finding_under_the_cited_file(scanned_copy, plugin_root):
    _scan_with_cross_file_finding(scanned_copy, plugin_root)
    index = json.loads((scanned_copy / ".thunderstruck" / "index.json").read_text())
    primary = index["files"][RELEASES]["findings"][0]
    secondary = index["files"][WRAPPER]
    assert "via" not in primary
    assert secondary["findings"][0]["id"] == primary["id"]
    assert secondary["findings"][0]["via"] == "evidence"
    assert secondary["findings"][0]["anchor"] == RELEASES
    assert secondary["content_hash"] == c.sha256_file(scanned_copy / WRAPPER)
    assert index["files"][RELEASES]["content_hash"] == c.sha256_file(scanned_copy / RELEASES)
    assert set(index["files"]) == {RELEASES, WRAPPER}, "one entry per canonical path"


def test_guardrail_warns_on_the_cited_file(scanned_copy, plugin_root):
    _scan_with_cross_file_finding(scanned_copy, plugin_root)
    context = json.loads(run_hook(scanned_copy, WRAPPER).stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert f"cited as evidence; finding is on {RELEASES}" in context
    assert "changed since the scan" not in context


def test_each_entry_goes_stale_with_its_own_file(scanned_copy, plugin_root):
    _scan_with_cross_file_finding(scanned_copy, plugin_root)
    with (scanned_copy / WRAPPER).open("a") as fh:
        fh.write("// edited\n")
    wrapper = json.loads(run_hook(scanned_copy, WRAPPER, session="a").stdout)
    releases = json.loads(run_hook(scanned_copy, RELEASES, session="a").stdout)
    assert "changed since the scan" in wrapper["hookSpecificOutput"]["additionalContext"]
    assert "changed since the scan" not in releases["hookSpecificOutput"]["additionalContext"]


def test_report_does_not_call_a_cited_hotspot_clean(scanned_copy, plugin_root):
    by_file = _scan_with_cross_file_finding(scanned_copy, plugin_root)
    report = (scanned_copy / ".thunderstruck" / "report.md").read_text()
    clean = report.split("## Hotspots investigated with no finding", 1)[1].split("\n## ", 1)[0]
    line = next(ln for ln in clean.splitlines() if by_file[WRAPPER] in ln)
    assert "no finding of its own; cited as evidence by FR-001" in line
    assert WRAPPER in line


def test_save_finding_strips_model_supplied_evidence_hashes(scanned_copy, plugin_root):
    data = _hotspots(scanned_copy)
    hid, doc = _valid_finding(scanned_copy, data)
    doc["findings"][0]["evidence_hashes"] = {RELEASES: "sha256:forged"}
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / "save_finding.py"),
                           "--repo", str(scanned_copy), "--id", hid],
                          input=json.dumps(doc), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert "evidence_hashes" not in saved["findings"][0]
