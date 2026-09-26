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

Both functions first make the value visible and flat:

- line breaks (`str.splitlines` semantics) become spaces;
- C0 and C1 controls, DEL, and bidi marks, overrides and isolates (U+061C, U+200E/F, U+202A–E, U+2066–9) become the visible text `\uXXXX`. The source writes these as escapes, never as raw characters. Otherwise a field could hide characters, or reverse what the reader sees.

### `code(value, cell=False)`: a verbatim code span

- **Fence:** one backtick longer than the longest run inside.
- **Padding:** a space is added on both sides when the text starts or ends with a backtick **or a space**, because CommonMark strips one such space.
- **Empty values:** `None`, an empty string or only whitespace renders as `—`, never as an empty span.
- **Tables:** with `cell=True`, `|` becomes `\|`. GFM splits cells on `|` even inside code spans, and renders `\|` there as `|`.

### `text(value, cell=False, heading=False)`: prose that stays prose

1. **Flatten and trim**, as above. Runs of spaces and tabs collapse to one space. An empty or whitespace-only result renders as `—`.
2. **Whole words that could hold a link become code spans.** The text is split on whitespace. A token containing any of the following is rendered whole as `code(token, cell)`:
   - `://`, a protocol-relative `//` (linkify-it links `//localhost:8080/x`), `www.`, `mailto:`, `xmpp:` or `@`;
   - a dot followed by two letters (Unicode letters, so `.рф` counts);
   - an emoji shortcode `:name:`, where the name contains a letter (so `10:30:45` stays text), or one of GitHub's letterless codes `:+1:`, `:-1:`, `:100:`, `:1234:`.

   The match is case-insensitive.

   **Why whole tokens, not substrings.** Neither GFM nor linkify-it links across whitespace, so a token-level rule is a superset of both by construction:
   - linkify-it (VS Code's preview) links bare domains, including `a+.co` and even `deploy.py`, since `.py` is a country TLD;
   - GitHub links e-mail forms as loose as `_@.h`.

   The design review's substring regexes kept missing cases like these. It also removes the fence-merging problem, where two adjacent spans pair up wrongly and leave a URL outside a span. The cost: a few harmless words such as `Node.js` render as code.

   **Sentence punctuation stays outside the span.** Leading `(` `[` `{` `"` `'` and trailing `)` `]` `}` `,` `;` `:` `.` `!` `?` `"` `'` are peeled off the token first, and the span wraps only what is left, provided that still matches. Prose such as `saved as <artist>.jpg: audio (.ogg/.oga),` then renders the file names as code and the colon, parentheses and comma as text. The peeled characters are escaped like any other text (step 3). They hold no letter, digit, `@` or `/`, and sit between whitespace and a code span, so no renderer can build a link or a shortcode from them (dogfood on a real repository, 2026-09-26).
3. **Backslash-escape** the rest. CommonMark allows escaping any ASCII punctuation. The escaped set is `\ ` * _ [ ] < > | ~ & $`, plus `#` when `heading=True`. The reasons:
   - `[` `]`: links and images (with `[` escaped, a leading `!` is inert);
   - `<` `>`: raw HTML;
   - `` ` ``: code spans;
   - `*` `_` `~`: emphasis and strikethrough;
   - `|`: table cells;
   - `&`: entities;
   - `$`: GitHub math;
   - `#`: an ATX heading's closing sequence;
   - `\`: the escape itself.
4. **Escape a leading block marker.** A leading `#`, `-`, `+`, `=`, `>`, or `1.` / `1)` gets a backslash. `text()` is safe at the start of a line and as a list item's content, where the report puts warnings and validator errors. Leading spaces are already trimmed, so four-space indented code can't start either.

The output is one line whose rendering shows the input characters (AC-3), with whitespace collapsed and invisible characters made visible.

**Not handled, by design:**
- `#123` is linkified by GitHub in issues and comments, but not in rendered repository files. `@name` is now code anyway.
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
| hotspot table: file, lead IDs | `code(file, cell=True)`, `text(id, cell=True)` |
| confidence breakdown, missing-pattern IDs, evidence type, stable key, scan window, fetch date, catalog hash, pattern tier | `text` / `code`. These are validated or generated, but rendering them safely costs nothing, and a findings file can reach the report with a self-asserted stamp (#32). |

The fallback for a missing `sustaining_effect` is the tool's own emphasis (`_none — …_`) and stays as it is.

`report._code` and `report._linked` move to `mdtext.code` and `mdtext.linked`, so there is a single implementation. `report.json` and the guardrail are unchanged (ticket scope).

`context.json` is a file on disk, not trusted structure. `collect()` keeps only string warnings from it, at most 20, and adds a visible "N more context warning(s) not shown" line when it drops any. An evidence item without a note renders without a dangling `—`.

## 4. Test strategy

- **Two renderers.**
  - **`cmarkgfm`**, the Python binding of cmark-gfm, GitHub's own engine, with its autolink, table and strikethrough extensions and unsafe HTML allowed. This is the authority for GitHub.
  - **`markdown-it-py` in `gfm-like` with `linkify-it-py`**, which is stricter than GitHub: it links bare domains, as VS Code's preview does.

  Every renderer test runs against both.
- **`tests/test_mdtext.py`:**
  - **Units:** fences, padding, empty values, pipes in cells, the escaped set, heading `#`, leading block markers, invisible characters, and times not taken for emoji.
  - **Renderer tests:** every hostile payload is rendered in prose, as list-item content, in a table cell, in a heading, and as a code span. They check:
    - no `<a>`, `<img>`, HTML, heading, rule, list or emphasis element;
    - the reader-visible text equals the input;
    - the table keeps one row.
  - **The design review's payloads**, as a regression test.
  - **A seeded fuzz test:** 400 random mixes of Markdown-significant fragments per renderer, in all four positions.
  - **Once, before merge,** the same fuzz ran over 30 seeds and 600,000 renders, with no issue left.
- **`tests/test_inert_report.py`** (end to end):
  - Hostile text in every model field and note is validated and reported.
  - A second case edits `collect()` output with a hostile hotspot file name, branch, repo name, scan window and warnings. It adds validator errors that start with block markers, and hostile confidence, pattern IDs, key, evidence type and service-context values.
  - Every `<a href>` must start with the fixture's link base. There must be no `<img>` and no elements beyond the report's own. Tables keep their rows, and there is exactly one `<h1>`.
- **Code review:**
  - protocol-relative `//` URLs were still linked by linkify-it, including metadata IPs such as `//169.254.169.254/…`;
  - letterless GitHub emoji, and raw bidi characters in the module's own source;
  - the end-to-end href check now uses both renderers, and the fuzz covers every position (nested item, heading, bold, emphasis, `<sub>`);
  - the renderer versions are pinned in CI and in the documented commands.
- **Gating:** one helper, `_require_renderers()`. It skips when any renderer package is missing, and calls `pytest.fail` instead when `THUNDERSTRUCK_REQUIRE_RENDERER` is set, which CI does. CI and CLAUDE.md install `markdown-it-py`, `linkify-it-py` and `cmarkgfm`.
- **Sample report (AC-5):** regenerated. FR-003's quoted injection text renders inertly.

## 5. Decisions

| Decision | Rationale |
|---|---|
| Escape a minimal punctuation set instead of wrapping all prose in code spans | Findings stay readable prose. The escaped characters render as themselves. |
| Linkish substrings become code spans | Escaping can't stop GFM's extended autolinks or GitHub's emoji filter, which run on text. A code span can. |
| Collapse line breaks | One field can never start a block, a heading, a list or a table row (AC-2). |
| One module for all Markdown rendering primitives | `report.py` had two ad-hoc styles. One place to test and to extend. |
| A real renderer in the tests, required in CI | AC-6 asks for rendered output. String checks alone would miss renderer behaviour. |

## 6. Design review (2026-09-24)

A review prototyped §2 as first written and rendered it with cmark-gfm and markdown-it. It found:

- **3 blockers:** case-sensitive URL schemes, adjacent spans merging their fences, and GFM's broad e-mail forms.
- **5 majors:** the emoji pattern swallowing `https:`; a test renderer that didn't match GitHub; text at the start of a list item; missed sites; and test gating.
- **4 minors:** code-span edge cases, control and bidi characters, whitespace rules, and line-break semantics.

All are fixed above. The token-level rule in §2.2 replaced the substring regexes after fuzzing kept finding linkify edge cases (`e.co_`, `a+.co`, `@+x.io`, `.@=.io`).

Out of scope, and filed separately:
- #32: a findings file can assert its own `validated_with` stamp and skip validation in `report.py`;
- #33: the S10 Java detector's speed test runs at its 1.0 s budget on Python 3.13.

## 7. Open design questions

- GitHub also renders Mermaid and math fenced blocks, and footnote syntax `[^1]`. Fences can't start without a newline, and `[` is escaped, so none of these can start from a field. They are listed here in case the renderer changes.
