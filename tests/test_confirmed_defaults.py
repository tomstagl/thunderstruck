"""#57: defaults a finding relies on are confirmed or flagged, never assumed."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


# --- Task 1 -----------------------------------------------------------------
def _item(found="same", **over) -> dict:
    it = {"setting": "s", "precondition": 0, "found": found, "default": "1", "default_ref": "a.py:1",
          "default_ref_error": None, "default_call_site": False}
    it.update(over)
    return it


@pytest.mark.parametrize("call_site, item, basis", [
    (None, None, "not_checked"),
    (False, None, "not_checked"),
    (True, None, "call_site_fallback"),
    (True, _item("same"), "registered"),
    (False, _item("same"), "registered"),
    (False, _item("different"), "contradicted"),
    (False, _item("not_found", default=None, default_ref=None), "not_found"),
    (False, _item("same", default_ref_error="no such file"), "unresolved"),
    (False, _item("same", default_names_setting=False), "unresolved"),
    (False, _item("different", default_names_setting=False), "unresolved"),
    (False, _item("same", default_names_setting=True), "registered"),
    (False, _item("same", default_call_site=True), "call_site_fallback"),
    (True, _item("same", default_call_site=True), "call_site_fallback"),
    (False, _item("different", default_call_site=True), "call_site_fallback"),
    (False, _item("maybe"), "not_checked"),
])
def test_confirm_table(call_site, item, basis):
    got = c.confirm(call_site, item)
    assert got["basis"] == basis
    assert got["state"] == ("confirmed" if basis == "registered" else "unconfirmed")
    assert got["reason"] == c.CONFIRMATION_REASONS[basis]


def test_vocabularies_are_the_spec_spelling():
    assert c.CONFIRMATION_STATES == ("confirmed", "unconfirmed")
    assert c.CONFIRMATION_BASES == ("registered", "contradicted", "call_site_fallback",
                                    "not_found", "unresolved", "not_checked")
    assert c.CONFIRMATION_FOUND == ("same", "different", "not_found")
    assert set(c.CONFIRMATION_REASONS) == set(c.CONFIRMATION_BASES)
    assert c.GATES == ("none", "unconfirmed_default", "non_default_setting")
    assert c.GATE_MARKERS["unconfirmed_default"] == "relies on a doubtful default"
    assert c.DOUBTFUL_BASES == ("call_site_fallback", "contradicted", "not_found", "unresolved")
    assert c.DEFAULT_UNCONFIRMED_MARKER == "default unconfirmed"


def _pre(needs="default", call_site=False, setting="s") -> dict:
    return {"setting": setting, "default": "1", "default_ref": "a.py:1", "needs": needs,
            "value": None if needs == "default" else "2", "documented": "no", "doc_ref": None,
            "confirmation": {"call_site": call_site}}


def test_with_confirmations_derives_listed_and_unlisted_items_without_mutating():
    f = {"preconditions": [_pre(call_site=True), _pre(setting="t")],
         "check": {"status": "upheld", "confirmations": [
             _item("same", setting="t", precondition=1),
             _item("different", setting="u", precondition=None, claim="u is 1", stated_call_site=True)]}}
    before = json.dumps(f, sort_keys=True)
    got = c.with_confirmations(f, f["check"]["confirmations"])
    assert json.dumps(f, sort_keys=True) == before
    p0, p1 = got["preconditions"]
    assert (p0["confirmation"]["basis"], p0["confirmation"]["by"], p0["confirmation"]["call_site"]) == \
        ("call_site_fallback", "validator", True)
    assert (p1["confirmation"]["state"], p1["confirmation"]["by"]) == ("confirmed", "skeptic")
    unlisted = got["check"]["confirmations"][1]
    assert unlisted["confirmation"]["basis"] == "contradicted"


def test_with_confirmations_without_a_check_is_mechanical_only():
    got = c.with_confirmations({"preconditions": [_pre(call_site=True), _pre(call_site=None)]}, None)
    assert [p["confirmation"]["basis"] for p in got["preconditions"]] == ["call_site_fallback", "not_checked"]


def test_unconfirmed_defaults_counts_needs_default_and_unlisted_only():
    f = c.with_confirmations({"preconditions": [_pre("changed", call_site=True), _pre("default")],
                              "check": {"confirmations": [_item("same", setting="u", precondition=None)]}},
                             [_item("same", setting="u", precondition=None)])
    names = [x["setting"] for x in c.unconfirmed_defaults(f)]
    assert names == ["s"]  # the needs: changed one does not count; the unlisted one is confirmed


@pytest.mark.parametrize("finding, gate", [
    ({"preconditions": []}, "none"),
    ({"preconditions": [{**_pre(), "confirmation": {"state": "confirmed"}}]}, "none"),
    ({"preconditions": [_pre()]}, "none"),                                  # not_checked: not doubtful
    ({"preconditions": [{"setting": "s", "default": "1", "needs": "default"}]}, "none"),
    *[({"preconditions": [{**_pre(), "confirmation": {"state": "unconfirmed", "basis": b}}]}, "unconfirmed_default")
      for b in ("call_site_fallback", "contradicted", "not_found", "unresolved")],
    ({"preconditions": [{**_pre(), "confirmation": {"state": "unconfirmed", "basis": "not_checked"}}]}, "none"),
    ({"preconditions": [_pre(), _pre("changed", setting="t")]}, "non_default_setting"),
    ({"preconditions": [], "check": {"confirmations": [
        {"setting": "u", "precondition": None, "confirmation": {"state": "unconfirmed", "basis": "contradicted"}}]}},
     "unconfirmed_default"),
    ({"preconditions": [], "check": {"confirmations": [
        {"setting": "u", "precondition": None, "confirmation": {"state": "unconfirmed", "basis": "not_checked"}}]}},
     "none"),
])
def test_finding_gate_has_three_gates_in_precedence(finding, gate):
    assert c.finding_gate(finding) == gate
