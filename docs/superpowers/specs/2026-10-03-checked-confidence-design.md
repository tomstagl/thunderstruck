# Confidence that means the claim was checked: design

**Requirements:** [#56](https://github.com/tomstagl/thunderstruck/issues/56), part of [#54](https://github.com/tomstagl/thunderstruck/issues/54). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-10-03-checked-confidence.md`.
**Evidence:** `docs/calibration/correctness.md` (Spike 3) and `docs/calibration/correctness/celery/verdicts.json` (#53). Measured with #55 (`docs/superpowers/specs/2026-10-03-correctness-benchmark-design.md`).

This ticket owns the finding contract that #37 (verification) and #57 (confirmed defaults) build on. §7 names every extension point; nothing in either ticket should need a field this spec does not define or reserve.

## 1. Architecture

```
investigator     writes   confidence (its claim), preconditions[], evidence[].role,
                          amplifier? sustaining_effect?               (§2)
save_finding.py  strips   check, history, confidence_claimed and the existing
                          validator-owned fields from model output    (§3.4)
validate.py      checks   §2's rules; writes check (unchecked when absent),
                          history[], key, content_hash, …             (§3)
(#37, later)     writes   check.status and its own keys under check   (§7.1)
report.py        derives  confidence_claimed, confidence (capped), gate;
                          orders by gate; renders md · json · index   (§4–§6)
report_html.py   renders  report.json as delivered, in its order      (§6.4)
guardrail.py     reads    index.json; states check status, preconditions,
                          history; caps an older index's confidence   (§6.5)
```

One rule decides confidence, one decides the gate, and both live in `scripts/_common.py` (`effective_confidence`, `finding_gate`). `guardrail.py` cannot import `_common` (stdlib only, no shared modules), so it carries a copy of the ceiling table, and a test asserts the two agree on every combination (§10).

The governing rule holds: the model states a claim and its preconditions; whether a commit is a fix, whether it wrote a cited line, where a reference points, what the confidence ceiling is and where a finding sits in the list are all computed.

## 2. The finding contract (investigator-written)

### 2.1 Fields

| Field | Required | Change |
|---|---|---|
| `location`, `missing_patterns`, `failure_mode`, `trigger_condition`, `blast_radius`, `evidence`, `confidence`, `confidence_rationale`, `how_to_verify` | yes | unchanged, except `confidence` (§2.4) and commit evidence (§2.3) |
| `preconditions` | yes, may be `[]` | new (§2.2) |
| `amplifier`, `sustaining_effect` | no | were required (AC-6) |
| `prediction` | no | unchanged |

`amplifier` and `sustaining_effect`, when present, are non-empty strings. Absent and `null` mean the same: not stated. An empty or whitespace string is rejected with "leave it out when there is nothing to state", so a model cannot satisfy the field with filler. `report.md`, the HTML report and the guardrail render a missing value as *not stated* and never substitute a sentence. Today's `_none — this one stops when the trigger stops_` and the HTML's "None. This one stops when the trigger stops." are removed: they filled an absent field with a claim.

### 2.2 `preconditions`

Each item is one setting the failure depends on:

```json
{
  "setting": "API_RETRY_ON_429",
  "default": "false (unset)",
  "default_ref": "src/client/api.ts:1",
  "needs": "changed",
  "value": "true",
  "documented": "no",
  "doc_ref": null
}
```

| Key | Values | Rule |
|---|---|---|
| `setting` | non-empty string | The setting's name as the code or docs spell it. Unique within the finding, compared case-folded with whitespace removed |
| `default` | non-empty string | The default as the code registers it, written as text (`"None"`, `"10"`, `"false (unset)"`) |
| `default_ref` | `path:line` or `path:start-end` | Where the default is registered. Resolved exactly like a `code` ref (§3.1): a tracked file, the canonical path, the lines inside it |
| `needs` | `changed` · `default` | `changed`: the failure happens only when the setting is changed from its default. `default`: the failure happens on the default and the claim rests on the default being what `default` says |
| `value` | non-empty string | Required when `needs` is `changed`: the value or range the failure needs (`"true"`, `"any value above 0"`). Absent or `null` when `needs` is `default` |
| `documented` | `yes` · `no` · `not_checked` | Whether the repository's docs describe the behaviour the finding claims. `no` means the investigator looked and they do not |
| `doc_ref` | `path:line` / `path:start-end`, or `null` | Required when `documented` is `yes`, resolved like a `code` ref; `null` or absent otherwise |

No other key is accepted from the investigator: an unknown key is a validation error naming it. That keeps a model from writing a key a later stage owns (§7.2).

**What is a precondition.** A setting the code reads, with a default the repository registers. A condition of the deployment (a database user's privileges, a route a user wrote) is not one: it has no default to register and stays in `trigger_condition` (Decision 7). A setting whose default the repository does not register (a dependency's own default) cannot be cited until #37 adds dependency references (§7.1); until then the investigator states it in `trigger_condition`.

An empty list means the failure happens on default settings and relies on no stated default. A list whose items all have `needs: default` is a default-path finding too; its items are there so the reader, and #57, can see which defaults the claim rests on.

### 2.3 Commit evidence: `role`

Every `commit` evidence item gains a required `role`, the investigator's statement of what that commit did to the code the finding is about:

| `role` | Meaning | Checked |
|---|---|---|
| `introduced` | It wrote the cited code | Mechanically: it must have written at least one line of a cited `code` range, per `git blame` (AC-3) |
| `fixed` | An earlier attempt to fix this failure or one like it | No: intent is judgment |
| `mitigated` | It added a guard, option or retry that limits the failure without removing it | No |
| `changed` | Any other change to the cited code | No |

The evidence item becomes `{"type": "commit", "ref": "1a39f8c", "role": "mitigated", "note": "…"}`. `role` on any other evidence type is rejected. The three unchecked roles are shown as stated by the investigator, beside the mechanical class and blame result (§3.3), so a reader sees where they disagree: a commit stated as `fixed` whose subject classifies as `feature` is shown as both.

### 2.4 `confidence` is a claim

The investigator's `confidence` stays `low` · `medium` · `high` and keeps its key in the findings file. It now means: how strongly the evidence read supports the claim, if the claim survives a check. The reported confidence is derived from it (§4) and never written back into the findings file. The fix-commit rule is removed from the prompt and the validator (AC-1): history neither raises nor caps the claim.

## 3. Validator-written fields

### 3.1 Rules added to `validate.py`

`VALIDATION_RULES` goes from 3 to 4. In `Validator.check_finding`:

- `REQUIRED_FIELDS` drops `amplifier` and `sustaining_effect` and adds `preconditions`. The "it may be null" hint moves from `sustaining_effect` to `preconditions` ("it may be [], but the key must be present").
- `amplifier`, `sustaining_effect`: when present and not `null`, a non-empty string.
- `preconditions`: a list; each item checked against §2.2. `default_ref` and `doc_ref` go through a new `check_ref(ref, where, errors)` that applies the existing `CODE_REF` parse, `_resolve` and `range_fits`, with the same messages a `code` evidence ref gets. Errors are addressed `findings[i].preconditions[j].default_ref`.
- `commit` evidence: `role` required and one of §2.3's four; `role` on another type rejected.
- `role: introduced`: the commit must be one of the shas `_introduced` returns for some cited `code` range, matched as today (`full.startswith(short.lower())`). Otherwise: `findings[i].evidence[j] is cited as having introduced the cited code, but it wrote none of the cited lines (git blame). Use role "changed", or cite the commit that wrote them.` An uncommitted line is introduced by no commit, as today.
- `check`: absent is fine (§3.2). When present it must be an object whose `status` is one of the five (§4.1), and whose `by` and `reason` are strings or `null`. Other keys under `check` are accepted unread (§7.1).
- Removed: "`confidence` is `high` but there is no `commit` evidence", "`high` but no cited commit is a fix", and `_corroborates`. `extra_fix` stays: it feeds the commit class (§3.3).

Nothing else changes: the 0–3 cap, the `code`-evidence rule, every existing ref rule.

### 3.2 `check`

When a document passes, `validate.py` writes, per finding without one:

```json
"check": {"status": "unchecked", "by": null, "reason": null}
```

It never changes an existing `check`. `save_finding.py` strips `check` from model output, so a fresh investigation always starts `unchecked`, and only a stage that runs after validation (#37) can write another status. A finding is never `upheld` because a model said so about itself.

### 3.3 `history`

Written by `validate.py` per finding that passes, one entry per distinct cited commit in citation order:

```json
"history": [
  {"sha": "1a39f8c", "class": "fix", "role": "mitigated", "wrote_cited_line": true}
]
```

- `sha`: the cited ref's first token, as cited.
- `class`: `_common.classify_commit(subject, extra_fix)` over `Validator._subject(sha)`, one of `fix`, `resilience`, `refactor`, `feature`; `null` when the subject could not be read (rendered "class unavailable").
- `role`: copied from the evidence item.
- `wrote_cited_line`: whether the commit wrote at least one line of any cited `code` range, from the same `_introduced` blame cache the `introduced` rule uses. It is computed for every cited commit, not only `introduced` ones; this is the "wrote a cited line" of AC-3.

`history` is a signal of fragility, so every output labels it as one and none feeds it into confidence or order.

### 3.4 Owned fields

`save_finding.py` strips, from each model-supplied finding, `key`, `content_hash`, `catalog_evidence`, `evidence_hashes` (today) and `check`, `history`, `confidence_claimed` (new). If #5's `scripts/finding_shape.py` has taken over that list when this lands, the new names go there; the list is one tuple either way.

### 3.5 Cached findings (AC-8)

The bump to `VALIDATION_RULES = 4` routes every findings file validated under 3 through `bundle.py`'s `_still_valid`. None of them carries `preconditions` or commit `role`, so all fail today's rules and their hotspots are investigated again; `report.py` already refuses a file whose `validated_with` is not current. No `high` granted by the fix rule survives, because no file validated under that rule passes, and because reported confidence is derived at render time from the check status (§4), not stored. The cost of the re-investigation on the first scan after upgrading is the price of AC-3 of #54 (every finding states its preconditions); Decision 4 records it.

`FINDING_SCHEMA_VERSION` goes to `thunderstruck.finding/v2`. Nothing branches on it; it records which contract wrote the file.

## 4. Confidence

### 4.1 Check status

`CHECK_STATUSES = ("unchecked", "upheld", "narrowed", "inconclusive", "refuted")` in `_common`. This ticket produces only `unchecked`. `c.check_status(finding) -> str` returns `finding["check"]["status"]` when it is one of the five, and `unchecked` otherwise (a missing or malformed `check` in a file the validator never saw); report.py adds a run warning naming each finding that fell back this way, so the fallback is visible.

### 4.2 The rule (AC-1, AC-2)

```
CONFIDENCE_LEVELS = ("low", "medium", "high")
CONFIDENCE_CEILING = {"upheld": "high", "unchecked": "medium", "narrowed": "medium",
                      "inconclusive": "medium", "refuted": "low"}

effective_confidence(claimed, status):
    level = claimed if claimed in CONFIDENCE_LEVELS else "low"
    if status == "narrowed": level = one step lower, never below "low"
    return the lower of level and CONFIDENCE_CEILING[status]   (an unknown status counts as unchecked)
```

| claimed ↓ / status → | unchecked | upheld | narrowed | inconclusive | refuted |
|---|---|---|---|---|---|
| high | medium | high | medium | medium | low |
| medium | medium | medium | low | medium | low |
| low | low | low | low | low | low |

The claim is an upper bound: a check never raises a finding above what its investigator claimed (Decision 2). `narrowed` drops one level and then the ceiling applies (product decision). `refuted` is `low`; #37 removes refuted findings from the list, so the value matters only where #37 shows them.

### 4.3 Where it is applied

`report.py`'s `collect()` sets, on its copy of each finding, `confidence_claimed` (the file's `confidence`) and `confidence` (`effective_confidence(claimed, check_status(f))`). Every output reads `confidence` from there: `report.md`, `report.json`, `index.json`, and through them the HTML report and the guardrail. The findings file is never rewritten.

## 5. Gate and order (AC-5)

`GATES = ("none", "non_default_setting")`. `finding_gate(f)` returns `non_default_setting` when any precondition has `needs: changed`, else `none`. The report's sort key becomes:

```
(GATES.index(gate), CONFIDENCE_RANK[confidence], -hotspot_score, file)
```

The last three terms are today's key, unchanged, so the order among default-path findings follows today's rule (with today's rule applied to the capped confidence). Display ids are assigned after sorting, as today. One list; gated findings follow the default-path ones and are marked (product decision). `report.json` keeps the findings in this order and the HTML report no longer re-sorts them (§6.4).

## 6. Outputs

All model-written values (setting names, defaults, values, roles, the check's `reason`) are inert: `md.code` for setting names, defaults and values, `md.text` for the rest in `report.md`; `textContent` in the HTML; plain text in the guardrail, which already emits no markup. Only the tool builds links (`mdtext.linked`), including those to `default_ref` and `doc_ref`.

### 6.1 `report.md`

**Header.** The breakdown line keeps its count by confidence and gains a second line:

```
Check status: 5 unchecked · 1 finding needs a non-default setting and is listed last
```

The blockquote under the header is replaced (AC-7):

> Findings are **falsifiable hypotheses**. Every citation in them was resolved mechanically: each cited file:line, commit, detector hit and catalog edge exists. That is all validation proves. Whether a claim holds is its **check status**; a finding nobody has tried to refute is `unchecked`, and its confidence is at most `medium`. Check the `Verify` line before you act on one.

The coverage paragraph's "those a validated finding cites" becomes "those cited by a finding whose citations resolved", and the `lead_precision` docstring's wording follows. The Incomplete reason "findings not validated by this version's rules" stays: there "validated" names the step, and the sentence says which rules.

**Per finding**, the badge line gains the check status and, for a gated finding, the marker:

```
**medium confidence** · unchecked · needs a non-default setting · [src/client/api.ts:3-15](…) · `callApi` · hotspot H07 (score 0.0249)
```

The row table shows `Amplifier` and `Sustaining effect` with *not stated* when absent. After the evidence list and before **Verify**:

```
**Check** — unchecked. No one has tried to refute this claim, so it is reported at medium confidence (claimed high).

**Preconditions**

- `API_RETRY_ON_429` set to `true`; default `false (unset)`, registered at [src/client/api.ts:1](…). The docs do not describe this behaviour.

**History** — a signal of how often this code changed, not of whether the claim holds.

- [`1a2b3c4`](…) fix · stated role: fixed · wrote a cited line
```

- **Check**: one sentence per status, from `CHECK_SENTENCES` in `_common` (unchecked: "No one has tried to refute this claim"; upheld: "A check tried to refute this claim and it held"; narrowed: "A check found that only part of this claim holds"; inconclusive: "A check could not settle this claim"; refuted: "A check refuted this claim"), then, only when the reported confidence is below the claim, ", so it is reported at C confidence (claimed X)", then `check.reason` when present.
- **Preconditions**: `**Preconditions** — none: the failure happens on default settings.` for an empty list. Otherwise one line per item: `needs: changed` reads "`S` set to `V`; default `D`, registered at REF."; `needs: default` reads "`S` left at its default `D`, registered at REF."; then "The docs describe this behaviour: REF." / "The docs do not describe this behaviour." / "Docs not checked." A list of only `needs: default` items is preceded by "The failure happens on default settings and rests on these defaults:".
- **History**: one line per entry: the linked short sha, the class (or "class unavailable"), "stated role: R", and "wrote a cited line" or "wrote none of the cited lines". With no cited commit: `**History** — none cited.`
- **Evidence**: a commit line keeps its subject (`— “subject”`) and drops the `(kind)` suffix, which moves to History. Nothing else in the evidence list changes.

### 6.2 `report.json`

`REPORT_SCHEMA_VERSION` becomes `thunderstruck.report/v2` (Decision 9): `confidence` changes meaning and `amplifier`/`sustaining_effect` may be absent. Per finding, in addition to today's fields:

| Field | Value |
|---|---|
| `confidence` | the reported confidence (§4.2) |
| `confidence_claimed` | the investigator's claim |
| `check` | the finding's `check` object as stored, with `status` normalised by `check_status` |
| `gate` | `none` · `non_default_setting` |
| `preconditions` | as validated, each item gaining `default_url` and `doc_url` (a link or `null`) |
| `history` | as validated, each entry gaining `url` (the commit link or `null`) and `subject` |

Absent `amplifier` and `sustaining_effect` stay absent. `counts` gains `check_status` (all five keys, zeros included) and `gate` (both keys). The commit evidence item's `kind` is dropped in favour of `history[].class`; `subject` stays.

### 6.3 `index.json`

Stays `thunderstruck.index/v1`; the change is additive. Each finding entry gains:

```json
"check_status": "unchecked",
"gate": "non_default_setting",
"preconditions": [{"setting": "API_RETRY_ON_429", "default": "false (unset)", "needs": "changed", "value": "true"}],
"history": [{"sha": "1a2b3c4", "class": "fix", "wrote_cited_line": true}]
```

`confidence` is the reported one. `sustaining_effect` is written only when present. Refs, docs and roles are left out: the guardrail states facts in a few lines and points at the report for the rest.

### 6.4 HTML report

`templates/report.html`:

- The client-side sort by confidence is removed; findings appear in `report.json` order. The rail still groups consecutive findings of one hotspot.
- The dossier's meta row shows a tag for the check status beside the confidence tag, and a `needs a non-default setting` tag for a gated finding. A rail item for a gated finding shows a small `setting` marker after its patterns.
- New rows, in this order after Evidence: **Check** (the same sentence as §6.1, from a `CHECK_SENTENCES` object in the script that a test compares with `_common`), **Preconditions** (one line per item, as §6.1, `default_ref`/`doc_ref` linked through the existing `link()` with `default_url`/`doc_url`), **History** (one line per entry, as §6.1).
- **Amplifier** and **Keeps it failing** show "Not stated." when absent, styled `quiet`.
- The commit evidence line drops `(kind)`.
- The overview's hypothesis banner and its coverage sentence get §6.1's wording. The head counts gain the number of unchecked findings.

Everything stays `textContent`; no new sink, no new network access, and the CSP hash is recomputed by `report_html.py` as today.

### 6.5 Guardrail

`guardrail.py` (stdlib only, always exit 0, statements of fact). Per shown finding:

```
- FR-005 (lines 3-15): A 429 is retried after a fixed 5s …
  missing patterns: S03; confidence: medium; check status: unchecked.
  It happens only with a non-default setting: API_RETRY_ON_429 set to true (default false (unset)).
  Cited commits: 1a2b3c4 fix, wrote a cited line; 5d6e7f8 feature, wrote none of the cited lines.
  what keeps it failing: …
```

- The precondition line: no items: "It happens on default settings."; only `needs: default`: "It happens on default settings and rests on S at its default D."; any `needs: changed`: "It happens only with a non-default setting:" and those items. At most 3 items, then "and N more".
- The history line: at most 3 entries, then "and N more"; omitted when there are none.
- An entry from an index written before this change has no `check_status`: the guardrail treats it as `unchecked`, applies its copy of the ceiling to the stored `confidence` (so an old `high` is stated as `medium`), and omits the precondition and history lines rather than inventing them.
- Findings are ordered by gate, then confidence, matching the report. The closing sentence stays: "These are hypotheses from a past scan, not verified defects."

The latency budget (100 ms median) is unchanged; the added work is string formatting over at most three findings.

## 7. Extension points

### 7.1 For #37 (verification)

- **Status.** #37 writes `check.status` into each findings file after `validate.py`, using the five values of §4.1, and nothing else changes confidence: `effective_confidence` already maps every status. #37 must not add a status; a sixth value needs this spec changed first.
- **Its own keys.** Everything else #37 records about a verdict goes under `check`: `by` (e.g. `"skeptic"`), `reason` (one line, inert text), and keys this spec reserves for #37 without defining: `holds`, `refuted_claims`, `evidence`, `model`, `dependency_versions`, `reused_from`. `validate.py` accepts and does not read them; `report.json` passes `check` through whole; rendering them is #37's change.
- **Refs into dependencies.** When #37 adds a reference form into dependency source, `default_ref` and `doc_ref` accept it through `check_ref` (§3.1), the one function both use.
- **Re-validation.** `validate.py` never overwrites an existing `check` (§3.2). Invalidating a verdict when cited code changes is #37's rule (its AC-9), applied by #37.

### 7.2 For #57 (confirmed defaults)

- **Confirmation per precondition.** #57 adds one key to each precondition item, which this spec reserves as `confirmation` (e.g. `{"state": "unconfirmed", "reason": "…"}`), and writes it after validation. To do so #57 adds `confirmation` to the precondition keys `validate.py` accepts from a later stage and to the keys `save_finding.py` strips from model output; until then a model writing it fails validation (§2.2).
- **Order.** #57 appends its value to `GATES` (reserved name: `unconfirmed_default`) and extends `finding_gate`. The sort key, the marker, `counts.gate` and the guardrail's ordering all read `GATES`, so no renderer changes order logic. Whether `unconfirmed_default` sorts before or after `non_default_setting` is #57's decision.
- **`needs: default` items** are the defaults #57 confirms; they exist from this ticket on, so #57 adds no investigator field.

## 8. Fixture and sample (AC-10)

The fixture has no setting with a registered default, so the sample could not show a gated finding. `tests/fixtures/build_fixture.py`'s `IGNORES_RETRY_AFTER` (`src/client/api.ts`) gains an opt-in switch:

```ts
const RETRY_ON_429 = process.env.API_RETRY_ON_429 === "true";

export async function callApi(path: string): Promise<Response> {
  …
  if (RETRY_ON_429 && res.status === 429) {
```

S03's TypeScript detector still fires (the anchor `429` and the `setTimeout` requirement are unchanged, and nothing matches its `Retry-After` absent pattern). `gen_sample_report.py`'s canned api.ts finding gains the `API_RETRY_ON_429` precondition (`needs: changed`, `documented: no`, `default_ref` found by anchor), and is listed last and marked. Every canned commit carries a role (`introduced` for the `OTHER` finding's blamed commit, `fixed` for a cited fix, `changed` otherwise). The scheduler finding drops `sustaining_effect` so the sample shows *not stated*. The three canned `high` claims stay: the sample shows them as `medium` with "(claimed high)". Both samples are regenerated in the same change.

## 9. Measuring it on #55 (AC-9)

This needs #55's `scripts/benchmark.py` on `main`.

- **Adapter.** `run_from_report` (#55 §3.2) adds `preconditions: [{"setting", "default"}]` to a run record when the report's finding carries `preconditions`, as #55's spec assigns to this ticket. Reports without the field (the frozen Celery scan) produce records without it.
- **After-run.** `docs/calibration/correctness/celery/runs/checked-confidence.json` (`produced_by: {"stage": "confidence", "model": null, "source": "scan/report.json via _common.effective_confidence, every finding unchecked"}`) holds, per frozen finding, `effective_confidence(claimed, "unchecked")`. A test re-derives it from `scan/report.json` and compares, as #55 does for its refuter baseline.
- **Figures** (labels: 21 by claude-fable-5-1, 20 executed, 1 read):

| Run | exact | within one | over | under | `high` above deserved |
|---|---|---|---|---|---|
| Before: `--report scan/report.json` | 8 | 20 | 6 | 7 | FR-001, FR-003 |
| After: `--run runs/checked-confidence.json` | 8 | 21 | 5 | 8 | none |

Agreement equals the always-`medium` baseline (8 of 21), which is the ticket's floor before #37; the over-rated `high`s go to zero. The PR quotes both lines as `benchmark.py` prints them, with their intervals.

## 10. Test strategy

- **Rule tables.** `effective_confidence` over all 15 cells of §4.2; `finding_gate` on empty, `needs: default`-only and mixed lists; `check_status` on missing, malformed and each valid status; the guardrail's ceiling copy equals `_common`'s on every cell; the HTML script's `CHECK_SENTENCES` equals `_common`'s.
- **Validator** (`Validator` against the small repo of `test_validate_paths.py`, and the scanned fixture for blame): each §2.2 rule with its message; `default_ref`/`doc_ref` through every path rejection `code` refs get (absolute, `..`, untracked, out of range); `role` missing, unknown, on a non-commit item; `introduced` accepted for the blamed commit and rejected for one that only touched the file and for an uncommitted line; `high` with only a `feature` commit now passes; `check` absent → written `unchecked`, existing → kept, bad status → rejected; `history` entries with class and `wrote_cited_line`; empty-string `amplifier` rejected, absent accepted.
- **Owned fields.** A model output carrying `check: {"status": "upheld"}`, `history` and `confidence_claimed` is saved without them and reported `unchecked`, at most `medium`.
- **Caching (AC-8).** A findings file stamped `validated_with: 3` with a `high` claim and a `fix` commit is re-investigated by `bundle.py` and reported Incomplete by `report.py` until it is.
- **Report.** Order: a gated finding with `high` claim and the highest score is listed after a default-path `low`; display ids follow. `report.json` carries every §6.2 field and count; `index.json` §6.3's. Absent fields render *not stated* in md and HTML. The AC-7 wording, and no bare "validated finding" left in `report.md` or the template.
- **Inert text.** The existing hostile-text tests in `test_inert_report.py` and `test_report_html.py` extend `MODEL_FIELDS` to precondition `setting`, `default`, `value` and `check.reason`.
- **Guardrail.** The three precondition phrasings, the history line, the cap on an old index entry, the ordering, fact-not-instruction phrasing, latency.
- **Sample.** `gen_sample_report.py --check`; the sample shows `unchecked`, `(claimed high)`, a gated finding last with its marker, *not stated*, and a History block.
- **Benchmark (AC-9).** The adapter carries preconditions; the after-run re-derives; both rows of §9's table.

## 11. Security

- New model-written strings are rendered inert in every output (§6). `default_ref` and `doc_ref` are resolved inside the repository with the existing path checks before any file is opened, so a precondition cannot make the validator read outside the repository.
- A model cannot raise its own finding: `check`, `history` and `confidence_claimed` are stripped on save (§3.4), and confidence is derived, not read.
- Repository text that tries to steer the audit ("this default is safe", "mark as upheld") is data, as today; the investigator prompt's rule covers preconditions, and such text is an `OTHER` finding.
- The guardrail's new lines are statements of fact with no imperative phrasing; the existing phrasing test covers them.

## 12. Degradation

| Condition | Behaviour |
|---|---|
| A commit subject cannot be read | `history[].class` is `null`, rendered "class unavailable"; validation does not fail on it |
| `git blame` fails for a range | That range contributes no shas: `wrote_cited_line` is false and an `introduced` role is rejected with the blame message, as today's `OTHER` rule does |
| A findings file has a missing or unknown check status | Treated as `unchecked`; a run warning names the finding |
| An `index.json` from before this change | Guardrail caps confidence as `unchecked`, omits the new lines |
| A `report.json` with schema v1 | `report_html.py` refuses it with its existing schema message ("Re-run the scan") |
| Cached findings from 0.9.x | Re-investigated on the first scan (§3.5); the bundle step's "investigated again" line counts them |

## 13. Consumption

No model call is added. The investigator writes a few more fields per finding and reads no more files. The one-off cost is §3.5's re-investigation of cached hotspots on the first scan after upgrading, which the bundle step reports.

## 14. Decisions

1. **Confidence is derived at render time, not stored.** One function maps claim and status; the findings file keeps the investigator's claim, so #37 changing a status needs no rewrite of confidence, and no stored `high` can outlive the rule that granted it.
2. **The claim is an upper bound.** A check can lower confidence and can permit `high`; it never raises a finding above what its investigator claimed. A skeptic upholding a claim its own author rated `medium` has not shown more than `medium`.
3. **Fix history leaves confidence entirely.** Spike 3: no history rule beats always-`medium` by more than 3 of 21. History is kept, per commit, as a labelled signal.
4. **`preconditions` is required, and cached findings are re-investigated once.** Letting old findings through as "preconditions not stated" would break #54 AC-3 for exactly the scans that upgrade; a one-time re-investigation is the existing cost of every rules bump.
5. **A commit's role is stated by the model and checked only where it can be.** `introduced` is decidable by blame; `fixed`, `mitigated` and `changed` are intent, shown beside the mechanical class so a disagreement is visible.
6. **`needs: default` items exist now, though they do not gate.** The defaults a claim rests on are what #57 confirms; defining them here keeps the investigator contract from changing twice.
7. **No environment preconditions.** A deployment condition has no registered default to cite or confirm; it is a trigger. Celery's one such item (a database user's privileges) reads correctly as a trigger.
8. **`default_ref` resolves inside the repository only.** A reference that cannot be resolved cannot be shown as resolved; dependency refs arrive with #37.
9. **`report.json` goes to v2.** `confidence` changes meaning and two fields may be absent; a consumer must notice. `index.json`'s change is additive and its one reader, the guardrail, handles both.
10. **`documented` is three-valued.** "We did not look" and "we looked and the docs are silent" are different facts, and the investigator's read budget makes the first common.
11. **History in its own block; evidence keeps the subject.** One place states class, role and blame; the evidence list stays what the investigator cited.
12. **The fixture gains an opt-in setting.** A sample that cannot show a gated finding would not describe the feature; the change keeps every planted fracture and its detector.

## 15. Open design questions

None.
