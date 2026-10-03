# HTML report: design

**Requirements:** [#3](https://github.com/tomstagl/thunderstruck/issues/3). The problem, stories, scope, acceptance criteria (AC-n) and decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-10-01-html-report.md`
**Builds on:** inert report text (`2026-09-24-inert-report-text-design.md`, #28), source links (#22) and hotspot links (#24).
**Design reference:** the "reader" layout from Claude Design, committed as delivered in `docs/superpowers/specs/assets/2026-10-01-html-report/` (`report.html`, `report_html.py`). Both are ported with the changes listed in §4.4. The design's sample data came from a non-public codebase and is not in this repository.

## 1. Architecture

```
signals.py      unchanged
bundle.py       unchanged    bundles stay byte-identical
validate.py     unchanged
report.py       render_json  + a few additive report.json fields, so the page computes nothing (§2)
report_html.py  NEW          report.json -> report.html: one placeholder, one embedded JSON block (§3)
templates/
  report.html   NEW          static page: CSS, one inline script, a JSON data block (§4)
guardrail.py    unchanged    index.json keeps its shape
skills/
  thunderstruck-report/      NEW   /thunderstruck-report, rebuilds the page on demand (§5)
  thunderstruck-scan/        Step 5 runs report_html.py after report.py; Step 6 names the file (§5)
```

The page is a static template plus data. `report_html.py` has no logic of its own beyond shaping and embedding the data. The script in the page only displays: it sorts, filters and lays out values that `report.py` already computed. Anything that has to be reproducible (counts, coverage numbers, which links exist) is computed in Python, not in the browser. This is the governing rule ("scripts for anything that must be reproducible") applied to the page.

`report_html.py` reads **only** `report.json`. That file already contains exactly the findings that passed today's validator (`report.collect()` drops unvalidated, stale and failed ones), with their `FR-nnn` ids, `key`s, links, `shares_code_with` and `catalog_evidence`. Reading `findings/H*.json` directly would bypass all of that (AC-3).

## 2. `report.json` additions

`report.md` builds several sections from data that `report.json` does not carry, or carries only in raw form. Each section is added as an **additive** field, and the schema stays `thunderstruck.report/v1`, because existing fields keep their meaning:

| Field | Content | Source in `report.py` today |
|---|---|---|
| `scanned_at` | `hotspots.json` `generated_at`, the scan time that `report.md` shows | `hs["generated_at"]` |
| `run_warnings` | the exact list under **Run warnings** in `report.md`: hotspot warnings, context warnings and link warnings, in that order | the `warnings` local in `render_markdown` |
| `suppressed` | `[{detector, path, hits, reason}]` | `hs.get("suppressed")` |
| `coverage_rows` | one row per scanned pattern, in `report.md` order: `{id, name, tier, unconfirmed_files, leads_read, leads_confirmed, findings}`, plus the `OTHER` row when present (with `null` for the columns `report.md` shows as `—`) | the coverage-table block in `render_markdown` |
| `files_affected` | number of distinct finding files | `render_markdown` |
| `clean[].cited_by` | per clean hotspot, the ids of findings from other hotspots that cite its file as `code` evidence (empty when none). This is the "no finding of its own; cited as evidence by …" note in `report.md` | the `cited_by` map in `render_markdown` |
| `not_scanned` | `{intro, items}` in plain text: the sentences under **Not scanned**, or `null` without `coverage_gaps` | `render_not_scanned` |

`warnings` keeps its current content (hotspot plus link warnings). `run_warnings` exists so the page shows exactly what `report.md` shows, context warnings included, without changing an existing field.

The coverage table, run warnings, clean citations and not-scanned lines move into helpers (`coverage_rows(data)`, `run_warnings(data)`, `clean_cited_by(findings)`, `not_scanned(gaps, code, text)`). `render_markdown` and `render_json` both call them; `not_scanned` takes the span formatters, so Markdown passes `md.code`/`md.text` and JSON passes plain text, so the two outputs can't drift. `render_markdown`'s output does not change by a byte: `test_sample_report` and `gen_sample_report.py --check` prove it.

`report.json` keeps `repo.root` (the absolute path). Its other readers rely on it. The page drops it (§3.2).

## 3. `scripts/report_html.py`

Stdlib only, PEP 723 header with `requires-python = ">=3.11"` and no dependencies. `_common`'s `yaml` import is deferred, so importing `_common` stays stdlib-only. Uses `_common.find_repo_root`, `out_dir`, `load_json`, `die` and `ThunderstruckError`, which all exist on `main`.

```
uv run scripts/report_html.py [--repo PATH]
```

### 3.1 Flow

1. `report = load_json(out / "report.json")`. If it is missing or not a dict, raise `ThunderstruckError("no report.json — run report.py first.")`, exit 2, write nothing (AC-2).
2. If `report["schema"] != c.REPORT_SCHEMA_VERSION`, raise an error naming both versions. A report from another schema is refused rather than half-rendered.
3. `page = page_data(report)` (§3.2).
4. `html = render(page, template_text)` (§3.3).
5. Write `out / "report.html"` via a temp file and `os.replace`, so a failed run never leaves a truncated page.
6. Print `report.html: <path> (<size in KB> KB, <n> finding(s))`.

The template is found at `Path(__file__).resolve().parent.parent / "templates" / "report.html"`, which works from a checkout and from the installed plugin. A missing template is a `ThunderstruckError`.

### 3.2 `page_data(report) -> dict`

A deep copy of the report, with one change:

- `repo.root` is removed, and `repo.name` is set to `Path(root).name`. The page needs only the name, and a page people share must not carry a local path (AC-8). This is the same name `report.md` uses in its title.

Nothing else is filtered or reordered. Determinism follows from `report.json` itself: same input, same output (AC-8).

### 3.3 `render(page, template) -> str`

The template contains exactly two placeholders, each exactly once (otherwise `ThunderstruckError`):

| Placeholder | Replaced with |
|---|---|
| `__THUNDERSTRUCK_REPORT__` | `embed(page)` |
| `__THUNDERSTRUCK_SCRIPT_HASH__` | `sha256-<base64>` of the inline application script's exact text (§4.2) |

`embed()` is taken from the design unchanged: `json.dumps(ensure_ascii=False, separators=(",", ":"))`, then `<`, `>`, `&`, U+2028 and U+2029 are replaced by their `\uXXXX` escapes. The JSON can then never close its `<script>` element, open a comment, or break a JavaScript string, and it still parses to the same value.

The script hash is computed at render time from the template's own script element: the text between `<script id="thunderstruck-app">` and its `</script>`. The CSP therefore can never drift from the script it guards, and editing the template needs no extra step.

## 4. `templates/report.html`

### 4.1 Layout (from the design)

- **Rail** (left, 340px): eyebrow, repo name, `branch @ sha7 · date · window · commits`; counts (findings, high, medium, low); an All/High/Medium/Low filter showing only the levels present; "N of M reviewed"; a collapsible run-warnings block; findings grouped by hotspot (`H01 path`), each with a confidence dot, `FR-nnn`, its patterns and two lines of `failure_mode`.
- **Dossier** (right): id, hotspot and score, pattern tags, confidence tag; `failure_mode` as `h1`; the location linked when it has a `url`; a shared-code note; rows for Trigger, Amplifier, "Keeps it failing" (`null` → "None. This one stops when the trigger stops."), Blast radius, Dependents (from `catalog_evidence`), Evidence, "Why <confidence>", Prediction; a "How to prove it wrong" box with `how_to_verify` and a copyable `/thunderstruck-verify FR-nnn`; the stable `key`.
- **Footer:** Previous / Next, "i of n", the `j` / `k` / `r` key hint (hidden below 1100px), and Mark reviewed.
- **Responsive and print:** the design's 860px single-column layout. Print shows the dossier only.
- **Palette:** warm light paper tokens as CSS custom properties. Fonts are `Lora` and `DM Sans` when installed locally, otherwise Georgia and the system sans. No font is ever loaded (AC-6).

### 4.2 Security (AC-6, AC-7)

The page's rules, each enforced by a test (§7):

1. **Data is never markup.** Every value from the report enters the DOM through `textContent` or `createTextNode`, via the design's `h()` helper. The template never uses `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval` or `new Function`.
2. **Only tool-built URLs become links.** `href` is set only from a `url`, `history_url` or `location.url` field (all built by `links.py`), and only if it matches `^https?://`. Otherwise the text is shown unlinked, as in `report.md`. Model text is never put into `href`, `style`, `class`, `id` or an event handler. Attribute values come from the template or from validated enums (`confidence`, evidence `type`).
3. **Content-Security-Policy** in a `<meta>` as the first element of `<head>`:
   `default-src 'none'; script-src '__THUNDERSTRUCK_SCRIPT_HASH__'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none'`.
   So even a successful injection could not run script, fetch anything or load anything. `style-src 'unsafe-inline'` is needed for the `<style>` element and the few `style` attributes the script sets. Those values are constants in the template.
4. **No network.** The design's `fetch("report.json")` fallback is removed (`connect-src 'none'` would block it anyway). A template opened with the placeholder intact shows "No report data — run /thunderstruck-scan".
5. **Links open safely:** `target="_blank" rel="noopener noreferrer"`.
6. The application script is a single element, `<script id="thunderstruck-app">`. The data block is `<script type="application/json" id="thunderstruck-report">`. A non-executable type is not subject to `script-src`.

### 4.3 Parity sections (AC-4, AC-5)

A rail entry above the findings, **Overview**, selected by default when the URL has no `#FR-nnn` (otherwise the named finding opens). It renders, in `report.md` order and with the same wording for headings:

| Section | From | Shown when |
|---|---|---|
| Run header, with the "findings are falsifiable hypotheses" note | `repo`, `scanned_at`, `window`, `counts`, `files_affected` | always |
| Run warnings and suppressed leads | `run_warnings`, `suppressed` | non-empty |
| Not scanned | `not_scanned` | not `null` |
| Service context | `service_context` (entity, `fetched_at` date, inbound and outbound edges, truncation) | not `null` |
| Pattern coverage | `coverage_rows`, plus the "0 leads" footnote | always |
| Hotspots investigated with no finding | `clean` (file linked by `url`, `notes` as text, and "no finding of its own; cited as evidence by FR-…" from `cited_by`) | non-empty |
| Incomplete | `incomplete` (file, reason, first errors as text) | non-empty |
| Ranked hotspots | `hotspots` (id, file → `url`, history → `history_url`, score, patterns) | always |
| Dormant integration points | `dormant` | non-empty |

Service-context age is shown as the `fetched_at` date, not "N days ago": the page must not depend on the time it is opened, and the date is what `report.json` holds.

**Empty and failed states (AC-5).** With no findings, the rail shows only Overview, and the dossier pane is replaced by a status line computed from the counts:

- every investigated hotspot clean: "No findings: all N investigated hotspots came back clean."
- some incomplete: "No findings, but K of N hotspots could not be analysed. See Incomplete." The word "clean" is never used for an incomplete hotspot.
- all incomplete: "No hotspot could be analysed. This report says nothing about the code."
- no investigated hotspot at all: "No hotspot was investigated. This report says nothing about the code."

The design's fixed "Every investigated hotspot came back clean" text is removed.

### 4.4 Changes from the delivered design, in full

1. CSP `<meta>` and the script-hash placeholder (§4.2).
2. `fetch` fallback removed (§4.2).
3. Repo name read from `repo.name`, not derived from `repo.root` (§3.2).
4. Overview entry and parity sections (§4.3).
5. Status lines replace the fixed empty-state text (§4.3).
6. A `low` count next to `high` and `medium`.
7. `rel="noopener noreferrer"`.
8. The application script gets `id="thunderstruck-app"`.

Nothing else changes: palette, typography, spacing, interaction and keyboard model all stay as delivered.

### 4.5 Reviewed state (AC-9)

`localStorage["thunderstruck:reviewed:" + repo.name]` maps a finding's `key` (falling back to `id`) to `true`. The `key` is used because it is stable across scans, so a reviewed mark survives a re-scan that renumbers ids (CLAUDE.md: nothing matches on `id`). Storage failures, such as a private window or a blocked `file://` origin, are caught: marks then last only for the session, and nothing else breaks. Nothing is ever sent anywhere.

## 5. Skills

### 5.1 `skills/thunderstruck-report/SKILL.md`

`description` covers: build or rebuild the HTML report, open the report in a browser, share a scan. Body:

1. Preflight: `uv --version`. If `.thunderstruck/report.json` is missing, say there is no scan to render, suggest `/thunderstruck-scan`, and stop.
2. Run `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/report_html.py"`.
3. Relay the printed path and size. Note that the file is self-contained and can be sent as-is, and that it shows findings as hypotheses.
4. On failure, relay the error verbatim. Do not retry, and do not edit `report.json` by hand.

No `skills` entry in `plugin.json`: skills are auto-discovered, and declaring them breaks loading (CLAUDE.md, regression tests). Paths use `${CLAUDE_PLUGIN_ROOT}` (`test_plugin_paths`).

### 5.2 `skills/thunderstruck-scan/SKILL.md`

- **Step 5:** after `report.py`, run `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/report_html.py"`. If it exits non-zero, note its last line and continue: this step never fails the scan (AC-1). No retry.
- **Step 6:** link `.thunderstruck/report.html` next to `report.md`. If the HTML step failed, say so in one line, with the reason.
- `references/report-format.md`: add `report.html` to the tree, and document the additive `report.json` fields (§2).

## 6. Degradation

| Situation | Behaviour |
|---|---|
| `report.json` missing or unreadable | exit 2, message, nothing written |
| wrong schema | exit 2, both versions named, nothing written |
| template missing, or a placeholder count other than 1 | exit 2, nothing written |
| optional field missing (older `report.json` from v1 without §2 fields) | the section is omitted, and the Overview says "This report predates the HTML view; re-run /thunderstruck-report after a scan for every section." |
| scan's HTML step fails | scan completes, summary says the HTML is missing (AC-1) |
| `localStorage` unavailable | reviewed marks last only for the session |

## 7. Test strategy

`tests/test_report_html.py` (stdlib and pytest only):

- `embed`: `</script>`, `<!--`, `&`, U+2028 and U+2029 never appear raw in the output, and `json.loads` of the embedded text equals the input.
- `render`: zero or two of either placeholder → error. The script hash in the CSP equals the sha256 of the `#thunderstruck-app` text, recomputed in the test.
- `page_data`: `repo.root` absent, `repo.name` present, and the input is not mutated.
- Determinism: rendering the same `report.json` twice gives identical bytes, and the output contains no absolute path of the fixture checkout (AC-8).
- Pipeline: over the fixture (as `test_pipeline` builds it), `report_html.py` exits 0. Every finding id from `report.json` is in the embedded data, and nothing from a findings file that failed validation is (AC-3).
- Inertness: the fixture's injection comment appears only inside the JSON block, never outside it (AC-7).
- Template lint (AC-6, AC-7): no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(`, `new Function`, `fetch(`, `XMLHttpRequest`, `<link`, `@import`, `url(`, `src=` or `http` URL in the template. The CSP `<meta>` is the first child of `<head>`.
- Stdlib only: an AST check of `report_html.py`'s imports, like the guardrail's.
- `report.py`: `coverage_rows` and `run_warnings` match the rendered Markdown, and the sample `report.md` is byte-identical.
- Errors: no `report.json`, wrong schema, missing template → exit 2 and no `report.html`.

`tests/test_report_html_browser.py` (Playwright, Chromium):

- Skips when Playwright is not importable, unless `THUNDERSTRUCK_REQUIRE_BROWSER=1`, as the renderer tests do. CI sets it.
- Opens `examples/sample-report.html` from `file://`. No console errors, no CSP violations, and zero network requests besides the page itself (AC-6).
- The fixture's injection text is present as text, and no element exists that it would have created (AC-7).
- Filter, `j`/`k`, `r` and reload (the mark persists), and the copy button's text (AC-9).
- Overview lists each parity section that the fixture's `report.md` has (AC-4).
- An all-incomplete report shows the "could not be analysed" status and never "clean" (AC-5).

Sample (AC-10): `gen_sample_report.py` also writes `examples/sample-report.html`, pinning `generated_at` and `scanned_at` to the fixture's last commit day, as it does for the Markdown. `--check` covers both files. `tests/test_sample_report.py` asserts that every fixture finding id is in the HTML.

## 8. Decisions and rationale

- **Embedded JSON with DOM rendering, not a Jinja template.** It was the delivered design, and it keeps `report_html.py` stdlib-only. Inertness rests on one mechanism (`textContent`) instead of autoescape per call site, plus a CSP as a second wall. The cost is that the page needs JavaScript. A static, readable `report.md` already exists for anyone without it.
- **Template in `templates/` at the repo root, not under the skill.** Two entry points use it: the scan and `/thunderstruck-report`. It is a plugin asset next to `catalog/`, not part of one skill.
- **Script hash computed at render time.** A hard-coded hash would break silently on every template edit.
- **Additive `report.json` fields rather than computing in the browser.** Coverage numbers and warnings are reproducible facts. Computing them twice, in two languages, invites drift.
- **The design's sample data is not used.** It came from a real, non-public codebase. The public sample is built from the fixture through the real pipeline, as the Markdown sample is.

## 9. Open design questions

None.
