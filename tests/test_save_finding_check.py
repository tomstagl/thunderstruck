"""save_finding.py --check, --fallback and --usage (#5).

--check is how the orchestrator learns which results the SubagentStop hook
saved, without reading a finding file. --fallback and --usage record, in
agents/<ID>.json, that the orchestrator had to save a result itself and
what the Agent result said it consumed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_pipeline import _hotspots, _valid_finding

ROOT = Path(__file__).resolve().parent.parent
SAVE = ROOT / "scripts" / "save_finding.py"


def _save(repo: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SAVE), "--repo", str(repo), *args],
                          input=stdin, capture_output=True, text=True)


def _check(repo: Path, *ids: str) -> dict[str, str]:
    proc = _save(repo, "--check", *ids)
    assert proc.returncode == 0, proc.stderr
    return dict(line.split(" ", 1) for line in proc.stdout.splitlines())


def _result(repo: Path, tmp_path: Path) -> tuple[str, Path]:
    hid, doc = _valid_finding(repo, _hotspots(repo))
    src = tmp_path / "result.json"
    src.write_text(json.dumps(doc))
    return hid, src


def test_saved_after_a_save_and_missing_before(scanned_copy, tmp_path):
    hid, src = _result(scanned_copy, tmp_path)
    assert _check(scanned_copy, hid) == {hid: "missing"}
    assert _save(scanned_copy, "--id", hid, "--from", str(src)).returncode == 0
    assert _check(scanned_copy, hid, "H99") == {hid: "saved", "H99": "missing"}


def test_failed_after_failed(scanned_copy):
    assert _save(scanned_copy, "--id", "H02", "--failed").returncode == 0
    assert _check(scanned_copy, "H02") == {"H02": "failed"}


def test_a_finding_from_an_older_bundle_is_missing(scanned_copy, tmp_path):
    hid, src = _result(scanned_copy, tmp_path)
    assert _save(scanned_copy, "--id", hid, "--from", str(src)).returncode == 0
    index = json.loads((scanned_copy / ".thunderstruck" / "bundles" / "index.json").read_text())
    target = scanned_copy / next(b["file"] for b in index["bundles"] if b["id"] == hid)
    target.write_text(target.read_text() + "// changed\n")
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "bundle.py"),
                           "--repo", str(scanned_copy)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert _check(scanned_copy, hid) == {hid: "missing"}


def test_fallback_and_usage_are_recorded(scanned_copy, tmp_path):
    hid, src = _result(scanned_copy, tmp_path)
    proc = _save(scanned_copy, "--id", hid, "--from", str(src), "--fallback", "--usage",
                 '{"input_tokens": 5, "output_tokens": 2, "note": "x", "model": "sonnet",'
                 ' "cache_read_input_tokens": true}')
    assert proc.returncode == 0, proc.stderr
    rec = json.loads((scanned_copy / ".thunderstruck" / "agents" / f"{hid}.json").read_text())
    assert rec["fallback"] is True
    assert rec["relayed_usage"] == {"input_tokens": 5, "output_tokens": 2, "model": "sonnet"}
    assert rec["bundle_hash"] == json.loads(
        (scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())["bundle_hash"]
    assert _check(scanned_copy, hid) == {hid: "saved"}


def test_fallback_on_failed_is_recorded(scanned_copy):
    assert _save(scanned_copy, "--id", "H02", "--failed", "--fallback").returncode == 0
    rec = json.loads((scanned_copy / ".thunderstruck" / "agents" / "H02.json").read_text())
    assert rec["fallback"] is True


@pytest.mark.parametrize("usage", ["{not json", "[1]"])
def test_malformed_usage_is_refused(scanned_copy, tmp_path, usage):
    hid, src = _result(scanned_copy, tmp_path)
    proc = _save(scanned_copy, "--id", hid, "--from", str(src), "--usage", usage)
    assert proc.returncode == 2
    assert _check(scanned_copy, hid) == {hid: "missing"}


def test_prose_before_the_json_is_still_missing(scanned_copy, tmp_path):
    hid, src = _result(scanned_copy, tmp_path)
    src.write_text("Here is the result:\n" + src.read_text())
    assert _save(scanned_copy, "--id", hid, "--from", str(src)).returncode == 2
    assert _check(scanned_copy, hid) == {hid: "missing"}


def test_check_and_id_together_are_an_error(scanned_copy):
    assert _save(scanned_copy, "--check", "H01", "--id", "H01").returncode == 2
