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


# --- Task 3 -----------------------------------------------------------------
def _run(findings: dict, model=None, commit=SHA) -> dict:
    return {"schema": b.RUN_SCHEMA, "commit": commit, "produced_by": {"stage": "test", "model": model},
            "findings": findings}


def test_today_confidences_baseline():
    run = b.run_from_report(CELERY / "scan" / "report.json")
    assert run["commit"] == SHA and run["produced_by"]["model"] is None
    records, unlabelled, excluded = b.split_run(run, _celery())
    m = b.score_confidence(records, _celery())
    assert m["counts"] == {"exact": 8, "within one": 20, "over": 6, "under": 7}
    assert m["high_above_deserved"] == sorted([_key("FR-001"), _key("FR-003")])
    assert unlabelled == [] and excluded == []


def test_unlabelled_keys_are_listed_and_never_scored():
    run = _run({"000000000000": {"confidence": "high"}, _key("FR-002"): {"confidence": "high"}})
    records, unlabelled, _ = b.split_run(run, _celery())
    assert unlabelled == ["000000000000"]
    assert b.score_confidence(records, _celery())["counts"]["exact"] == 1


def test_findings_are_matched_on_key_never_on_display_id():
    # A run whose records carry another finding's display id still scores by its key.
    run = _run({_key("FR-002"): {"confidence": "high", "display": "FR-003"}})
    records, _, _ = b.split_run(run, _celery())
    rows = b.score_confidence(records, _celery())["rows"]
    assert rows[_key("FR-002")] == {"run": "high", "deserved": "high", "step": 0}


def test_labeller_scoring_its_own_labels_is_excluded():
    run = _run({_key("FR-002"): {"confidence": "high"}}, model="claude-fable-5-1")
    records, _, excluded = b.split_run(run, _celery())
    assert records == {} and excluded == [_key("FR-002")]


@pytest.mark.parametrize("doc, needle", [
    ({"schema": "x"}, "schema is not"),
    ({"schema": b.RUN_SCHEMA, "commit": SHA, "produced_by": {}, "findings": {}}, "produced_by.stage"),
    ({"schema": b.RUN_SCHEMA, "commit": SHA, "produced_by": {"stage": "s"}, "findings": []}, "keyed by finding key"),
    ({"schema": b.RUN_SCHEMA, "commit": SHA, "produced_by": {"stage": "s"},
      "findings": {"k": {"verdict": "maybe"}}}, "verdict 'maybe'"),
    ({"schema": b.RUN_SCHEMA, "commit": SHA, "produced_by": {"stage": "s"},
      "findings": {"k": {"confidence": "certain"}}}, "confidence 'certain'"),
])
def test_an_invalid_run_is_refused(tmp_path, doc, needle):
    p = tmp_path / "run.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(b.InputError) as e:
        b.load_run(p)
    assert any(needle in x for x in e.value.problems)


# --- Task 4 -----------------------------------------------------------------
TRUTH = ("correct", "correct_but_gated", "partially_correct", "wrong")
EXPECTED_MATRIX = {
    "upheld": ("same", "one step", "wrong direction", "wrong direction"),
    "upheld_but_gated": ("one step", "same", "wrong direction", "wrong direction"),
    "narrowed": ("one step", "one step", "same", "one step"),
    "refuted": ("correct refuted", "correct refuted", "one step", "same"),
}


@pytest.mark.parametrize("run_verdict", list(EXPECTED_MATRIX))
@pytest.mark.parametrize("truth", TRUTH)
def test_every_matrix_cell(run_verdict, truth):
    assert b.verdict_outcome(run_verdict, truth) == EXPECTED_MATRIX[run_verdict][TRUTH.index(truth)]


def test_spike_refuter_baseline():
    run = b.load_run(CELERY / "runs" / "spike-refuter.json")
    records, unlabelled, excluded = b.split_run(run, _celery())
    v = b.score_verdicts(records, _celery())
    assert v["counts"] == {"same": 15, "one step": 4, "wrong direction": 2, "correct refuted": 0}
    assert sorted(k for k, x in v["rows"].items() if x["outcome"] == "wrong direction") == \
        sorted([_key("FR-003"), _key("FR-009")])
    d = b.score_duplicates(records, _celery())
    assert d["found"] == [_key("FR-006")] and d["missed"] == [] and d["false"] == []
    assert unlabelled == [] and excluded == []


