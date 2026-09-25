#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Detector calibration sweep.

Runs the selected patterns' detectors over *every* tracked file of a
repository in one language, not just the ranked hotspots signals.py keeps,
so a detector batch can be judged against code nobody wrote for the test.

    uv run scripts/calibrate.py --repo /path/to/repo --lang java --patterns S01,S27

stdout: one `detector_id<TAB>file:line<TAB>snippet` line per hit, sorted.
stderr: hit count per detector. With --summary, stdout is instead a JSON
document of counts per detector and nothing else, safe to paste into a
public issue: `--lang all --patterns all --summary`. Test directories are skipped unless
--include-tests, matching signals.py's defaults.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
from detectors import run_detectors  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


SUMMARY_SCHEMA = "thunderstruck.calibration-summary/v1"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--lang", required=True, help="a catalog language, or `all`")
    ap.add_argument("--patterns", required=True,
                    help="comma-separated pattern ids, or `all` for every scanned pattern")
    ap.add_argument("--include-tests", action="store_true")
    ap.add_argument("--summary", action="store_true",
                    help="print only counts per detector as JSON: no path, snippet, "
                         "SHA or repository name, so it is safe to share publicly")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    catalog = c.load_catalog(PLUGIN_ROOT)
    langmap = c.language_map(catalog)
    filters = c.Filters(include_tests=args.include_tests)
    langs = (sorted(catalog.get("languages") or {}) if args.lang == "all" else [args.lang])
    if args.patterns == "all":
        wanted = [p["id"] for p in catalog["patterns"] if p.get("tier") in ("A", "B")]
    else:
        wanted = [p.strip() for p in args.patterns.split(",") if p.strip()]

    rows: list[tuple[str, str, int, str]] = []
    swept: Counter = Counter()
    for rel in sorted(p for p in c.git(repo, "ls-files").split("\n") if p):
        lang = c.detect_language(rel, langmap)
        if lang not in langs or filters.excludes_path(rel):
            continue
        text = c.read_text(repo / rel)
        if text is None:
            continue
        swept[lang] += 1
        for h in run_detectors(catalog, rel, text, lang, pattern_ids=wanted):
            rows.append((h.detector_id, h.file, h.line, h.snippet))

    if args.summary:
        print(json.dumps(summarise(rows, swept, catalog), indent=2))
        return 0

    rows.sort()
    for det, rel, line, snippet in rows:
        print(f"{det}\t{rel}:{line}\t{snippet}")
    for det, n in sorted(Counter(r[0] for r in rows).items()):
        print(f"{n:5d}  {det}", file=sys.stderr)
    return 0


def summarise(rows: list[tuple[str, str, int, str]], swept: Counter, catalog: dict) -> dict:
    """Counts only. Detector ids and language names come from the catalog, so
    nothing in the output was written by the scanned repository."""
    total = sum(swept.values())
    per_det: dict[str, dict] = {}
    for det in sorted({r[0] for r in rows}):
        mine = [r for r in rows if r[0] == det]
        per_det[det] = {"hits": len(mine), "files": len({r[1] for r in mine}),
                        "hits_per_1k_files": round(1000 * len(mine) / total, 2) if total else 0.0}
    catalog_file = PLUGIN_ROOT / "catalog" / "stability.yaml"
    return {"schema": SUMMARY_SCHEMA,
            "catalog_hash": c.sha256_file(catalog_file),
            "catalog_version": catalog.get("version"),
            "files_swept": dict(sorted(swept.items())),
            "detectors": per_det}


if __name__ == "__main__":
    sys.exit(main())
