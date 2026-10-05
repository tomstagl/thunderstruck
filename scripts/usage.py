#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Measure what a scan consumed, from Claude Code's own transcripts.

  orchestrator   the session transcript, from hotspots.json's generated_at
                 to now, so earlier conversation is not charged to the scan
  investigators  every subagent transcript the SubagentStop hook recorded
                 in agents/<ID>.json for this run's bundles

Writes .thunderstruck/usage.json: token counts by type and model, and one
weighted total (Claude Sonnet 5.5 input = 1, _common.TOKEN_WEIGHTS). Only
counts, model names, ids and timestamps are read from a transcript; no text
from the conversation is written anywhere. Whatever could not be measured is
named in `missing`, never left out of a total silently.

    uv run scripts/usage.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402

BUCKETS = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")
_DATED = re.compile(r"-\d{8}\Z")


class Entries(list):
    """Distinct API calls from one transcript, and how many lines were unreadable."""
    skipped = 0


def projects_root() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"


def safe_transcript(path: str | Path | None) -> Path | None:
    """The resolved path if it is a .jsonl under the projects root, else None."""
    if not isinstance(path, (str, Path)) or not str(path):
        return None
    try:
        resolved = Path(path).resolve()
        root = projects_root().resolve()
    except (OSError, RuntimeError):
        return None
    if resolved.suffix != ".jsonl" or not resolved.is_relative_to(root):
        return None
    return resolved


def _when(ts: object) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        when = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def read_entries(path: Path, since: str | None = None,
                 until: str | None = None) -> Entries | None:
    """One {"model", "usage"} per distinct API response, or None if unreadable."""
    lo, hi = _when(since), _when(until)
    by_id: dict[str, dict] = {}
    entries = Entries()
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    entries.skipped += 1
                    continue
                if not isinstance(row, dict) or row.get("type") != "assistant":
                    continue
                msg = row.get("message")
                if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                    continue
                model = msg.get("model")
                if not isinstance(model, str) or model == "<synthetic>":
                    continue
                if lo or hi:
                    when = _when(row.get("timestamp"))
                    if when is None or (lo and when < lo) or (hi and when > hi):
                        continue
                key = msg.get("id") or row.get("requestId")
                entry = {"model": model, "usage": msg["usage"]}
                if isinstance(key, str) and key:
                    by_id[key] = entry  # one response, written as several blocks
                else:
                    entries.append(entry)
    except (OSError, UnicodeDecodeError):
        return None
    entries.extend(by_id.values())
    return entries


def _int(v: object) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def split(usage: dict) -> dict[str, int]:
    """The five weighted buckets; a cache write without a TTL counts as 5m."""
    out = {b: 0 for b in BUCKETS}
    out["input"] = _int(usage.get("input_tokens"))
    out["cache_read"] = _int(usage.get("cache_read_input_tokens"))
    out["output"] = _int(usage.get("output_tokens"))
    detail = usage.get("cache_creation")
    if isinstance(detail, dict) and ("ephemeral_5m_input_tokens" in detail
                                     or "ephemeral_1h_input_tokens" in detail):
        out["cache_write_5m"] = _int(detail.get("ephemeral_5m_input_tokens"))
        out["cache_write_1h"] = _int(detail.get("ephemeral_1h_input_tokens"))
    else:
        out["cache_write_5m"] = _int(usage.get("cache_creation_input_tokens"))
    return out


def _weights(model: str) -> dict[str, float] | None:
    # A dated id (claude-haiku-4-5-20251001) is the same model as its alias.
    return c.TOKEN_WEIGHTS.get(model) or c.TOKEN_WEIGHTS.get(_DATED.sub("", model))


def weighted(model: str, buckets: dict[str, int]) -> int | None:
    w = _weights(model)
    if w is None:
        return None
    return round(sum(w[b] * buckets.get(b, 0) for b in BUCKETS))


def tally(entries: list[dict], missing: list[str] | None = None) -> dict:
    by_model: dict[str, dict[str, int]] = {}
    for e in entries:
        row = by_model.setdefault(e["model"], {b: 0 for b in BUCKETS})
        for b, n in split(e["usage"]).items():
            row[b] += n
    out: dict[str, dict] = {}
    for model in sorted(by_model):
        w = weighted(model, by_model[model])
        out[model] = {**by_model[model], "weighted": w}
        line = f"model {model} has no weights; its tokens are not in the total"
        if w is None and missing is not None and line not in missing:
            missing.append(line)
    return {"calls": len(entries), "by_model": out}


