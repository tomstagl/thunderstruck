"""#37: refuting findings before they reach the report."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


# --- Task 1 -----------------------------------------------------------------
def test_verdicts_are_check_statuses_but_unchecked():
    assert c.VERDICTS == ("upheld", "narrowed", "refuted", "inconclusive")
    assert set(c.VERDICTS) == set(c.CHECK_STATUSES) - {"unchecked"}


def test_refutable_fields_are_finding_fields():
    assert c.REFUTABLE_FIELDS == ("failure_mode", "trigger_condition", "amplifier",
                                  "sustaining_effect", "blast_radius", "how_to_verify",
                                  "prediction", "preconditions")


SETTING = {"setting": "S", "default": "False", "default_ref": "a.py:1", "value": "True"}


@pytest.mark.parametrize("check, gate", [
    ({"status": "narrowed", "refuted_claims": [{"field": "preconditions", "setting": SETTING}]},
     "non_default_setting"),
    ({"status": "upheld", "refuted_claims": [{"field": "preconditions", "setting": SETTING}]}, "none"),
    ({"status": "narrowed", "refuted_claims": [{"field": "preconditions"}]}, "none"),
    ({"status": "narrowed", "refuted_claims": [{"field": "amplifier", "setting": SETTING}]}, "none"),
    ({"status": "narrowed", "refuted_claims": "junk"}, "none"),
    ({"status": "narrowed"}, "none"),
])
def test_a_setting_the_skeptic_found_gates_a_narrowed_finding(check, gate):
    assert c.finding_gate({"preconditions": [], "check": check}) == gate


def test_investigator_preconditions_still_gate():
    f = {"preconditions": [{"needs": "changed"}], "check": {"status": "upheld"}}
    assert c.finding_gate(f) == "non_default_setting"
    assert c.skeptic_settings(f) == []
