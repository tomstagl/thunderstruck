# Hotspot Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Link every file in the ranked hotspots table and in the clean and incomplete lists to the scanned commit, and link each hotspot to its change history.

**Spec:** `docs/superpowers/specs/2026-09-24-hotspot-links-design.md`. Requirements AC-1…AC-7 are in GitHub issue #24.

**Branch:** `feat/hotspot-links`. One commit per task. Before every push, run the full suite on Python 3.11, 3.12 and 3.13, checking the real exit code:

```bash
for py in 3.11 3.12 3.13; do THUNDERSTRUCK_REQUIRE_RENDERER=1 uv run --python $py --with pytest \
  --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 \
  --with cmarkgfm==2025.10.22 pytest tests/ -q > /tmp/pt$py.log 2>&1; echo "$py rc=$?"; done
```

### Task 1: History links and the summarised warning in `links.py` (AC-2, AC-3)

**Files:** `scripts/links.py`, `tests/test_links.py`.

- [ ] Write the failing tests (spec §5, `test_links.py`), plus a unit test for the five-name warning.
- [ ] Add the history template to `TEMPLATES`, `LinkContext.history_tpl`, and `LinkContext.history()` (spec §2.1).
- [ ] Summarise the stale-file warning (spec §2.2).
- [ ] Commit: `Add file-history links and cap the stale-file warning at five names`.

### Task 2: Link the hotspot, clean and incomplete entries (AC-1, AC-3, AC-4, AC-5, AC-6)

**Files:** `scripts/report.py`, `tests/test_report_links.py`, `tests/test_inert_report.py`.

- [ ] Write the failing end-to-end tests (spec §5): hotspots, no findings, incomplete, the stale cases, the warning cap, no remote and disabled, templates, and JSON.
- [ ] Extend `link_refs` and `collect()` (spec §3.1).
- [ ] Render the links in `report.md` (spec §3.2), and add the URLs to `report.json` (spec §3.3).
- [ ] Update `test_a_report_without_findings_says_nothing_about_links` for the new signature. An empty report still returns nothing.
- [ ] Commit: `Link ranked hotspots, clean and incomplete files, with or without findings`.

### Task 3: Sample, version, docs (AC-7)

**Files:** `examples/sample-report.md` (regenerated), `tests/test_sample_report.py`, `CHANGELOG.md`, `README.md` if it describes the links, and version `0.6.0` in all four places.

- [ ] Add the sample-link test (spec §5).
- [ ] Regenerate the sample with `uv run scripts/gen_sample_report.py`. Check that the diff only adds links.
- [ ] Run the three-Python suite, `gen_catalog_docs.py --check`, `gen_sample_report.py --check` and `claude plugin validate . --strict`.
- [ ] Commit: `Show hotspot links in the sample report; bump to 0.6.0`.

## AC coverage

| AC | Tasks |
|---|---|
| AC-1 | 2 |
| AC-2 | 1, 2 |
| AC-3 | 1, 2 |
| AC-4 | 2 |
| AC-5 | 2 |
| AC-6 | 2 |
| AC-7 | 3 |
