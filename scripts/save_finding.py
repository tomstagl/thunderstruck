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
    save_finding.py --id H01 --from result.json --fallback --usage '{"output_tokens": 812}'
    save_finding.py --check H01 H02     # saved | missing | failed, one line each
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
import finding_shape as fs  # noqa: E402
from finding_shape import normalise  # noqa: E402,F401  (tests import it from here)

USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens")


def relayed_usage(raw: str) -> dict:
    """The token counts an Agent result reported. Absent stays absent, never 0."""
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--usage is not valid JSON ({exc})") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"--usage: expected a JSON object, got {type(doc).__name__}")
    kept = {k: doc[k] for k in USAGE_KEYS
            if isinstance(doc.get(k), int) and not isinstance(doc[k], bool)}
    if isinstance(doc.get("model"), str):
        kept["model"] = doc["model"]
    return kept


def check(index: dict, findings: Path, ids: list[str]) -> None:
    for hid in ids:
        entry = fs.find_entry(index, hid)
        doc = None
        if entry is not None:
            doc = c.load_json(findings / f"{entry['id']}.json", None)
        if not isinstance(doc, dict) or doc.get("bundle_hash") != entry["bundle_hash"]:
            state = "missing"
        else:
            state = "failed" if doc.get("analysis_failed") else "saved"
        print(f"{hid} {state}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="save_finding.py")
    ap.add_argument("--id", default=None, help="hotspot id, e.g. H01")
    ap.add_argument("--check", nargs="+", metavar="ID", default=None,
                    help="say for each id whether its result reached disk")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--from", dest="src", default=None,
                    help="read JSON from this file instead of stdin")
    ap.add_argument("--failed", action="store_true",
                    help="record the hotspot as analysis_failed instead")
    ap.add_argument("--fallback", action="store_true",
                    help="the orchestrator saved this because the hook did not")
    ap.add_argument("--usage", default=None,
                    help="the Agent result's token usage, as JSON")
    args = ap.parse_args(argv)
    if args.check is not None and args.id is not None:
        ap.error("--check and --id are mutually exclusive")
    if args.check is None and args.id is None:
        ap.error("one of --id or --check is required")

    try:
        repo = c.find_repo_root(args.repo)
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2

    out = c.out_dir(repo)
    bundles = c.load_json(out / "bundles" / "index.json", {}) or {}
    if args.check is not None:
        check(bundles, out / "findings", args.check)
        return 0
    entry = fs.find_entry(bundles, args.id)
    if entry is None:
        c.die(f"{args.id} is not in bundles/index.json — run bundle.py first.")
        return 2

    usage = None
    if args.usage is not None:
        try:
            usage = relayed_usage(args.usage)
        except ValueError as exc:
            c.die(f"{args.id}: {exc}")
            return 2

    if args.failed:
        doc = fs.failed_doc(entry)
    else:
        raw = Path(args.src).read_text(encoding="utf-8") if args.src else sys.stdin.read()
        try:
            doc = fs.shape(fs.parse_result(raw), entry)
        except ValueError as exc:
            c.die(f"{args.id}: {exc}")
            return 2

    dest = out / "findings" / f"{args.id}.json"
    c.write_json(dest, doc)
    notes = {"fallback": True} if args.fallback else {}
    if usage is not None:
        notes["relayed_usage"] = usage
    if notes:
        fs.annotate_record(out, entry, notes)
    n = len(doc["findings"]) if isinstance(doc.get("findings"), list) else 0
    print(f"{args.id}: {n} finding(s) -> {dest}")
    for line in doc.get("normalised") or []:
        print(f"  normalised: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
