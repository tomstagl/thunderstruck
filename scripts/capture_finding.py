#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""SubagentStop hook: save a thunderstruck investigator's or skeptic's result to disk.

The orchestrator used to re-type every result into save_finding.py, and
results that never reached it were paid for twice (#5). This hook takes the
investigator's last message straight from Claude Code and writes the same
file save_finding.py would.

Contract, the guardrail's:

1. **It never fails.** Exit code is always 0; any error is a silent no-op.
2. **It is quiet.** It prints nothing, so nothing reaches the model.
3. **It is stdlib only** (plus finding_shape.py), so it runs on bare python3.
4. **It writes only where the index says.** The message is model output that
   read the scanned repository. The destination comes from
   bundles/index.json, never from the payload, and only under
   .thunderstruck/findings/ and .thunderstruck/agents/. A skeptic's verdict
   goes under .thunderstruck/checks/, by a key from checks/plan.json (#37).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import finding_shape  # noqa: E402

MAX_PAYLOAD = 1_000_000


def _root(cwd: str) -> Path | None:
    p = Path(cwd).resolve()
    for d in (p, *p.parents):
        if (d / ".git").exists():
            return d
    return None


def _load(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _listed_invalid(out: Path, hotspot_id: str) -> bool:
    results = (_load(out / "validation.json") or {}).get("results")
    return any(isinstance(r, dict) and r.get("hotspot_id") == hotspot_id
               and r.get("valid") is False
               for r in (results if isinstance(results, list) else []))


def _capture_skeptic(payload: dict) -> None:
    root = _root(payload.get("cwd") or os.getcwd())
    out = root / ".thunderstruck" if root else None
    plan_path = out / "checks" / "plan.json" if out else None
    if not plan_path or not plan_path.is_file():
        return
    message = payload.get("last_assistant_message")
    if not isinstance(message, str):
        return
    doc = finding_shape.parse_result(message)
    plan = json.loads(plan_path.read_text("utf-8"))
    entry = finding_shape.find_plan_entry(plan, doc.get("key"))
    if entry is None:
        return
    dest = out / "checks" / "results" / f"{entry['key']}.json"
    prior = _load(dest)
    kind = "respawn" if prior and prior.get("scan") == plan["generated_at"] else "first"
    finding_shape.write_json_atomic(dest, finding_shape.stamp_verdict(doc, plan, entry))
    agent = {k: payload.get(k) for k in ("agent_id", "session_id", "transcript_path", "stop_reason")}
    finding_shape.record_skeptic(out, plan, entry, {**agent, "kind": kind})


def main(stdin_text: str) -> None:
    if len(stdin_text) > MAX_PAYLOAD:
        return
    payload = json.loads(stdin_text)
    if not isinstance(payload, dict):
        return
    agent_type = str(payload.get("agent_type", ""))
    if agent_type.endswith("thunderstruck-skeptic"):
        _capture_skeptic(payload)
        return
    if not agent_type.endswith("thunderstruck-investigator"):
        return
    root = _root(payload.get("cwd") or os.getcwd())
    out = root / ".thunderstruck" if root else None
    index_path = out / "bundles" / "index.json" if out else None
    if not index_path or not index_path.is_file():
        return
    message = payload.get("last_assistant_message")
    if not isinstance(message, str):
        return
    doc = finding_shape.parse_result(message)
    entry = finding_shape.find_entry(json.loads(index_path.read_text("utf-8")),
                                     doc.get("hotspot_id"))
    if entry is None:
        return
    dest = out / "findings" / f"{entry['id']}.json"
    # A finding with this bundle hash may be from an earlier scan of an
    # unchanged repo (findings/ deleted, or requeued under newer rules). Only
    # an agent already recorded from this session makes this a second delivery.
    rec = _load(out / "agents" / f"{entry['id']}.json") or {}
    earlier = [a for a in rec.get("agents") or [] if isinstance(a, dict)] \
        if rec.get("bundle_hash") == entry["bundle_hash"] else []
    this_run = any(a.get("session_id") == payload.get("session_id") for a in earlier)
    previous = _load(dest)
    kind = "first"
    if this_run and previous and previous.get("bundle_hash") == entry["bundle_hash"]:
        finding_shape.write_json_atomic(out / "agents" / f"{entry['id']}.attempt1.json", previous)
        kind = "repair" if _listed_invalid(out, entry["id"]) else "respawn"
    finding_shape.write_json_atomic(dest, finding_shape.shape(doc, entry))
    agent = {k: payload.get(k) for k in ("agent_id", "session_id", "transcript_path", "stop_reason")}
    finding_shape.record_agent(out, entry, {**agent, "kind": kind},
                               reset=bool(earlier) and not this_run)


if __name__ == "__main__":
    try:
        main(sys.stdin.read(MAX_PAYLOAD + 1))
    except BaseException:
        pass
    sys.exit(0)
