"""Turn an investigator's answer into the finding file thunderstruck stores.

Shared by save_finding.py and the SubagentStop hook (capture_finding.py), so
a finding saved either way is byte-identical. The hook runs on bare python3
under the guardrail's constraints, so this module imports the stdlib only:
no pyyaml, no _common.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

FINDING_SCHEMA_VERSION = "thunderstruck.finding/v2"

# "path:42" or "path:42-118"; anything else stays a bare path
_PATH_LINES = re.compile(r"^(?P<file>.+?):(?P<lines>[0-9]+(?:-[0-9]+)?)\Z")
_COMMIT_PREFIX = re.compile(r"^(?:commit|sha)\s*[:=]\s*", re.IGNORECASE)
_TYPE_ALIASES = {"git": "commit", "sha": "commit"}
# Written by validate.py or a later stage, never by a model (spec §3.4).
OWNED_FINDING_KEYS = ("key", "content_hash", "catalog_evidence", "evidence_hashes",
                      "check", "history", "confidence_claimed")


def _lines_of(obj: dict) -> str | None:
    for k in ("lines", "line"):
        v = obj.get(k)
        if isinstance(v, int) and not isinstance(v, bool):
            return str(v)
        if isinstance(v, str) and re.fullmatch(r"[0-9]+(?:-[0-9]+)?", v.strip()):
            return v.strip()
    return None


def normalise(doc: dict) -> list[str]:
    """Repair shapes whose meaning is unambiguous, and say what was rewritten.

    Only structure moves: a key is renamed, a split ref is joined, a known
    alias becomes the one type name. Nothing is invented and nothing is
    dropped, so a missing field or an unknown type still reaches validate.py,
    which resolves every ref exactly as it would have.
    """
    done: list[str] = []
    if "findings" not in doc and isinstance(doc.get("hypotheses"), list):
        doc["findings"] = doc.pop("hypotheses")
        done.append("renamed top-level 'hypotheses' to 'findings'")
    findings = doc.get("findings")
    for i, f in enumerate(findings if isinstance(findings, list) else []):
        if not isinstance(f, dict):
            continue
        where = f"findings[{i}]"
        loc = f.get("location")
        if isinstance(loc, str) and loc.strip():
            m = _PATH_LINES.match(loc.strip())
            f["location"] = ({"file": m["file"], "lines": m["lines"]} if m
                             else {"file": loc.strip()})
            done.append(f"{where}.location {loc!r} -> {f['location']}")
        evidence = f.get("evidence")
        for j, ev in enumerate(evidence if isinstance(evidence, list) else []):
            if not isinstance(ev, dict):
                continue
            ew = f"{where}.evidence[{j}]"
            etype = ev.get("type")
            if isinstance(etype, str) and etype.strip().lower() in _TYPE_ALIASES:
                ev["type"] = _TYPE_ALIASES[etype.strip().lower()]
                done.append(f"{ew}.type {etype!r} -> {ev['type']!r}")
            ref = ev.get("ref")
            if ev.get("type") == "code":
                src = ref if isinstance(ref, dict) else ev if ref is None else None
                if src is not None and isinstance(src.get("file"), str) and src["file"].strip():
                    lines = _lines_of(src)
                    if lines is not None:
                        ev["ref"] = f"{src['file'].strip()}:{lines}"
                        for k in ("file", "line", "lines"):
                            if src is ev:
                                ev.pop(k, None)
                        done.append(f"{ew}.ref joined into {ev['ref']!r}")
            elif ev.get("type") == "commit":
                if ref is None and isinstance(ev.get("sha"), str):
                    ref = ev.pop("sha")
                    ev["ref"] = ref
                    done.append(f"{ew}.sha moved to ref")
                if isinstance(ref, str) and _COMMIT_PREFIX.match(ref.strip()):
                    ev["ref"] = _COMMIT_PREFIX.sub("", ref.strip())
                    done.append(f"{ew}.ref {ref!r} -> {ev['ref']!r}")
    return done


def parse_result(raw: str) -> dict:
    """An investigator's answer as one JSON object; ValueError otherwise."""
    raw = raw.strip()
    # Models fence JSON out of habit; strip it rather than fail the run.
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"investigator output is not valid JSON ({exc}). "
                         f"Re-run that investigator or record it with --failed.") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"expected a JSON object, got {type(doc).__name__}")
    return doc


def _stamp(doc: dict, entry: dict) -> dict:
    doc["bundle_hash"] = entry["bundle_hash"]
    doc["schema"] = FINDING_SCHEMA_VERSION
    return doc


def shape(doc: dict, entry: dict) -> dict:
    """Normalise, drop validator-owned fields and stamp the bundle hash."""
    rewrites = normalise(doc)
    if rewrites:
        doc["normalised"] = rewrites
    else:
        doc.pop("normalised", None)
    doc.setdefault("hotspot_id", entry["id"])
    doc.setdefault("file", entry["file"])
    doc.pop("validated_with", None)
    findings = doc.get("findings")
    for f in findings if isinstance(findings, list) else []:
        if isinstance(f, dict):
            for owned in OWNED_FINDING_KEYS:
                f.pop(owned, None)
    return _stamp(doc, entry)


def failed_doc(entry: dict) -> dict:
    return _stamp({"hotspot_id": entry["id"], "file": entry["file"], "findings": [],
                   "analysis_failed": True,
                   "notes": "investigator produced no usable output"}, entry)


def write_json_atomic(path: Path, payload: Any) -> None:
    """The bytes _common.write_json writes, never through a symlink."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise OSError(f"refusing to write through a symlinked directory: {path.parent}")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = (json.dumps(payload, indent=2, sort_keys=False) + "\n").encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def find_entry(index: dict, hotspot_id: Any) -> dict | None:
    """The bundles/index.json entry whose id is exactly hotspot_id."""
    if not isinstance(hotspot_id, str):
        return None
    bundles = index.get("bundles") if isinstance(index, dict) else None
    for b in bundles if isinstance(bundles, list) else []:
        if isinstance(b, dict) and b.get("id") == hotspot_id:
            return b
    return None


def _record(out: Path, entry: dict) -> tuple[Path, dict]:
    path = Path(out) / "agents" / f"{entry['id']}.json"
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = None
    if not isinstance(rec, dict) or rec.get("bundle_hash") != entry["bundle_hash"] \
            or not isinstance(rec.get("agents"), list):
        rec = {"hotspot_id": entry["id"], "bundle_hash": entry["bundle_hash"], "agents": []}
    return path, rec


def record_agent(out: Path, entry: dict, agent: dict, reset: bool = False) -> None:
    """Append to agents/<ID>.json, starting afresh for a different bundle or
    when reset (the record is from an earlier scan of the same bundle)."""
    path, rec = _record(out, entry)
    if reset:
        rec = {"hotspot_id": entry["id"], "bundle_hash": entry["bundle_hash"], "agents": []}
    rec["agents"].append(agent)
    write_json_atomic(path, rec)


def annotate_record(out: Path, entry: dict, fields: dict) -> None:
    """Set fields on agents/<ID>.json, starting afresh for a different bundle."""
    path, rec = _record(out, entry)
    rec.update(fields)
    write_json_atomic(path, rec)
