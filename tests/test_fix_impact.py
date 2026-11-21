"""#105: what a fix would remove, what was traced and what was inferred, what was
not checked, and numbered lines in a bundle's source."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent




# --- Task 1 -----------------------------------------------------------------
def test_vocabulary_is_the_spec_spelling():
    assert c.FIX_TOUCHES == ("lock", "retry", "cache")
    assert c.BLAST_BASES == ("traced", "catalog", "assumption")
    assert c.GUARANTEE_KEYS == ("guarantee", "removed_by", "evidence")
    assert c.BLAST_KEYS == ("claim", "basis", "evidence")
    assert c.NOT_CHECKED_KEYS == ("item", "how_to_check")
    assert c.RESOLUTION_STATES == ("resolved", "unresolved")
    assert (c.MAX_GUARANTEES, c.MAX_BLAST_ITEMS, c.MAX_NOT_CHECKED) == (5, 8, 5)


def test_the_catalog_marks_the_patterns_whose_fix_changes_a_mechanism(catalog):
    marked = {p["id"]: p["fix_touches"] for p in catalog["patterns"] if "fix_touches" in p}
    assert marked == {"S02": "retry", "S03": "retry", "S04": "retry", "S10": "retry",
                      "S09": "cache", "S28": "lock"}
    assert set(marked.values()) <= set(c.FIX_TOUCHES)


@pytest.mark.parametrize("finding, state", [
    ({}, "not_assessed"),
    ("junk", "not_assessed"),
    ({"blast_items": []}, "not_stated"),
    ({"blast_items": [], "implicit_guarantees": []}, "not_stated"),
    ({"blast_items": [], "no_guarantees_reason": "  "}, "not_stated"),
    ({"implicit_guarantees": [{}]}, "stated"),
    ({"no_guarantees_reason": "nothing else uses it"}, "none_found"),
    ({"implicit_guarantees": [{}], "no_guarantees_reason": "x"}, "stated"),
])
def test_guarantee_state(finding, state):
    assert c.guarantee_state(finding) == state


@pytest.mark.parametrize("finding, states", [
    ({}, []),
    ({"not_checked": []}, []),
    ({"not_checked": [{}, {}]}, ["open", "open"]),
    ({"not_checked": [{}, {}], "check": {"status": "upheld"}}, ["open", "open"]),
    ({"not_checked": [{}, {}, {}],
      "check": {"not_checked": [{"item": 1, "state": "resolved"}, {"item": 2, "state": "unresolved"}]}},
     ["open", "resolved", "unresolved"]),
    ({"not_checked": [{}], "check": {"not_checked": [{"item": 0, "state": "maybe"}]}}, ["open"]),
    ({"not_checked": [{}], "check": {"not_checked": [{"item": True, "state": "resolved"}, "junk"]}}, ["open"]),
    ({"not_checked": [{}], "check": {"not_checked": "junk"}}, ["open"]),
])
def test_not_checked_states_keep_every_item(finding, states):
    assert c.not_checked_states(finding) == states


# --- Task 2 -----------------------------------------------------------------
INVESTIGATOR = ROOT / "agents" / "thunderstruck-investigator.md"
SCAN = ROOT / "skills" / "thunderstruck-scan" / "SKILL.md"


def test_the_investigator_prompt_states_the_new_rules():
    flat = " ".join(INVESTIGATOR.read_text(encoding="utf-8").split())
    assert "all twelve required keys" in flat and "all ten" not in flat
    for fragment in ("`implicit_guarantees`", "`no_guarantees_reason`", "`blast_items`", "`not_checked`",
                     "A catalog edge never makes an item `traced`",
                     'completes "removed by"', "a skeptic reads this list and never reads that rationale",
                     "whatever its patterns",
                     "The validator checks that each cited line exists, not that the lines connect"):
        assert fragment in flat, fragment
    assert "say so in `confidence_rationale`" not in flat


def test_the_repair_round_asks_for_every_new_key():
    flat = " ".join(SCAN.read_text(encoding="utf-8").split())
    assert "all twelve required keys" in flat and "all ten" not in flat
    assert "`not_checked`" in flat and "`implicit_guarantees` or `no_guarantees_reason`" in flat


def test_the_catalog_brief_marks_the_patterns_the_ticket_scoped(tmp_path, catalog):
    import bundle
    path = bundle.write_catalog_brief(tmp_path, catalog, {})
    sections = path.read_text().split("\n### ")[1:]
    marked = {s.split(" — ", 1)[0]: s for s in sections if "A finding for this pattern (kind: " in s}
    assert set(marked) == {"S02", "S03", "S04", "S09", "S10", "S28"}
    assert "(kind: lock) states `implicit_guarantees`" in marked["S28"]
    assert "(kind: cache)" in marked["S09"] and "(kind: retry)" in marked["S10"]
    assert "changes a" not in path.read_text(), "the gate is the ticket's scope, not a property of the patterns"


def test_the_prompt_example_has_a_traced_item_citing_two_lines():
    from test_investigator_contract import _example
    example = _example(INVESTIGATOR.read_text(encoding="utf-8"))
    traced = [i for f in example["findings"] for i in f["blast_items"] if i["basis"] == "traced"]
    assert traced and any(len(i["evidence"]) >= 2 for i in traced), \
        "a single cited line would read as a traced path"
