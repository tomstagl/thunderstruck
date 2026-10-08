"""The SubagentStop hook that saves an investigator's result to disk (#5).

It has the guardrail's contract: always exit 0, say nothing, stdlib only,
under 100ms. And it is the one place model output that read the scanned
repository turns into a file, so every path it writes comes from
bundles/index.json, never from the payload.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "scripts" / "capture_finding.py"
SCRIPTS = ROOT / "scripts"
PAYLOADS = ROOT / "tests" / "fixtures" / "hook_payloads"


def _payload(name: str, cwd: Path, **over) -> str:
    doc = json.loads((PAYLOADS / f"{name}.json").read_text())
    return json.dumps({**doc, "cwd": str(cwd), **over})


def _run(stdin: str) -> subprocess.CompletedProcess:
    proc = subprocess.run([sys.executable, str(HOOK)], input=stdin,
                          capture_output=True, text=True)
    assert proc.returncode == 0
    assert proc.stdout == "" and proc.stderr == ""
    return proc


def _written(repo: Path) -> set[str]:
    out = repo / ".thunderstruck"
    return {str(p.relative_to(out)) for d in ("findings", "agents")
            if (out / d).is_dir() for p in (out / d).rglob("*")}


def _save_by_hand(repo: Path, tmp_path: Path, hid: str, text: str) -> bytes:
    src = tmp_path / "by-hand.json"
    src.write_text(text)
    dest = repo / ".thunderstruck" / "findings" / f"{hid}.json"
    before = dest.read_bytes() if dest.exists() else None
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "save_finding.py"),
                           "--repo", str(repo), "--id", hid, "--from", str(src)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    saved = dest.read_bytes()
    if before is None:
        dest.unlink()
    else:
        dest.write_bytes(before)
    return saved


@pytest.mark.parametrize("name", ["valid", "fenced"])
def test_a_result_is_saved_exactly_as_save_finding_would(scanned_copy, tmp_path, name):
    message = json.loads((PAYLOADS / f"{name}.json").read_text())["last_assistant_message"]
    expected = _save_by_hand(scanned_copy, tmp_path, "H01", message)
    _run(_payload(name, scanned_copy))
    out = scanned_copy / ".thunderstruck"
    assert (out / "findings" / "H01.json").read_bytes() == expected
    rec = json.loads((out / "agents" / "H01.json").read_text())
    assert rec["hotspot_id"] == "H01"
    assert [a["agent_id"] for a in rec["agents"]] == ["a-1"]
    assert rec["agents"][0] == {"agent_id": "a-1", "session_id": "s-1",
                                "transcript_path": "/tmp/projects/x/s-1.jsonl",
                                "stop_reason": "completed", "kind": "first"}


@pytest.mark.parametrize("name", ["prose_first", "unknown_id", "path_id", "other_agent",
                                  "not_json", "no_fields"])
def test_anything_else_writes_nothing(scanned_copy, name):
    _run(_payload(name, scanned_copy))
    assert _written(scanned_copy) == set()


def test_an_oversized_payload_writes_nothing(scanned_copy):
    _run(_payload("valid", scanned_copy, padding="x" * 1_000_001))
    assert _written(scanned_copy) == set()


def test_outside_a_scan_it_writes_nothing(scanned_copy):
    (scanned_copy / ".thunderstruck" / "bundles" / "index.json").unlink()
    _run(_payload("valid", scanned_copy))
    assert _written(scanned_copy) == set()


@pytest.mark.parametrize("stdin", ["", "not json", "[]", "{}", '{"agent_type": 3}'])
def test_never_fails(stdin):
    _run(stdin)


def test_finds_the_repository_from_a_subdirectory(scanned_copy):
    _run(_payload("valid", scanned_copy / "src"))
    assert (scanned_copy / ".thunderstruck" / "findings" / "H01.json").is_file()
    assert not (scanned_copy / "src" / ".thunderstruck").exists()


@pytest.mark.parametrize("invalid,kind", [(False, "respawn"), (True, "repair")])
def test_a_second_delivery_keeps_the_first_as_an_attempt(scanned_copy, invalid, kind):
    out = scanned_copy / ".thunderstruck"
    _run(_payload("valid", scanned_copy))
    first = (out / "findings" / "H01.json").read_bytes()
    if invalid:
        (out / "validation.json").write_text(json.dumps(
            {"results": [{"hotspot_id": "H01", "valid": False, "errors": ["x"]}]}))
    second = json.loads((PAYLOADS / "valid.json").read_text())["last_assistant_message"]
    second = second.replace("The delay is constant.", "The delay is fixed.")
    _run(_payload("valid", scanned_copy, agent_id="a-2", last_assistant_message=second))

    assert (out / "agents" / "H01.attempt1.json").read_bytes() == first
    assert b"The delay is fixed." in (out / "findings" / "H01.json").read_bytes()
    rec = json.loads((out / "agents" / "H01.json").read_text())
    assert [(a["agent_id"], a["kind"]) for a in rec["agents"]] == [("a-1", "first"),
                                                                  ("a-2", kind)]
    assert [p.name for p in (out / "findings").iterdir()] == ["H01.json"]


def test_latency_is_within_budget(scanned_copy):
    stdin = _payload("valid", scanned_copy)
    timings = []
    for _ in range(20):
        start = time.perf_counter()
        subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True)
        timings.append((time.perf_counter() - start) * 1000)
    timings.sort()
    median = timings[len(timings) // 2]
    assert median < 100, f"median {median:.0f}ms exceeds the 100ms budget: {timings}"


def test_hook_imports_the_stdlib_and_finding_shape_only():
    source = HOOK.read_text()
    for forbidden in ("import yaml", "import lizard", "from yaml", "import _common"):
        assert forbidden not in source, f"capture_finding imports {forbidden!r}"
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add(node.module.split(".")[0])
    outside = names - set(sys.stdlib_module_names) - {"__future__", "finding_shape"}
    assert not outside, f"capture_finding.py imports {outside}"


def test_a_new_session_starts_a_fresh_record(scanned_copy):
    """A later scan of an unchanged repo (findings/ deleted, or a bundle
    requeued under newer rules) is a first delivery, not a re-spawn."""
    out = scanned_copy / ".thunderstruck"
    _run(_payload("valid", scanned_copy))
    _run(_payload("valid", scanned_copy, session_id="s-2", agent_id="b-1"))
    rec = json.loads((out / "agents" / "H01.json").read_text())
    assert [(a["agent_id"], a["kind"]) for a in rec["agents"]] == [("b-1", "first")]
    assert not (out / "agents" / "H01.attempt1.json").exists()


# --- #37 ---------------------------------------------------------------------
def _skeptic_payload(repo: Path, message: str, agent_id: str = "s1") -> str:
    return json.dumps({"session_id": "sess", "transcript_path": "/x/sess.jsonl", "cwd": str(repo),
                       "hook_event_name": "SubagentStop", "agent_id": agent_id,
                       "agent_type": "plugin:thunderstruck:thunderstruck-skeptic",
                       "stop_reason": "completed", "last_assistant_message": message})


def _planned(validated_repo, validated_env) -> tuple[dict, dict]:
    subprocess.run([sys.executable, str(SCRIPTS / "verify.py"), "prepare", "--repo", str(validated_repo)],
                   check=True, capture_output=True, cwd=str(validated_repo), env=validated_env)
    plan = json.loads((validated_repo / ".thunderstruck" / "checks" / "plan.json").read_text())
    return plan, plan["findings"][0]


def test_a_skeptic_verdict_is_captured(validated_repo, validated_env):
    plan, entry = _planned(validated_repo, validated_env)
    verdict = {"key": entry["key"], "verdict": "upheld", "reason": "held", "holds": None,
               "refuted_claims": [], "evidence": [], "dependencies_read": [], "duplicate_of": None}
    _run(_skeptic_payload(validated_repo, json.dumps(verdict)))
    saved = json.loads((validated_repo / ".thunderstruck" / "checks" / "results" / f"{entry['key']}.json").read_text())
    assert saved["verdict"] == "upheld" and saved["brief_hash"] == entry["brief_hash"]
    assert saved["scan"] == plan["generated_at"]
    agents = json.loads((validated_repo / ".thunderstruck" / "checks" / "agents" / f"{entry['key']}.json").read_text())
    assert [a["kind"] for a in agents["agents"]] == ["first"]


@pytest.mark.parametrize("message", [
    lambda k: json.dumps({"key": "ffffffffffff", "verdict": "upheld"}),   # not planned
    lambda k: json.dumps({"key": "../../x", "verdict": "upheld"}),        # path-shaped
    lambda k: "Here is my verdict:\n" + json.dumps({"key": k, "verdict": "upheld"}),
    lambda k: json.dumps([k]),
])
def test_a_skeptic_message_without_a_planned_key_writes_nothing(validated_repo, validated_env, message):
    """Review Focus 2."""
    _, entry = _planned(validated_repo, validated_env)
    before = sorted(p for p in (validated_repo / ".thunderstruck").rglob("*"))
    _run(_skeptic_payload(validated_repo, message(entry["key"])))
    assert sorted(p for p in (validated_repo / ".thunderstruck").rglob("*")) == before


def test_a_second_delivery_is_a_respawn_and_wins(validated_repo, validated_env):
    _, entry = _planned(validated_repo, validated_env)
    for agent_id, verdict in (("s1", "upheld"), ("s2", "refuted")):
        _run(_skeptic_payload(validated_repo, json.dumps({"key": entry["key"], "verdict": verdict}), agent_id))
    out = validated_repo / ".thunderstruck" / "checks"
    assert json.loads((out / "results" / f"{entry['key']}.json").read_text())["verdict"] == "refuted"
    assert [a["kind"] for a in json.loads((out / "agents" / f"{entry['key']}.json").read_text())["agents"]] == \
        ["first", "respawn"]


def test_the_hook_still_ignores_other_agents_and_stays_fast(validated_repo, validated_env):
    _planned(validated_repo, validated_env)
    payload = json.loads(_skeptic_payload(validated_repo, "{}"))
    payload["agent_type"] = "Explore"
    _run(json.dumps(payload))
    assert not (validated_repo / ".thunderstruck" / "checks" / "results").exists()
