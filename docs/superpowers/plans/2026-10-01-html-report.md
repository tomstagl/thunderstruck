# HTML Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every scan also writes a self-contained, inert, deterministic `report.html` in the reader layout, with full parity to `report.md`, and `/thunderstruck-report` rebuilds it on demand.

**Spec:** `docs/superpowers/specs/2026-10-01-html-report-design.md`. Requirements AC-1…AC-10 are in GitHub issue #3.

**Design input:** `docs/superpowers/specs/assets/2026-10-01-html-report/report.html` and `report_html.py`, as delivered from Claude Design. Task 2 copies them to `templates/report.html` and `scripts/report_html.py`, and Tasks 2–3 apply spec §4.4. The assets stay unchanged as the reference. The design's sample data came from a non-public codebase and is **never** committed.

**Branch:** `feat/html-report`. One commit per task. Before every push, run the full suite on Python 3.11, 3.12 and 3.13, checking the real exit code:

```bash
for py in 3.11 3.12 3.13; do THUNDERSTRUCK_REQUIRE_RENDERER=1 uv run --python $py --with pytest \
  --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 \
  --with cmarkgfm==2025.10.22 pytest tests/ -q > /tmp/pt$py.log 2>&1; echo "$py rc=$?"; done
```

The browser tests run separately, from Task 5 on:

```bash
THUNDERSTRUCK_REQUIRE_BROWSER=1 uv run --with pytest --with pyyaml --with lizard \
  --with playwright==1.55.0 pytest tests/test_report_html_browser.py -q
```

(In this cloud environment, Chromium is pre-installed. Do not run `playwright install`; pass `executable_path` from `PLAYWRIGHT_BROWSERS_PATH` if the pinned version does not find it.)

### Task 1: `report.json` carries every section the page needs (AC-3, AC-4)

**Files:** `scripts/report.py`, `tests/test_report_json_fields.py` (new), `skills/thunderstruck-scan/references/report-format.md`.

- [x] Write the failing tests (spec §2, §7): over the fixture pipeline, `report.json` has `scanned_at`, `run_warnings`, `suppressed`, `coverage_rows` and `files_affected`. `coverage_rows` equals the rows of the Markdown coverage table, and `run_warnings` equals the bullet list under **Run warnings**. `warnings` is unchanged.
- [x] Extract `coverage_rows(data)` and `run_warnings(data)` from `render_markdown`, and make `render_markdown` use them. Its output must not change: `uv run scripts/gen_sample_report.py --check` passes with no regeneration.
- [x] Add the five fields to `render_json` (spec §2 table).
- [x] Document the fields in `report-format.md`.
- [x] Commit: `Carry coverage rows, run warnings and suppressed leads in report.json`.

### Task 2: `report_html.py`, embedding and determinism (AC-6, AC-7, AC-8)

**Files:** `scripts/report_html.py` (new, from the design asset), `templates/report.html` (the design asset verbatim, plus the two placeholders and the `id="thunderstruck-app"` attribute only; the rest follows in Task 3), `tests/test_report_html.py` (new).

- [x] Write the failing tests (spec §7, `test_report_html.py`): `embed` escaping and round-trip; placeholder count errors; script hash equals the recomputed sha256; `page_data` drops `repo.root`, sets `repo.name` and does not mutate its input; byte-identical double render; no fixture checkout path in the output; stdlib-only imports (AST); exit 2 with no file written for a missing `report.json`, a wrong schema and a missing template.
- [x] Port `report_html.py` (spec §3): schema check, `page_data`, two placeholders, script hash from `#thunderstruck-app`, atomic write, and the `report.html: <path> (<KB> KB, <n> finding(s))` line.
- [x] Add the template with the CSP `<meta>` first in `<head>` (spec §4.2 rule 3) and the placeholders.
- [x] Commit: `Render report.json into a self-contained report.html`.

### Task 3: The template: design port, CSP and parity sections (AC-4, AC-5, AC-6, AC-7, AC-9)

**Files:** `templates/report.html`, `tests/test_report_html.py`.

- [x] Write the failing tests: the template lint (spec §7: forbidden APIs and external references); pipeline render over the fixture contains every finding id; the injection comment appears only inside the JSON block.
- [x] Apply the changes from the delivered design, one by one (spec §4.4, items 2–8): drop the `fetch` fallback, read `repo.name`, add the Overview entry and the parity sections (spec §4.3 table, `report.md` order and headings), add the status lines for empty and failed reports, add the `low` count, use `rel="noopener noreferrer"`. Leave everything else as delivered.
- [x] Older `report.json` without the spec §2 fields: omit those sections and show the "predates the HTML view" note (spec §6).
- [x] Open the rendered fixture page in Chromium by hand and check the Overview, a finding with commit evidence, a finding with `catalog_evidence`, the filter and the keys.
- [x] Commit: `Show every report.md section in the HTML report`.

