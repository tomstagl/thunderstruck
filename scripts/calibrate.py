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
stderr: hit count per detector. Test directories are skipped unless
--include-tests, matching signals.py's defaults.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
from detectors import run_detectors  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--lang", required=True)
    ap.add_argument("--patterns", required=True, help="comma-separated pattern ids")
    ap.add_argument("--include-tests", action="store_true")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    catalog = c.load_catalog(PLUGIN_ROOT)
    langmap = c.language_map(catalog)
    filters = c.Filters(include_tests=args.include_tests)
    wanted = [p.strip() for p in args.patterns.split(",") if p.strip()]

    rows: list[tuple[str, str, int, str]] = []
    for rel in sorted(p for p in c.git(repo, "ls-files").split("\n") if p):
        if c.detect_language(rel, langmap) != args.lang or filters.excludes_path(rel):
            continue
        text = c.read_text(repo / rel)
        if text is None:
            continue
        for h in run_detectors(catalog, rel, text, args.lang, pattern_ids=wanted):
            rows.append((h.detector_id, h.file, h.line, h.snippet))

    rows.sort()
    for det, rel, line, snippet in rows:
        print(f"{det}\t{rel}:{line}\t{snippet}")
    for det, n in sorted(Counter(r[0] for r in rows).items()):
        print(f"{n:5d}  {det}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
