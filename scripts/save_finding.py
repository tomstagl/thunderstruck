#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Persist one investigator's JSON, stamped with the bundle hash it came from.

The investigator subagent is read-only by design, so the orchestrating skill
writes its result through here. Stamping the bundle hash is what makes the
next run's cache check meaningful: a finding is reusable exactly when the
bundle that produced it is byte-identical.

    save_finding.py --id H01 < result.json
    save_finding.py --id H01 --from result.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402

# "path:42" or "path:42-118"; anything else stays a bare path
_PATH_LINES = re.compile(r"^(?P<file>.+?):(?P<lines>[0-9]+(?:-[0-9]+)?)\Z")
_COMMIT_PREFIX = re.compile(r"^(?:commit|sha)\s*[:=]\s*", re.IGNORECASE)
_TYPE_ALIASES = {"git": "commit", "sha": "commit"}


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="save_finding.py")
    ap.add_argument("--id", required=True, help="hotspot id, e.g. H01")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--from", dest="src", default=None,
                    help="read JSON from this file instead of stdin")
    ap.add_argument("--failed", action="store_true",
                    help="record the hotspot as analysis_failed instead")
    args = ap.parse_args(argv)

    try:
        repo = c.find_repo_root(args.repo)
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2

    out = c.out_dir(repo)
    bundles = c.load_json(out / "bundles" / "index.json", {}) or {}
    entry = next((b for b in bundles.get("bundles", []) if b["id"] == args.id), None)
    if entry is None:
        c.die(f"{args.id} is not in bundles/index.json — run bundle.py first.")
        return 2

    if args.failed:
        doc = {"hotspot_id": args.id, "file": entry["file"], "findings": [],
               "analysis_failed": True,
               "notes": "investigator produced no usable output"}
    else:
        raw = Path(args.src).read_text(encoding="utf-8") if args.src else sys.stdin.read()
        raw = raw.strip()
        # Models fence JSON out of habit; strip it rather than fail the run.
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            c.die(f"{args.id}: investigator output is not valid JSON ({exc}). "
                  f"Re-run that investigator or record it with --failed.")
            return 2
        if not isinstance(doc, dict):
            c.die(f"{args.id}: expected a JSON object, got {type(doc).__name__}")
            return 2
        rewrites = normalise(doc)
        if rewrites:
            doc["normalised"] = rewrites
        else:
            doc.pop("normalised", None)
        doc.setdefault("hotspot_id", args.id)
        doc.setdefault("file", entry["file"])
        # validate.py owns these; a model echoing them must not pass as validated
        doc.pop("validated_with", None)
        findings = doc.get("findings")
        for f in findings if isinstance(findings, list) else []:
            if isinstance(f, dict):
                for owned in ("key", "content_hash", "catalog_evidence", "evidence_hashes"):
                    f.pop(owned, None)

    doc["bundle_hash"] = entry["bundle_hash"]
    doc["schema"] = c.FINDING_SCHEMA_VERSION
    dest = out / "findings" / f"{args.id}.json"
    c.write_json(dest, doc)
    n = len(doc["findings"]) if isinstance(doc.get("findings"), list) else 0
    print(f"{args.id}: {n} finding(s) -> {dest}")
    for line in doc.get("normalised") or []:
        print(f"  normalised: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
