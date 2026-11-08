"""The second ground-truth set (#59): provenance, labels, baselines (spec 2026-10-03-second-ground-truth-design.md)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import benchmark as b

ROOT = Path(__file__).resolve().parent.parent
SETS = ROOT / "docs" / "calibration" / "correctness"
CELERY = SETS / "celery"
SECOND = SETS / "trigger-dev"  # the set chosen in Task 1 (spec §1)


def readme_row(name: str) -> str:
    text = (SECOND / "README.md").read_text()
    m = re.search(rf"^\| {re.escape(name)} \| (.+?) \|$", text, re.M)
    assert m, f"README.md has no '| {name} | … |' row"
    return m.group(1).strip()


def readme_commit() -> str:
    m = re.fullmatch(r"`([0-9a-f]{40})`", readme_row("Commit"))
    assert m, "the Commit row is not a backquoted 40-character SHA"
    return m.group(1)


# --- Task 1 -----------------------------------------------------------------
def readme_role() -> str:
    return readme_row("Role")


def test_the_set_is_public_pinned_and_licensed():
    assert re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", readme_row("Repository"))
    readme_commit()
    assert re.fullmatch(r"`\d{4}-\d{2}-\d{2}`", readme_row("Window from"))
    assert readme_role() in ("holdout", "development")
    assert readme_row("Licence")
    assert readme_row("Tests at the pinned commit")
    licences = sorted(p.name for p in (SECOND / "LICENSES").iterdir() if p.is_file())
    assert licences, "LICENSES/ is empty"
    for p in (SECOND / "LICENSES").iterdir():
        assert p.read_text().strip(), f"{p.name} is empty"
