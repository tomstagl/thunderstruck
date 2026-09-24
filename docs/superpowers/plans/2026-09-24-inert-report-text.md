# Inert Report Text Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nothing a model or a scanned repository wrote can render as a link, image, HTML or report structure in `report.md`.

**Spec:** `docs/superpowers/specs/2026-09-24-inert-report-text-design.md`. Requirements AC-1…AC-6 are in GitHub issue #28.

**Branch:** `feat/inert-report-text`. One commit per task. Before every push, run the full suite on Python 3.11, 3.12 and 3.13, checking the real exit code:

```bash
for py in 3.11 3.12 3.13; do uv run --python $py --with pytest --with pyyaml --with lizard \
  --with markdown-it-py --with linkify-it-py pytest tests/ -q > /tmp/pt$py.log 2>&1; echo "$py rc=$?"; done
```

### Task 1: The primitives (AC-1, AC-2, AC-3)

**Files:** create `scripts/mdtext.py` and `tests/test_mdtext.py`.

- [ ] Write failing unit and renderer tests (spec §4).
- [ ] Implement `code`, `text` and `linked` (spec §2).
- [ ] Commit: `Add Markdown primitives that keep untrusted text inert`.

### Task 2: Use them for every untrusted value in the report (AC-1, AC-2, AC-4)

**Files:** `scripts/report.py`; create `tests/test_inert_report.py`.

- [ ] Write the failing end-to-end tests: hostile model fields, and hostile repository names (spec §4).
- [ ] Apply the table in spec §3. Move `_code`/`_linked` to `mdtext`, keeping thin aliases only if tests import them.
- [ ] Run the existing report and link tests unchanged. #22's links must render exactly as before (AC-4).
- [ ] Commit: `Render every model- and repository-written value in the report as inert text`.

### Task 3: CI, docs, sample, version (AC-5, AC-6)

**Files:** `.github/workflows/ci.yml` (the two `--with` flags and `THUNDERSTRUCK_REQUIRE_RENDERER=1`), `CLAUDE.md`, `CONTRIBUTING.md` (test command), `examples/sample-report.md` (regenerated), `CHANGELOG.md`, and version `0.5.1` in all four places.

- [ ] Regenerate the sample. Check that the diff only changes escaping, and that FR-003's text renders the same.
- [ ] Run the three-Python suite, `gen_catalog_docs.py --check`, `gen_sample_report.py --check` and `claude plugin validate . --strict`.
- [ ] Commit: `Require the renderer tests in CI; regenerate the sample; bump to 0.5.1`.

## AC coverage

| AC | Tasks |
|---|---|
| AC-1 | 1, 2 |
| AC-2 | 1, 2 |
| AC-3 | 1 |
| AC-4 | 2 |
| AC-5 | 3 |
| AC-6 | 1, 2, 3 |
