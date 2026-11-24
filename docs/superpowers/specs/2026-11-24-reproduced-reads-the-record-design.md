# Reproduced reads the record: design

**Requirements:** [#143](https://github.com/tomstagl/thunderstruck/issues/143), part of [#104](https://github.com/tomstagl/thunderstruck/issues/104). The problem, stories, scope and acceptance criteria (AC-n) are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-24-reproduced-reads-the-record.md`.
**Builds on:** [`2026-11-22-record-reproductions-design.md`](2026-11-22-record-reproductions-design.md) (#103: the record, its states and its wording, §2.1–§2.3) and [`2026-11-12-finding-to-ticket-design.md`](2026-11-12-finding-to-ticket-design.md) (#108: §10 gates `Reproduced`, §16 names this change as its extension point).
**Evidence:** `scripts/finding_ticket.py` (`recorded_reproduction`, `require_status`, `render`, `main`), `scripts/report.py` (`render_reproduction`, and the loop that attaches `reproduction` to each finding), `scripts/reproduction.py` (`state`, `summaries`, `sentence_parts`) and `skills/thunderstruck-verify/SKILL.md` (Step 6) as read at `main` c376fdb. Every `file:line` drifts; the plan's Task 0 checks the anchors.

In this repository "ticket" also names a GitHub issue for developing thunderstruck. Here a **finding ticket** is the text `scripts/finding_ticket.py` writes for a scanned repository's tracker, as in the #108 spec.

## 1. What changes

One function and its callers. `recorded_reproduction(finding)` returned `None` because nothing recorded a reproduction. It now reads the `reproduction` object `report.py` attaches to a finding, and returns it only for a failing test whose record is current. `require_status` turns every other state into its own refusal. `render` shows the record in the header and the Reproduce section, whatever status is asked.

Nothing else moves: not the record, the report, the guardrail, the default status, `Fix proposed` and `Fix reviewed` (the requester's word, #108 §10 and §16, and #133 may change that), the ticket's section list, or any schema.

## 2. What this relies on

`finding["reproduction"]` is absent when the finding has no record. When present it is `{status, state, test_path, command, recorded_head, stale_because, sentence}` (`report.py` adds `sentence`; `reproduction.summaries` builds the rest):

- `status` is `fails_as_predicted`, `passes` or `blocked`, or `None` when the record is `unreadable`.
- `state` is `current`, `stale` or `unreadable`. `stale_because` lists what changed: `the test file is gone`, `the test file changed`, `the finding changed`.
- `report.render_reproduction(f)` returns `[]` with no record, otherwise the line `**Reproduction** — …`, a blank line and, unless the record is unreadable, `Recorded with the command `…` at commit `…`` (with `, test `…`` when the line does not already name the test: a passed or blocked record) and a blank line. Every value in it goes through `mdtext`. It indexes the object without checking it, so it needs the vocabulary above (§3.2 sees to that).

`reproduction.py record` writes only `.thunderstruck/reproductions/<key>.json`. It does not rebuild `report.json`; the verify skill's Step 6 says to rebuild afterwards. So between a recording and a rebuild a record exists that the report does not show. §3.3 handles that.

## 3. Decisions

### 3.1 The report's word is the source

The ticket reads `finding["reproduction"]`; it never opens a record file to learn a state. #103 decides `current` and `stale` once, in `reproduction.state`, and `report.py` stores the answer. A second derivation here would be a second rule that can disagree with the one the report prints.

**An accepted limit.** `current` is the report's verdict when it was built. A test edited after the report was built is not seen: record, rebuild, edit the test so it passes, ask for `Reproduced`, and the ticket is made. `check_snapshot` compares the cited code and the finding to the scanned commit, not the test file. That is the product decision "a ticket is made from the last report", and the cost of closing it is a second hash of a file the ticket does not otherwise read. If it ever matters, the report carries the test's hash and the ticket compares it; nothing here prevents that.

### 3.2 One state accepts; every other state refuses, fail closed

`recorded_reproduction` returns the object only when `status == "fails_as_predicted"` and `state == "current"`, and `None` for anything else: a different state, a different status, a value that is not an object, a key that is missing. A value this code does not know is therefore refused, not accepted. A report from a later version that adds a status cannot make a ticket claim `Reproduced`.

The renderer in §3.4 indexes the object, so an object it could not index must not reach it. `_normalised`, which already gives every finding a `check` the renderers can index, also reads a `reproduction` object that is not in #103's vocabulary as `{status: None, state: "unreadable"}`: an unknown `state` or `status`, a `status` that disagrees with `unreadable`, `stale_because` that is not a list of text or that is empty on a stale record (and non-empty on any other), a `test_path`, `command` or `recorded_head` that is neither text nor `null`. `report.py` cannot produce such an object, so only a hand-edited or foreign `report.json` reaches this, and it reads as unreadable in the header and in the refusal alike. A `reproduction` value that is not an object is not normalised: it is treated as none (§5).

`require_status(status, finding, on_disk=False)` does nothing for any status but `Reproduced`. For `Reproduced` it asks `reproduction_refusal(finding, on_disk)`, which returns the reason or `None`:

| Record | Refusal says |
|---|---|
| none, and no file | no reproduction is recorded for it; run `/thunderstruck-verify`, record the outcome of the test run, rebuild the report, ask again; or ask for Hypothesis |
| none in the report, a file on disk | a reproduction is recorded for it, but `report.json` does not show it yet; rebuild the report (`report.py`) and ask again |
| `unreadable` | the reproduction recorded for it is unreadable; record it again with `/thunderstruck-verify`, then rebuild |
| `passes` | the recorded reproduction passed: the hypothesis did not hold as tested, and a test that passes does not reproduce a failure; ask for Hypothesis, or write a test that fails for the reason the finding names and record it |
| `blocked` | the recorded reproduction was blocked: no test could be made to run; ask for Hypothesis, or get a test to fail and record it |
| `fails_as_predicted`, `stale` | the recorded failing test is stale: what changed, joined with `and`, at most three items; run it again, record the outcome, rebuild |
| anything else (reached only by a caller that skipped `_normalised`) | the recorded reproduction has an unrecognised result (the value, clipped); record it again, then rebuild |

Every message begins `status Reproduced refused for finding <key>: `, says what to do, and ends `No ticket was written.` The order of the table is the order of the checks: `unreadable` is tested before `status`, because an unreadable record has `status: None`. Values taken from the report go through `_one_line`, which drops controls and clips, because the message goes to a terminal.

A refusal writes nothing and leaves an earlier ticket for that key alone, as every stop does (#108 §8).

### 3.3 A record the report does not show

When the report has no `reproduction` object, `main` checks whether `.thunderstruck/reproductions/<key>.json` is a regular file and passes that as `on_disk`. It only does so when `--status Reproduced` was asked, so every other request does no extra file access. The check never reads the file: reading it to say more would be the second derivation §3.1 rules out. It is one `is_file()` on a path built from a key that has passed `KEY_SHAPE` (12 lowercase hex), so a key cannot name another path.

The only difference is the sentence. A person who has just recorded gets "rebuild the report", not "nothing is recorded". The ticket is still made from the last report (a product decision in the ticket); a record the report does not show is never used.

`record_on_disk` is not part of the pure function that makes a ticket. It chooses between two refusals and never changes a ticket that is written, because on a ticket that is written the report already shows the record.

### 3.4 The record is shown, whatever status is asked

`render` calls `report.render_reproduction(f)`, the renderer #103 wrote for the report, and does not copy it (the same rule as #108 §2 for #105's renderers).

- **Header.** One line after `Status`: `- **Reproduction** — …`, the renderer's first element: the result, and the test when the result names one (a failing test, current or stale). A finding with no record gets no line.
- **Reproduce.** After `Verify`, the renderer's whole block: the line, then the command and the commit it was recorded at, and the test when the line does not name it. An unreadable record has no command to show and shows its line only. A finding with no record keeps `No reproduction is recorded for this finding.`

A stale record reads `Stale: a failing test was recorded …`, a passed one `A recorded reproduction passed …`, a blocked one `A reproduction was attempted and blocked`, an unreadable one `A recorded reproduction is unreadable`, all as #103 words them. The ticket therefore never says `Reproduced` in the header's Reproduction line for anything but a current failing test; the status line is the requester's claim and is checked by §3.2.

### 3.5 The default status does not change

`--status` still defaults to `Hypothesis`. A current record does not promote it. `Reproduced` is a claim the requester makes and the plugin checks, as #108 decided (Decision 6); making it automatic would make a ticket's status depend on a file the requester may not have looked at.

## 4. Safety (AC-4)

The recorded `command` is a string a person typed. It is stored by #103 as text, never executed by any script, and here it reaches the ticket only through `report.render_reproduction`, which prints it with `mdtext.code`: a backtick, link, tag, `#12` or long hex word in it stays text. It also reaches the ticket through the finding, which `main` passes through the same scrubber as every other value before anything is rendered (`scrub(find_finding(...))`), so the home directory, login name and host name of the scanning machine are replaced there, and in a refusal message, which is built from the scrubbed finding.

No new write path, no subprocess and no network. `finding_ticket.py` gains one import, `reproduction`, for `records_dir`; it is stdlib and `_common` only, and no path of `tests/test_no_execution.py` changes.

## 5. Determinism and degradation (AC-5, AC-6)

The ticket stays a pure function of `report.json`, the blobs at the scanned commit, the drafts file and the flags. The new input is `finding["reproduction"]`, which is part of `report.json`, so two runs on the same report give the same bytes. `record_on_disk` can only turn a refusal into a different refusal and never changes a written ticket (§3.3).

- A report written before #103 has no `reproduction` key on any finding. `recorded_reproduction` returns `None`, the Reproduce section keeps its old sentence, and `Reproduced` is refused as "no reproduction is recorded".
- A `reproduction` value that is not an object (a string, a list, `null`) is treated as none.
- An object this version does not recognise reads as unreadable (§3.2), in the header and in the refusal; it never raises.
- `reproduction_refusal` still refuses any combination it is handed, normalised or not: its last branch says the result is unrecognised.
- No schema version moves: not the report's, the finding's, the record's or the ticket's, and `VALIDATION_RULES` stays. The change tightens nothing a validator checks.

## 6. Test strategy

New tests go in `tests/test_finding_ticket.py` under one `# --- #143` comment, test first, each task red before green.

- **The one rule (AC-1, AC-5).** Parametrized over every state of §2 and the values §3.2 refuses: only a current failing test counts. A finding with no `reproduction` key has none recorded.
- **Accept (AC-1).** A report with a current failing record, `--status Reproduced`: exit 0 and `Reproduced` in the header.
- **Each refusal (AC-2).** One parametrized test over §3.2's table: exit 2, nothing on stdout, the key, the reason and what to do in the message, `No ticket was written.`, and no `tickets/` directory. The "file on disk" row writes a record file and leaves the report without one.
- **A record this version does not know.** Seven hand-made objects (an unknown status or state, no status, reasons that are not text or are one string, a stale record with no reason, a command that is not text): each is refused as unreadable and, for the default status, shown as unreadable, and none raises. A direct call of `reproduction_refusal` on an unnormalised unknown result is still refused.
- **Unsafe names (§3.3).** `record_on_disk` is false for `../x`, the empty string and a key with no file.
- **Shown (AC-3).** Header and Reproduce show a current record, and show each other state with its own lead, for the default status and for `Fix proposed`; Reproduce also shows the test, the command and the commit for every state but unreadable; no record keeps the old sentence.
- **Inert and scrubbed (AC-4).** A command with a home directory, a user name, a host name, a backtick, a link, a tag and `#12`: none of the machine values is in the Reproduce section, and the rest is exactly `mdtext.code` of the scrubbed command.
- **Byte-identical (AC-6).** Two runs, same bytes.
- **The real chain.** With nothing hand-built, on #103's fixture (`tests/test_report_reproduction.py`): `reproduction.record`, then `report.py`, then the ticket accepts `Reproduced`. The same chain with the test file edited after recording is refused as stale; with the report not rebuilt it is refused with "does not show it yet" and "Rebuild the report". These three are what a hand-built `reproduction` dict cannot prove: that the object the report really attaches is the one the ticket reads.
- **Words (AC-7).** The README, `CLAUDE.md` and the ticket skill each say when `Reproduced` is accepted, pinned the way `tests/test_finding_ticket.py` already pins them.

Tests the change makes untrue are edited in the same commit, and the commit says so: `test_nothing_records_a_reproduction_yet` becomes the pair above; `test_reproduced_is_refused_and_writes_nothing` keeps its checks and changes its reason from "#103" to "no reproduction is recorded for it"; the two assertions that the skill and the README say `Reproduced` is refused become the new sentences. No test is skipped or weakened: each replaced assertion is replaced by one at least as strict.

The sample (`examples/sample-report.*`, `examples/sample-ticket.md`) is not regenerated. Its fixture has no record, and it shows the no-record sentence, which does not change. `gen_sample_report.py --check` is run to prove that.

## 7. Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Read `finding["reproduction"]`, never the record file, for a state | One rule for `current`; the ticket and the report cannot disagree (§3.1) |
| 2 | Accept only `fails_as_predicted` and `current`; refuse all else, including values it does not know | A claim the plugin checks must fail closed (§3.2) |
| 3 | A distinct refusal for a record the report has not shown yet | It is the one mistake the documented flow makes easy: `record` does not rebuild (§3.3) |
| 4 | Show the record for every status | The ticket is for the person who fixes it; the test and command help whatever the status (§3.4) |
| 5 | The default stays `Hypothesis` | Status is a claim the requester makes (§3.5) |
| 6 | Call `report.render_reproduction`, not a copy | One wording, one inert-text path (§3.4) |
| 6a | `_normalised` reads an object it does not recognise as unreadable | The renderer indexes the object; the header and the gate must agree and a hand-edited report must not crash the ticket (§3.2) |
| 7 | No sample change, no version bump | The fixture has no record; the project lists releases under `## Unreleased` (§6) |
| 8 | A test edited after the report was built is not seen | The ticket is made from the last report; closing it would need a second hash (§3.1) |

## 8. Extension points and open design questions

**Extension points.**

- **#133**, the opt-in fix simulation, may let `Fix proposed` or `Fix reviewed` depend on a recorded result. It adds a gate beside `reproduction_refusal`; the table in §3.2 is the pattern.
- **A second record per finding** (more than one test) would change `reproduction.summaries` first, then the one `reproduction` object here. Nothing in this design assumes one test beyond reading the object as it is.

**Open design questions.** None blocks the plan.

1. **Should the ticket refuse to say `Fix proposed` or `Fix reviewed` after a `passes` record?** Recommendation: no. The status is the requester's word (ticket, product decisions) and a fix may be proposed for a hypothesis a test did not confirm. Revisit with #133.
2. **Should `main` rebuild a stale report?** Recommendation: no. Every script reads what an earlier stage wrote and says when it is out of date; a ticket that runs `report.py` would hide that the scan is not the one on screen.
