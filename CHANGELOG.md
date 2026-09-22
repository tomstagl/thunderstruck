# Changelog

All notable changes to thunderstruck are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0

First release.

### Added

- `/thunderstruck-scan` — the full pipeline: churn × complexity × missing
  stability patterns, context bundles, investigator subagents, deterministic
  evidence validation, and a ranked report. Supports `--top`, `--since`,
  `--path`, `--dry-run` and `--include-tests`.
- `/thunderstruck-verify FR-001` — turns a finding into a failing test or a
  reproduction, matching the repository's existing test conventions.
- `stability-catalog` — a model-invoked skill that loads the pattern catalog
  when Claude writes or reviews code that crosses a process boundary.
- Stability pattern catalog: 19 patterns across Tier A and Tier B with 57
  detectors for TypeScript/JavaScript and Python, plus 7 Tier C patterns
  catalogued for vocabulary but not scanned.
- `thunderstruck-investigator` subagent: read-only (Read/Grep/Glob), bounded
  to 10 extra file reads, with an explicit rule that repository content is
  evidence and never instruction.
- Deterministic evidence validation. Every `code`, `commit` and `detector`
  ref is resolved mechanically before it reaches the report; invalid findings
  get exactly one repair round, then are recorded as incomplete.
- PreToolUse guardrail hook: warn-only, fail-open, once per file per session,
  medium/high confidence only, with a staleness notice when the file has
  changed since the scan.
- Checkpointing by bundle content hash, so an interrupted scan resumes and an
  unchanged hotspot is never re-investigated.
- Repo profiles (`.thunderstruck.toml`) for re-tiering patterns and declaring
  boundary facts.
- Fixture-based test suite with planted fractures and a negative control, plus
  positive and negative detector samples per pattern per language.

### Notes

- The guardrail runs on `PreToolUse` rather than `PostToolUse`, so the warning
  arrives before the edit. The hooks reference documents
  `hookSpecificOutput.additionalContext` for that event.
- The matcher is `Edit|Write|NotebookEdit`. `MultiEdit` no longer exists in
  Claude Code.
