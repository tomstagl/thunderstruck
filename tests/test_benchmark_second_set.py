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


# --- Task 2 -----------------------------------------------------------------
# CI cannot know the labeller's $HOME or work directory; the check for those is
# Step 5's grep. A per-user macOS temp directory never appears in upstream source.
LOCAL_PATH = re.compile(r"/var/folders/")


def report() -> dict:
    return json.loads((SECOND / "scan" / "report.json").read_text())


def test_the_scan_is_of_the_pinned_commit_with_the_recorded_scope():
    r = report()
    assert r["repo"]["head"] == readme_commit()
    assert r["repo"]["root"] == "<repo>"
    for name in ("hotspots.json", "validation.json", "catalog-brief.md", "profile.toml"):
        assert (SECOND / "scan" / name).is_file(), name
    hs = json.loads((SECOND / "scan" / "hotspots.json").read_text())
    assert hs["config"]["profile"] is True
    assert hs["repo"]["root"] == "<repo>"
    assert hs["window"]["since"] == readme_row("Window from").strip("`")  # spec §4.2
    assert readme_row("Scan").startswith("`/thunderstruck-scan --top ")
    assert readme_row("Plugin")
    assert readme_row("Investigator model")


def test_the_scan_has_enough_valid_findings():
    r = report()
    assert r["counts"]["findings"] >= 15            # spec §4.2
    assert r["counts"]["findings"] == len(r["findings"])
    assert all(f["key"] for f in r["findings"])
    assert {f["hotspot_id"] for f in r["findings"]} <= {h["id"] for h in r["hotspots"]}


def test_no_local_path_is_checked_in():
    leaks = [str(p.relative_to(SECOND)) for p in SECOND.rglob("*")
             if p.is_file() and LOCAL_PATH.search(p.read_text(errors="ignore"))]
    assert leaks == []
