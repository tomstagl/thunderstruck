# Finding to ticket: design

**Requirements:** [#108](https://github.com/tomstagl/thunderstruck/issues/108), part of [#104](https://github.com/tomstagl/thunderstruck/issues/104). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-12-finding-to-ticket.md`.
**Builds on:** [`2026-11-12-fix-impact-in-findings-design.md`](2026-11-12-fix-impact-in-findings-design.md) (#105, "A", its §16 is this ticket's input contract) and [`2026-11-12-fix-and-review-guidance-design.md`](2026-11-12-fix-and-review-guidance-design.md) (#107, "C", its §2 and §11 fix where the guidance lives and how a ticket links it). Neither was merged when this was written; §2 lists what is relied on, and the plan's Task 0 checks it. Reconciled with `main` at 74805f7, which holds #102 (confirmed defaults) and #109 (call-site search).
**Evidence:** `scripts/report.py`, `scripts/links.py`, `scripts/validate.py`, `scripts/mdtext.py` and `scripts/gen_sample_report.py` as read at `main` 74805f7, before A and C are built. Every `file:line` below is from there and drifts.

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

**From A (#105), §16 of its spec, as the contract stands now.** In `report.json` `findings[]`: `blast_radius`, `blast_items` (`claim`, `basis`, `evidence` positions), `not_checked`, `implicit_guarantees`, `no_guarantees_reason`, `check.guarantees`, `check.not_checked`; `_common.IMPACT_SENTENCES`, `guarantee_state`, `not_checked_states`; the renderers `report.render_impact`, `render_guarantees` and `render_not_checked`, which this ticket calls and does not copy; `VALIDATION_RULES` 5 or more. A's contract for this ticket is unchanged by its reconciliation with #102; its one added sentence (#102's `confirmation.basis == "not_checked"` is unrelated to `check.not_checked`) affects nothing here. A's renderers now say a traced item *cites* code and that each cited line is checked to exist, not to connect; the ticket reuses that wording and asserts only the bold labels. If a name moves, the plan's Task 0 prints `MISSING` and the ticket stops; the fix is an amendment to this plan, not new design.

**From #102 (confirmed defaults), merged.** A finding in `report.json` now carries `preconditions[].confirmation` and `check.confirmations`, and `gate` has three values (`_common.GATES`: `none`, `unconfirmed_default`, `non_default_setting`, with `GATE_MARKERS` for the last two). The ticket's Trigger section calls `report.render_preconditions`, so each default reads `**Confirmed**` or `**Unconfirmed**` in #102's words, and the gate sentence is `GATE_MARKERS[gate]`: "This failure relies on a doubtful default." or "…needs a non-default setting." A report from before #102 reads `**Unconfirmed**: no check looked for where this default is registered`, #102's own wording for "not checked", which the ticket does not recompute. #102's `tests/test_no_execution.py` reviews where a process may start in any script; `finding_ticket._git` joins its list (§14). #109 changes nothing this ticket reads.

**From C (#107), §2 and §11 of its spec.** The two documents at `docs/fix-agent-instructions.md` and `docs/review-briefs.md`, never edited here; the README section `## From a finding to a reviewed fix`, which this ticket extends and whose heading it keeps; the URL form `<repository>/blob/main/docs/<name>.md` with `repository` from `plugin.json`; that a script must not import from `tests/`.

**From the code that exists.**

- `report.json` carries `scanned_at` (`report.py:1192`, the scan's own timestamp, equal across rebuilds of one scan) and `generated_at` (`report.py:1191`, the clock at rendering: volatile). `repo.root` is an absolute path (`signals.py:588`).
- Every reference has a `url` set by the tool, never by a model: `_set_urls` (`report.py:429`) overwrites it. `links` is `{provider, base_url, sha, remote}` or `null` (`report.py:375-377`); when `null`, the reason is one `references are not linked: …` entry in `warnings` and `run_warnings` (`links.NOT_LINKED`, `links.py:250`), except when `[links] enabled = false`, which is silent (`links.py:293-294`).
- `links._stale_paths` (`links.py:423`) is the existing test for "this file is what the scanned commit has": a regular blob in `ls-tree`, clean in `git diff`, and neither assume-unchanged nor skip-worktree.
- `content_hash` and `evidence_hashes` are sha256 of *working-tree bytes at validation time* (`validate.py:672`, `759`); nothing compares them today.
- Lines are counted at `\n` (`validate.py:110`, `_count_lines`); `mdtext.code` is single-line and `mdtext.text` flattens (`mdtext.py:59`, `103`); no multi-line verbatim primitive exists. `verify.py:158` shows the fence rule (longer than any backtick run inside).
- Scripts write only under `.thunderstruck/` (README, "What you get"; `orchestration.md`).

## 3. The command (Decision 1)

| | |
|---|---|
| Skill | `skills/thunderstruck-ticket/SKILL.md`, invoked `/thunderstruck-ticket <key>`. Auto-discovered; `plugin.json` is not touched (CLAUDE.md, *Plugin manifest*). |
| Script | `scripts/finding_ticket.py`, run as `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/finding_ticket.py" …` in the skill (`tests/test_plugin_paths.py` checks the path exists). |
| Flags | `--repo`, `--key KEY` (12 lowercase hex), `--list` (print every reported finding as `key · id · location · failure mode`, no ticket), `--status` (§10). Exactly one of `--key` and `--list`. |
| Output | `.thunderstruck/tickets/<key>.md`, replaced atomically; `.thunderstruck/tickets/<key>.sections.json` is the optional input (§6). One stdout line, `ticket for <key>: .thunderstruck/tickets/<key>.md (N sections not assessed, M drafted)`. Nothing is written elsewhere. |
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
| Trigger | `trigger_condition`, the gate marker (`_common.GATE_MARKERS`, two entries for three gates), `report.render_preconditions` (with #102's confirmation of each default) | none |
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

A's renderers return `report.md` lines (`**Traced impact** — …`), used as they are: one wording for one fact, which A's `IMPACT_SENTENCES` already guarantees. A finding without A's fields shows A's "not assessed" sentences (AC-7). The renderers index `f["check"]["status"]`, so the script gives a finding without a valid `check` the `unchecked` one `report.collect` would (`report.py:158-161`). Since #102, `collect` also derives each precondition's `confirmation`; a report written by it carries them, and the ticket reads what is there.

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

- **Source.** The blob at the scanned commit: `git cat-file blob <head>:<path>`, bytes. Not the working tree, whose bytes depend on `core.autocrlf` and filters. §8 has shown the working tree is the commit's file, by git's own comparison, before this runs. One filter breaks that: a file stored with Git LFS is a short pointer in the commit while the working tree holds the content, so a blob that starts `version https://git-lfs.github.com/spec/v1` is a stop (`"<path>" is stored with Git LFS at the scanned commit: the commit holds a pointer, not the code`), never shown as code.
- **Lines.** Split at `\n` only, drop the empty string after a final newline, drop one trailing `\r` per line, decode UTF-8 with replacement: how `_count_lines` and `git blame` count, and A's numbering (`source_lines`). A lone `\r` inside a line is shown as `\u000d` here, like every control character, where A's bundle shows `␍`: the bundle is read by a model, the ticket by a person, and `report.md` already shows controls this way. An empty file is one empty line, as `_count_lines` says. Tabs and trailing spaces are kept. A range outside `1..N` stops generation: the file at the scanned commit does not hold what the finding cites.
- **Caps, always said.** At most 40 lines per snippet and 240 characters per line, at most 12 steps. What is cut is named *outside* the fence, in the step: `Lines 41-90 (50 lines) not shown: open the link or the file.`, `3 lines were shortened to 240 characters.`, `5 further code references are listed under Evidence status.` The text inside a fence is therefore always a literal prefix of the file's lines.
- **The whole ticket is capped too (Decision 14).** `TRACKER_BODY_LIMIT = 65_536` is GitHub's limit on an issue body (a figure to verify against the tracker's current limit, said in a comment beside it), `TICKET_MARGIN = 5_536` the room left for what the cap cannot drop, and `MAX_TICKET_CHARS` their difference, 60,000. Twelve full steps are about 120,000 characters, so the per-step caps alone do not fit. When the ticket is longer, steps are dropped from the end, one at a time, and the Mechanism section says `N further steps are left out so that the ticket fits a tracker (at most 60,000 characters); the code references are listed under Evidence status.` Every reference stays in Evidence status. A ticket that is still longer with no step left (an enormous finding field) is a stop, named, writing nothing: a cut model field would be a silent edit of the finding.
- **Characters that hide.** C0 and C1 controls, DEL, bidirectional marks and a `\r` inside a line are shown as `\uXXXX` and counted in a step note (`2 control or bidirectional characters are shown as \uXXXX.`). `mdtext._INVISIBLE` already does this for every other value; leaving them raw in a code block would let a file reverse what the reader sees.
- **The fence primitive.** `mdtext.verbatim(lines) -> (block, escaped)`: a fence of backticks one longer than the longest run in any line, at least three, no info string, opened and closed at column 0. A line cannot end it because every run inside is shorter than the fence; the block is a top-level block, never nested in a list, so no indentation rule applies. A hostile test covers backticks, HTML, a link, a heading, a very long line and a lone `\r`, in both markdown engines of #28 (§12).
- **Step layout.** `### Step n`, the permalink line, the fence, `What to notice: <note>` (the evidence `note`, through `mdtext.text`). Headings, not an ordered list: a fence inside a list item needs indentation that trackers handle differently.

## 8. Stop when the code is not the scan (AC-3)

Generation reads `repo.head` from `report.json` and checks, in this order, for every file the ticket quotes (the finding's `location.file` and each `code` evidence path):

1. `head` is 40 lowercase hex, and `git cat-file -e <head>^{commit}` succeeds. A scan that recorded no commit, a shallow or different clone without it: stop.
2. No path fails `_common.path_problem`.
3. `links.stale_paths(repo, head, paths)`, a public name for `links._stale_paths`, returns none. It is the rule the links already use, so a file a link would leave unlinked is a file a ticket refuses.
4. For each path, `_common.sha256_file(repo/path)` equals the finding's `content_hash` (the location file) or `evidence_hashes[path]`. Both were taken of working-tree bytes, so comparing working-tree bytes needs no assumption about line-ending conversion. A missing recorded hash is a stop: nothing proves the file. A recorded hash that differs from the file now means one of two things: the file changed since the scan (undone by a checkout or not), or the scan saw it in a state the commit does not have (it was dirty when scanned). The check cannot tell which, so §8's message does not promise the checkout.

| Condition | Caught by | Message says the file… |
|---|---|---|
| untracked | 3: not a regular blob in `ls-tree` | is not tracked by git |
| symlink, submodule | 3 (modes 120000, 160000) | is a symbolic link, is a submodule |
| missing | 3 | is missing from the working tree |
| edited, staged, committed since | 3: `git diff` against `head` | differs from the scanned commit |
| assume-unchanged, skip-worktree | 3: `ls-files -v` tag | differs from the scanned commit |
| scanned dirty, now the commit's text (or edited since) | 4 | changed since the scan recorded it, and only a rescan fixes it |
| head unknown or not in this clone | 1 | (names the commit) |
| git fails or times out | all | git did not answer |
| a dirty file nothing cites | not compared | no stop |
| `core.autocrlf` | 3 uses git's own comparison, 4 compares like with like | no stop |

The cause is named by `_why_stale`, a few `git` and `os` checks used for the message only; the decision is always step 3 or 4. The message names up to five files then a count (`links.named`), quoted as JSON strings, then the way forward. When every problem is one of step 3 it is: *Rescan with `/thunderstruck-scan`, or check out the scanned commit `<40 hex>` (`git switch --detach <sha>`; stash or commit edits to those files first) and run this again. If it then stops with "changed since the scan recorded it", the scan saw that file in another state, and only a rescan fixes that.* When any problem is one of step 4 (the scan saw a file the commit does not have, so a checkout cannot fix it) it is only: *Rescan with `/thunderstruck-scan`. The scan saw a file above in a state the scanned commit does not have, so checking out the commit cannot fix that.* Exit 2, no ticket file written and an existing one left untouched.

## 9. Links (AC-4, AC-6)

- **Permalinks** come from `report.json`: `location.url` and each evidence item's `url`, taken verbatim from the tool's own field. Each is accepted only if it is a string beginning `https://` or `http://` with no whitespace or `<>()[]"'\` character; any other value is treated as no link. A hand-edited `report.json` therefore cannot plant `javascript:` or break out of a Markdown link. Nothing is built from a model string.
- **Links unavailable.** The header says `Links — Not built. The report records: …` and gives the reason the report recorded, the `references are not linked: …` entry from `run_warnings`; with none recorded and `links` `null`, the reason is `disabled in the repository's link settings (enabled = false)`, the one silent case. Refs then appear as code spans. Unrecognised host, invalid `[links]` and unreadable `.thunderstruck.toml` all arrive through the recorded entry.
- **Links by nature absent.** A catalog reference reads `… (not linked: catalog data has no source location)`, a dependency reference in `check.evidence` `… (not linked: a dependency's source is not in this repository)`, a commit the repository cannot resolve `… (not linked: commit not found)`. Any other `null` is `(not linked: no link could be built)`.
- **The guidance (C).** Fix options and acceptance criteria each end with *How to fix: [fix-agent-instructions.md](URL) · how to review: [review-briefs.md](URL)*. The ticket is filed in the scanned repository, which has neither document, so a relative path would be a dead link there. `URL` is `<repository>/blob/main/docs/<name>.md`, `repository` read from the plugin's `.claude-plugin/plugin.json` through `_common.plugin_root()` and accepted only if `links.valid_base_url` does. The two paths are the constant `GUIDANCE` in the script, equal to C's `PUBLISHED`, and a test asserts both the equality and that the files exist. The link names current `main`: versioning the documents is out of scope (the ticket's Out). **Offline** the file is generated without a network, since nothing is fetched. **From a fork** whose `plugin.json` names its own `repository` the links point there; one that does not keeps pointing at the upstream. **If `plugin.json` is unreadable or has no valid `repository`** the line reads `fix-agent-instructions.md and review-briefs.md in the thunderstruck repository (no link could be built)`; generation never fails for it.

## 10. Status (AC-5)

`--status` takes `Hypothesis` (default), `Reproduced`, `Fix proposed`, `Fix reviewed`, case-insensitive, `-` or `_` for a space. `Reproduced` is the one claim the plugin can check, so it is the one it checks (Decision 6): `finding_ticket.recorded_reproduction(finding)` returns the finding's recorded failing reproduction, and returns `None` today, because nothing records one (`/thunderstruck-verify` leaves no data; #103 will). A request for `Reproduced` while it returns `None` is refused once the report is read and the key found, and before anything looks at the cited files. The one git call that has run is `git rev-parse --show-toplevel`, to find the repository (`_common.find_repo_root`). A test makes the code check fail if reached and edits a cited file:

> status Reproduced refused for finding `<key>`: no failing reproduction is recorded for it. A reproduction is a failing test that a verification run left behind and recorded; thunderstruck does not record one yet (issue #103 in the thunderstruck repository). Ask for Hypothesis, or record a reproduction first. No ticket was written.

The header prints the status; Reproduce ends `No reproduction is recorded for this finding.` while the function returns `None`. The test pins both the `None` and the refusal. The extension point is §16.

## 11. Safety (AC-8, AC-9)

**Inert text.** Every value a model or the repository wrote goes through `mdtext.text` or `mdtext.code`, or into the fence of §7; only the tool builds links (`mdtext.linked`). A's renderers and `render_check` already do this. All model text follows a label or a bullet, never the start of a line, so a leading `/close` or `#` cannot act as a quick action or a heading.

**Tracker references.** `mdtext` today escapes Markdown but not what a tracker adds after rendering: `#12`, `acme/api#12` and `PR#7` (an issue link and a notification), GitLab's `!12` and `group/proj!3`, a Jira key such as `ABC-123`, a short sha. `@name` is already a code span (`mdtext._LINKISH` has `@`). The plan adds three alternatives to `_LINKISH`: `[#!][0-9]`, with no look-behind, so a reference that names another repository is caught too; a key of capitals only, `(?-i:\b[A-Z][A-Z0-9]+-[0-9])`, so `utf-8`, `sha-256` and `x86-64` stay words; and a run of 7 to 40 hex digits that holds both a digit and a letter, so `defaced` stays a word. Such a token becomes a code span, which trackers do not link. **Not covered:** a short commit id made of digits only, because it cannot be told from a number (the ticket's AC-9 says so), and one of letters only. This changes `report.md` too, and only for text containing those tokens. Proved against `main` at 74805f7, #102's tests and regenerated samples included: one existing test pinned the old form (§14) and neither sample report moved. Tracker syntax beyond these (`~label`, `%milestone`, a quick action GitLab runs at the start of a line, which no model text can reach because it always follows a label or a bullet) is not covered, and the GitLab rule was not tested.

**Machine values (AC-8).** Nothing about the machine that ran the scan reaches a ticket: its repository path, home directory, user name or host name. `repo.branch` (a branch can carry a user name) and `generated_at` are never read; `repo.root` is read only to be removed. Every string a model or the repository wrote that the ticket shows, a finding field or a drafted item, passes `scrubber` first, which replaces the repository path (`report.repo.root` and the resolved `--repo`) with `<repo>`, `Path.home()` with `<home>`, the login name with `<user>` and the host name (full and short) with `<host>`, the last two as whole words only. `machine_values()` reads them, so a test can supply a machine. Three limits keep the scrub from corrupting what must stay exact. References, links, ids and hashes (`SCRUB_SKIP`: `ref`, `file`, `url` and the like) are never scrubbed, so a file under `src/alice/` still resolves. A snippet is the repository's own text at the commit and is shown as it is, even when it holds a path like the scanner's home: that is content, not a value from the scan. And a generic account name (`GENERIC_ACCOUNTS`: `root`, `admin`, `runner`, …) is the same on every machine and says nothing about this one, so `root` is not replaced (it would turn "root cause" into "<user> cause"), though `/root` as a home directory is. A name shorter than three characters, and a host name shorter than four, are not replaced for the same reason. Permalinks and the remote's web address are the repository's own public address, which AC-4 requires; credentials are never part of the base (`links.py:66-100`).

**What the tracker renders.** The file is CommonMark with GitHub-style fenced code. GitHub, GitLab and Bitbucket render it fully (inferred; this repository tests cmark-gfm and markdown-it-py only); a tracker that does not render Markdown shows the same text with its marks, still readable. The ticket contains no HTML, image, table, task list, footnote or emoji shortcode, so there is no feature a stricter renderer could drop. A snippet is a fenced block, so a tracker's autolinking and quick actions are not applied inside it (the GFM spec; GitLab's own rule for quick actions was not tested).

**Writes.** Only `.thunderstruck/tickets/`: a symlinked `.thunderstruck` or `tickets` directory is refused, and the key is validated before it becomes a path. The ticket is written to a temporary file with a name made fresh for each run (`.<key>.<random>.tmp`), opened with `O_CREAT|O_EXCL|O_NOFOLLOW`, so a link planted at that name, or at the one an earlier version used, is never written through (the open fails and the run stops, naming it); then `os.replace` moves it over `<key>.md`, replacing a link there and never following it. The temporary file is removed whether or not the run succeeds. `report.json` is untrusted input: every string is escaped and every URL checked.

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
| A ticket longer than `MAX_TICKET_CHARS` | steps dropped from the end and said so (§7); with no step left, a **hard stop** |
| `report.json`, its schema, the key, a stale, unreadable or LFS-stored file, an unknown commit | **hard stop**, named, exit 2, nothing written |

## 13. The sample (AC-11)

`examples/sample-ticket.md` is the ticket for the sample's first finding, FR-001 (`client/releases.ts`: two retry layers, a guarantee, a traced and a catalog item, an upheld check; #102's fixture adds findings after it, so it is still first), produced by the real pipeline. It extends `gen_sample_report.py` rather than adding a generator: one run already builds the validated, verified, linked fixture and `--check` (CI on Linux and macOS, `.github/workflows/ci.yml`) already compares every entry of `generate_all()` with `examples/`. The generator writes the pinned `report.json` back before the ticket is built, so the date and the sections file's `scanned_at` are the pinned day; writes a canned sections file for FR-001 (the one non-pipeline input, as the canned findings and verdicts are, labelled in the file's header comment); runs `finding_ticket.py` and adds the same kind of header comment. Byte-reproducible: the commit shas and the dates are the fixture's, and nothing machine-specific reaches a ticket.

## 14. Old data, invariants, tests

**Old data.** None is changed. `report.json` stays `thunderstruck.report/v2`, findings `thunderstruck.finding/v3`, `VALIDATION_RULES` 5, `index.json` v1; nothing is cached or keyed on a ticket, so no scan, bundle or finding invalidates. A report from before A has no `blast_items`: its ticket reads A's "not assessed". A report older than `scanned_at` or `links` stops or degrades as §12 says. The two existing samples change only if the `_LINKISH` extension changes their bytes. Nothing but CI's `--check` would notice, since no suite test compares them, so the plan's Task 1 runs `gen_sample_report.py --check` itself and, if it reports a sample stale, regenerates and commits it in that task. It did not at `main` 74805f7. #102 regenerated both samples; Task 8 adds the third file and CI's two `--check` steps (Linux and macOS, `.github/workflows/ci.yml`) cover it unchanged.

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

**Existing tests that pin behaviour that changes.** One, found by running the full suite after the `mdtext` change: `tests/test_report_links.py::test_file_edited_after_the_scan_is_not_linked`, whose pattern expects the scanned commit's short sha bare in the run warning; it now sits in a code span, and Task 1 changes the pattern to allow the backticks. Nothing else failed. A second is edited: #102's `tests/test_no_execution.py::GIT_ONLY` lists the functions allowed to start a process, and `finding_ticket._git` runs `git`, so Task 3 adds `("finding_ticket.py", "_git")` after a test of this ticket's own fails for lack of it. `test_every_script_has_a_docstring` and `test_plugin_paths.py` apply to the new script and skill and must pass; C's neutrality rules read the tree and must still pass on the two documents.

**New tests**, in `tests/test_finding_ticket.py`, appended per task: the fence primitive and tracker references on hostile text (both engines); lookup and every refusal; the stop table of §8 on small real git repositories; snippet bytes against `git show` for LF, CRLF, no final newline, tabs and a lone `\r`, with the caps; the sections file rules; links on and off; the status refusal, and that it precedes the code check; the whole-ticket cap, at its edge and with the worst case of twelve full steps; a link planted at the temporary name; the machine scrub; an LFS pointer; every section in order with its reason; determinism; hostile text in every model field, in the snippet, in the sections file, in `report.json` URLs and in the key, through the engines of #28 with `pre` allowed and no tag, link or heading added; no machine value; the sample and its freshness. A **mutation check** in the hostile task removes each defence in turn and the test must fail.

**What was proved while designing this, and what was not.** A fresh clone of `main` at 74805f7 (#102 and #109 included) with the branch's docs, #105's reconciled plan applied task by task (its Tasks 1 to 10) and #107's plan applied with two stand-in documents; then each of this plan's tasks replayed test-first. Every task's tests failed for the stated reason and then passed, except Task 7, which is test-only and carries mutation checks. The full suite exited 0 (2763 passed, 21 skipped; the baseline without this plan was 2539 and 21), with `gen_catalog_docs.py --check`, `gen_sample_report.py --check` (three files) and `validate_plugin.py`; the plugin installed into an empty home and listed the skill, the script and both documents in its installed copy. The CLI was also run against the sample fixture, including a stop on an edited file and the `Reproduced` refusal. **Not proved:** the real guidance documents; Python 3.11 and 3.12; macOS; how any tracker renders the ticket; GitLab's treatment of a quick action inside a fenced block.

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
11. **Tracker references are code-spanned in `mdtext`, for every output.** One primitive, one rule; the alternative (a ticket-only variant) would leave A's renderers unprotected. Cross-repository references are included; keys are capitals only and a sha needs a digit and a letter, to keep ordinary words out.
12. **The sample extends `gen_sample_report.py`.** §13.
13. **The guidance links name `main`.** C's decision; versioning is out of scope.
14. **The whole ticket is capped below a tracker's limit, and drops steps, not words.** Steps are the one section that is a copy of repository text and is long by nature; every reference stays listed. The limit and the margin are named constants to verify against the tracker.
15. **The machine is scrubbed from text, not from references or code.** What AC-8 names (path, home, user, host) is replaced in model text and drafts; references and snippets are exact by AC-3; generic account names are not machine values.
16. **A temporary file made exclusively, never through a link.** A fresh name, `O_EXCL|O_NOFOLLOW`, then an atomic replace.
17. **A way forward that fits the cause.** A file the scan saw in another state is a rescan, not a checkout.
18. **An LFS pointer is a stop.** A snippet of a pointer is not code.

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
4. **The tracker limit.** 65,536 characters is GitHub's issue-body limit as the review reported it; it was not checked against GitHub or any other tracker here. The constant carries a comment saying to verify it. A tracker with a lower limit needs a lower `TICKET_MARGIN`.
