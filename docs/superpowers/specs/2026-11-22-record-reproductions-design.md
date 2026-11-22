# A reproduction is recorded, shown and kept: design

**Requirements:** [#103](https://github.com/tomstagl/thunderstruck/issues/103). The problem, stories, scope and acceptance criteria (AC-n) are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-22-record-reproductions.md`.
**Depends on:** #98 (its archive keeps a replaced scan; this ticket's records live outside what a scan replaces and need nothing from it, but AC-5 is only meaningful once a re-scan's handling is defined).
**Evidence:** `skills/thunderstruck-verify/SKILL.md` ("Scope": "nothing it produces feeds [a scan]", "diagnosis and remedy are kept apart"); `scripts/guardrail.py:247` ("hypotheses from a past scan, not verified defects"); `scripts/report.py:1460` (`render_index` writes `index.json`, the guardrail's only input); CLAUDE.md "Confidence is capped by check status, never by history" and "The guardrail's hard constraints".

## 1. What is wrong

`/thunderstruck-verify` ends at a failing test. The outcome lives only in a hand-written Markdown file no script reads. A finding that was reproduced looks, in `report.json`, `report.md`, `report.html` and the guardrail, exactly like one nobody ran, and the guardrail calls it an unverified hypothesis while it edits the very lines.

This ticket records the outcome and shows it. The simulation of a fix, which the reporter also proposed, is a separate feature with its own risks (it edits the scanned tree) and is a separate ticket (see §6).

## 2. Decisions

### 2.1 One record per finding key, in a directory no scan replaces

`.thunderstruck/reproductions/<key>.json`, written only by a new script, `scripts/reproduction.py`:

```json
{"schema": "thunderstruck.reproduction/v1", "key": "…", "status": "fails_as_predicted",
 "test": {"path": "tests/test_x.py", "sha256": "…"}, "command": "pytest tests/test_x.py -q",
 "head": "8491915…", "finding_hash": "…", "recorded_at": "2026-11-22T…"}
```

`status` is `fails_as_predicted`, `passes` (the hypothesis does not hold as tested) or `blocked` (the test could not be made to run). `command` is the one the user ran, at most 300 characters, stored as text and never executed by any script. One record per key: a new run replaces it, and the previous file is not kept.

`reproduction.py record --key K --status S --test PATH --command CMD` checks: `K` is a key in the current `report.json`; `PATH` is a regular file inside the repository (`c.tracked_file_problem`-style `lstat` rules, no symlink, no `..`); the status is one of the three. It stores the test file's SHA-256, the repository's `HEAD` and the finding's `content_hash` from `report.json` (as `finding_hash`). It runs and imports nothing from the repository. **It cannot know the test failed**: it records what the verify session says happened. The report says so (§2.3), and only a user-run test is behind a `fails_as_predicted`.

`scripts/reproduction.py` is a command the verify skill calls after it has run the test, with the exit it saw. The skill's "Scope" sentence changes (§2.5).

### 2.2 Records survive a re-scan, and say when they no longer apply

Nothing a scan does deletes `reproductions/`. `report.py` reads the record for each finding's key and marks it:

- `current`: the record's test file hash equals the file's present hash, and `finding_hash` equals the finding's present `content_hash`.
- `stale`: either differs, or the test file is gone. The record is shown as stale, with which of the two changed, and is never deleted.
- A record whose key is in no finding of this scan is not shown and is not deleted.

This answers the ticket's "a re-scan keeps these records for findings whose key is unchanged". #98's archive does not copy `reproductions/` (a record is not part of the scan it follows).

### 2.3 Display only: it feeds nothing

The record appears in `report.json` as an additive `reproduction` object on a finding (`status`, `state` current|stale, `test_path`, `command`, `recorded_head`, `stale_because`), in `report.md` and `report.html` beside the check status, and in `index.json` for the guardrail. It never changes a rank, a confidence (`effective_confidence` is untouched), a check status, a verdict's reuse or a gate. It is not in a bundle or a skeptic's brief: a skeptic that is told the finding was reproduced stops trying to refute it. `test_labels_never_reach_the_pipeline`-style tests pin that (§5).

Wording, always the same, built from stored values and passed through `mdtext`: `Reproduced by a failing test (recorded by /thunderstruck-verify; the scan did not run it): tests/test_x.py` for `fails_as_predicted`; `A recorded reproduction passed: the hypothesis did not hold as tested` for `passes`; `A reproduction was attempted and blocked` for `blocked`; each followed by `, stale: the test file changed` when stale. A stale `fails_as_predicted` is shown as stale first and never as reproduced.

`report.json` keeps its schema string: the key is additive and absent when there is no record. Task 0 of the plan checks how earlier additive fields (`impact`, `defaults`) were handled and follows that.

### 2.4 The guardrail

`index.json` gains the same `reproduction` summary per finding. The guardrail's text keeps `check status: <status>` and changes its closing statement from one sentence for all findings to: for each finding with a current reproduction, `reproduced by a recorded failing test (<path>)`; the sentence "These are hypotheses from a past scan, not verified defects" stays for any finding without one. Statements of fact, never instructions (the guardrail's constraint). A stale or `passes` record is stated as that. The guardrail stays stdlib-only, exits 0 and under 100 ms; it reads only `index.json`.

### 2.5 The verify skill

`skills/thunderstruck-verify/SKILL.md`: after the user's test run, the skill calls `reproduction.py record` with the status the run gave. Its Scope sentence "nothing it produces feeds [a scan]" becomes: nothing it produces changes what a scan finds, ranks or checks; `report.py` reads the record for display only. The "diagnosis and remedy are kept apart" paragraph stays.

## 3. Out of scope

Anything that edits the scanned tree (§6); the neighbouring tests; running a test from a script (`reproduction.py` never runs one); a record for a finding that is not in the current report.

## 4. Degradation

A malformed record is shown as `unreadable` and ignored by the guardrail. A missing `reproductions/` is no records. An unwritable directory is the script's error, exit 1, with the reason.

## 5. Test strategy

- `reproduction.py`: each status; refusals (unknown key, a path outside the repository, a symlink, an over-long command, an unknown status); the hash and head stored; it never runs the command (a trapped test file with a `conftest.py` that would fail the suite if imported; `tests/test_no_execution.py` lists the script).
- `report.py`: current, stale by test change, stale by finding change, record for an absent key; `report.json` additive key; the wording above, exactly, with a hostile command text rendered inert.
- No effect: with and without a record, `effective_confidence`, the gates, the ordering and every bundle and brief are byte-identical.
- Guardrail: current, stale, `passes`, none; the statement is not imperative; latency and the AST stdlib-only checks.
- `report.html` shows it (browser test as the existing ones).
- The sample report is regenerated with a record for its first finding only if the plan's Task 6 chooses to show it; otherwise unchanged (`--check`).

## 6. The fix simulation

The reporter's proposal (an opt-in step that applies a patch, runs the test and the neighbouring tests, reverts and saves the patch) is a separate ticket, filed as a DRAFT with the reporter's text. It needs this record, because it runs only for a finding whose reproduction is `fails_as_predicted`, and it must show the test file hash unchanged. Splitting it lets this ticket ship without a feature that edits the scanned tree. The original ticket's two acceptance criteria about the simulation (the tree left byte-identical, a changed test reported invalid) move with it.
