# A reproduction is recorded, shown and kept: Implementation Plan

> For agentic workers: build task by task, test first. Steps use checkbox (`- [ ]`) syntax.

**Ticket:** #103. **Spec:** `docs/superpowers/specs/2026-11-22-record-reproductions-design.md`. Each task names the `AC-n` of the ticket it satisfies. A design change goes in the spec first.

**Goal:** the outcome of `/thunderstruck-verify` is stored by a script, shown beside the skeptic's verdict and in the guardrail, and kept across re-scans.

**Branch:** named by whoever builds it; the agent uses `agent/103-record-reproductions`. Stage explicit paths only. Do not bump the version (maintainer's call, 2026-11-22); add the change under `## Unreleased` in `CHANGELOG.md`.

**Depends on #98.** Build on a `main` where #98 has merged.

## Task 0: anchors (no AC)

- [x] Read the spec. Confirm: `report.py` `render_index` (`:1460` region) and what it writes per finding; `guardrail.py` around `:247`; the verify skill's Scope paragraph; `c.tracked_file_problem` in `_common.py`.
- [x] Find how earlier additive finding fields were added to `report.json`: `git log --oneline -S'"impact"' -- scripts/report.py` and whether `REPORT_SCHEMA_VERSION` moved. Follow that practice for the `reproduction` key; if a bump is needed, stop and amend the spec first, because a bump changes #98's scan identity.
- [x] Run `tests/test_guardrail.py`, `tests/test_report*.py`, `tests/test_no_execution.py`: note they pass.

## Task 1: the script and its record (AC-1)

**Files:** `scripts/reproduction.py` (new, stdlib and `_common`), `tests/test_reproduction.py` (new), `tests/test_no_execution.py`.

- [x] Failing tests of spec §5 for the script (each status, each refusal, hash and head stored, never runs the command, a trapped `conftest.py`).
- [x] Implement `record`, and `show --key K` printing the record. Add `reproduction.py` to the stage list `test_no_execution.py` expects, as that test dictates.
- [x] Commit `scripts/reproduction.py`, `tests/test_reproduction.py`, `tests/test_no_execution.py` by path. `AC-1`, `Task: 1`.

## Task 2: current or stale (AC-1, AC-5)

**Files:** `scripts/_common.py` or `scripts/reproduction.py` (a `state(repo, record, finding)` function), tests.

- [ ] Failing tests: current; stale by test change; stale by finding `content_hash` change; test file gone; record for an absent key ignored and kept.
- [ ] Implement. Commit. `AC-1, AC-5`, `Task: 2`.

## Task 3: the report (AC-2)

**Files:** `scripts/report.py`, `scripts/report_html.py`, `templates/report.html`, `tests/test_report_reproduction.py` (new), `tests/test_report_html_browser.py`.

- [ ] Failing tests: the additive `reproduction` key in `report.json`; the exact wording of spec §2.3 in `report.md` and `report.html`, through `mdtext` (a hostile `command` is inert); stale shown first; no record, no key, no line.
- [ ] The no-effect test: with and without a record, `effective_confidence`, gates, ordering, every bundle and every skeptic brief are byte-identical.
- [ ] Implement. Browser test: `THUNDERSTRUCK_REQUIRE_BROWSER=1` command from CLAUDE.md.
- [ ] `uv run scripts/gen_sample_report.py --check` stays 0 (decide whether to show a record in the sample; if yes, regenerate in this task and say so in the commit).
- [ ] Commit by path. `AC-2`, `Task: 3`.

## Task 4: the guardrail (AC-3)

**Files:** `scripts/report.py` (`render_index`), `scripts/guardrail.py`, `tests/test_guardrail.py`.

- [ ] Failing tests: `index.json` carries the summary; the guardrail says `reproduced by a recorded failing test (<path>)` for a current one, says stale or passes as that, keeps the old sentence for findings without a record; the text is not imperative (reuse the existing phrasing test); latency under budget; stdlib-only AST check.
- [ ] Implement. Commit. `AC-3`, `Task: 4`.

## Task 5: the verify skill and docs (AC-4)

- [ ] `skills/thunderstruck-verify/SKILL.md`: call `reproduction.py record` after the user's run; amend the Scope sentence per spec §2.5. Pin both in a test beside `test_skeptic_contract.py`.
- [ ] README, CLAUDE.md (the report and guardrail paragraphs: the record is display only), `report-format.md` if it lists finding fields. `CHANGELOG.md` under `## Unreleased`.
- [ ] Full suite (CLAUDE.md command, with the browser tests), both `--check` generators, `uv run scripts/validate_plugin.py`. All pass before any push.
- [ ] Commit. `AC-4`, `Task: 5`.
