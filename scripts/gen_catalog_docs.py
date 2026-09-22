#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Generate skills/stability-catalog/references/patterns.md from the catalog.

Kept generated rather than hand-written so the prose a model reads and the
detectors that run can never disagree. tests/test_docs_in_sync.py fails the
build if this output is stale.

    uv run scripts/gen_catalog_docs.py          # write
    uv run scripts/gen_catalog_docs.py --check  # exit 1 if stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402

BANNER = ("<!-- Generated from catalog/stability.yaml by "
          "scripts/gen_catalog_docs.py. Do not edit by hand. -->")


def render(catalog: dict) -> str:
    L = [BANNER, "", "# Stability patterns", "",
         "The failure each pattern prevents, and what its absence looks like "
         "in code. Tiers are defaults; a repository re-prioritises them in "
         f"`{c.PROFILE_FILENAME}`.", ""]

    for tier, title, blurb in (
        ("A", "Tier A",
         "Scanned and reasoned about by default, at full weight."),
        ("B", "Tier B",
         "Scanned and reasoned about by default, at lower weight."),
    ):
        rows = [p for p in catalog["patterns"] if str(p["tier"]).upper() == tier]
        if not rows:
            continue
        L += [f"## {title}", "", blurb, ""]
        for p in sorted(rows, key=lambda r: r["id"]):
            L += [f"### {p['id']} — {p['name']}", ""]
            L.append(f"**Failure if absent.** {str(p.get('failure_if_absent', '')).strip()}")
            L.append("")
            if p.get("metastable_role"):
                L += [f"**Role in a metastable failure.** Usually the "
                      f"*{p['metastable_role']}*.", ""]
            langs = p.get("detectors") or {}
            if langs:
                L.append("**What the detectors look for.**")
                L.append("")
                seen: set[str] = set()
                for dets in langs.values():
                    for d in dets or []:
                        note = d.get("note", "")
                        if note and note not in seen:
                            seen.add(note)
                            L.append(f"- {note}")
                L.append("")
            refs = p.get("references") or []
            if refs:
                L.append("**References.** " + "; ".join(str(r) for r in refs))
                L.append("")

    tier_c = catalog.get("tier_c") or []
    if tier_c:
        L += ["## Tier C — named, not scanned", "",
              "No detectors ship for these. They are here so that a finding "
              "whose evidence supports one has an ID to use.", ""]
        for p in tier_c:
            L.append(f"- **{p['id']} {p['name']}** — {p.get('failure_if_absent', '')}")
        L.append("")

    L += ["## The metastability lens", "",
          "A metastable failure needs three things: a **vulnerable state**, a "
          "**trigger**, and a **sustaining effect** that keeps the system "
          "failing after the trigger is gone. The third is the one that gets "
          "missed, and it is the reason an incident outlives its cause.", "",
          "Typical sustaining effects:", "",
          "- Retries consuming exactly the capacity recovery needs.",
          "- Failed jobs re-queuing at full cost, so the backlog never drains.",
          "- Errors invalidating caches, turning recovery into a miss flood.",
          "- Expensive work regenerated on every failed request.", "",
          "When reviewing code that calls an external system, ask the question "
          "explicitly: *once this fails, what keeps it failing?* A clean answer "
          "of \"nothing — it drains and recovers\" is worth stating.", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gen_catalog_docs.py")
    ap.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = ap.parse_args(argv)

    root = c.plugin_root()
    catalog = c.load_catalog(root)
    dest = root / "skills" / "stability-catalog" / "references" / "patterns.md"
    body = render(catalog) + "\n"

    if args.check:
        current = dest.read_text(encoding="utf-8") if dest.is_file() else ""
        if current != body:
            print(f"{dest} is stale — run: uv run scripts/gen_catalog_docs.py",
                  file=sys.stderr)
            return 1
        print(f"{dest.name} is in sync with the catalog")
        return 0

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    print(f"wrote {dest} ({len(body.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
