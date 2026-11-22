# The scan skill works when agents return in the background: Implementation Plan

> For agentic workers: build task by task, test first. Steps use checkbox (`- [ ]`) syntax.

**Ticket:** #97. **Spec:** `docs/superpowers/specs/2026-11-22-background-agents-design.md`. Each task names the `AC-n` of the ticket it satisfies. A design change goes in the spec first.

**Goal:** the scan skill says what to do whether an `Agent` call returns a result or a background launch, and the usage figure is never lost or invented.

**Branch:** named by whoever builds it; the agent uses `agent/97-background-agents`. Stage explicit paths only. Do not bump the version (maintainer's call, 2026-11-22); add the change under `## Unreleased` in `CHANGELOG.md`.

## Task 0: anchors (no AC)

- [x] Read the spec. Confirm in `skills/thunderstruck-scan/SKILL.md` the phrases "in the foreground" and "Never use agent teams" (step 3), "foreground, waiting for each batch" (the skeptic step), and the repair round text of step 4. Check `skills/thunderstruck-scan/references/orchestration.md` for the same phrases: `git grep -n -i "foreground\|background" -- skills agents docs/*.md README.md`. Any other place that says results return inline is part of Task 2.
- [x] Run `tests/test_no_execution.py` and `tests/test_skeptic_contract.py` (they read the skill) and note they pass.

## Task 1: pin the new behaviour (AC-1, AC-2, AC-3)

**Files:** `tests/test_scan_skill_background.py` (new).

- [x] Write the tests of spec §4 first: the skill contains the two-mode text (assert on short quoted phrases: `"launch acknowledgement"`, `"every agent of the batch"`, `"completion notification"`, `"without --usage"`); it still contains each forbidden thing under a never-sentence (`run_in_background`, `agent teams`, `SendMessage`, `ListAgents`, `poll`); steps 4 and 6 contain `"the rule of step 3"`.
- [x] And the executed one: `save_finding.py --id H01 --from <result> --fallback` with no `--usage`, then `usage.py`; `usage.json` has `source: "partial"` and `missing` names H01 (copy the fixture setup of `tests/test_usage.py`).
- [x] Run: the skill-text tests fail; the executed one passes (it documents existing behaviour).
- [x] Commit `tests/test_scan_skill_background.py` by path. `AC-1, AC-2, AC-3`, `Task: 1`, red line.

## Task 2: the skill text (AC-1, AC-2, AC-3)

**Files:** `skills/thunderstruck-scan/SKILL.md`, and any file Task 0 found.

- [x] Step 3, "How to run them": replace the foreground sentence with the two modes of spec §2.1; replace the "Never use … background agents" bullet with spec §2.3's wording; add the batch-complete rule; in the fallback paragraph, take `--usage` "from the completion notification (or the inline result)" and add the no-`--usage` sentence of spec §2.2, plus "never invent a figure". Add the missing-notification sentence of spec §3.
- [x] Step 4 (repair round) and step 6 (skeptics): say "as in step 3, in either mode" and "the rule of step 3" instead of "foreground".
- [x] Tests of Task 1 pass; `tests/test_no_execution.py`, `tests/test_skeptic_contract.py` and the docs-in-sync tests pass.
- [x] Commit by path. `AC-1, AC-2, AC-3`, `Task: 2`.

## Task 3: record it and verify (AC-4)

- [ ] `CHANGELOG.md` under `## Unreleased`: "The scan skill says what to do when agents return in the background (#97)." CLAUDE.md needs no change unless Task 0 found a sentence there.
- [ ] Run the full suite (CLAUDE.md command), `uv run scripts/gen_sample_report.py --check`, `gen_catalog_docs.py --check`, `uv run scripts/validate_plugin.py`. All pass before any push.
- [ ] Commit. `AC-4`, `Task: 3`.