### Task 4: `/thunderstruck-report` and the scan's Step 5 and 6 (AC-1, AC-2)

**Files:** `skills/thunderstruck-report/SKILL.md` (new), `skills/thunderstruck-scan/SKILL.md`, `skills/thunderstruck-scan/references/report-format.md`, `tests/test_report_html.py`.

- [ ] Write the failing tests: the new skill and the scan skill reference `report_html.py` only through `${CLAUDE_PLUGIN_ROOT}` (this is covered by `test_plugin_paths` once the files exist; run it); the scan skill's Step 5 runs `report_html.py` after `report.py` and states that a failure never stops the scan; `plugin.json` still declares no `skills` (the existing regression test).
- [ ] Write `skills/thunderstruck-report/SKILL.md` (spec §5.1).
- [ ] Patch Step 5 and Step 6 of `thunderstruck-scan/SKILL.md` (spec §5.2), and add `report.html` to the tree in `report-format.md`.
- [ ] `claude plugin validate . --strict`, then install the plugin from this checkout and confirm `claude plugin list` says `enabled` and lists `thunderstruck-report`.
- [ ] Commit: `Add /thunderstruck-report and build the HTML report on every scan`.

### Task 5: Browser test (AC-6, AC-7, AC-9)

**Files:** `tests/test_report_html_browser.py` (new), `.github/workflows/ci.yml`.

- [ ] Write the browser tests (spec §7, `test_report_html_browser.py`) against a page rendered from the fixture in `tmp_path`: no console errors and no CSP violations; no network request besides the page; the injection text is shown as text and creates no element; filter, `j`/`k`, `r` and reload persistence; the copy button; Overview sections; the all-incomplete status line, built by rendering a `report.json` with every hotspot moved to `incomplete`.
- [ ] Skip without Playwright unless `THUNDERSTRUCK_REQUIRE_BROWSER=1`.
- [ ] CI: one step in the test job installs Chromium for the pinned Playwright and runs the browser tests with `THUNDERSTRUCK_REQUIRE_BROWSER=1`, on one Python version only.
- [ ] Commit: `Test the HTML report in a real browser`.

### Task 6: Sample, CI, version, docs (AC-10)

**Files:** `scripts/gen_sample_report.py`, `examples/sample-report.html` (generated), `tests/test_sample_report.py`, `.github/workflows/ci.yml` if the check step needs a change, `README.md`, `CHANGELOG.md`, `CLAUDE.md` (Commands and Generated files), and version `0.9.0` in `plugin.json`, `marketplace.json`, `pyproject.toml` and the top `CHANGELOG.md` heading.

- [ ] Write the failing sample test: `examples/sample-report.html` exists, contains every fixture finding id, and contains no path of the temporary fixture checkout.
- [ ] Extend `gen_sample_report.py`: after `report.py`, pin `generated_at` and `scanned_at` in the loaded `report.json` to the fixture's last commit day, render with `report_html.render`, and write `examples/sample-report.html`. `--check` compares both samples and fails if either is stale.
- [ ] Regenerate both samples. The Markdown sample must not change.
- [ ] Run the three-Python suite, the browser tests, `gen_catalog_docs.py --check`, `gen_sample_report.py --check` and `claude plugin validate . --strict`.
- [ ] Docs: the README mentions `report.html` and `/thunderstruck-report`; CLAUDE.md lists `examples/sample-report.html` under generated files and `report_html.py` in the architecture; CHANGELOG `## 0.9.0`.
- [ ] Commit: `Publish a sample HTML report; bump to 0.9.0`.

## AC coverage

| AC | Task(s) | Proved by |
|---|---|---|
| AC-1 | 4 | scan skill Step 5/6 test, manual scan |
| AC-2 | 2, 4 | missing-`report.json` test, skill text |
| AC-3 | 1, 3 | pipeline test: ids equal `report.json`, rejected findings absent |
| AC-4 | 1, 3, 5 | `coverage_rows`/`run_warnings` tests, Overview browser test |
| AC-5 | 3, 5 | all-incomplete browser test |
| AC-6 | 2, 3, 5 | template lint, CSP test, no-network browser test |
| AC-7 | 2, 3, 5 | embed tests, injection tests (text and DOM) |
| AC-8 | 2 | double-render and no-absolute-path tests |
| AC-9 | 3, 5 | browser interaction tests |
| AC-10 | 6 | `gen_sample_report.py --check` in CI, sample test |
