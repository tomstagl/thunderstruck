"""usage.py: what a scan consumed, read from Claude Code's own transcripts (#5).

The transcripts here are synthetic and built per test under a temporary
CLAUDE_CONFIG_DIR. They carry message text on purpose, so the tests can
prove none of it reaches usage.json.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-10-03-reduce-consumption-design.md"
GENERATED_AT = "2026-10-03T09:00:00+00:00"
NOW = "2026-10-03T09:30:00+00:00"
SECRET = "the orchestrator said something private"
BUCKETS = {"input_tokens": 1000, "cache_creation_input_tokens": 1000,
           "cache_read_input_tokens": 1000, "output_tokens": 1000}


def _assistant(mid: str, ts: str, usage: dict, model: str = "claude-sonnet-5-5",
               text: str = SECRET) -> dict:
    return {"type": "assistant", "timestamp": ts, "requestId": f"req-{mid}",
            "message": {"id": mid, "model": model, "role": "assistant",
                        "content": [{"type": "text", "text": text}], "usage": usage}}


def _jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows))


@pytest.fixture
def scan(tmp_path, monkeypatch):
    """A finished scan of two hotspots, with its session and subagent transcripts."""
    config = tmp_path / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    session = config / "projects" / "-repo" / "sess-1.jsonl"
    _jsonl(session, [
        _assistant("m0", "2026-10-03T08:00:00Z", {"input_tokens": 999_999}, "claude-opus-5-5"),
        {"type": "user", "timestamp": "2026-10-03T09:01:00Z",
         "message": {"role": "user", "content": SECRET}},
        # one API response written as three content blocks
        *[_assistant("m1", "2026-10-03T09:01:00Z", {"input_tokens": 10, "output_tokens": 4},
                     "claude-opus-5-5") for _ in range(3)],
        {"type": "user", "timestamp": "2026-10-03T09:02:00Z", "toolUseResult": SECRET,
         "message": {"role": "user", "content": [{"type": "tool_result", "content": SECRET}]}},
        _assistant("m2", "2026-10-03T09:02:00Z", {"output_tokens": 1}, "<synthetic>"),
        _assistant("m3", "2026-10-03T09:03:00Z", {"input_tokens": 20, "output_tokens": 6},
                   "claude-opus-5-5"),
    ])
    subagents = session.with_suffix("") / "subagents"
    _jsonl(subagents / "agent-a1.jsonl", [
        _assistant("s1", "2026-10-03T07:00:00Z", {"input_tokens": 100, "output_tokens": 10}),
        _assistant("s2", "2026-10-03T09:05:00Z", {"input_tokens": 100, "output_tokens": 10}),
    ])
    _jsonl(subagents / "agent-a2.jsonl", [
        _assistant("s3", "2026-10-03T09:06:00Z", {"input_tokens": 50, "output_tokens": 5}),
    ])

    repo = tmp_path / "repo"
    out = repo / ".thunderstruck"
    (out / "bundles").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (out / "agents").mkdir()
    (out / "hotspots.json").write_text(json.dumps({"generated_at": GENERATED_AT}))
    bundles = [{"id": h, "file": f"src/{h}.ts", "bundle_hash": f"sha256:{h}", "cached": False}
               for h in ("H01", "H02")]
    bundles.append({"id": "H03", "file": "src/H03.ts", "bundle_hash": "sha256:H03",
                    "cached": True})
    (out / "bundles" / "index.json").write_text(json.dumps({"bundles": bundles}))
    for hid, aid in (("H01", "a1"), ("H02", "a2")):
        _record(out, hid, [{"agent_id": aid, "session_id": "sess-1",
                            "transcript_path": str(session), "stop_reason": "completed",
                            "kind": "first"}])
    return {"repo": repo, "out": out, "session": session, "subagents": subagents,
            "config": config}


def _record(out: Path, hid: str, agents: list, **extra) -> None:
    (out / "agents" / f"{hid}.json").write_text(json.dumps(
        {"hotspot_id": hid, "bundle_hash": f"sha256:{hid}", "agents": agents, **extra}))


def _build(scan) -> dict:
    import usage
    return usage.build(scan["repo"], NOW)


# --- weights ---------------------------------------------------------------


def test_weights_follow_the_table_per_model_and_bucket():
    import usage
    buckets = usage.split({**BUCKETS, "cache_creation": {"ephemeral_5m_input_tokens": 400,
                                                         "ephemeral_1h_input_tokens": 600}})
    assert buckets == {"input": 1000, "cache_write_5m": 400, "cache_write_1h": 600,
                       "cache_read": 1000, "output": 1000}
    even = {"input": 1000, "cache_write_5m": 1000, "cache_write_1h": 1000,
            "cache_read": 1000, "output": 1000}
    assert usage.weighted("claude-sonnet-5-5", even) == 1000 + 1250 + 2000 + 100 + 5000
    assert usage.weighted("claude-opus-5-5", even) == 2000 + 2500 + 4000 + 100 + 10000
    assert usage.weighted("claude-future-9", even) is None


def test_a_cache_write_without_a_ttl_is_weighted_as_five_minutes():
    import usage
    assert usage.split({"cache_creation_input_tokens": 70}) == {
        "input": 0, "cache_write_5m": 70, "cache_write_1h": 0, "cache_read": 0, "output": 0}


def test_token_weights_equal_the_spec_table():
    text = SPEC.read_text()
    section = text[text.index("### 2.3"):text.index("### 2.4")]
    table = {}
    for row in re.findall(r"^\| `([^`]+)` \|(.+)\|$", section, re.M):
        values = [float(v) for v in row[1].split("|")]
        table[row[0]] = dict(zip(("input", "cache_write_5m", "cache_write_1h",
                                  "cache_read", "output"), values))
    assert table and c.TOKEN_WEIGHTS == table


def test_an_unknown_model_is_counted_raw_and_named(scan):
    _jsonl(scan["subagents"] / "agent-a2.jsonl", [
        _assistant("s3", "2026-10-03T09:06:00Z", {"input_tokens": 50}, "claude-future-9")])
    doc = _build(scan)
    row = doc["investigators"]["by_model"]["claude-future-9"]
    assert row["input"] == 50 and row["weighted"] is None
    assert doc["source"] == "partial"
    assert any("claude-future-9" in m for m in doc["missing"])


# --- what is counted -------------------------------------------------------


def test_a_normal_scan(scan):
    doc = _build(scan)
    assert doc["schema"] == c.USAGE_SCHEMA
    assert doc["source"] == "transcripts" and doc["missing"] == []
    assert doc["window"] == {"from": GENERATED_AT, "to": NOW}
    inv = doc["investigators"]
    assert (inv["agents"], inv["respawns"], inv["repairs"], inv["fallback_saves"]) == (2, 0, 0, 0)
    # subagent entries are never windowed: s1 predates generated_at and counts
    assert inv["by_model"]["claude-sonnet-5-5"]["input"] == 250
    assert inv["by_hotspot"]["H01"] == {"agents": 1, "calls": 2,
                                       "weighted": 200 + 20 * 5}
    assert set(inv["by_hotspot"]) == {"H01", "H02"}
    orch = doc["orchestrator"]
    # m0 is before the window, m1 counts once, m2 is <synthetic>, user lines never count
    assert orch["calls"] == 2
    assert orch["by_model"] == {"claude-opus-5-5": {
        "input": 30, "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": 0,
        "output": 10, "weighted": 30 * 2 + 10 * 10}}
    assert doc["total_weighted"] == 160 + 300 + 75


@pytest.mark.parametrize("kind,respawns,repairs", [("respawn", 1, 0), ("repair", 0, 1)])
def test_a_second_agent_is_counted_by_kind(scan, kind, respawns, repairs):
    _record(scan["out"], "H01", [
        {"agent_id": "a1", "transcript_path": str(scan["session"]), "kind": "first"},
        {"agent_id": "a2", "transcript_path": str(scan["session"]), "kind": kind}])
    inv = _build(scan)["investigators"]
    assert (inv["respawns"], inv["repairs"]) == (respawns, repairs)
    assert inv["by_hotspot"]["H01"]["agents"] == 2


def test_an_unreadable_subagent_falls_back_to_relayed_usage(scan):
    (scan["subagents"] / "agent-a2.jsonl").unlink()
    _record(scan["out"], "H02", [{"agent_id": "a2", "transcript_path": str(scan["session"]),
                                  "kind": "first"}],
            fallback=True, relayed_usage={"input_tokens": 70, "output_tokens": 3,
                                          "model": "sonnet"})
    doc = _build(scan)
    assert doc["source"] == "partial"
    assert any("H02" in m and "transcript" in m for m in doc["missing"])
    assert doc["investigators"]["by_hotspot"]["H02"]["weighted"] == 70 + 15
    assert doc["investigators"]["fallback_saves"] == 1
    assert "claude-sonnet-5-5" in doc["investigators"]["by_model"]


def test_a_record_from_an_older_bundle_is_ignored(scan):
    rec = json.loads((scan["out"] / "agents" / "H02.json").read_text())
    rec["bundle_hash"] = "sha256:older"
    (scan["out"] / "agents" / "H02.json").write_text(json.dumps(rec))
    doc = _build(scan)
    assert "H02" not in doc["investigators"]["by_hotspot"]
    assert "H02: no agent record, the hook did not fire" in doc["missing"]
    assert doc["source"] == "partial"


def test_no_agent_records_is_unavailable(scan):
    for p in (scan["out"] / "agents").iterdir():
        p.unlink()
    doc = _build(scan)
    assert doc["source"] == "unavailable"
    assert "orchestrator: session transcript not readable" in doc["missing"]


def test_a_line_that_is_not_json_is_skipped_and_reported(scan):
    with scan["subagents"].joinpath("agent-a2.jsonl").open("a") as fh:
        fh.write("{ truncated\n")
    doc = _build(scan)
    assert doc["investigators"]["by_hotspot"]["H02"]["calls"] == 1
    assert doc["source"] == "partial"
    assert any("H02" in m and "1 line" in m for m in doc["missing"])


# --- security --------------------------------------------------------------


@pytest.mark.parametrize("where", ["/etc/passwd", "outside"])
def test_transcripts_outside_the_projects_dir_are_never_opened(scan, monkeypatch, where):
    outside = scan["config"].parent / "elsewhere" / "sess-1.jsonl"
    _jsonl(outside, [_assistant("x", "2026-10-03T09:01:00Z", {"input_tokens": 1})])
    target = "/etc/passwd" if where == "/etc/passwd" else str(outside)
    for hid, aid in (("H01", "a1"), ("H02", "a2")):
        _record(scan["out"], hid, [{"agent_id": aid, "transcript_path": target,
                                    "kind": "first"}])
    real_open = Path.open

    def guarded(self, *a, **k):
        assert not str(self).startswith(str(Path(target).parent)), f"opened {self}"
        return real_open(self, *a, **k)

    monkeypatch.setattr(Path, "open", guarded)
    doc = _build(scan)
    assert doc["source"] == "unavailable"


def test_usage_json_holds_no_conversation_text(scan):
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "usage.py"),
                           "--repo", str(scan["repo"])], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    written = (scan["out"] / "usage.json").read_text()
    assert SECRET not in written and "sess-1" not in written
    assert proc.stdout.startswith("usage: transcripts, ~")
    assert json.loads(written)["source"] == "transcripts"


def test_without_hotspots_json_it_exits_2(scan):
    (scan["out"] / "hotspots.json").unlink()
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "usage.py"),
                           "--repo", str(scan["repo"])], capture_output=True, text=True)
    assert proc.returncode == 2


def test_a_session_with_nothing_in_the_window_is_not_the_orchestrator(scan):
    _jsonl(scan["session"], [
        _assistant("m0", "2026-10-03T08:00:00Z", {"input_tokens": 5}, "claude-opus-5-5")])
    doc = _build(scan)
    assert "orchestrator: session transcript not readable" in doc["missing"]
    assert doc["source"] == "partial"


def test_relayed_usage_beside_readable_transcripts_is_an_extra_agent(scan):
    _record(scan["out"], "H01", [{"agent_id": "a1", "transcript_path": str(scan["session"]),
                                  "kind": "first"}],
            fallback=True, relayed_usage={"input_tokens": 40, "model": "sonnet"})
    doc = _build(scan)
    hs = doc["investigators"]["by_hotspot"]["H01"]
    assert hs["agents"] == 2 and hs["weighted"] == 300 + 40
    assert doc["source"] == "partial"
    assert any(m.startswith("H01:") and "relayed" in m for m in doc["missing"])
