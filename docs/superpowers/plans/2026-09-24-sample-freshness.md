# Sample Freshness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The sample report is byte-reproducible on any machine, and CI fails when it is stale.

**Architecture:** Git isolation lives in `build_fixture`. Date pinning, dependency pins and the check mode live in `gen_sample_report.py`. A CI step runs the check on each supported Python. No production script changes.

**Spec:** `docs/superpowers/specs/2026-09-24-sample-freshness-design.md` (§n below refers to it). Requirements AC-1…AC-7 are in GitHub issue #26.

**Branch:** `feat/sample-freshness`. One commit per task.

## Global constraints

- `signals.py`, `context.py`, `bundle.py`, `validate.py`, `report.py` and `guardrail.py` are not modified.
- Full suite on every commit: `uv run --with pytest --with pyyaml --with lizard pytest tests/ -q`.
- The sample is regenerated once, in Task 4, with the finished generator.

### Task 1: Isolate the fixture from git configuration (AC-1)

**Files:** modify `tests/fixtures/build_fixture.py`; create `tests/test_sample_report.py`.

- [ ] **Step 1:** Write `test_fixture_ignores_user_git_config`. It writes a hostile global config and template dir into `tmp_path` (spec §8), builds the fixture with `GIT_CONFIG_GLOBAL` pointing at that config and `GIT_DEFAULT_HASH=sha256` set via `monkeypatch.setenv`, then builds it again with `GIT_CONFIG_GLOBAL=/dev/null`. Both builds use the same `base_date`. Assert that both succeed and that `rev-parse HEAD` is equal.
- [ ] **Step 2:** Run it and confirm it fails: the hostile build either raises (signing via `gpg.program=false`) or differs.
- [ ] **Step 3:** Add `isolated_git_env(base=None)` (spec §3). Make `run()` default to it, pass it to the commit call, and init with `--template= --object-format=sha1 -b main`.
- [ ] **Step 4:** Run the full suite.
- [ ] **Step 5:** Commit: `Build the fixture with no user or system git configuration`.

### Task 2: Pinned dates, pinned dependencies, isolated pipeline (AC-1, AC-4, AC-5, AC-6)

**Files:** modify `scripts/gen_sample_report.py` and `tests/test_sample_report.py`.

- [ ] **Step 1:** Write the tests:
  - `test_pin_dates_rewrites_and_labels`;
  - `test_pin_dates_requires_exactly_one_match`, covering zero matches and two;
  - `test_real_report_never_prints_the_label`: run `report.py` on `scanned_copy` with a valid finding, and assert "dates fixed for this sample" is absent.
- [ ] **Step 2:** Implement:
  - `pin_dates(report, day)` (spec §4);
  - `generate()` computes `day` from `git log -1 --format=%cs` in the fixture;
  - it builds one `env = isolated_git_env()` plus the existing variables and passes it to every `_run` and `subprocess.run` (the `save_finding`, `validate` and `report` calls included);
  - the PEP 723 block pins `pyyaml==6.0.3` and `lizard==1.24.0`.
- [ ] **Step 3:** Run the full suite. Commit: `Pin the sample's dates and dependencies, and run its pipeline without user git config`.

### Task 3: A real check mode, run in CI (AC-2, AC-3)

**Files:** modify `scripts/gen_sample_report.py`, `.github/workflows/ci.yml` and `tests/test_sample_report.py`.

- [ ] **Step 1:** Write the tests for `check(dest, body) -> (ok, message)`: equal body passes; stale body gives a diff and "regenerate with"; missing file fails; a diff longer than 80 lines is truncated with a note.
- [ ] **Step 2:** Implement `check` and wire `--check` to it (spec §6). Add the CI step (spec §7).
- [ ] **Step 3:** Run the full suite. Commit: `Compare the sample report with a fresh generation, and check it in CI`.

### Task 4: Regenerate, docs (AC-4, AC-7)

**Files:** `examples/sample-report.md` (regenerated), `CLAUDE.md`, `CONTRIBUTING.md`, the header comment in `gen_sample_report.py`.

- [ ] **Step 1:** Update the header comment, then regenerate with `uv run scripts/gen_sample_report.py`. The diff may change only the header comment, the run line (fixed date plus label) and the context fetch line.
- [ ] **Step 2:** Verify AC-1 by hand:
  - regenerate under a hostile global config (signing on, hooks, `GIT_DEFAULT_HASH=sha256`) and check the file is unchanged;
  - run `--check` with `--python 3.11`, `3.12` and `3.13`;
  - stale the file by hand, confirm `--check` exits 1 with a diff, then restore it.
- [ ] **Step 3:** Update the docs (spec §9).
- [ ] **Step 4:** Run the full suite, `gen_catalog_docs.py --check` and `gen_sample_report.py --check`. Commit: `Regenerate the sample with fixed dates and document the check`.

## AC coverage

| AC | Tasks |
|---|---|
| AC-1 | 1, 2, 4 (manual cross-config and cross-Python), CI matrix |
| AC-2 | 3 |
| AC-3 | 3 |
| AC-4 | 2, 4 |
| AC-5 | 2 |
| AC-6 | 2 |
| AC-7 | 4 |
