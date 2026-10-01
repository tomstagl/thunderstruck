#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Render .thunderstruck/report.json into a single-file HTML reader.

    uv run scripts/report_html.py [--repo PATH]

Writes .thunderstruck/report.html from templates/report.html. The report JSON
is embedded as data in a <script type="application/json"> block; the template
inserts every value with textContent, so repository text stays inert (#28).
No network access, no external assets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "report.html"
PLACEHOLDER = "__THUNDERSTRUCK_REPORT__"


def embed(report: dict) -> str:
    """JSON that cannot close or comment out its <script> element."""
    raw = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    return (raw.replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render(report: dict, template: str) -> str:
    if template.count(PLACEHOLDER) != 1:
        raise c.ThunderstruckError(f"{TEMPLATE.name}: expected exactly one {PLACEHOLDER}")
    return template.replace(PLACEHOLDER, embed(report))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="report_html.py", description="render report.html")
    ap.add_argument("--repo", default=None)
    args = ap.parse_args(argv)
    try:
        repo = c.find_repo_root(args.repo)
        out = c.out_dir(repo)
        report = c.load_json(out / "report.json")
        if not report:
            raise c.ThunderstruckError("no report.json — run report.py first.")
        html = render(report, TEMPLATE.read_text(encoding="utf-8"))
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2
    dest = out / "report.html"
    dest.write_text(html, encoding="utf-8")
    print(f"{len(report.get('findings') or [])} finding(s) -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
