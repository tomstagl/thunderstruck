"""The guardrail's contract, which is mostly about what it must NOT do.

A forensic tool that blocks an edit, or adds latency to every keystroke, or
warns about the same file repeatedly, gets switched off — and then it warns
about nothing at all.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

GUARDRAIL = Path(__file__).resolve().parent.parent / "scripts" / "guardrail.py"


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    flagged = tmp_path / "src" / "flagged.ts"
    flagged.write_text("const a = 1;\n")
    (tmp_path / "src" / "clean.ts").write_text("const b = 2;\n")
    moved = tmp_path / "src" / "moved.ts"
    moved.write_text("const c = 3;\n")
    linked = tmp_path / "src" / "linked.ts"
    linked.write_text("const d = 4;\n")

    inbound = [{"ref": f"dependencyOf component:default/{n}", "direction": "inbound",
                "neighbour": f"component:default/{n}", "attributes": {}}
               for n in ("d1", "d2", "d3", "d4", "d5", "d6")]
    web = {"ref": "dependencyOf component:default/web-frontend", "direction": "inbound",
           "neighbour": "component:default/web-frontend", "attributes": {"tier": "2"}}
    pay = {"ref": "dependsOn component:default/payments-api", "direction": "outbound",
           "neighbour": "component:default/payments-api", "attributes": {"tier": "1"}}
    index = {
        "schema": "thunderstruck.index/v1",
        "files": {
            "src/flagged.ts": {
                "content_hash": _sha(flagged),
                "findings": [
                    {"id": "FR-001", "lines": "1-10",
                     "failure_mode": "Resync restarts from page 1 on 429",
                     "missing_patterns": ["S03", "S07"], "confidence": "high",
                     "sustaining_effect": "The job re-queues itself at full cost"},
                    {"id": "FR-007", "failure_mode": "Low confidence thing",
                     "missing_patterns": ["S06"], "confidence": "low"},
                ]},
            "src/moved.ts": {
                "content_hash": "sha256:" + "0" * 64,
                "findings": [{"id": "FR-009", "failure_mode": "Something that moved",
                              "missing_patterns": ["S02"], "confidence": "medium"}]},
            "src/linked.ts": {
                "content_hash": _sha(linked),
                "findings": [
                    {"id": "FR-002", "failure_mode": "Checkout stalls under retry storms",
                     "missing_patterns": ["S02"], "confidence": "high",
                     "catalog_evidence": [web, *inbound[:2]]},
                    {"id": "FR-003", "failure_mode": "Payment calls pile up",
                     "missing_patterns": ["S01"], "confidence": "medium",
                     "catalog_evidence": [*inbound[2:], web, pay]},
                ]},
        }}
    out = tmp_path / ".thunderstruck"
    out.mkdir()
    (out / "index.json").write_text(json.dumps(index))
    return tmp_path


def run_hook(project: Path, rel: str, session: str = "s1",
             tool: str = "Edit") -> subprocess.CompletedProcess:
    payload = json.dumps({
        "session_id": session, "hook_event_name": "PreToolUse",
        "cwd": str(project), "scratchpad_dir": str(project / ".state"),
        "tool_name": tool, "tool_input": {"file_path": str(project / rel)},
    })
    return subprocess.run([sys.executable, str(GUARDRAIL)], input=payload,
                          capture_output=True, text=True)


def test_flagged_file_emits_additional_context(project):
    proc = run_hook(project, "src/flagged.ts")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    out = payload["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    context = out["additionalContext"]
    assert "FR-001" in context
    assert "S03" in context
    assert "re-queues itself" in context


def test_low_confidence_findings_are_not_surfaced(project):
    context = json.loads(run_hook(project, "src/flagged.ts").stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert "FR-007" not in context
    assert "1 open finding" in context


def test_context_is_phrased_as_fact_not_instruction(project):
    """Claude Code's hooks reference warns that imperative, system-command
    shaped context trips prompt-injection defences and is surfaced to the user
    instead of used."""
    context = json.loads(run_hook(project, "src/flagged.ts").stdout)[
        "hookSpecificOutput"]["additionalContext"]
    lowered = context.lower()
    for imperative in ("you must", "do not edit", "re-check this edit",
                       "stop and", "ignore previous"):
        assert imperative not in lowered, f"imperative phrasing: {imperative!r}"


def test_warns_only_once_per_file_per_session(project):
    assert run_hook(project, "src/flagged.ts", session="a").stdout.strip()
    assert run_hook(project, "src/flagged.ts", session="a").stdout.strip() == ""
    # A different session starts fresh.
    assert run_hook(project, "src/flagged.ts", session="b").stdout.strip()


def test_silent_on_unflagged_file(project):
    proc = run_hook(project, "src/clean.ts")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_staleness_is_announced(project):
    context = json.loads(run_hook(project, "src/moved.ts").stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert "changed since the scan" in context


@pytest.mark.parametrize("payload", [
    "", "not json", "{}", '{"tool_input": {}}',
    '{"tool_input": {"file_path": "/nope/x.ts"}, "cwd": "/nope"}',
    '{"tool_input": {"file_path": null}}',
    '[1, 2, 3]',
])
def test_never_fails_the_edit(payload):
    """Whatever it is handed, the hook exits 0 and says nothing."""
    proc = subprocess.run([sys.executable, str(GUARDRAIL)], input=payload,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"non-zero exit on {payload!r}"
    assert proc.stdout.strip() == ""


def test_unreadable_index_is_a_silent_no_op(project):
    (project / ".thunderstruck" / "index.json").write_text("{ broken json")
    proc = run_hook(project, "src/flagged.ts")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_latency_is_within_budget(project):
    timings = []
    for i in range(15):
        start = time.perf_counter()
        run_hook(project, "src/flagged.ts", session=f"perf{i}")
        timings.append((time.perf_counter() - start) * 1000)
    timings.sort()
    median = timings[len(timings) // 2]
    assert median < 100, f"median {median:.0f}ms exceeds the 100ms budget: {timings}"


def test_finds_the_project_from_a_subdirectory(project):
    payload = json.dumps({
        "session_id": "sub", "hook_event_name": "PreToolUse",
        "cwd": str(project / "src"), "scratchpad_dir": str(project / ".state"),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(project / "src" / "flagged.ts")},
    })
    proc = subprocess.run([sys.executable, str(GUARDRAIL)], input=payload,
                          capture_output=True, text=True)
    assert proc.returncode == 0
    assert "FR-001" in proc.stdout


def test_hook_needs_no_third_party_imports():
    """It runs on bare python3, not `uv run`, so it must not import pyyaml or
    anything else that would need resolving."""
    source = GUARDRAIL.read_text()
    for forbidden in ("import yaml", "import lizard", "from yaml", "import _common"):
        assert forbidden not in source, f"guardrail imports {forbidden!r}"


def test_hooks_json_matches_current_tool_names():
    root = GUARDRAIL.parent.parent
    hooks = json.loads((root / "hooks" / "hooks.json").read_text())
    entries = hooks["hooks"]["PreToolUse"]
    matcher = entries[0]["matcher"]
    assert "MultiEdit" not in matcher, "MultiEdit no longer exists in Claude Code"
    assert "Edit" in matcher and "Write" in matcher
    command = entries[0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}" in command
    assert "exit 0" in command, "the hook command must fail open"


def test_cited_neighbours_are_named(project):
    context = json.loads(run_hook(project, "src/linked.ts").stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert ("Cited dependents of this component: web-frontend (tier: 2), d1, d2, d3, d4 "
            "and 2 more.") in context
    assert "Cited dependencies of this component: payments-api (tier: 1)." in context
    lowered = context.lower()
    for imperative in ("you must", "do not edit", "stop and", "ignore previous"):
        assert imperative not in lowered


def test_no_neighbour_line_without_catalog_evidence(project):
    context = json.loads(run_hook(project, "src/flagged.ts").stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert "Cited dependents" not in context and "Cited dependencies" not in context


def test_malformed_catalog_evidence_still_shows_findings(project):
    path = project / ".thunderstruck" / "index.json"
    index = json.loads(path.read_text())
    findings = index["files"]["src/flagged.ts"]["findings"]
    findings[0]["catalog_evidence"] = "oops"
    findings.append({"id": "FR-010", "failure_mode": "x", "missing_patterns": [],
                     "confidence": "high",
                     "catalog_evidence": [None, 3, {"direction": "inbound"}]})
    path.write_text(json.dumps(index))
    context = json.loads(run_hook(project, "src/flagged.ts").stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert "FR-001" in context and "Cited" not in context
