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
  resolve. A `detector` ref is `S0x@path:line` matching a hit in
  `hotspots.json` exactly.
- **`missing_patterns` ⊆ catalog IDs ∪ {`OTHER`}.**
- **`confidence: "high"` requires both `code` and `commit` evidence.** A
  hypothesis the change history does not corroborate tops out at `medium`.
- **`sustaining_effect` may be `null`, never omitted.** Asking the question is
  mandatory; a negative answer is a real answer.
- **0–3 findings per hotspot.** Empty is valid and common on well-built code.

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
