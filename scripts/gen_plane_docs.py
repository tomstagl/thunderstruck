#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Generate skills/stability-catalog/references/planes.md from planes/.

The coverage matrix (#112): one row per plane, one column per Tier A/B
pattern, each cell `R` (a rubric section), `n/a`, `planned` or `MISSING`,
with ` D` where the catalog has a detector for that pattern in one of the
plane's languages. Generated so the matrix can never disagree with the
planes; tests/test_docs_in_sync.py and CI fail the build when it is stale.

    uv run scripts/gen_plane_docs.py          # write
    uv run scripts/gen_plane_docs.py --check  # exit 1 if stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
import fracture_planes as fp  # noqa: E402

BANNER = ("<!-- Generated from planes/ by "
          "scripts/gen_plane_docs.py. Do not edit by hand. -->")

CELL_TEXT = {"rubric": "R", "na": "n/a", "planned": "planned", "missing": "MISSING"}


def has_detector(catalog: dict, plane: fp.Plane, pattern_id: str) -> bool:
    pattern = next((p for p in catalog.get("patterns") or [] if p["id"] == pattern_id), {})
    detectors = pattern.get("detectors") or {}
    return any(detectors.get(c.detector_language(catalog, lang)) for lang in plane.languages)


def cell(catalog: dict, plane: fp.Plane, pattern_id: str) -> str:
    text = CELL_TEXT[fp.cell_state(plane, pattern_id)]
    return text + " D" if has_detector(catalog, plane, pattern_id) else text


def _rule(rule: fp.DetectRule) -> str:
    return f"`{rule.file}`" + (f" containing `{rule.contains}`" if rule.contains else "")


def render(planes: dict[str, fp.Plane], catalog: dict) -> str:
    L = [BANNER, "", "# Fracture planes", "",
         "A plane is stack-specific guidance on what counts as protection for "
         "each Tier A and B pattern.", ""]
    if not planes:
        L.append("No planes are installed.")
        return "\n".join(L)

    ids = fp.tier_ab_ids(catalog)
    L += ["`R`: the rubric has a section for the pattern. `n/a`: the failure "
          "does not exist on this stack. `planned`: a known gap. `MISSING`: "
          "undeclared, which fails the build. ` D`: the catalog has a detector "
          "for the pattern in one of the plane's languages.", "",
          "| Plane | " + " | ".join(ids) + " |",
          "|---|" + "---|" * len(ids)]
    for pid in sorted(planes):
        L.append(f"| `{pid}` | " + " | ".join(cell(catalog, planes[pid], i) for i in ids) + " |")
    L.append("")

    for pid in sorted(planes):
        plane = planes[pid]
        L += [f"## {pid} — {plane.title}", "",
              f"- Maturity: {plane.maturity}",
              f"- Languages: {', '.join(plane.languages)}",
              f"- Active when any tracked file matches: {'; '.join(_rule(r) for r in plane.detect)}"]
        if plane.supersedes:
            L.append(f"- Supersedes: {', '.join(f'`{s}`' for s in plane.supersedes)}")
        L.append("")
        for state, heading in (("na", "Not applicable"), ("planned", "Planned")):
            rows = [(i, plane.cells[i][state]) for i in ids
                    if fp.cell_state(plane, i) == state]
            if rows:
                L += [f"{heading}:", ""] + [f"- {i}: {reason}" for i, reason in rows] + [""]
    return "\n".join(L).rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gen_plane_docs.py")
    ap.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = ap.parse_args(argv)

    root = c.plugin_root()
    catalog = c.load_catalog(root)
    planes, problems = fp.load_planes(root / "planes")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    dest = root / "skills" / "stability-catalog" / "references" / "planes.md"
    body = render(planes, catalog) + "\n"

    if args.check:
        current = dest.read_text(encoding="utf-8") if dest.is_file() else ""
        if current != body:
            print(f"{dest} is stale — run: uv run scripts/gen_plane_docs.py",
                  file=sys.stderr)
            return 1
        print(f"{dest.name} is in sync with planes/")
        return 0

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    print(f"wrote {dest} ({len(body.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
