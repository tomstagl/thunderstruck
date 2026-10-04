#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""`claude plugin validate . --strict`, allowing one known warning.

This repository is both the plugin and its development checkout, so
CLAUDE.md sits at the plugin root. Claude Code warns that a CLAUDE.md there
is not loaded as plugin context, which is true and intended: it is context
for working on thunderstruck, not something users of the plugin receive.
`--strict` turns that warning into a failure.

This runs the same validation with `--json` and passes when there are no
errors and every warning is that one. Any other warning or error fails, so
`--strict` keeps its meaning for everything else.

    uv run scripts/validate_plugin.py          # exit 0 clean, 1 failed, 2 not run
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KNOWN_WARNINGS = {
    ("CLAUDE.md", "CLAUDE.md at the plugin root is not loaded as project context."),
}


def _known(file: str, message: str) -> bool:
    name = Path(file).name
    return any(name == f and message.startswith(m) for f, m in KNOWN_WARNINGS)


def problems(report: dict) -> list[str]:
    """Every error, and every warning that is not known, as one line each."""
    out = []
    sections = [report.get("manifest") or {}, *(report.get("contents") or [])]
    for section in sections:
        file = str(section.get("file") or "")
        for e in section.get("errors") or []:
            out.append(f"error: {file}: {e.get('path')}: {e.get('message')}")
        for w in section.get("warnings") or []:
            message = str(w.get("message") or "")
            if not _known(file, message):
                out.append(f"warning: {file}: {w.get('path')}: {message}")
    return out


def main() -> int:
    claude = shutil.which("claude")
    if claude is None:
        print("not run: `claude` is not on PATH", file=sys.stderr)
        return 2
    proc = subprocess.run(
        [claude, "plugin", "validate", str(ROOT), "--strict", "--json"],
        capture_output=True, text=True, check=False,
    )
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        sys.stderr.write(proc.stdout + proc.stderr)
        print("failed: the validator's report is not JSON", file=sys.stderr)
        return 1
    found = problems(report)
    for line in found:
        print(line)
    if found:
        print(f"failed: {len(found)} problem(s)")
        return 1
    print("passed (the known CLAUDE.md warning is allowed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
