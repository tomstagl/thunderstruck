"""#56: confidence that means the claim was checked, preconditions, and the
history signal, from the rule tables to every output."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent


# --- Task 1 -----------------------------------------------------------------
TABLE = {
    ("high", "unchecked"): "medium", ("high", "upheld"): "high", ("high", "narrowed"): "medium",
    ("high", "inconclusive"): "medium", ("high", "refuted"): "low",
    ("medium", "unchecked"): "medium", ("medium", "upheld"): "medium", ("medium", "narrowed"): "low",
    ("medium", "inconclusive"): "medium", ("medium", "refuted"): "low",
    ("low", "unchecked"): "low", ("low", "upheld"): "low", ("low", "narrowed"): "low",
    ("low", "inconclusive"): "low", ("low", "refuted"): "low",
}


@pytest.mark.parametrize("claimed, status", sorted(TABLE))
def test_effective_confidence_table(claimed, status):
    assert c.effective_confidence(claimed, status) == TABLE[(claimed, status)]


def test_only_upheld_can_be_high():
    assert {s for s in c.CHECK_STATUSES if c.effective_confidence("high", s) == "high"} == {"upheld"}


def test_an_unknown_status_counts_as_unchecked_and_an_unknown_claim_as_low():
    assert c.effective_confidence("high", "probably") == "medium"
    assert c.effective_confidence("certain", "upheld") == "low"
    assert c.effective_confidence(None, "unchecked") == "low"


@pytest.mark.parametrize("finding, expected", [
    ({}, "unchecked"),
    ({"check": None}, "unchecked"),
    ({"check": "upheld"}, "unchecked"),
    ({"check": {"status": "maybe"}}, "unchecked"),
    *[({"check": {"status": s}}, s) for s in ("unchecked", "upheld", "narrowed", "inconclusive", "refuted")],
])
def test_check_status(finding, expected):
    assert c.check_status(finding) == expected


@pytest.mark.parametrize("preconditions, gate", [
    ([], "none"),
    (None, "none"),
    ([{"needs": "default"}, {"needs": "default"}], "none"),
    ([{"needs": "default"}, {"needs": "changed"}], "non_default_setting"),
    (["not an object", {"needs": "changed"}], "non_default_setting"),
])
def test_finding_gate(preconditions, gate):
    assert c.finding_gate({"preconditions": preconditions}) == gate


def test_vocabularies_are_the_spec_spelling():
    assert c.CHECK_STATUSES == ("unchecked", "upheld", "narrowed", "inconclusive", "refuted")
    assert c.COMMIT_ROLES == ("introduced", "fixed", "mitigated", "changed")
    assert c.PRECONDITION_NEEDS == ("changed", "default")
    assert c.DOCUMENTED == ("yes", "no", "not_checked")
    assert c.GATES == ("none", "non_default_setting")
    assert set(c.CHECK_SENTENCES) == set(c.CHECK_STATUSES)
    assert set(c.GATE_MARKERS) == set(c.GATES) - {"none"}
