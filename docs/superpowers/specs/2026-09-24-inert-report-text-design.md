# Inert report text: design

**Requirements:** [#28](https://github.com/tomstagl/thunderstruck/issues/28). The problem, stories, scope, acceptance criteria (AC-n) and decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-24-inert-report-text.md`

## 1. What reaches `report.md` today

| Source | Fields | Rendered as |
|---|---|---|
| Investigator (model) | `failure_mode` (heading), `trigger_condition`, `amplifier`, `sustaining_effect`, `blast_radius` (table cells), evidence `note`, `how_to_verify`, `confidence_rationale`, `prediction`, `location.symbol` (inside backticks), clean-hotspot `notes` | raw |
| Validator | *Incomplete* errors, which quote model-written refs | raw |
| Scanned repository | file paths in the hotspot table and in the clean and incomplete lists (inside backticks), the repository directory name (heading), the branch name (inside backticks), run warnings that name paths | raw |
| Service catalog command | entity ref, edge refs, direction, attributes | raw, though `context_extract` already restricts them to label patterns |

Only #22's evidence and location refs go through a safe code span (`report._code`).

## 2. Two primitives

A new stdlib-only module, `scripts/mdtext.py`, provides two functions. `report.py` uses them for **every** interpolated value it does not generate itself.

### `code(text, cell=False)`: a verbatim code span

- **Fence:** one backtick longer than the longest run inside the text. If the text starts or ends with a backtick, it is padded with a space (#22's rule, moved here).
- **Newlines:** `\r\n`, `\r` and `\n` are replaced by a space, so a code span cannot end a block.
- **Tables:** with `cell=True`, `|` becomes `\|`. GFM splits table cells on `|` even inside code spans, and renders `\|` there as `|`.

Used for paths, symbols, branch names, refs and catalog values.

### `text(value, cell=False, heading=False)`: prose that stays prose

1. Normalise whitespace. `None` becomes `—`; any other value is converted with `str()`. Every run of line breaks and tabs becomes a single space, so no block structure can start inside a field (AC-2).
2. **Split out "linkish" substrings** and render each as `code(…, cell)`. These are the substrings a GFM renderer would autolink, or that GitHub post-processes, whatever the escaping:
   - `(?:https?|ftp)://\S+`, `www\.\S+`, `mailto:\S+`, `xmpp:\S+`
   - e-mail addresses: `[\w.+-]+@[\w-]+(?:\.[\w-]+)+`
   - emoji shortcodes: `:[a-z0-9_+-]+:`

   A code span shows the characters exactly, is copyable, and is never linkified (decision in #28: URLs appear as text).
3. **Backslash-escape** the rest. CommonMark allows escaping any ASCII punctuation. The escaped set is `\ ` * _ [ ] < > | ~ & $`, plus `#` when `heading=True`. The reasons:
   - `[` `]`: links and images (with `[` escaped, a leading `!` is inert);
   - `<` `>`: raw HTML and angle autolinks;
   - `` ` ``: code spans;
   - `*` `_` `~`: emphasis and strikethrough;
   - `|`: table cells;
   - `&`: entities (so `&copy;` stays those six characters);
   - `$`: GitHub math;
   - `#`: an ATX heading's closing sequence;
   - `\`: the escape itself.

   Everything else passes through, so ordinary prose stays readable in the raw file.

The output is a single line whose rendering shows exactly the input characters (AC-3), except that line breaks and tabs become spaces.

**Not handled, by design:**
- `@name` and `#123` are linkified by GitHub in issues and comments, but not in rendered repository files.
- Tool-generated links and code spans, such as #22's evidence links and our own `<sub>` key line, are built by `report.py` and don't pass through `text()` (AC-4).

## 3. Where each primitive is applied

| Site in `render_markdown` / `render_service_context` | Call |
|---|---|
| `# thunderstruck — {repo_name}` | `text(repo_name, heading=True)` |
| branch in the run line | `code(branch)` |
| run warnings, and context warnings | `text(w)` |
| service context: entity ref, edge ref, direction, attributes | `code(…, cell=True)` / `text(…, cell=True)` |
| finding heading: `failure_mode` | `text(…, heading=True)` |
| finding line: symbol | `code(symbol)` |
| finding table: trigger, amplifier, sustaining effect, blast radius, dependents | `text(…, cell=True)`; neighbour and attributes via `code(…, cell=True)` |
| evidence note | `text(note)` |
| Verify, Why this confidence, Prediction | `text(…)` |
| clean list: file, notes | `code(file)`, `text(notes)` |
| incomplete list: file, reason, errors | `code(file)`, `text(reason)`, `text(err)` |
| hotspot table: file | `code(file, cell=True)` |

The fallback for a missing `sustaining_effect` is the tool's own emphasis (`_none — …_`) and stays as it is.

`report._code` and `report._linked` move to `mdtext.code` and `mdtext.linked`, so there is a single implementation. `report.json` and the guardrail are unchanged (ticket scope).

## 4. Test strategy

- **`tests/test_mdtext.py`** (unit tests):
  - `code`: fence length, padding, newlines, and `|` in cells.
  - `text`: every character in the escaped set, heading `#`, and whitespace collapse.
  - Linkish splitting: URL, `www.`, e-mail, `mailto:`, emoji.
  - `None`.
- **Renderer tests** (`markdown-it-py` in its `gfm-like` preset with `linkify-it-py`, a GFM-like renderer with tables and autolinks):
  - Every hostile payload is rendered, both in prose and in a table cell.
  - The HTML must contain no `<a>`, `<img>` or raw-HTML element.
  - The plain text of the output must equal the input, with whitespace collapsed.
  - A table stays one row with the expected number of cells.
- **End to end** (`tests/test_inert_report.py`):
  - The fixture finding gets hostile text in every model field and note.
  - Validate, then report.
  - Render `report.md`: every `<a href>` must start with the fixture's link base, and there must be no `<img>` and no HTML elements other than our `<sub>`.
  - The finding's table keeps its row count.
  - A second case edits `collect()` output with a hostile hotspot file name, branch, repo name and warning, then renders it.
- **Sample report (AC-5):** regenerated. FR-003's quoted injection text renders inertly.
- **Test dependencies:** the renderer tests `importorskip` `markdown_it`. CI installs `markdown-it-py` and `linkify-it-py` and sets `THUNDERSTRUCK_REQUIRE_RENDERER=1`, which turns that skip into a failure, so CI can never silently skip them. CLAUDE.md's test command gains the two `--with` flags.

## 5. Decisions

| Decision | Rationale |
|---|---|
| Escape a minimal punctuation set instead of wrapping all prose in code spans | Findings stay readable prose. The escaped characters render as themselves. |
| Linkish substrings become code spans | Escaping can't stop GFM's extended autolinks or GitHub's emoji filter, which run on text. A code span can. |
| Collapse line breaks | One field can never start a block, a heading, a list or a table row (AC-2). |
| One module for all Markdown rendering primitives | `report.py` had two ad-hoc styles. One place to test and to extend. |
| A real renderer in the tests, required in CI | AC-6 asks for rendered output. String checks alone would miss renderer behaviour. |

## 6. Open design questions

- GitHub also renders Mermaid and math fenced blocks, and footnote syntax `[^1]`. Fences can't start without a newline, and `[` is escaped, so none of these can start from a field. They are listed here in case the renderer changes.
