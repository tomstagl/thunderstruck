# Validator Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every path in a finding is one canonical, tracked, in-repository file, and every line range lies inside it. Findings validated under older rules are investigated again.

**Architecture:** `_common` gains canonical-path helpers and a rules version. `validate.py` resolves paths against the git index, checks every range, and writes canonical paths back. `bundle.py` stops caching findings validated under older rules. The prompts state the accepted forms.

**Spec:** `docs/superpowers/specs/2026-09-24-validator-gaps-design.md` (§n below refers to it). Requirements AC-1…AC-7 are in GitHub issue #25.

**Branch:** `feat/validator-gaps`. One commit per task. The full suite passes on every commit: `uv run --with pytest --with pyyaml --with lizard pytest tests/ -q`.

### Task 1: Canonical paths, tracked files only (AC-2, AC-3)

**Files:** `scripts/_common.py`, `scripts/validate.py`; new `tests/test_validate_paths.py`; `tests/test_links.py` (the `../` expectation).

- [ ] Write failing tests for every path case in spec §9, including the `Path.open` spy.
- [ ] Implement `ref_path` (leading `./` only), `path_problem`, the `Validator` index load (`git ls-files -s -z`) and `_resolve` (spec §2–§3). `check_finding` and `check_evidence` (code refs) use `_resolve`.
- [ ] Update `test_links.py`: `../src/x.ts` now stays `../src/x.ts`, and it is unlinked because it escapes.
- [ ] Run the full suite, then commit: `Resolve cited paths against the git index and reject paths that leave the repository`.

### Task 2: Line ranges (AC-1)

**Files:** `scripts/validate.py`, `tests/test_validate_paths.py`, `scripts/gen_sample_report.py` (clamp), `examples/sample-report.md` (regenerated).

- [ ] Write failing tests: the `location.lines` accept/reject table and a reversed code ref (spec §9).
- [ ] Implement `parse_range` and both checks, with the error texts in spec §4.
- [ ] In the generator, clamp the canned range end to the file length. Regenerate the sample: only the `api.ts` and `format.ts` locations change. Run `--check`.
- [ ] Run the full suite, then commit: `Check every line range, including a finding's location`.

### Task 3: One identity per file (AC-4, AC-5)

**Files:** `scripts/validate.py`, `tests/test_validate_paths.py`.

- [ ] Write failing tests:
  - `./src/a.ts` is written back canonical, and its key equals the key for `src/a.ts`;
  - after `report.py`, `index.json` has a single entry for the file;
  - a finding without `./` keeps its key.
- [ ] Implement the write-back canonicalisation (spec §5).
- [ ] Run the full suite, then commit: `Write canonical paths back, so a file has one key and one index entry`.

### Task 4: Re-investigate findings validated under older rules (AC-7)

**Files:** `scripts/_common.py` (`VALIDATION_RULES`), `scripts/validate.py` (stamp), `scripts/bundle.py`, new tests in `tests/test_validate_paths.py`.

- [ ] Write failing tests on the fixture:
  - a validated doc without the stamp makes its bundle not cached;
  - a stamped doc is cached;
  - a clean doc is cached;
  - `bundle.py` prints the re-queued count.
- [ ] Implement the changes in spec §6.
- [ ] Run the full suite, then commit: `Re-investigate findings validated under older rules`.

### Task 5: Prompts, docs, version (AC-6)

**Files:** `agents/thunderstruck-investigator.md`, `skills/thunderstruck-scan/SKILL.md`, a test asserting the forms appear, `CHANGELOG.md`, and version `0.5.0` in all four places.

- [ ] Add the accepted-forms text (spec §7), and a test that looks for `"42-118"`, "tracked" and "no `./`" in both files.
- [ ] Add a CHANGELOG entry. It notes that findings from earlier scans are investigated again once.
- [ ] Run the full suite, `gen_catalog_docs.py --check`, `gen_sample_report.py --check` and `claude plugin validate . --strict`, then commit: `State the accepted path and line forms to the investigator; bump to 0.5.0`.

## AC coverage

| AC | Tasks |
|---|---|
| AC-1 | 2 |
| AC-2 | 1 |
| AC-3 | 1 |
| AC-4 | 3 |
| AC-5 | 2 (the sample still validates), 3 (keys) |
| AC-6 | 5 |
| AC-7 | 4 |
