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
