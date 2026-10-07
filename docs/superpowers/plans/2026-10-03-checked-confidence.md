# Checked Confidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A finding's reported confidence says whether its claim was checked, never whether its area has fix history; every output shows the check status, the settings the failure needs and the cited history as separate facts.

**Architecture:** The investigator states a confidence claim, `preconditions` and a `role` per cited commit. `validate.py` checks them, writes `check` (`unchecked`) and a `history` signal. `report.py` derives the reported confidence with `_common.effective_confidence(claim, status)` and orders by `_common.finding_gate`, then renders `report.md`, `report.json` (v2) and `index.json`; the HTML report and the guardrail render what those carry.

**Tech Stack:** Python 3.11+ (stdlib, pyyaml where the scripts already use it), `uv`, pytest, the existing vanilla-JS HTML template.

**Spec:** `docs/superpowers/specs/2026-10-03-checked-confidence-design.md` (§n below refers to it). Requirements AC-1…AC-10 and the product decisions are in GitHub issue #56, part of #54.

**Branch:** `feat/checked-confidence`. One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

New tests go in one file, `tests/test_checked_confidence.py`, appended task by task under a `# --- Task N` comment. Run one task's tests with `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py -q -k "<name>"`.

## Global Constraints

- One confidence rule (`_common.effective_confidence`) and one gate rule (`_common.finding_gate`). Nothing else computes either; `guardrail.py` carries a copy of the ceiling table only because it may not import `_common`, and a test pins the copy (§1).
- Whether a commit is a fix never affects confidence or order anywhere (AC-1). `classify_commit` feeds `history[].class` only.
- The findings file keeps the investigator's `confidence` claim; it is never rewritten with the reported confidence (§4.3).
- `validate.py` never changes an existing `check` (§3.2). `finding_shape.shape()`, which `save_finding.py` and the capture hook both call, strips `check`, `history` and `confidence_claimed` from model output (§3.4).
- Every model-written value (setting, default, value, role, `check.reason`) is inert: `md.code`/`md.text` in `report.md`, `textContent` in the HTML, plain text in the guardrail. Only the tool builds links.
- `guardrail.py` stays stdlib-only, always exits 0, states facts and never instructs, and stays under 100 ms median.
- Field names, values and their spelling are exactly the spec's: `check.status` ∈ `unchecked upheld narrowed inconclusive refuted`; `preconditions[]` keys `setting default default_ref needs value documented doc_ref`; `needs` ∈ `changed default`; `documented` ∈ `yes no not_checked`; commit `role` ∈ `introduced fixed mitigated changed`; `gate` ∈ `none non_default_setting`. #37 and #57 build on these names.
- `VALIDATION_RULES` becomes 4, `FINDING_SCHEMA_VERSION` `thunderstruck.finding/v2`, `REPORT_SCHEMA_VERSION` `thunderstruck.report/v2`. `index.json` stays `thunderstruck.index/v1`.
- Bundles stay byte-identical across runs; nothing in this plan writes into a bundle body.
- This plan builds on #5 and #55 as merged (Task 0). Result shaping lives in `scripts/finding_shape.py` (#5): `FINDING_SCHEMA_VERSION` and the validator-owned keys are defined there, and `_common` only re-exports the version; `save_finding.py` and the `SubagentStop` hook `scripts/capture_finding.py` both call `finding_shape.shape()`.
- A missing prerequisite stops the run: replace `agent:in-progress` with `agent:blocked`, comment naming the task and the missing ticket, open no PR. Never skip a task and continue.
- The examples are regenerated once, in Task 8. Between Task 2 and Task 8, `uv run scripts/gen_sample_report.py --check` reports them stale; that is expected and Task 8 ends it. The generator itself must keep producing valid findings from Task 2 on, because `test_the_sample_does_not_carry_todays_date` runs it.
- Public repository: no organisation-specific names, hosts or credentials in any file.

## Review Focus

1. **An `index.json` written by 0.9.x** (a `high` entry with no `check_status`, no `preconditions`). The guardrail states it as `medium` and `unchecked` and invents no precondition line. Pinned in Task 6.
2. **A precondition whose `default_ref` names an untracked file or a line past the end** (`.env.example:3`, `src/a.ts:99`). Rejected with the same message a `code` ref gets, addressed `preconditions[j].default_ref`. Pinned in Task 2.
3. **A finding whose preconditions all have `needs: default`.** It is a default-path finding: sorted with them and not marked. Pinned in Task 3.
4. **A model that echoes `"check": {"status": "upheld"}`, `history` or `confidence_claimed` in its JSON.** Saved without them, reported `unchecked` and at most `medium`. Pinned in Task 2 (save) and Task 3 (report).
5. **`documented: "yes"` without a `doc_ref`, or a `doc_ref` with `documented: "no"`.** Both rejected. Pinned in Task 2.

---

### Task 0: Prerequisites are merged

**Satisfies:** none directly; every later task assumes it.

- [x] **Step 1: Check #5 and #55 are on `main`.**

```bash
git fetch -q origin
for f in scripts/finding_shape.py scripts/capture_finding.py scripts/benchmark.py \
         docs/calibration/correctness/celery/labels.json; do
  git cat-file -e "origin/main:$f" 2>/dev/null && echo "ok      $f" || echo "MISSING $f"
done
git show origin/main:hooks/hooks.json | grep -q SubagentStop && echo "ok      SubagentStop hook" || echo "MISSING SubagentStop hook"
git show origin/main:scripts/finding_shape.py | grep -q "def shape" && echo "ok      finding_shape.shape" || echo "MISSING finding_shape.shape"
```

Expected: every line `ok`.

- [x] **Step 2: Stop if anything is missing.** Any `MISSING` line ends the run before Task 1: replace `agent:in-progress` with `agent:blocked` on #56, comment "Blocked at Task 0: <the missing files>. #5 (finding_shape.py, capture_finding.py, the SubagentStop hook) / #55 (benchmark.py, labels.json) is not merged", open no PR. Do not build Tasks 1–8 without #55: a branch that cannot finish Task 9 cannot merge.

No commit: this task changes nothing.

### Task 1: The shared vocabulary and the two rules

**Satisfies:** AC-1 (confidence no longer reads history), AC-2 (the ceilings, `narrowed` drops a level).

**Files:**
- Modify: `scripts/_common.py` (new section after `classify_commit`)
- Create: `tests/test_checked_confidence.py`

**Interfaces:**
- Produces, in `_common`: `CONFIDENCE_LEVELS: tuple[str, ...]`, `CHECK_STATUSES`, `CONFIDENCE_CEILING: dict[str, str]`, `CHECK_SENTENCES: dict[str, str]`, `COMMIT_ROLES`, `PRECONDITION_NEEDS`, `DOCUMENTED`, `GATES`, `GATE_MARKERS: dict[str, str]`; `check_status(finding: dict) -> str`; `effective_confidence(claimed, status: str) -> str`; `finding_gate(finding: dict) -> str`.

- [x] **Step 1: Write the failing tests.** Create `tests/test_checked_confidence.py`:

```python
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
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py -q`
Expected: FAIL, `AttributeError: module '_common' has no attribute 'effective_confidence'` (and the like).

- [x] **Step 3: Write the implementation.** In `scripts/_common.py`, directly after `classify_commit`, add:

```python
# --------------------------------------------------------------------------
# check status, confidence and gate (spec 2026-10-03-checked-confidence-design.md)
# --------------------------------------------------------------------------

CONFIDENCE_LEVELS = ("low", "medium", "high")
# #37 writes these into a finding's check.status; a sixth needs the spec changed first.
CHECK_STATUSES = ("unchecked", "upheld", "narrowed", "inconclusive", "refuted")
CONFIDENCE_CEILING = {"upheld": "high", "unchecked": "medium", "narrowed": "medium",
                      "inconclusive": "medium", "refuted": "low"}
CHECK_SENTENCES = {
    "unchecked": "No one has tried to refute this claim",
    "upheld": "A check tried to refute this claim and it held",
    "narrowed": "A check found that only part of this claim holds",
    "inconclusive": "A check could not settle this claim",
    "refuted": "A check refuted this claim",
}
COMMIT_ROLES = ("introduced", "fixed", "mitigated", "changed")
PRECONDITION_NEEDS = ("changed", "default")
DOCUMENTED = ("yes", "no", "not_checked")
# Report order: default-path findings first. #57 inserts "unconfirmed_default" (its spec).
GATES = ("none", "non_default_setting")
GATE_MARKERS = {"non_default_setting": "needs a non-default setting"}


def check_status(finding: dict) -> str:
    """The finding's check status; anything missing or unrecognised is unchecked."""
    check = finding.get("check") if isinstance(finding, dict) else None
    status = check.get("status") if isinstance(check, dict) else None
    return status if status in CHECK_STATUSES else "unchecked"


def effective_confidence(claimed, status: str) -> str:
    """The reported confidence: the investigator's claim, one level lower when
    narrowed, never above the check status's ceiling. History plays no part."""
    level = CONFIDENCE_LEVELS.index(claimed) if claimed in CONFIDENCE_LEVELS else 0
    status = status if status in CHECK_STATUSES else "unchecked"
    if status == "narrowed":
        level = max(0, level - 1)
    ceiling = CONFIDENCE_LEVELS.index(CONFIDENCE_CEILING[status])
    return CONFIDENCE_LEVELS[min(level, ceiling)]


def finding_gate(finding: dict) -> str:
    """non_default_setting when any precondition needs a setting changed.
    The one gate rule: #37 extends it to read the check, #57 adds a gate (spec §7)."""
    pre = finding.get("preconditions") if isinstance(finding, dict) else None
    items = pre if isinstance(pre, list) else []
    if any(isinstance(p, dict) and p.get("needs") == "changed" for p in items):
        return "non_default_setting"
    return "none"
```

