# Finding to ticket: design

**Requirements:** [#108](https://github.com/tomstagl/thunderstruck/issues/108), part of [#104](https://github.com/tomstagl/thunderstruck/issues/104). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-12-finding-to-ticket.md`.
**Builds on:** [`2026-11-12-fix-impact-in-findings-design.md`](2026-11-12-fix-impact-in-findings-design.md) (#105, "A", its §16 is this ticket's input contract) and [`2026-11-12-fix-and-review-guidance-design.md`](2026-11-12-fix-and-review-guidance-design.md) (#107, "C", its §2 and §11 fix where the guidance lives and how a ticket links it). Neither was merged when this was written; §2 lists what is relied on, and the plan's Task 0 checks it.
**Evidence:** `scripts/report.py`, `scripts/links.py`, `scripts/validate.py`, `scripts/mdtext.py` and `scripts/gen_sample_report.py` as read at the commit this was written against (before A and C). Every `file:line` below is from that commit and drifts.

In this repository "ticket" also names a GitHub issue for developing thunderstruck (`.claude/skills/implement-ticket/`, `pick_ticket.py`, CLAUDE.md's "Tickets, specs and plans"). Here a **finding ticket**, or ticket, is the text a scan runner files in the *scanned* repository's tracker. §3 says how the names keep apart.

## 1. Architecture

```
/thunderstruck-ticket <key>   skill, runs in the host session
  1  finding_ticket.py --key K     deterministic   every section from the finding; judgement sections "Not assessed"
  2  host session's model          ← MODEL →       optional: writes <key>.sections.json, four short lists          (§6)
  3  finding_ticket.py --key K     deterministic   reads and validates that file, shows it labelled as a proposal

  report.json ─────────────┐   (findings, links, urls, check, A's fields; never repo.root, never generated_at)
  git, at the scanned commit ┼─→ finding_ticket.py ─→ .thunderstruck/tickets/<key>.md
  <key>.sections.json  ─────┘   refuses, writes nothing, when the code no longer matches the scan             (§8)
```

The governing rule holds: whether a snippet equals the scanned commit's text, which link a reference gets, what a section says when it has no data and what a status may be are computed. The model's one job is the four sections no finding field holds (§6).

## 2. What this relies on

**From A (#105), §16 of its spec, as the contract stands now.** In `report.json` `findings[]`: `blast_radius`, `blast_items` (`claim`, `basis`, `evidence` positions), `not_checked`, `implicit_guarantees`, `no_guarantees_reason`, `check.guarantees`, `check.not_checked`; `_common.IMPACT_SENTENCES`, `guarantee_state`, `not_checked_states`; the renderers `report.render_impact`, `render_guarantees` and `render_not_checked`, which this ticket calls and does not copy; `VALIDATION_RULES` 5. If A's review changes a name, the plan's Task 0 prints `MISSING` and the ticket stops; the fix is an amendment to this plan, not new design.

**From C (#107), §2 and §11 of its spec.** The two documents at `docs/fix-agent-instructions.md` and `docs/review-briefs.md`, never edited here; the README section `## From a finding to a reviewed fix`, which this ticket extends and whose heading it keeps; the URL form `<repository>/blob/main/docs/<name>.md` with `repository` from `plugin.json`; that a script must not import from `tests/`.

**From the code that exists.**

- `report.json` carries `scanned_at` (`report.py:1106`, the scan's own timestamp, equal across rebuilds of one scan) and `generated_at` (`report.py:1105`, the clock at rendering: volatile). `repo.root` is an absolute path (`signals.py:588`).
- Every reference has a `url` set by the tool, never by a model: `_set_urls` (`report.py:424`) overwrites it. `links` is `{provider, base_url, sha, remote}` or `null` (`report.py:369-371`); when `null`, the reason is one `references are not linked: …` entry in `warnings` and `run_warnings` (`links.NOT_LINKED`, `links.py:250`), except when `[links] enabled = false`, which is silent (`links.py:288-289`).
- `links._stale_paths` (`links.py:423`) is the existing test for "this file is what the scanned commit has": a regular blob in `ls-tree`, clean in `git diff`, and neither assume-unchanged nor skip-worktree.
- `content_hash` and `evidence_hashes` are sha256 of *working-tree bytes at validation time* (`validate.py:633-642`, `720`); nothing compares them today.
- Lines are counted at `\n` (`validate.py:109`, `_count_lines`); `mdtext.code` is single-line and `mdtext.text` flattens (`mdtext.py:59`, `103`); no multi-line verbatim primitive exists. `verify.py:150` shows the fence rule (longer than any backtick run inside).
- Scripts write only under `.thunderstruck/` (README, "What you get"; `orchestration.md`).

## 3. The command (Decision 1)

| | |
|---|---|
| Skill | `skills/thunderstruck-ticket/SKILL.md`, invoked `/thunderstruck-ticket <key>`. Auto-discovered; `plugin.json` is not touched (CLAUDE.md, *Plugin manifest*). |
| Script | `scripts/finding_ticket.py`, run as `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/finding_ticket.py" …` in the skill (`tests/test_plugin_paths.py` checks the path exists). |
| Flags | `--repo`, `--key KEY` (12 lowercase hex), `--list` (print every reported finding as `key · id · location · failure mode`, no ticket), `--status` (§10). Exactly one of `--key` and `--list`. |
| Output | `.thunderstruck/tickets/<key>.md`, replaced atomically; `.thunderstruck/tickets/<key>.sections.json` is the optional input (§6). One stdout line names the relative path. Nothing is written elsewhere. |
| Exit | 0 written (or listed); 2 for every refusal and stop, the message on stderr naming the cause and the way forward (`_common.die`). |

**Lookup is by `key`, never `id`.** `FR-001` renumbers whenever ranking changes (CLAUDE.md, *`id` vs `key`*), so a ticket and its file name carry the key, and the header states it. `--list` prints the id beside the key because the reader sees ids in the report. The skill may turn an id the user typed into a key once, against the current report (`/thunderstruck-verify` accepts both already); the script never matches on an id. A key must match `^[0-9a-f]{12}$` before it is used in a path, so `../x` cannot leave `tickets/`.

**Names.** "Ticket" is the ticket's and the source PRD's word, so the skill keeps it. The script is `finding_ticket.py` and the folder lives under `.thunderstruck/`, so neither collides with `pick_ticket.py` or `implement-ticket`, which are development tooling and never ship. The README section says: "In this section a ticket is the issue you file in your own repository from a finding. It is not one of the GitHub issues used to develop thunderstruck." CLAUDE.md says the same in one line next to *Tickets, specs and plans*. C's neutrality rules derive forbidden names from the tree; the new skill and script names join them, which cannot affect the two documents because they predate both.

## 4. Choosing the finding

`report.json` must exist and carry `schema == thunderstruck.report/v2` (`report_html.py:95`'s rule, same message). The key is looked up in `findings[]`. Not found there:

| Case | Refusal names |
|---|---|
| bad key shape | the shape |
| in `refuted[]` | that a check refuted it, and that no ticket is made for a refuted finding (Decision 9) |
| a key listed under another finding's `also_at` | the survivor's key: this finding is reported there as a duplicate |
| unknown | the key, and up to 20 keys in report order |

All four write nothing.

## 5. Layout, and where every section comes from (AC-1, AC-7)

Markdown only: headings, bullets, bold, code spans, links, fenced blocks. No table, HTML, image or task list (§11). Sections in the ticket's order; `SECTIONS` in the script holds the order and a test pins it. A section whose data is absent reads `Not assessed: <reason>.`, the reason a fixed sentence from the script, never model text.

| Section | Source | Absent, exact reason |
|---|---|---|
| Title `# …` | `failure_mode`, whitespace flattened, at most 100 characters, cut at a word with `…`. #47 will replace this | none (required field) |
| Header | location `file:lines` linked with `location.url`, `location.symbol`; `confidence` (reported; "claimed X" when lower); `check.status`; the status (§10); `key`; `scanned_at[:10]`; a Links line (§9) | date: `not recorded` |
| Summary | `failure_mode` in full, then `prediction` | no prediction: the line is left out |
| Trigger | `trigger_condition`, the gate marker (`_common.GATE_MARKERS`), `report.render_preconditions` | none |
| Mechanism | the `amplifier` line, then one step per `code` evidence item, in evidence order (§7) | amplifier: `Amplifier: not stated.`; no code evidence: `Not assessed: the finding cites no code.` |
| Persistence | `sustaining_effect` | `the finding states no sustaining effect; it is given only when the code shows one` |
| Blast radius | `blast_radius`, then `report.render_impact` | A's sentences for an older finding |
| Implicit guarantees at risk | `report.render_guarantees` | A's |
| Evidence status | `report.render_check`; every `evidence` item and every `check.evidence` item, linked or labelled (§9); `report.render_history` | none |
| Assumptions and open questions | `report.render_not_checked` (each item with `how_to_check` and its state); `confidence_rationale` | A's |
| Reproduce | `how_to_verify`, then the recorded-reproduction line (§10) | `No reproduction is recorded for this finding.` |
| Detection | no source | `a finding records no detection signal (the log line, metric or alert that would show the failure)` |
| Fix options, Acceptance criteria, Out of scope, Rollout and rollback | the drafted section (§6); the first two also carry the guidance line (§9) | `no proposal was drafted for this section; a finding records none and the plugin proposes none`, or the reason a draft was not used (§6) |
| Provenance | scanned commit, scan stamp, key, hotspot id, `schema`, whether verification ran, which sections were proposals and the sha256 of their file | none |
| Disclaimer | a constant: the finding is a hypothesis with a way to prove it wrong, not a confirmed defect; proposals are unverified | none |

A's renderers return `report.md` lines (`**Traced impact** — …`), used as they are: one wording for one fact, which A's `IMPACT_SENTENCES` already guarantees. A finding without A's fields shows A's "not assessed" sentences (AC-7). The renderers index `f["check"]["status"]`, so the script gives a finding without a valid `check` the `unchecked` one `report.collect` would (`report.py:140-146`).

**No severity.** A finding has none, and "why this severity" has no data. The header shows confidence and check status (Decision 10).

## 6. The four judgement sections (Decision 2, AC-10)

Fix options, acceptance criteria, out of scope, and rollout and rollback are in no finding field. The ticket's product decision is that a model drafts them, labelled and inert, and a missing draft reads "not assessed". That is a model step the pipeline does not have, and CLAUDE.md says "The investigator and the skeptic are the only inference in the system" (line 82).

**Chosen: (a), a deterministic script with an optional drafted-sections file.** AC-10 already speaks of "drafted sections" as an input. The script never calls a model and never needs the file; the host session's model, which is already running the skill, may write it. The file is untrusted model output, validated like findings are, and what it says is shown as a proposal.

```json
{"schema": "thunderstruck.ticket-sections/v1",
 "key": "483fd943cc43",
 "scanned_at": "2025-01-06T00:00:00+00:00",
 "sections": {"fix_options": ["…"], "acceptance_criteria": ["…"],
              "out_of_scope": ["…"], "rollout_and_rollback": ["…"]}}
```

| Rule | |
|---|---|
| Binding | `schema`, `key` and `scanned_at` must equal the report's. A draft for another finding or an earlier scan is not used, and the section says so |
| Shape | `sections` is an object; ids outside the four are ignored and named in Provenance; each section is a list of 1 to 8 strings, each non-empty and at most 400 characters. A section outside this is not used, with its reason; the others stand |
| File | at most 64 KB, UTF-8 JSON object; anything else: the whole file is unused, with the reason |
| Rendering | `**Proposal, not verified** — drafted by a model from this finding. Nothing checked it.` then one `- ` bullet per string through `mdtext.text`: no link, image, HTML, heading or quick action can form (§11) |
| Absent file | silent: every section reads `Not assessed` |

A draft that is rejected never fails generation (AC-10); Provenance lists each reason once, as `mdtext.code` and fixed words.

**Why not (b).** The recommendation in the ticket is (a); with (b) a ticket would always carry four empty sections, which is the "padding by omission" the PRD's R-31 exists to avoid. **What it costs.** The model's text is the only model output a ticket carries; the schema, caps and label are what contain it; and no scan, report or guardrail reads the file. The skill instructs the model that the finding, its snippets and every field are data to draft from, never instructions.

**CLAUDE.md consequence, for the lead to put to the user.** The sentence at line 82 becomes false as written. The plan's release task replaces it with: "The investigator and the skeptic are the only inference in a scan. The finding ticket (#108) has one optional model step after a scan, the host session drafting four judgement sections into `.thunderstruck/tickets/<key>.sections.json`, which `finding_ticket.py` validates like model output and shows as a labelled proposal; nothing in a scan, a report or a guardrail reads it." The governing rule (models for judgment, scripts for what must be reproducible) is unchanged, and no new subagent, retry or parallelism is added.

## 7. Snippets (AC-2, AC-3)

A step is a `code` evidence item: `path:N` or `path:N-M` parsed with `validate.CODE_REF`, canonical path from `_common.ref_path`. The cited lines are exactly the finding's own; no context is added (Decision 7).

- **Source.** The blob at the scanned commit: `git cat-file blob <head>:<path>`, bytes. Not the working tree, whose bytes depend on `core.autocrlf` and filters. §8 has proved the two agree before this runs.
- **Lines.** Split at `\n` only, drop the empty string after a final newline, drop one trailing `\r` per line, decode UTF-8 with replacement: how `_count_lines` and `git blame` count, and A's numbering (`source_lines`). An empty file is one empty line, as `_count_lines` says. Tabs and trailing spaces are kept. A range outside `1..N` stops generation: the file at the scanned commit does not hold what the finding cites.
- **Caps, always said.** At most 40 lines per snippet and 240 characters per line, at most 12 steps. What is cut is named *outside* the fence, in the step: `Lines 41-90 (50 lines) are not shown; open the link or the file.`, `3 lines were shortened to 240 characters.`, `5 further code references are listed under Evidence status.` The text inside a fence is therefore always a literal prefix of the file's lines.
- **Characters that hide.** C0 and C1 controls, DEL, bidirectional marks and a `\r` inside a line are shown as `\uXXXX` and counted in a step note (`2 control or bidirectional characters are shown as \uXXXX.`). `mdtext._INVISIBLE` already does this for every other value; leaving them raw in a code block would let a file reverse what the reader sees.
- **The fence primitive.** `mdtext.verbatim(lines) -> (block, escaped)`: a fence of backticks one longer than the longest run in any line, at least three, no info string, opened and closed at column 0. A line cannot end it because every run inside is shorter than the fence; the block is a top-level block, never nested in a list, so no indentation rule applies. A hostile test covers backticks, HTML, a link, a heading, a very long line and a lone `\r`, in both markdown engines of #28 (§12).
- **Step layout.** `### Step n`, the permalink line, the fence, `What to notice: <note>` (the evidence `note`, through `mdtext.text`). Headings, not an ordered list: a fence inside a list item needs indentation that trackers handle differently.

## 8. Stop when the code is not the scan (AC-3)

Generation reads `repo.head` from `report.json` and checks, in this order, for every file the ticket quotes (the finding's `location.file` and each `code` evidence path):

1. `head` is 40 lowercase hex, and `git cat-file -e <head>^{commit}` succeeds. A scan that recorded no commit, a shallow or different clone without it: stop.
2. No path fails `_common.path_problem`.
3. `links.stale_paths(repo, head, paths)`, a public name for `links._stale_paths`, returns none. It is the rule the links already use, so a file a link would leave unlinked is a file a ticket refuses.
4. For each path, `_common.sha256_file(repo/path)` equals the finding's `content_hash` (the location file) or `evidence_hashes[path]`. Both were taken of working-tree bytes, so comparing working-tree bytes needs no assumption about line-ending conversion. A missing recorded hash is a stop: nothing proves the file.

| Condition | Caught by | Message says the file… |
|---|---|---|
| untracked | 3: not a regular blob in `ls-tree` | is not tracked by git |
| symlink, submodule | 3 (modes 120000, 160000) | is a symbolic link, is a submodule |
| missing | 3 | is missing from the working tree |
| edited, staged, committed since | 3: `git diff` against `head` | differs from the scanned commit |
| assume-unchanged, skip-worktree | 3: `ls-files -v` tag | differs from the scanned commit |
| edited, scanned dirty, then reverted | 4 | changed since the scan recorded it |
| head unknown or not in this clone | 1 | (names the commit) |
| git fails or times out | all | git did not answer |
| a dirty file nothing cites | not compared | no stop |
| `core.autocrlf` | 3 uses git's own comparison, 4 compares like with like | no stop |

The cause is named by `_why_stale`, a few `git` and `os` checks used for the message only; the decision is always step 3 or 4. The message names up to five files then a count (`links.named`), quoted as JSON strings, then the way forward in these words: *Rescan with `/thunderstruck-scan`, or check out the scanned commit `<40 hex>` (`git switch --detach <sha>`; stash or commit edits to those files first) and run this again.* Exit 2, no ticket file written and an existing one left untouched.

## 9. Links (AC-4, AC-6)

- **Permalinks** come from `report.json`: `location.url` and each evidence item's `url`, taken verbatim from the tool's own field. Each is accepted only if it is a string beginning `https://` or `http://` with no whitespace or `<>()[]"'\` character; any other value is treated as no link. A hand-edited `report.json` therefore cannot plant `javascript:` or break out of a Markdown link. Nothing is built from a model string.
- **Links unavailable.** The header says `Links: not built.` and gives the reason the report recorded, the `references are not linked: …` entry from `run_warnings`; with none recorded and `links` `null`, the reason is `disabled in the repository's link settings (enabled = false)`, the one silent case. Refs then appear as code spans. Unrecognised host, invalid `[links]` and unreadable `.thunderstruck.toml` all arrive through the recorded entry.
- **Links by nature absent.** A catalog reference reads `… (not linked: catalog data has no source location)`, a dependency reference in `check.evidence` `… (not linked: a dependency's source is not in this repository)`, a commit the repository cannot resolve `… (not linked: commit not found)`. Any other `null` is `(not linked: no link could be built)`.
- **The guidance (C).** Fix options and acceptance criteria each end with *How to fix: [fix-agent-instructions.md](URL) · how to review: [review-briefs.md](URL)*. The ticket is filed in the scanned repository, which has neither document, so a relative path would be a dead link there. `URL` is `<repository>/blob/main/docs/<name>.md`, `repository` read from the plugin's `.claude-plugin/plugin.json` through `_common.plugin_root()` and accepted only if `links.valid_base_url` does. The two paths are the constant `GUIDANCE` in the script, equal to C's `PUBLISHED`, and a test asserts both the equality and that the files exist. The link names current `main`: versioning the documents is out of scope (the ticket's Out). **Offline** the file is generated without a network, since nothing is fetched. **From a fork** whose `plugin.json` names its own `repository` the links point there; one that does not keeps pointing at the upstream. **If `plugin.json` is unreadable or has no valid `repository`** the line reads `fix-agent-instructions.md and review-briefs.md in the thunderstruck repository (no link could be built)`; generation never fails for it.

## 10. Status (AC-5)

`--status` takes `Hypothesis` (default), `Reproduced`, `Fix proposed`, `Fix reviewed`, case-insensitive, `-` or `_` for a space. `Reproduced` is the one claim the plugin can check, so it is the one it checks (Decision 6): `finding_ticket.recorded_reproduction(finding)` returns the finding's recorded failing reproduction, and returns `None` today, because nothing records one (`/thunderstruck-verify` leaves no data; #103 will). A request for `Reproduced` while it returns `None` is refused before any git call:

> status Reproduced refused for finding `<key>`: no failing reproduction is recorded for it. A reproduction is a failing test that a verification run left behind and recorded; thunderstruck does not record one yet (issue #103 in the thunderstruck repository). Ask for Hypothesis, or record a reproduction first. No ticket was written.

The header prints the status; Reproduce ends `No reproduction is recorded for this finding.` while the function returns `None`. The test pins both the `None` and the refusal. The extension point is §16.

## 11. Safety (AC-8, AC-9)

**Inert text.** Every value a model or the repository wrote goes through `mdtext.text` or `mdtext.code`, or into the fence of §7; only the tool builds links (`mdtext.linked`). A's renderers and `render_check` already do this. All model text follows a label or a bullet, never the start of a line, so a leading `/close` or `#` cannot act as a quick action or a heading.

**Tracker references.** `mdtext` today escapes Markdown but not what a tracker adds after rendering: `#12` (an issue link and a cross-reference), a short SHA, GitLab's `!12`, a Jira key such as `ABC-123`. `@name` is already a code span (`mdtext._LINKISH` has `@`). The plan adds `#<digit>`, `!<digit>`, a `LETTERS-<digit>` key and a run of 7 to 40 hex digits to `_LINKISH`, so such a token becomes a code span, which trackers do not link. This changes `report.md` too, and only for text containing those tokens; the plan runs the suite and the sample check to show what moved. A tracker's syntax beyond these is not covered.

**Machine values.** No absolute path, user name or host of the scan: `repo.root`, `repo.branch` (a branch can carry a user name) and `generated_at` are never read. Model text can still name the scanner's root, so every string passes `_scrub` first, which replaces `report.repo.root`, the resolved `--repo` and the home directory with `<repo>` and `<home>`; a test plants each in a note and in a snippet-adjacent field. Permalinks and the remote's web address are the repository's own public address, which AC-4 requires; credentials are dropped upstream (`links.py:72`).

**What the tracker renders.** The file is CommonMark with GitHub-style fenced code. GitHub, GitLab and Bitbucket render it fully (inferred; this repository tests cmark-gfm and markdown-it-py only); a tracker that does not render Markdown shows the same text with its marks, still readable. The ticket contains no HTML, image, table, task list, footnote or emoji shortcode, so there is no feature a stricter renderer could drop. A snippet is a fenced block, so a tracker's autolinking and quick actions are not applied inside it (the GFM spec; GitLab's own rule for quick actions was not tested).

**Writes.** Only `.thunderstruck/tickets/`: a symlinked `tickets` directory is refused, the file is replaced atomically (`os.replace` swaps a symlink and never follows one), and the key is validated before it becomes a path. `report.json` is untrusted input: every string is escaped and every URL checked.

## 12. Determinism and degradation (AC-10)

The ticket is a pure function of `report.json`, the blobs at `head`, the optional sections file and the arguments: no clock, no environment, no locale, no absolute path, no `set` order, no plugin version (a release would otherwise stale the sample). The date is `scanned_at`. Generating twice is byte-identical.

| Input | Absent or bad |
|---|---|
| Sections file | `Not assessed` in four sections; a bad one adds a reason to Provenance |
| `plugin.json` | the guidance line without links (§9) |
| A's fields | A's "not assessed" sentences |
| `check` | `unchecked` |
| `links` | §9 |
| `scanned_at` | the date reads `not recorded`; a draft cannot bind and is unused |
| `report.json`, its schema, the key, a stale or unreadable file, an unknown commit | **hard stop**, named, exit 2, nothing written |

## 13. The sample (AC-11)

`examples/sample-ticket.md` is the ticket for FR-001 (`client/releases.ts`: two retry layers, a guarantee, a traced and a catalog item, an upheld check), produced by the real pipeline. It extends `gen_sample_report.py` rather than adding a generator: one run already builds the validated, verified, linked fixture and `--check` (CI on Linux and macOS, `.github/workflows/ci.yml`) already compares every entry of `generate_all()` with `examples/`. The generator writes the pinned `report.json` back before the ticket is built, so the date and the sections file's `scanned_at` are the pinned day; writes a canned sections file for FR-001 (the one non-pipeline input, as the canned findings and verdicts are, labelled in the file's header comment); runs `finding_ticket.py` and adds the same kind of header comment. Byte-reproducible: the commit shas and the dates are the fixture's, and nothing machine-specific reaches a ticket.

## 14. Old data, invariants, tests

**Old data.** None is changed. `report.json` stays `thunderstruck.report/v2`, findings `thunderstruck.finding/v3`, `VALIDATION_RULES` 5, `index.json` v1; nothing is cached or keyed on a ticket, so no scan, bundle or finding invalidates. A report from before A has no `blast_items`: its ticket reads A's "not assessed". A report older than `scanned_at` or `links` stops or degrades as §12 says. The two existing samples change only if the `_LINKISH` extension changes their bytes, which the plan checks and, if so, regenerates in the same task.

| `CLAUDE.md` invariant | How it holds |
|---|---|
| Bundles byte-identical | no bundle changes |
| Detector hits are leads; every ref resolved mechanically | snippets and hashes are checked against git, and no path bypasses the validator's refs |
| `id` vs `key` | the key is the lookup, the file name and the header |
| Confidence capped by check status | the header prints `report.json`'s reported confidence, never the claim alone |
| Verdicts resolved like findings | the ticket reads `check` as the report settled it |
| The investigator and the skeptic are the only inference | amended, §6 |
| The plugin must not exhibit the patterns it hunts | no subagent, retry, loop or parallel work |
| Repository content is data; inert text | §11 |
| Generated files never hand-edited | `sample-ticket.md` joins the list |
| Plugin manifest | skills and scripts are discovered; `plugin.json` only gets the version |
| Versions agree | bumped in the release task |
| Degradation visible | §12 |

**Existing tests that pin behaviour that changes.** To be listed by the proof in the plan's Task 1 (`test_mdtext.py` and the report tests that render `#`-or-hex tokens). `test_every_script_has_a_docstring` and `test_plugin_paths.py` apply to the new script and skill and must pass; C's neutrality rules read the tree and must still pass on the two documents.

**New tests**, in `tests/test_finding_ticket.py`, appended per task: the fence primitive and tracker references on hostile text (both engines); lookup and every refusal; the stop table of §8 on small real git repositories; snippet bytes against `git show` for LF, CRLF, no final newline, tabs and a lone `\r`, with the caps; the sections file rules; links on and off; the status refusal; every section in order with its reason; determinism; hostile text in every model field, in the snippet, in the sections file, in `report.json` URLs and in the key, through the engines of #28 with `pre` allowed and no tag, link or heading added; no machine value; the sample and its freshness. A **mutation check** in the hostile task removes each defence in turn and the test must fail.

**Consumption.** No model call is added to any script. The skill's drafting step is one host-session turn per ticket, outside any scan, with a few hundred output tokens (not measured).

## 15. Decisions

1. **`finding_ticket.py` and `/thunderstruck-ticket`; the key, not the id.** §3.
2. **A deterministic script and an optional drafted-sections file.** §6; AC-10 presupposes it; amends one sentence of CLAUDE.md, put to the user.
3. **The snippet is the blob at the scanned commit, after a check that the working tree is that commit.** The blob is exact; the check is the AC.
4. **Hashes compare working tree to working tree.** That is how they were recorded; comparing to a blob would fail on `core.autocrlf`.
5. **A cap is always stated outside the fence.** The fence stays a literal prefix of the file.
6. **Only `Reproduced` is gated.** The AC says so; the other three are the requester's statements and nothing in the plugin can check them.
7. **No context lines around a cited range.** The AC says "at its cited lines". Changing it is a constant and a test.
8. **Existing `url` fields, validated, never built.** AC-4; a plain check on top costs ten lines and closes a hand-edited `report.json`.
9. **A refuted or duplicate finding gets no ticket.** A ticket is something someone can act on; the refusal names why, and the report still lists it.
10. **Severity is omitted; no short variant.** The ticket's recommendations: no data exists, and a section with none says so instead of padding.
11. **Tracker references are code-spanned in `mdtext`, for every output.** One primitive, one rule; the alternative (a ticket-only variant) would leave A's renderers unprotected.
12. **The sample extends `gen_sample_report.py`.** §13.
13. **The guidance links name `main`.** C's decision; versioning is out of scope.

## 16. Extension points and open design questions

**Extension points.**

- **#103** records a reproduction. A follow-up changes `recorded_reproduction` to read that record, the header and Reproduce to show it, and the refusal test to assert acceptance; nothing else here changes. The record's format is #103's.
- **#47** gives a finding a one-line title: replace `title()`.
- **Related findings, a detection field, the lessons slot, document versions** each add a section or a line to §5's table; none is reserved here.
- **A short variant** needs a severity or a rule for "short": a new section list beside `SECTIONS`.
- **Opening in a tracker** reads `tickets/<key>.md`; it is not designed here.

**Open design questions.** None blocks the plan; each is built to the recommendation.

1. **Tracker references in `mdtext` for every output (Decision 11).** It changes `report.md` for text containing `#12`-like tokens or 7-or-more-hex words. Recommendation: yes, as built. Alternative: ticket-only, losing protection in A's renderers.
2. **Context lines.** Recommendation: none, per the AC's wording.
3. **Should `Fix proposed` or `Fix reviewed` need a recorded reproduction?** Recommendation: no, until #103 defines the record; then a follow-up decides.
