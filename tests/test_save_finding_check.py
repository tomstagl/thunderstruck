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
    # the first word is the state; a reason may follow in parentheses (#96)
    return {line.split(" ")[0]: line.split(" ")[1] for line in proc.stdout.splitlines()}


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


# --- #96 Task 2: a missing result says why ---------------------------------
SCAN_BEGAN = "2000-01-01T00:00:00+00:00"


def _lines(repo: Path, *ids: str) -> list[str]:
    proc = _save(repo, "--check", *ids)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.splitlines()


def _trace(repo: Path, *rows: tuple[str, str]) -> None:
    """(at, outcome) rows; outcome 'saved:H09' names the id a save was for."""
    out = repo / ".thunderstruck"
    lines = []
    for at, outcome in rows:
        row = {"at": at, "agent_type": "thunderstruck:thunderstruck-investigator",
               "keys": ["agent_id"], "outcome": outcome.split(":")[0]}
        if ":" in outcome and outcome.startswith("saved"):
            row["id"] = outcome.split(":")[1]
        lines.append(json.dumps(row))
    (out / "hook-trace.jsonl").write_text("\n".join(lines) + "\n")


def test_missing_with_no_trace_says_the_hook_did_not_run(scanned_copy):
    assert _lines(scanned_copy, "H01") == [
        "H01 missing (the capture hook did not run for any agent in this scan)"]


def test_a_trace_from_before_this_scan_is_ignored(scanned_copy):
    _trace(scanned_copy, ("2000-01-01T00:00:00+00:00", "no_message"))
    assert "did not run for any agent" in _lines(scanned_copy, "H01")[0]


def test_missing_after_other_agents_were_saved(scanned_copy):
    _trace(scanned_copy, ("2999-01-01T00:00:00+00:00", "saved:H02"),
           ("2999-01-01T00:00:01+00:00", "no_message"))
    assert _lines(scanned_copy, "H01") == [
        "H01 missing (the hook ran for 2 other agents, none delivered this one)"]


def test_missing_when_every_line_has_the_same_failure(scanned_copy):
    _trace(scanned_copy, ("2999-01-01T00:00:00+00:00", "no_message"),
           ("2999-01-01T00:00:01+00:00", "no_message"))
    assert _lines(scanned_copy, "H01") == ["H01 missing (the hook ran and recorded no_message)"]


def test_differing_failures_name_the_most_frequent(scanned_copy):
    _trace(scanned_copy, ("2999-01-01T00:00:00+00:00", "no_entry"),
           ("2999-01-01T00:00:01+00:00", "no_message"),
           ("2999-01-01T00:00:02+00:00", "no_message"))
    assert _lines(scanned_copy, "H01") == ["H01 missing (the hook ran and recorded no_message)"]


def test_a_saved_or_failed_result_carries_no_reason(scanned_copy):
    assert _save(scanned_copy, "--id", "H02", "--failed").returncode == 0
    assert _lines(scanned_copy, "H02") == ["H02 failed"]


def test_a_malformed_trace_line_is_skipped(scanned_copy):
    (scanned_copy / ".thunderstruck" / "hook-trace.jsonl").write_text("{not json\n[]\n")
    assert "did not run for any agent" in _lines(scanned_copy, "H01")[0]