- [x] **Step 4: Run the tests to verify they pass** (same command as Step 2). Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add scripts/_common.py tests/test_checked_confidence.py
git commit -m "Checked confidence: the confidence ceiling and the gate (#56)"
```

### Task 2: The validator's new contract

**Satisfies:** AC-1 (the fix gate is gone), AC-3 (`role`, the `introduced` rule, `history`), AC-4 (preconditions resolve), AC-6 (`amplifier`/`sustaining_effect` optional), AC-8 (rules version 4).

**Files:**
- Modify: `scripts/validate.py` (`REQUIRED_FIELDS`, `check_evidence`, `check_finding`, `_corroborates` removed, new `check_ref`, `check_preconditions`, `_written`, `_wrote`, `history`; `main`)
- Modify: `scripts/_common.py` (`VALIDATION_RULES = 4`)
- Modify: `scripts/finding_shape.py` (`FINDING_SCHEMA_VERSION = "thunderstruck.finding/v2"`; `OWNED_FINDING_KEYS`, used by `shape()`)
- Modify: `scripts/gen_sample_report.py` (`_corroborating_commit` returns a role; every canned finding gets `preconditions`)
- Modify (test data and two old-contract tests, Step 1): `tests/test_pipeline.py`, `tests/test_validate_paths.py`, `tests/test_context_pipeline.py`, `tests/test_dormant.py`, `tests/test_cross_file.py`
- Delete: `tests/test_high_gate.py` (its blame tests move here in the new form)
- Test: `tests/test_checked_confidence.py`

**Interfaces:**
- Consumes: `c.COMMIT_ROLES`, `c.PRECONDITION_NEEDS`, `c.DOCUMENTED`, `c.CHECK_STATUSES` (Task 1).
- Produces: in `validate`: `PRECONDITION_KEYS: frozenset[str]`; `Validator.check_ref(ref, where: str, errors: list[str]) -> tuple[str, int, int] | None`; `Validator.check_preconditions(pre, where: str, errors: list[str]) -> None`; `Validator.history(finding: dict) -> list[dict]` (entries `{sha, class, role, wrote_cited_line}`). Findings files that pass carry `check` and `history`.

- [x] **Step 1: Update the test data to the new contract.** Two mechanical rules, applied to every finding a test builds by hand:
  1. every finding dict gains `"preconditions": []` (place it after `"evidence"`);
  2. every `{"type": "commit", …}` evidence item gains `"role": "changed"`, except where Step 2's tests set another role.

  In `tests/test_pipeline.py::_valid_finding` the commit item becomes `{"type": "commit", "ref": sha, "role": "changed", "note": "recent change"}` and the finding gains `"preconditions": []`; in `tests/test_validate_paths.py::_doc` the finding gains `"preconditions": []`. Find the rest with:

  ```bash
  grep -n '"how_to_verify"' tests/*.py
  grep -n '"type": "commit"' tests/*.py
  ```

  The hits to update are exactly: `tests/test_pipeline.py` (`_valid_finding`, and the commit items of the `0000000000000000` parametrize row and of `test_commit_evidence_must_touch_the_finding_file`'s `foreign` item), `tests/test_validate_paths.py` (`_doc`, and the `only_i` commit item), `tests/test_context_pipeline.py` (the finding builder near line 122), `tests/test_dormant.py` (the D01 finding near line 182) and `tests/test_cross_file.py` (`"role": "fixed"` on its fix commit).

  **Not** test data; leave them as they are: the commit items in `tests/test_investigator_contract.py` (lines 62–72 are `normalise()` inputs and its expected outputs, line 144 an error-message case); `tests/test_shared_code.py` (never validated); the `"how_to_verify"` hits in `test_inert_report.py`, `test_report_html.py` and `test_report_html_browser.py` (field-name lists). `_malformed` derives from `_valid_finding`, so its commit item carries `role` through `normalise()` unchanged.

  Two existing tests encode the old contract:
  - `tests/test_pipeline.py::test_broken_evidence_is_rejected`: its row `(lambda f: f.pop("sustaining_effect"), "sustaining_effect is missing")` becomes `(lambda f: f.pop("preconditions"), "preconditions is missing (it may be [], but the key must be present)")`.
  - `tests/test_pipeline.py::test_high_confidence_requires_commit_evidence`: delete it (`high` no longer needs a commit).

  Then delete `tests/test_high_gate.py`. (Checked: with Tasks 1–2 applied to today's `main`, these are the only changes the existing suite needs.)

- [x] **Step 2: Write the failing tests.** Append to `tests/test_checked_confidence.py`:

```python
# --- Task 2 -----------------------------------------------------------------
import bundle  # noqa: E402
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding  # noqa: E402
from test_validate_paths import _doc, _git, _validator, repo  # noqa: E402,F401

FORMAT = "src/util/format.ts"
RELEASES = "src/client/releases.ts"
_DROP = object()


def _pre(**over) -> dict:
    p = {"setting": "RETRY_ON_429", "default": "false", "default_ref": "src/a.ts:1",
         "needs": "changed", "value": "true", "documented": "no", "doc_ref": None}
    p.update(over)
    return {k: v for k, v in p.items() if v is not _DROP}


def _errors(repo, *items) -> list[str]:
    doc = _doc("src/a.ts")
    doc["findings"][0]["preconditions"] = list(items)
    return _validator(repo).check_document(doc)


def test_complete_preconditions_pass(repo):
    assert _errors(repo) == []
    assert _errors(repo, _pre()) == []
    assert _errors(repo, _pre(needs="default", value=_DROP, documented="yes",
                              doc_ref="src/a.ts:2-3")) == []


@pytest.mark.parametrize("over, fragment", [
    ({"setting": ""}, "preconditions[0].setting must be a non-empty string"),
    ({"default": None}, "preconditions[0].default must be a non-empty string"),
    ({"default_ref": "src/a.ts:99"}, "that line does not exist"),
    ({"default_ref": "src/new.ts:1"}, "not tracked by git"),
    ({"default_ref": "/etc/hostname:1"}, "is absolute"),
    ({"default_ref": "src/a.ts"}, "is not path:line"),
    ({"default_ref": _DROP}, "preconditions[0].default_ref must be one string"),
    ({"needs": "maybe"}, "needs 'maybe' is not one of"),
    ({"value": None}, "value must name the value the failure needs"),
    ({"needs": "default"}, "value must be absent or null"),
    ({"documented": True}, "documented True is not one of"),
    ({"documented": "yes"}, "preconditions[0].doc_ref must be one string"),
    ({"documented": "no", "doc_ref": "src/a.ts:2"}, 'doc_ref is only given when documented is "yes"'),
    ({"confirmation": {"state": "confirmed"}}, "unknown key(s) ['confirmation']"),
])
def test_each_precondition_rule(repo, over, fragment):
    errors = _errors(repo, _pre(**over))
    assert any(fragment in e for e in errors), errors


def test_a_setting_is_listed_once(repo):
    errors = _errors(repo, _pre(), _pre(setting=" retry_on_429 "))
    assert any("listed twice" in e for e in errors), errors


def test_preconditions_must_be_present_and_a_list(repo):
    doc = _doc("src/a.ts")
    del doc["findings"][0]["preconditions"]
    assert "findings[0].preconditions is missing (it may be [], but the key must be present)" \
        in _validator(repo).check_document(doc)
    doc["findings"][0]["preconditions"] = {"setting": "x"}
    assert any("preconditions must be a list" in e for e in _validator(repo).check_document(doc))


def test_amplifier_and_sustaining_effect_are_optional_but_never_filler(repo):
    doc = _doc("src/a.ts")
    f = doc["findings"][0]
    del f["amplifier"], f["sustaining_effect"]
    assert _validator(repo).check_document(doc) == []
    f["amplifier"] = "  "
    assert any("amplifier must be a non-empty string when present; leave it out" in e
               for e in _validator(repo).check_document(doc))


def _with_commit(repo, role=_DROP, etype="commit") -> list[str]:
    doc = _doc("src/a.ts")
    sha = _git(repo, "rev-parse", "HEAD").strip()[:7]
    item = {"type": etype, "ref": sha if etype == "commit" else "src/a.ts:1", "note": "n"}
    if role is not _DROP:
        item["role"] = role
    doc["findings"][0]["evidence"].append(item)
    return _validator(repo).check_document(doc)


def test_commit_evidence_needs_a_role(repo):
    assert any("role None is not one of" in e for e in _with_commit(repo))
    assert any("role 'blamed' is not one of" in e for e in _with_commit(repo, "blamed"))
    assert _with_commit(repo, "introduced") == []          # init wrote src/a.ts:1
    assert any("role is only given on commit evidence" in e
               for e in _with_commit(repo, "changed", etype="code"))


@pytest.mark.parametrize("check, ok", [
    ({"status": "upheld", "by": "skeptic", "reason": "held", "holds": "all"}, True),
    ({"status": "probably"}, False),
    ("upheld", False),
    ({"status": "unchecked", "reason": 3}, False),
])
def test_an_existing_check_is_validated(repo, check, ok):
    doc = _doc("src/a.ts")
    doc["findings"][0]["check"] = check
    assert (_validator(repo).check_document(doc) == []) is ok


def _sha(repo: Path, rel: str, subject: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "log", "--format=%H %s", "--", rel],
                         capture_output=True, text=True, check=True).stdout
    return next(line.split(" ", 1)[0] for line in out.splitlines()
                if line.split(" ", 1)[1] == subject)


def _fixture_doc(repo: Path, *, file: str, line: int, commits: list[tuple[str, str]],
                 patterns=("S02",), confidence="high"):
    hid, doc = _valid_finding(repo, _hotspots(repo))
    f = doc["findings"][0]
    f["location"] = {"file": file, "symbol": "f", "lines": str(line)}
    f["missing_patterns"] = list(patterns)
    f["confidence"] = confidence
    f["evidence"] = [{"type": "code", "ref": f"{file}:{line}", "note": "the text"}] + [
        {"type": "commit", "ref": sha[:7], "role": role, "note": "history"} for sha, role in commits]
    return hid, doc


def _check(repo, plugin_root, hid, doc):
    _write_finding(repo, hid, doc)
    return _validate(repo, plugin_root)


def test_high_with_only_a_feature_commit_now_passes(scanned_copy, plugin_root):
    sha = _sha(scanned_copy, RELEASES, "feat: add release client")
    hid, doc = _fixture_doc(scanned_copy, file=RELEASES, line=1, commits=[(sha, "changed")])
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 0


def test_introduced_needs_the_commit_that_wrote_the_lines(scanned_copy, plugin_root):
    wrote = _sha(scanned_copy, FORMAT, "feat: add title formatting")
    tidy = _sha(scanned_copy, FORMAT, "refactor: tidy imports")      # touched the file, not line 4
    hid, doc = _fixture_doc(scanned_copy, file=FORMAT, line=4, commits=[(wrote, "introduced")])
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 0
    hid, doc = _fixture_doc(scanned_copy, file=FORMAT, line=4, commits=[(tidy, "introduced")])
    proc = _check(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "cited as having introduced the cited code, but it wrote none of the cited lines" in proc.stdout


def test_an_uncommitted_line_is_introduced_by_no_commit(scanned_copy, plugin_root):
    wrote = _sha(scanned_copy, FORMAT, "feat: add title formatting")
    path = scanned_copy / FORMAT
    lines = path.read_text().split("\n")
    lines[3] = " * edited locally"
    path.write_text("\n".join(lines))
    hid, doc = _fixture_doc(scanned_copy, file=FORMAT, line=4, commits=[(wrote, "introduced")])
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 1


def test_validation_writes_check_and_history(scanned_copy, plugin_root):
    feat = _sha(scanned_copy, RELEASES, "feat: add release client")
    fix = _sha(scanned_copy, RELEASES, "fix: timeout again on large releases")
    hid, doc = _fixture_doc(scanned_copy, file=RELEASES, line=1,
                            commits=[(fix, "fixed"), (feat, "introduced"), (fix, "fixed")])
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 0
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    f = saved["findings"][0]
    assert saved["validated_with"] == c.VALIDATION_RULES == 4
    assert f["check"] == {"status": "unchecked", "by": None, "reason": None}
    assert f["confidence"] == "high"                      # the claim is kept as written
    assert f["history"] == [
        {"sha": fix[:7], "class": "fix", "role": "fixed", "wrote_cited_line": False},
        {"sha": feat[:7], "class": "feature", "role": "introduced", "wrote_cited_line": True},
    ]


def test_validation_keeps_an_existing_check(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    doc["findings"][0]["check"] = {"status": "upheld", "by": "skeptic", "reason": "held"}
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 0
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert saved["findings"][0]["check"]["status"] == "upheld"


def test_save_finding_strips_what_a_model_must_not_set(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    f = doc["findings"][0]
    f["check"] = {"status": "upheld"}
    f["history"] = [{"sha": "x", "class": "fix"}]
    f["confidence_claimed"] = "high"
    src = scanned_copy / "out.json"
    src.write_text(json.dumps(doc))
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "save_finding.py"),
                    "--repo", str(scanned_copy), "--id", hid, "--from", str(src)],
                   check=True, capture_output=True)
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert not {"check", "history", "confidence_claimed"} & set(saved["findings"][0])
    assert _validate(scanned_copy, plugin_root).returncode == 0
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert saved["findings"][0]["check"]["status"] == "unchecked"


def test_the_capture_hook_strips_what_a_model_must_not_set(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    doc["findings"][0].update(check={"status": "upheld"}, history=[{"sha": "x"}],
                              confidence_claimed="high")
    payload = {"session_id": "s", "transcript_path": "/dev/null", "cwd": str(scanned_copy),
               "hook_event_name": "SubagentStop", "agent_id": "a1",
               "agent_type": "plugin:thunderstruck:thunderstruck-investigator",
               "stop_reason": "completed", "last_assistant_message": json.dumps(doc)}
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / "capture_finding.py")],
                          input=json.dumps(payload), capture_output=True, text=True)
    assert proc.returncode == 0
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert not {"check", "history", "confidence_claimed"} & set(saved["findings"][0])
    assert saved["schema"] == "thunderstruck.finding/v2"


def test_findings_validated_under_rules_3_are_investigated_again(scanned_copy, plugin_root):
    old = {"findings": [{"key": "k", "confidence": "high"}], "validated_with": 3}
    assert bundle._validated_under_older_rules(old)
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    for f in doc["findings"]:
        del f["preconditions"]                               # written by 0.9.x
    from validate import Validator
    v = Validator(scanned_copy, _hotspots(scanned_copy), c.load_catalog())
    assert not bundle._still_valid(v, doc)
```

- [x] **Step 3: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py -q`
Expected: FAIL on the Task 2 tests (e.g. `preconditions is missing` not reported, `VALIDATION_RULES == 3`).

- [x] **Step 4: Write the implementation.**

In `scripts/_common.py`: `VALIDATION_RULES = 4`. In `scripts/finding_shape.py`: `FINDING_SCHEMA_VERSION = "thunderstruck.finding/v2"` (`_common` re-exports it unchanged).

In `scripts/validate.py`, replace `REQUIRED_FIELDS` and add the precondition constants:

```python
REQUIRED_FIELDS = [
    "location", "missing_patterns", "failure_mode", "trigger_condition",
    "blast_radius", "evidence", "preconditions",
    "confidence", "confidence_rationale", "how_to_verify",
]
# Present or absent; never an empty string (#56 AC-6)
OPTIONAL_TEXT = ("amplifier", "sustaining_effect")
# The keys an investigator may write. #57 adds "confirmation", written after validation.
PRECONDITION_KEYS = frozenset({"setting", "default", "default_ref", "needs", "value",
                               "documented", "doc_ref"})
PRECONDITION_FORM = ('{"setting": "API_RETRY_ON_429", "default": "false", '
                     '"default_ref": "src/client/api.ts:1", "needs": "changed", "value": "true", '
                     '"documented": "no", "doc_ref": null}')
```

Update the module docstring's list of refs with one line: `  precondition  default_ref / doc_ref — path:line, resolved like a code ref`.

In `check_evidence`, directly after `ref = ref.strip()`:

```python
        role = ev.get("role")
        if etype == "commit" and role not in c.COMMIT_ROLES:
            errors.append(f"{where}.role {role!r} is not one of {list(c.COMMIT_ROLES)}: what this "
                          f"commit did to the cited code (introduced = wrote it; fixed = an "
                          f"earlier fix attempt; mitigated = added a guard or option; changed = "
                          f"anything else)")
        elif etype != "commit" and "role" in ev:
            errors.append(f"{where}.role is only given on commit evidence")
```

Add these methods to `Validator`:

```python
    def check_ref(self, ref: Any, where: str, errors: list[str]) -> tuple[str, int, int] | None:
        """A path:line or path:start-end that must resolve exactly as a `code`
        evidence ref does. The one place a precondition ref is resolved (spec §7)."""
        if not isinstance(ref, str) or not ref.strip():
            errors.append(f"{where} must be one string, {REF_FORMS['code']}; got {shown(ref)}")
            return None
        ref = ref.strip()
        m = CODE_REF.match(ref)
        if not m:
            errors.append(f"{where} {ref!r} is not path:line or path:start-end, e.g. "
                          f"{REF_FORMS['code']}")
            return None
        rel, total, problem = self._resolve(m["path"])
        if problem:
            errors.append(f"{where} {ref!r} — {m['path']!r} {problem}")
            return None
        span = (int(m["start"]), int(m["end"] or m["start"]))
        if not range_fits(span, total):
            errors.append(f"{where} {ref!r} — {range_error(rel, total)}")
            return None
        return rel, *span

    def check_preconditions(self, pre: Any, where: str, errors: list[str]) -> None:
        if not isinstance(pre, list):
            errors.append(f"{where} must be a list ([] when the failure happens on default "
                          f"settings); got {shown(pre)}")
            return
        seen: set[str] = set()
        for j, p in enumerate(pre):
            pw = f"{where}[{j}]"
            if not isinstance(p, dict):
                errors.append(f"{pw} is not an object: got {shown(p)}. Use {PRECONDITION_FORM}")
                continue
            unknown = sorted(set(p) - PRECONDITION_KEYS)
            if unknown:
                errors.append(f"{pw} has unknown key(s) {unknown}; the keys are "
                              f"{sorted(PRECONDITION_KEYS)}")
            for key in ("setting", "default"):
                if not isinstance(p.get(key), str) or not p[key].strip():
                    errors.append(f"{pw}.{key} must be a non-empty string; got {shown(p.get(key))}")
            name = p.get("setting")
            if isinstance(name, str) and name.strip():
                norm = "".join(name.split()).casefold()
                if norm in seen:
                    errors.append(f"{pw}.setting {name!r} is listed twice; one item per setting")
                seen.add(norm)
            self.check_ref(p.get("default_ref"), f"{pw}.default_ref", errors)
            needs, value = p.get("needs"), p.get("value")
            if needs not in c.PRECONDITION_NEEDS:
                errors.append(f'{pw}.needs {needs!r} is not one of {list(c.PRECONDITION_NEEDS)}: '
                              f'"changed" when the failure needs the setting changed from its '
                              f'default, "default" when it happens on the default')
            elif needs == "changed" and (not isinstance(value, str) or not value.strip()):
                errors.append(f'{pw}.value must name the value the failure needs when needs is '
                              f'"changed"; got {shown(value)}')
            elif needs == "default" and value is not None:
                errors.append(f'{pw}.value must be absent or null when needs is "default"; the '
                              f'default is the value')
            documented = p.get("documented")
            if documented not in c.DOCUMENTED:
                errors.append(f"{pw}.documented {documented!r} is not one of {list(c.DOCUMENTED)}")
            elif documented == "yes":
                self.check_ref(p.get("doc_ref"), f"{pw}.doc_ref", errors)
            elif p.get("doc_ref") is not None:
                errors.append(f'{pw}.doc_ref is only given when documented is "yes"')

    def _written(self, evidence: list) -> set[str]:
        """Full SHAs that wrote any line of any cited code range (git blame)."""
        out: set[str] = set()
        for ev in evidence:
            if not isinstance(ev, dict) or ev.get("type") != "code":
                continue
            m = CODE_REF.match(str(ev.get("ref") or "").strip())
            if not m:
                continue
            rel, total, err = self._resolve(m.group("path"))
            start, end = int(m["start"]), int(m["end"] or m["start"])
            if err or not range_fits((start, end), total or 0):
                continue
            out |= self._introduced(rel, start, end)
        return out

    @staticmethod
    def _wrote(sha: str, written: set[str]) -> bool:
        return any(full.startswith(sha.lower()) for full in written)

    def history(self, finding: dict) -> list[dict]:
        """One entry per distinct cited commit: its class, its stated role and
        whether it wrote a cited line. A signal of fragility; never confidence."""
        evidence = [ev for ev in finding.get("evidence") or [] if isinstance(ev, dict)]
        written = self._written(evidence)
        out: list[dict] = []
        seen: set[str] = set()
        for ev in evidence:
            if ev.get("type") != "commit":
                continue
            sha = str(ev.get("ref") or "").strip().split()[0]
            if sha in seen:
                continue
            seen.add(sha)
            subject = self._subject(sha)
            out.append({"sha": sha,
                        "class": (c.classify_commit(subject, self.extra_fix)
                                  if subject is not None else None),
                        "role": ev.get("role"),
                        "wrote_cited_line": self._wrote(sha, written)})
        return out
```

In `check_finding`:

- Replace the missing-key hint so it reads `+ (" (it may be [], but the key must be present)" if key == "preconditions" else "")`.
- Before `evidence = f.get("evidence")`, add:

```python
        for field in OPTIONAL_TEXT:
            value = f.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append(f"{where}.{field} must be a non-empty string when present; leave it "
                              f"out when there is nothing to state (got {shown(value)})")
        if "preconditions" in f:
            self.check_preconditions(f["preconditions"], f"{where}.preconditions", errors)
        check = f.get("check")
        if check is not None:
            if not isinstance(check, dict) or check.get("status") not in c.CHECK_STATUSES:
                errors.append(f"{where}.check.status must be one of {list(c.CHECK_STATUSES)}; "
                              f"got {shown(check)}")
            else:
                for key in ("by", "reason"):
                    if check.get(key) is not None and not isinstance(check[key], str):
                        errors.append(f"{where}.check.{key} must be a string or null")
```

- Replace everything after `touching = self.check_commits_touch(...)` and the `code`-evidence rule (the two `conf == "high"` branches) with:

```python
        written: set[str] | None = None
        for i, (ev, etype) in enumerate(zip(evidence, types)):
            if etype != "commit" or ev.get("role") != "introduced":
                continue
            short = str(ev["ref"]).strip().split()[0]
            if short not in touching:
                continue  # unresolvable or not touching: already reported
            written = self._written(evidence) if written is None else written
            if not self._wrote(short, written):
                errors.append(
                    f"{where}.evidence[{i}] is cited as having introduced the cited code, but it "
                    f"wrote none of the cited lines (git blame). Use role \"changed\", or cite "
                    f"the commit that wrote them.")
```

- Delete `_corroborates`.

In `main()`, after `f["evidence_hashes"] = evidence_hashes(repo, f)`:

```python
                f["history"] = validator.history(f)
                if "check" not in f:
                    f["check"] = {"status": "unchecked", "by": None, "reason": None}
```

In `scripts/finding_shape.py`, the keys `shape()` pops from each finding become a module constant, and `shape()` iterates over it:

```python
# Written by validate.py or a later stage, never by a model (spec §3.4).
OWNED_FINDING_KEYS = ("key", "content_hash", "catalog_evidence", "evidence_hashes",
                      "check", "history", "confidence_claimed")
```

`save_finding.py` and `capture_finding.py` need no change: both call `shape()`.

In `scripts/gen_sample_report.py`, `_corroborating_commit` returns a third value, the role: `"introduced"` for the blamed `OTHER` commit, `"fixed"` for the most recent fix, `"changed"` for the most recent change, and `(None, "", None)` when there is none. Its call site becomes:

```python
                sha, note, role = _corroborating_commit(repo, hs, spec, line, env)
                if sha:
                    evidence.append({"type": "commit", "ref": sha, "role": role, "note": note})
```

and every built item gets `item["preconditions"] = []` (Task 8 fills one in).

- [x] **Step 5: Run the tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py tests/test_validate_paths.py tests/test_investigator_contract.py tests/test_pipeline.py -q`
Expected: PASS. Then run the full suite (command in the header); expected `exit=0`.

- [x] **Step 6: Commit**

```bash
git add -A scripts/validate.py scripts/_common.py scripts/finding_shape.py scripts/gen_sample_report.py tests/
git commit -m "Validator: preconditions, commit roles and history; the fix gate goes (#56)"
```

### Task 3: Reported confidence, order and the JSON outputs

**Satisfies:** AC-1, AC-2 (reported confidence and status in `report.json` and `index.json`), AC-3 (history in both), AC-4 (preconditions with links), AC-5 (order), AC-8 (no stored `high` survives).

**Files:**
- Modify: `scripts/report.py` (`collect`, `_attach_commit_subjects`, `link_refs`, `_set_urls`, new `_preconditions`, `_history`, `_ref_url`, `order_key`; `run_warnings`, `render_json`, `render_index`)
- Modify: `scripts/_common.py` (`REPORT_SCHEMA_VERSION = "thunderstruck.report/v2"`)
- Modify: `tests/test_report_html.py` (the schema test's expected `v1` → `v2`)
- Test: `tests/test_checked_confidence.py`

**Interfaces:**
- Consumes: `c.check_status`, `c.effective_confidence`, `c.finding_gate`, `c.GATES`, `c.CHECK_STATUSES` (Task 1); `check`, `history` in findings files (Task 2).
- Produces: each finding in `collect()`'s data carries `confidence` (reported), `confidence_claimed`, `check` (`{status, by, reason, …}`), `gate`, `preconditions[]` with `default_url`/`doc_url`, `history[]` with `subject`/`url`; `report.order_key(f: dict) -> tuple`; `report._preconditions(f) -> list[dict]`; `report._history(f) -> list[dict]`; `report.json` `counts.check_status`, `counts.gate`; `index.json` entries with `check_status`, `gate`, `preconditions`, `history`.

- [x] **Step 1: Write the failing tests.** Append:

```python
# --- Task 3 -----------------------------------------------------------------
import report  # noqa: E402


def _report(repo: Path, plugin_root: Path) -> tuple[dict, dict]:
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(repo)], check=True, capture_output=True)
    out = repo / ".thunderstruck"
    return json.loads((out / "report.json").read_text()), json.loads((out / "index.json").read_text())


def _second_hotspot_finding(repo: Path, confidence: str, preconditions: list) -> tuple[str, dict]:
    hs = _hotspots(repo)["hotspots"][1]
    return hs["id"], {"hotspot_id": hs["id"], "file": hs["file"], "findings": [{
        "location": {"file": hs["file"], "lines": "1"}, "missing_patterns": ["S01"],
        "failure_mode": "A second failure", "trigger_condition": "t", "blast_radius": "b",
        "evidence": [{"type": "code", "ref": f"{hs['file']}:1", "note": "n"}],
        "preconditions": preconditions, "confidence": confidence,
        "confidence_rationale": "r", "how_to_verify": "v"}]}


def test_reported_confidence_is_capped_and_the_claim_kept(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))   # claims high
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    payload, index = _report(scanned_copy, plugin_root)
    f = payload["findings"][0]
    assert (f["confidence"], f["confidence_claimed"]) == ("medium", "high")
    assert f["check"] == {"status": "unchecked", "by": None, "reason": None}
    assert f["gate"] == "none" and f["preconditions"] == []
    assert payload["schema"] == "thunderstruck.report/v2"
    assert payload["counts"]["check_status"] == {"unchecked": 1, "upheld": 0, "narrowed": 0,
                                                 "inconclusive": 0, "refuted": 0}
    assert payload["counts"]["gate"] == {"none": 1, "non_default_setting": 0}
    entry = index["files"][f["location"]["file"]]["findings"][0]
    assert entry["confidence"] == "medium" and entry["check_status"] == "unchecked"
    assert entry["gate"] == "none" and entry["preconditions"] == []
    assert entry["history"] == [{k: h[k] for k in ("sha", "class", "wrote_cited_line")}
                                for h in f["history"]]


def test_an_upheld_check_allows_high_and_a_narrowed_one_drops_a_level(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    path = scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json"
    for status, expected in (("upheld", "high"), ("narrowed", "medium"), ("refuted", "low")):
        saved = json.loads(path.read_text())
        saved["findings"][0]["check"] = {"status": status, "by": "test", "reason": None}
        path.write_text(json.dumps(saved))
        assert _report(scanned_copy, plugin_root)[0]["findings"][0]["confidence"] == expected


def test_a_malformed_check_is_reported_unchecked_with_a_warning(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    path = scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json"
    saved = json.loads(path.read_text())
    saved["findings"][0]["check"] = {"status": "upheld!"}     # tampered after validation
    path.write_text(json.dumps(saved))
    payload, _ = _report(scanned_copy, plugin_root)
    assert payload["findings"][0]["check"]["status"] == "unchecked"
    assert payload["findings"][0]["confidence"] == "medium"
    assert any("FR-001" in w and "reported as unchecked" in w for w in payload["run_warnings"])


def test_gated_findings_follow_default_path_ones(scanned_copy, plugin_root):
    data = _hotspots(scanned_copy)
    hid, doc = _valid_finding(scanned_copy, data)      # highest score, claims high
    gated_ref = f"{data['hotspots'][0]['file']}:1"
    doc["findings"][0]["preconditions"] = [{
        "setting": "SWITCH", "default": "off", "default_ref": gated_ref, "needs": "changed",
        "value": "on", "documented": "not_checked"}]
    _write_finding(scanned_copy, hid, doc)
    hid2, doc2 = _second_hotspot_finding(scanned_copy, "low", [{
        "setting": "LIMIT", "default": "10", "default_ref": gated_ref, "needs": "default",
        "documented": "not_checked"}])
    _write_finding(scanned_copy, hid2, doc2)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    payload, _ = _report(scanned_copy, plugin_root)
    order = [(f["id"], f["gate"], f["failure_mode"]) for f in payload["findings"]]
    assert order[0][1:] == ("none", "A second failure")      # needs: default only → default path
    assert order[1][1] == "non_default_setting" and order[1][0] == "FR-002"
    assert payload["findings"][1]["preconditions"][0]["default_url"] is None   # no remote: unlinked


def test_order_key_keeps_todays_rule_inside_a_gate():
    a = {"gate": "none", "confidence": "medium", "hotspot_score": 1.0, "location": {"file": "a"}}
    b = {"gate": "none", "confidence": "low", "hotspot_score": 9.0, "location": {"file": "b"}}
    g = {"gate": "non_default_setting", "confidence": "high", "hotspot_score": 9.0,
         "location": {"file": "c"}}
    assert sorted([g, b, a], key=report.order_key) == [a, b, g]


def test_preconditions_and_history_are_linked(linked_copy, plugin_root):
    data = _hotspots(linked_copy)
    hid, doc = _valid_finding(linked_copy, data)
    ref = f"{data['hotspots'][0]['file']}:1"
    doc["findings"][0]["preconditions"] = [{
        "setting": "S", "default": "d", "default_ref": ref, "needs": "default",
        "documented": "yes", "doc_ref": ref}]
    _write_finding(linked_copy, hid, doc)
    assert _validate(linked_copy, plugin_root).returncode == 0
    f = _report(linked_copy, plugin_root)[0]["findings"][0]
    p = f["preconditions"][0]
    assert p["default_url"].startswith("https://github.com/acme/fixture/") and p["doc_url"]
    assert f["history"][0]["url"].startswith("https://github.com/acme/fixture/")
    assert isinstance(f["history"][0]["subject"], str)
    assert all("kind" not in ev for ev in f["evidence"])
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py -q -k "capped or upheld or malformed or gated or order_key or linked"`
Expected: FAIL (`KeyError: 'confidence_claimed'`, `AttributeError: module 'report' has no attribute 'order_key'`).

- [x] **Step 3: Write the implementation.**

`scripts/_common.py`: `REPORT_SCHEMA_VERSION = "thunderstruck.report/v2"`. `tests/test_report_html.py::test_wrong_schema_writes_nothing`: expect `thunderstruck.report/v2` in stderr.

In `scripts/report.py`, add helpers next to `_evidence`:

```python
def _preconditions(f: dict) -> list[dict]:
    return [p for p in (f.get("preconditions") or []) if isinstance(p, dict)]


def _history(f: dict) -> list[dict]:
    return [h for h in (f.get("history") or []) if isinstance(h, dict)]


def order_key(f: dict) -> tuple:
    """Default-path findings first (#56 AC-5); inside a gate, today's order."""
    return (c.GATES.index(f.get("gate", "none")) if f.get("gate", "none") in c.GATES else len(c.GATES),
            CONFIDENCE_RANK.get(f.get("confidence"), 9),
            -(f.get("hotspot_score") or 0.0),
            str(f.get("location", {}).get("file", "")))
```

In `collect()`, inside `for f in items:` after `f["hotspot_score"] = …`:

```python
            status = c.check_status(f)
            stored = f.get("check") if isinstance(f.get("check"), dict) else {}
            f["_check_fallback"] = stored.get("status") != status
            f["check"] = {"by": None, "reason": None, **stored, "status": status}
            f["confidence_claimed"] = f.get("confidence")
            f["confidence"] = c.effective_confidence(f["confidence_claimed"], status)
            f["gate"] = c.finding_gate(f)
```

Replace the `findings.sort(...)` call with `findings.sort(key=order_key)`. After the ids are assigned:

```python
    check_warnings = [f"{f['id']}: check status missing or unrecognised in its findings file; "
                      f"reported as unchecked" for f in findings if f.pop("_check_fallback")]
```

and add `"check_warnings": check_warnings` to the returned dict. `run_warnings` appends `+ list(data.get("check_warnings") or [])`.

Replace `_attach_commit_subjects`'s body so it attaches the subject to evidence items and history entries, and no longer writes `kind`:

```python
    cache: dict[str, str | None] = {}

    def subject(sha: str) -> str | None:
        if sha not in cache:
            try:
                cache[sha] = c.git_paths(repo, "log", "-1", "--format=%s", sha, "--").strip("\n")
            except (c.ThunderstruckError, OSError, subprocess.SubprocessError):
                cache[sha] = None
        return cache[sha]

    for f in findings:
        for ev in _evidence(f):
            if ev.get("type") == "commit" and str(ev.get("ref") or "").strip():
                ev["subject"] = subject(str(ev["ref"]).split()[0])
        for h in _history(f):
            if h.get("sha"):
                h["subject"] = subject(str(h["sha"]))
```

Its docstring says: "Give every cited commit its subject, so a reader sees the history itself. The class is in `history`." Drop the now-unused `extra_fix` lookup there.

In `link_refs`, inside the `for f in findings:` loop, add the precondition paths:

```python
            for p in _preconditions(f):
                for key in ("default_ref", "doc_ref"):
                    if (m := CODE_REF.match(str(p.get(key) or "").strip())):
                        paths.add(m["path"])
```

Add `_ref_url` and extend `_set_urls`:

```python
def _ref_url(ctx: "links.LinkContext | None", ref) -> str | None:
    m = CODE_REF.match(str(ref or "").strip())
    if not ctx or not m:
        return None
    start, end = int(m["start"]), int(m["end"] or m["start"])
    return ctx.code(m["path"], min(start, end), max(start, end))
```

and at the end of `_set_urls`'s per-finding loop:

```python
        for p in _preconditions(f):
            p["default_url"] = _ref_url(ctx, p.get("default_ref"))
            p["doc_url"] = _ref_url(ctx, p.get("doc_ref"))
        for h in _history(f):
            full = result.commits.get(str(h.get("sha"))) if (ctx and result) else None
            h["url"] = ctx.commit(full) if full else None
```

In `render_json`'s `counts`:

```python
            "check_status": {s: sum(1 for f in data["findings"] if f["check"]["status"] == s)
                             for s in c.CHECK_STATUSES},
            "gate": {g: sum(1 for f in data["findings"] if f["gate"] == g) for g in c.GATES},
```

In `render_index`, the item becomes:

```python
        item = {
            "id": f["id"], "key": f.get("key"), "lines": loc.get("lines"),
            "symbol": loc.get("symbol"),
            "failure_mode": f.get("failure_mode"),
            "missing_patterns": f.get("missing_patterns") or [],
            "confidence": f.get("confidence"),
            "check_status": f["check"]["status"],
            "gate": f["gate"],
            "preconditions": [{k: p.get(k) for k in ("setting", "default", "needs", "value")}
                              for p in _preconditions(f)],
            "history": [{k: h.get(k) for k in ("sha", "class", "wrote_cited_line")}
                        for h in _history(f)],
        }
        if f.get("sustaining_effect"):
            item["sustaining_effect"] = f["sustaining_effect"]
```

- [x] **Step 4: Run the tests to verify they pass** (same command as Step 2, then the full suite). Expected: PASS, `exit=0`.

- [x] **Step 5: Commit**

```bash
git add scripts/report.py scripts/_common.py tests/test_checked_confidence.py tests/test_report_html.py
git commit -m "Report: confidence capped by check status, default-path findings first (#56)"
```

### Task 4: `report.md`

**Satisfies:** AC-2 (status shown), AC-3 (History block), AC-4 (Preconditions block), AC-5 (the marker), AC-6 (*not stated*), AC-7 (what validation proved).

**Files:**
- Modify: `scripts/report.py` (`render_markdown`, `_evidence_ref`, `lead_precision` docstring; new `_not_stated`, `render_check`, `render_preconditions`, `render_history`)
- Modify: `tests/test_inert_report.py` (`MODEL_FIELDS` and the precondition and check fields)
- Test: `tests/test_checked_confidence.py`

**Interfaces:**
- Consumes: Task 3's per-finding fields; `c.CHECK_SENTENCES`, `c.GATE_MARKERS`.
- Produces: `report.render_check(f) -> list[str]`, `report.render_preconditions(f) -> list[str]`, `report.render_history(f) -> list[str]`.

- [x] **Step 1: Write the failing tests.** Append:

```python
# --- Task 4 -----------------------------------------------------------------
def _f(**over) -> dict:
    f = {"confidence": "medium", "confidence_claimed": "high", "gate": "none",
         "check": {"status": "unchecked", "by": None, "reason": None},
         "preconditions": [], "history": []}
    f.update(over)
    return f


def test_check_line():
    assert report.render_check(_f())[0] == (
        "**Check** — unchecked. No one has tried to refute this claim, so it is reported at "
        "medium confidence (claimed high).")
    assert report.render_check(_f(confidence_claimed="medium"))[0] == (
        "**Check** — unchecked. No one has tried to refute this claim.")
    upheld = _f(confidence="high", check={"status": "upheld", "by": "s", "reason": "it held"})
    assert report.render_check(upheld)[0].endswith("refute this claim and it held. it held")


PRE = {"setting": "API_RETRY_ON_429", "default": "false (unset)", "default_ref": "src/a.ts:1",
       "default_url": None, "needs": "changed", "value": "true", "documented": "no"}


def test_preconditions_block():
    assert report.render_preconditions(_f())[0] == (
        "**Preconditions** — none: the failure happens on default settings.")
    gated = "\n".join(report.render_preconditions(_f(gate="non_default_setting", preconditions=[PRE])))
    assert ("- `API_RETRY_ON_429` set to `true`; default `false (unset)`, registered at "
            "`src/a.ts:1`. The docs do not describe this behaviour.") in gated
    rests = {**PRE, "needs": "default", "value": None, "documented": "yes",
             "doc_ref": "docs/x.md:3", "doc_url": "https://h/x#L3"}
    text = "\n".join(report.render_preconditions(_f(preconditions=[rests])))
    assert "The failure happens on default settings and rests on these defaults:" in text
    assert "`API_RETRY_ON_429` left at its default `false (unset)`" in text
    assert "The docs describe this behaviour: [`docs/x.md:3`](https://h/x#L3)." in text
    assert "Docs not checked." in "\n".join(
        report.render_preconditions(_f(preconditions=[{**PRE, "documented": "not_checked"}])))


def test_history_block():
    assert report.render_history(_f())[0] == "**History** — none cited."
    hist = [{"sha": "1a2b3c4d", "class": "fix", "role": "fixed", "wrote_cited_line": False, "url": None},
            {"sha": "5d6e7f8", "class": None, "role": "introduced", "wrote_cited_line": True, "url": None}]
    text = "\n".join(report.render_history(_f(history=hist)))
    assert text.startswith("**History** — a signal of how often this code changed, "
                           "not of whether the claim holds.")
    assert "- `1a2b3c4` fix · stated role: fixed · wrote none of the cited lines" in text
    assert "- `5d6e7f8` class unavailable · stated role: introduced · wrote a cited line" in text


def test_report_md_states_what_validation_proved(scanned_copy, plugin_root):
    data = _hotspots(scanned_copy)
    hid, doc = _valid_finding(scanned_copy, data)
    f = doc["findings"][0]
    del f["amplifier"]
    f["preconditions"] = [{"setting": "SWITCH", "default": "off",
                           "default_ref": f"{data['hotspots'][0]['file']}:1", "needs": "changed",
                           "value": "on", "documented": "not_checked"}]
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    _report(scanned_copy, plugin_root)
    md_text = (scanned_copy / ".thunderstruck" / "report.md").read_text()
    assert "That is all validation proves." in md_text
    assert "validated finding" not in md_text
    assert "Check status: 1 unchecked · 1 finding needs a non-default setting and is listed last" in md_text
    assert "**medium confidence** · unchecked · needs a non-default setting · " in md_text
    assert "| Amplifier | _not stated_ |" in md_text
    assert "_none — this one stops" not in md_text
    for block in ("**Check** — unchecked.", "**Preconditions**", "**History** — "):
        assert block in md_text
    commit_line = next(l for l in md_text.splitlines() if l.startswith("- _commit_"))
    assert commit_line.count("(fix)") == 0
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py -q -k "check_line or block or validation_proved"`
Expected: FAIL, `AttributeError: module 'report' has no attribute 'render_check'`.

- [x] **Step 3: Write the implementation.** In `scripts/report.py`, add after `_shared_line`:

```python
def _not_stated(value) -> str:
    return md.text(value, cell=True) if value else "_not stated_"


def render_check(f: dict) -> list[str]:
    status = f["check"]["status"]
    line = f"**Check** — {status}. {c.CHECK_SENTENCES[status]}"
    claimed = f.get("confidence_claimed")
    if claimed in c.CONFIDENCE_LEVELS and claimed != f.get("confidence"):
        line += f", so it is reported at {f['confidence']} confidence (claimed {claimed})"
    line += "."
    if f["check"].get("reason"):
        line += f" {md.text(f['check']['reason'])}"
    return [line, ""]


def _precondition_line(p: dict) -> str:
    setting, default = md.code(p.get("setting")), md.code(p.get("default"))
    where = _linked(str(p.get("default_ref")), p.get("default_url"))
    if p.get("needs") == "changed":
        line = f"{setting} set to {md.code(p.get('value'))}; default {default}, registered at {where}."
    else:
        line = f"{setting} left at its default {default}, registered at {where}."
    if p.get("documented") == "yes":
        line += f" The docs describe this behaviour: {_linked(str(p.get('doc_ref')), p.get('doc_url'))}."
    elif p.get("documented") == "no":
        line += " The docs do not describe this behaviour."
    else:
        line += " Docs not checked."
    return f"- {line}"


def render_preconditions(f: dict) -> list[str]:
    items = _preconditions(f)
    if not items:
        return ["**Preconditions** — none: the failure happens on default settings.", ""]
    L = ["**Preconditions**", ""]
    if f.get("gate") == "none":
        L += ["The failure happens on default settings and rests on these defaults:", ""]
    return L + [_precondition_line(p) for p in items] + [""]


def render_history(f: dict) -> list[str]:
    items = _history(f)
    if not items:
        return ["**History** — none cited.", ""]
    L = ["**History** — a signal of how often this code changed, not of whether the claim holds.", ""]
    for h in items:
        cls = md.text(h["class"]) if h.get("class") else "class unavailable"
        wrote = "wrote a cited line" if h.get("wrote_cited_line") else "wrote none of the cited lines"
        L.append(f"- {_linked(str(h.get('sha'))[:7], h.get('url'))} {cls} · "
                 f"stated role: {md.text(h.get('role') or '?')} · {wrote}")
    return L + [""]
```

In `_evidence_ref`, the subject suffix becomes `f" — “{md.text(subject)}”"` (no class).

In `render_markdown`:

- After the `breakdown` line, compute and add the check line (the breakdown line gains a trailing double space):

```python
    by_status = [(s, sum(1 for f in findings if f["check"]["status"] == s)) for s in c.CHECK_STATUSES]
    gated = sum(1 for f in findings if f["gate"] != "none")
    check_line = ("Check status: " + " · ".join(f"{n} {s}" for s, n in by_status if n)
                  + (f" · {gated} {'finding needs' if gated == 1 else 'findings need'} a "
                     f"non-default setting and {'is' if gated == 1 else 'are'} listed last"
                     if gated else "")) if findings else None
```

  The header list then reads `…(f" — {breakdown}" if breakdown else "") + "  "`, then `*([check_line] if check_line else [])`, then `""`.
- The blockquote is replaced by:

```python
        "> Findings are **falsifiable hypotheses**. Every citation in them was resolved "
        "mechanically: each cited file:line, commit, detector hit and catalog edge exists. "
        "That is all validation proves. Whether a claim holds is its **check status**; a "
        "finding nobody has tried to refute is `unchecked`, and its confidence is at most "
        "`medium`. Check the `Verify` line before you act on one.",
```

- The coverage paragraph's last sentence: "*Leads confirmed* counts those cited by a finding whose citations resolved." `lead_precision`'s docstring: "the distinct ones cited by a finding whose citations resolved (confirmed)".
- The finding rows: `| Amplifier | {_not_stated(f.get('amplifier'))} |` and `| Sustaining effect | {_not_stated(f.get('sustaining_effect'))} |`.
- The badge line:

```python
            marker = f" · {c.GATE_MARKERS[f['gate']]}" if f["gate"] in c.GATE_MARKERS else ""
            badge = (f"**{BADGE.get(f.get('confidence'), '?')} confidence** · "
                     f"{f['check']['status']}{marker} · ")
```

  and the line is `badge + f"{where}{symbol} · hotspot {f['hotspot_id']} (score {f.get('hotspot_score')})"`.
- After the evidence list, `L += ["", *render_check(f), *render_preconditions(f), *render_history(f), f"**Verify** — …  ", f"**Why this confidence** — …  "]` (Verify and Why lines unchanged).

In `tests/test_inert_report.py::test_hostile_model_text_stays_inert`, after the field loop, add hostile text to a precondition and to the check reason:

```python
    finding["preconditions"] = [{"setting": f"setting: {HOSTILE}", "default": f"default: {HOSTILE}",
                                 "default_ref": finding["evidence"][0]["ref"], "needs": "changed",
                                 "value": f"value: {HOSTILE}", "documented": "not_checked"}]
```

  and, after `_validate` and before `report.py`, set `check.reason` to `f"reason: {HOSTILE}"` in the saved findings file (read, edit, write the JSON). The assertions are unchanged.

- [x] **Step 4: Run the tests to verify they pass** (Step 2's command, `tests/test_inert_report.py`, then the full suite). Expected: PASS, `exit=0`.

- [x] **Step 5: Commit**

```bash
git add scripts/report.py tests/test_checked_confidence.py tests/test_inert_report.py
git commit -m "report.md: check status, preconditions and history per finding (#56)"
```

### Task 5: The HTML report

**Satisfies:** AC-2, AC-3, AC-4, AC-5 (the page keeps the report's order and marks gated findings), AC-6, AC-7.

**Files:**
- Modify: `templates/report.html`
- Modify: `tests/test_report_html.py` (`MODEL_FIELDS`), `tests/test_report_html_browser.py` (`_two_findings`, filter test)
- Test: `tests/test_checked_confidence.py`

**Interfaces:**
- Consumes: `report.json` v2 fields (Task 3); `c.CHECK_SENTENCES`, `c.GATE_MARKERS`.
- Produces: in the template script, `var CHECK_SENTENCES = {…}` and `var GATE_MARKERS = {…}` written as JSON object literals (double-quoted keys), on one line each.

- [x] **Step 1: Write the failing tests.** Append:

```python
# --- Task 5 -----------------------------------------------------------------
import re  # noqa: E402

TEMPLATE = ROOT / "templates" / "report.html"


def _js_object(name: str) -> dict:
    m = re.search(rf"var {name} = (\{{.*?\}});", TEMPLATE.read_text(encoding="utf-8"))
    assert m, name
    return json.loads(m.group(1))


def test_template_sentences_and_markers_match_common():
    assert _js_object("CHECK_SENTENCES") == c.CHECK_SENTENCES
    assert _js_object("GATE_MARKERS") == c.GATE_MARKERS


def test_template_keeps_the_report_order_and_states_what_validation_proved():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert ".sort(" not in text.split("function start(R)", 1)[1].split("var hotspots", 1)[0]
    assert "That is all validation proves." in text
    assert "validated finding" not in text
    assert "This one stops when the trigger stops" not in text
    for label in ('"Check"', '"Preconditions"', '"History"', '"Not stated."'):
        assert label in text, label
```

In `tests/test_report_html.py`, `MODEL_FIELDS` stays a tuple of finding fields; `test_hostile_model_text_stays_inside_the_data_block` additionally sets, before validating, `doc["findings"][0]["preconditions"] = [{"setting": HOSTILE_TEXT, "default": HOSTILE_TEXT, "default_ref": doc["findings"][0]["evidence"][0]["ref"], "needs": "changed", "value": HOSTILE_TEXT, "documented": "not_checked"}]`. Its assertions are unchanged.

In `tests/test_report_html_browser.py`, `_two_findings` sets the second finding's `confidence="low"`, and `test_filter_and_keyboard_stepping` clicks the `"Low"` button instead of `"Medium"` (every finding claimed `high` is now reported `medium`, so `Medium` would list both). Add:

```python
def test_dossier_shows_check_preconditions_and_history(page, scanned_copy, plugin_root):
    report = _report(scanned_copy, plugin_root)
    f = report["findings"][0]
    f["gate"] = "non_default_setting"
    f["preconditions"] = [{"setting": "SWITCH", "default": "off", "default_ref": "a.ts:1",
                           "default_url": None, "needs": "changed", "value": "on",
                           "documented": "no", "doc_ref": None, "doc_url": None}]
    f.pop("amplifier", None)
    p = page(report)
    p.page.keyboard.press("j")
    body = p.page.inner_text("#doc")
    assert "unchecked" in body and "needs a non-default setting" in body
    assert "SWITCH set to on; default off, registered at a.ts:1." in body
    assert "Not stated." in body and "History" in body
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py -q -k "template"`
Expected: FAIL, `AssertionError: CHECK_SENTENCES`.

- [x] **Step 3: Write the implementation.** In `templates/report.html`'s script:

- After `var KIND = …`, add (one line each, JSON-compatible):

```js
  var CHECK_SENTENCES = {"unchecked": "No one has tried to refute this claim", "upheld": "A check tried to refute this claim and it held", "narrowed": "A check found that only part of this claim holds", "inconclusive": "A check could not settle this claim", "refuted": "A check refuted this claim"};
  var GATE_MARKERS = {"non_default_setting": "needs a non-default setting"};
```

- In `start(R)`: `var findings = (R.findings || []).slice();` (the sort is removed; `RANK` is deleted if nothing else uses it).
- Add, before `renderDoc`:

```js
    function checkText(f) {
      var ck = f.check || {}, st = CHECK_SENTENCES[ck.status] ? ck.status : "unchecked";
      var s = st + ". " + CHECK_SENTENCES[st];
      if (f.confidence_claimed && f.confidence_claimed !== f.confidence)
        s += ", so it is reported at " + f.confidence + " confidence (claimed " + f.confidence_claimed + ")";
      s += ".";
      if (ck.reason) s += " " + ck.reason;
      return s;
    }
    function preconditionList(f) {
      var ps = f.preconditions || [];
      if (!ps.length) return "None: the failure happens on default settings.";
      var lead = f.gate === "none" ? [h("div", { class: "small", text: "The failure happens on default settings and rests on these defaults:" })] : [];
      return h("div", { class: "ev" }, lead.concat(ps.map(function (p) {
        var kids = [h("span", { class: "mono", text: String(p.setting || "") })];
        kids.push(p.needs === "changed"
          ? " set to " + p.value + "; default " + p["default"] + ", registered at "
          : " left at its default " + p["default"] + ", registered at ");
        kids.push(link(String(p.default_ref || ""), p.default_url, "mono"));
        kids.push(".");
        if (p.documented === "yes") {
          kids.push(" The docs describe this behaviour: ");
          kids.push(link(String(p.doc_ref || ""), p.doc_url, "mono"));
          kids.push(".");
        } else kids.push(p.documented === "no" ? " The docs do not describe this behaviour." : " Docs not checked.");
        return h("div", null, kids);
      })));
    }
    function historyList(f) {
      var hs = f.history || [];
      if (!hs.length) return "None cited.";
      return h("div", { class: "ev" }, [h("div", { class: "small", text: "A signal of how often this code changed, not of whether the claim holds." })]
        .concat(hs.map(function (x) {
          return h("div", null, [link(String(x.sha || "").slice(0, 7), x.url, "mono"),
            " " + (x["class"] || "class unavailable") + " · stated role: " + (x.role || "?") + " · " +
            (x.wrote_cited_line ? "wrote a cited line" : "wrote none of the cited lines")]);
        })));
    }
```

- In `renderDoc`, the meta row's last tags become the confidence tag, then `h("span", { class: "tag", text: (f.check && f.check.status) || "unchecked" })`, then, when `GATE_MARKERS[f.gate]`, `h("span", { class: "tag accent", text: GATE_MARKERS[f.gate] })`.
- Rows: `row("Amplifier", f.amplifier || "Not stated.", { cls: f.amplifier ? "" : "quiet" })`; `row("Keeps it failing", f.sustaining_effect || "Not stated.", { amber: true, cls: f.sustaining_effect ? "" : "quiet" })`. After the Evidence row: `rows.appendChild(row("Check", checkText(f)));`, `rows.appendChild(row("Preconditions", preconditionList(f)));`, `rows.appendChild(row("History", historyList(f)));`.
- `evidenceList`: the commit sub-line is `"“" + ev.subject + "”"` (no class) or `"(subject unavailable)"`.
- `renderList`: inside `item-top`, after the patterns span, add `GATE_MARKERS[f.gate] ? h("span", { class: "pat", text: "setting", title: GATE_MARKERS[f.gate] }) : null`.
- `renderHead`: the counts gain `h("span", null, [h("b", { text: String(nUnchecked) }), "unchecked"])` when `nUnchecked` (the number of findings whose `check.status` is `unchecked` or missing) is non-zero.
- The overview's `hypo` text becomes: `"Findings are falsifiable hypotheses. Every citation in them was resolved mechanically: each cited file:line, commit, detector hit and catalog edge exists. That is all validation proves. Whether a claim holds is its check status; a finding nobody has tried to refute is unchecked, and its confidence is at most medium. Check it before you act on one."` The coverage sentence ends "leads confirmed counts those cited by a finding whose citations resolved."

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py tests/test_report_html.py -q`, then, where Chromium is installed, `THUNDERSTRUCK_REQUIRE_BROWSER=1 uv run --with pytest --with pyyaml --with lizard --with playwright==1.56.0 pytest tests/test_report_html_browser.py -q`, then the full suite.
Expected: PASS, `exit=0`.

- [x] **Step 5: Commit**

```bash
git add templates/report.html tests/test_checked_confidence.py tests/test_report_html.py tests/test_report_html_browser.py
git commit -m "HTML report: check status, preconditions and history; the report's order (#56)"
```

### Task 6: The guardrail

**Satisfies:** AC-2, AC-3, AC-4 (stated in the guardrail), AC-8 (an older index never states a `high`).

**Files:**
- Modify: `scripts/guardrail.py`
- Test: `tests/test_checked_confidence.py`

**Interfaces:**
- Consumes: `index.json` entries from Task 3 (`check_status`, `gate`, `preconditions`, `history`, reported `confidence`).
- Produces: in `guardrail`: `CEILING: dict[str, str]`, `LEVELS`, `GATE_ORDER` (pinned to `_common.GATES` by a test), `effective(confidence, status) -> str` (a copy of `_common.effective_confidence`), `precondition_line(f) -> str | None`, `history_line(f) -> str | None`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 6 -----------------------------------------------------------------
import guardrail  # noqa: E402
from test_guardrail import project, run_hook  # noqa: E402,F401


@pytest.mark.parametrize("claimed, status", sorted(TABLE))
def test_guardrail_ceiling_copy_matches_common(claimed, status):
    assert guardrail.effective(claimed, status) == c.effective_confidence(claimed, status)
    assert guardrail.effective(claimed, "bogus") == c.effective_confidence(claimed, "bogus")


def test_guardrail_gate_order_matches_common():
    assert guardrail.GATE_ORDER == c.GATES


def _context(project: Path, findings: list[dict]) -> str:
    index = json.loads((project / ".thunderstruck" / "index.json").read_text())
    index["files"]["src/flagged.ts"]["findings"] = findings
    (project / ".thunderstruck" / "index.json").write_text(json.dumps(index))
    return json.loads(run_hook(project, "src/flagged.ts").stdout)["hookSpecificOutput"]["additionalContext"]


NEW = {"id": "FR-001", "failure_mode": "f", "missing_patterns": ["S03"], "confidence": "medium",
       "check_status": "unchecked", "gate": "none", "preconditions": [], "history": []}


def test_guardrail_states_status_preconditions_and_history(project):
    gated = {**NEW, "id": "FR-002", "gate": "non_default_setting",
             "preconditions": [{"setting": "API_RETRY_ON_429", "default": "false (unset)",
                                "needs": "changed", "value": "true"}],
             "history": [{"sha": "1a2b3c4", "class": "fix", "wrote_cited_line": True},
                         {"sha": "5d6e7f8", "class": "feature", "wrote_cited_line": False}]}
    rests = {**NEW, "id": "FR-003", "preconditions": [{"setting": "LIMIT", "default": "10",
                                                       "needs": "default", "value": None}]}
    text = _context(project, [gated, NEW, rests])
    assert "confidence: medium; check status: unchecked." in text
    assert "It happens on default settings." in text
    assert "It happens on default settings and rests on LIMIT at its default 10." in text
    assert ("It happens only with a non-default setting: API_RETRY_ON_429 set to true "
            "(default false (unset)).") in text
    assert ("Cited commits: 1a2b3c4 fix, wrote a cited line; 5d6e7f8 feature, wrote none of "
            "the cited lines.") in text
    assert text.index("FR-001") < text.index("FR-003") < text.index("FR-002")


def test_guardrail_caps_an_index_from_before_checked_confidence(project):
    old = {"id": "FR-001", "failure_mode": "f", "missing_patterns": ["S03"], "confidence": "high",
           "sustaining_effect": "s"}
    text = _context(project, [old])
    assert "confidence: medium; check status: unchecked." in text
    assert "high" not in text
    assert "It happens" not in text and "Cited commits" not in text


def test_guardrail_lists_at_most_three_items(project):
    many = [{"setting": f"S{n}", "default": "d", "needs": "changed", "value": "v"} for n in range(5)]
    text = _context(project, [{**NEW, "gate": "non_default_setting", "preconditions": many}])
    assert "S2 set to v (default d) and 2 more." in text and "S3" not in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py -q -k guardrail`
Expected: FAIL, `AttributeError: module 'guardrail' has no attribute 'effective'`.

- [ ] **Step 3: Write the implementation.** In `scripts/guardrail.py`, add after the constants:

```python
# A copy of _common's confidence rule: this hook may not import _common.
# tests/test_checked_confidence.py pins the two together.
LEVELS = ("low", "medium", "high")
CEILING = {"upheld": "high", "unchecked": "medium", "narrowed": "medium",
           "inconclusive": "medium", "refuted": "low"}
GATE_ORDER = ("none", "non_default_setting")
MAX_ITEMS_SHOWN = 3


def effective(confidence, status) -> str:
    level = LEVELS.index(confidence) if confidence in LEVELS else 0
    status = status if status in CEILING else "unchecked"
    if status == "narrowed":
        level = max(0, level - 1)
    return LEVELS[min(level, LEVELS.index(CEILING[status]))]


def _capped(parts: list[str], sep: str) -> str:
    text = sep.join(parts[:MAX_ITEMS_SHOWN])
    if len(parts) > MAX_ITEMS_SHOWN:
        text += f" and {len(parts) - MAX_ITEMS_SHOWN} more"
    return text


def precondition_line(f: dict) -> str | None:
    if "check_status" not in f:
        return None  # an index from before #56 states nothing about preconditions
    items = [p for p in f.get("preconditions") or [] if isinstance(p, dict)]
    changed = [p for p in items if p.get("needs") == "changed"]
    if changed:
        return ("It happens only with a non-default setting: " + _capped(
            [f"{p.get('setting')} set to {p.get('value')} (default {p.get('default')})"
             for p in changed], ", ") + ".")
    if items:
        return ("It happens on default settings and rests on " + _capped(
            [f"{p.get('setting')} at its default {p.get('default')}" for p in items], ", ") + ".")
    return "It happens on default settings."


def history_line(f: dict) -> str | None:
    items = [h for h in f.get("history") or [] if isinstance(h, dict)]
    if not items:
        return None
    return "Cited commits: " + _capped(
        [f"{h.get('sha')} {h.get('class') or 'class unavailable'}, "
         + ("wrote a cited line" if h.get("wrote_cited_line") else "wrote none of the cited lines")
         for h in items], "; ") + "."
```

In `build_context`, replace the selection, sort and per-finding lines:

```python
    findings = []
    for f in entry.get("findings", []):
        if not isinstance(f, dict):
            continue
        status = f.get("check_status") if f.get("check_status") in CEILING else "unchecked"
        confidence = effective(f.get("confidence"), status)
        if confidence in MIN_CONFIDENCE:
            findings.append({**f, "_status": status, "_confidence": confidence})
    if not findings:
        return None
    order = {"high": 0, "medium": 1}
    findings.sort(key=lambda f: (GATE_ORDER.index(f.get("gate")) if f.get("gate") in GATE_ORDER
                                 else 0, order.get(f["_confidence"], 9)))
```

and, per shown finding:

```python
        lines.append(f"  missing patterns: {pats}; confidence: {f['_confidence']}; "
                     f"check status: {f['_status']}.")
        for extra in (precondition_line(f), history_line(f)):
            if extra:
                lines.append(f"  {extra}")
        if f.get("sustaining_effect"):
            lines.append(f"  what keeps it failing: {f['sustaining_effect']}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py tests/test_guardrail.py -q`, then the full suite.
Expected: PASS (including `test_hook_needs_no_third_party_imports`, `test_context_is_phrased_as_fact_not_instruction` and `test_latency_is_within_budget`), `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/guardrail.py tests/test_checked_confidence.py
git commit -m "Guardrail: check status, preconditions and cited history as facts (#56)"
```

### Task 7: The investigator's instructions

**Satisfies:** AC-10 (the investigator instructions describe the new fields), AC-1 (no instruction ties confidence to a fix), AC-6.

**Files:**
- Modify: `agents/thunderstruck-investigator.md`
- Modify: `skills/thunderstruck-scan/SKILL.md` (step 4's repair text)
- Modify: `scripts/bundle.py` (`write_catalog_brief`'s metastability paragraph)
- Modify: `skills/thunderstruck-verify/SKILL.md`
- Modify: `tests/test_investigator_contract.py`

**Interfaces:**
- Consumes: `validate.REQUIRED_FIELDS`, `validate.PRECONDITION_KEYS`, `c.COMMIT_ROLES` (Task 2).

- [ ] **Step 1: Write the failing tests.** In `tests/test_investigator_contract.py`:

```python
from validate import PRECONDITION_KEYS, REQUIRED_FIELDS

REQUIRED = list(REQUIRED_FIELDS)
```

replaces the hand-written `REQUIRED` list. `test_the_prompt_example_is_a_complete_valid_shape` becomes:

```python
def test_the_prompt_example_is_a_complete_valid_shape():
    example = _example(AGENT.read_text(encoding="utf-8"))
    assert set(example) <= {"hotspot_id", "file", "findings", "notes"}
    findings = example["findings"]
    assert 1 <= len(findings) <= 3
    for f in findings:
        assert set(REQUIRED) <= set(f), set(REQUIRED) - set(f)
        assert isinstance(f["location"], dict) and "file" in f["location"]
        for ev in f["evidence"]:
            expected = {"type", "ref", "role", "note"} if ev["type"] == "commit" else {"type", "ref", "note"}
            assert set(ev) == expected and isinstance(ev["ref"], str)
            assert ev["type"] in {"code", "commit", "detector", "catalog"}
            if ev["type"] == "commit":
                assert ev["role"] in c.COMMIT_ROLES
        for p in f["preconditions"]:
            assert set(p) <= PRECONDITION_KEYS and p["needs"] in c.PRECONDITION_NEEDS
    assert any(f["preconditions"] for f in findings), "the example must show a precondition"
    assert any(f["preconditions"] == [] for f in findings), "and a default-path finding"
    assert any("sustaining_effect" not in f for f in findings), \
        "the example must show an optional field left out"
```

In `test_the_prompt_states_each_field_observed_rule`, the fragment tuple replaces `'"sustaining_effect": null'` with `'"preconditions": []'`, `"`role`"` and `"History never raises or caps your confidence"`; `"[fix]"` stays. Add:

```python
def test_the_prompt_never_ties_confidence_to_a_fix():
    flat = " ".join(AGENT.read_text(encoding="utf-8").split())
    assert "needs a cited commit labelled `[fix]`" not in flat
    assert "Without such a commit the ceiling is" not in flat
```

and in `test_the_repair_round_asks_for_the_whole_object`, add `assert "`preconditions` may be `[]` but must be present" in flat`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_investigator_contract.py -q`
Expected: FAIL (the example has no `preconditions`; the old `[fix]` ceiling sentence is present).

- [ ] **Step 3: Write the implementation.**

In `agents/thunderstruck-investigator.md`:

- **Method step 2** ends with: "History never raises or caps your confidence: the report shows each cited commit's class and whether it wrote a cited line as a separate signal of how fragile the code is."
- **Method step 3**: "If nothing sustains it, leave `sustaining_effect` out — a fast-recovering failure is a normal finding, not a weak one. The same holds for `amplifier`: state one only when the code shows it."
- New **Method step 5**: "**State what has to be true.** For each setting the failure depends on, add a `preconditions` item: the setting, its default as the code registers it, where that default is registered, whether the failure needs the setting changed (`needs: \"changed\"`, with the `value` it needs) or happens on the default (`needs: \"default\"`), and whether the repository's docs describe the behaviour. A failure that needs nothing changed and rests on no default has `\"preconditions\": []`. A condition of the deployment rather than a setting belongs in `trigger_condition`."
- **Rule 3** becomes: "**Every finding has all ten required keys**, even in a repair: `location`, `missing_patterns`, `failure_mode`, `trigger_condition`, `blast_radius`, `evidence`, `preconditions`, `confidence`, `confidence_rationale`, `how_to_verify`. `\"preconditions\": []` is valid; the key must be present. `amplifier`, `sustaining_effect` and `prediction` are optional: leave a field out when there is nothing to state, never write an empty string or filler."
- **Rule 5**'s table: the `commit` row's example is `"a1b2c3d"`, and a paragraph after the table: "A `commit` item also has `role`: `introduced` (it wrote the cited code — checked against `git blame`, and rejected if it wrote none of the cited lines), `fixed` (an earlier attempt to fix this failure or one like it), `mitigated` (it added a guard, option or retry that limits the failure without removing it) or `changed` (anything else). `role` is only given on commit evidence."
- New **rule 6a**, numbered as the next rule after rule 6 (renumber the rest): "**Each precondition is one object** with exactly these keys: `setting`, `default` (text), `default_ref` (a `path:line` where the default is registered, resolving like a `code` ref), `needs` (`changed` or `default`), `value` (required when `needs` is `changed`, otherwise left out), `documented` (`yes`, `no` or `not_checked`) and `doc_ref` (a `path:line` in the docs, only when `documented` is `yes`). One item per setting."
- **Rule 9** becomes: "**`confidence`** is `\"low\"`, `\"medium\"` or `\"high\"`: how strongly what you read supports the claim if it survives someone trying to refute it. The report caps it at `medium` until a check upholds the claim, and says so. History never raises or caps your confidence; do not rate a finding up because a `[fix]` commit exists, or down because none does."
- **The example**: the first finding (`syncCatalog`) keeps `amplifier` and `sustaining_effect`, gains `"preconditions": []`, and its commit item becomes `{ "type": "commit", "ref": "a1b2c3d", "role": "fixed", "note": "3rd 'fix timeout' commit in 6 weeks" }`. The second (`fetchPage`) drops `sustaining_effect`, keeps `amplifier`, its commit item becomes `{ "type": "commit", "ref": "e4f5a6b", "role": "introduced", "note": "wrote fetchPage without a timeout" }`, its `confidence` is `"medium"` with rationale `"The call has no timeout on the default path; the upstream's stall behaviour was not read"`, and it gains:

```json
      "preconditions": [
        { "setting": "SYNC_REQUEST_TIMEOUT_MS", "default": "0 (no timeout)",
          "default_ref": "src/sync/config.ts:12", "needs": "default",
          "documented": "yes", "doc_ref": "docs/configuration.md:40" }
      ],
```

  The sentence introducing the example becomes: "This example shows two findings: one on the default path with no preconditions, and one that rests on a registered default and leaves `sustaining_effect` out because nothing sustains it."

In `skills/thunderstruck-scan/SKILL.md` step 4, the repair text's "each with all eleven keys from your system prompt (`sustaining_effect` may be `null` but must be present)" becomes "each with all ten required keys from your system prompt (`preconditions` may be `[]` but must be present; leave `amplifier` and `sustaining_effect` out when there is nothing to state), and every commit item with its `role`". Step 6's last paragraph adds: "State each finding's check status; until a check runs, every finding is `unchecked`."

In `scripts/bundle.py`'s `write_catalog_brief`, the metastability paragraph's last sentence becomes: "If nothing sustains it, leave `sustaining_effect` out: the report shows it as not stated, never as a sentence nobody wrote." (The catalog brief is not part of any bundle body or `bundle_hash`.)

In `skills/thunderstruck-verify/SKILL.md`, where it describes building the test from the finding, add: "Set every precondition with `needs: changed` to its stated `value` in the test, and leave the others at their defaults: a gated finding's test that passes on defaults proves nothing."

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_investigator_contract.py tests/test_docs_in_sync.py -q`, then the full suite.
Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add agents/thunderstruck-investigator.md skills/thunderstruck-scan/SKILL.md skills/thunderstruck-verify/SKILL.md scripts/bundle.py tests/test_investigator_contract.py
git commit -m "Investigator: preconditions, commit roles, confidence as a claim (#56)"
```

### Task 8: A gated finding in the fixture, and the samples

**Satisfies:** AC-10 (the sample report describes the new fields), AC-5 (the sample shows a gated finding last, marked).

**Files:**
- Modify: `tests/fixtures/build_fixture.py` (`IGNORES_RETRY_AFTER`)
- Modify: `scripts/gen_sample_report.py` (canned findings, precondition building)
- Modify: `tests/test_docs_in_sync.py`
- Regenerate: `examples/sample-report.md`, `examples/sample-report.html`

- [ ] **Step 1: Write the failing tests.** In `tests/test_docs_in_sync.py`, `test_sample_report_is_a_real_artefact` expects `"thunderstruck.report/v2"`, and add:

```python
def test_sample_report_shows_check_status_preconditions_and_history():
    sample = (ROOT / "examples" / "sample-report.md").read_text()
    assert "· unchecked ·" in sample and "(claimed high)" in sample
    assert "That is all validation proves." in sample
    findings = sample.split("## Findings", 1)[1].split("\n## ", 1)[0]
    headings = [l for l in findings.splitlines() if l.startswith("### FR-")]
    gated = [n for n, l in enumerate(findings.split("\n### ")[1:]) if "needs a non-default setting" in l]
    assert gated == [len(headings) - 1], "the gated finding is listed last, and only it is marked"
    assert "`API_RETRY_ON_429` set to `true`" in sample
    assert "_not stated_" in sample and "**History** — a signal" in sample
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_docs_in_sync.py -q -k sample`
Expected: FAIL (the committed sample is still `report/v1` with no check status).

- [ ] **Step 3: Write the implementation.**

In `tests/fixtures/build_fixture.py`, `IGNORES_RETRY_AFTER` becomes:

```python
IGNORES_RETRY_AFTER = '''\
const RETRY_ON_429 = process.env.API_RETRY_ON_429 === "true";

export async function callApi(path: string): Promise<Response> {
  const res = await fetch(`https://api.example.com${path}`, {
    signal: AbortSignal.timeout(10_000),
  });

  if (RETRY_ON_429 && res.status === 429) {
    // Back off and try again.
    await new Promise(resolve => setTimeout(resolve, 5000));
    return callApi(path);
  }

  return res;
}
'''
```

In `scripts/gen_sample_report.py`:

- The `client/api.ts` canned finding: `"anchor": "res.status === 429"` stays (it still matches the `if` line); `trigger_condition` becomes `"API_RETRY_ON_429 is set to true and the API returns 429 with Retry-After longer than 5 seconds"`; add

```python
        "preconditions": [{"setting": "API_RETRY_ON_429", "default": "false (unset)",
                           "anchor": "const RETRY_ON_429", "needs": "changed", "value": "true",
                           "documented": "no"}],
```

- The `sync/scheduler.ts` and `util/format.ts` canned findings drop their `"sustaining_effect": None` lines.
- When building each item, `"preconditions"` joins the excluded keys of the `item = {k: v …}` comprehension, and:

```python
                item["preconditions"] = [
                    {**{k: v for k, v in p.items() if k != "anchor"},
                     "default_ref": f"{hs['file']}:{_line_of(repo, hs['file'], p['anchor'])}"}
                    for p in spec.get("preconditions", [])]
```

  (replacing Task 2's `item["preconditions"] = []`).

Then regenerate:

```bash
uv run scripts/gen_sample_report.py
uv run scripts/gen_sample_report.py --check; echo "exit=$?"
```

Read the regenerated `examples/sample-report.md` in full before committing: five findings, all `unchecked`; the three `high` claims shown as `medium` with "(claimed high)"; the api.ts finding last with "needs a non-default setting"; *not stated* under the scheduler and format findings' Sustaining effect; a History block under every finding with a cited commit.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_docs_in_sync.py tests/test_sample_report.py tests/test_pipeline.py -q`, then the full suite.
Expected: PASS (`test_pipeline`'s S03 lead on `client/api.ts` still fires), `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/build_fixture.py scripts/gen_sample_report.py tests/test_docs_in_sync.py examples/sample-report.md examples/sample-report.html
git commit -m "Sample: a gated finding, check status, preconditions and history (#56)"
```

### Task 9: Confidence agreement on the benchmark

**Satisfies:** AC-9.

**Precondition:** Task 0 confirmed #55 is merged. If `scripts/benchmark.py` or `docs/calibration/correctness/celery/labels.json` is nevertheless missing here, stop the run: replace `agent:in-progress` with `agent:blocked`, comment "Blocked at Task 9: #55 is not merged", open no PR. Do not skip this task and continue to Task 10.

**Files:**
- Modify: `scripts/benchmark.py` (`run_from_report`)
- Create: `docs/calibration/correctness/celery/runs/checked-confidence.json`
- Test: `tests/test_checked_confidence.py`

**Interfaces:**
- Consumes: from #55's `benchmark`: `RUN_SCHEMA`, `load_label_sets`, `load_run`, `run_from_report`, `split_run`, `score_confidence`; `c.effective_confidence`.
- Produces: `test_checked_confidence.checked_confidence_run() -> dict`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 9 -----------------------------------------------------------------
CELERY = ROOT / "docs" / "calibration" / "correctness" / "celery"
AFTER = CELERY / "runs" / "checked-confidence.json"


def checked_confidence_run() -> dict:
    """Every frozen Celery finding under the new rule, all unchecked."""
    import benchmark as b
    frozen = json.loads((CELERY / "scan" / "report.json").read_text())
    return {"schema": b.RUN_SCHEMA, "commit": frozen["repo"]["head"],
            "produced_by": {"stage": "confidence", "model": None,
                            "source": "scan/report.json via _common.effective_confidence, "
                                      "every finding unchecked"},
            "findings": {f["key"]: {"confidence": c.effective_confidence(f["confidence"], "unchecked")}
                         for f in sorted(frozen["findings"], key=lambda f: f["key"])}}


def test_the_after_run_is_derived_from_the_frozen_scan():
    assert json.loads(AFTER.read_text()) == checked_confidence_run()


def test_confidence_agreement_before_and_after():
    import benchmark as b
    celery = b.load_label_sets([CELERY / "labels.json"])[0]

    def score(run):
        return b.score_confidence(b.split_run(run, celery)[0], celery)

    before = score(b.run_from_report(CELERY / "scan" / "report.json"))
    after = score(b.load_run(AFTER))
    assert before["counts"] == {"exact": 8, "within one": 20, "over": 6, "under": 7}
    assert len(before["high_above_deserved"]) == 2
    assert after["counts"] == {"exact": 8, "within one": 21, "over": 5, "under": 8}
    assert after["high_above_deserved"] == []


def test_the_report_adapter_reads_preconditions(tmp_path):
    import benchmark as b
    doc = {"repo": {"head": "a" * 40}, "findings": [
        {"key": "k1", "confidence": "medium",
         "preconditions": [{"setting": "S", "default": "10", "needs": "default"}]},
        {"key": "k2", "confidence": "low"}]}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(doc))
    run = b.run_from_report(path)
    assert run["findings"]["k1"]["preconditions"] == [{"setting": "S", "default": "10"}]
    assert "preconditions" not in run["findings"]["k2"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_checked_confidence.py -q -k "after_run or agreement or adapter"`
Expected: FAIL (`FileNotFoundError` for the run file; the adapter drops preconditions).

- [ ] **Step 3: Write the implementation.** In `scripts/benchmark.py`'s `run_from_report`, the loop becomes:

```python
    for f in report.get("findings") or []:
        if f.get("key"):
            record = {"confidence": f.get("confidence")}
            if isinstance(f.get("preconditions"), list):
                record["preconditions"] = [{"setting": p.get("setting"), "default": p.get("default")}
                                           for p in f["preconditions"] if isinstance(p, dict)]
            findings[f["key"]] = record
```

Write the run file from the same function the test uses:

```bash
mkdir -p docs/calibration/correctness/celery/runs
uv run --with pytest --with pyyaml --with lizard python -c "
import json, sys; sys.path[:0] = ['scripts', 'tests']
import test_checked_confidence as t
open('docs/calibration/correctness/celery/runs/checked-confidence.json', 'w').write(
    json.dumps(t.checked_confidence_run(), indent=2) + '\n')"
```

- [ ] **Step 4: Run the tests to verify they pass** (Step 2's command, then the full suite). Expected: PASS, `exit=0`. Then record the figures for the PR description:

```bash
uv run scripts/benchmark.py --report docs/calibration/correctness/celery/scan/report.json
uv run scripts/benchmark.py --run docs/calibration/correctness/celery/runs/checked-confidence.json
```

Expected: confidence 8/21 exact before and after; `high` above deserved FR-001, FR-003 before and none after; each line with `celery/celery@508c112`, `n=21` and `labels: 21 claude-fable-5-1`. Paste both outputs into the PR.

- [ ] **Step 5: Commit**

```bash
git add scripts/benchmark.py docs/calibration/correctness/celery/runs/checked-confidence.json tests/test_checked_confidence.py
git commit -m "Benchmark: confidence before and after checked confidence (#56)"
```

### Task 10: Documentation and release

**Satisfies:** AC-10.

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `skills/thunderstruck-scan/references/report-format.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`

- [ ] **Step 1: README.** In "Findings are falsifiable, and checked", replace the "`high` confidence requires corroborating history" and "`sustaining_effect` is mandatory" bullets with:

```markdown
- **Confidence says whether the claim was checked.** Only a finding whose
  claim survived a check can be `high`; until one has, a finding is
  `unchecked` and at most `medium`, and the report says what the investigator
  claimed. Fix history does not count: it is shown per cited commit (its
  class, its stated role, and whether it wrote a cited line) as a signal of
  how fragile the code is.
- **Preconditions are stated.** Each finding lists the settings it needs
  changed or relies on, with the default and where it is registered.
  Findings that happen on default settings come first; the rest are marked.
- **Nothing is filled in.** `amplifier` and `sustaining_effect` are given
  only when the code shows them; otherwise the report says *not stated*.
- **Validation proves the citations, not the claim.** A commit cited as
  having introduced the code must have written a cited line, per `git blame`.
```

  Update the guardrail example to the new lines (`confidence: medium; check status: unchecked.` and `It happens on default settings.`).

- [ ] **Step 2: CLAUDE.md.** Replace the "**`high` needs a corroborating commit.**" paragraph with:

```markdown
**Confidence is capped by check status, never by history.** A finding's
`confidence` in its findings file is the investigator's claim. `report.py`
reports `_common.effective_confidence(claim, check status)`: only `upheld`
can be `high`, everything else is at most `medium`, and `narrowed` drops one
level. Until #37 lands every finding is `unchecked`. `finding_shape.shape()` strips
`check`, `history` and `confidence_claimed` from model output, so a model
cannot raise its own finding, and `validate.py` never overwrites an existing
`check`. A cited commit's class (`_common.classify_commit`) and whether it
wrote a cited line are reported as `history` and feed nothing. A commit cited
with `role: introduced` must have written a cited line per `git blame`.
Findings whose `preconditions` need a setting changed (`_common.finding_gate`)
are listed after default-path findings and marked. Tightening a validator
rule means bumping `VALIDATION_RULES`.
```

- [ ] **Step 3: report-format.md.** The tree line reads `thunderstruck.report/v2`. The finding contract's `high` and `sustaining_effect` bullets are replaced by: `preconditions` required (may be `[]`) with its keys and rules; commit `role` with the `introduced` rule; `amplifier`/`sustaining_effect` optional, never empty; `confidence` is a claim, reported through the check-status ceiling. A new section "Check status, preconditions and history" lists §6.2's per-finding fields, `counts.check_status` and `counts.gate`, §6.3's `index.json` additions, and names the keys reserved for #37 (`check.by`, `check.reason`, `check.holds`, `check.refuted_claims`, `check.evidence`, `check.model`, `check.dependency_versions`, `check.reused_from`, `check.duplicate_of`, `check.confirmations`; and #37's extension of `finding_gate` to a narrowed verdict naming a missing setting) and #57 (`preconditions[].confirmation`, gate `unconfirmed_default`, placed in `GATES` by #57). The "Sections of `report.md` in `report.json`" intro notes that `run_warnings` now ends with check-status warnings, and that v2 changed `confidence`'s meaning.

- [ ] **Step 4: Version and CHANGELOG.** Bump the minor version in all four places to `<version>`, the next minor above `main`'s at the time (read it from `pyproject.toml` on `origin/main`; e.g. `0.9.3` becomes `0.10.0`), and add, with that version in the heading:

```markdown
## <version>

Confidence that means the claim was checked (#56).

### Changed

- **Reported confidence is capped by check status.** Only a finding whose claim was checked and held can be `high`; an `unchecked`, `narrowed` or `inconclusive` finding is at most `medium`, and `narrowed` drops one level. Until verification lands (#37) every finding is `unchecked`. Fix history no longer affects confidence anywhere.
- **`report.json` is `thunderstruck.report/v2`.** `confidence` is the reported confidence; `confidence_claimed` is the investigator's. `amplifier` and `sustaining_effect` may be absent.
- **Findings that need a non-default setting are listed after default-path findings**, and marked.
- **`amplifier` and `sustaining_effect` are optional.** An absent one is shown as *not stated*.
- **Validation rules version 4.** Findings cached from earlier versions are investigated again on the next scan.

### Added

- **Check status** on every finding: `unchecked`, `upheld`, `narrowed`, `inconclusive` or `refuted`, in `report.md`, `report.json`, `index.json`, the HTML report and the guardrail.
- **Preconditions** per finding: the setting, its default, where the default is registered (a resolved reference), whether the failure needs it changed or rests on it, and whether the docs describe the behaviour.
- **History** per finding: each cited commit's class, its stated role, and whether it wrote a cited line. A commit cited as having introduced the code must have written a cited line.
- On the Celery benchmark (#55): 0 findings rated `high` above their deserved confidence (2 before); exact agreement 8 of 21 before and after.
```

- [ ] **Step 5: Run the full suite and the generated-file checks**

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
uv run scripts/gen_catalog_docs.py --check; echo "exit=$?"
uv run scripts/gen_sample_report.py --check; echo "exit=$?"
claude plugin validate . --strict; echo "exit=$?"
claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck && claude plugin list
```

Expected: every `exit=0`; `test_versions_agree` passes; `claude plugin list` shows thunderstruck `enabled`.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md skills/thunderstruck-scan/references/report-format.md CHANGELOG.md .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml
git commit -m "Checked confidence: docs and release note (#56)"
```

## Acceptance criteria coverage

| AC | Tasks |
|---|---|
| AC-1 | 1 (the rule), 2 (the fix gate removed), 3 (every output reads the rule), 7 (no instruction ties confidence to a fix) |
| AC-2 | 1, 3 (json, index), 4 (md), 5 (HTML), 6 (guardrail) |
| AC-3 | 2 (`role`, `introduced`, `history`), 3, 4, 5, 6 (rendered) |
| AC-4 | 2 (validated, resolved), 3 (linked), 4, 5, 6 (rendered) |
| AC-5 | 3 (order), 4 and 5 (marked), 8 (in the sample) |
| AC-6 | 2 (optional, never filler), 4 and 5 (*not stated*), 7 (instructions) |
| AC-7 | 4 (`report.md`), 5 (HTML) |
| AC-8 | 2 (rules version 4, cached findings re-investigated), 3 (confidence derived, never stored), 6 (older index capped) |
| AC-9 | 9 |
| AC-10 | 7 (investigator), 8 (sample), 10 (README, CLAUDE.md, version, checks) |
