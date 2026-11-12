# Output schemas and the finding contract

All output lives in `.thunderstruck/` in the scanned repository.

```
.thunderstruck/
├── report.md          human report
├── report.html        the same report as one self-contained page, for a browser
├── report.json        thunderstruck.report/v2 — stable, versioned
├── index.json         thunderstruck.index/v1 — file → findings, read by the hook
├── hotspots.json      thunderstruck.hotspots/v1 — deterministic layer output
├── validation.json    thunderstruck.validation/v1 — what passed, what failed and why
├── usage.json         thunderstruck.usage/v1 — what the scan consumed, counts only
├── catalog-brief.md   the Tier A/B catalog the investigator reads
├── context.json       thunderstruck.context/v1 — service context used by this scan
├── context/raw/       raw catalog responses, kept for audit, never read by bundles
├── bundles/           one briefing per hotspot, plus index.json
├── agents/            per hotspot: which investigators delivered, and a replaced first attempt
├── findings/          per-hotspot investigator output, keyed by bundle hash
├── checks/            verification (#37): plan.json, briefs/, results/, agents/,
│                      verdicts.json, ledger.json (kept across scans), run.json
└── deps/              dependency source the skeptics may read: index.json, and one
                       read-only snapshot per <ecosystem>/<name>@<version>/
```

## Sections of `report.md` in `report.json`

Every section of `report.md` is in `report.json`, computed by `report.py`,
so nothing that reads the JSON has to derive a number itself. These fields
were added without a schema bump; existing fields keep their meaning, except
that v2 changed what `confidence` means (see *Check status, preconditions and
history* below).

- `scanned_at`: when `signals.py` ran (`hotspots.json` `generated_at`), the
  date `report.md` prints as *Scanned*. `generated_at` is when the report
  was rendered.
- `run_warnings`: exactly the list under **Run warnings**: hotspot, context,
  link, usage and check-status warnings, in that order (a check-status warning
  names a finding whose stored check status was missing or unrecognised and
  was reported as `unchecked`). `warnings` keeps its older content
  (hotspot and link warnings only).
- `suppressed`: `[{detector, path, hits, reason}]`, one per suppression rule
  in `.thunderstruck.toml`.
- `coverage_rows`: the **Detector leads by pattern** table, in order:
  `{id, name, tier, unconfirmed_files, leads_read, leads_confirmed, findings}`.
  The `OTHER` row, when present, has `null` where `report.md` shows `—`.
- `files_affected`: the number of distinct files the findings are located in.
- `clean[].cited_by`: per clean hotspot, the ids of findings from other
  hotspots that cite its file as `code` evidence (empty when none).
- `not_scanned`: `{intro, items}`, the sentences under **Not scanned** in
  plain text, or `null` when the scan recorded no coverage gaps.
- `consumption`: the `usage.json` behind the **Consumption** section, with
  per-hotspot figures under `investigators.by_hotspot`, or `null` when this
  scan was not measured. A `usage.json` from an earlier scan is ignored with
  a run warning.

## The finding contract

Enforced mechanically by `validate.py`. A finding that breaks any of these
does not reach the report.

- **At least one `code` evidence item.** A detector hit alone never justifies
  a finding — detectors are pattern matchers, and the investigator's job is to
  decide whether the pattern means anything here.
- **Every ref resolves.** A `code` ref is `path:line` or `path:start-end` in a
  file that exists, with the line inside it. A `commit` ref is a SHA git can
  resolve that changed the finding's file (or a file cited as `code`
  evidence). A `detector` ref is `S0x@path:line` matching a hit in
  `hotspots.json` exactly. A catalog ref is `<relation type> <entity ref>`,
  copied from the bundle's Service context section. It must be an edge in
  `context.json`, from the same snapshot the finding's bundle was built from.
- **`missing_patterns` ⊆ catalog IDs ∪ {`OTHER`}.**
- **`preconditions` is required and may be `[]`.** Each item is one setting
  the failure depends on, with exactly the keys `setting` (non-empty, unique
  within the finding), `default` (non-empty text), `default_ref` (`path:line`
  or `path:start-end`, resolved like a `code` ref), `needs` (`changed` or
  `default`), `value` (required when `needs` is `changed`, absent or `null`
  otherwise), `documented` (`yes`, `no` or `not_checked`) and `doc_ref`
  (resolved like a `code` ref, given only when `documented` is `yes`). Any
  other key is rejected. An empty list means the failure happens on defaults.
- **Every `commit` item has a `role`:** `introduced`, `fixed`, `mitigated` or
  `changed`, and no other evidence type has one. A commit cited as
  `introduced` must have written at least one line of a cited `code` range,
  per `git blame`.
