"""#103 Task 3: a recorded reproduction is shown in the report, and changes nothing else."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import mdtext as md
import reproduction
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CURRENT = ("Reproduced by a failing test (recorded by /thunderstruck-verify; "
           "the scan did not run it): ")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _report_md(repo: Path) -> tuple[str, dict]:
    subprocess.run([sys.executable, str(SCRIPTS / "report.py"), "--repo", str(repo)],
                   check=True, capture_output=True)
    out = repo / ".thunderstruck"
    return (out / "report.md").read_text(), json.loads((out / "report.json").read_text())


@pytest.fixture
def reported(scanned_copy, plugin_root) -> tuple[Path, str]:
    """A scanned copy with one validated finding, reported, and a test file to cite."""
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    (scanned_copy / "tests").mkdir(exist_ok=True)
    (scanned_copy / "tests" / "test_repro.py").write_text("def test_repro():\n    assert False\n")
    _, payload = _report_md(scanned_copy)
    return scanned_copy, payload["findings"][0]["key"]


def _rep(payload: dict) -> dict | None:
    return payload["findings"][0].get("reproduction")


def test_no_record_no_key_no_line(reported):
    repo, _ = reported
    markdown, payload = _report_md(repo)
    assert "reproduction" not in payload["findings"][0]
    assert "**Reproduction**" not in markdown


def test_a_current_reproduction_is_in_report_json_and_report_md(reported):
    repo, key = reported
    reproduction.record(repo, key, "fails_as_predicted", "tests/test_repro.py",
                        "pytest tests/test_repro.py -q")
    markdown, payload = _report_md(repo)
    rep = _rep(payload)
    assert rep == {"status": "fails_as_predicted", "state": "current",
                   "test_path": "tests/test_repro.py", "command": "pytest tests/test_repro.py -q",
                   "recorded_head": rep["recorded_head"], "stale_because": [],
                   "sentence": CURRENT + "tests/test_repro.py"}
    assert len(rep["recorded_head"]) == 40
    assert (f"**Reproduction** — {md.text(CURRENT.rstrip(': '))}: "
            f"{md.code('tests/test_repro.py')}.") in markdown
    assert md.code("pytest tests/test_repro.py -q") in markdown
    # next to the check: the reproduction line follows the check block
    block = markdown.split("**Check** — ", 1)[1]
    assert block.index("**Reproduction**") < block.index("**Verify**")


@pytest.mark.parametrize("status, sentence", [
    ("passes", "A recorded reproduction passed: the hypothesis did not hold as tested"),
    ("blocked", "A reproduction was attempted and blocked"),
])
def test_passes_and_blocked_wording(reported, status, sentence):
    repo, key = reported
    reproduction.record(repo, key, status, "tests/test_repro.py", "pytest -q")
    markdown, payload = _report_md(repo)
    assert _rep(payload)["sentence"] == sentence
    assert f"**Reproduction** — {md.text(sentence)}." in markdown


def test_a_stale_reproduction_is_shown_as_stale_first_and_never_as_reproduced(reported):
    repo, key = reported
    reproduction.record(repo, key, "fails_as_predicted", "tests/test_repro.py", "pytest -q")
    (repo / "tests" / "test_repro.py").write_text("def test_repro():\n    assert True\n")
    markdown, payload = _report_md(repo)
    rep = _rep(payload)
    assert (rep["state"], rep["stale_because"]) == ("stale", ["the test file changed"])
    assert rep["sentence"] == ("Stale: a failing test was recorded by /thunderstruck-verify "
                               "(the scan did not run it): tests/test_repro.py, "
                               "stale: the test file changed")
    line = next(l for l in markdown.splitlines() if l.startswith("**Reproduction**"))
    assert line.startswith("**Reproduction** — Stale")
    assert "Reproduced" not in line


def test_a_stale_passes_names_what_changed(reported):
    repo, key = reported
    reproduction.record(repo, key, "passes", "tests/test_repro.py", "pytest -q")
    (repo / "tests" / "test_repro.py").unlink()
    _, payload = _report_md(repo)
    assert _rep(payload)["sentence"] == ("A recorded reproduction passed: the hypothesis did not "
                                         "hold as tested, stale: the test file is gone")


def test_an_unreadable_record_is_shown_as_that(reported):
    repo, key = reported
    d = repo / ".thunderstruck" / "reproductions"
    d.mkdir()
    (d / f"{key}.json").write_text("{nope")
    markdown, payload = _report_md(repo)
    assert _rep(payload)["state"] == "unreadable"
    assert "**Reproduction** — A recorded reproduction is unreadable." in markdown


HOSTILE = "pytest `x` [a](https://evil.example) <img src=x onerror=alert(1)> ![i](https://e.example/i.png)"


def test_a_hostile_command_is_inert(reported):
    repo, key = reported
    reproduction.record(repo, key, "fails_as_predicted", "tests/test_repro.py", HOSTILE)
    markdown, payload = _report_md(repo)
    assert _rep(payload)["command"] == HOSTILE
    assert md.code(HOSTILE) in markdown
    assert "](https://evil.example)" not in markdown.replace(md.code(HOSTILE), "")
    assert "<img" not in markdown.replace(md.code(HOSTILE), "")


# --------------------------------------------------------------------------
# No effect (AC-2): a record changes no rank, confidence, gate, bundle or brief
# --------------------------------------------------------------------------


def _tree(d: Path) -> dict[str, str]:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.rglob("*")) if p.is_file()} if d.is_dir() else {}


def _pipeline(repo: Path, env: dict) -> dict:
    for step in (["bundle.py"], ["verify.py", "prepare", "--model", "sonnet"], ["report.py"]):
        proc = subprocess.run([sys.executable, str(SCRIPTS / step[0]), *step[1:], "--repo", str(repo)],
                              capture_output=True, text=True, cwd=str(repo), env=env)
        assert proc.returncode == 0, (step, proc.stderr)
    out = repo / ".thunderstruck"
    report = json.loads((out / "report.json").read_text())
    return {"bundles": _tree(out / "bundles"), "briefs": _tree(out / "checks" / "briefs"),
            "plan": (out / "checks" / "plan.json").read_text()
            if (out / "checks" / "plan.json").is_file() else None,
            "findings": [{k: f.get(k) for k in ("id", "key", "confidence", "confidence_claimed",
                                                  "gate", "check", "hotspot_score")}
                         for f in report["findings"]]}


def test_a_record_changes_no_rank_confidence_gate_bundle_or_brief(validated_repo, validated_env):
    before = _pipeline(validated_repo, validated_env)
    assert before["bundles"] and before["briefs"], "the comparison needs bundles and briefs"
    keys = [f["key"] for f in before["findings"]]
    (validated_repo / "tests").mkdir(exist_ok=True)
    (validated_repo / "tests" / "test_repro.py").write_text("x = 1\n")
    for key, status in zip(keys, ("fails_as_predicted", "passes", "blocked")):
        reproduction.record(validated_repo, key, status, "tests/test_repro.py", "pytest -q")
    after = _pipeline(validated_repo, validated_env)
    assert after == before
    report = json.loads((validated_repo / ".thunderstruck" / "report.json").read_text())
    assert sum("reproduction" in f for f in report["findings"]) == min(3, len(keys))