def test_spike_run_is_the_spike_files_mapped_to_keys():
    report = json.loads((CELERY / "scan" / "report.json").read_text())
    key_of = {f["id"]: f["key"] for f in report["findings"]}
    expected = {}
    for src in sorted((CELERY / "spikes" / "refute").glob("refute_*.json")):
        for f in json.loads(src.read_text())["findings"]:
            expected[key_of[f["id"]]] = {"verdict": f["verdict"],
                                        "duplicate_of": key_of[f["duplicate_of"]] if f.get("duplicate_of") else None}
    run = b.load_run(CELERY / "runs" / "spike-refuter.json")
    assert run["findings"] == expected
    assert run["commit"] == SHA and run["produced_by"]["model"] is None


def test_duplicates_missed_and_false():
    s = _celery()
    k1, k6, k2 = _key("FR-001"), _key("FR-006"), _key("FR-002")
    d = b.score_duplicates({k6: {"duplicate_of": None}, k2: {"duplicate_of": k1}}, s)
    assert d["found"] == [] and d["missed"] == [k6] and d["false"] == [k2]


# --- Task 5 -----------------------------------------------------------------
def test_today_bundles_baseline():
    run = b.run_from_report(CELERY / "scan" / "report.json")
    b.add_bundles(run, CELERY / "scan" / "bundles", CELERY / "scan" / "report.json")
    records, _, _ = b.split_run(run, _celery())
    m = b.score_bundles(records, _celery())
    c = m["counts"]
    assert (c["shown"], c["not shown"], c["elsewhere"], c["not in repository"], c["unreadable"]) == (4, 5, 3, 0, 0)
    assert sorted(k for k, x in m["rows"].items() if x["partly_elsewhere"]) == sorted([_key("FR-003"), _key("FR-015")])


def _render(tmp_path: Path, n: int, budget: int, top: dict | None) -> str:
    import bundle
    (tmp_path / "m.py").write_text("\n".join(f"x_{i:04d} = {i}  # line {i}" for i in range(1, n + 1)) + "\n")
    hs = {"file": "m.py", "language": "python", "complexity": {"top_function": top} if top else {}}
    return bundle.section_source(tmp_path, hs, budget)


@pytest.mark.parametrize("n, budget, top", [
    (50, 10000, None),                                  # whole file
    (400, 500, None),                                   # file trimmed, clipped
    (400, 10000, {"name": "f", "lines": "100-150"}),    # fits: whole file
    (400, 200, {"name": "f", "lines": "100-250"}),      # function excerpt, clipped
    (400, 600, {"name": "f", "lines": "100-120"}),      # function excerpt, not clipped
    (400, 300, {"name": "f", "lines": "300-400"}),      # excerpt reaching the file's end, clipped
])
def test_bundle_parser_matches_what_bundle_py_renders(tmp_path, n, budget, top):
    text = _render(tmp_path, n, budget, top)
    file, ranges = b.shown_lines(text)
    assert file == "m.py"
    body = text.split("```python\n", 1)[1].rsplit("\n```", 1)[0]
    whole = {int(m.group(1)) for line in body.split("\n")
             if (m := re.fullmatch(r"x_\d{4} = \d+  # line (\d+)", line))}
    claimed = {i for lo, hi in ranges for i in range(lo, hi + 1)}
    assert claimed <= whole
    assert len(whole - claimed) <= 2


def test_an_unparsable_source_block_is_unreadable_never_not_shown(tmp_path):
    assert b.shown_lines("## Source — `a.py`\n\n_something new_\n\n```python\nx\n```\n") is None
    s = _celery()
    k = _key("FR-001")
    m = b.score_bundles({k: {"bundle": {"file": "celery/app/base.py", "shown": None}}}, s)
    assert m["rows"][k]["outcome"] == "unreadable"


def test_a_missing_bundle_file_is_unreadable(tmp_path):
    import shutil
    shutil.copytree(CELERY / "scan" / "bundles", tmp_path / "bundles")
    (tmp_path / "bundles" / "H03.md").unlink()
    run = b.run_from_report(CELERY / "scan" / "report.json")
    b.add_bundles(run, tmp_path / "bundles", CELERY / "scan" / "report.json")
    records, _, _ = b.split_run(run, _celery())
    assert b.score_bundles(records, _celery())["rows"][_key("FR-001")]["outcome"] == "unreadable"
