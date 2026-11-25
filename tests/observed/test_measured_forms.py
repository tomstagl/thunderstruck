"""Only measured forms ship (#6, spec §12).

Every form id in catalog/observed.yaml must be in the "Measured forms" table of
docs/calibration/observed-dependencies.md, and exercised by a positive sample.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "calibration" / "observed-dependencies.md"
RULES = ROOT / "catalog" / "observed.yaml"
SAMPLES = Path(__file__).parent / "samples"


def shipped_ids() -> set[str]:
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {form["id"] for kinds in doc["forms"].values()
            for forms in kinds.values() for form in forms}


def measured_ids() -> set[str]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Measured forms", 1)[1]
    return set(re.findall(r"^\|\s*`([a-z][a-z0-9.-]+)`\s*\|", section, re.M))


def test_the_doc_ends_in_go():
    verdicts = [line for line in DOC.read_text(encoding="utf-8").splitlines()
                if line.startswith("Verdict:")]
    assert verdicts[-1] == "Verdict: go"


def test_only_measured_forms_ship():
    assert shipped_ids() and shipped_ids() <= measured_ids(), shipped_ids() - measured_ids()


def test_every_form_has_a_positive_sample():
    named: set[str] = set()
    for expected in SAMPLES.rglob("*.expected"):
        first = expected.read_text(encoding="utf-8").splitlines()[0]
        named |= {f.strip() for f in first[len("# forms:"):].split(",") if f.strip()}
    assert shipped_ids() <= named, shipped_ids() - named
