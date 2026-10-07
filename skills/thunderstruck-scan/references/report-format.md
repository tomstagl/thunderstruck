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
└── findings/          per-hotspot investigator output, keyed by bundle hash
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
- `coverage_rows`: the **Pattern coverage** table, in order:
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
- `gate`: `none` or `non_default_setting` (`_common.finding_gate`). Findings
  are ordered by gate, then confidence, then hotspot score; gated findings
  come last and are marked.
- `preconditions`: as validated, each item gaining `default_url` and
  `doc_url` (a link or `null`).
- `history`: one entry per distinct cited commit, `{sha, class, role,
  wrote_cited_line, subject, url}`. A signal of fragility, never of
  confidence.

`counts.check_status` counts all five statuses (zeros included) and
`counts.gate` both gates. Commit evidence no longer carries `kind`; the class
is in `history[].class`.

`index.json` (still `thunderstruck.index/v1`, additive) gives each finding
`check_status`, `gate`, `preconditions` (`setting`, `default`, `needs`,
`value`) and `history` (`sha`, `class`, `wrote_cited_line`); `confidence` is
the reported one, and `sustaining_effect` is written only when present.

Reserved for #37 (verification), under `check`: `by`, `reason`, `holds`,
`refuted_claims`, `evidence`, `model`, `dependency_versions`, `reused_from`,
`duplicate_of` and `confirmations`. `validate.py` accepts them unread and
`report.json` passes `check` through whole. #37 also extends `finding_gate` so
that a `narrowed` verdict naming a missing setting gates the finding.

Reserved for #57 (confirmed defaults): `preconditions[].confirmation`, and the
gate `unconfirmed_default`, placed in `GATES` by #57.

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
