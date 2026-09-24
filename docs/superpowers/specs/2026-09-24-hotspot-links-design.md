# Hotspot links: design

**Requirements:** [#24](https://github.com/tomstagl/thunderstruck/issues/24). The problem, stories, scope, acceptance criteria (AC-n) and decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-24-hotspot-links.md`
**Builds on:** the source-links design (`2026-09-24-source-links-design.md`, #22) and inert report text (`2026-09-24-inert-report-text-design.md`, #28).

## 1. Architecture

```
signals.py    unchanged
bundle.py     unchanged    bundles stay byte-identical
validate.py   unchanged
links.py      + history    a history template per provider, LinkContext.history(),
                           a summarised stale-file warning
report.py     link_refs    also collects hotspot, clean and incomplete files, and runs
                           whenever the report lists any file, with or without findings
guardrail.py  unchanged    index.json keeps its shape (AC-5)
```

Nothing new reaches a URL. Hotspot files come from `hotspots.json`, which `signals.py` built from `git ls-files`. Clean and incomplete entries carry the same `hs["file"]` values; `collect()` copies them from `hotspots.json`, never from a findings file. Every path still goes through `LinkContext.code()`, which applies `c.ref_path`, the `unlinked` set and percent-encoding, exactly as for a finding's location (#22).

## 2. `links.py`

### 2.1 History template

A new `HISTORY` table, next to `TEMPLATES`, gives each provider's link to a file's change history up to the scanned commit:

| Provider | Template | Checked |
|---|---|---|
| github | `{base}/commits/{sha}/{path}` | 200 on a public repository |
| gitlab | `{base}/-/commits/{sha}/{path}` | 200 on a public repository |
| bitbucket | `{base}/history-node/{sha}/{path}` | 200; an unknown route gives 404. The page is rendered client-side, so its content could not be checked without a browser. |

`LinkContext` gains `history_tpl: str | None`. `for_provider` fills it. `for_templates` leaves it `None`: custom templates get no history link, and the configuration contract does not change (AC-2).

`LinkContext.history(path) -> str | None` returns `None` when:
- there is no history template;
- the path is empty after `ref_path`;
- the path is in `unlinked`.

Otherwise it fills the template with `base`, `sha` and `encode_path(rel)`. A history page is a list of commits, not a rendered file, so `?plain=1` never applies.

A history link uses the same staleness rule as a code link. A file edited since the scan still has valid history up to the scanned commit, but a reader who sees one link and not the other would read that as a bug. One rule for both links is simpler to state and to test.

### 2.2 Summarised stale warning (AC-3)

`_resolve` builds the stale-file warning from `sorted(unlinked)`:

```
N file(s) differ from the scanned commit abc1234 or are not in it, and are not linked: a, b, c, d, e … and M more
```

- At most five names are shown. The suffix ` … and M more` appears only when `M > 0`.
- The word "cited" is dropped, because the set now includes listed hotspots as well as cited evidence. The rest of the sentence is unchanged, so existing assertions on it still hold.
- The warning is rendered through `md.text`, as today.

This is the same shape as the unpushed-commits warning, which already caps at five.

The names are shown as they are, not quoted. A file name containing `, ` or ` … and 9 more` could make the list misleading. It can't make a link: the warning still goes through `md.text`. That risk is accepted.

### 2.3 Chunked git calls

`_stale_paths` now receives every hotspot path as well as the cited ones, and `--top` has no upper limit. A single `ls-tree`, `diff` or `ls-files` call could exceed the command-line limit (about 32K characters on Windows). The resulting `OSError` would unlink every reference, findings included. `_stale_paths` therefore splits the paths into chunks of at most `PATHS_PER_CALL = 100` paths and `CHARS_PER_CALL = 8000` characters, and merges the results.

### 2.4 Template characters

A custom template's literal text now reaches a table cell. There, a `|` splits the row, and whitespace, `(`, `)`, `<`, `>`, `[`, `]`, a backtick, `\` or `"` would end the link or change its meaning. `template_error` rejects exactly those characters and controls, and names the one it found. Everything else stays allowed, including the `$`, `!`, `*` and `'` that some hosts use, such as Phabricator's `;{sha}${start}-{end}`.

A code template with `{start}` or `{end}` before the `#` has no whole-file form. Such a template links findings but can't link listed files. The report then says so in one warning, rather than leaving the sections silently plain.

## 3. `report.py`

### 3.1 `link_refs`

```python
link_refs(repo, head, findings, hotspots, listed) -> (meta, warnings, hotspot_links)
```

- `hotspots` is `hs["hotspots"]`.
- `listed` is `clean + failed`: dicts with a `file`, to which a `url` is added in place. `collect()` builds these dicts itself, so nothing on disk is written.
- `hotspot_links` maps a hotspot id to `{"url": …, "history_url": …}`.

Behaviour:
1. If there are no findings, no hotspots and no listed entries, return `(None, [], {})`, as today.
2. Otherwise gather paths from findings (unchanged), from every hotspot file, and from every listed file. Call `links.link_context` once. A report without findings now reaches it too (AC-1, AC-6).
3. With a context:
   - each listed entry gets `url = ctx.code(file)`;
   - each hotspot gets `url = ctx.code(file)` and `history_url = ctx.history(file)`.
4. Without a context (profile unreadable, linking impossible, or an internal error): every such `url` and `history_url` is `None`. The single warning from `link_context` is returned as today, so AC-4's "at most one not-linked warning" holds for every report. `enabled = false` still returns no warning.

A path that fails `c.path_problem` gets no link. A hotspot path is trusted input, but the check costs nothing and keeps the rule identical to `_location_url`.

`collect()` stores `hotspot_links` in `data`.

### 3.2 `report.md`

| Section | Before | After |
|---|---|---|
| Ranked hotspots, file cell | `` `f` `` | `` [`f`](url) · [history](history_url) ``; either link is dropped when its URL is `None` |
| Clean list | `` - **H04** `f` — note `` | `` - **H04** [`f`](url) — note `` |
| Incomplete list | `` - **H07** `f` — reason `` | `` - **H07** [`f`](url) — reason `` |

- File names use `md.linked(file, url, cell=…)`, the same primitive as #22's links.
- The word `history` is the tool's own text. Nothing written by a model or the scanned repository reaches a link text or target (#28).
- With no URL, `md.linked` returns exactly `md.code(file, cell)`, so an unlinked report is byte-identical to today's (AC-4).

### 3.3 `report.json` (AC-5)

- `hotspots[]` gains `url` and `history_url`.
- `clean[]` and `incomplete[]` gain `url`.
- Each is `null` when unlinked, the same representation as #22 AC-8. The keys are always present, so consumers don't need to probe for them.
- `index.json` is built only from findings and does not change. The guardrail reads only `index.json`.

## 4. Degradation

| Case | Result |
|---|---|
| No remote, unknown host, bad `[links]`, unreadable profile, git failure | Plain names everywhere, one "references are not linked" warning, with or without findings |
| `enabled = false` | Plain names, no warning |
| Custom templates | Code links, no history links, no warning |
| Hotspot file edited, staged, committed after the scan, untracked, assume-unchanged, a symlink or a submodule at the scanned commit | That file is plain in every section, and the summarised warning names it |
| Report without findings on an unpushed branch | Now linked, with #22's "resolve once pushed" warning. Before, such a report had no links and so no warning. |

## 5. Test strategy

`tests/test_report_links.py`, on the fixture with a github.com origin:

- **Hotspots, AC-1, AC-2:** every table row links `blob/<sha>/<file>` and `commits/<sha>/<file>`.
- **No findings, AC-6:** every hotspot comes back clean. The clean list and the table are linked, and `report.json` carries the URLs.
- **Incomplete, AC-6:** no investigator output. The incomplete list is linked.
- **Stale hotspot, AC-3:** parametrised over edited, staged, committed after the scan, untracked (`git rm --cached`), and assume-unchanged. A symlink case points a hotspot at a symlink committed at the scanned commit. Each case checks that the entry is plain in the table and in its list, and has no history link.
- **Warning cap, AC-3:** seven stale hotspots give a count of 7, five names, and "… and 2 more". There is also a unit test on the sentence.
- **No remote / disabled, AC-4:** in a report without findings: exactly one warning with no remote, none when disabled, and the sections are byte-identical to the plain rendering.
- **Custom templates, AC-2:** code links present, no `history`.
- **JSON, AC-5:** `url` and `history_url` keys are present (null or a string), and `index.json` has no `url`.
- **Inertness:** a hostile hotspot file name renders with no stray `<a>` under both renderers. `test_inert_report.py` already fuzzes the hotspot table; it gains the linked case.

`tests/test_links.py`: `history()` for the three providers, templates giving `None`, and an unlinked path giving `None`.

`tests/test_sample_report.py`, AC-7 and the success measure: in `examples/sample-report.md`, every ranked hotspot row has a code link and a history link, and every clean-list entry has a code link.

## 6. Design review (2026-09-24)

No blockers. Changes made:
- chunked git calls (§2.3);
- restricted template characters (§2.4), narrowed after the code review to a blocklist so existing templates keep working;
- chunks bounded by length as well as count (§2.3), and a warning for templates with no whole-file form (§2.4), both from the code review;
- the inertness test builds real links for hostile names, since hostile names set after `collect()` would never be linked;
- URLs are `None` on every failure path;
- more stale cases at the report level (assume-unchanged);
- a `path_problem` test;
- the unpushed-branch note (§4);
- the accepted naming risk (§2.2).

## 7. Decisions

| Decision | Rationale |
|---|---|
| History link in the file cell, not a new column | The table is already seven columns wide. A new column would change its shape for every reader. |
| One staleness rule for code and history links | One rule to state and test. Readers can't tell apart "history still valid" from "link missing by mistake". |
| URL maps kept in `data`, not written into `hotspots.json` | `hotspots.json` is signal output and feeds bundles. Report-time presentation must not reach it. |
| No history for custom templates | That would need a new template key and config validation. The ticket keeps it out of scope. |

## 8. Open design questions

- Bitbucket's history page is a client-side app. The route answers 200 and unknown routes answer 404, but its rendered content was not checked. If users report a blank page, drop the Bitbucket history template: that is a one-line change.
