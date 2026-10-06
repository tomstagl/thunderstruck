"""The correctness benchmark (#55): scoring against labelled ground truth."""

from __future__ import annotations

import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import benchmark as b

ROOT = Path(__file__).resolve().parent.parent
CELERY = ROOT / "docs" / "calibration" / "correctness" / "celery"
SHA = "508c1129269d2b1baffc516d8f5c05da06273ef0"


def _set(**over) -> dict:
    doc = {"schema": b.LABELS_SCHEMA, "repo": "example/lib", "commit": "a" * 40, "role": "development",
           "scan": "scan/report.json",
           "labels": [{"key": "k1", "display": "FR-001", "verdict": "correct", "basis": "read",
                       "labelled_by": "a-person", "deserved_confidence": "high", "duplicate_of": None,
                       "refuting_fact": None, "preconditions": []}]}
    doc.update(over)
    return doc


def _write_set(tmp_path: Path, doc: dict, name: str = "lib") -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "labels.json").write_text(json.dumps(doc))
    return d / "labels.json"


def _celery() -> dict:
    return b.load_label_sets([CELERY / "labels.json"])[0]


def _key(display: str) -> str:
    return next(lb["key"] for lb in _celery()["labels"] if lb["display"] == display)
# --- Task 1 -----------------------------------------------------------------
def test_a_valid_set_loads(tmp_path):
    [s] = b.load_label_sets([_write_set(tmp_path, _set())])
    assert s["_by_key"]["k1"]["verdict"] == "correct"


@pytest.mark.parametrize("mutate, needle", [
    (lambda d: d.update(schema="other/v1"), "schema is not"),
    (lambda d: d.update(commit="abc123"), "40-character hex SHA"),
    (lambda d: d.update(role="training"), "role must be one of"),
    (lambda d: d["labels"].append(copy.deepcopy(d["labels"][0])), "occurs more than once"),
    (lambda d: d["labels"][0].pop("basis"), "basis is missing"),
    (lambda d: d["labels"][0].update(labelled_by=""), "labelled_by is missing"),
    (lambda d: d["labels"][0].update(verdict="mostly"), "verdict 'mostly'"),
    (lambda d: d["labels"][0].update(basis="executed", established_by=""), "established_by is empty"),
    (lambda d: d["labels"][0].update(duplicate_of="nope"), "duplicate_of 'nope'"),
    (lambda d: d["labels"][0].update(duplicate_of="k1"), "duplicate_of 'k1'"),
    (lambda d: d["labels"][0].update(refuting_fact={"ranges": [{"file": "a.py", "lo": 9, "hi": 3, "kind": "repo"}]}),
     "not a valid line range"),
    (lambda d: d["labels"][0].update(refuting_fact={"ranges": [{"file": "a.py", "lo": 0, "hi": 3, "kind": "repo"}]}),
     "not a valid line range"),
])
def test_an_invalid_set_is_rejected_whole(tmp_path, mutate, needle):
    doc = _set()
    doc["labels"].append({"key": "k2", "verdict": "wrong", "basis": "read", "labelled_by": "a-person"})
    mutate(doc)
    with pytest.raises(b.InputError) as e:
        b.load_label_sets([_write_set(tmp_path, doc)])
    assert any(needle in p for p in e.value.problems), e.value.problems


def test_every_problem_is_named_not_only_the_first(tmp_path):
    doc = _set()
    doc["labels"][0].pop("basis")
    doc["labels"][0]["labelled_by"] = ""
    with pytest.raises(b.InputError) as e:
        b.load_label_sets([_write_set(tmp_path, doc)])
    assert len(e.value.problems) == 2


def test_two_sets_with_one_commit_are_rejected(tmp_path):
    a = _write_set(tmp_path, _set(), "a")
    c = _write_set(tmp_path, _set(repo="example/other"), "c")
    with pytest.raises(b.InputError, match="also the commit of"):
        b.load_label_sets([a, c])


def test_a_run_commit_selects_its_set_and_an_unknown_one_is_refused(tmp_path):
    sets = b.load_label_sets([_write_set(tmp_path, _set())])
    assert b.select_set(sets, "a" * 7)["repo"] == "example/lib"
    with pytest.raises(b.InputError, match="matches no loaded label set"):
        b.select_set(sets, "b" * 40)
    with pytest.raises(b.InputError):
        b.select_set(sets, "aaa")  # too short to identify a commit


@pytest.mark.parametrize("k, n, lo, hi", [(15, 21, 50, 86), (8, 21, 21, 59), (4, 9, 19, 73), (0, 21, 0, 15), (0, 0, 0, 100)])
def test_wilson_interval(k, n, lo, hi):
    assert b.wilson(k, n) == (lo, hi)


def test_a_figure_line_states_what_it_rests_on(tmp_path):
    [s] = b.load_label_sets([_write_set(tmp_path, _set())])
    line = b.format_figure(b.figure("verdict: same", 1, 1, b.basis_of(s, ["k1"])))
    assert "example/lib@aaaaaaa" in line and "n=1 findings" in line and "labels: 1 a-person (1 read)" in line
    assert line.endswith("revealed") is False
    assert b.format_figure(b.figure("x", 0, 1, b.basis_of(s, ["k1"])), revealed=True).endswith("· revealed")
