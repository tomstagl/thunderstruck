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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
import finding_shape as fs  # noqa: E402
from finding_shape import normalise  # noqa: E402,F401  (tests import it from here)


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
    entry = fs.find_entry(bundles, args.id)
    if entry is None:
        c.die(f"{args.id} is not in bundles/index.json — run bundle.py first.")
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
    n = len(doc["findings"]) if isinstance(doc.get("findings"), list) else 0
    print(f"{args.id}: {n} finding(s) -> {dest}")
    for line in doc.get("normalised") or []:
        print(f"  normalised: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