- **`amplifier` and `sustaining_effect` are optional**, and never an empty
  string when present. An absent one is reported as *not stated*.
- **`confidence` is the investigator's claim** (`low`, `medium` or `high`).
  The reported confidence goes through the check-status ceiling below; fix
  history plays no part in it.
- **0–3 findings per hotspot.** Empty is valid and common on well-built code.

## Check status, preconditions and history

`validate.py` writes `check` (`{"status": "unchecked", "by": null, "reason":
null}` unless one is already present, which it never overwrites) and
`history` into each finding it passes. `report.py` reports a confidence of
`_common.effective_confidence(claim, check status)`: only `upheld` can be
`high`, `unchecked`, `narrowed` and `inconclusive` are at most `medium`,
`narrowed` drops one level, and `refuted` is `low`.

Per finding, `report.json` carries, in addition to the contract's fields:

- `confidence`: the reported confidence; `confidence_claimed`: the claim.
- `check`: the stored check object, with `status` normalised to one of
  `unchecked`, `upheld`, `narrowed`, `inconclusive`, `refuted`.
- `gate`: `none`, `unconfirmed_default` or `non_default_setting`
  (`_common.finding_gate`, in that order). Findings are ordered by gate, then
  confidence, then hotspot score; gated findings come after the default-path
  ones and are marked.
- `preconditions`: as validated, each item gaining `default_url` and
  `doc_url` (a link or `null`).
- `history`: one entry per distinct cited commit, `{sha, class, role,
  wrote_cited_line, subject, url}`. A signal of fragility, never of
  confidence.

`counts.check_status` counts all five statuses (zeros included) and
`counts.gate` all three gates. Commit evidence no longer carries `kind`; the class
is in `history[].class`.

`index.json` (still `thunderstruck.index/v1`, additive) gives each finding
`check_status`, `gate`, `preconditions` (`setting`, `default`, `needs`,
`value`, and `confirmation`: `confirmed` or `unconfirmed`) and `history` (`sha`, `class`, `wrote_cited_line`); `confidence` is
the reported one, and `sustaining_effect` is written only when present.

Reserved for #37 (verification), under `check`: `by`, `reason`, `holds`,
`refuted_claims`, `evidence`, `model`, `dependency_versions`, `reused_from`,
`duplicate_of` and `confirmations`. `validate.py` accepts them unread and
`report.json` passes `check` through whole. #37 also extends `finding_gate` so
that a `narrowed` verdict naming a missing setting gates the finding.

## Verification

Step 4b (`verify.py`) gives each validated finding to one read-only skeptic
whose only task is to refute it, and writes the settled result into the
finding's `check`. `checks/run.json` belonging to this scan (its
`generated_at` equals `hotspots.json`'s) is what says verification ran;
without it `report.py` reports every finding `unchecked`, whatever an earlier
scan left in the findings files.

Keys under `check`, all written by `verify.py apply`:

| Key | Content |
|---|---|
| `status` | `upheld`, `narrowed`, `refuted`, `inconclusive` from a verdict; `unchecked` when there is none |
| `by` | `"skeptic"`, or `null` when the pass did not reach the finding |
| `reason` | One line: the skeptic's, or the script's when it downgrades or cannot settle a verdict |
| `holds` | What still holds; required for `narrowed` |
| `refuted_claims` | `[{field, claim, fact, evidence, setting?}]`: `claim` quotes the finding's `field`, `evidence` indexes into `check.evidence` |
| `evidence` | `[{type, ref, note}]`, `type` one of `code`, `commit`, `dependency` (`ecosystem:name@version:path:lines`, into `.thunderstruck/deps/` only); every item resolved |
| `model` | The model id the skeptic ran as |
| `dependency_versions` | `{"pypi:kombu": "5.7.0a1"}`: the packages the skeptic read |
| `reused_from` | `null`, or `{scan, head}` of the scan whose skeptic produced a reused verdict |
| `duplicate_of` | `null`, or the key of another finding in this scan |
| `confirmations` | The skeptic's resolved confirmation items (see *Confirmed defaults*) |

The skeptic returns exactly one JSON object with the top-level keys `key`,
`verdict`, `reason`, `holds`, `refuted_claims`, `evidence`,
`dependencies_read`, `duplicate_of` and `confirmations`; an unknown key, a `verdict` outside
the four, or a `key` it was not given leaves the finding `unchecked` with the
reason. A `refuted` or `narrowed` verdict with no resolving evidence is
`inconclusive`.

