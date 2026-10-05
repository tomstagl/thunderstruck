#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""SubagentStop hook: save a thunderstruck investigator's result to disk.

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
   .thunderstruck/findings/ and .thunderstruck/agents/.
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


def main(stdin_text: str) -> None:
    if len(stdin_text) > MAX_PAYLOAD:
        return
    payload = json.loads(stdin_text)
    if not isinstance(payload, dict):
        return
    if not str(payload.get("agent_type", "")).endswith("thunderstruck-investigator"):
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
    previous = _load(dest)
    kind = "first"
    if previous and previous.get("bundle_hash") == entry["bundle_hash"]:
        finding_shape.write_json_atomic(out / "agents" / f"{entry['id']}.attempt1.json", previous)
        kind = "repair" if _listed_invalid(out, entry["id"]) else "respawn"
    finding_shape.write_json_atomic(dest, finding_shape.shape(doc, entry))
    agent = {k: payload.get(k) for k in ("agent_id", "session_id", "transcript_path", "stop_reason")}
    finding_shape.record_agent(out, entry, {**agent, "kind": kind})


if __name__ == "__main__":
    try:
        main(sys.stdin.read(MAX_PAYLOAD + 1))
    except BaseException:
        pass
    sys.exit(0)
