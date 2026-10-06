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


# --- Task 2 -----------------------------------------------------------------
# verdicts.json qualifies some setting names; labels.json uses the plain name (spec §6.1).
SETTING_NAMES = {
    "result_backend_always_retry (database backend)": ["result_backend_always_retry"],
    "result_backend_max_retries (database backend)": ["result_backend_max_retries"],
    "retry_backoff / retry_jitter": ["retry_backoff", "retry_jitter"],
}


def test_celery_labels_agree_with_the_evidence():
    verdicts = {v["id"]: v for v in json.loads((CELERY / "verdicts.json").read_text())["findings"]}
    report = json.loads((CELERY / "scan" / "report.json").read_text())
    key_of = {f["id"]: f["key"] for f in report["findings"]}
    s = _celery()
    assert s["commit"] == report["repo"]["head"] == SHA
    assert s["role"] == "development"
    assert sorted(lb["display"] for lb in s["labels"]) == sorted(verdicts)
    for lb in s["labels"]:
        v = verdicts[lb["display"]]
        assert lb["key"] == v["key"] == key_of[lb["display"]]
        assert lb["source"] == f"verdicts.json#{lb['display']}"
        assert lb["verdict"] == v["verdict"]
        assert lb["basis"] == {"read_code": "read"}.get(v["verdict_basis"], v["verdict_basis"])
        assert lb["labelled_by"] == "claude-fable-5-1"
        if lb["basis"] == "executed":
            assert lb["established_by"] == v["how_to_verify"]["what_you_ran_or_why_not"]
        assert lb["deserved_confidence"] == v["confidence_assessment"]["deserved"]
        assert lb["duplicate_of"] == (key_of[v["duplicate_of"]] if v["duplicate_of"] else None)
        assert (lb["refuting_fact"] is None) == (not (v["refuting_fact"] or {}).get("where"))
        expected = [n for p in v["preconditions"] for n in SETTING_NAMES.get(p["setting"], [p["setting"]])]
        assert [p["setting"] for p in lb["preconditions"]] == expected


def test_celery_refuting_ranges_are_the_evidence_ranges():
    s = _celery()
    fr001 = s["_by_key"][_key("FR-001")]["refuting_fact"]["ranges"]
    assert fr001 == [{"file": "celery/app/base.py", "lo": 1640, "hi": 1657, "kind": "repo"},
                     {"file": "celery/backends/base.py", "lo": 236, "hi": 236, "kind": "repo"},
                     {"file": "celery/backends/asynchronous.py", "lo": 358, "hi": 363, "kind": "repo"}]
    kinds = {lb["display"]: sorted({r["kind"] for r in lb["refuting_fact"]["ranges"]})
             for lb in s["labels"] if lb["refuting_fact"]}
    assert kinds["FR-013"] == ["dependency", "repo"]
    assert kinds["FR-012"] == ["history", "repo"]
    assert kinds["FR-021"] == ["docs", "repo"]
    assert len(kinds) == 12


@pytest.mark.xfail(reason="values_match arrives in Task 6", strict=True)
def test_celery_has_exactly_five_discriminating_preconditions():
    s = _celery()
    found = sorted((lb["display"], p["setting"]) for lb in s["labels"] for p in lb["preconditions"]
                   if p["kind"] == "setting" and not b.values_match(p["literal"], p["effective"]))
    assert found == [("FR-001", "redis_socket_connect_timeout"), ("FR-002", "task_acks_on_timeout"),
                     ("FR-014", "result_backend_always_retry"), ("FR-015", "result_backend_always_retry"),
                     ("FR-015", "result_backend_max_retries")]
    env = sorted((lb["display"], p["setting"]) for lb in s["labels"] for p in lb["preconditions"]
                 if p["kind"] == "environment")
    assert env == [("FR-014", "database user privileges"), ("FR-014", "result_backend"), ("FR-019", "task_routes")]
