"""Dogfood 2026-09-26: two hotspots that call one defective function each
report it. Findings whose code evidence overlaps across hotspots are linked,
never merged (spec §2.5)."""

from __future__ import annotations

import json
import subprocess
import sys

import report
from test_cross_file import RELEASES, WRAPPER
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding


def _f(hid: str, fid: str, *refs: str) -> dict:
    return {"id": fid, "key": f"k-{fid}", "hotspot_id": hid,
            "evidence": [{"type": "code", "ref": r} for r in refs]
            + [{"type": "commit", "ref": "abc1234"}]}


def test_overlapping_ranges_across_hotspots_are_linked():
    a = _f("H02", "FR-007", "a.ts:785-795", "a.ts:1104-1108", "a.ts:753-760")
    b = _f("H05", "FR-011", "page.tsx:151-176", "a.ts:790", "a.ts:1103-1107")
    shared = report.shared_code([a, b])
    assert shared["FR-007"] == [{"id": "FR-011", "key": "k-FR-011",
                                 "refs": ["a.ts:785-795", "a.ts:1104-1108"]}]
    assert shared["FR-011"] == [{"id": "FR-007", "key": "k-FR-007",
                                 "refs": ["a.ts:790", "a.ts:1103-1107"]}]


def test_same_hotspot_adjacent_lines_and_other_files_are_not_linked():
    same = [_f("H01", "FR-001", "a.ts:10-20"), _f("H01", "FR-002", "a.ts:15")]
    adjacent = [_f("H01", "FR-001", "a.ts:10-20"), _f("H02", "FR-002", "a.ts:21-30")]
    other = [_f("H01", "FR-001", "a.ts:10-20"), _f("H02", "FR-002", "b.ts:10-20")]
    detector_only = [_f("H01", "FR-001", "a.ts:10"),
                     {"id": "FR-002", "key": "k", "hotspot_id": "H02",
                      "evidence": [{"type": "detector", "ref": "S01@a.ts:10"}]}]
    for findings in (same, adjacent, other, detector_only):
        assert report.shared_code(findings) == {}


def test_report_links_findings_that_share_code(scanned_copy, plugin_root):
    data = _hotspots(scanned_copy)
    by_file = {h["file"]: h["id"] for h in data["hotspots"]}
    for anchor in (RELEASES, WRAPPER):
        hid, doc = _valid_finding(scanned_copy, data)
        f = doc["findings"][0]
        f["location"] = {"file": anchor, "symbol": "f", "lines": "1"}
        f["confidence"] = "medium"
        f["failure_mode"] = f"Failure seen from {anchor}"
        f["evidence"] = [{"type": "code", "ref": f"{anchor}:1", "note": "own side"},
                         {"type": "code", "ref": f"{WRAPPER}:1-2", "note": "the shared branch"}]
        doc["hotspot_id"], doc["file"] = by_file[anchor], anchor
        _write_finding(scanned_copy, by_file[anchor], doc)
    proc = _validate(scanned_copy, plugin_root)
    assert proc.returncode == 0, proc.stdout
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(scanned_copy)], check=True, capture_output=True)
    out = scanned_copy / ".thunderstruck"
    findings = json.loads((out / "report.json").read_text())["findings"]
    ids = {f["location"]["file"]: f["id"] for f in findings}
    for f in findings:
        other = ids[RELEASES if f["location"]["file"] == WRAPPER else WRAPPER]
        assert [(s["id"], s["refs"]) for s in f["shares_code_with"]] == [
            (other, [f"{WRAPPER}:1-2"] if f["location"]["file"] == RELEASES
             else [f"{WRAPPER}:1", f"{WRAPPER}:1-2"])]
    md = (out / "report.md").read_text()
    block = md.split(f"### {ids[RELEASES]} ·", 1)[1].split("\n### ", 1)[0]
    assert (f"Shares cited code with {ids[WRAPPER]} (`{WRAPPER}:1-2`): "
            "one fix may close both.") in block
