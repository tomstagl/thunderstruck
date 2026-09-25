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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
