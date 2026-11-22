# The capture hook says whether it ran: Implementation Plan

> For agentic workers: build task by task, test first. Steps use checkbox (`- [ ]`) syntax.

**Ticket:** #96. **Spec:** `docs/superpowers/specs/2026-11-22-hook-capture-trace-design.md`. Each task names the `AC-n` of the ticket it satisfies. A design change goes in the spec first.

**Goal:** after a scan, `--check` and the report say whether the capture hook ran and why a result was not saved.

**Branch:** named by whoever builds it; the agent uses `agent/96-hook-capture-trace`. Stage explicit paths only. Do not bump the version (maintainer's call, 2026-11-22); add the change under `## Unreleased` in `CHANGELOG.md`.

**Tests:** the whole suite is the command at the top of CLAUDE.md. Guardrail and hook tests: `tests/test_guardrail.py`, `tests/test_capture_finding.py` (find the real name in Task 0).

## Task 0: anchors (no AC)

- [x] Read the spec. Confirm `capture_finding.py` filters with `endswith`, `hooks.json` has the matcher, `save_finding.py` has `check(index, findings, ids)`, and find the verify check function with `grep -n "missing" scripts/verify.py`.
- [x] Find the existing hook tests: `git grep -ln capture_finding tests`. Record their names here when found.
- [x] Run them; note they pass.

## Task 1: the trace (AC-1)

**Files:** `scripts/capture_finding.py`, the hook test file.

- [x] Failing tests, one per outcome of spec §2.1 (`saved`, `no_message`, `no_index`, `no_entry`, `bad_payload`, `error:<Class>`), each asserting the line in `.thunderstruck/hook-trace.jsonl`: keys as listed, `agent_type`, `outcome`, no message text, and that stdout is empty and the exit code 0. Plus: another plugin's `agent_type` writes no file; a 64 KiB file takes no more lines; a read-only `.thunderstruck/` still exits 0 silently.
- [x] Run: fail (no trace).
- [x] Implement a `_trace(root_out, payload, outcome, hotspot_id=None)` in `capture_finding.py` (stdlib; `json`, `datetime`). Call it once per run from `main`, with the outcome decided where each early `return` is today. The `except BaseException` in `__main__` writes `error:<type(exc).__name__>` if it can find the root, and swallows any failure to do so.
- [x] Tests pass; the guardrail's AST check (stdlib only) and latency tests still pass.
- [x] Commit `scripts/capture_finding.py` and the test file by path. Body: `AC-1`, `Task: 1`, red line.

## Task 2: `--check` says why (AC-2)

**Files:** `scripts/save_finding.py`, `scripts/verify.py`, a shared helper in `scripts/finding_shape.py` (stdlib; it is imported by the hook).

- [ ] Failing tests for the three situations of spec §2.2, for `save_finding.py --check` and `verify.py check`: the first word of each line is unchanged; the parenthesis is the sentence the spec gives.
- [ ] Implement `finding_shape.trace_reason(out, scan_stamp, hotspot_id_or_key)` returning the sentence or `None`; both checks append it to a `missing` line.
- [ ] Commit by path. `AC-2`, `Task: 2`.

## Task 3: the report says it once (AC-3)

**Files:** `scripts/report.py`, `scripts/usage.py` only if it must expose the count, tests.

- [ ] Failing test: with `fallback_saves` over half the saved results and a trace with no lines, Run warnings holds "The capture hook delivered 0 of N results: it did not run."; with `no_message` lines the sentence names the outcome. Text built from counts and outcome names; the existing inert-text tests still pass.
- [ ] Implement, regenerate `examples/` only if the sample changes (it should not): `uv run scripts/gen_sample_report.py --check`.
- [ ] Commit. `AC-3`, `Task: 3`.

## Task 4: drop the matcher (AC-4)

**Files:** `hooks/hooks.json`, `tests/test_guardrail.py`.

- [ ] Change the pinning test (`test_hooks_json_declares_each_event_once`) to assert `"matcher" not in stop` and to import `capture_finding` and assert that an `agent_type` of `thunderstruck:thunderstruck-skeptic` and of `thunderstruck-skeptic` are both accepted and `other:agent` is not. Run: fails on the matcher.
- [ ] Remove the matcher from `hooks.json`.
- [ ] Time the hook on a payload for an unrelated agent: median under 100 ms (`tests/test_guardrail.py`'s latency approach).
- [ ] `uv run scripts/validate_plugin.py` and a plugin install (CLAUDE.md "Plugin manifest"): `claude plugin list` must say enabled.
- [ ] Commit. `AC-4`, `Task: 4`.

## Task 5: docs and the skill (AC-5)

- [ ] `skills/thunderstruck-scan/SKILL.md` step 3 and 5: say `--check` may print a reason, and that "the hook did not run for any agent" means every result is saved by fallback and the report names it. CLAUDE.md "The guardrail's hard constraints" gains the trace sentence. `CHANGELOG.md` under `## Unreleased`.
- [ ] Run the full suite, `gen_sample_report.py --check`, `gen_catalog_docs.py --check`, `validate_plugin.py`. All pass before any push.
- [ ] Commit. `AC-5`, `Task: 5`.

## Task 6: the measured run (maintainer, AC-6)

- [ ] Maintainer: install this checkout as a local marketplace, run one scan in a fresh session with background agents as in the ticket, then copy `.thunderstruck/hook-trace.jsonl`'s keys and outcomes into `docs/calibration/hook-capture.md` with the plugin version, commit and Claude Code version. If the trace shows `no_message` or no lines, say which follow-up of spec §2.5 applies and open it as a ticket.
- [ ] The agent stops here and labels nothing: it marks the PR ready after Task 5 and notes that AC-6 is the maintainer's.