def _total(t: dict) -> int:
    return sum(row["weighted"] or 0 for row in t["by_model"].values())


def _relayed(rec: dict) -> dict | None:
    usage = rec.get("relayed_usage")
    if not isinstance(usage, dict):
        return None
    model = usage.get("model") if isinstance(usage.get("model"), str) else "unknown"
    return {"model": c.MODEL_ALIASES.get(model, model), "usage": usage}


def build(repo: Path, now: str) -> dict:
    out = c.out_dir(repo)
    hotspots = c.load_json(out / "hotspots.json", None)
    if not isinstance(hotspots, dict) or "generated_at" not in hotspots:
        raise c.ThunderstruckError("no hotspots.json: run signals.py first")
    since = hotspots["generated_at"]
    index = c.load_json(out / "bundles" / "index.json", {}) or {}
    missing: list[str] = []
    inv_entries: list[dict] = []
    by_hotspot: dict[str, dict] = {}
    agents = respawns = repairs = fallback_saves = 0
    sessions: list[str] = []

    for b in index.get("bundles") or []:
        if not isinstance(b, dict) or b.get("cached"):
            continue
        hid = b.get("id")
        rec = c.load_json(out / "agents" / f"{hid}.json", None)
        if not isinstance(rec, dict) or rec.get("bundle_hash") != b.get("bundle_hash"):
            missing.append(f"{hid}: no agent record, the hook did not fire")
            continue
        listed = [a for a in rec.get("agents") or [] if isinstance(a, dict)]
        fallback_saves += rec.get("fallback") is True
        hs_entries: list[dict] = []
        relayed_used = False
        for a in listed:
            kind = a.get("kind")
            respawns += kind == "respawn"
            repairs += kind == "repair"
            session = safe_transcript(a.get("transcript_path"))
            if session is not None:
                sessions.append(str(session))
            sub = None
            if session is not None and isinstance(a.get("agent_id"), str):
                sub = safe_transcript(session.with_suffix("") / "subagents"
                                      / f"agent-{a['agent_id']}.jsonl")
            entries = read_entries(sub) if sub is not None else None
            if entries is None:
                relayed = None if relayed_used else _relayed(rec)
                if relayed is not None:
                    relayed_used = True
                    hs_entries.append(relayed)
                    missing.append(f"{hid}: subagent transcript not readable, "
                                   f"used the usage the orchestrator relayed")
                else:
                    missing.append(f"{hid}: subagent transcript not readable")
                continue
            if entries.skipped:
                missing.append(f"{hid}: {entries.skipped} line(s) of a subagent "
                               f"transcript were not readable")
            hs_entries.extend(entries)
        n_agents = len(listed)
        if not listed:
            relayed = _relayed(rec)
            if relayed is not None:
                hs_entries.append(relayed)
                n_agents = 1
            else:
                missing.append(f"{hid}: no agent recorded")
        agents += n_agents
        inv_entries.extend(hs_entries)
        hs = tally(hs_entries)
        by_hotspot[hid] = {"agents": n_agents, "calls": hs["calls"], "weighted": _total(hs)}

    investigators = tally(inv_entries, missing)
    orch_entries = None
    for path in dict.fromkeys(sessions):
        orch_entries = read_entries(Path(path), since, now)
        if orch_entries is not None:
            break
    if orch_entries is None:
        missing.append("orchestrator: session transcript not readable")
        orchestrator = tally([])
    else:
        if orch_entries.skipped:
            missing.append(f"orchestrator: {orch_entries.skipped} line(s) of the session "
                           f"transcript were not readable")
        orchestrator = tally(orch_entries, missing)

    read_any = bool(inv_entries) or bool(orch_entries)
    source = "transcripts" if not missing else "partial" if read_any else "unavailable"
    return {
        "schema": c.USAGE_SCHEMA,
        "source": source,
        "window": {"from": since, "to": now},
        "orchestrator": orchestrator,
        "investigators": {"agents": agents, "respawns": respawns, "repairs": repairs,
                          "fallback_saves": fallback_saves, **investigators,
                          "by_hotspot": by_hotspot},
        "total_weighted": _total(orchestrator) + _total(investigators),
        "missing": missing,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="usage.py")
    ap.add_argument("--repo", default=None)
    args = ap.parse_args(argv)
    try:
        repo = c.find_repo_root(args.repo)
        doc = build(repo, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2
    dest = c.out_dir(repo) / "usage.json"
    c.write_json(dest, doc)
    print(f"usage: {doc['source']}, ~{round(doc['total_weighted'] / 1000)}k "
          f"weighted tokens -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
