# Missing Gate Setting Implementation Plan

**Ticket:** #144. **Spec:** `docs/superpowers/specs/2026-11-25-missing-gate-setting-design.md`. Every task names the `AC-n` it satisfies. A design change goes in the spec first.

**Goal:** A skeptic is shown how to name the setting a failure needs, a gate it names without one is visible as that, and the effect is measured on both benchmark sets.

**Branch:** `feat/144-gate-setting`. Stage explicit paths only. Whole suite: the command in CLAUDE.md "Commands".

## Task 0: prediction and the before arm (AC-3, AC-4, AC-5)

- [ ] Commit the spec and this plan. The prediction (spec §7) is in that commit, before any run.
- [ ] Check the plugin is enabled from this checkout and `agents/thunderstruck-skeptic.md` equals `main`'s.
- [ ] Three Celery runs and three holdout runs (spec §7). Save each run's `checks/results/`, `checks/plan.json`, `deps/index.json` and session id outside the repository.

## Task 1: a gate without a usable setting is named (AC-2)

**Files:** `scripts/verify.py`, `tests/test_verification.py`.

- [ ] Failing tests from spec §6, second and third items.
- [ ] `_gate_setting(rc, where, resolver) -> tuple[dict | None, str | None]` beside `_decide`, returning the normalised setting or the problem; `_decide` sets `kept["setting"]` or `kept["gate_problem"]` and appends the problem to `ignored`.

## Task 2: the reports say so (AC-2)

**Files:** `scripts/report.py`, `templates/report.html`, `tests/test_verification.py`, `tests/test_report_html.py`, `skills/thunderstruck-scan/references/report-format.md`.

- [ ] Failing tests; then one sentence in `_claim_lines` and in the template's `checkRows`.
- [ ] Document `gate_problem` beside `refuted_claims`.

## Task 3: the instructions show the setting (AC-1)

**Files:** `agents/thunderstruck-skeptic.md`, `tests/test_skeptic_contract.py`.

- [ ] Failing tests: the example settles to a gate; its words are in no frozen scan.
- [ ] The two edits of spec §2.

## Task 4: the after arm (AC-3, AC-4)

- [ ] Only `agents/thunderstruck-skeptic.md` differs from Task 0's plugin in what a skeptic sees. Three runs per set as in Task 0.

## Task 5: the record (AC-3, AC-4, AC-5)

**Files:** `docs/calibration/verification.md`, `docs/calibration/correctness/celery/runs/`, `CHANGELOG.md`.

- [ ] Settle all twelve runs with this branch's `verify.py`; `benchmark.py` on each export.
- [ ] Record spec §7's table beside the prediction, whatever it shows. Check in the Celery exports; the holdout is totals only.
- [ ] Whole suite, catalog and sample checks, `validate_plugin.py`.