In `report.json`:

- `verification`: `{ran, model, checked, reused, dependencies: [{id, version,
  basis, status, reason}], warnings}`.
- `findings[]` leaves out refuted findings and findings merged into another;
  a survivor of a duplicate group gains `also_at: [{key, hotspot_id,
  location, url}]`. Check evidence items gain `url` (repository refs only;
  a dependency ref is never a link), and a refuted claim's `setting` gains
  `default_url`.
- `refuted`: the refuted findings, each shaped like a `findings[]` item
  without an `id`.
- `counts.check_status` counts reported and refuted findings, each duplicate
  group once; `counts.refuted` and `counts.duplicates_merged` are integers.
- `consumption.skeptics`: the skeptics' consumption, separately from the
  investigators'.

In `index.json`: refuted findings are left out, so the guardrail never states
them; a narrowed entry gains `holds`; a survivor of a duplicate group is also
filed under each absorbed finding's file with `"via": "duplicate"` and
`"anchor"` its own file.

## Confirmed defaults

Every precondition carries `confirmation`, written by `validate.py` on every
run and by `verify.py apply`, and derived again by `report.py` from stored
facts (`_common.with_confirmations`); a model never writes it.

| Key | Values |
|---|---|
| `state` | `confirmed` or `unconfirmed` |
| `basis` | `registered` (the only confirmed one), `contradicted`, `call_site_fallback`, `not_found`, `unresolved`, `not_checked` |
| `reason` | `_common.CONFIRMATION_REASONS[basis]` |
| `call_site` | whether the investigator's `default_ref` is a fallback read of the setting (`setting_reads` in the catalog), or `null` when it could not be read |
| `by` | `validator` or `skeptic` |

The skeptic's verdict may carry `confirmations`, a list of `{setting, claim,
stated_ref, found, default, default_ref, reason}`; `found` is `same`,
`different` or `not_found`. `apply` keeps the items that follow the contract
under `check.confirmations`, each with `precondition` (the index of the listed
precondition, or `null` for a default the finding relies on but does not
list), `stated_call_site`, `default_names_setting`, `default_call_site`,
`default_ref_error` and its derived `confirmation`. In `report.json` each item
gains `default_url` and `stated_url` (`null` for a dependency ref). A finding
whose check is `upheld` but that relies on an unconfirmed default settles as
`inconclusive`.

`counts.defaults` is `{"confirmed": n, "unconfirmed": n, "basis": {<six
bases>: n}}` over the listed preconditions and unlisted items of the reported
findings. A doubtful basis (`call_site_fallback`, `contradicted`, `not_found`,
`unresolved`) gates the finding as `unconfirmed_default`, marked "relies on a
doubtful default"; an ungated finding with a `not_checked` default is marked
"default unconfirmed".

## Service context

When `[context]` is configured and approved, `context.json` records the
scanned component's 1-hop catalog neighbours. Its `status` is one of
`not_configured`, `disabled`, `invalid_config`, `untrusted`, `fresh`,
`cached`, `stale` or `failed`. Only `fresh`, `cached` and `stale` are
shown in bundles and the report.

- `report.md` gains a **Service context** section and, per finding that
  cites edges, a **Dependents / dependencies** row.
- `report.json` gains `service_context` (or `null`), and every finding
  carries `catalog_evidence: [{ref, direction, neighbour, attributes}]`,
  resolved from `context.json` by `validate.py`.
- `index.json` finding entries carry `catalog_evidence` when non-empty.

Catalog evidence never stands alone: the `code` rule still applies, and
the edges describe the component, not a file.

## Findings that share cited code

Investigators never see each other's findings, so two hotspots that call one
defective function can each report it. When findings from different hotspots
cite overlapping line ranges of one file as `code` evidence, `report.md`
says so under each of them. In `report.json`, every finding carries
`shares_code_with: [{id, key, refs}]`, empty when there is no overlap.
`refs` lists this finding's own overlapping refs. The findings are linked,
never merged.

## Identity: `id` versus `key`

`id` (`FR-001`) is a display label. It renumbers whenever ranking changes.

`key` is a 12-character hash of the file path and the failure mode. It is
stable across runs, so a later scan can tell whether a finding is the same one
or a new one. Prediction tracking will match on `key`; nothing should match on
`id`.

## Degradation is visible, not silent

A run missing `lizard` ranks on churn alone and says so in `warnings`, which
the report prints in a **Run warnings** section. Hotspots whose analysis
failed appear under **Incomplete** with the reason. A partial report always
states what is missing — a report that quietly analysed four of ten hotspots
would be worse than no report.
