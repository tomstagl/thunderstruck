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


# --- Task 3 -----------------------------------------------------------------
DEP_PLACEHOLDERS = ("<node_modules>/", "<gradle-cache>/")


def labels() -> dict:
    return b.load_label_sets([CELERY / "labels.json", SECOND / "labels.json"])[1]


def ac2_count(set_: dict) -> int:
    return sum(1 for lb in set_["labels"]
               if lb["basis"] == "executed"
               or (lb["basis"] == "read" and any(d in (lb.get("established_by") or "") for d in DEP_PLACEHOLDERS)))


def test_the_set_validates_beside_celery_with_the_recorded_role():
    s = labels()
    assert s["role"] == readme_role()
    assert s["commit"] == report()["repo"]["head"] == readme_commit()
    assert s["repo"] == readme_row("Repository").removeprefix("https://github.com/")


def test_every_finding_is_labelled_once_and_nothing_else():
    keys = [f["key"] for f in report()["findings"]]
    assert len(keys) == len(set(keys))
    assert sorted(lb["key"] for lb in labels()["labels"]) == sorted(keys)


def test_at_least_half_are_executed_or_read_from_dependency_source():
    s = labels()
    assert 2 * ac2_count(s) >= len(s["labels"]), (ac2_count(s), len(s["labels"]))


def test_every_label_says_how_and_executed_ones_name_checked_in_reproductions():
    for lb in labels()["labels"]:
        assert lb.get("established_by"), lb["display"]
        if lb["basis"] == "executed":
            named = re.findall(r"repro/[\w./-]+", lb["established_by"])
            assert named, lb["display"]
            for path in named:
                assert (SECOND / path).is_file(), path


def test_the_labeller_is_recorded_and_is_not_the_investigator():
    who = {lb["labelled_by"] for lb in labels()["labels"]}
    assert readme_row("Labelled by")
    assert readme_row("Investigator model") not in who


def test_review_has_a_section_per_finding():
    text = (SECOND / "review.md").read_text()
    for lb in labels()["labels"]:
        assert re.search(rf"^## {re.escape(lb['display'])} ", text, re.M), lb["display"]
