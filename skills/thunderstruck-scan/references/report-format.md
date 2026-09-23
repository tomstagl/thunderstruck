# Output schemas and the finding contract

All output lives in `.thunderstruck/` in the scanned repository.

```
.thunderstruck/
├── report.md          human report
├── report.json        thunderstruck.report/v1 — stable, versioned
├── index.json         thunderstruck.index/v1 — file → findings, read by the hook
├── hotspots.json      thunderstruck.hotspots/v1 — deterministic layer output
├── validation.json    thunderstruck.validation/v1 — what passed, what failed and why
├── catalog-brief.md   the Tier A/B catalog the investigator reads
├── context.json       thunderstruck.context/v1 — service context used by this scan
├── context/raw/       raw catalog responses, kept for audit, never read by bundles
├── bundles/           one briefing per hotspot, plus index.json
└── findings/          per-hotspot investigator output, keyed by bundle hash
```

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
- **`confidence: "high"` requires both `code` and `commit` evidence.** A
  hypothesis the change history does not corroborate tops out at `medium`.
- **`sustaining_effect` may be `null`, never omitted.** Asking the question is
  mandatory; a negative answer is a real answer.
- **0–3 findings per hotspot.** Empty is valid and common on well-built code.

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
