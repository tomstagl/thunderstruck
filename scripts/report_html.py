#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Render .thunderstruck/report.json into a single-file HTML reader.

    uv run scripts/report_html.py [--repo PATH]

Writes .thunderstruck/report.html from templates/report.html. The report JSON
is embedded as data in a <script type="application/json"> block; the template
inserts every value with textContent, so repository text stays inert (#28).
A Content-Security-Policy allows only the template's own script, by hash.
No network access, no external assets. Standard library only.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "report.html"
PLACEHOLDER = "__THUNDERSTRUCK_REPORT__"
HASH_PLACEHOLDER = "__THUNDERSTRUCK_SCRIPT_HASH__"
APP_SCRIPT = re.compile(r'<script id="thunderstruck-app">(.*?)</script>', re.S)


def embed(report: dict) -> str:
    """JSON that cannot close or comment out its <script> element."""
    raw = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    return (raw.replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def page_data(report: dict) -> dict:
    """The report as the page sees it: the repository's name, never its local path."""
    page = copy.deepcopy(report)
    repo = page.get("repo")
    if isinstance(repo, dict):
        root = repo.pop("root", None)
        repo["name"] = Path(str(root)).name if root else repo.get("name")
    return page


def script_hash(template: str) -> str:
    """The CSP source for the template's one application script."""
    scripts = APP_SCRIPT.findall(template)
    if len(scripts) != 1:
        raise c.ThunderstruckError(f"{TEMPLATE.name}: expected exactly one "
                                   f'<script id="thunderstruck-app">, found {len(scripts)}')
    digest = hashlib.sha256(scripts[0].encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def render(page: dict, template: str) -> str:
    for placeholder in (PLACEHOLDER, HASH_PLACEHOLDER):
        if template.count(placeholder) != 1:
            raise c.ThunderstruckError(f"{TEMPLATE.name}: expected exactly one {placeholder}")
    # the hash first: the data inserted after it is never searched again
    html = template.replace(HASH_PLACEHOLDER, script_hash(template))
    before, after = html.split(PLACEHOLDER)
    return before + embed(page) + after


def _write_atomic(dest: Path, text: str) -> None:
    """A failed write never leaves a truncated page behind."""
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="report_html.py", description="render report.html")
    ap.add_argument("--repo", default=None)
    args = ap.parse_args(argv)
    try:
        repo = c.find_repo_root(args.repo)
        out = c.out_dir(repo)
        report = c.load_json(out / "report.json")
        if not isinstance(report, dict) or not report:
            raise c.ThunderstruckError("no report.json — run report.py first.")
        if report.get("schema") != c.REPORT_SCHEMA_VERSION:
            raise c.ThunderstruckError(
                f"report.json has schema {report.get('schema')!r}; this version renders "
                f"{c.REPORT_SCHEMA_VERSION!r}. Re-run the scan.")
        try:
            template = TEMPLATE.read_text(encoding="utf-8")
        except OSError:
            raise c.ThunderstruckError(f"template not found: {TEMPLATE}") from None
        html = render(page_data(report), template)
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2
    dest = out / "report.html"
    _write_atomic(dest, html)
    size = len(html.encode("utf-8")) / 1024
    print(f"report.html: {dest} ({size:.1f} KB, "
          f"{len(report.get('findings') or [])} finding(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
