# Correctness Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One deterministic command scores a refutation run, a confidence assignment, a scan's bundles and stated defaults against executed ground truth, and every figure it prints says what it rests on.

**Architecture:** `scripts/benchmark.py` (stdlib only) loads label sets (`docs/calibration/correctness/<set>/labels.json`), validates them whole, and scores run files or a scan's `report.json` and `bundles/` against them by finding `key`. The Celery set is converted once from the frozen evidence and checked in with two baseline inputs; tests pin the published baselines.

**Tech Stack:** Python 3.11+ standard library, `uv`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-03-correctness-benchmark-design.md` (§n below refers to it). Requirements AC-1…AC-11 and the product decisions are in GitHub issue #55, part of #54.

**Branch:** `feat/correctness-benchmark`. One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

One file of tests, `tests/test_benchmark.py`, grows task by task; each task's tests are appended under a `# --- Task N` comment. Run one task's tests with `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q -k "<name>"`.

## Global Constraints

- `scripts/benchmark.py` imports the standard library only: no `yaml`, no `lizard`, no `_common` (§1, §8). It never calls git, a model or the network, and never executes anything from a scanned repository.
- Findings are matched on `key` only; a display id is printed for a reader and never used to join (AC-7, §2.1).
- No rate is formatted except through `format_figure`, which always prints repo@commit, n and the labeller mix (AC-6, §5.1).
- The scorer prints keys, display ids, setting names, vocabulary words and counts only, never verdict prose, refuting-fact text or anything a scanned repository wrote (§9).
- Nothing in the scorer names a repository, hotspot id, file path or setting; those live only in `labels.json` (§1).
- `docs/calibration/correctness/celery/verdicts.json`, `scan/` and `spikes/` are evidence and are not edited (§6.1).
- Exit codes: 0 when the input was scored, 2 when it could not be; no threshold ever changes the exit code (§7).
- No label, refuting fact or verdict is read by anything under `agents/`, `skills/`, `catalog/`, `scripts/` (except `benchmark.py`), `hooks/` or `templates/` (§9).
- No model calls are added; nothing in this plan changes scan consumption (§11).
- Public repository: no organisation-specific names, hosts or credentials in any file.

## Review Focus

