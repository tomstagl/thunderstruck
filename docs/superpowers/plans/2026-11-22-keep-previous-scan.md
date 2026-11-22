# A re-scan keeps the scan it replaces: Implementation Plan

> For agentic workers: build task by task, test first. Steps use checkbox (`- [x]`) syntax.

**Ticket:** #98. **Spec:** `docs/superpowers/specs/2026-11-22-keep-previous-scan-design.md`. Each task names the `AC-n` of the ticket it satisfies. A design change goes in the spec first.

**Goal:** a re-scan never loses the finished scan it replaces without saying so and keeping a copy, and a window can be repeated.

**Branch:** named by whoever builds it; the agent uses `agent/98-keep-previous-scan`. Stage explicit paths only. Do not bump the version (maintainer's call, 2026-11-22); add the change under `## Unreleased` in `CHANGELOG.md`.

**#103 depends on this ticket** (its AC "a re-scan keeps these records" reads `previous/`). Do not widen the archive list for it here.

## Task 0: anchors (no AC)

- [x] Read the spec. Confirm: `signals.py` writes `hotspots.json` in `main` after printing warnings and has `--since` default `"12m"`; `window` and `config` keys as the spec lists; `report_html.py` has the schema refusal; `report.py` prints `hotspots["warnings"]` under Run warnings.
- [x] `git grep -n "generated_at" scripts/report.py | head` to find the finished-scan rule used for `checks/run.json`, and reuse that helper, not a second copy.
- [x] Run `tests/test_signals*.py` and `tests/test_report*.py`: note they pass.

## Task 1: the scan identity and the finished test (AC-1, AC-2)

**Files:** `scripts/_common.py`, `tests/test_previous_scan.py` (new).

- [x] Failing tests for `c.scan_identity(hotspots_doc)` (returns the tuple of spec §2.1, `None` for a document missing a part) and `c.scan_finished(out_dir)` (true only when `report.json` exists and its `scanned_at` equals `hotspots.json`'s `generated_at`).
- [x] Implement both in `_common.py`. Commit `scripts/_common.py` and the test file. `AC-1, AC-2`, `Task: 1`.

## Task 2: the archive (AC-1, AC-2, AC-5)

**Files:** `scripts/previous.py` (new, stdlib and `_common`), `tests/test_previous_scan.py`.

- [x] Failing tests, each building an `.thunderstruck/` by hand: archive copies exactly the paths of spec §2.2 with the old bytes; names by old date and head, with `-2` on a clash; does nothing for an equal identity and for an unfinished scan; keeps 3 and removes only matching directory names; a symlinked `previous/` is skipped with a warning; a failing copy (monkeypatch `shutil.copy2` to raise) leaves no partial directory and returns a warning.
- [x] Implement `previous.archive(repo, new_identity) -> {"archived": name|None, "warning": str|None, "previous": {...}|None}`. No model, no network, no execution of the scanned project (`tests/test_no_execution.py` must still pass; add `previous.py` to its stage list as the test dictates).
- [x] Commit `scripts/previous.py` and the tests. `AC-1, AC-2, AC-5`, `Task: 2`.

## Task 3: signals writes it, and `--since previous` (AC-1, AC-3)

**Files:** `scripts/signals.py`, `tests/test_previous_scan.py`.

- [x] Failing tests through `signals.py` on the fixture (`tests/fixtures/build_fixture.py`): a second run with a different `--top` archives and warns with the spec's sentence; `hotspots.json` has `previous`; `--since previous` resolves to the first run's `since_date`; with no earlier scan it exits 2 with the message of §2.4; a bare re-run on a later date (monkeypatch the clock the way existing tests do) prints the window sentence.
- [x] Change `--since` to default `None` with the resolution of spec §2.4; call `previous.archive` just before `c.write_json(dest, payload)`; append the warning(s) to `payload["warnings"]` before they are printed (the warnings are printed after the write today: keep that order, and add them to the payload first).
- [x] Bundles stay identical: run `tests/test_bundles*` (the determinism test). Commit by path. `AC-1, AC-3`, `Task: 3`.

## Task 4: the report and the renderer say it (AC-4, AC-6)

**Files:** `scripts/report.py`, `scripts/report_html.py`, tests.

- [ ] Failing tests: Run warnings carries the replaced-scan line (inert text; it is built from stored values and goes through `mdtext`); `report_html.py` with a stored `report.json` of another schema prints the `previous/` sentence of spec §2.5, and prints the "not kept" variant when no `previous/` exists.
- [ ] Implement. `uv run scripts/gen_sample_report.py --check` must stay 0 (the fixture has no earlier scan).
- [ ] Commit by path. `AC-4, AC-6`, `Task: 4`.

## Task 5: the skill, docs and checks (AC-7)

- [ ] `skills/thunderstruck-scan/SKILL.md` Arguments: `--since previous`; step 1: relay the replaced-scan and window lines, and when an earlier scan exists and the user gave no `--since` and can be asked, offer `--since previous` once. README and CLAUDE.md ("Output lands in `.thunderstruck/`") name `previous/`. `CHANGELOG.md` under `## Unreleased`.
- [ ] Run the full suite (CLAUDE.md command), both `--check` generators, `uv run scripts/validate_plugin.py`. All pass before any push.
- [ ] Commit. `AC-7`, `Task: 5`.
