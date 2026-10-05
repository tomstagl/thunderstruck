"""bundle.py and validate.py print summaries by default (#5).

Every line a script prints lands in the orchestrator's context and is paid
for again on every later call. Per-hotspot success lines move behind
--verbose; errors are always printed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c
from test_pipeline import _hotspots, _valid_finding, _write_finding

ROOT = Path(__file__).resolve().parent.parent
PER_BUNDLE = re.compile(r"^[HD]\d\d  ~", re.M)


def _run(script: str, repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script),
                           "--repo", str(repo), *args], capture_output=True, text=True)


def _todo_tokens(repo: Path) -> list[int]:
    index = json.loads((repo / ".thunderstruck" / "bundles" / "index.json").read_text())
    return [b["tokens_estimated"] for b in index["bundles"] if not b["cached"]]


def test_bundle_prints_a_summary_and_the_estimate(scanned_copy):
    proc = _run("bundle.py", scanned_copy)
    assert proc.returncode == 0, proc.stderr
    assert not PER_BUNDLE.search(proc.stdout), proc.stdout
    assert "need investigating" in proc.stdout
    todo = _todo_tokens(scanned_copy)
    k = round(sum(todo) * c.INVESTIGATOR_TOKENS_PER_BUNDLE_TOKEN / 1000)
    lines = proc.stdout.rstrip("\n").splitlines()
    assert lines[-2] == (f"estimate: ~{k}k weighted tokens for {len(todo)} investigators "
                         f"on sonnet, plus the orchestrator")
    assert lines[-1].startswith(f"  assumes ~{c.INVESTIGATOR_TOKENS_PER_BUNDLE_TOKEN:g} "
                                f"weighted tokens per bundle token on sonnet")
    assert lines[-1].endswith("(docs/calibration/consumption.md)")


def test_bundle_verbose_restores_the_per_bundle_lines(scanned_copy):
    proc = _run("bundle.py", scanned_copy, "--verbose")
    assert proc.returncode == 0, proc.stderr
    assert PER_BUNDLE.search(proc.stdout)


def test_the_estimate_scales_with_the_model(scanned_copy):
    proc = _run("bundle.py", scanned_copy, "--model", "opus")
    assert proc.returncode == 0, proc.stderr
    todo = _todo_tokens(scanned_copy)
    factor = c.TOKEN_WEIGHTS[c.MODEL_ALIASES["opus"]]["input"]
    k = round(sum(todo) * c.INVESTIGATOR_TOKENS_PER_BUNDLE_TOKEN * factor / 1000)
    assert f"estimate: ~{k}k weighted tokens for {len(todo)} investigators on opus" \
        in proc.stdout
    assert "opus" in proc.stdout.rstrip("\n").splitlines()[-1]


def test_no_investigators_to_run():
    import bundle
    assert bundle.estimate_line([]) == ["estimate: no investigators to run"]


def test_bundles_are_identical_with_and_without_verbose(scanned_copy):
    out = scanned_copy / ".thunderstruck" / "bundles"
    assert _run("bundle.py", scanned_copy).returncode == 0
    quiet = {p.name: p.read_bytes() for p in out.iterdir()}
    assert _run("bundle.py", scanned_copy, "--verbose", "--model", "opus").returncode == 0
    assert {p.name: p.read_bytes() for p in out.iterdir()} == quiet


@pytest.fixture
def validated(scanned_copy):
    data = _hotspots(scanned_copy)
    hid, doc = _valid_finding(scanned_copy, data)
    _write_finding(scanned_copy, hid, doc)
    bad = data["hotspots"][1]["id"]
    _write_finding(scanned_copy, bad, {"hotspot_id": bad, "findings": [{"location": {}}]})
    return scanned_copy, hid, bad


def test_validate_prints_failures_and_the_summary(validated):
    repo, good, bad = validated
    proc = _run("validate.py", repo)
    assert proc.returncode == 1
    assert "ok  " not in proc.stdout
    lines = proc.stdout.splitlines()
    i = lines.index(next(line for line in lines if line.startswith(f"FAIL {bad}")))
    assert lines[i + 1].startswith("       - ")
    assert re.search(r"^\d+/\d+ valid, \d+ findings$", proc.stdout, re.M)


def test_validate_verbose_restores_ok_lines(validated):
    repo, good, bad = validated
    proc = _run("validate.py", repo, "--verbose")
    assert f"ok   {good}" in proc.stdout


def test_validate_quiet_prints_nothing(validated):
    repo, _, _ = validated
    assert _run("validate.py", repo, "--quiet").stdout == ""
