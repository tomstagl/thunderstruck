# Confirmed Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every default a finding relies on carries `confirmed` or `unconfirmed` with a reason; a default stated at a fallback read of its setting is caught mechanically; no finding resting on an unconfirmed default is reported `upheld`; and nothing in a scan ever runs, imports or builds the scanned project.

**Architecture:** A catalog section (`setting_reads`) and `_common.reads_with_fallback` recognise a fallback read. `validate.py` applies it to every precondition's `default_ref` on every run and writes a mechanical `confirmation`. The skeptic (#37) returns `confirmations`; `verify.settle` resolves them, derives each confirmation with the one rule `_common.confirm`, and turns an `upheld` resting on an unconfirmed default into `inconclusive`. `report.py` derives confirmations again from stored facts, gates with the third gate `unconfirmed_default`, and renders md · json · index; the HTML report and the guardrail render what those carry.

**Tech Stack:** Python 3.11+ (stdlib; pyyaml where scripts already use it; `packaging` via #37's `deps.py`), `uv`, pytest, the vanilla-JS HTML template, the plugin's skeptic agent.

**Spec:** `docs/superpowers/specs/2026-10-04-confirmed-defaults-design.md` (§n below refers to it). Requirements AC-1…AC-8 and the product decisions are in GitHub issue #57, part of #54.

**Prerequisites, checked in Task 0, which blocks until they hold:** #5 (`scripts/finding_shape.py` with the owned keys and `FINDING_SCHEMA_VERSION`, the capture hook), #56 (`preconditions`, `check_ref`, `finding_gate`, `GATES`, `GATE_MARKERS`, `report.json` v2), #37 (`verify.py` with `settle`, `VERDICT_KEYS`, `claim_hash`, `cited_files`, `export_run`; `deps.py`; `agents/thunderstruck-skeptic.md`; the `validated_repo` test fixtures) and #55 (`scripts/benchmark.py`, the Celery `labels.json`) are merged on `main`.

**Who builds what.** Tasks 0–14 are built by the ticket agent (or anyone) on the branch. Task 15 is a measurement that needs the maintainer: a Claude Code session with the plugin installed and a Celery checkout. After Task 14 the build stops with one defined outcome, **ready for maintainer measurement**:

- the PR is opened as a **draft**, and its description starts with "Do not merge before Task 15 (maintainer measurement on #55, spec §13.2)"; it does not say "Close #57" or any other closing keyword;
- a comment on #57 says "Ready for maintainer measurement: Task 15 of the plan" and links the draft PR;
- #57 stays open; the agent does not mark the PR ready.

The maintainer runs Task 15 on the same branch, commits its results there, and marks the PR ready only when AC-6 holds.

**Branch:** named by whoever builds it (the ticket agent names its own). One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with packaging --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

New tests go in `tests/test_confirmed_defaults.py` (every task but Task 11) and `tests/test_no_execution.py` (Task 11), appended task by task under a `# --- Task N` comment. Run one task's tests with `uv run --with pytest --with pyyaml --with lizard --with packaging pytest tests/test_confirmed_defaults.py -q -k "<name>"`.

## Global Constraints

- One confirmation rule (`_common.confirm`), one reliance rule (`_common.unconfirmed_defaults`), one derivation (`_common.with_confirmations`), one gate rule (`_common.finding_gate`). Nothing else decides any of them (§1).
- `confirmed` only with a check's item whose `default_ref` resolves, names the setting (§4.3) and is not a fallback read, and whose `found` is `same` (§3.2). The validator alone never confirms.
- Vocabularies exactly as the spec: `state` ∈ `confirmed unconfirmed`; `basis` ∈ `registered contradicted call_site_fallback not_found unresolved not_checked`; `found` ∈ `same different not_found`; `GATES == ("none", "unconfirmed_default", "non_default_setting")`; marker "relies on an unconfirmed default"; verdict key `confirmations`; item keys `setting claim stated_ref found default default_ref reason`.
- `preconditions[].confirmation` is never taken from a model: `finding_shape.py`'s owned-field strip removes it (for `save_finding.py` and the capture hook alike), `validate.py` overwrites it, `report.py` re-derives it (§5.3, §9).
- `verify.settle` refuses `upheld` on an unconfirmed default on every path, reuse included (§7.1).
- `VALIDATION_RULES` does not change (Decision 12). `REPORT_SCHEMA_VERSION` stays `thunderstruck.report/v2`; `index.json` stays `thunderstruck.index/v1`.
- No script starts a process other than `git` and the approved context command (which may be a script committed in the scanned repository, approved by hash, #1); nothing else imports, executes or builds anything from the scanned repository or its dependencies; hooks run `python3 -S` (§11, AC-5).
- Every model-written value (a confirmation's `setting`, `default`, `default_ref`, `stated_ref`, `claim`, `reason`) is inert in every output; dependency refs are never links.
- `guardrail.py` stays stdlib-only, always exits 0, states facts, under 100 ms median.
- Bundles stay byte-identical; briefs and `checks/plan.json` stay deterministic.
- The examples are regenerated once, in Task 12. From Task 5 (which changes the fixture and the canned verdicts) to Task 12 `gen_sample_report.py --check` may report them stale; Task 12 ends it. The generator itself must keep running from Task 5 on (`expect` on canned verdicts, Task 5).
- Which unconfirmed defaults gate the finding is an open product question (ticket; spec §8, §19 q4). Build the spec's current choice (every unconfirmed `needs: default` default); do not change it without the maintainer's answer.
- Public repository: no organisation-specific names, hosts, credentials or local paths in any file.

## Review Focus

1. **A setting name that is prose or carries regex metacharacters** (`"max_retries (database backend)"`, `"a.b*c"`, `"x)("`). Never a fallback read, never an exception. Pinned in Task 2.
2. **A skeptic that "confirms" by citing the investigator's own fallback line with `found: same`** (Spike 2's refuter that was wrong). Basis `call_site_fallback`, state `unconfirmed`, and an `upheld` verdict settles `inconclusive`. Pinned in Tasks 5 and 6.
3. **`--no-verify` after a verified scan** whose findings files still carry skeptic-confirmed preconditions. The report shows only mechanical confirmations (`call_site_fallback` / `not_checked`) and no `registered`. Pinned in Task 7.
4. **A ledger entry written before this ticket, reused as `upheld`.** It settles `inconclusive` because its defaults derive `not_checked`. Pinned in Task 5.
5. **A `default_ref` into a file that is not UTF-8, or in a language with no `setting_reads` entry** (`.go`, a binary-ish `.properties`). `call_site` is `null`, basis `not_checked`, validation passes. Pinned in Task 3.

---

### Task 0: Prerequisites

**Satisfies:** none on its own; every later task assumes it.

- [ ] **Step 1: Check that #5, #56, #37 and #55 are merged.** On a branch from current `origin/main`:

```bash
grep -n "def finding_gate\|^GATES\|^GATE_MARKERS" scripts/_common.py
grep -n "def check_ref" scripts/validate.py
grep -n "^VERDICT_KEYS\|^def settle\|^def claim_hash\|^def cited_files\|^def export_run\|^def render_brief\|^class Resolver" scripts/verify.py
grep -n "^def resolve_dependency_ref\|^def snapshot_dir\|^DEP_REF" scripts/deps.py
grep -n "^def score_defaults" scripts/benchmark.py
test -f agents/thunderstruck-skeptic.md && test -f docs/calibration/correctness/celery/labels.json && echo ok
grep -n "^FINDING_SCHEMA_VERSION" scripts/finding_shape.py
grep -n "^OWNED_FINDING_KEYS" scripts/finding_shape.py
grep -n "^def shape" scripts/finding_shape.py
```

Expected: every grep prints a line, and `ok`. **This task blocks.** If any line is missing, #5, #56, #37 or #55 is not merged: stop, start no other task, and report the ticket blocked with the missing names. The plan builds on those exact names.

- [ ] **Step 2: Run the full suite** (the command above). Expected: `exit=0`. No commit.

---

### Task 1: The vocabulary, the confirmation rule and the third gate

**Satisfies:** AC-1 (two states and a reason), AC-3 (what "relies on an unconfirmed default" means), AC-8 (the order).

**Files:**
- Modify: `scripts/_common.py` (after #56's `finding_gate`; `GATES`, `GATE_MARKERS`, `finding_gate`)
- Modify: `tests/test_checked_confidence.py` (#56's `test_finding_gate` and `test_vocabularies_are_the_spec_spelling` expectations)
- Create: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: #56's `GATES`, `GATE_MARKERS`, `finding_gate`; #37's extension of `finding_gate`.
- Produces, in `_common`: `CONFIRMATION_STATES`, `CONFIRMATION_BASES`, `CONFIRMATION_FOUND`, `CONFIRMATION_REASONS: dict[str, str]`; `confirm(call_site: bool | None, item: dict | None = None) -> dict` (`{"state", "basis", "reason"}`); `confirmation_state(conf) -> str`; `with_confirmations(finding: dict, items: list[dict] | None) -> dict` (a shallow copy whose `preconditions[j].confirmation` and `check.confirmations[k].confirmation` are derived); `unconfirmed_defaults(finding: dict) -> list[dict]`; `GATES == ("none", "unconfirmed_default", "non_default_setting")`; `GATE_MARKERS["unconfirmed_default"]`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_confirmed_defaults.py`:

```python
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
    assert c.GATE_MARKERS["unconfirmed_default"] == "relies on an unconfirmed default"


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
    ({"preconditions": [_pre()]}, "unconfirmed_default"),
    ({"preconditions": [{"setting": "s", "default": "1", "needs": "default"}]}, "unconfirmed_default"),
    ({"preconditions": [_pre(), _pre("changed", setting="t")]}, "non_default_setting"),
    ({"preconditions": [], "check": {"confirmations": [
        {"setting": "u", "precondition": None, "confirmation": {"state": "unconfirmed"}}]}}, "unconfirmed_default"),
])
def test_finding_gate_has_three_gates_in_precedence(finding, gate):
    assert c.finding_gate(finding) == gate
```

- [ ] **Step 2: Run them to verify they fail.** `uv run --with pytest --with pyyaml --with lizard --with packaging pytest tests/test_confirmed_defaults.py -q`. Expected: FAIL, `AttributeError: module '_common' has no attribute 'confirm'`.

- [ ] **Step 3: Write the implementation.** In `scripts/_common.py`, change #56's two constants:

```python
# Report order: default-path findings first, then findings resting on an
# unconfirmed default (#57), then findings that need a non-default setting.
GATES = ("none", "unconfirmed_default", "non_default_setting")
GATE_MARKERS = {"unconfirmed_default": "relies on an unconfirmed default",
                "non_default_setting": "needs a non-default setting"}
```

In `finding_gate`, replace the final `return "none"` (after #56's `needs: changed` test and #37's narrowed-setting test) with:

```python
    return "unconfirmed_default" if unconfirmed_defaults(finding) else "none"
```

and directly after `finding_gate` add:

```python
# --------------------------------------------------------------------------
# confirmed defaults (spec 2026-10-04-confirmed-defaults-design.md)
# --------------------------------------------------------------------------

CONFIRMATION_STATES = ("confirmed", "unconfirmed")
CONFIRMATION_BASES = ("registered", "contradicted", "call_site_fallback",
                      "not_found", "unresolved", "not_checked")
CONFIRMATION_FOUND = ("same", "different", "not_found")
CONFIRMATION_REASONS = {
    "registered": "a check found this default registered, and it agrees",
    "contradicted": "a check found a different default registered",
    "call_site_fallback": ("the default is stated where the setting is read, as a fallback; "
                           "the value in effect may be registered elsewhere"),
    "not_found": "a check found no place that registers this default",
    "unresolved": "the place a check gave for this default does not resolve",
    "not_checked": "no check looked for where this default is registered",
}


def confirm(call_site, item: dict | None = None) -> dict:
    """The one confirmation rule (spec §3.2). `call_site` is the fallback-read
    rule applied to the stated location; `item` is a check's resolved item."""
    if not isinstance(item, dict):
        basis = "call_site_fallback" if call_site is True else "not_checked"
    elif item.get("found") == "not_found":
        basis = "not_found"
    elif item.get("default_ref_error") or item.get("default_names_setting") is False:
        basis = "unresolved"
    elif item.get("default_call_site") is True:
        basis = "call_site_fallback"
    elif item.get("found") == "different":
        basis = "contradicted"
    elif item.get("found") == "same":
        basis = "registered"
    else:
        basis = "not_checked"
    return {"state": "confirmed" if basis == "registered" else "unconfirmed",
            "basis": basis, "reason": CONFIRMATION_REASONS[basis]}


def confirmation_state(conf) -> str:
    state = conf.get("state") if isinstance(conf, dict) else None
    return state if state in CONFIRMATION_STATES else "unconfirmed"


def with_confirmations(finding: dict, items: list[dict] | None) -> dict:
    """A copy of the finding with every confirmation derived from stored facts:
    each precondition's validator `call_site`, and the check's items (None when
    no check counts for this scan). Never trusts a stored state."""
    out = dict(finding)
    items = [it for it in items or [] if isinstance(it, dict)]
    by_index = {it["precondition"]: it for it in items if isinstance(it.get("precondition"), int)}
    pres = []
    for j, p in enumerate(finding.get("preconditions") or []):
        if not isinstance(p, dict):
            pres.append(p)
            continue
        stored = p.get("confirmation") if isinstance(p.get("confirmation"), dict) else {}
        call_site = stored.get("call_site")
        it = by_index.get(j)
        pres.append({**p, "confirmation": {**confirm(call_site, it), "call_site": call_site,
                                           "by": "skeptic" if it else "validator"}})
    out["preconditions"] = pres
    check = finding.get("check") if isinstance(finding.get("check"), dict) else None
    if check is not None or items:
        derived = []
        for it in items:
            j = it.get("precondition")
            conf = (pres[j]["confirmation"] if isinstance(j, int) and j < len(pres)
                    and isinstance(pres[j], dict) else confirm(it.get("stated_call_site"), it))
            derived.append({**it, "confirmation": {k: conf[k] for k in ("state", "basis", "reason")}})
        out["check"] = {**(check or {}), "confirmations": derived}
    return out


def unconfirmed_defaults(finding: dict) -> list[dict]:
    """The defaults a finding relies on that no check confirmed: needs-default
    preconditions and the check's unlisted items. The one reliance rule."""
    out = [p for p in finding.get("preconditions") or []
           if isinstance(p, dict) and p.get("needs") == "default"
           and confirmation_state(p.get("confirmation")) != "confirmed"]
    check = finding.get("check") if isinstance(finding.get("check"), dict) else {}
    out += [it for it in check.get("confirmations") or []
            if isinstance(it, dict) and it.get("precondition") is None
            and confirmation_state(it.get("confirmation")) != "confirmed"]
    return out
```

In `tests/test_checked_confidence.py`: in `test_finding_gate`, the row `([{"needs": "default"}, {"needs": "default"}], "none")` becomes `"unconfirmed_default"` (an item with no confirmation is unconfirmed), and in `test_vocabularies_are_the_spec_spelling` `c.GATES` is `("none", "unconfirmed_default", "non_default_setting")`.

- [ ] **Step 4: Run the tests and the full suite.** Expected: PASS, `exit=0`. Report-order tests from #56 and #37 that build findings with `needs: default` items and expect them first may now expect them after default-path findings; where a test exists to pin #56's order of a default-path finding, give its items `"confirmation": {"state": "confirmed"}` rather than changing the expected order.

- [ ] **Step 5: Commit**

```bash
git add scripts/_common.py tests/test_confirmed_defaults.py tests/test_checked_confidence.py tests/
git commit -m "Confirmed defaults: the confirmation rule and the third gate (#57)"
```

---

### Task 2: The fallback-read rule

**Satisfies:** AC-2 (the call-site fallback is recognised mechanically).

**Files:**
- Modify: `catalog/stability.yaml` (new top-level `setting_reads`, after `aliases`)
- Modify: `scripts/_common.py` (`reads_with_fallback`)
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: `c.strip_comments(text, lang)`, `c.detector_language(catalog, lang)`, `c.load_catalog()`.
- Produces: `c.reads_with_fallback(text: str, setting: str, lang: str | None, catalog: dict) -> bool | None` (`None` when the language has no `setting_reads` entry); `c.names_setting(text: str, setting: str, lang: str | None) -> bool` (spec §4.3); catalog key `setting_reads: {language: [pattern, …]}`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 2 -----------------------------------------------------------------
CATALOG = c.load_catalog()

# (language, text, setting, expected). Positives first per language, then the
# negative controls of spec §4.2.
READS = [
    ("python", "        self.always_retry = conf.get('result_backend_always_retry', True)\n",
     "result_backend_always_retry", True),
    ("python", "        self.max_retries = conf.get('result_backend_max_retries', 3)\n",
     "result_backend_max_retries", True),
    ("python", "x = conf.get(\n    'result_backend_always_retry',\n    True)\n", "result_backend_always_retry", True),
    ("python", "max_retries = kwargs.pop('max_retries', 3)\n", "max_retries", True),
    ("python", "t = getattr(settings, 'HTTP_TIMEOUT', 30)\n", "HTTP_TIMEOUT", True),
    ("python", "t = os.getenv('HTTP_TIMEOUT', '30')\n", "HTTP_TIMEOUT", True),
    ("python", "t = os.environ.get(\"HTTP_TIMEOUT\", \"30\")\n", "http_timeout", True),
    ("python", "    backend_always_retry=Option(False, type='bool'),\n", "backend_always_retry", False),
    ("python", "DEFAULTS = {'max_retries': 3}\n", "max_retries", False),
    ("python", "x = conf.result_backend_always_retry\n", "result_backend_always_retry", False),
    ("python", "x = conf.get('result_backend_always_retry')\n", "result_backend_always_retry", False),
    ("python", "x = conf.get('other_setting', True)\n", "result_backend_always_retry", False),
    ("python", "# x = conf.get('result_backend_always_retry', True)\n", "result_backend_always_retry", False),
    ("python", "parser.add_argument('--timeout', default=30)\n", "timeout", False),
    ("typescript", "const PAGE_SIZE = get<number>(\"sync.pageSize\", 100);\n", "sync.pageSize", True),
    ("typescript", "const n = config.get('sync.pageSize', 100);\n", "sync.pageSize", True),
    ("typescript", "const t = process.env.TIMEOUT_MS ?? 30000;\n", "TIMEOUT_MS", True),
    ("typescript", "const t = process.env[\"TIMEOUT_MS\"] || \"30000\";\n", "TIMEOUT_MS", True),
    ("typescript", "const REGISTERED = { \"sync.pageSize\": 500 };\n", "sync.pageSize", False),
    ("typescript", "const on = process.env.API_RETRY_ON_429 === \"true\";\n", "API_RETRY_ON_429", False),
    ("typescript", "// const n = config.get('sync.pageSize', 100);\n", "sync.pageSize", False),
    ("java", "String t = props.getProperty(\"http.timeout\", \"30\");\n", "http.timeout", True),
    ("java", "@Value(\"${http.timeout:30}\") private int timeout;\n", "http.timeout", True),
    ("java", "int n = map.getOrDefault(\"pool.size\", 10);\n", "pool.size", True),
    ("java", "private Duration timeout = Duration.ofSeconds(30);\n", "timeout", False),
    ("java", "String t = System.getenv(\"HTTP_TIMEOUT\");\n", "HTTP_TIMEOUT", False),
    ("yaml", "timeout: ${http.timeout:30}\n", "http.timeout", True),
    ("yaml", "http:\n  timeout: 30\n", "http.timeout", False),
    ("properties", "client.timeout=${http.timeout:30}\n", "http.timeout", True),
    ("properties", "http.timeout=30\n", "http.timeout", False),
]


@pytest.mark.parametrize("lang, text, setting, expected", READS)
def test_fallback_reads(lang, text, setting, expected):
    assert c.reads_with_fallback(text, setting, lang, CATALOG) is expected


def test_javascript_uses_the_typescript_patterns():
    assert c.reads_with_fallback("const t = process.env.T ?? 5;\n", "T", "javascript", CATALOG) is True


def test_every_language_with_setting_reads_has_both_polarities():
    langs = set(CATALOG["setting_reads"])
    for lang in langs:
        polarities = {exp for lg, _, _, exp in READS if lg == lang}
        assert polarities == {True, False}, f"{lang} needs a positive and a negative case"


@pytest.mark.parametrize("setting", ["max_retries (database backend)", "a.b*c", "x)(", "", "   "])
def test_a_name_that_is_prose_or_regex_never_matches_and_never_raises(setting):
    assert c.reads_with_fallback("x = conf.get('a.b*c', 1)\n", setting, "python", CATALOG) in (False,)


@pytest.mark.parametrize("text, setting, lang, expected", [
    ("x = conf.get('result_backend_always_retry', True)\n", "result_backend_always_retry", "python", True),
    ("    backend_always_retry=Option(False, type='bool'),\n", "result_backend_always_retry", "python", True),
    ("        socket_connect_timeout=None,\n", "redis_socket_connect_timeout", "python", True),
    ("    retry=Option(False),\n", "result_backend_always_retry", "python", False),  # one segment
    ("TIMEOUT = 30\n", "TIMEOUT", "python", True),
    ("x = 1  # result_backend_always_retry\n", "result_backend_always_retry", "python", False),
    ('  "sync.pageSize": 500,\n', "sync.pageSize", "typescript", True),
    ("const x = 1;\n", "sync.pageSize", "typescript", False),
    ("pool.size=10\n", "pool.size", None, True),
    ("anything\n", "max_retries (database backend)", "python", False),
])
def test_names_setting(text, setting, lang, expected):
    assert c.names_setting(text, setting, lang) is expected


def test_a_language_without_setting_reads_is_unknown():
    assert c.reads_with_fallback("x := os.Getenv(\"X\")\n", "X", "go", CATALOG) is None
    assert c.reads_with_fallback("x\n", "X", None, CATALOG) is None
```

The regex-metacharacter row expects `False` for `"a.b*c"` although the text contains it literally: a name with `*` is not a setting name the patterns accept. Implement that by refusing names outside `[\w.\-:/\[\]@]+`.

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL, `KeyError: 'setting_reads'` / `AttributeError`.

- [ ] **Step 3: Write the implementation.** In `catalog/stability.yaml`, after the `aliases:` block:

```yaml
# Reads of a setting that supply their own fallback (#57). A default stated at
# one of these is unconfirmed: a settings layer may hold another value. Each
# pattern is matched against the cited lines with comments blanked; {setting}
# is replaced by the setting's name, escaped. Matched case-insensitively.
# Every language here needs a positive and a negative case in
# tests/test_confirmed_defaults.py (READS).
setting_reads:
  python:
    - '\.(?:get|pop)\(\s*[''"]{setting}[''"]\s*,'
    - '\bgetattr\(\s*[^,()]+,\s*[''"]{setting}[''"]\s*,'
    - '\bgetenv\(\s*[''"]{setting}[''"]\s*,'
  typescript:
    - '\.?\bget\w*\s*(?:<[^>()]*>)?\(\s*[''"`]{setting}[''"`]\s*,'
    - 'process\.env(?:\.{setting}\b|\[\s*[''"`]{setting}[''"`]\s*\])\s*(?:\?\?|\|\|)'
  java:
    - '\.get\w*\(\s*"{setting}"\s*,'
    - '\$\{{setting}:'
  yaml:
    - '\$\{{setting}:'
  properties:
    - '\$\{{setting}:'
```

(The TypeScript `get` pattern allows a bare `get<number>(…)` as well as `config.get(…)`.) In `scripts/_common.py`, after `unconfirmed_defaults`:

```python
_SETTING_NAME = re.compile(r"[\w.\-:/\[\]@]+")


def names_setting(text: str, setting, lang: str | None) -> bool:
    """Spec §4.3: the text (comments blanked when the language is known) contains
    the setting's name or a `_`/`.`-delimited suffix of it of two or more segments."""
    name = setting.strip() if isinstance(setting, str) else ""
    if not name or not _SETTING_NAME.fullmatch(name):
        return False
    body = (strip_comments(text, lang) if lang else text).casefold()
    parts = re.split(r"[_.]", name.casefold())
    seps = re.findall(r"[_.]", name)
    candidates = {name.casefold()}
    for i in range(1, len(parts) - 1):
        candidates.add("".join(parts[j] + (seps[j] if j < len(seps) else "") for j in range(i, len(parts))))
    return any(cand and cand in body for cand in candidates)


def reads_with_fallback(text: str, setting, lang: str | None, catalog: dict) -> bool | None:
    """True when `text` reads `setting` and supplies its own fallback at that read
    (spec §4). None when the language has no setting_reads patterns."""
    reads = catalog.get("setting_reads") or {}
    if not lang:
        return None
    patterns = reads.get(lang) or reads.get(detector_language(catalog, lang))
    if not patterns:
        return None
    name = setting.strip() if isinstance(setting, str) else ""
    if not name or not _SETTING_NAME.fullmatch(name):
        return False
    body = strip_comments(text, lang)
    escaped = re.escape(name)
    return any(re.search(p.replace("{setting}", escaped), body, re.IGNORECASE | re.MULTILINE)
               for p in patterns)
```

- [ ] **Step 4: Run the tests and the full suite** (including `gen_catalog_docs.py --check`, which must stay clean: the generator renders `patterns` and `tier_c` only). Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add catalog/stability.yaml scripts/_common.py tests/test_confirmed_defaults.py
git commit -m "Confirmed defaults: recognise a default stated at a fallback read (#57)"
```

---

### Task 3: The validator writes the mechanical confirmation

**Satisfies:** AC-1 (every precondition carries a state, in every scan), AC-2 (decided mechanically).

**Files:**
- Modify: `scripts/validate.py` (`PRECONDITION_KEYS`, `Validator.__init__`, new `Validator.fallback_read`, `main`)
- Modify: `scripts/finding_shape.py` (`shape`, which `save_finding.py` and the capture hook both call)
- Modify: `tests/test_checked_confidence.py` (#56's precondition-rule row for `confirmation`)
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: `Validator.check_ref(ref, where, errors, allow_dependency=False)` (#56, #37); `deps.DEP_REF`, `deps.resolve_dependency_ref`, `deps.snapshot_dir` (#37); `c.reads_with_fallback`, `c.confirm` (Tasks 1–2).
- Produces: `Validator.fallback_read(ref, setting, allow_dependency: bool = False) -> bool | None`; `Validator.names_setting(ref, setting, allow_dependency: bool = False) -> bool | None` (spec §4.3; `None` when the ref does not resolve or the file is not text); every precondition of a passing document carries `confirmation = {"state", "basis", "reason", "call_site", "by": "validator"}`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 3 -----------------------------------------------------------------
import validate  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def _tiny_repo(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    for rel, body in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body) if isinstance(body, bytes) else p.write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


CELERYISH = {
    "backends/database.py": (
        "class DatabaseBackend:\n"
        "    def __init__(self, conf):\n"
        "        # We maintain this behavior by default.\n"
        "        self.always_retry = conf.get('result_backend_always_retry', True)\n"
        "        self.max_retries = conf.get('result_backend_max_retries', 3)\n"),
    "app/defaults.py": (
        "NAMESPACES = dict(\n"
        "    backend_always_retry=Option(False, type='bool'),\n"
        "    backend_max_retries=Option(float('inf'), type='float'),\n"
        ")\n"),
    "conf/blob.properties": b"timeout=\xff\xfe\n",
    "cmd/main.go": "package main\n",
}


def _validator(repo: Path) -> "validate.Validator":
    return validate.Validator(repo, {"hotspots": []}, c.load_catalog())


def test_fallback_read_on_repository_refs(tmp_path):
    v = _validator(_tiny_repo(tmp_path, CELERYISH))
    assert v.fallback_read("backends/database.py:4", "result_backend_always_retry") is True
    assert v.fallback_read("backends/database.py:4-5", "result_backend_max_retries") is True
    assert v.fallback_read("app/defaults.py:2", "result_backend_always_retry") is False
    assert v.fallback_read("conf/blob.properties:1", "timeout") is None      # not UTF-8
    assert v.fallback_read("cmd/main.go:1", "X") is None                     # no setting_reads for go
    assert v.fallback_read("backends/database.py:99", "x") is None           # does not resolve


def test_validate_writes_a_mechanical_confirmation_and_overwrites_a_claimed_one(validated_repo, validated_env):
    out = validated_repo / ".thunderstruck"
    path = next(p for p in sorted((out / "findings").glob("*.json"))
                if any(f.get("preconditions") for f in json.loads(p.read_text())["findings"]))
    doc = json.loads(path.read_text())
    doc["findings"][0]["preconditions"][0]["confirmation"] = {"state": "confirmed", "basis": "registered"}
    path.write_text(json.dumps(doc))
    proc = subprocess.run([sys.executable, str(SCRIPTS / "validate.py"), "--repo", str(validated_repo)],
                          capture_output=True, text=True, env=validated_env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    pre = json.loads(path.read_text())["findings"][0]["preconditions"][0]
    assert pre["confirmation"]["state"] == "unconfirmed"
    assert pre["confirmation"]["by"] == "validator"
    assert pre["confirmation"]["basis"] in ("call_site_fallback", "not_checked")
    assert "call_site" in pre["confirmation"]


def test_save_finding_strips_a_model_written_confirmation(validated_repo, validated_env, tmp_path):
    out = validated_repo / ".thunderstruck"
    path = next(p for p in sorted((out / "findings").glob("*.json"))
                if any(f.get("preconditions") for f in json.loads(p.read_text())["findings"]))
    doc = json.loads(path.read_text())
    doc["findings"][0]["preconditions"][0]["confirmation"] = {"state": "confirmed"}
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"hotspot_id": doc["hotspot_id"], "findings": doc["findings"]}))
    proc = subprocess.run([sys.executable, str(SCRIPTS / "save_finding.py"), "--repo", str(validated_repo),
                           "--id", doc["hotspot_id"], "--from", str(raw)],
                          capture_output=True, text=True, env=validated_env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    saved = json.loads(path.read_text())
    assert all("confirmation" not in p for f in saved["findings"] for p in f.get("preconditions") or [])
```

If `save_finding.py`'s CLI reads the model output from stdin rather than `--from`, adapt the call to the CLI as it stands on `main` (the assertion is what matters). Add the same assertion for the capture hook: feed `capture_finding.py` an investigator payload in the form of #5's `tests/fixtures/hook_payloads/` whose finding carries `preconditions[0].confirmation`, and assert the saved findings file has none.

In `tests/test_checked_confidence.py`, #56's `test_each_precondition_rule` row `({"confirmation": {"state": "confirmed"}}, "unknown key(s) ['confirmation']")` no longer holds: `confirmation` is accepted and then overwritten. Remove that row and add to the same file:

```python
def test_a_precondition_confirmation_is_accepted_then_replaced(repo):
    assert not [e for e in _errors(repo, _pre(confirmation={"state": "confirmed"})) if "confirmation" in e]
```

(The replacement itself is pinned by `test_validate_writes_a_mechanical_confirmation_and_overwrites_a_claimed_one`.) And in `tests/test_confirmed_defaults.py`:

```python
def test_names_setting_on_repository_refs(tmp_path):
    v = _validator(_tiny_repo(tmp_path, CELERYISH))
    assert v.names_setting("app/defaults.py:2", "result_backend_always_retry") is True
    assert v.names_setting("app/defaults.py:4", "result_backend_always_retry") is False
    assert v.names_setting("backends/database.py:99", "x") is None
```

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL, `AttributeError: 'Validator' object has no attribute 'fallback_read'`, and the confirmation assertions.

- [ ] **Step 3: Write the implementation.** In `scripts/validate.py`:

```python
# The keys an investigator may write, plus "confirmation", which validate.py
# replaces on every run (#57); its value is never read.
PRECONDITION_KEYS = frozenset({"setting", "default", "default_ref", "needs", "value",
                               "documented", "doc_ref", "confirmation"})
```

In `Validator.__init__`, store the catalog and its language map:

```python
        self.catalog = catalog
        self.langmap = c.language_map(catalog)
```

Add the methods (import `deps` at module top if #37 did not):

```python
    def _cited_text(self, ref: Any, allow_dependency: bool) -> tuple[str, str | None] | None:
        """The cited lines (joined) and their language, for a ref check_ref resolves.
        None when it does not resolve or the file is not UTF-8 text. Reads only
        tracked repository files and snapshot files under .thunderstruck/deps/."""
        errors: list[str] = []
        got = self.check_ref(ref, "ref", errors, allow_dependency=allow_dependency)
        if got is None:
            return None
        _, start, end = got
        text_ref = str(ref).strip()
        if deps.DEP_REF.match(text_ref):
            info, _ = deps.resolve_dependency_ref(self.repo, self.deps_index, text_ref)
            if info is None:
                return None
            eco, name = info["id"].split(":", 1)
            path = deps.snapshot_dir(self.repo, eco, name, info["version"]) / info["path"]
        else:
            path = self.repo / got[0]
        text = c.read_text(path)
        if text is None:
            return None
        lines = text.splitlines()[start - 1:end]
        return "\n".join(lines) + "\n", c.detect_language(path.name, self.langmap)

    def fallback_read(self, ref: Any, setting: Any, allow_dependency: bool = False) -> bool | None:
        """Spec §5.2: whether the cited lines read `setting` with a fallback.
        None when unreadable or the language has no setting_reads patterns."""
        got = self._cited_text(ref, allow_dependency)
        return None if got is None else c.reads_with_fallback(got[0], setting, got[1], self.catalog)

    def names_setting(self, ref: Any, setting: Any, allow_dependency: bool = False) -> bool | None:
        """Spec §4.3: whether the cited lines name the setting (or a 2+ segment suffix)."""
        got = self._cited_text(ref, allow_dependency)
        return None if got is None else c.names_setting(got[0], setting, got[1])
```

In `main`, in the loop over a passing document's findings, after `f["evidence_hashes"] = …`:

```python
                for p in f.get("preconditions") or []:
                    if isinstance(p, dict):
                        call_site = validator.fallback_read(p.get("default_ref"), p.get("setting"))
                        p["confirmation"] = {**c.confirm(call_site), "call_site": call_site,
                                             "by": "validator"}
```

Check that `c.read_text` returns `None` for undecodable bytes (it does on `main`: it reads UTF-8 strictly and returns `None` on error); if it does not, decode with `errors="strict"` inside a `try` here.

In `scripts/finding_shape.py`, in `shape(doc, entry)`, after it pops `OWNED_FINDING_KEYS` from each finding:

```python
        for p in finding.get("preconditions") or []:
            if isinstance(p, dict):
                p.pop("confirmation", None)  # #57: never from a model
```

- [ ] **Step 4: Run the tests and the full suite.** Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate.py scripts/finding_shape.py tests/test_confirmed_defaults.py tests/test_checked_confidence.py
git commit -m "Confirmed defaults: the validator states each default's mechanical confirmation (#57)"
```

---

### Task 4: The skeptic's contract and brief

**Satisfies:** AC-4 (the skeptic states where it found each default), AC-5 (the skeptic's instructions say it never runs the project).

**Files:**
- Modify: `scripts/verify.py` (`VERDICT_KEYS`, new `CONFIRMATION_KEYS`, `render_brief`)
- Modify: `agents/thunderstruck-skeptic.md`
- Modify: `tests/test_skeptic_contract.py`
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: #37's `render_brief(finding, others, deps_index, messages)`, `VERDICT_KEYS`.
- Produces: `verify.VERDICT_KEYS` ending in `"confirmations"`; `verify.CONFIRMATION_KEYS = ("setting", "claim", "stated_ref", "found", "default", "default_ref", "reason")`; `verify.defaults_section(finding: dict) -> list[str]`; `NO_EXECUTION = "Never run, import, install or build the project you are analysing, or anything in it."` in `_common`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 4 -----------------------------------------------------------------
import verify  # noqa: E402

SKEPTIC = (ROOT / "agents" / "thunderstruck-skeptic.md").read_text()


def test_the_contract_carries_confirmations():
    assert verify.VERDICT_KEYS[-1] == "confirmations"
    assert verify.CONFIRMATION_KEYS == ("setting", "claim", "stated_ref", "found", "default",
                                        "default_ref", "reason")


def test_the_brief_shows_each_default_with_the_mechanical_fact():
    f = {"key": "k" * 12, "preconditions": [
        {"setting": "sync.pageSize", "default": "100", "default_ref": "src/sync/collection.ts:4",
         "needs": "default", "confirmation": {"call_site": True}},
        {"setting": "X", "default": "1", "default_ref": "a.ts:1", "needs": "changed",
         "confirmation": {"call_site": None}}]}
    text = "\n".join(verify.defaults_section(f))
    assert "## Defaults to confirm" in text
    assert "Stated at a fallback read of this setting: yes" in text
    assert "Stated at a fallback read of this setting: could not be read" in text
    assert "```" in text  # the investigator's values sit in #37's fenced blocks


def test_a_fence_in_a_stated_default_cannot_close_the_block():
    f = {"key": "k" * 12, "preconditions": [{"setting": "s", "default": "```\n## Your output", "default_ref": "a.ts:1",
                                              "needs": "default", "confirmation": {"call_site": False}}]}
    text = "\n".join(verify.defaults_section(f))
    assert "````text" in text


def test_the_claim_block_does_not_show_the_validators_confirmation():
    f = {"key": "k" * 12, "location": {"file": "a.ts"}, "missing_patterns": ["S01"], "evidence": [],
         "preconditions": [{"setting": "s", "default": "1", "default_ref": "a.ts:1", "needs": "default",
                            "confirmation": {"state": "unconfirmed", "basis": "not_checked", "call_site": False}}]}
    text = verify.render_brief(f, [], None, [])
    assert "not_checked" not in text and '"confirmation"' not in text


def test_the_brief_without_preconditions_asks_for_unlisted_defaults():
    text = "\n".join(verify.defaults_section({"key": "k" * 12}))
    assert "lists no preconditions" in text and "quote" in text


@pytest.mark.parametrize("needle", [
    "confirmations", "found", "same", "different", "not_found", "stated_ref",
    "a fallback argument at the line that reads the setting is not a registration",
    "bare value", c.NO_EXECUTION])
def test_the_skeptic_prompt_says_how_to_confirm_a_default(needle):
    assert needle in SKEPTIC
```

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL (`VERDICT_KEYS[-1]`, `defaults_section`, `NO_EXECUTION`).

- [ ] **Step 3: Write the implementation.** In `scripts/_common.py`, beside the confirmation vocabulary:

```python
# The one sentence every agent and the scan skill carry (#57 AC-5).
NO_EXECUTION = "Never run, import, install or build the project you are analysing, or anything in it."
```

In `scripts/verify.py`:

```python
VERDICT_KEYS = ("key", "verdict", "reason", "holds", "refuted_claims", "evidence",
                "dependencies_read", "duplicate_of", "confirmations")
CONFIRMATION_KEYS = ("setting", "claim", "stated_ref", "found", "default", "default_ref", "reason")


def defaults_section(finding: dict) -> list[str]:
    """Spec §6.2: each default to confirm, as written (in #37's fenced _block),
    then one line written by the tool."""
    items = [p for p in finding.get("preconditions") or [] if isinstance(p, dict)]
    L = ["## Defaults to confirm", ""]
    if not items:
        return L + ["The finding lists no preconditions. If its claim rests on a default, "
                    "confirm it as an unlisted default: quote the claim in `claim`.", ""]
    for j, p in enumerate(items):
        stated = "\n".join([f"setting: {p.get('setting')}", f"stated default: {p.get('default')}",
                            f"stated at: {p.get('default_ref')}", f"needs: {p.get('needs')}"])
        L += _block(f"default {j} (the investigator's words)", stated)
        conf = p.get("confirmation") if isinstance(p.get("confirmation"), dict) else {}
        said = {True: "yes", False: "no"}.get(conf.get("call_site"), "could not be read")
        L += [f"Stated at a fallback read of this setting: {said}", ""]
    return L
```

In `render_brief`, append `defaults_section(finding)` directly after *The claim* section, and change #37's preconditions block so it serialises the items without the validator's key:

```python
    shown = [{k: v for k, v in p.items() if k != "confirmation"} if isinstance(p, dict) else p
             for p in finding.get("preconditions") or []]
    L += _block("preconditions", json.dumps(shown, indent=2, ensure_ascii=False))
```

Recompute nothing else: `brief_hash` follows the text.

In `agents/thunderstruck-skeptic.md`, add `c.NO_EXECUTION`'s sentence verbatim to the rules, `confirmations` to the output skeleton (empty list), and this numbered rule after the missing-gate rule:

```markdown
N. **Confirm every default the claim rests on.** For each setting under
   *Defaults to confirm*, and for any default the claim relies on that the
   finding does not list, add one item to `confirmations`:
   `{"setting", "claim", "stated_ref", "found", "default", "default_ref", "reason"}`.
   Find where the settings layer registers the default: a defaults table, a
   schema, a settings class, a configuration file the project ships, or the
   dependency's own default in the snapshots listed in your brief. Cite that
   place as `default_ref`. A fallback argument at the line that reads the setting
   is not a registration and confirms nothing: when a settings layer holds its
   own defaults, it returns those and the fallback never applies.
   `found` is `same` when the registered default is the one the finding states,
   `different` when it is not, `not_found` when you found no registration
   (then `default` and `default_ref` are null). Give `default` as the bare value
   (`False`, `120`, `None`), and `setting` as the name the code reads.
   For a listed setting, `claim` and `stated_ref` are null. For an unlisted one,
   `claim` quotes the finding's words that rest on the default, and
   `stated_ref` is the finding's own code ref where it locates that default, or null.
   A default that is not what the finding says is also a refuted claim.
```

In `tests/test_skeptic_contract.py`, the pinned `VERDICT_KEYS` gains `"confirmations"`.

- [ ] **Step 4: Run the tests and the full suite.** #37's brief-determinism test must still pass. Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/_common.py scripts/verify.py agents/thunderstruck-skeptic.md tests/test_skeptic_contract.py tests/test_confirmed_defaults.py
git commit -m "Confirmed defaults: the skeptic confirms each default it is shown (#57)"
```

---

### Task 5: Settling confirmations, and no `upheld` on an unconfirmed default

**Satisfies:** AC-1 (the skeptic-informed state), AC-3 (no `upheld`), AC-4 (both defaults kept).

**Files:**
- Modify: `scripts/verify.py` (`Resolver.fallback_read`, new `resolve_confirmations`, `_quotes_any`, `no_upheld_on_unconfirmed`; `settle`, `apply`, `claim_hash`, `cited_files`)
- Modify: `tests/fixtures/build_fixture.py`, `scripts/gen_sample_report.py` (Task 12 Steps 3–4, done here first; and the canned-verdict guard learns `expect`)
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: `Validator.fallback_read` (Task 3); `c.with_confirmations`, `c.unconfirmed_defaults`, `c.CONFIRMATION_FOUND`, `c.CONFIRMATION_REASONS` (Task 1); #37's `settle`, `_norm`, `Resolver`, `apply`, `claim_hash`, `cited_files`, `OWNED`.
- Produces: `Resolver.fallback_read(ref, setting) -> bool | None`; `verify.resolve_confirmations(finding: dict, result: dict, resolver: Resolver, ignored: list[str]) -> list[dict]` (items with `precondition`, `stated_call_site`, `default_names_setting`, `default_call_site`, `default_ref_error` added); `Resolver.names_setting(ref, setting) -> bool | None`; `verify.no_upheld_on_unconfirmed(finding: dict, check: dict) -> dict`; `check.confirmations` on every settled check that came from a result or the ledger; `preconditions[j].confirmation` written by `apply`; `cited_files(finding, verdict_evidence=(), confirmations=())`.

- [ ] **Step 1: Write the failing tests.** Append (they use #37's `validated_repo` and the helpers of `tests/test_verification.py`, imported):

```python
# --- Task 5 -----------------------------------------------------------------
from test_verification import _apply, _entry, _finding, _line, _prepare, _save, _v  # noqa: E402


def _collection(repo: Path, env: dict) -> tuple[dict, dict]:
    plan = _prepare(repo, env)
    e = _entry(plan, "collection.ts")
    return plan, e


def _conf(**over) -> dict:
    item = {"setting": "sync.pageSize", "claim": None, "stated_ref": None, "found": "same",
            "default": "100", "default_ref": None, "reason": "r"}
    item.update(over)
    return item


def test_a_confirmation_at_the_fallback_read_confirms_nothing(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    read = _line(validated_repo, "src/sync/collection.ts", "sync.pageSize")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(default_ref=f"src/sync/collection.ts:{read}")]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "inconclusive"
    assert check["reason"].startswith("The check upheld this claim, but it rests on a default no one confirmed: sync.pageSize")
    pre = _finding(validated_repo, e["key"])["preconditions"][0]
    assert (pre["confirmation"]["state"], pre["confirmation"]["basis"]) == ("unconfirmed", "call_site_fallback")


def test_a_registry_that_disagrees_contradicts_and_keeps_both(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(found="different", default="500", default_ref=f"src/config/settings.ts:{reg}")]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "inconclusive"
    [item] = check["confirmations"]
    assert (item["default"], item["confirmation"]["basis"]) == ("500", "contradicted")
    pre = _finding(validated_repo, e["key"])["preconditions"][0]
    assert pre["default"] == "100" and pre["confirmation"]["basis"] == "contradicted"


def test_a_registry_that_agrees_confirms_and_upheld_stands(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "api.ts")
    f = _finding(validated_repo, e["key"])
    pre = f["preconditions"][0]
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(setting=pre["setting"], default=pre["default"], default_ref=pre["default_ref"])]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "upheld"
    assert _finding(validated_repo, e["key"])["preconditions"][0]["confirmation"]["state"] == "confirmed"


def test_items_that_break_the_contract_are_dropped_and_named(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "inconclusive", confirmations=[
        {"setting": "sync.pageSize", "found": "maybe"},
        _conf(setting="unlisted.thing", claim="a paraphrase not in the finding"),
        _conf(default_ref="src/nowhere.ts:1"),
        _conf()]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert "Ignored: confirmations[0]" in check["reason"]
    assert "confirmations[1]" in check["reason"]
    [item] = check["confirmations"]  # [2] kept as unresolved; [3] names the same setting twice
    assert item["confirmation"]["basis"] == "unresolved" and item["default_ref_error"]
    assert "confirmations[3]" in check["reason"]


def test_a_reused_upheld_without_confirmations_settles_inconclusive(validated_repo, validated_env, tmp_path):
    """Review focus 4: a ledger entry written before #57."""
    plan, e = _collection(validated_repo, validated_env)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(found="same", default="100", default_ref=f"src/config/settings.ts:{reg}")]))
    _apply(validated_repo, validated_env)
    ledger_path = validated_repo / ".thunderstruck" / "checks" / "ledger.json"
    ledger = json.loads(ledger_path.read_text())
    ledger["entries"][e["key"]]["check"].pop("confirmations")
    ledger["entries"][e["key"]]["check"]["status"] = "upheld"
    ledger_path.write_text(json.dumps(ledger))
    again = _prepare(validated_repo, validated_env)
    assert _entry(again, "collection.ts")["action"] == "reuse"
    assert _apply(validated_repo, validated_env)[e["key"]]["status"] == "inconclusive"


def test_claim_hash_ignores_confirmation_and_the_registry_is_in_the_ledger(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    f = _finding(validated_repo, e["key"])
    g = json.loads(json.dumps(f))
    g["preconditions"][0]["confirmation"] = {"state": "confirmed"}
    assert verify.claim_hash(f) == verify.claim_hash(g)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "inconclusive", confirmations=[
        _conf(found="different", default="500", default_ref=f"src/config/settings.ts:{reg}")]))
    _apply(validated_repo, validated_env)
    ledger = json.loads((validated_repo / ".thunderstruck" / "checks" / "ledger.json").read_text())["entries"]
    assert "src/config/settings.ts" in ledger[e["key"]]["files"]
```

These tests need the fixture and the canned collection precondition of Task 12. **Do Task 12 Steps 3 and 4 first, as part of this task**, including the `expect` guard of Task 12 Step 4 (the fixture files, the page-size read, the canned precondition and the two canned confirmations), and include those files in this task's commit; Task 12 then adds its sample tests and regenerates the samples.

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL (unknown key `confirmations` is now allowed by Task 4, but `check["confirmations"]` is absent and `upheld` stands).

- [ ] **Step 3: Write the implementation.** In `scripts/verify.py`:

```python
CLAIM_FIELDS = ("failure_mode", "trigger_condition", "amplifier", "sustaining_effect",
                "blast_radius", "how_to_verify")


def _quotes_any(finding: dict, claim) -> bool:
    if not isinstance(claim, str) or not claim.strip():
        return False
    notes = [ev.get("note") for ev in finding.get("evidence") or [] if isinstance(ev, dict)]
    source = " ".join(str(finding.get(k) or "") for k in CLAIM_FIELDS) + " " + " ".join(map(str, notes))
    return _norm(claim) in _norm(source)


def _code_refs(finding: dict) -> set[str]:
    out = set()
    for ev in finding.get("evidence") or []:
        m = CODE_REF.match(str(ev.get("ref") or "").strip()) if isinstance(ev, dict) and ev.get("type") == "code" else None
        if m:
            out.add(f"{c.ref_path(m['path'])}:{m['start']}" + (f"-{m['end']}" if m["end"] else ""))
    return out


def resolve_confirmations(finding: dict, result: dict, resolver: "Resolver", ignored: list[str]) -> list[dict]:
    """Spec §6.3: keep, resolve and annotate the skeptic's confirmation items."""
    index = {"".join(str(p.get("setting", "")).split()).casefold(): j
             for j, p in enumerate(finding.get("preconditions") or []) if isinstance(p, dict)}
    refs = _code_refs(finding)
    kept, seen = [], set()
    for n, item in enumerate(result.get("confirmations") or []):
        where = f"confirmations[{n}]"
        if not isinstance(item, dict) or set(item) - set(CONFIRMATION_KEYS):
            ignored.append(f"{where} is not an object with the keys {list(CONFIRMATION_KEYS)}")
            continue
        setting = item.get("setting")
        if not isinstance(setting, str) or not setting.strip():
            ignored.append(f"{where}.setting must be a non-empty string")
            continue
        norm = "".join(setting.split()).casefold()
        if norm in seen:
            ignored.append(f"{where} names {setting!r} a second time")
            continue
        if item.get("found") not in c.CONFIRMATION_FOUND:
            ignored.append(f"{where}.found {item.get('found')!r} is not one of {list(c.CONFIRMATION_FOUND)}")
            continue
        j = index.get(norm)
        out = {"setting": setting, "precondition": j, "claim": None, "stated_ref": None,
               "stated_call_site": None, "found": item["found"], "default": None, "default_ref": None,
               "default_ref_error": None, "default_names_setting": None, "default_call_site": None,
               "reason": str(item.get("reason") or "")}
        if j is None:
            if not _quotes_any(finding, item.get("claim")):
                ignored.append(f"{where} names a setting the finding does not list, and its claim "
                               f"does not quote the finding")
                continue
            out["claim"] = item["claim"]
            sref = item.get("stated_ref")
            if sref is not None:
                m = CODE_REF.match(str(sref).strip())
                canon = (f"{c.ref_path(m['path'])}:{m['start']}" + (f"-{m['end']}" if m["end"] else "")) if m else None
                if canon in refs:
                    out["stated_ref"] = canon
                    out["stated_call_site"] = resolver.fallback_read(canon, setting)
                else:
                    ignored.append(f"{where}.stated_ref {sref!r} is not one of the finding's code refs")
        if item["found"] != "not_found":
            if not isinstance(item.get("default"), str) or not item["default"].strip():
                ignored.append(f"{where}.default must be the value found")
                continue
            out["default"], out["default_ref"] = item["default"], item.get("default_ref")
            errors: list[str] = []
            if resolver.ref(item.get("default_ref"), f"{where}.default_ref", errors):
                out["default_names_setting"] = resolver.names_setting(item["default_ref"], setting)
                out["default_call_site"] = resolver.fallback_read(item["default_ref"], setting)
            else:
                out["default_ref_error"] = errors[0] if errors else f"{where}.default_ref does not resolve"
        seen.add(norm)
        kept.append(out)
    return kept


def no_upheld_on_unconfirmed(finding: dict, check: dict) -> dict:
    """Spec §7.1: the one place #57 changes a status."""
    derived = c.with_confirmations({**finding, "check": check}, check.get("confirmations") or [])
    check = {**check, "confirmations": derived["check"]["confirmations"]}
    if check.get("status") != "upheld":
        return check
    missing = c.unconfirmed_defaults(derived)
    if not missing:
        return check
    first = missing[0]
    basis = (first.get("confirmation") or {}).get("basis", "not_checked")
    more = f" and {len(missing) - 1} more" if len(missing) > 1 else ""
    return {**check, "status": "inconclusive",
            "reason": (f"The check upheld this claim, but it rests on a default no one confirmed: "
                       f"{first.get('setting')} ({c.CONFIRMATION_REASONS[basis]}){more}.")}
```

`Resolver` gains:

```python
    def fallback_read(self, ref, setting) -> bool | None:
        return self.v.fallback_read(ref, setting, allow_dependency=True)

    def names_setting(self, ref, setting) -> bool | None:
        return self.v.names_setting(ref, setting, allow_dependency=True)
```

#37's `settle` is a wrapper with one exit around `_decide` (#37 §16). Change it to:

```python
def settle(finding, entry, result, resolver, plan, ledger_entry) -> dict:
    return no_upheld_on_unconfirmed(finding, _decide(finding, entry, result, resolver, plan, ledger_entry))
```

That covers the reuse path and every other path. In `_decide`:

- On the main path, directly after the refuted-claims loop: `items = resolve_confirmations(finding, result, resolver, ignored)`. Where #37 builds `read` (dependency versions), add each item whose `default_ref_error` is `None` and whose `default_ref` matches `deps.DEP_REF`: `read[f"{m['eco']}:{m['name']}"] = m["version"]`.
- In the final `return {…}`, add the key `"confirmations": items`.

The paths that return `unchecked` stay as they are (no status to refuse, no items).

In `claim_hash`, after building `body`:

```python
    if isinstance(body.get("preconditions"), list):
        body["preconditions"] = [{k: v for k, v in p.items() if k != "confirmation"}
                                 if isinstance(p, dict) else p for p in body["preconditions"]]
```

`cited_files` gains `confirmations=()` and adds `_ref_path(it.get("default_ref"))` and `_ref_path(it.get("stated_ref"))` for each item. In `apply`, the ledger's `files` call becomes `cited_files(f, check["evidence"], check.get("confirmations") or [])`, and where `apply` writes `f["check"] = checks[f["key"]]` it also writes:

```python
                    f["preconditions"] = c.with_confirmations(
                        {**f, "check": checks[f["key"]]},
                        checks[f["key"]].get("confirmations"))["preconditions"]
```

- [ ] **Step 4: Run the tests and the full suite.** #37's settle tests must still pass: their verdicts carry no `confirmations`, and a fixture finding they expect `upheld` now settles `inconclusive` only if it lists a `needs: default` precondition. Where such a #37 test expects `upheld` for a finding with a `needs: default` item, add a confirming item to its canned verdict rather than weakening the expectation. Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify.py tests/test_confirmed_defaults.py tests/test_verification.py tests/fixtures/build_fixture.py scripts/gen_sample_report.py
git commit -m "Confirmed defaults: settle each confirmation; no upheld on an unconfirmed default (#57)"
```

---

### Task 6: Spike 2 replayed

**Satisfies:** AC-2 and AC-3 on the shape of the evidence; the deterministic half of AC-6.

**Files:**
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: `verify.settle`, `verify.Resolver` (#37, Task 5); `_tiny_repo`, `CELERYISH` (Task 3).

- [ ] **Step 1: Write the test.** Append:

```python
# --- Task 6 -----------------------------------------------------------------
FR015_LIKE = {
    "key": "6345778fa223", "location": {"file": "backends/database.py", "lines": "4-5"},
    "missing_patterns": ["S04"],
    "failure_mode": "Workers retry every DatabaseError and dispose the pool before each retry.",
    "trigger_condition": "The database returns errors.",
    "amplifier": "Every DatabaseError is treated as retryable. always_retry defaults to True with 3 retries.",
    "blast_radius": "Result storage.", "how_to_verify": "Run a burst.",
    "evidence": [{"type": "code", "ref": "backends/database.py:4-5",
                  "note": "always_retry is on by default with 3 retries"}],
    "confidence": "medium", "confidence_rationale": "-",
}


def _settle(repo: Path, verdict: dict) -> dict:
    plan = {"generated_at": "t", "head": "h", "model": "sonnet",
            "findings": [{"key": FR015_LIKE["key"], "action": "check", "brief_hash": "b"}]}
    result = {**verdict, "key": FR015_LIKE["key"], "brief_hash": "b", "scan": "t"}
    return verify.settle(FR015_LIKE, plan["findings"][0], result, verify.Resolver(repo, None), plan, None)


def _conf015(found: str, default: str, ref: str) -> dict:
    return {"setting": "result_backend_always_retry", "claim": "always_retry defaults to True with 3 retries",
            "stated_ref": "backends/database.py:4-5", "found": found, "default": default,
            "default_ref": ref, "reason": "r"}


def test_refuter_a_upholds_from_the_fallback_line_and_cannot(tmp_path):
    repo = _tiny_repo(tmp_path, CELERYISH)
    check = _settle(repo, {"verdict": "upheld", "reason": "Retries are on by default.", "evidence": [],
                           "confirmations": [_conf015("same", "True", "backends/database.py:4")]})
    assert check["status"] == "inconclusive"
    [item] = check["confirmations"]
    assert item["stated_call_site"] is True and item["default_call_site"] is True
    assert (item["confirmation"]["state"], item["confirmation"]["basis"]) == ("unconfirmed", "call_site_fallback")


def test_refuter_b_cites_the_registry_and_contradicts(tmp_path):
    repo = _tiny_repo(tmp_path, CELERYISH)
    check = _settle(repo, {
        "verdict": "narrowed", "reason": "No retries on defaults.",
        "holds": "Every DatabaseError is classified retryable when a user opts in.",
        "refuted_claims": [{"field": "amplifier", "claim": "always_retry defaults to True with 3 retries",
                            "fact": "The registered default is False.", "evidence": [0]}],
        "evidence": [{"type": "code", "ref": "app/defaults.py:2", "note": "registered False"}],
        "confirmations": [_conf015("different", "False", "app/defaults.py:2")]})
    assert check["status"] == "narrowed"
    [item] = check["confirmations"]
    assert (item["default"], item["confirmation"]["basis"]) == ("False", "contradicted")
```

- [ ] **Step 2: Run it.** Expected: PASS on the first run, since Tasks 3–5 implement the rule; if it fails, the failure is in those tasks, fixed there.

- [ ] **Step 3: Commit**

```bash
git add tests/test_confirmed_defaults.py
git commit -m "Confirmed defaults: replay Spike 2's disagreement on Celery's shape (#57)"
```

---

### Task 7: The report's data, `report.json` and `index.json`

**Satisfies:** AC-1 (in every output), AC-4 (both defaults carried), AC-8 (the order).

**Files:**
- Modify: `scripts/report.py` (`collect`, `_set_urls`/`link_refs` for confirmation refs, `render_json`, `render_index`; new `defaults_counts`)
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: `c.with_confirmations`, `c.finding_gate` (Task 1); #37's verification-ran decision in `collect()`; #56's `order_key`, `_ref_url`.
- Produces: each finding in `collect()`'s data carries derived `preconditions[].confirmation` and `check.confirmations[]` (each with `confirmation` and `default_url`); `report.defaults_counts(findings: list[dict]) -> dict` (`{"confirmed", "unconfirmed", "basis": {…}}`); `report.json` `counts.defaults`, `counts.gate` with three keys; `index.json` precondition entries with `confirmation`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 7 -----------------------------------------------------------------
import report  # noqa: E402


def _report(repo: Path, env: dict) -> dict:
    proc = subprocess.run([sys.executable, str(SCRIPTS / "report.py"), "--repo", str(repo)],
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads((repo / ".thunderstruck" / "report.json").read_text())


def test_without_verification_confirmations_are_mechanical_only(validated_repo, validated_env, tmp_path):
    """Review focus 3: findings files still carry an earlier skeptic's confirmations."""
    plan, e = _collection(validated_repo, validated_env)
    api = _entry(plan, "api.ts")
    pre = _finding(validated_repo, api["key"])["preconditions"][0]
    _save(validated_repo, validated_env, tmp_path, _v(api["key"], "upheld", confirmations=[
        _conf(setting=pre["setting"], default=pre["default"], default_ref=pre["default_ref"])]))
    _apply(validated_repo, validated_env)
    (validated_repo / ".thunderstruck" / "checks" / "run.json").unlink()  # this scan did not verify
    data = _report(validated_repo, validated_env)
    bases = {p["confirmation"]["basis"] for f in data["findings"] for p in f.get("preconditions") or []}
    assert bases <= {"call_site_fallback", "not_checked"}
    assert data["counts"]["defaults"]["confirmed"] == 0


def test_the_report_orders_three_gates_and_counts_defaults(validated_repo, validated_env):
    data = _report(validated_repo, validated_env)
    gates = [f["gate"] for f in data["findings"]]
    assert gates == sorted(gates, key=c.GATES.index)
    assert set(data["counts"]["gate"]) == set(c.GATES)
    d = data["counts"]["defaults"]
    assert set(d["basis"]) == set(c.CONFIRMATION_BASES)
    assert d["confirmed"] + d["unconfirmed"] == sum(d["basis"].values())
    index = json.loads((validated_repo / ".thunderstruck" / "index.json").read_text())
    pres = [p for entry in index["files"].values() for f in entry["findings"] for p in f.get("preconditions") or []]
    assert pres and all(p["confirmation"] in c.CONFIRMATION_STATES for p in pres)


def test_a_contradicted_default_keeps_both_with_their_locations(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(found="different", default="500", default_ref=f"src/config/settings.ts:{reg}")]))
    _apply(validated_repo, validated_env)
    data = _report(validated_repo, validated_env)
    f = next(x for x in data["findings"] if x["key"] == e["key"])
    p = f["preconditions"][0]
    [item] = f["check"]["confirmations"]
    assert (p["default"], p["default_ref"]) != (item["default"], item["default_ref"])
    assert item["default_url"] is None or "settings.ts" in item["default_url"]
    assert f["gate"] == "unconfirmed_default"
```

If `index.json`'s shape on `main` is not `{"files": {path: {"findings": [...]}}}`, read its entries the way `tests/test_checked_confidence.py`'s Task 3 tests do.

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL (`KeyError: 'defaults'`, confirmations not derived).

- [ ] **Step 3: Write the implementation.** In `scripts/report.py`'s `collect()`, after #37 has set `f["check"]` (the stored check when verification ran for this scan, the reset `unchecked` one otherwise) and **before** `f["gate"] = c.finding_gate(f)`:

```python
            derived = c.with_confirmations(f, (f.get("check") or {}).get("confirmations"))
            f["preconditions"] = derived["preconditions"]
            if "check" in derived:
                f["check"] = derived["check"]
```

Where #56's `_set_urls` adds `default_url`/`doc_url` to preconditions, also add to each `check.confirmations` item `default_url = _ref_url(ctx, item.get("default_ref"))` and `stated_url = _ref_url(ctx, item.get("stated_ref"))`, with `None` for a dependency ref (`deps.DEP_REF.match`) and when links are off.

Add:

```python
def defaults_counts(findings: list[dict]) -> dict:
    """counts.defaults: every listed precondition and unlisted item of the reported findings."""
    basis = {b: 0 for b in c.CONFIRMATION_BASES}
    for f in findings:
        confs = [p.get("confirmation") for p in _preconditions(f)]
        confs += [it.get("confirmation") for it in (f.get("check") or {}).get("confirmations") or []
                  if isinstance(it, dict) and it.get("precondition") is None]
        for conf in confs:
            b = conf.get("basis") if isinstance(conf, dict) else None
            basis[b if b in basis else "not_checked"] += 1
    return {"confirmed": basis["registered"], "unconfirmed": sum(basis.values()) - basis["registered"],
            "basis": basis}
```

In `render_json`, `counts["defaults"] = defaults_counts(findings)`; `counts["gate"]` is built from `c.GATES` (it already is, per #56; confirm it lists all three keys with zeros). In `render_index`, each precondition entry gains `"confirmation": c.confirmation_state(p.get("confirmation"))`.

- [ ] **Step 4: Run the tests and the full suite.** Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/report.py tests/test_confirmed_defaults.py
git commit -m "Confirmed defaults: derive, order and count them in the report's data (#57)"
```

---

### Task 8: `report.md`

**Satisfies:** AC-1, AC-4, AC-8.

**Files:**
- Modify: `scripts/report.py` (`_precondition_line`, `render_preconditions`, `render_markdown`; new `_confirmation_clause`, `defaults_line`)
- Modify: `tests/test_inert_report.py` (`MODEL_FIELDS`)
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: Task 7's data; #56's `_precondition_line(p)`, `render_preconditions(f)`, `_linked`, `md`.
- Produces: `report.defaults_line(data: dict) -> str | None`; `report._confirmation_clause(conf: dict, item: dict | None) -> str`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 8 -----------------------------------------------------------------
def _md(repo: Path, env: dict) -> str:
    _report(repo, env)
    return (repo / ".thunderstruck" / "report.md").read_text()


def test_report_md_states_every_default_and_shows_both_when_they_differ(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(found="different", default="500", default_ref=f"src/config/settings.ts:{reg}",
              reason="The registry holds 500.")]))
    _apply(validated_repo, validated_env)
    text = _md(validated_repo, validated_env)
    assert text.count("**Unconfirmed**") + text.count("**Confirmed**") >= 1
    assert "a check found a different default registered: `500` at" in text
    assert "relies on an unconfirmed default" in text
    assert "Check's note: “The registry holds 500.”" in text
    assert text.startswith("#") and "Defaults: " in text


def test_defaults_line_counts_bases():
    data = {"findings": [], "counts": {"defaults": {"confirmed": 1, "unconfirmed": 3, "basis": {
        "registered": 1, "contradicted": 1, "call_site_fallback": 2, "not_found": 0, "unresolved": 0,
        "not_checked": 0}}, "gate": {"none": 1, "unconfirmed_default": 2, "non_default_setting": 0}}}
    assert report.defaults_line(data) == (
        "Defaults: 1 confirmed · 3 unconfirmed (2 stated where the setting is read, 1 contradicted by a check)"
        " · 2 findings rely on an unconfirmed default and are listed after default-path findings")
    assert report.defaults_line({"findings": [], "counts": {"defaults": {"confirmed": 0, "unconfirmed": 0,
                                                                         "basis": {}}, "gate": {}}}) is None
```

In `tests/test_inert_report.py`, extend `MODEL_FIELDS` with the paths `check.confirmations[].setting`, `.default`, `.default_ref`, `.stated_ref`, `.claim` and `.reason` (in the form that file uses for nested fields) so the hostile-text test plants text there.

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL.

- [ ] **Step 3: Write the implementation.** In `scripts/report.py`:

```python
_BASIS_PHRASE = {"call_site_fallback": "stated where the setting is read",
                 "contradicted": "contradicted by a check", "not_found": "not found by a check",
                 "unresolved": "with a location that did not resolve", "not_checked": "not checked"}


def defaults_line(data: dict) -> str | None:
    d = (data.get("counts") or {}).get("defaults") or {}
    if not d.get("confirmed") and not d.get("unconfirmed"):
        return None
    parts = [f"{n} {_BASIS_PHRASE[b]}" for b, n in (d.get("basis") or {}).items()
             if n and b in _BASIS_PHRASE]
    line = f"Defaults: {d['confirmed']} confirmed · {d['unconfirmed']} unconfirmed"
    line += f" ({', '.join(parts)})" if parts else ""
    gated = ((data.get("counts") or {}).get("gate") or {}).get("unconfirmed_default", 0)
    if gated:
        line += (f" · {gated} {'finding relies' if gated == 1 else 'findings rely'} on an unconfirmed "
                 f"default and {'is' if gated == 1 else 'are'} listed after default-path findings")
    return line


def _confirmation_clause(conf: dict, item: dict | None) -> str:
    conf = conf if isinstance(conf, dict) else c.confirm(None)
    head = "**Confirmed**" if conf.get("state") == "confirmed" else "**Unconfirmed**"
    text = f" {head}: {conf.get('reason') or c.CONFIRMATION_REASONS['not_checked']}"
    if item and item.get("default") is not None and item.get("default_ref"):
        where = (_linked(str(item["default_ref"]), item.get("default_url"))
                 if not deps.DEP_REF.match(str(item["default_ref"])) else md.code(item["default_ref"]))
        text += (f": {where}" if conf.get("basis") == "registered"
                 else f": {md.code(item['default'])} at {where}")
    text += "."
    if item and item.get("reason"):
        text += f" Check's note: “{md.text(item['reason'])}”"
    return text
```

`_precondition_line(p)` becomes `_precondition_line(p, item=None)` and appends `_confirmation_clause(p.get("confirmation"), item)` before returning. `render_preconditions(f)`:

- passes each precondition's item (`check.confirmations` entry whose `precondition` is its index);
- shows "The failure happens on default settings and rests on these defaults:" when `f["gate"]` is `none` **or** `unconfirmed_default`;
- after the listed lines, when unlisted items exist, adds "Defaults the check found this claim rests on:" and per item `f"- {md.code(item['setting'])}: the finding says “{md.text(item['claim'])}”;"` + `_confirmation_clause(item["confirmation"], item)`; a `stated_ref` is appended as " (stated at " + the linked ref, or `md.code` for a dependency ref, + ")".

In `render_markdown`, after #56's check-status line (and #37's verification line), add `defaults_line(data)` when it is not `None`. The badge marker comes from `c.GATE_MARKERS` already (#56), so `relies on an unconfirmed default` appears without further change; confirm by the test.

- [ ] **Step 4: Run the tests and the full suite.** Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/report.py tests/test_inert_report.py tests/test_confirmed_defaults.py
git commit -m "Confirmed defaults: report.md states each default's confirmation (#57)"
```

---

### Task 9: The HTML report

**Satisfies:** AC-1, AC-4, AC-8.

**Files:**
- Modify: `templates/report.html`
- Modify: `tests/test_report_html.py` (`MODEL_FIELDS`; a test pinning `CONFIRMATION_REASONS`)
- Modify: `tests/test_report_html_browser.py` (one dossier assertion)

**Interfaces:**
- Consumes: `report.json`'s `preconditions[].confirmation`, `check.confirmations[]`, `counts.defaults`, the third gate; #56's `GATE_MARKERS` object and preconditions row; `link()`.
- Produces: in the template script, `var CONFIRMATION_REASONS = {…}` (one line, JSON object literal) and `function confirmationClause(conf, item)` returning a DOM fragment.

- [ ] **Step 1: Write the failing tests.** In `tests/test_report_html.py`:

```python
def test_confirmation_reasons_match_common():
    import re
    template = (ROOT / "templates" / "report.html").read_text()
    m = re.search(r"var CONFIRMATION_REASONS = (\{.*?\});", template)
    assert m and json.loads(m.group(1)) == c.CONFIRMATION_REASONS


def test_gate_markers_include_the_unconfirmed_default():
    import re
    template = (ROOT / "templates" / "report.html").read_text()
    m = re.search(r"var GATE_MARKERS = (\{.*?\});", template)
    assert json.loads(m.group(1)) == c.GATE_MARKERS
```

and extend `MODEL_FIELDS` with the same six confirmation paths as Task 8 (`setting`, `default`, `default_ref`, `stated_ref`, `claim`, `reason`). In `tests/test_report_html_browser.py`, in the test that opens a dossier with preconditions, assert that its Preconditions row contains `Unconfirmed` or `Confirmed`, and that a finding with `gate: unconfirmed_default` shows the marker text in its rail item.

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL (`CONFIRMATION_REASONS` absent; `GATE_MARKERS` has two keys).

- [ ] **Step 3: Write the implementation.** In `templates/report.html`'s script, next to `GATE_MARKERS` (which takes the three-gate value of `c.GATE_MARKERS`, as #56's generator or literal does):

```javascript
var CONFIRMATION_REASONS = {"registered": "a check found this default registered, and it agrees", "contradicted": "a check found a different default registered", "call_site_fallback": "the default is stated where the setting is read, as a fallback; the value in effect may be registered elsewhere", "not_found": "a check found no place that registers this default", "unresolved": "the place a check gave for this default does not resolve", "not_checked": "no check looked for where this default is registered"};

function confirmationClause(conf, item) {
  var span = document.createElement("span");
  var tag = document.createElement("span");
  var ok = conf && conf.state === "confirmed";
  tag.className = "tag " + (ok ? "ok" : "warn");
  tag.textContent = ok ? "Confirmed" : "Unconfirmed";
  span.appendChild(document.createTextNode(" "));
  span.appendChild(tag);
  var basis = conf && CONFIRMATION_REASONS[conf.basis] ? conf.basis : "not_checked";
  span.appendChild(document.createTextNode(" " + CONFIRMATION_REASONS[basis]));
  if (item && item.default !== null && item.default !== undefined && item.default_ref) {
    span.appendChild(document.createTextNode(basis === "registered" ? ": " : ": " + item.default + " at "));
    span.appendChild(link(item.default_ref, item.default_url));
  }
  span.appendChild(document.createTextNode("."));
  if (item && item.reason) {
    span.appendChild(document.createTextNode(" Check's note: “" + item.reason + "”"));
  }
  return span;
}
```

In the Preconditions row builder (#56), append `confirmationClause(p.confirmation, itemFor(f, i))` to each line, where `itemFor` returns the `f.check.confirmations` entry whose `precondition === i`, and add one line per unlisted item ("<setting>: the finding says “<claim>”" + the clause). In the overview counts, add the defaults line built from `report.counts.defaults` with the same words as `report.defaults_line`. `link()` already returns plain text when the URL is null. Use the existing `tag` classes; add `.tag.ok`/`.tag.warn` only if they do not exist, with colours from the existing tokens. `report_html.py` recomputes the CSP hash as today.

- [ ] **Step 4: Run the tests, the browser test** (`THUNDERSTRUCK_REQUIRE_BROWSER=1 uv run --with pytest --with pyyaml --with lizard --with playwright==1.56.0 pytest tests/test_report_html_browser.py -q`) **and the full suite.** Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add templates/report.html tests/test_report_html.py tests/test_report_html_browser.py
git commit -m "Confirmed defaults: the HTML report shows each default's confirmation (#57)"
```

---

### Task 10: The guardrail

**Satisfies:** AC-1 (the guardrail's statements), AC-8 (its order).

**Files:**
- Modify: `scripts/guardrail.py` (`GATE_ORDER`, `precondition_line`)
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: `index.json` precondition entries with `confirmation` (Task 7); #56's `precondition_line(f)`, `_capped`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 10 ----------------------------------------------------------------
import guardrail  # noqa: E402


def test_guardrail_gate_order_is_common_gates():
    assert guardrail.GATE_ORDER == c.GATES


@pytest.mark.parametrize("state, phrase", [
    ("confirmed", "which a check confirmed"), ("unconfirmed", "which no check confirmed")])
def test_guardrail_states_the_confirmation(state, phrase):
    f = {"check_status": "unchecked", "preconditions": [
        {"setting": "sync.pageSize", "default": "100", "needs": "default", "confirmation": state}]}
    line = guardrail.precondition_line(f)
    assert line == f"It happens on default settings and rests on sync.pageSize at its default 100, {phrase}."


def test_guardrail_says_nothing_about_confirmation_for_an_older_index():
    f = {"check_status": "unchecked", "preconditions": [{"setting": "s", "default": "1", "needs": "default"}]}
    assert guardrail.precondition_line(f) == "It happens on default settings and rests on s at its default 1."
```

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL.

- [ ] **Step 3: Write the implementation.** In `scripts/guardrail.py`:

```python
GATE_ORDER = ("none", "unconfirmed_default", "non_default_setting")
_CONFIRMED = {"confirmed": ", which a check confirmed", "unconfirmed": ", which no check confirmed"}
```

In `precondition_line`, the `needs: default` branch's item text becomes:

```python
            [f"{p.get('setting')} at its default {p.get('default')}{_CONFIRMED.get(p.get('confirmation'), '')}"
             for p in items], ", ") + ".")
```

The `needs: changed` branch is unchanged. Nothing imperative; nothing new imported.

- [ ] **Step 4: Run the tests, the guardrail latency and stdlib tests, and the full suite.** Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/guardrail.py tests/test_confirmed_defaults.py
git commit -m "Confirmed defaults: the guardrail states whether a default was confirmed (#57)"
```

---

### Task 11: No stage runs, imports or builds the scanned project

**Satisfies:** AC-5.

**Files:**
- Create: `tests/test_no_execution.py`
- Modify: `agents/thunderstruck-investigator.md`, `skills/thunderstruck-scan/SKILL.md` (the sentence)
- Modify: `hooks/hooks.json` (every command runs `python3 -S`)

**Interfaces:**
- Consumes: `c.NO_EXECUTION` (Task 4); #37's `validated_repo`, `validated_env`; the scripts as they are.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_no_execution.py`:

```python
"""#57 AC-5: no stage runs, imports or builds the scanned project."""

from __future__ import annotations

import ast
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

FORBIDDEN_NAMES = {"exec", "eval", "compile", "__import__"}
FORBIDDEN_MODULES = {"importlib", "runpy", "ctypes", "pty"}
FORBIDDEN_OS = {"system", "popen", "execv", "execve", "execvp", "execvpe", "execl", "execle",
                "execlp", "execlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe", "spawnl",
                "spawnle", "spawnlp", "spawnlpe", "posix_spawn", "posix_spawnp"}
# (file, function): the only places a process may start. The first group must
# start git; context.run_command starts the catalog command the user approved
# by hash (#1); gen_sample_report is not a scan stage.
GIT_ONLY = {("_common.py", "git"), ("_common.py", "git_paths"), ("_common.py", "commit_touches"),
            ("_common.py", "commit_exists"), ("_common.py", "tracked_index"),
            ("_common.py", "find_repo_root")}
OTHER_ALLOWED = {("context.py", "run_command")}
NOT_A_STAGE = {"gen_sample_report.py", "gen_catalog_docs.py"}


def _scripts() -> list[Path]:
    return sorted(p for p in SCRIPTS.rglob("*.py") if p.name not in NOT_A_STAGE)


def _calls(tree: ast.AST):
    """Every call with the name of its innermost enclosing def ("<module>" at top level)."""
    def visit(node: ast.AST, owner: str):
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else owner
            if isinstance(child, ast.Call):
                yield owner, child
            yield from visit(child, inner)
    yield from visit(tree, "<module>")


def test_calls_are_attributed_to_their_innermost_def_only():
    tree = ast.parse("import subprocess\ndef outer():\n    def inner():\n        subprocess.run(['git'])\n"
                     "    subprocess.run(['git'])\nsubprocess.run(['x'])\n")
    owners = sorted(fn for fn, call in _calls(tree) if ast.unparse(call.func) == "subprocess.run")
    assert owners == ["<module>", "inner", "outer"]


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_no_script_imports_or_evaluates_code(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & FORBIDDEN_MODULES, path
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in FORBIDDEN_MODULES, path
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in FORBIDDEN_NAMES, f"{path.name}: {node.func.id}()"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
            assert node.func.attr not in FORBIDDEN_OS, f"{path.name}: os.{node.func.attr}()"


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_processes_start_only_where_reviewed(path):
    tree = ast.parse(path.read_text())
    for fn, call in _calls(tree):
        f = call.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "subprocess" \
                and f.attr in {"run", "Popen", "call", "check_call", "check_output"}:
            where = (path.name, fn)
            assert where in GIT_ONLY | OTHER_ALLOWED, f"{path.name}:{call.lineno} starts a process in {fn}()"
            if where in GIT_ONLY:
                argv = call.args[0] if call.args else None
                assert isinstance(argv, ast.List) and isinstance(argv.elts[0], ast.Constant) \
                    and argv.elts[0].value == "git", f"{path.name}:{call.lineno} must start git"


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_sys_path_only_gains_the_plugins_own_directories(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in {"insert", "append"} and isinstance(node.func.value, ast.Attribute) \
                and node.func.value.attr == "path" and getattr(node.func.value.value, "id", None) == "sys":
            assert "__file__" in ast.unparse(node), f"{path.name}:{node.lineno}: {ast.unparse(node)}"


def test_the_hooks_run_only_the_plugins_scripts_without_site():
    """AC-5: python3 -S, so an active project venv's .pth files never run in a hook."""
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    commands = [h["command"] for group in hooks["hooks"].values() for m in group for h in m["hooks"]]
    assert commands and all("${CLAUDE_PLUGIN_ROOT}/scripts/" in cmd for cmd in commands)
    assert all(cmd.startswith("python3 -S ") for cmd in commands), commands


@pytest.mark.parametrize("path", ["agents/thunderstruck-investigator.md", "agents/thunderstruck-skeptic.md",
                                  "skills/thunderstruck-scan/SKILL.md"])
def test_instructions_say_it(path):
    assert c.NO_EXECUTION in (ROOT / path).read_text()


@pytest.mark.parametrize("path", ["agents/thunderstruck-investigator.md", "agents/thunderstruck-skeptic.md"])
def test_agents_cannot_run_anything(path):
    head = (ROOT / path).read_text().split("---")[1]
    tools = next(l for l in head.splitlines() if l.startswith("tools:")).split(":", 1)[1]
    assert {t.strip() for t in tools.split(",")} <= {"Read", "Grep", "Glob"}


TRAPS = {
    "setup.py": "import pathlib; pathlib.Path('{s}/setup.py').touch()\n",
    "conftest.py": "import pathlib; pathlib.Path('{s}/conftest.py').touch()\n",
    "sitecustomize.py": "import pathlib; pathlib.Path('{s}/sitecustomize.py').touch()\n",
    "trap/__init__.py": "import pathlib; pathlib.Path('{s}/trap_init').touch()\n",
    ".venv/lib/python3.12/site-packages/trap.pth": "import pathlib; pathlib.Path('{s}/pth').touch()\n",
    ".venv/lib/python3.12/site-packages/trap-1.0.dist-info/METADATA": "Name: trap\nVersion: 1.0\n",
    ".venv/lib/python3.12/site-packages/trap-1.0.dist-info/RECORD": "trap.pth,,\n",
    "Makefile": "all:\n\ttouch {s}/make\n",
    "build.gradle": "task x { doLast { new File('{s}/gradle').text = '' } }\n",
    "pom.xml": "<project><build><plugins/></build></project>\n",
    ".envrc": "touch {s}/envrc\n",
}
TOOLS = ["npm", "npx", "yarn", "pnpm", "pip", "pip3", "poetry", "mvn", "gradle", "gradlew", "make",
         "node", "java", "go", "cargo", "tox", "pytest"]


def test_no_stage_runs_anything_from_a_trapped_repository(validated_repo, validated_env, tmp_path):
    sentinels = tmp_path / "sentinels"
    sentinels.mkdir()
    for rel, body in TRAPS.items():
        p = validated_repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.replace("{s}", str(sentinels)))
    pkg = json.loads((validated_repo / "package.json").read_text())
    pkg["scripts"] = {k: f"touch {sentinels}/npm-{k}" for k in ("preinstall", "postinstall", "prepare")}
    pkg["dependencies"] = {"trap": "1.0.0"}
    (validated_repo / "package.json").write_text(json.dumps(pkg))
    (validated_repo / "requirements.txt").write_text("trap==1.0\n")
    shadow = tmp_path / "bin"
    shadow.mkdir()
    for tool in TOOLS:
        t = shadow / tool
        t.write_text(f"#!/bin/sh\ntouch {sentinels}/tool-{tool}\n")
        t.chmod(t.stat().st_mode | stat.S_IEXEC)
    env = {**validated_env, "PATH": f"{shadow}{os.pathsep}{validated_env.get('PATH', os.environ['PATH'])}",
           "VIRTUAL_ENV": str(validated_repo / ".venv")}
    steps = [["signals.py", "--top", "5"], ["bundle.py"], ["validate.py"],
             ["verify.py", "prepare", "--model", "sonnet"], ["verify.py", "apply"],
             ["report.py"], ["report_html.py"]]
    for step in steps:
        subprocess.run([sys.executable, str(SCRIPTS / step[0]), *step[1:], "--repo", str(validated_repo)],
                       capture_output=True, text=True, cwd=str(validated_repo), env=env)
    payload = {"tool_name": "Edit", "cwd": str(validated_repo), "session_id": "s",
               "tool_input": {"file_path": str(validated_repo / "src/sync/collection.ts")}}
    subprocess.run([sys.executable, str(SCRIPTS / "guardrail.py")], input=json.dumps(payload),
                   capture_output=True, text=True, cwd=str(validated_repo), env=env)
    assert sorted(p.name for p in sentinels.iterdir()) == []
```

The steps' exit codes are not asserted: a stage may legitimately fail on the trapped repository (an extra `pom.xml` with no sources, say). What is asserted is that nothing ran.

- [ ] **Step 2: Run them to verify which fail.** `uv run --with pytest --with pyyaml --with lizard --with packaging pytest tests/test_no_execution.py -q`. Expected: `test_instructions_say_it` FAILS for the investigator and the scan skill. If a static test fails on another script, read the call: a `git` call outside the allowlisted functions is moved into `_common.git`/`git_paths` (or the function is added to `GIT_ONLY` when it builds a git argv itself, with the AST check proving it); any other process start is a defect to fix, not to allowlist.

- [ ] **Step 3: Hooks without `site`.** In `hooks/hooks.json`, every command's `python3 ` becomes `python3 -S ` (the guardrail and #5's capture hook). Both are stdlib-only and import the plugin's modules by path, so nothing is lost; run `tests/test_guardrail.py` and #5's capture tests (latency included) to confirm.

- [ ] **Step 4: Write the sentence.** Add `c.NO_EXECUTION` verbatim to `agents/thunderstruck-investigator.md` (in the rules about repository content being data) and to `skills/thunderstruck-scan/SKILL.md` (in the rules the orchestrator follows, before step 1).

- [ ] **Step 5: Run the tests and the full suite.** Expected: PASS, `exit=0`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_no_execution.py agents/thunderstruck-investigator.md skills/thunderstruck-scan/SKILL.md hooks/hooks.json
git commit -m "Confirmed defaults: prove that no stage runs the scanned project (#57)"
```

---

### Task 12: A settings registry in the fixture, and the samples

**Satisfies:** AC-7 (the sample describes confirmed and unconfirmed defaults), AC-3 and AC-8 shown in the sample.

**Files:**
- Modify: `tests/fixtures/build_fixture.py` (`SETTINGS_REGISTRY`, `UNCHECKPOINTED_SYNC`, `FILES`, `HISTORY`)
- Modify: `scripts/gen_sample_report.py` (the canned collection finding's precondition; `CANNED_VERDICTS` for collection and api.ts)
- Modify: `examples/sample-report.md`, `examples/sample-report.html` (regenerated)
- Modify: `tests/test_pipeline.py`, `tests/test_docs_in_sync.py` (only where they count the fixture's files, hotspots or findings)
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: `gen_sample_report.CANNED_VERDICTS`, `build_validated` (#37); `_line_of(repo, rel, anchor)`.
- Produces: fixture files `src/config/settings.ts` and the page-size read in `src/sync/collection.ts`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 12 ----------------------------------------------------------------
SAMPLE = (ROOT / "examples" / "sample-report.md").read_text


def test_the_sample_shows_confirmed_contradicted_and_call_site_defaults():
    text = SAMPLE()
    assert "**Confirmed**" in text
    assert "a check found a different default registered" in text
    assert "relies on an unconfirmed default" in text
    assert "rests on a default no one confirmed: sync.pageSize" in text
    assert "Defaults: " in text


def test_the_unconfirmed_default_finding_is_listed_after_default_path_ones():
    """Badge lines in finding order: no marker, then the unconfirmed default, then the setting."""
    badges = [l for l in SAMPLE().splitlines() if l.startswith("**") and " confidence** · " in l]
    rank = [2 if c.GATE_MARKERS["non_default_setting"] in l
            else 1 if c.GATE_MARKERS["unconfirmed_default"] in l else 0 for l in badges]
    assert rank == sorted(rank) and 1 in rank and 2 in rank
    collection = next(i for i, l in enumerate(badges) if "collection.ts" in l)
    assert rank[collection] == 1
```

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL (the sample has none of it yet).

- [ ] **Step 3: The fixture** (already made in Task 5; check it is as below). In `tests/fixtures/build_fixture.py`:

```python
SETTINGS_REGISTRY = '''\
// Registered defaults. get() returns these when present; the fallback a
// caller passes applies only to keys that are not registered here.
const REGISTERED: Record<string, unknown> = {
  "sync.pageSize": 500,
};

export function get<T>(key: string, fallback: T): T {
  return key in REGISTERED ? (REGISTERED[key] as T) : fallback;
}
'''
```

`UNCHECKPOINTED_SYNC` gains, after its first import, `import { get } from "../config/settings";`, a line `const PAGE_SIZE = get<number>("sync.pageSize", 100);` before `syncCollection`, and the page fetch passes it: `fetchCollectionPage(userId, page, PAGE_SIZE)`. Add `("src/config/settings.ts", SETTINGS_REGISTRY)` to `FILES`, and one `HISTORY` entry `("feat: page size from settings", ["src/config/settings.ts", "src/sync/collection.ts"])` placed before the entries from #56/#37 that later touch `collection.ts`, so S07 still fires and the collection file stays a hotspot. Run `uv run --with pytest --with pyyaml --with lizard pytest tests/test_pipeline.py -q` and adjust only counts that the new file changes.

- [ ] **Step 4: The canned findings and verdicts** (already made in Task 5; check them). In `scripts/gen_sample_report.py`, the canned collection finding gains:

```python
"preconditions": [{"setting": "sync.pageSize", "default": "100",
                   "default_ref": f"src/sync/collection.ts:{_line_of(repo, 'src/sync/collection.ts', 'sync.pageSize')}",
                   "needs": "default", "value": None, "documented": "no", "doc_ref": None}],
```

and its `failure_mode` or `trigger_condition` says the restart re-fetches pages of 100 items (so the precondition is what the claim rests on). In `CANNED_VERDICTS`, the collection verdict stays `upheld`, gains `"expect": "inconclusive"`, and gains:

```python
"confirmations": [{"setting": "sync.pageSize", "claim": None, "stated_ref": None, "found": "different",
                   "default": "500", "default_ref": "src/config/settings.ts:{registry_line}",
                   "reason": "The registry holds 500; get() returns it, so the fallback 100 never applies."}],
```

`expect` is the generator's, not the contract's: #37's generator fails (`SystemExit` naming the key) when a canned verdict settles to a status other than its `verdict`; change that guard to compare against `entry.get("expect", entry["verdict"])`, and pop `expect` before the verdict is saved (an unknown top-level key would make `apply` leave it `unchecked`). With `{registry_line}` filled by `_line_of(repo, "src/config/settings.ts", '"sync.pageSize": 500')` where the verdict is saved. The api.ts verdict (`narrowed`) gains a confirmation of `API_RETRY_ON_429`: `found: same`, `default: "false (unset)"`, `default_ref` = the canned precondition's `default_ref`, reason "Unset means false; nothing else registers it."

- [ ] **Step 5: Regenerate and run everything.**

```bash
uv run scripts/gen_sample_report.py
uv run scripts/gen_sample_report.py --check
```

Then the full suite. Expected: `--check` clean; PASS, `exit=0`. Read the regenerated `examples/sample-report.md` once: the collection finding is `inconclusive` with the reason naming `sync.pageSize`, marked, listed after the default-path findings and before the api.ts finding; its Preconditions line shows both `100` and `500` with their locations; api.ts shows **Confirmed**.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/build_fixture.py scripts/gen_sample_report.py examples/ tests/
git commit -m "Confirmed defaults: a settings registry in the fixture, shown in the sample (#57)"
```

---

### Task 13: Defaults in the benchmark run

**Satisfies:** AC-6 (the figures the PR reports are produced by code, not by hand).

**Files:**
- Modify: `scripts/verify.py` (`export_run`)
- Modify: `scripts/benchmark.py` (`score_defaults`, the defaults output)
- Modify: `tests/test_benchmark.py`
- Test: `tests/test_confirmed_defaults.py`

**Interfaces:**
- Consumes: #37's `export_run(repo)`; #55's `score_defaults(records, label_set)`, `figure`, `format_figure`, `basis_of`, `EFFECTIVE`.
- Produces: run records with `preconditions: [{"setting", "default", "confirmation"}]`; `score_defaults(...)["rows"][i]["confirmation"]` when the run gives one; `score_defaults(...)["confirmed_not_effective"]: list[{"key", "setting"}]` and `["confirmed"]: int`; `benchmark.upheld_on_wrong_default(records: dict, label_set: dict) -> list[{"key", "setting"}]`. #55's spec reserves both figures and the run record's `preconditions[].confirmation` (a one-line extension point the lead adds to #55); if it does not, stop and report it.

- [ ] **Step 1: Write the failing tests.** In `tests/test_benchmark.py`, after #55's Task 6 tests:

```python
def test_confirmed_defaults_that_are_not_effective_are_listed():
    s = _celery()
    k = _key("FR-015")
    m = b.score_defaults({k: {"preconditions": [
        {"setting": "result_backend_always_retry", "default": "True", "confirmation": "confirmed"},
        {"setting": "result_backend_max_retries", "default": "inf", "confirmation": "confirmed"}]}}, s)
    assert m["confirmed"] == 2
    assert m["confirmed_not_effective"] == [{"key": k, "setting": "result_backend_always_retry"}]
    assert {r["setting"]: r.get("confirmation") for r in m["rows"] if r["key"] == k}[
        "result_backend_max_retries"] == "confirmed"


def test_upheld_findings_on_a_wrong_or_unstated_default_are_listed():
    s = _celery()
    k15, k16 = _key("FR-015"), _key("FR-016")
    records = {
        k15: {"verdict": "upheld", "preconditions": [
            {"setting": "result_backend_always_retry", "default": "True"}]},   # max_retries not stated
        k16: {"verdict": "upheld", "preconditions": []},                       # no discriminating label
    }
    got = b.upheld_on_wrong_default(records, s)
    assert {"key": k15, "setting": "result_backend_always_retry"} in got
    assert {"key": k15, "setting": "result_backend_max_retries"} in got
    assert all(x["key"] != k16 for x in got)
    assert b.upheld_on_wrong_default({k15: {"verdict": "narrowed"}}, s) == []
```

In `tests/test_confirmed_defaults.py`:

```python
# --- Task 13 ----------------------------------------------------------------
def test_export_run_carries_the_checks_defaults(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(found="different", default="500", default_ref=f"src/config/settings.ts:{reg}")]))
    _apply(validated_repo, validated_env)
    run = verify.export_run(validated_repo)
    assert run["findings"][e["key"]]["preconditions"] == [
        {"setting": "sync.pageSize", "default": "500", "confirmation": "unconfirmed"}]
    assert "verdict" not in run["findings"][e["key"]]  # inconclusive carries none (#37)
```

- [ ] **Step 2: Run them to verify they fail.** Expected: FAIL (`KeyError: 'confirmed'`, no `preconditions` in the record).

- [ ] **Step 3: Implement.** In `verify.export_run`, for each key, after `record["duplicate_of"] = …`:

```python
        finding = c.with_confirmations({**items.get(key, {}), "check": check}, check.get("confirmations"))
        pres = []
        listed = {it.get("precondition"): it for it in finding["check"].get("confirmations") or []}
        for j, p in enumerate(finding.get("preconditions") or []):
            it = listed.get(j)
            default = it["default"] if it and it.get("default") is not None else p.get("default")
            pres.append({"setting": p.get("setting"), "default": default,
                         "confirmation": p["confirmation"]["state"]})
        for it in finding["check"].get("confirmations") or []:
            if it.get("precondition") is None and it.get("default") is not None:
                pres.append({"setting": it["setting"], "default": it["default"],
                             "confirmation": it["confirmation"]["state"]})
        if pres:
            record["preconditions"] = pres
```

In `benchmark.score_defaults`, keep each stated precondition's `confirmation` (`stated_conf = {name: p.get("confirmation") …}` built like `stated`); each row gains `"confirmation": stated_conf.get(name)` when not `None`; after the loop:

```python
    confirmed = [x for x in rows if x.get("confirmation") == "confirmed"]
    wrong = [{"key": x["key"], "setting": x["setting"]} for x in confirmed if x["outcome"] != EFFECTIVE]
    return {..., "confirmed": len(confirmed), "confirmed_not_effective": wrong}
```

Add:

```python
def upheld_on_wrong_default(records: dict, label_set: dict) -> list[dict]:
    """Upheld findings whose label has a discriminating precondition the run did not
    state at its effective value: the ticket's success measure, counted directly."""
    out = []
    for k, r in sorted(records.items()):
        if r.get("verdict") not in ("upheld", "upheld_but_gated"):
            continue
        stated = {str(p.get("setting", "")).strip().casefold(): p.get("default")
                  for p in r.get("preconditions") or []}
        for pc in label_set["_by_key"][k].get("preconditions") or []:
            if pc["kind"] != "setting" or values_match(pc["literal"], pc["effective"]):
                continue
            name = pc["setting"].casefold()
            if name not in stated or not values_match(normalise_value(stated[name]), pc["effective"]):
                out.append({"key": k, "setting": pc["setting"]})
    return out
```

and print it as a figure over the run's upheld findings, `figure("upheld on a default not stated at its effective value", len(found keys), upheld count, basis)`, listing keys and settings. Where `benchmark.py` prints the defaults measure, also add one figure line when `confirmed` is non-zero: `figure("confirmed defaults that are not effective", len(wrong), confirmed, basis)` through `format_figure`, and list the keys and settings (no prose; #55 §9).

- [ ] **Step 4: Run the tests and the full suite.** Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify.py scripts/benchmark.py tests/test_benchmark.py tests/test_confirmed_defaults.py
git commit -m "Confirmed defaults: carry confirmations into benchmark runs (#57)"
```

---

### Task 14: Documentation and release

**Satisfies:** AC-7.

**Files:**
- Modify: `README.md` (*Findings are falsifiable, and checked*; *Privacy*), `CLAUDE.md`, `skills/thunderstruck-scan/references/report-format.md`, `skills/thunderstruck-verify/SKILL.md` (one sentence), `CHANGELOG.md`, `pyproject.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1: README.** Under *Findings are falsifiable, and checked*, a paragraph: every default a finding relies on is shown as confirmed or unconfirmed with why; a default stated at the line that reads the setting with a fallback argument is flagged mechanically, because a settings layer may hold another value; a finding resting on an unconfirmed default is never reported upheld and is listed after default-path findings, marked. Under *Privacy*: thunderstruck never runs, imports, installs or builds the project it scans; it starts `git`, and the catalog command you approved by hash (even when that command is a script in the repository, it runs only as approved); its hooks start Python with `-S`.

- [ ] **Step 2: CLAUDE.md.** In *Things that will bite you*, a paragraph:

```markdown
**A default is confirmed only by a check.** `validate.py` writes each
precondition's `confirmation` on every run from the fallback-read rule
(`setting_reads` in the catalog, `_common.reads_with_fallback`); only a
skeptic's item whose location resolves, is not a fallback read and says
`same` confirms one (`_common.confirm`, the one rule). `report.py` re-derives
confirmations from stored facts; never read a stored state. `verify.settle`
turns `upheld` into `inconclusive` when a `needs: default` precondition is
unconfirmed. Gates sort `none`, `unconfirmed_default`, `non_default_setting`.
```

In *The catalog is the source of truth*, one line: `setting_reads` patterns follow the negative-control discipline; every language needs a positive and a negative case in `READS`. In *Architecture*, after the pipeline diagram: "No stage runs, imports or builds the scanned project; `tests/test_no_execution.py` holds every script to that."

- [ ] **Step 3: report-format.md.** Document `preconditions[].confirmation` (keys, states, bases), `check.confirmations[]` (keys, `precondition`, `default_url`), the verdict key `confirmations`, `counts.defaults`, the third gate and its marker, and `index.json`'s `confirmation`.

- [ ] **Step 4: thunderstruck-verify.** One sentence at the top of its *Scope*: "This skill runs the project's tests because you asked; it is not part of a scan, and nothing it produces feeds one." (Pending the ticket's open product question; if the maintainer decides otherwise, this step follows the decision.)

- [ ] **Step 5: Version and CHANGELOG.** Bump the minor version in all four places (the next minor above `main`'s) and add under it:

```markdown
### Added
- Every default a finding relies on is shown as confirmed or unconfirmed, with why (#57).
  A default stated at a fallback argument where the setting is read is flagged
  mechanically; the skeptic confirms a default only by citing where it is registered.
- Findings resting on an unconfirmed default are never `upheld`, and are listed after
  default-path findings, marked "relies on an unconfirmed default".
- A test proves no scan stage runs, imports or builds the scanned project.
```

- [ ] **Step 6: Verify everything.**

```bash
uv run --with pytest --with pyyaml --with lizard --with packaging --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
uv run scripts/gen_catalog_docs.py --check
uv run scripts/gen_sample_report.py --check
claude plugin validate . --strict
claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck
claude plugin list
```

Expected: `exit=0`; both checks clean; validate clean; `claude plugin list` says `enabled`.

- [ ] **Step 7: Commit**

```bash
git add README.md CLAUDE.md skills/ CHANGELOG.md pyproject.toml .claude-plugin/
git commit -m "Confirmed defaults: documentation and release (#57)"
```

- [ ] **Step 8: Stop: ready for maintainer measurement.** Push the branch and open the PR as a **draft** whose description starts with "Do not merge before Task 15 (maintainer measurement on #55, spec §13.2)". It must not contain "Close #57", "Fixes #57" or any other closing keyword. Comment on #57: "Ready for maintainer measurement: Task 15 of the plan", with the PR link. Tick Tasks 0–14 in the ticket's checklist; Task 15 stays open until the maintainer commits it on this branch.

---

### Task 15: On #55's frozen set (maintainer, with the plugin installed)

**An agent building this plan stops after Task 14.** This task runs a model against a Celery checkout and is done by the maintainer.

**Satisfies:** AC-6.

**Files:**
- Create: `docs/calibration/correctness/celery/runs/confirmed-defaults-<alias>.json`
- Modify: `docs/calibration/verification.md` (new section "Defaults")

Done in a Claude Code session after #37's measurement task has set the default skeptic model (`<alias>`).

- [ ] **Step 1: Prepare.** A Celery checkout at `508c1129269d2b1baffc516d8f5c05da06273ef0` with the `.venv` of #37 §13 (kombu 5.7.0a1, py-amqp 5.4.0, billiard 4.3.0, redis 8.1.0, SQLAlchemy 2.1.3). From it:

```bash
uv run <thunderstruck>/scripts/verify.py prepare --frozen <thunderstruck>/docs/calibration/correctness/celery/scan --model <alias>
```

- [ ] **Step 2: Run the skeptics** with #37's step 4b loop (at most four at a time, none re-spawned), then:

```bash
uv run <thunderstruck>/scripts/verify.py apply
uv run <thunderstruck>/scripts/verify.py export-run --out <thunderstruck>/docs/calibration/correctness/celery/runs/confirmed-defaults-<alias>.json
uv run <thunderstruck>/scripts/benchmark.py --run docs/calibration/correctness/celery/runs/confirmed-defaults-<alias>.json
```

- [ ] **Step 3: Record**, in `docs/calibration/verification.md` under "Defaults", with `benchmark.py`'s lines quoted as printed:

1. FR-015's status (must not be `upheld`) and the state and basis of its `result_backend_always_retry` and `result_backend_max_retries` items (each `unconfirmed`: `contradicted` or `call_site_fallback`). If FR-015 is `upheld` or either default is `confirmed`, stop: AC-6 is not met, and the cause (the skeptic's items in `verdicts.json`) goes in the PR.
2. The defaults measure: counts over the five discriminating preconditions and over the rest.
3. `confirmed defaults that are not effective` and `upheld on a default not stated at its effective value`: both expected 0 (success measure).
4. #37 AC-12's same-class count on this run, and every finding whose `check.reason` starts "The check upheld this claim, but it rests on a default no one confirmed", with its label (§19 q3).
5. The skeptics' consumption from `usage.json`, beside #37's figure for the same model.

Copy local paths out as #53 did (`<celery>`, `<thunderstruck>`).

- [ ] **Step 4: Commit**

```bash
git add docs/calibration/correctness/celery/runs/confirmed-defaults-*.json docs/calibration/verification.md
git commit -m "Confirmed defaults: measured on the Celery benchmark (#57)"
```
