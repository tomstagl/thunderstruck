# Fix impact in findings: design

**Requirements:** [#105](https://github.com/tomstagl/thunderstruck/issues/105), part of [#104](https://github.com/tomstagl/thunderstruck/issues/104). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-12-fix-impact-in-findings.md`.
**Builds on:** [`2026-10-03-checked-confidence-design.md`](2026-10-03-checked-confidence-design.md) (`#56 §n`) and [`2026-10-03-finding-verification-design.md`](2026-10-03-finding-verification-design.md) (`#37 §n`); bare `§n` is this document. §5 amends `#37 §6.1`, `§6.2`, `§8.1` and `§9`; those documents are not edited, they record decisions at their date.
**Evidence:** the ticket's reproduction of the bundle offset; `docs/calibration/correctness/celery/scan/bundles/` (frozen, unnumbered); #99 (every investigator named something unread, in prose a skeptic never sees).

This ticket owns the finding fields that the ticket generator (#108) renders. §16 gives their exact names and shapes.

## 1. Architecture

```
bundle.py        numbers every source line with the file's own number, names what it leaves out    (§7)
investigator     writes  implicit_guarantees? · no_guarantees_reason? · blast_items · not_checked   (§2)
validate.py      checks  shapes, the gate on the catalog's fix_touches, positions into evidence    (§3)
verify.py        prepare: the brief carries the claims, never confidence_rationale                 (§5.1)
skeptic          ← MODEL →  guarantees · no_guarantees_reason · not_checked                        (§5.2)
verify.py        apply: resolves them through the evidence resolver, writes check.guarantees,
                 check.not_checked; never touches check.status                                     (§5.3)
report.py        renders md · json (counts.not_checked) · index                                    (§6)
report_html.py   renders report.json as delivered
guardrail.py     reads index.json: states guarantees and open items as the investigator's          (§6.4)
```

The governing rule holds: the model states claims and points at code; whether a position is in range, what type it points at, which patterns need a statement, what a verdict resolves and what is still open are all computed.

## 2. The finding contract (investigator-written)

| Field | Required | Shape |
|---|---|---|
| `blast_radius` | yes | unchanged: one string, the summary |
| `blast_items` | yes, 1 to 8 | `{claim, basis, evidence?}` (§2.3) |
| `not_checked` | yes, may be `[]`, at most 5 | `{item, how_to_check}` (§2.4) |
| `implicit_guarantees` | only under the gate (§2.2) | at most 5 `{guarantee, removed_by, evidence}` |
| `no_guarantees_reason` | only under the gate | non-empty string, never beside guarantees |

`REQUIRED_FIELDS` goes from ten keys to twelve. Every `evidence` in these fields is a list of **positions** in the finding's own `evidence` list, counted from 0. The impact fields hold no ref of their own, so each cited line is resolved once, by the existing evidence rules (`#56 §3`); an item is only a pointer, with a type rule (Decision 1).

### 2.1 Free text

`guarantee`, `claim`, `item`, `how_to_check` and `no_guarantees_reason` are non-empty strings, inert in every output. No key other than those listed is accepted in an item: an unknown key is a validation error naming it, so a model cannot write a key a later stage owns (`#56 §2.2`'s rule).

### 2.2 `implicit_guarantees` and the gate (AC-1, AC-2)

An item says what the current code provides by accident (`guarantee`), the kind of change that would remove it (`removed_by`, one phrase that completes "removed by", e.g. "releasing the lock before the fetch"), and the code that provides it (`evidence`, at least one position, each pointing at a `code` item).

`removed_by` is free text, not a vocabulary (Decision 3). No "fix class" exists in the catalog or the code (`classify_commit`'s kinds are commit kinds), the requirement comes from one case, and a taxonomy invented from one case misleads when an investigator picks the nearest member. A closed set can be added later as a tightening with a rules bump, once the evaluation under #104 shows which kinds occur.

**The gate.** The catalog marks the patterns whose findings must state guarantees. AC-2 scopes the rule to lock, retry and cache patterns, and this is the ticket's list:

| Pattern | `fix_touches` |
|---|---|
| `S02`, `S03`, `S04`, `S10` | `retry` |
| `S09` | `cache` |
| `S28` | `lock` |

`Validator` reads `catalog["_by_id"][id]["fix_touches"]` (one of `_common.FIX_TOUCHES`), so adding a pattern to the rule is one catalog line, the key (the catalog is the source of truth). Because it makes the rule stricter, it is a `VALIDATION_RULES` bump. A finding whose `missing_patterns` include one of them must have a non-empty `implicit_guarantees`, or a non-empty `no_guarantees_reason`. Giving both is an error. The reason is a sibling key, not a sentinel item: a consumer iterating `implicit_guarantees` never meets a "none" entry.

Outside the gate both keys are optional and an empty list needs nothing. `S05` (rate limiting) and `S12` (circuit breaker, retry token bucket) are not marked, and `S09` is: the list is scoped by the ticket, not derived from a property of the patterns (Decision 4; whether `S12` joins is an open product question). **Limit:** the gate keys off ids, so a lock, retry or cache finding filed under `OTHER` alone escapes it. The investigator prompt asks for guarantees "whatever its patterns"; nothing enforces it.

**State.** `_common.guarantee_state(finding)` is `stated` (non-empty list), `none_found` (a reason), `not_stated` (the finding has `blast_items`, so it was written under these rules, and says nothing, which only an ungated finding may) or `not_assessed` (no `blast_items`: written before). The split between the last two is what keeps "the investigator was not asked" from reading as "the investigator found none".

### 2.3 `blast_items` (AC-3)

`blast_radius` stays a required string and the skeptic's quotable summary (`REFUTABLE_FIELDS` is unchanged, Decision 2). `blast_items` says what is behind it:

| `basis` | `evidence` | Meaning |
|---|---|---|
| `traced` | 1 or more positions, every one a `code` item | the investigator followed code to reach it and cites the lines it followed, in order |
| `catalog` | 1 or more positions, every one a `catalog` item | rests on a catalog edge |
| `assumption` | absent (or empty) | rests on neither |

"Traced" and "inferred" (`catalog` plus `assumption`) are separated in every output. An item resting only on a catalog edge cannot be `traced`: a position that points at a `catalog` item (or at any non-`code` item) is rejected with a message that says the item has basis `catalog`. Dependency refs cannot appear at all: investigator evidence has no `dependency` type (`EVIDENCE_TYPES`, `validate.py:47`), and a skeptic's dependency refs live in `check.evidence`, which this field never points at. The list may not be empty: an investigator that traced nothing writes its `blast_radius` as one `assumption` item.

**What this proves.** Each cited line exists (it is a resolved `code` evidence item). Nothing proves the lines connect: whether the investigator followed a path is judgment, and the only check for it is a skeptic quoting the item as `blast_radius` (§5.2). So no user-facing text calls a traced item a path: `report.md`, the HTML, the README, both prompts and the validator's messages say it cites code the investigator says it followed, and that each cited line is checked to exist, not to connect to the next. Cited lines are listed with commas, never arrows, and the investigator prompt's example has a traced item citing two lines. `_quotes` matches a quote against the summary or against one item's `claim`, each separately, so words spanning two items do not pass.

### 2.4 `not_checked` (AC-4)

Each item is `item` (what was not read or tested that the failure or its impact depends on) and `how_to_check`. It is the structured form of the "not checked" prose that sat in `confidence_rationale` (investigator prompt, method step 8), which the skeptic's brief withholds. What the investigator could not read within its limit goes here too. `[]` is valid and rendered "none listed by the investigator", never "everything was checked". Absence in the findings file means written before, "not assessed".

**`preconditions[].documented == "not_checked"`** (`#56 §2.2`) is unrelated and unchanged: it states that the docs were not looked at for one setting. It is not an item of this list, and nothing converts one into the other.

## 3. Validator (rules version 5)

`VALIDATION_RULES` goes from 4 to 5. In `Validator.check_finding`:

- `REQUIRED_FIELDS` gains `blast_items` and `not_checked`; the "it may be [], but the key must be present" hint applies to `preconditions` and `not_checked` (`LIST_MAY_BE_EMPTY`).
- `check_impact(f, where, errors, evidence, types)` checks §2: item shapes through one helper (`_items`: a list, at most the cap, objects with exactly the keys, non-empty strings), positions through another (`_evidence_indexes`: a non-empty list of integers, not booleans, in range, of an allowed type), the gate, and "not both".
- It runs once after the evidence types are known, and once with `None` when the evidence list is itself invalid, so a broken `evidence` does not hide the other impact errors from the one repair round. Position checks are skipped in that case.
- A position pointing at an item that failed its own validation is not reported again.
- Messages name the field and index (`findings[0].blast_items[1].evidence[0] points at evidence[2], which is 'catalog' evidence; …`) and the fix.

`FINDING_SCHEMA_VERSION` becomes `thunderstruck.finding/v3`, recording which contract wrote the file (nothing branches on it, as in `#56 §3.5`). `OWNED_FINDING_KEYS` is unchanged: the new fields are model-written. An unknown key on a finding is still kept, not rejected (`shape()` pops only owned keys).

## 4. Old data and the cache (AC-7)

| What | Effect |
|---|---|
| A findings file validated under rules 4 | Lacks `blast_items` and `not_checked`, so `bundle.py`'s `_still_valid` fails it: re-investigated. It also fails `report.py`'s `validated_with` check (Incomplete, "re-run the scan") and is skipped by `verify.load_findings`. No cached finding passes under the old rules |
| Every bundle | Its source is numbered (§7), so its hash changes: every hotspot is re-investigated once, including clean ones and ones whose finding would still pass. The ticket decided the two costs land together |
| `report.json` written before | Loads without error and renders. `REPORT_SCHEMA_VERSION` stays `thunderstruck.report/v2`: `report_html.py` exact-matches it (`report_html.py:95`), so a bump would refuse every old report, which AC-7 forbids. The additions are optional fields, as `report-format.md` records for earlier ones. A finding without `blast_items` renders every new section as "not assessed" |
| `index.json` written before | Loads without error. The guardrail states neither new line (§6.4) and says nothing is "not assessed"; `index.json` stays `thunderstruck.index/v1` |
| `check` in an old ledger or findings file | Has no `guarantees` or `not_checked`; outputs treat an absent key as "no check has looked" (open). A reused verdict needs equal `claim_hash`, which now covers the new fields, so an old verdict never applies to a re-investigated finding |
| A benchmark scan written before (the frozen Celery scan) | Loads without error, read unchanged: `verify.py prepare --frozen` builds briefs without the new blocks, `shown_lines` parses its unnumbered bundles by their notes, no label, verdict or run file is edited |
| The sample report | Regenerated once (§8) |

AC-7 splits three ways, and the tests follow it: a `report.json` loads and its new sections read "not assessed"; an `index.json` and a benchmark scan load without error and nothing more is claimed; a findings file validated under the old rules is investigated again and none keeps passing under them.

## 5. The skeptic

This only acts on `--verify` scans (`VERIFY_BY_DEFAULT = False`, `_common.py:588`). Without verification every finding is `unchecked` and the new fields are shown as the investigator's claims (AC-6).

### 5.1 The brief (AC-4)

`render_brief` is an allowlist (`verify.py:160`). After `preconditions` it adds, only when present and non-empty, fenced blocks under headings that say whose words they are: `blast_items` (as written), `implicit_guarantees` and `not_checked` (each item with an `index`, the position a verdict answers by), and `no_guarantees_reason`. They are claims, so they belong with the claim; none reads `confidence`, `confidence_rationale`, `notes`, `history` or `check`, which stay withheld (`test_the_brief_holds_the_claim_and_evidence_only`). The positions in `blast_items` and `implicit_guarantees` refer to the brief's own `evidence[i]` blocks. The blocks are `json.dumps` of the finding's own lists, so the brief stays byte-identical for an unchanged finding. A finding without the fields (the frozen scan) gets no block.

### 5.2 The verdict contract, amended (`#37 §8.1`)

`VERDICT_KEYS` gains `guarantees`, `no_guarantees_reason` and `not_checked`, after `duplicate_of`: eleven keys. They are optional exactly as `holds` is: omitted, `null` or empty are accepted, and an unknown top-level key is still a contract error that leaves the finding `unchecked` (the exact-keys rule is deliberate and untouched).

```json
"guarantees": [
  {"of": 0, "evidence": [1]},
  {"of": null, "guarantee": "…", "removed_by": "…", "evidence": [1]}],
"no_guarantees_reason": null,
"not_checked": [
  {"item": 0, "state": "resolved", "note": "…", "evidence": [0]},
  {"item": 1, "state": "unresolved", "note": "…"}]
```

- `guarantees` item: `of` is the `index` of the finding's own guarantee the skeptic confirms, or `null` for one it adds (then `guarantee` and `removed_by` are required); `evidence` points into the verdict's own `evidence` list and needs at least one resolved `code` or `dependency` item. A confirmed item takes its text from the finding: the skeptic never rewords the investigator's.
- `no_guarantees_reason`: a non-empty string when the skeptic found none and named none; otherwise `null`.
- `not_checked` item: `item` is the `index`; `state` is `resolved` (needs resolved evidence of type `code`, `commit` or `dependency`) or `unresolved`; `note` is non-empty (what the reading showed, or why it could not resolve the item).

`_contract_problem` is unchanged except that `VERDICT_KEYS` is longer: a wrong type for a new key is not a contract error (below). The prompt (`agents/thunderstruck-skeptic.md`) gains a "Guarantees and what was not checked" section, rule 6 for the two item shapes (the old rule 6, never invent evidence, becomes 7), the three keys in rule 1 and in the example (`test_the_example_output_follows_the_contract` pins the example's key set to `VERDICT_KEYS`), and a note that for `blast_radius` the quoted words may be the summary's or one item's, and that a traced item's cited lines are only checked to exist, so whether they connect is the skeptic's to test.

### 5.3 Settling (`#37 §9`)

`_decide` resolves the verdict's evidence as today (`Resolver.evidence`, `verify.py:407-413`), then two new functions read the resolved positions, so a guarantee or an answer can only cite what resolved:

- `settle_guarantees` returns `check.guarantees = {state, reason, items}`: `named` when at least one item survives, `none_found` when a reason is given and none survive, else `not_addressed` with a fixed reason. Dropped items and a reason given beside items are named under "Ignored".
- `settle_not_checked` returns `check.not_checked`: **exactly one entry per item of the finding, in order**. An item the skeptic did not answer, or answered badly (unknown index, repeated, no note, `resolved` without resolving evidence), is `unresolved` with `_common.NOT_ADDRESSED` and the cause under "Ignored". So no item disappears (AC-5), and an unresolved item stays open on the reported finding.
- Evidence positions are renumbered with `refuted_claims`' (`verify.py:475`), so they index `check.evidence`.

A wrong type for `guarantees` or `not_checked` (say a string) is ignored with a note, and every item is then unresolved. It never costs the verdict (Decision 8): the two are secondary duties, and losing a refutation to a malformed secondary field would make verification worse than before this change.

**Neither changes a status.** `settle`'s table (`#37 §9`) is untouched and runs on the same inputs; the new results are written beside the status. A skeptic cannot raise confidence by resolving everything: `effective_confidence` reads `check.status` only. The ledger and reuse copy `check` whole (`verify.py:383, 522`), so resolutions are remembered with the verdict, and any change to a guarantee, blast item or not-checked item changes `claim_hash` (`verify.py:76` hashes every non-owned key) and forces a new check.

### 5.4 The read cap and resolving N items (AC-5)

The skeptic's 10-file cap (`skeptic.md:22`) and the haiku default stay: raising the cap raises the cost of `--verify`, whose ceiling was measured (`VERIFY_MEASURED_COST`) and is not re-measured here. Instead the work is bounded and the shortfall is a state. The finding carries at most 5 guarantees and 5 not-checked items. The prompt says refuting the claim comes first, that the reads are shared, and that items not reached are marked `unresolved` with the reason (for example "read limit"), which alone never makes a verdict `inconclusive`. At the haiku default resolution will often be partial; that share is the #104 success measure, and `counts.not_checked` reports it. Whether to raise the cap is the evaluation's question (Open design questions).

## 6. Outputs

All model-written values are inert: `md.text` (`md.code` for refs) in `report.md`, `textContent` in the HTML, one flattened line in the guardrail. Only the tool builds links. A position is turned into a link by looking up the finding's `evidence[i].url` (or `check.evidence[i].url`), which `_set_urls` already sets, so `report.json` gains no `url` field here.

### 6.1 `report.md`

After **Check** and before **Preconditions**, three blocks (the table of the finding is unchanged, so no row is added):

```
**Traced impact** — each item cites the code the investigator says it followed to reach it; each cited line is checked to exist, not to connect to the next.

- <claim> — cites: <link>, <link>

**Inferred impact** — each item rests on a catalog edge or an assumption, not on cited code.

- <claim> — rests on the catalog: `dependencyOf component:default/web-frontend`
- <claim> — an assumption

**Implicit guarantees** — what this code provides without saying so, as the investigator stated it. No check has confirmed this.

- <guarantee> — provided by <link>, <link> — removed by: <removed_by> [— confirmed by the check: <links> | — not confirmed by the check]

Added by the check:

- <guarantee> — removed by: <removed_by> — evidence: <links>

**Not checked** — what the investigator did not read or test, and how to check it.

- <item> — how to check: <how_to_check> — open: no check has looked at it
- <item> — how to check: <how_to_check> — resolved by a check: <note> — evidence: <links>
- <item> — how to check: <how_to_check> — still open after a check: <note>
```

Empty or absent: `**Traced impact** — none: no item cites code it followed.`, `**Inferred impact** — none.`, `**Implicit guarantees** — none found, per the investigator: <reason>` or `none stated by the investigator, who was not required to for these patterns.`, `**Not checked** — none listed by the investigator.`, and for a finding without `blast_items`: `**Traced and inferred impact** — not assessed: this finding was written before it was recorded.` (and the same words for the other two). The sentences are `_common.IMPACT_SENTENCES`, shared with the HTML. "No check has confirmed this." is shown unless `check.guarantees.state` is `named`, and "confirmed by the check" only beside an item the check confirmed (AC-6). What a check said is shown even when the investigator listed none: "The check found none: <reason>", the not-addressed reason, or "Added by the check".

### 6.2 `report.json`

Findings carry the investigator's fields as written, and `check.guarantees` and `check.not_checked` as §5.3 writes them. `counts.not_checked` is `{listed, resolved, unresolved, open}` over the reported findings (`open` counts items with no check entry); `listed == resolved + unresolved + open`. Nothing else is added and the schema stays `thunderstruck.report/v2`.

### 6.3 `index.json`

Stays `thunderstruck.index/v1`, additive. A finding's entry gains `implicit_guarantees` (`[{guarantee, removed_by}]`) when it has any, and `not_checked` (the `item` texts not resolved) when any remain.

### 6.4 HTML report and guardrail

`templates/report.html` gains `impactRows(f)`, called after the check rows: rows "Traced impact", "Inferred impact", "Implicit guarantees" and "Not checked" (or "Traced and inferred impact" for an old finding), with the §6.1 wording from an `IMPACT_SENTENCES` object a test compares with `_common`. Positions are resolved with `evLinks`; everything stays `textContent`.

The guardrail decides to state them (Decision 12): it runs exactly when someone is about to edit the code that provides a guarantee, which is the case the ticket exists for. `guardrail.py` (stdlib only, exits 0, facts) adds, per finding and only when `index.json` carries them:

```
  The investigator found this code also provides, without saying so: <guarantee> (removed by: <removed_by>); … and N more.
  Not checked and still open: <item>; <item> and N more.
```

At most 3 each, each flattened to one line and clipped (200 and 160 characters). An index from before states neither line.

## 7. Bundle numbering (AC-8, AC-9)

`section_source` (`bundle.py:207`) emitted raw text, so counting from the top of an excerpt (which starts at the function's line minus 15) is off by the excerpt's start line. It now numbers.

- **Format.** `f"{n:>{w}} | {text}"` for line `n` (1-based), `w` the digit count of the file's last line number, constant for the file. Blank lines keep the trailing space. A source line cannot end the fence: its prefix keeps "```" from starting a line.
- **Lines.** `source_lines(path)` reads bytes, decodes UTF-8 with replacement, splits at `\n` only, drops the empty string after a final newline, drops one trailing `\r` per line (CRLF), and shows any other `\r` as `␍` (U+240D). That is how `validate.py`'s `_count_lines` and `git blame` count; `c.read_text` (universal newlines) and `splitlines()` (form feed, lone `\r`) are not, and are no longer used for this block. The shown text therefore differs from the file's in three ways only: the CRLF's `\r` is dropped, a lone `\r` is `␍`, invalid UTF-8 is replaced. A lone `\r` is not a line break to git, so raw it would put `b = 2` after `a = 1` on a row with no number (`1 | a = 1\rb = 2`); `␍` keeps one numbered row per file line. A form feed is shown as is: it breaks no row.
- **Notes.** The three forms are unchanged in wording (`whole file, N lines`; `lines A-B — the most complex function … the file is N lines and did not fit the budget`; `file trimmed to fit the budget; N lines total`), with `A = max(1, start − 15)`, `B = min(N, end + 15)` and `N` the real count: the old note counted the empty string after a final newline (562 for a 561-line file).
- **Budget.** The numbers count. Whole file only if the numbered text is within the budget, else the excerpt or the head and tail of the file, clipped by `_clip_lines`: whole lines, 70% of the budget from the start and 25% from the end, and one marker line `... [trimmed: lines X-Y omitted] ...` naming the numbers left out. A line that does not fit is omitted and named, not cut. The block stays within `budget × 4` characters plus the marker. A file that fitted before may now be an excerpt.
- **Determinism.** Nothing volatile enters the block; `test_bundles_are_within_budget_and_deterministic` is unchanged and passes.
- **Hash.** Every `bundle_hash` changes once (§4).
- **The reader.** `benchmark.shown_lines` first tries `_numbered_ranges`: when every body row is numbered or the marker, the ranges are the runs of consecutive numbers, exact (the legacy reconstruction under-counted by up to two lines). Otherwise it uses the old notes and the `characters omitted` marker, so the frozen Celery bundles parse as before and `test_today_bundles_baseline` is untouched.
- **What stays wrong.** Other sections' line numbers (detector leads, boundaries) still come from `c.read_text`, so they differ from git's in a file containing a lone `\r` (Open design questions).

## 8. Fixture and sample

`tests/fixtures/build_fixture.py` needs no change. `gen_sample_report.py`'s canned findings gain what rules 5 require, with evidence positions written by name (`"code"`, `"also:N"`, `"catalog:N"`) and resolved when the finding is built: FR-001 (releases.ts, `S02`/`S10`) states a guarantee and a traced and a catalog item; the `S03` api.ts finding uses `no_guarantees_reason`; the others show the not-stated form. The canned verdicts show every skeptic state: FR-001 confirms its guarantee and resolves one item and leaves one open; api.ts says it found none; the rest are not addressed. Both samples are regenerated in one task.

## 9. Test strategy

New tests in `tests/test_fix_impact.py`, appended per task. Existing tests that pin behaviour that changes, and how:

| Test | Change |
|---|---|
| `test_checked_confidence.py::test_validation_writes_check_and_history` | `== 4` becomes `== 5` |
| `test_checked_confidence.py::test_the_capture_hook_strips_what_a_model_must_not_set` | `finding/v2` becomes `finding/v3` |
| `test_benchmark.py::test_bundle_parser_matches_what_bundle_py_renders` | its body regex gets the number prefix, and the parser must now be exact |
| builders: `test_pipeline._valid_finding`, `test_validate_paths._doc`, `test_context_pipeline._catalog_finding`, `test_dormant` (D01 finding), `test_checked_confidence._second_hotspot_finding` | gain the new required keys, and the gate's statement where they use `S02` |

Unchanged and still passing: `test_the_prompt_example_is_a_complete_valid_shape` (reads `REQUIRED_FIELDS`), the skeptic contract tests (they read `VERDICT_KEYS`), `test_refutable_fields_are_finding_fields`, `test_the_brief_holds_the_claim_and_evidence_only`, `test_prepare_is_deterministic`, `test_bundles_are_within_budget_and_deterministic`, every benchmark baseline test, `test_labels_never_reach_the_pipeline`.

- **Validator.** Every §2 rule with its message; the gate over each marked pattern and over `S05`, `S01`, `S12`, `OTHER`; a quote spanning two blast items; "not both"; a traced item pointing at a catalog item; the broken-evidence case.
- **Settling.** `settle_guarantees` and `settle_not_checked` as pure functions over every malformed form; end to end through `verify.py save`/`apply`: named guarantees, items resolved and open, a verdict saying nothing, malformed keys, an unknown key (still a contract error), the ledger and reuse, a quoted blast item; resolving everything never changes status or reported confidence.
- **Outputs.** An unverified finding shows claims as the investigator's; a verified one shows confirmed, added, resolved and open; every listed item appears once in `report.md`; `counts.not_checked` adds up; links come from evidence; old, empty and not-stated findings read as §6.1 says; the HTML in a real browser (rows, an old report, hostile text).
- **Inert text.** Dedicated tests, because the lists in `test_inert_report.py:24` and `test_report_html.py:235` set top-level strings and `no_guarantees_reason` cannot sit beside guarantees: hostile text in every new field (including `no_guarantees_reason`, `removed_by`, `how_to_check`, the check's `reason` and a guarantee the check added), in `report.md` (no added heading or table row), in the HTML data block and in the browser (each in both forms of the guarantees statement), and in the guardrail line (newlines flattened).
- **Numbering.** The number before each line equals the file's line for LF, no-final-newline, CRLF, lone `\r` and form-feed files, a lone `\r` is shown as `␍` and no row is unnumbered, for whole, excerpt, trimmed and clipped blocks; the marker's range plus the shown lines equals the note's range; the reproduction (function at line 76); the note counts equal `_count_lines`; the numbers count against the budget; an over-long line is named as omitted; determinism; every fixture bundle numbered; `shown_lines` exact on numbered blocks and unchanged on a legacy one.
- **Prompts and sample.** The investigator example validates; the prompt states the rules; the catalog brief marks exactly the six patterns; the sample shows every state.

## 10. `CLAUDE.md` invariants

| Invariant | How it holds |
|---|---|
| Bundles byte-identical | Numbering is a pure function of the file and the budget; determinism test unchanged |
| Detector hits are leads | Untouched |
| Every evidence ref resolved mechanically | The new fields add no ref; positions are checked for range and type; skeptic evidence goes through `Resolver.evidence`. The limit that steps connect is judgment (§2.3) |
| `id` vs `key` | Nothing matches on `id`; `claim_hash` covers the new fields |
| Confidence capped by check status | `effective_confidence` untouched; resolutions never change `check.status` |
| Verdicts resolved like findings | Guarantees and answers resolve through the same evidence list, and an unresolved answer is stated, not trusted |
| `run.json` decides whether verification ran | Untouched; an unverified scan has no `check.guarantees` |
| Briefs deterministic, withhold the rationale | Held (§5.1) |
| The plugin must not exhibit the patterns it hunts | No new subagent, retry or loop; the cap of four and the 10 reads are unchanged |
| The benchmark measures, never feeds | `shown_lines` only reads; no label, verdict or run file is edited |
| Guardrail: stdlib, exit 0, under 100 ms, facts | Two helper functions over at most 3 short strings; phrasing test extended |
| Repository content is data | Every new string is inert (§6) |
| Generated files never hand-edited | The samples are regenerated once; `patterns.md` is unaffected (the generator does not print `fix_touches`) |

## 11. Security

New model-written strings are rendered inert everywhere (§6). Positions are integers checked against a list before any use, so a position cannot name a file or run anything. A skeptic's text that tries to steer ("resolved", "none found, approved") is data: `resolved` needs resolving evidence, a statement of none changes no status, and the OTHER-only guard is unaffected because nothing here settles a status. The brief fences the new blocks like the old claim blocks.

## 12. Degradation

| Condition | Behaviour |
|---|---|
| Verification did not run | Items shown as the investigator's; `not_checked` entries all open |
| A skeptic returned nothing usable | `check.status` is `unchecked` with no `guarantees` or `not_checked`; items open |
| A malformed `guarantees` or `not_checked` | Ignored with a note under the reason; every item unresolved; the verdict stands |
| A finding from before | "Not assessed" in every new section; counted nowhere in `counts.not_checked` |
| An evidence position out of range in a hand-edited file | Not linked; the item's text is still shown |
| A file whose lines cannot be read | An empty numbered block with `whole file, 0 lines`, as before |
| An investigator that cannot satisfy the new rules after the one repair round | Its hotspot is Incomplete, as for any rule, and the report says so; nothing is retried |

## 13. Consumption

No model call is added. An investigator writes more fields per finding (not measured); a bundle's source section carries 14% more characters for the numbers on the ten frozen Celery bundles (13 to 16% each; paid out of the same budget, so a file shows about 12% fewer lines); a skeptic's brief and verdict grow by the same fields. The measured figures in `docs/calibration/consumption.md` and `VERIFY_MEASURED_COST` predate this change and are not re-measured (the evaluation under #104 does). The one-off cost is the re-investigation of every hotspot on the first scan after upgrading (§4).

## 14. Decisions

1. **The impact fields point into `evidence` by position.** A second place for refs would need its own resolver, URLs, hashes, guardrail filing and shared-code detection; positions get all of them from the evidence list, and "every ref resolved mechanically" stays true by construction. Cost: a model must add the evidence item first. Messages name what a position points at.
2. **`blast_radius` stays a required string; `blast_items` is added.** Changing its type would break old reports, `claim_hash` continuity, the brief and the skeptic's quoting at once. The string is the summary; items carry the basis.
3. **`removed_by` is free text.** See §2.2.
4. **The gate keys off the catalog's `fix_touches`.** Six patterns, data not code: the ticket's scope of lock, retry and cache, not a property of the patterns. `S05` and `S12` are out and `S09` in because AC-2 says so. Adding one is one catalog line and a rules bump. `OTHER`-only escapes (a limit, stated).
5. **`no_guarantees_reason` is a sibling key.** A sentinel item would be iterated as a guarantee; an object-or-list value would vary in type.
6. **`blast_items` and `not_checked` are required, `implicit_guarantees` is not.** The rules bump re-checks everything anyway; leaving the first two optional would let a model skip them silently, which is the problem the ticket names.
7. **A check annotates, never edits.** The finding keeps the investigator's words; the check's statements live in `check` and never change a status.
8. **Malformed new verdict keys never cost the verdict.** Unknown keys stay contract errors; wrong types are ignored with a note.
9. **The cap of 10 reads stays; items are capped; unresolved is a state.** §5.4.
10. **Caps of 5, 8 and 5.** Unmeasured: chosen so a skeptic's per-finding work fits its reads. A change is a constant and, if lowered, a rules bump.
11. **No report-schema bump; finding schema v3.** §4.
12. **The guardrail states both lists.** §6.4.
13. **Numbers are the file's, counted as `validate.py` counts, and count against the budget.** §7.
14. **One regeneration.** The samples change once, in one task.

## 15. Extension points and open design questions

### Extension points

- **#108** reads §16 and renders it; it must not recompute states or counts.
- **#99** (callees in the bundle, confidence capped on "did not read") can read `not_checked_states` and `check.not_checked`; this ticket made "did not read" structured, which those need.
- **#103** (a recorded reproduction and fix simulation) adds its own keys to the finding or `check`; nothing here reserves them.
- **#106** (lessons) may select by `fix_touches`, which is data in the catalog.
- **A vocabulary for `removed_by`** is a later tightening: a rules bump, with the evaluation's counts as its evidence.
- **A check that quoted code occurs in the cited lines** (deferred) can use the same positions: each is a resolved `code` item with a line range.

### Open design questions

None blocks the plan: it builds each recommendation, and the answer changes a constant or opens a follow-up.

1. **Raise the skeptic's read cap for scans that resolve items?** Recommendation: no, until `counts.not_checked` from the #104 evaluation shows the resolved share.
2. **Line numbers outside the Source block.** Detector leads and boundaries come from `c.read_text`, so a file with a lone `\r` (classic Mac line ends) is numbered differently from git. Recommendation: a follow-up ticket; changing it changes `hotspots.json` hits and every hotspot hash. A form feed or CRLF is not affected.
3. **Product question: should `S12` (and `S05`) join the gate?** The ticket scoped the list, so the plan builds six patterns. One catalog line each and a rules bump if the maintainer says yes.
4. **Are two more required keys worth the repair rate?** Recommendation: keep them required, count Incomplete hotspots on the first scans, and make `not_checked` optional (a rules bump) if the repair round fails visibly more often than before.

## 16. Contract for #108

Everything below is what a finding, `report.json` and `report.md` carry after this change. The ticket generator renders it verbatim and must not recompute it.

**In a finding** (`.thunderstruck/findings/*.json`, and each item of `report.json` `findings[]` and `refuted[]`):

| Key | Type | Values |
|---|---|---|
| `blast_radius` | string | the summary, unchanged |
| `blast_items` | array of 1 to 8 | `{"claim": string, "basis": "traced" \| "catalog" \| "assumption", "evidence": [int, …]}`; `evidence` present and non-empty for `traced` (positions of the `code` items the investigator says it followed; checked to exist, not to connect) and `catalog` (positions of `catalog` items), absent for `assumption` |
| `not_checked` | array of 0 to 5 | `{"item": string, "how_to_check": string}` |
| `implicit_guarantees` | optional array of 1 to 5 | `{"guarantee": string, "removed_by": string, "evidence": [int, …]}`; `removed_by` completes "removed by"; `evidence` positions of `code` items |
| `no_guarantees_reason` | optional string | present only when `implicit_guarantees` is absent or empty |

Positions are 0-based indexes into the same finding's `evidence` array. In `report.json` each `evidence[i]` has `type`, `ref`, `note`, `url` (a link or `null`), and `role`/`subject` on commits.

**Key presence is the version.** No `blast_items`: written before; every new section is "not assessed". `blast_items` present and neither `implicit_guarantees` nor `no_guarantees_reason`: "none stated by the investigator, who was not required to for these patterns". Never render absence as "none found".

**In `check`** (`findings[].check`, only when verification ran for the scan):

```json
"guarantees": {"state": "named" | "none_found" | "not_addressed", "reason": string | null,
               "items": [{"of": int | null, "guarantee": string, "removed_by": string, "evidence": [int, …]}]},
"not_checked": [{"item": int, "state": "resolved" | "unresolved", "note": string, "evidence": [int, …]}]
```

`guarantees.items[].of` is the position in the finding's own `implicit_guarantees` that the check confirms, or `null` for a guarantee the check added; `evidence` here indexes `check.evidence`, not the finding's. `check.not_checked` has one entry per item of the finding's `not_checked`, in order, `item` its 0-based position; an absent list, or an absent entry, means open: "no check has looked at it". `state` `unresolved` means still open after a check. A guarantee is confirmed only by `check.guarantees` (`state` `named` and an item whose `of` equals its position); until then it is the investigator's claim.

**`report.json` top level:** `counts.not_checked` = `{"listed": int, "resolved": int, "unresolved": int, "open": int}`. Schemas stay `thunderstruck.report/v2` and `thunderstruck.index/v1`. **`index.json`**, per finding: optional `implicit_guarantees` = `[{"guarantee", "removed_by"}]` and `not_checked` = `[string]` (the `item` texts not resolved).

**In `report.md`** (after **Check**, before **Preconditions**), in this order: `**Traced impact**`, `**Inferred impact**`, `**Implicit guarantees**`, `**Not checked**`, with the lines and sentences of §6.1. The sentences are in `_common.IMPACT_SENTENCES` (`not_assessed`, `traced`, `traced_none`, `inferred`, `inferred_none`, `guarantees`, `guarantees_none`, `guarantees_not_stated`, `not_checked`, `not_checked_none`, `unverified`); the renderers are `report.render_impact`, `render_guarantees` and `render_not_checked`, which #108 may call rather than copy. Model-written text goes through `mdtext` (`text`, `code`, `linked`).

**Bundle source** (what a snippet is checked against): each shown line is `f"{n:>{w}} | {text}"`, `n` the file's 1-based line number, `w` the digit count of the file's last line number; a clipped block has one marker line `... [trimmed: lines X-Y omitted] ...`. `text` is the line with one trailing `\r` removed and any other `\r` shown as U+240D.