1. **A scan of a commit no label set covers** (`--report` from a fresh scan of another repository). Exit 2, listing the loaded sets, never an empty table that reads as "nothing wrong". Pinned in Task 7.
2. **A bundle file missing from `bundles/`** (a partial copy, or a hotspot whose bundle failed). Its facts are `unreadable`, never a crash and never `not shown`. Pinned in Task 5.
3. **A precondition setting written with different case or stray whitespace** (`" TASK_ACKS_ON_TIMEOUT "`). It matches the labelled setting. Pinned in Task 6.
4. **A run covering only some labelled findings** (#37 run on three findings). Every figure's line says `n=3 of 21 labelled findings`, so a partial run cannot read as the whole set. Pinned in Task 7.
5. **A malformed run file** (truncated JSON from an interrupted run). Exit 2 naming the file, never a traceback. Pinned in Task 7.

---

### Task 1: Label sets, validation and figures

**Satisfies:** AC-6 (figure lines carry their basis), AC-9 (a label without its basis is rejected).

**Files:**
- Create: `scripts/benchmark.py`
- Create: `tests/test_benchmark.py`

**Interfaces:**
- Produces: `InputError(problems: list[str])`; constants `LABELS_SCHEMA`, `RUN_SCHEMA`, `RESULT_SCHEMA`, `VERDICTS`, `RUN_VERDICTS`, `BASES`, `CONFIDENCE`, `ROLES`, `RANGE_KINDS`, `PRECONDITION_KINDS`, `VALUE_TYPES`; `validate_label_set(doc: dict, where: str) -> list[str]`; `load_label_sets(paths: list[Path]) -> list[dict]` (each set gains `_path` and `_by_key: dict[str, dict]`); `default_label_paths() -> list[Path]`; `select_set(sets: list[dict], commit: str) -> dict`; `wilson(k: int, n: int) -> tuple[int, int]`; `basis_of(label_set: dict, keys: list[str]) -> dict`; `figure(name: str, k: int, n: int, basis: dict) -> dict`; `format_basis(basis: dict) -> str`; `format_figure(fig: dict, revealed: bool = False) -> str`.

- [x] **Step 1: Write the failing tests.** Create `tests/test_benchmark.py` with this header and the Task 1 tests:

```python
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
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'benchmark'`.

- [x] **Step 3: Write the implementation.** Create `scripts/benchmark.py`:

```python
#!/usr/bin/env python3
"""Score a run against labelled ground truth (spec 2026-10-03-correctness-benchmark-design.md).

Deterministic, standard library only: no network, no model, no git.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETS = ROOT / "docs" / "calibration" / "correctness"

LABELS_SCHEMA = "thunderstruck.labels/v1"
RUN_SCHEMA = "thunderstruck.benchmark-run/v1"
RESULT_SCHEMA = "thunderstruck.benchmark/v1"

VERDICTS = ("correct", "correct_but_gated", "partially_correct", "wrong")
RUN_VERDICTS = ("upheld", "upheld_but_gated", "narrowed", "refuted")
BASES = ("executed", "read", "reasoned")
CONFIDENCE = ("low", "medium", "high")
ROLES = ("development", "holdout")
RANGE_KINDS = ("repo", "dependency", "docs", "history")
PRECONDITION_KINDS = ("setting", "environment")
VALUE_TYPES = ("none", "bool", "number", "text")

_SHA = re.compile(r"^[0-9a-f]{40}$")

class InputError(Exception):
    """Input that cannot be scored. ``problems`` names every reason."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# --------------------------------------------------------------- label sets
def validate_label_set(doc: dict, where: str) -> list[str]:
    p: list[str] = []
    if doc.get("schema") != LABELS_SCHEMA:
        return [f"{where}: schema is not {LABELS_SCHEMA}"]
    if not _SHA.match(str(doc.get("commit", ""))):
        p.append(f"{where}: commit is not a 40-character hex SHA")
    if doc.get("role") not in ROLES:
        p.append(f"{where}: role must be one of {', '.join(ROLES)}")
    if not doc.get("repo"):
        p.append(f"{where}: repo is empty")
    labels = doc.get("labels")
    if not isinstance(labels, list):
        return p + [f"{where}: labels is not a list"]
    keys = [lb.get("key") for lb in labels]
    for key in sorted({k for k in keys if keys.count(k) > 1}, key=str):
        p.append(f"{where}: key {key} occurs more than once")
    for lb in labels:
        k = lb.get("key") or "<no key>"
        for field in ("key", "verdict", "basis", "labelled_by"):
            if not lb.get(field):
                p.append(f"{where}: {k}: {field} is missing")
        if lb.get("verdict") and lb["verdict"] not in VERDICTS:
            p.append(f"{where}: {k}: verdict {lb['verdict']!r} is not one of {', '.join(VERDICTS)}")
        if lb.get("basis") and lb["basis"] not in BASES:
            p.append(f"{where}: {k}: basis {lb['basis']!r} is not one of {', '.join(BASES)}")
        if lb.get("basis") == "executed" and not lb.get("established_by"):
            p.append(f"{where}: {k}: basis is executed but established_by is empty")
        dc = lb.get("deserved_confidence")
        if dc is not None and dc not in CONFIDENCE:
            p.append(f"{where}: {k}: deserved_confidence {dc!r} is not one of {', '.join(CONFIDENCE)}")
        dup = lb.get("duplicate_of")
        if dup is not None and (dup == lb.get("key") or dup not in keys):
            p.append(f"{where}: {k}: duplicate_of {dup!r} is not another key in the set")
        for r in ((lb.get("refuting_fact") or {}).get("ranges") or []):
            if r.get("kind") not in RANGE_KINDS:
                p.append(f"{where}: {k}: range kind {r.get('kind')!r} is not one of {', '.join(RANGE_KINDS)}")
            elif r["kind"] == "repo":
                lo, hi = r.get("lo"), r.get("hi")
                if not (isinstance(lo, int) and isinstance(hi, int) and 0 < lo <= hi and r.get("file")):
                    p.append(f"{where}: {k}: repo range {r.get('file')}:{lo}-{hi} is not a valid line range")
        for pc in lb.get("preconditions") or []:
            if pc.get("kind") not in PRECONDITION_KINDS:
                p.append(f"{where}: {k}: precondition {pc.get('setting')!r} kind is not setting or environment")
            for side in ("literal", "effective"):
                if (pc.get(side) or {}).get("type") not in VALUE_TYPES:
                    p.append(f"{where}: {k}: precondition {pc.get('setting')!r} {side} has no valid type")
    return p


def load_label_sets(paths: list[Path]) -> list[dict]:
    """Load and validate every set; raise InputError naming every problem."""
    sets, problems = [], []
    for path in paths:
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError) as e:
            problems.append(f"{path}: {e}")
            continue
        found = validate_label_set(doc, str(path))
        if found:
            problems += found
            continue
        doc["_path"] = str(path)
        doc["_by_key"] = {lb["key"]: lb for lb in doc["labels"]}
        sets.append(doc)
    seen: dict[str, str] = {}
    for s in sets:
        if s["commit"] in seen:
            problems.append(f"{s['_path']}: commit {s['commit']} is also the commit of {seen[s['commit']]}")
        seen[s["commit"]] = s["_path"]
    if problems:
        raise InputError(problems)
    return sets


def default_label_paths() -> list[Path]:
    return sorted(DEFAULT_SETS.glob("*/labels.json"))


def select_set(sets: list[dict], commit: str) -> dict:
    for s in sets:
        if commit and s["commit"].startswith(commit) and len(commit) >= 7:
            return s
    loaded = ", ".join(f"{s['repo']}@{s['commit'][:7]}" for s in sets) or "none"
    raise InputError([f"run commit {commit or '<none>'} matches no loaded label set (loaded: {loaded})"])


# ------------------------------------------------------------------ figures
def wilson(k: int, n: int, z: float = 1.959964) -> tuple[int, int]:
    """Wilson 95% score interval, in whole percent."""
    if n == 0:
        return (0, 100)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round((c - h) / d * 100), round((c + h) / d * 100))


def basis_of(label_set: dict, keys: list[str]) -> dict:
    """What a figure over ``keys`` rests on."""
    mix: dict[str, dict[str, int]] = {}
    for k in sorted(keys):
        lb = label_set["_by_key"][k]
        by = mix.setdefault(lb["labelled_by"], {})
        by[lb["basis"]] = by.get(lb["basis"], 0) + 1
    return {"repo": label_set["repo"], "commit": label_set["commit"], "n": len(keys),
            "labelled": len(label_set["labels"]), "labellers": mix}


def figure(name: str, k: int, n: int, basis: dict) -> dict:
    lo, hi = wilson(k, n)
    return {"name": name, "k": k, "n": n, "interval": [lo, hi], "basis": basis}


def format_basis(basis: dict) -> str:
    parts = []
    for who, bases in sorted(basis["labellers"].items()):
        detail = ", ".join(f"{c} {b}" for b, c in sorted(bases.items(), key=lambda x: BASES.index(x[0])))
        parts.append(f"{sum(bases.values())} {who} ({detail})")
    n = (f"n={basis['n']} findings" if basis["n"] == basis["labelled"]
         else f"n={basis['n']} of {basis['labelled']} labelled findings")
    return f"{basis['repo']}@{basis['commit'][:7]} · {n} · labels: {'; '.join(parts) or 'none'}"


def format_figure(fig: dict, revealed: bool = False) -> str:
    lo, hi = fig["interval"]
    tail = " · revealed" if revealed else ""
    return f"{fig['name']:<28} {fig['k']}/{fig['n']}  ({lo}–{hi}%)  {format_basis(fig['basis'])}{tail}"
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q`
Expected: all Task 1 tests PASS.

- [x] **Step 5: Commit**

```bash
git add scripts/benchmark.py tests/test_benchmark.py
git commit -m "Benchmark: label sets, validation and figures (#55)"
```

### Task 2: The Celery label set

**Satisfies:** AC-8 (the ground truth the baseline rests on), AC-9 (every label records verdict, basis and labeller).

**Files:**
- Create: `docs/calibration/correctness/celery/labels.json` (generated once by the script below, then checked in)
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: `load_label_sets`, `values_match` (Task 6 defines `values_match`; until then the third test below is expected to fail with `AttributeError` and is marked so in Step 2).
- Produces: `docs/calibration/correctness/celery/labels.json` with 21 labels, `role: development`, `commit: 508c1129269d2b1baffc516d8f5c05da06273ef0`.

- [x] **Step 1: Write the failing tests.** Append to `tests/test_benchmark.py`:

```python
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
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q -k "celery"`
Expected: FAIL, `FileNotFoundError` for `labels.json`.

- [x] **Step 3: Generate `labels.json`.** Save this one-off converter in your scratch directory (not in the repository; spec §6.1 converts once and checks in the result) and run it with the set directory as its argument. The `PRECONDITIONS` table is the hand normalisation §6.1 calls for: one entry per precondition in `verdicts.json`, keyed by display id and the setting as written there. Measured consequences leave `effective` equal to `literal`; FR-014's `result_backend` and `database user privileges` and FR-019's `task_routes` are `environment`.

```python
"""One-off: docs/calibration/correctness/celery/verdicts.json -> labels.json (spec §6.1)."""
import json, re, sys
from pathlib import Path

SET = Path(sys.argv[1])
verdicts = json.loads((SET / "verdicts.json").read_text())
report = json.loads((SET / "scan" / "report.json").read_text())
key_of = {f["id"]: f["key"] for f in report["findings"]}

N = lambda: {"type": "none"}
B = lambda v: {"type": "bool", "value": v}
NUM = lambda v, unit=None: {"type": "number", "value": v, **({"unit": unit} if unit else {})}
T = lambda v: {"type": "text", "value": v}

# (display id, setting as in verdicts.json) -> [(label setting, kind, literal, effective)]
PRECONDITIONS = {
    ("FR-001", "broker_pool_acquire_timeout"): [("broker_pool_acquire_timeout", "setting", N(), N())],
    ("FR-001", "broker_pool_limit"): [("broker_pool_limit", "setting", NUM(10), NUM(10))],
    ("FR-001", "redis_socket_connect_timeout"): [("redis_socket_connect_timeout", "setting", N(), NUM(120, "s"))],
    ("FR-001", "redis_socket_timeout"): [("redis_socket_timeout", "setting", NUM(120, "s"), NUM(120, "s"))],
    ("FR-001", "result backend retry_policy"): [("result backend retry_policy", "setting", T("max_retries=20, interval 1 s"), T("max_retries=20, interval 1 s"))],
    ("FR-001", "result_backend_thread_safe"): [("result_backend_thread_safe", "setting", B(False), B(False))],
    ("FR-001", "task_ignore_result"): [("task_ignore_result", "setting", B(False), B(False))],
    ("FR-002", "task_acks_late"): [("task_acks_late", "setting", B(False), B(False))],
    ("FR-002", "task_acks_on_timeout"): [("task_acks_on_timeout", "setting", N(), B(True))],
    ("FR-002", "task_time_limit"): [("task_time_limit", "setting", N(), N())],
    ("FR-003", "worker_deduplicate_successful_tasks"): [("worker_deduplicate_successful_tasks", "setting", B(False), B(False))],
    ("FR-003", "task_acks_late"): [("task_acks_late", "setting", B(False), B(False))],
    ("FR-003", "Task.trail"): [("Task.trail", "setting", B(True), B(True))],
    ("FR-005", "result backend retry_policy"): [("result backend retry_policy", "setting", T("max_retries=20, interval 1 s"), T("max_retries=20, interval 1 s"))],
    ("FR-005", "result_backend_thread_safe"): [("result_backend_thread_safe", "setting", B(False), B(False))],
    ("FR-006", "result_backend_thread_safe"): [("result_backend_thread_safe", "setting", B(False), B(False))],
    ("FR-006", "redis_socket_timeout"): [("redis_socket_timeout", "setting", NUM(120, "s"), NUM(120, "s"))],
    ("FR-006", "result backend retry_policy"): [("result backend retry_policy", "setting", T("max_retries=20"), T("max_retries=20"))],
    ("FR-007", "result_backend_always_retry"): [("result_backend_always_retry", "setting", B(False), B(False))],
    ("FR-007", "result_backend_max_retries"): [("result_backend_max_retries", "setting", NUM("inf"), NUM("inf"))],
    ("FR-009", "task_publish_retry_policy"): [("task_publish_retry_policy", "setting", T("max_retries=3, 0/0.2/0.4 s"), T("max_retries=3, 0/0.2/0.4 s"))],
    ("FR-010", "task_send_sent_event"): [("task_send_sent_event", "setting", B(False), B(False))],
    ("FR-011", "task_acks_late"): [("task_acks_late", "setting", B(False), B(False))],
    ("FR-011", "result_backend_always_retry"): [("result_backend_always_retry", "setting", B(False), B(False))],
    ("FR-011", "task_ignore_result"): [("task_ignore_result", "setting", B(False), B(False))],
    ("FR-012", "task_reject_on_worker_lost"): [("task_reject_on_worker_lost", "setting", N(), N())],
    ("FR-012", "task_acks_late"): [("task_acks_late", "setting", B(False), B(False))],
    ("FR-012", "worker_lost_wait"): [("worker_lost_wait", "setting", NUM(10, "s"), NUM(10, "s"))],
    ("FR-014", "result_backend"): [("result_backend", "environment", N(), T("db+postgresql with a celery_taskmeta table created by an older release"))],
    ("FR-014", "database user privileges"): [("database user privileges", "environment", N(), T("DML only, not table owner"))],
    ("FR-014", "result_backend_always_retry (database backend)"): [("result_backend_always_retry", "setting", B(True), B(False))],
    ("FR-015", "result_backend_always_retry (database backend)"): [("result_backend_always_retry", "setting", B(True), B(False))],
    ("FR-015", "result_backend_max_retries (database backend)"): [("result_backend_max_retries", "setting", NUM(3), NUM("inf"))],
    ("FR-015", "result_backend_base_sleep_between_retries_ms"): [("result_backend_base_sleep_between_retries_ms", "setting", NUM(10), NUM(10))],
    ("FR-016", "task_publish_retry_policy"): [("task_publish_retry_policy", "setting", T("max_retries=3, interval_start=0, interval_step=0.2"), T("max_retries=3, interval_start=0, interval_step=0.2"))],
    ("FR-016", "task_publish_retry"): [("task_publish_retry", "setting", B(True), B(True))],
    ("FR-017", "task_publish_retry_policy"): [("task_publish_retry_policy", "setting", T("max_retries=3"), T("max_retries=3"))],
    ("FR-018", "task_send_sent_event"): [("task_send_sent_event", "setting", B(False), B(False))],
    ("FR-018", "task_publish_retry_policy"): [("task_publish_retry_policy", "setting", T("max_retries=3"), T("max_retries=3"))],
    ("FR-019", "task_routes"): [("task_routes", "environment", N(), T("a user-authored route naming only an exchange"))],
    ("FR-021", "Task.default_retry_delay"): [("Task.default_retry_delay", "setting", NUM(180, "s"), NUM(180, "s"))],
    ("FR-021", "Task.max_retries"): [("Task.max_retries", "setting", NUM(3), NUM(3))],
    ("FR-021", "retry_backoff / retry_jitter"): [("retry_backoff", "setting", B(False), B(False)),
                                                 ("retry_jitter", "setting", B(True), B(True))],
}

REF = re.compile(r"([\w./\-]+\.(?:py|rst|toml|cfg)):(\d+)(?:-(\d+))?((?:\s*(?:and|,)\s*\d+(?:-\d+)?)*)")
HIST = re.compile(r"git show ([0-9a-f]{7,40})")


def ranges(where):
    out = []
    for m in REF.finditer(where or ""):
        path = m.group(1)
        kind = "dependency" if path.startswith("site-packages/") else "docs" if path.endswith(".rst") else "repo"
        spans = [(int(m.group(2)), int(m.group(3) or m.group(2)))]
        spans += [(int(e.group(1)), int(e.group(2) or e.group(1))) for e in re.finditer(r"(\d+)(?:-(\d+))?", m.group(4) or "")]
        out += [{"file": path, "lo": lo, "hi": hi, "kind": kind} for lo, hi in spans]
    out += [{"file": f"git show {h.group(1)}", "kind": "history"} for h in HIST.finditer(where or "")]
    return out


labels = []
for v in verdicts["findings"]:
    fid = v["id"]
    basis = {"read_code": "read"}.get(v["verdict_basis"], v["verdict_basis"])
    pcs = []
    for p in v["preconditions"]:
        for setting, kind, lit, eff in PRECONDITIONS[(fid, p["setting"])]:
            pcs.append({"setting": setting, "kind": kind, "literal": lit, "effective": eff})
    rf = v.get("refuting_fact")
    labels.append({
        "key": v["key"], "display": fid, "source": f"verdicts.json#{fid}",
        "verdict": v["verdict"], "basis": basis, "labelled_by": "claude-fable-5-1",
        "established_by": v["how_to_verify"]["what_you_ran_or_why_not"] if basis == "executed" else None,
        "deserved_confidence": v["confidence_assessment"]["deserved"],
        "duplicate_of": key_of[v["duplicate_of"]] if v.get("duplicate_of") else None,
        "refuting_fact": {"ranges": ranges(rf["where"])} if rf and rf.get("where") else None,
        "preconditions": pcs,
    })
assert len(PRECONDITIONS) == sum(len(v["preconditions"]) for v in verdicts["findings"])
doc = {"schema": "thunderstruck.labels/v1", "repo": "celery/celery",
       "commit": report["repo"]["head"], "role": "development", "scan": "scan/report.json", "labels": labels}
(SET / "labels.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print(len(labels), "labels")
```

Run: `uv run --no-project python "$SCRATCH/build_labels.py" docs/calibration/correctness/celery`
Expected: `21 labels`. Open the file and check three labels by eye against `verdicts.json`: FR-001 (three repo ranges), FR-006 (`duplicate_of` is FR-001's key `f62fb0c3468b`), FR-020 (`basis: read`, `established_by: null`).

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q -k "celery"`
Expected: `test_celery_labels_agree_with_the_evidence` and `test_celery_refuting_ranges_are_the_evidence_ranges` PASS. `test_celery_has_exactly_five_discriminating_preconditions` fails with `AttributeError: module 'benchmark' has no attribute 'values_match'` until Task 6; that is the only failure allowed on this commit, so mark it for now:

```python
@pytest.mark.xfail(reason="values_match arrives in Task 6", strict=True)
```

placed on the line above `def test_celery_has_exactly_five_discriminating_preconditions`. Task 6 removes the marker.

- [x] **Step 5: Commit**

```bash
git add docs/calibration/correctness/celery/labels.json tests/test_benchmark.py
git commit -m "Benchmark: the Celery label set from the executed review (#55)"
```

### Task 3: Runs, the report adapter and confidence

**Satisfies:** AC-3, AC-7, AC-8 (today's confidences: 8 of 21 exact).

**Files:**
- Modify: `scripts/benchmark.py` (append)
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: `InputError`, `RUN_SCHEMA`, `RUN_VERDICTS`, `CONFIDENCE`, `load_label_sets`.
- Produces: `validate_run(doc: dict, where: str) -> list[str]`; `load_run(path: Path) -> dict`; `run_from_report(report_path: Path) -> dict` (a run with `produced_by.model` None); `split_run(run: dict, label_set: dict) -> tuple[dict, list[str], list[str]]` returning (records by key, unlabelled keys, excluded keys); `score_confidence(records: dict, label_set: dict) -> dict` with `rows`, `counts` (`exact`, `within one`, `over`, `under`), `high_above_deserved`, `keys`.

- [x] **Step 1: Write the failing tests.** Append:

```python
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
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q -k "confidence or unlabelled or display_id or labeller or invalid_run"`
Expected: FAIL, `AttributeError: module 'benchmark' has no attribute 'run_from_report'` (and the like).

- [x] **Step 3: Write the implementation.** Append to `scripts/benchmark.py`:

```python


# --------------------------------------------------------------------- runs
def validate_run(doc: dict, where: str) -> list[str]:
    if doc.get("schema") != RUN_SCHEMA:
        return [f"{where}: schema is not {RUN_SCHEMA}"]
    p = []
    if not doc.get("commit"):
        p.append(f"{where}: commit is missing")
    if not isinstance(doc.get("produced_by"), dict) or not doc["produced_by"].get("stage"):
        p.append(f"{where}: produced_by.stage is missing")
    if not isinstance(doc.get("findings"), dict):
        return p + [f"{where}: findings is not an object keyed by finding key"]
    for key, rec in sorted(doc["findings"].items()):
        v = rec.get("verdict")
        if v is not None and v not in RUN_VERDICTS:
            p.append(f"{where}: {key}: verdict {v!r} is not one of {', '.join(RUN_VERDICTS)}")
        c = rec.get("confidence")
        if c is not None and c not in CONFIDENCE:
            p.append(f"{where}: {key}: confidence {c!r} is not one of {', '.join(CONFIDENCE)}")
    return p


def load_run(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise InputError([f"{path}: {e}"]) from None
    problems = validate_run(doc, str(path))
    if problems:
        raise InputError(problems)
    return doc


def run_from_report(report_path: Path) -> dict:
    """--report: a scan's confidences as a run."""
    try:
        report = json.loads(report_path.read_text())
    except (OSError, ValueError) as e:
        raise InputError([f"{report_path}: {e}"]) from None
    findings = {}
    for f in report.get("findings") or []:
        if f.get("key"):
            findings[f["key"]] = {"confidence": f.get("confidence")}
    return {"schema": RUN_SCHEMA, "commit": (report.get("repo") or {}).get("head", ""),
            "produced_by": {"stage": "investigator", "model": None, "source": str(report_path)},
            "findings": findings}


def split_run(run: dict, label_set: dict) -> tuple[dict, list[str], list[str]]:
    """(scored records by key, unlabelled keys, keys excluded by independence)."""
    model = (run.get("produced_by") or {}).get("model")
    scored, unlabelled, excluded = {}, [], []
    for key, rec in sorted(run["findings"].items()):
        lb = label_set["_by_key"].get(key)
        if lb is None:
            unlabelled.append(key)
        elif model and lb["labelled_by"] == model:
            excluded.append(key)
        else:
            scored[key] = rec
    return scored, unlabelled, excluded


# ------------------------------------------------------------------ scoring
def score_confidence(records: dict, label_set: dict) -> dict:
    rows = {}
    for k, r in records.items():
        deserved = label_set["_by_key"][k].get("deserved_confidence")
        if not r.get("confidence") or not deserved:
            continue
        step = CONFIDENCE.index(r["confidence"]) - CONFIDENCE.index(deserved)
        rows[k] = {"run": r["confidence"], "deserved": deserved, "step": step}
    counts = {"exact": sum(1 for x in rows.values() if x["step"] == 0),
              "within one": sum(1 for x in rows.values() if abs(x["step"]) <= 1),
              "over": sum(1 for x in rows.values() if x["step"] > 0),
              "under": sum(1 for x in rows.values() if x["step"] < 0)}
    high_above = sorted(k for k, x in rows.items() if x["run"] == "high" and x["step"] > 0)
    return {"rows": rows, "counts": counts, "high_above_deserved": high_above, "keys": sorted(rows)}
```

- [x] **Step 4: Run the tests to verify they pass** (same command as Step 2). Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add scripts/benchmark.py tests/test_benchmark.py
git commit -m "Benchmark: runs, the report adapter and confidence scoring (#55)"
```

### Task 4: Verdicts, duplicates and the spike refuter baseline

**Satisfies:** AC-2, AC-8 (the spike's read-only refutation: 15 of 21 same class).

**Files:**
- Modify: `scripts/benchmark.py` (append)
- Create: `docs/calibration/correctness/celery/runs/spike-refuter.json` (generated once by the script below, then checked in)
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: `VERDICTS`, `load_run`, `split_run`.
- Produces: `SAME`, `ONE_STEP`, `WRONG_DIRECTION`, `CORRECT_REFUTED`, `VERDICT_OUTCOMES`, `VERDICT_MATRIX`; `verdict_outcome(run_verdict: str, label_verdict: str) -> str`; `score_verdicts(records, label_set) -> dict` with `rows`, `counts`, `keys`; `score_duplicates(records, label_set) -> dict` with `found`, `missed`, `false`, `keys`.

- [x] **Step 1: Write the failing tests.** Append:

```python
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
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q -k "matrix or spike or duplicates"`
Expected: FAIL, `AttributeError: ... 'verdict_outcome'`.

- [x] **Step 3: Write the implementation.** Append to `scripts/benchmark.py`:

```python


SAME, ONE_STEP, WRONG_DIRECTION, CORRECT_REFUTED = "same", "one step", "wrong direction", "correct refuted"
VERDICT_OUTCOMES = (SAME, ONE_STEP, WRONG_DIRECTION, CORRECT_REFUTED)
VERDICT_MATRIX = {
    #                   correct          correct_but_gated  partially_correct  wrong
    "upheld":           (SAME,            ONE_STEP,          WRONG_DIRECTION,   WRONG_DIRECTION),
    "upheld_but_gated": (ONE_STEP,        SAME,              WRONG_DIRECTION,   WRONG_DIRECTION),
    "narrowed":         (ONE_STEP,        ONE_STEP,          SAME,              ONE_STEP),
    "refuted":          (CORRECT_REFUTED, CORRECT_REFUTED,   ONE_STEP,          SAME),
}


def verdict_outcome(run_verdict: str, label_verdict: str) -> str:
    return VERDICT_MATRIX[run_verdict][VERDICTS.index(label_verdict)]


def score_verdicts(records: dict, label_set: dict) -> dict:
    rows = {k: {"run": r["verdict"], "label": label_set["_by_key"][k]["verdict"],
                "outcome": verdict_outcome(r["verdict"], label_set["_by_key"][k]["verdict"])}
            for k, r in records.items() if r.get("verdict")}
    counts = {o: sum(1 for x in rows.values() if x["outcome"] == o) for o in VERDICT_OUTCOMES}
    return {"rows": rows, "counts": counts, "keys": sorted(rows)}


def score_duplicates(records: dict, label_set: dict) -> dict:
    stated = {k: r.get("duplicate_of") for k, r in records.items() if "duplicate_of" in r}
    labelled = {k: lb["duplicate_of"] for k, lb in label_set["_by_key"].items()
                if lb.get("duplicate_of") and k in stated}
    found = sorted(k for k, d in labelled.items() if stated.get(k) == d)
    missed = sorted(k for k, d in labelled.items() if stated.get(k) != d)
    false = sorted(k for k, d in stated.items() if d and labelled.get(k) != d)
    return {"found": found, "missed": missed, "false": false, "keys": sorted(stated)}
```

- [x] **Step 4: Generate the spike run file.** Save this one-off converter in your scratch directory and run it (spec §6.2):

```python
"""One-off: spikes/refute/*.json -> runs/spike-refuter.json (spec §6.2)."""
import json, sys
from pathlib import Path

SET = Path(sys.argv[1])
report = json.loads((SET / "scan" / "report.json").read_text())
key_of = {f["id"]: f["key"] for f in report["findings"]}
sources = sorted((SET / "spikes" / "refute").glob("refute_*.json"))
findings = {}
for src in sources:
    for f in json.loads(src.read_text())["findings"]:
        findings[key_of[f["id"]]] = {"verdict": f["verdict"],
                                    "duplicate_of": key_of[f["duplicate_of"]] if f.get("duplicate_of") else None}
run = {"schema": "thunderstruck.benchmark-run/v1", "commit": report["repo"]["head"],
       "produced_by": {"stage": "refuter", "model": None,
                       "source": "spikes/refute/refute_H01-H05.json and refute_H06-H10.json, ids mapped to keys "
                                 "through scan/report.json; the spike files do not record the refuters' model, "
                                 "so independence is not checked"},
       "findings": dict(sorted(findings.items()))}
(SET / "runs").mkdir(exist_ok=True)
(SET / "runs" / "spike-refuter.json").write_text(json.dumps(run, indent=2) + "\n")
print(len(findings))
```

Run: `uv run --no-project python "$SCRATCH/build_spike_run.py" docs/calibration/correctness/celery`
Expected: `21`.

- [x] **Step 5: Run the tests to verify they pass** (same command as Step 2). Expected: PASS, including all 16 matrix cells.

- [x] **Step 6: Commit**

```bash
git add scripts/benchmark.py tests/test_benchmark.py docs/calibration/correctness/celery/runs/spike-refuter.json
git commit -m "Benchmark: verdict matrix, duplicates and the spike refuter baseline (#55)"
```

### Task 5: What a bundle shows

**Satisfies:** AC-4, AC-8 (today's bundles: 4 of 9 in-file refuting facts shown).

**Files:**
- Modify: `scripts/benchmark.py` (append)
- Test: `tests/test_benchmark.py` (imports `scripts/bundle.py` to render Source blocks; the benchmark itself never imports it)

**Interfaces:**
- Consumes: `InputError`, `run_from_report`, `split_run`; `bundle.section_source(repo: Path, hs: dict, budget: int) -> str` (existing, tests only).
- Produces: `shown_lines(bundle_text: str) -> tuple[str, list[tuple[int, int]]] | None`; `add_bundles(run: dict, bundles_dir: Path, report_path: Path) -> dict` (adds `bundle: {"file": str, "shown": list[[lo, hi]] | None}` to each record); `SHOWN`, `NOT_SHOWN`, `ELSEWHERE`, `NOT_IN_REPO`, `UNREADABLE`, `BUNDLE_OUTCOMES`; `score_bundles(records, label_set) -> dict` with `rows` (`outcome`, `partly_elsewhere`), `counts` (each outcome plus `partly elsewhere`), `keys`.

- [x] **Step 1: Write the failing tests.** Append:

```python
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
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q -k "bundle or unreadable"`
Expected: FAIL, `AttributeError: ... 'add_bundles'`.

- [x] **Step 3: Write the implementation.** Insert after `run_from_report` (before `split_run`), keeping the adapters together:

```python
_NOTE = re.compile(r"^## Source — `(?P<file>[^`]+)`\n\n_(?P<note>[^\n]*)_\n\n```[^\n]*\n(?P<body>.*?)\n```",
                   re.S | re.M)
_MARKER = re.compile(r"\n\n\.\.\. \[[^\]]*: \d+ characters omitted\] \.\.\.\n\n")
_WHOLE = re.compile(r"^whole file, (\d+) lines$")
_RANGE = re.compile(r"^lines (\d+)-(\d+) — ")
_TRIMMED = re.compile(r"^file trimmed to fit the budget; (\d+) lines total$")


def shown_lines(bundle_text: str) -> tuple[str, list[tuple[int, int]]] | None:
    """The file and line ranges a bundle's Source block shows; None if unparsable."""
    m = _NOTE.search(bundle_text)
    if not m:
        return None
    note, body = m.group("note"), m.group("body")
    if w := _WHOLE.match(note):
        return m.group("file"), [(1, int(w.group(1)))]  # never clipped
    if r := _RANGE.match(note):
        start, end = int(r.group(1)), int(r.group(2))
    elif t := _TRIMMED.match(note):
        start, end = 1, int(t.group(1))
    else:
        return None
    if body.endswith("\n"):
        # The excerpt ran to the file's final newline; bundle.py counted the empty line after it.
        body, end = body[:-1], end - 1
    parts = _MARKER.split(body)
    if len(parts) == 1:
        return m.group("file"), [(start, end)]
    if len(parts) != 2:
        return None
    head, tail = parts
    # A line the character cut split is not shown: drop the last head line and the first tail line.
    n_head = len(head.split("\n")) - 1
    n_tail = len(tail.split("\n")) - 1
    ranges = []
    if n_head > 0:
        ranges.append((start, start + n_head - 1))
    if n_tail > 0:
        ranges.append((end - n_tail + 1, end))
    return m.group("file"), ranges


def add_bundles(run: dict, bundles_dir: Path, report_path: Path) -> dict:
    """--bundles: attach what each finding's bundle shows, joined through the scan."""
    try:
        index = json.loads((bundles_dir / "index.json").read_text())
        report = json.loads(report_path.read_text())
    except (OSError, ValueError) as e:
        raise InputError([f"{bundles_dir}: {e}"]) from None
    files = {b["id"]: b["file"] for b in index.get("bundles") or []}
    for f in report.get("findings") or []:
        key, hid = f.get("key"), f.get("hotspot_id")
        if not key or hid not in files:
            continue
        path = bundles_dir / f"{hid}.md"
        parsed = shown_lines(path.read_text()) if path.is_file() else None
        rec = run["findings"].setdefault(key, {})
        if parsed is None or parsed[0] != files[hid]:
            rec["bundle"] = {"file": files[hid], "shown": None}
        else:
            rec["bundle"] = {"file": files[hid], "shown": [list(r) for r in parsed[1]]}
    return run
```

and append to the scoring section:

```python


SHOWN, NOT_SHOWN, ELSEWHERE, NOT_IN_REPO, UNREADABLE = (
    "shown", "not shown", "elsewhere", "not in repository", "unreadable")
BUNDLE_OUTCOMES = (SHOWN, NOT_SHOWN, ELSEWHERE, NOT_IN_REPO, UNREADABLE)


def score_bundles(records: dict, label_set: dict) -> dict:
    rows = {}
    for k, r in records.items():
        fact = label_set["_by_key"][k].get("refuting_fact")
        if not fact or "bundle" not in r:
            continue
        repo = [x for x in fact.get("ranges") or [] if x["kind"] == "repo"]
        bfile, shown = r["bundle"]["file"], r["bundle"]["shown"]
        mine = [x for x in repo if x["file"] == bfile]
        partly = bool(mine) and len(mine) < len(repo)
        if not repo:
            outcome = NOT_IN_REPO
        elif shown is None:
            outcome = UNREADABLE
        elif not mine:
            outcome = ELSEWHERE
        elif all(any(a <= x["lo"] and x["hi"] <= b for a, b in shown) for x in mine):
            outcome = SHOWN
        else:
            outcome = NOT_SHOWN
        rows[k] = {"outcome": outcome, "partly_elsewhere": outcome == SHOWN and partly}
    counts = {o: sum(1 for x in rows.values() if x["outcome"] == o) for o in BUNDLE_OUTCOMES}
    counts["partly elsewhere"] = sum(1 for x in rows.values() if x["partly_elsewhere"])
    return {"rows": rows, "counts": counts, "keys": sorted(rows)}
```

- [x] **Step 4: Run the tests to verify they pass** (same command as Step 2). Expected: PASS; the baseline is 4 shown, 5 not shown, 3 elsewhere, FR-003 and FR-015 partly elsewhere.

- [x] **Step 5: Commit**

```bash
git add scripts/benchmark.py tests/test_benchmark.py
git commit -m "Benchmark: what each bundle's Source block shows (#55)"
```

### Task 6: Defaults

**Satisfies:** AC-5.

**Files:**
- Modify: `scripts/benchmark.py` (append)
- Test: `tests/test_benchmark.py` (and remove Task 2's `xfail` marker)

**Interfaces:**
- Produces: `normalise_value(raw) -> dict`; `values_match(a: dict, b: dict) -> bool`; `EFFECTIVE`, `LITERAL_ONLY`, `NEITHER`, `NOT_STATED`, `DEFAULT_OUTCOMES`; `score_defaults(records, label_set) -> dict` with `rows` (`key`, `setting`, `discriminating`, `outcome`), `counts` (over discriminating preconditions), `non_discriminating`, `keys`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 6 -----------------------------------------------------------------
@pytest.mark.parametrize("raw, value", [
    (None, {"type": "none"}), ("None", {"type": "none"}), ("null", {"type": "none"}),
    (True, {"type": "bool", "value": True}), ("false", {"type": "bool", "value": False}),
    ("120.0", {"type": "number", "value": 120.0}), ("120 s", {"type": "number", "value": 120.0, "unit": "s"}),
    ("500ms", {"type": "number", "value": 0.5, "unit": "s"}), ("inf", {"type": "number", "value": "inf"}),
    (3, {"type": "number", "value": 3}), ("  Max_Retries=3 ", {"type": "text", "value": "max_retries=3"}),
])
def test_normalise_value(raw, value):
    assert b.normalise_value(raw) == value


def test_a_bare_number_matches_a_number_with_a_unit_but_not_another_unit():
    assert b.values_match({"type": "number", "value": 120.0}, {"type": "number", "value": 120, "unit": "s"})
    assert not b.values_match({"type": "number", "value": 120, "unit": "ms"}, {"type": "number", "value": 120, "unit": "s"})
    assert not b.values_match({"type": "number", "value": "inf"}, {"type": "number", "value": 3})


def test_defaults_effective_literal_neither_and_not_stated():
    s = _celery()
    run = {
        _key("FR-001"): {"preconditions": [{"setting": "redis_socket_connect_timeout", "default": "120.0"}]},
        _key("FR-002"): {"preconditions": [{"setting": "task_acks_on_timeout", "default": "None"}]},
        _key("FR-015"): {"preconditions": [{"setting": "Result_Backend_Always_Retry", "default": True},
                                           {"setting": "result_backend_max_retries", "default": "7"}]},
    }
    m = b.score_defaults(run, s)
    assert m["counts"] == {"matches effective": 1, "matches literal only": 2, "matches neither": 1, "not stated": 0}
    assert all(not x["discriminating"] for x in m["rows"] if x["outcome"] == "not stated")


def test_environment_preconditions_are_not_scored():
    s = _celery()
    m = b.score_defaults({_key("FR-014"): {"preconditions": [{"setting": "result_backend", "default": "x"}]}}, s)
    assert {x["setting"] for x in m["rows"]} == {"result_backend_always_retry"}
    assert m["counts"]["not stated"] == 1


def test_setting_names_ignore_case_and_surrounding_space():
    m = b.score_defaults({_key("FR-002"): {"preconditions": [{"setting": "  TASK_ACKS_ON_TIMEOUT ", "default": True}]}},
                         _celery())
    assert m["counts"]["matches effective"] == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q -k "normalise or number or defaults or environment or setting_names or discriminating"`
Expected: the new tests FAIL with `AttributeError`; `test_celery_has_exactly_five_discriminating_preconditions` XFAILs.

- [ ] **Step 3: Write the implementation.** Append to `scripts/benchmark.py`:

```python


_NUM = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(s|ms)?$")


def normalise_value(raw) -> dict:
    """A run's stated default as a §4.5 value."""
    if raw is None:
        return {"type": "none"}
    if isinstance(raw, bool):
        return {"type": "bool", "value": raw}
    if isinstance(raw, (int, float)):
        return {"type": "number", "value": raw}
    text = " ".join(str(raw).split())
    low = text.casefold()
    if low in ("none", "null"):
        return {"type": "none"}
    if low in ("true", "false"):
        return {"type": "bool", "value": low == "true"}
    if low in ("inf", "infinity"):
        return {"type": "number", "value": "inf"}
    if m := _NUM.match(low):
        value = float(m.group(1))
        if m.group(2) == "ms":
            return {"type": "number", "value": value / 1000, "unit": "s"}
        return {"type": "number", "value": value, **({"unit": "s"} if m.group(2) else {})}
    return {"type": "text", "value": low}


def values_match(a: dict, b: dict) -> bool:
    if a["type"] != b["type"]:
        return False
    if a["type"] == "none":
        return True
    if a["type"] == "number":
        va, vb = a["value"], b["value"]
        if (va == "inf") != (vb == "inf"):
            return False
        if va != "inf" and float(va) != float(vb):
            return False
        return not a.get("unit") or not b.get("unit") or a["unit"] == b["unit"]
    if a["type"] == "text":
        return " ".join(str(a["value"]).split()).casefold() == " ".join(str(b["value"]).split()).casefold()
    return a["value"] == b["value"]


EFFECTIVE, LITERAL_ONLY, NEITHER, NOT_STATED = "matches effective", "matches literal only", "matches neither", "not stated"
DEFAULT_OUTCOMES = (EFFECTIVE, LITERAL_ONLY, NEITHER, NOT_STATED)


def score_defaults(records: dict, label_set: dict) -> dict:
    rows = []
    for k, r in sorted(records.items()):
        if "preconditions" not in r:
            continue
        stated = {str(p.get("setting", "")).strip().casefold(): p.get("default") for p in r["preconditions"]}
        for pc in label_set["_by_key"][k].get("preconditions") or []:
            if pc["kind"] != "setting":
                continue
            name = pc["setting"].casefold()
            discriminating = not values_match(pc["literal"], pc["effective"])
            if name not in stated:
                outcome = NOT_STATED
            else:
                v = normalise_value(stated[name])
                outcome = (EFFECTIVE if values_match(v, pc["effective"])
                           else LITERAL_ONLY if values_match(v, pc["literal"]) else NEITHER)
            rows.append({"key": k, "setting": pc["setting"], "discriminating": discriminating, "outcome": outcome})
    head = [x for x in rows if x["discriminating"]]
    counts = {o: sum(1 for x in head if x["outcome"] == o) for o in DEFAULT_OUTCOMES}
    rest = {o: sum(1 for x in rows if not x["discriminating"] and x["outcome"] == o) for o in DEFAULT_OUTCOMES}
    return {"rows": rows, "counts": counts, "non_discriminating": rest,
            "keys": sorted({x["key"] for x in rows})}
```

- [ ] **Step 4: Remove the `@pytest.mark.xfail(...)` line** above `test_celery_has_exactly_five_discriminating_preconditions` (with `strict=True` it now fails as XPASS until removed).

- [ ] **Step 5: Run the tests to verify they pass** (same command as Step 2). Expected: PASS, including the five discriminating preconditions.

- [ ] **Step 6: Commit**

```bash
git add scripts/benchmark.py tests/test_benchmark.py
git commit -m "Benchmark: defaults scored against the effective value (#55)"
```

### Task 7: The command

**Satisfies:** AC-1, AC-6, AC-7, AC-8 (all three baselines from one command).

**Files:**
- Modify: `scripts/benchmark.py` (append)
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: every scorer above, `load_label_sets`, `default_label_paths`, `load_run`, `run_from_report`, `add_bundles`, `split_run`, `select_set`, `basis_of`, `figure`, `format_figure`, `wilson`.
- Produces: `PER_FINDING` (the per-finding fields hidden for a holdout set); `SCORERS: dict[str, Callable]`; `evaluate(runs: list[dict], sets: list[dict], reveal: bool = False) -> dict` (schema `thunderstruck.benchmark/v1`; `runs[]` with `repo`, `commit`, `role`, `revealed`, `produced_by`, `independence_checked`, `display`, `unlabelled`, `excluded`, `measures`; and `pooled`); `pooled(results: list[dict]) -> dict`; `render(result: dict) -> str`; `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 7 -----------------------------------------------------------------
def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "benchmark.py"), *args],
                          capture_output=True, text=True)


def test_cli_scores_every_baseline_and_every_rate_line_carries_its_basis():
    p = _cli("--run", str(CELERY / "runs" / "spike-refuter.json"),
             "--report", str(CELERY / "scan" / "report.json"), "--bundles", str(CELERY / "scan" / "bundles"))
    assert p.returncode == 0, p.stderr
    rate_lines = [ln for ln in p.stdout.splitlines() if re.search(r" \d+/\d+  \(", ln)]
    assert len(rate_lines) >= 15
    for ln in rate_lines:
        assert "celery/celery@508c112" in ln and "n=" in ln and "labels:" in ln, ln
    assert re.search(r"verdict: same\s+15/21  \(50–86%\)", p.stdout)
    assert re.search(r"confidence: exact\s+8/21  \(21–59%\)", p.stdout)
    assert re.search(r"refuting fact shown\s+4/9  \(19–73%\)", p.stdout)
    assert "high above deserved: FR-001 (f62fb0c3468b), FR-003 (b1af3746845c)" in p.stdout
    assert "  found: FR-006 (df2cb49b3e2c)" in p.stdout


def test_json_output_carries_the_basis_on_every_figure_and_is_deterministic():
    args = ("--run", str(CELERY / "runs" / "spike-refuter.json"), "--json")
    a, c = _cli(*args), _cli(*args)
    assert a.returncode == 0 and a.stdout == c.stdout
    doc = json.loads(a.stdout)
    figs = [f for r in doc["runs"] for m in r["measures"].values() for f in m["figures"]]
    assert figs and all({"repo", "commit", "n", "labellers"} <= set(f["basis"]) for f in figs)


@pytest.mark.parametrize("args, needle", [
    (["--bundles", "x"], "--bundles needs --report"),
    ([], "nothing to score"),
])
def test_cli_refuses_incomplete_arguments(args, needle):
    p = _cli(*args)
    assert p.returncode == 2 and needle in p.stderr


def test_cli_refuses_an_invalid_label_set_and_scores_nothing(tmp_path):
    doc = _set()
    doc["labels"][0].pop("basis")
    _write_set(tmp_path, doc)
    run = tmp_path / "run.json"
    run.write_text(json.dumps(_run({"k1": {"verdict": "upheld"}}, commit="a" * 40)))
    p = _cli("--labels", str(tmp_path / "lib"), "--run", str(run))
    assert p.returncode == 2 and "basis is missing" in p.stderr and p.stdout == ""


def test_a_scan_of_an_unlabelled_commit_is_refused(tmp_path):
    report = json.loads((CELERY / "scan" / "report.json").read_text())
    report["repo"]["head"] = "c" * 40
    p = tmp_path / "report.json"
    p.write_text(json.dumps(report))
    r = _cli("--report", str(p))
    assert r.returncode == 2 and "matches no loaded label set (loaded: celery/celery@508c112)" in r.stderr


def test_a_partial_run_states_how_many_labelled_findings_it_covers(tmp_path):
    run = tmp_path / "run.json"
    run.write_text(json.dumps(_run({_key(i): {"verdict": "upheld"} for i in ("FR-001", "FR-002", "FR-004")})))
    r = _cli("--run", str(run))
    assert r.returncode == 0 and "n=3 of 21 labelled findings" in r.stdout


def test_a_malformed_run_file_is_refused_without_a_traceback(tmp_path):
    run = tmp_path / "run.json"
    run.write_text("{not json")
    r = _cli("--run", str(run))
    assert r.returncode == 2 and str(run) in r.stderr and "Traceback" not in r.stderr
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q -k "cli or json_output or unlabelled_commit or partial_run or malformed"`
Expected: FAIL; the script has no `main` yet and exits 0 with no output.

- [ ] **Step 3: Write the implementation.** Append to `scripts/benchmark.py`:

```python


# ------------------------------------------------------------------ results
def _figures(measure: str, m: dict, basis: dict) -> list[dict]:
    c = m.get("counts", {})
    if measure == "verdicts":
        n = len(m["keys"])
        return [figure(f"verdict: {o}", c[o], n, basis) for o in VERDICT_OUTCOMES]
    if measure == "duplicates":
        pairs = len(m["found"]) + len(m["missed"])
        return [figure("duplicates found", len(m["found"]), pairs, basis),
                figure("false duplicates", len(m["false"]), len(m["keys"]), basis)]
    if measure == "confidence":
        n = len(m["keys"])
        return [figure(f"confidence: {o}", c[o], n, basis) for o in ("exact", "within one", "over", "under")]
    if measure == "bundles":
        located = c[SHOWN] + c[NOT_SHOWN]
        n = len(m["keys"])
        return [figure("refuting fact shown", c[SHOWN], located, basis),
                figure("shown, partly elsewhere", c["partly elsewhere"], located, basis)] + [
                figure(f"refuting fact {o}", c[o], n, basis) for o in (ELSEWHERE, NOT_IN_REPO, UNREADABLE)]
    if measure == "defaults":
        n = sum(c.values())
        return [figure(f"default {o}", c[o], n, basis) for o in DEFAULT_OUTCOMES]
    raise ValueError(measure)


PER_FINDING = ("rows", "found", "missed", "false", "high_above_deserved")
SCORERS = {"verdicts": score_verdicts, "duplicates": score_duplicates, "confidence": score_confidence,
           "bundles": score_bundles, "defaults": score_defaults}


def evaluate(runs: list[dict], sets: list[dict], reveal: bool = False) -> dict:
    out = []
    for run in runs:
        ls = select_set(sets, run.get("commit", ""))
        records, unlabelled, excluded = split_run(run, ls)
        hide = ls["role"] == "holdout" and not reveal
        measures = {}
        for name, scorer in SCORERS.items():
            m = scorer(records, ls)
            if not m["keys"]:
                continue
            basis = basis_of(ls, m["keys"])
            m["figures"] = _figures(name, m, basis)
            if hide:
                for detail in PER_FINDING:
                    m.pop(detail, None)
            measures[name] = m
        out.append({"repo": ls["repo"], "commit": ls["commit"], "role": ls["role"],
                    "revealed": ls["role"] == "holdout" and reveal,
                    "produced_by": run.get("produced_by"),
                    "independence_checked": bool((run.get("produced_by") or {}).get("model")),
                    "display": {lb["key"]: lb.get("display", "") for lb in ls["labels"]},
                    "unlabelled": unlabelled, "excluded": excluded, "measures": measures})
    return {"schema": RESULT_SCHEMA, "runs": out, "pooled": pooled(out)}


def pooled(results: list[dict]) -> dict:
    """Pooled figures per measure, only across runs on distinct sets."""
    commits = [r["commit"] for r in results]
    if len(set(commits)) < 2 or len(set(commits)) != len(commits):
        return {}
    out: dict[str, list[dict]] = {}
    for r in results:
        for name, m in r["measures"].items():
            for fig in m["figures"]:
                slot = {f["name"]: f for f in out.setdefault(name, [])}
                if fig["name"] in slot:
                    f = slot[fig["name"]]
                    k, n = f["k"] + fig["k"], f["n"] + fig["n"]
                    f.update({"k": k, "n": n, "interval": list(wilson(k, n))})
                    f["basis"] = _merge_basis(f["basis"], fig["basis"])
                else:
                    out[name].append(json.loads(json.dumps(fig)))
    return out


def _merge_basis(a: dict, b: dict) -> dict:
    mix = json.loads(json.dumps(a["labellers"]))
    for who, bases in b["labellers"].items():
        for bs, c in bases.items():
            mix.setdefault(who, {})[bs] = mix.get(who, {}).get(bs, 0) + c
    return {"repo": f"{a['repo']} + {b['repo']}", "commit": "pooled", "n": a["n"] + b["n"],
            "labelled": a["labelled"] + b["labelled"], "labellers": mix}


def render(result: dict) -> str:
    lines = []
    for r in result["runs"]:
        pb = r["produced_by"] or {}
        lines.append(f"# {r['repo']}@{r['commit'][:7]} ({r['role']}) — {pb.get('stage')}"
                     f"{' · ' + pb['model'] if pb.get('model') else ''}")
        if not r["independence_checked"]:
            lines.append("independence not checked: the run does not record a model")
        if r["excluded"]:
            lines.append(f"excluded: {len(r['excluded'])} — labeller is the scored model")
        if r["unlabelled"]:
            lines.append(f"unlabelled: {len(r['unlabelled'])} — " + ", ".join(r["unlabelled"]))
        for name, m in r["measures"].items():
            lines.append(f"## {name}")
            for fig in m["figures"]:
                lines.append(format_figure(fig, revealed=r["revealed"]))
            if m.get("high_above_deserved"):
                lines.append("high above deserved: " + ", ".join(_disp(r, k) for k in _order(r, m["high_above_deserved"])))
            if any(detail in m for detail in PER_FINDING):
                lines += _rows(name, m, r)
        lines.append("")
    for name, figs in result["pooled"].items():
        lines.append(f"## pooled {name}")
        lines += [format_figure(f) for f in figs]
    return "\n".join(lines).rstrip() + "\n"


def _disp(run_result: dict, key: str) -> str:
    d = run_result["display"].get(key)
    return f"{d} ({key})" if d else key


def _order(run_result: dict, keys) -> list[str]:
    """Keys in display order, so a reader finds FR-001 first; ties and missing ids by key."""
    return sorted(keys, key=lambda k: (run_result["display"].get(k) or "~", k))


def _rows(name: str, m: dict, r: dict) -> list[str]:
    if name == "verdicts":
        return [f"  {_disp(r, k)}: {x['run']} vs {x['label']} → {x['outcome']}" for k, x in ((k, m["rows"][k]) for k in _order(r, m["rows"]))]
    if name == "confidence":
        return [f"  {_disp(r, k)}: {x['run']} vs {x['deserved']} ({x['step']:+d})"
                for k, x in ((k, m["rows"][k]) for k in _order(r, m["rows"]))]
    if name == "bundles":
        return [f"  {_disp(r, k)}: {x['outcome']}{' (partly elsewhere)' if x['partly_elsewhere'] else ''}"
                for k, x in ((k, m["rows"][k]) for k in _order(r, m["rows"]))]
    if name == "defaults":
        return [f"  {_disp(r, x['key'])} {x['setting']}: {x['outcome']}{'' if x['discriminating'] else ' (non-discriminating)'}"
                for x in sorted(m["rows"], key=lambda x: (r["display"].get(x["key"]) or "~", x["key"]))]
    if name == "duplicates":
        return ([f"  found: {_disp(r, k)}" for k in m["found"]] + [f"  missed: {_disp(r, k)}" for k in m["missed"]]
                + [f"  false: {_disp(r, k)}" for k in m["false"]])
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", action="append", type=Path, default=[], help="a run file (repeatable)")
    ap.add_argument("--report", type=Path, help="a scan's report.json: its confidences")
    ap.add_argument("--bundles", type=Path, help="that scan's bundles/ (needs --report)")
    ap.add_argument("--labels", action="append", type=Path, default=[], help="a label set directory (repeatable)")
    ap.add_argument("--json", action="store_true", help="machine output")
    ap.add_argument("--reveal", action="store_true", help="per-finding rows for holdout sets")
    a = ap.parse_args(argv)
    try:
        if a.bundles and not a.report:
            raise InputError(["--bundles needs --report (the scan that produced the bundles)"])
        if not a.run and not a.report:
            raise InputError(["nothing to score: give --run or --report"])
        paths = [d / "labels.json" for d in a.labels] or default_label_paths()
        sets = load_label_sets(paths)
        runs = [load_run(p) for p in a.run]
        if a.report:
            run = run_from_report(a.report)
            if a.bundles:
                add_bundles(run, a.bundles, a.report)
            runs.append(run)
        result = evaluate(runs, sets, reveal=a.reveal)
    except InputError as e:
        for p in e.problems:
            print(f"benchmark: {p}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n" if a.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass** (same command as Step 2). Expected: PASS.

- [ ] **Step 5: Run the command by hand and read the output**

Run: `uv run scripts/benchmark.py --run docs/calibration/correctness/celery/runs/spike-refuter.json --report docs/calibration/correctness/celery/scan/report.json --bundles docs/calibration/correctness/celery/scan/bundles`
Expected: three blocks: refuter (`verdict: same 15/21 (50–86%)`, `duplicates found 1/1`), investigator (`confidence: exact 8/21 (21–59%)`, `high above deserved: FR-001 (f62fb0c3468b), FR-003 (b1af3746845c)`) and bundles (`refuting fact shown 4/9 (19–73%)`); each run block says `independence not checked`; every rate line ends `celery/celery@508c112 · n=… · labels: … claude-fable-5-1 (…)`.

- [ ] **Step 6: Commit**

```bash
git add scripts/benchmark.py tests/test_benchmark.py
git commit -m "Benchmark: the command, per-set and pooled figures, holdout (#55)"
```

### Task 8: A second repository, stability and isolation

**Satisfies:** AC-1 (stdlib only, in CI), AC-9 (adding labels never changes an existing finding's result), AC-10.

**Files:**
- Test: `tests/test_benchmark.py` (the synthetic set is written to `tmp_path`, so nothing is added under `docs/`)

**Interfaces:**
- Consumes: `main` via the CLI, `evaluate`, `load_label_sets`, `load_run`, `run_from_report`, `add_bundles`.

- [ ] **Step 1: Write the tests.** Append:

```python
# --- Task 8 -----------------------------------------------------------------
SECOND = "b" * 40


def _second_set(tmp_path: Path, role: str = "holdout") -> Path:
    labels = [
        {"key": "s1", "display": "FR-001", "verdict": "correct", "basis": "executed", "labelled_by": "a-person",
         "established_by": "repro/s1.sh", "deserved_confidence": "high", "duplicate_of": None,
         "refuting_fact": None, "preconditions": []},
        {"key": "s2", "display": "FR-002", "verdict": "correct_but_gated", "basis": "read", "labelled_by": "a-person",
         "deserved_confidence": "medium", "duplicate_of": None, "refuting_fact": None,
         "preconditions": [{"setting": "pool_size", "kind": "setting", "literal": {"type": "number", "value": 10},
                            "effective": {"type": "number", "value": 5}}]},
        {"key": "s3", "display": "FR-003", "verdict": "partially_correct", "basis": "reasoned",
         "labelled_by": "claude-sonnet-5-5", "deserved_confidence": "low", "duplicate_of": "s1",
         "refuting_fact": {"ranges": [{"file": "svc/pool.py", "lo": 10, "hi": 12, "kind": "repo"}]},
         "preconditions": []},
        {"key": "s4", "display": "FR-004", "verdict": "wrong", "basis": "executed", "labelled_by": "a-person",
         "established_by": "repro/s4.sh", "deserved_confidence": "low", "duplicate_of": None,
         "refuting_fact": {"ranges": [{"file": "docs/x.rst", "kind": "docs"}]}, "preconditions": []},
    ]
    return _write_set(tmp_path, _set(repo="example/service", commit=SECOND, role=role, labels=labels), "service")


def _second_run(tmp_path: Path) -> Path:
    p = tmp_path / "second-run.json"
    p.write_text(json.dumps(_run({
        "s1": {"verdict": "upheld", "confidence": "high", "duplicate_of": None},
        "s2": {"verdict": "narrowed", "confidence": "high", "duplicate_of": None,
               "preconditions": [{"setting": "pool_size", "default": "5"}]},
        "s3": {"verdict": "upheld", "confidence": "low", "duplicate_of": "s1"},
        "s4": {"verdict": "refuted", "confidence": "medium", "duplicate_of": None},
    }, model="claude-opus-5-5", commit=SECOND)))
    return p


def test_a_second_repository_is_data_only_and_pools_beside_celery(tmp_path):
    _second_set(tmp_path)
    p = _cli("--labels", str(CELERY), "--labels", str(tmp_path / "service"),
             "--run", str(CELERY / "runs" / "spike-refuter.json"), "--run", str(_second_run(tmp_path)))
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "# example/service@bbbbbbb (holdout)" in out
    assert re.search(r"verdict: same\s+2/4 .*example/service@bbbbbbb · n=4 findings · labels: 3 a-person "
                     r"\(2 executed, 1 read\); 1 claude-sonnet-5-5 \(1 reasoned\)", out)
    assert "## pooled verdicts" in out
    assert re.search(r"verdict: same\s+17/25 .*pooled", out)
    assert "  FR-001 (s1)" not in out and "found: FR-003" not in out  # holdout detail hidden without --reveal
    revealed = _cli("--labels", str(CELERY), "--labels", str(tmp_path / "service"),
                    "--run", str(_second_run(tmp_path)), "--reveal")
    assert "  FR-001 (s1): upheld vs correct → same" in revealed.stdout
    assert "  found: FR-003 (s3)" in revealed.stdout
    assert all(ln.endswith("· revealed") for ln in revealed.stdout.splitlines() if re.search(r" \d+/\d+  \(", ln))


def test_runs_on_one_set_are_never_pooled():
    p = _cli("--run", str(CELERY / "runs" / "spike-refuter.json"), "--report", str(CELERY / "scan" / "report.json"))
    assert p.returncode == 0 and "pooled" not in p.stdout


def test_adding_labels_never_changes_an_existing_findings_result(tmp_path):
    base = json.loads((CELERY / "labels.json").read_text())
    run = b.load_run(CELERY / "runs" / "spike-refuter.json")
    run_c = b.run_from_report(CELERY / "scan" / "report.json")
    b.add_bundles(run_c, CELERY / "scan" / "bundles", CELERY / "scan" / "report.json")
    before = b.evaluate([run, run_c], b.load_label_sets([CELERY / "labels.json"]))
    grown = copy.deepcopy(base)
    grown["labels"].append({"key": "ffffffffffff", "display": "FR-099", "verdict": "wrong", "basis": "read",
                            "labelled_by": "a-person", "deserved_confidence": "low", "duplicate_of": None,
                            "refuting_fact": None, "preconditions": []})
    after = b.evaluate([run, run_c], b.load_label_sets([_write_set(tmp_path, grown, "celery")]))
    for r0, r1 in zip(before["runs"], after["runs"]):
        for name, m in r0["measures"].items():
            per_finding = lambda x: {k: v for k, v in x.items() if k in ("rows", "found", "missed", "false")}
            assert json.dumps(per_finding(m), sort_keys=True) == json.dumps(per_finding(r1["measures"][name]), sort_keys=True)


def test_benchmark_imports_only_the_standard_library():
    tree = ast.parse((ROOT / "scripts" / "benchmark.py").read_text())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert names <= set(sys.stdlib_module_names) | {"__future__"}, names - set(sys.stdlib_module_names)


def test_labels_never_reach_the_pipeline():
    hits = []
    for d in ("agents", "skills", "catalog", "scripts", "hooks", "templates"):
        for p in (ROOT / d).rglob("*"):
            if p.is_file() and p.name != "benchmark.py" and p.suffix in (".py", ".md", ".yaml", ".json", ".html"):
                if "calibration/correctness" in p.read_text(errors="ignore"):
                    hits.append(str(p.relative_to(ROOT)))
    assert hits == []
```

- [ ] **Step 2: Run them**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark.py -q -k "second or pooled or adding_labels or standard_library or never_reach"`
Expected: PASS. These pin behaviour Tasks 1–7 already built; if any fails, the defect is in the scorer, and the fix goes there, not in the test. Check the second set's figures by hand against the run: same = s1 and s4 (2/4), pooled with Celery 17/25.

- [ ] **Step 3: Commit**

```bash
git add tests/test_benchmark.py
git commit -m "Benchmark: a second repository is data only; stability and isolation (#55)"
```

### Task 9: Documentation and release note

**Satisfies:** AC-9 (the labelling procedure), AC-11.

**Files:**
- Create: `docs/calibration/correctness/labelling.md`
- Modify: `CLAUDE.md` (Commands; a new subsection under "Things that will bite you")
- Modify: `docs/calibration/correctness.md` (one line under Files)
- Modify: `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml` (version)

- [ ] **Step 1: Write `docs/calibration/correctness/labelling.md`:**

````markdown
# Labelling findings for the correctness benchmark

The benchmark (`scripts/benchmark.py`, #55) scores runs against labelled
ground truth. This page says how a label is made, how a repository is added,
and what the figures cannot show. The design is in
`docs/superpowers/specs/2026-10-03-correctness-benchmark-design.md`.

## A label set

One directory per repository and commit under `docs/calibration/correctness/`:

| Path | What it is |
|---|---|
| `labels.json` | The ground truth, `thunderstruck.labels/v1` (spec §2.1) |
| `scan/` | The scan whose findings are labelled: `report.json`, `hotspots.json`, `bundles/`, `findings/` |
| `runs/` | Optional: checked-in runs to score, `thunderstruck.benchmark-run/v1` (spec §3.1) |

Anything else in the directory is evidence for a reader (reproduction notes,
spikes). The scorer reads only `labels.json` and the files it is given.

## Making labels

1. **Scan at a pinned commit.** Run `/thunderstruck-scan` with the release
   under test on a clean checkout of the commit. Copy `report.json`,
   `hotspots.json`, `bundles/` and `findings/` into `<set>/scan/`, replacing
   local absolute paths with placeholders (`<repo>`, `<site-packages>`).
2. **Establish each verdict**, preferring, in order:
   - `executed`: a reproduction you ran. Name it in `established_by`;
   - `read`: the code, docs, full commit messages and dependency source settle it;
   - `reasoned`: neither was possible; say why in your notes.
3. **Record the verdict class.** `correct`, `correct_but_gated` (true, but
   only behind a non-default setting; it counts as correct), `partially_correct`
   or `wrong`.
4. **Record what the scorer needs:** the deserved confidence; `duplicate_of`
   (a key) for a finding that is another finding's defect seen from elsewhere;
   the refuting fact as line ranges, each typed `repo`, `dependency`, `docs`
   or `history`; and each precondition the finding depends on, with its
   literal default (what the code or docs state) and its effective default
   (what holds at runtime). A precondition about the deployment rather than a
   setting is `kind: environment`. A measured consequence is not a default:
   record the setting's value, not how long it took.
5. **Name who labelled it** in `labelled_by`: a model id or a person's handle.
   A model may label. It must not label findings for a set that will score a
   run of the same model; the scorer excludes such findings and says so.
6. **Validate:** `uv run scripts/benchmark.py --labels <set> --report <set>/scan/report.json`.
   A set with any invalid label is rejected whole and nothing is scored.

Thunderstruck never executes the project it scans. That rule binds the plugin
and its pipeline. A labeller works outside both and may execute the project in
their own sandbox, as the Celery review did.

## Adding a repository

Add a directory in the form above. The scorer needs no change; a set's figures
are printed separately, with a pooled line only below them. A set no change was
tuned on can be marked `"role": "holdout"`: its per-finding rows then appear
only with `--reveal`, and every figure line says `revealed`.

## Changing a label

Adding labels never changes another finding's result. Changing an existing
label is a relabel: the diff shows it, and the baseline tests in
`tests/test_benchmark.py` fail until they are updated in the same PR, with the
reason.

## What the figures cannot show

- **Recall.** A defect the scan missed has no key, so nothing matches it
  mechanically. Missed defects stay in the evidence and are not scored.
- **An investigator change, without new labels.** A re-scan's reworded
  findings get new keys and are unlabelled until someone labels them.
- **Anything beyond the labelled repositories.** A figure is evidence about
  the sets it names: repository, commit, n and who labelled them.
- **An effect inside the interval.** At n=21, one relabel moves a rate by
  about 5 points; a change smaller than the printed Wilson interval is not
  shown to be a change.

The figures are measures, not targets. Tuning a stage against one set's
findings until its score looks good fits that set.
````

- [ ] **Step 2: Add to CLAUDE.md's Commands block**, after the `calibrate.py` lines:

```bash
# The correctness benchmark (#55): score a run or a scan against labelled ground truth. No model, no network.
uv run scripts/benchmark.py --run docs/calibration/correctness/celery/runs/spike-refuter.json
uv run scripts/benchmark.py --report <scan>/report.json --bundles <scan>/bundles   # confidences and bundles
```

- [ ] **Step 3: Add this subsection to CLAUDE.md** at the end of "Things that will bite you":

```markdown
**The correctness benchmark measures; it never feeds.** `scripts/benchmark.py`
scores runs against `docs/calibration/correctness/<set>/labels.json` by `key`.
No label, refuting fact or verdict may reach a prompt, a bundle, the catalog or
a sample (`test_labels_never_reach_the_pipeline`). Every figure prints the
repository, commit, n and labeller mix; state them in a PR. What it cannot
show: recall (missed defects have no key); an investigator change without new
labels (reworded findings get new keys); anything beyond the labelled
repositories; an effect smaller than the printed interval. Do not tune a stage
against the Celery findings until the score looks good — that fits Celery.
Adding a set is data only (`labelling.md`); changing a label fails the
baseline tests on purpose.
```

- [ ] **Step 4: In `docs/calibration/correctness.md`**, add to the Files table:

```markdown
| `celery/labels.json`, `celery/runs/` | The same ground truth normalised for `scripts/benchmark.py`, and the two baseline inputs; see [`correctness/labelling.md`](correctness/labelling.md) |
```

- [ ] **Step 5: Version and CHANGELOG.** Bump the patch version in all four places (the next patch above `main`'s at the time; `0.9.1` if `main` is still `0.9.0`) and add an entry in the 0.8.2 entry's form:

```markdown
## 0.9.1

A correctness benchmark scored against executed ground truth (#55).

### Added

- **`scripts/benchmark.py`.** Scores a refutation run, a confidence assignment, a scan's bundles and stated defaults against labelled ground truth, by finding `key`, with no model call and no network. Every figure prints the repository, commit, n, a Wilson 95% interval and who labelled the findings.
- **The Celery label set** (`docs/calibration/correctness/celery/labels.json`): the 21 findings of the executed review, with the baselines for today's pipeline (8 of 21 confidences exact, 4 of 9 in-file refuting facts shown) and for the spike's read-only refuters (15 of 21 same verdict class).
- **`docs/calibration/correctness/labelling.md`**: how to label new findings and add a repository.
```

- [ ] **Step 6: Run the full suite and the generated-file checks**

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
uv run scripts/gen_catalog_docs.py --check; echo "exit=$?"
uv run scripts/gen_sample_report.py --check; echo "exit=$?"
```

Expected: all three `exit=0`; `test_versions_agree` and `test_docs_in_sync` pass.

- [ ] **Step 7: Commit**

```bash
git add docs/calibration/correctness/labelling.md docs/calibration/correctness.md CLAUDE.md CHANGELOG.md .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml
git commit -m "Benchmark: labelling procedure, docs and release note (#55)"
```

## Acceptance criteria coverage

| AC | Tasks |
|---|---|
| AC-1 | 7 (the command), 8 (stdlib only, in the CI suite) |
| AC-2 | 4 |
| AC-3 | 3 |
| AC-4 | 5 |
| AC-5 | 6 |
| AC-6 | 1 (figure lines), 7 (every line of the command's output) |
| AC-7 | 3 (match on key, unlabelled), 7 (unlabelled in the output) |
| AC-8 | 2 (labels), 3, 4, 5 (each baseline), 7 (all three from one command) |
| AC-9 | 1 (rejection), 2 (basis on every label), 8 (stability), 9 (procedure) |
| AC-10 | 8 |
| AC-11 | 9 |
