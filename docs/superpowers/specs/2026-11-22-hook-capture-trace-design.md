# The capture hook says whether it ran: design

**Requirements:** [#96](https://github.com/tomstagl/thunderstruck/issues/96). The problem, stories, scope and acceptance criteria (AC-n) are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-22-hook-capture-trace.md`.
**Evidence:** `hooks/hooks.json` (`SubagentStop`, matcher `thunderstruck-investigator|thunderstruck-skeptic`, command ends `2>/dev/null || exit 0`); `scripts/capture_finding.py` (`main`: filters on `agent_type.endswith(...)`, returns silently when `last_assistant_message` is not a string, the whole body inside `except BaseException: pass`); `scripts/save_finding.py:49-58` (`check`, prints `saved|missing|failed`); `tests/test_guardrail.py:204-216` (pins the matcher); the scan skill step 3 (`--check`, then a fallback save per `missing`).

## 1. What is known and what is not

Two scans saved 0 of 19 results by hook. The hook's own contract (exit 0, silent, never fails) makes "did not run" and "ran and wrote nothing" identical from outside. The ticket names three candidate causes, none verified:

1. The matcher does not match the namespaced agent type (`thunderstruck:thunderstruck-investigator`).
2. A background agent's payload has no `last_assistant_message`, and the script returns without saying so.
3. The hook is not registered when the plugin runs from a source checkout.

**Design rule.** This ticket does not guess among them. It makes the next scan say which one it is, and removes the cause that the script already makes unnecessary.

## 2. Decisions

### 2.1 A trace line per invocation, always on, bounded

`capture_finding.py` appends one JSON line to `.thunderstruck/hook-trace.jsonl` for each invocation whose `agent_type` ends with `thunderstruck-investigator` or `thunderstruck-skeptic`:

```json
{"at": "2026-11-22T10:01:02+00:00", "agent_type": "thunderstruck:thunderstruck-investigator",
 "keys": ["agent_id", "agent_type", "cwd", "session_id", "transcript_path"], "outcome": "no_message"}
```

`outcome` is one of `saved`, `no_message` (the field is absent or not a string), `no_index`, `no_entry` (the result named no hotspot or key in the index or plan), `bad_payload`, `error:<ExceptionClassName>`. Only key names, the agent type, a time and the outcome are written: never the message, a path or any repository text. The file stops growing at 64 KiB (a line that would pass it is dropped), is written under `.thunderstruck/` only (`_root` finds the repository as today; no directory is created), and any failure to write is swallowed. The hook's contract (exit 0, silent, stdlib only, under 100 ms) is unchanged; `tests/test_guardrail.py`'s latency and AST checks apply to it.

**Why always on.** An opt-in switch needs the user to know the problem exists before it happens; the ticket's whole complaint is that it was invisible. The cost is one small append per subagent stop.

**Why not log to stderr.** The command redirects it away, correctly: it must never reach the model.

### 2.2 `--check` tells "never ran" from "ran and did not save"

`save_finding.py --check` and `verify.py check` still print `saved`, `missing`, `failed` first on the line. A `missing` line gains a reason from the trace, taken from lines at or after the scan's `generated_at` (`hotspots.json`):

- no trace line for this scan at all: `missing (the capture hook did not run for any agent in this scan)`;
- lines exist, none for this id: `missing (the hook ran for N other agents, none delivered this one)`. A line carries `id` (a hotspot id or finding key) only when the outcome is `saved`, because only then has the hook parsed the message and found the entry; for every other outcome the hook does not know whose result it was, so the reason is the aggregate above;
- every line since the scan began has an outcome other than `saved`, and they agree: `missing (the hook ran and recorded no_message)`; when they differ the reason names the most frequent outcome.

A script that prints a reason never changes what `missing` means to the skill: the first word is unchanged.

### 2.3 The run says it once

`usage.py` already knows `fallback_saves`. `report.py` prints, in Run warnings, one line when `fallback_saves` is more than half of the saved results and the trace explains why (the same three sentences, aggregated): "The capture hook delivered 0 of 19 results: it did not run." The sentence is built from counts and an outcome name, never from payload text.

### 2.4 Remove the matcher

The script already ignores any `agent_type` that does not end with one of its two names. A matcher that excludes the namespaced form silently disables it; one that is absent cannot. `hooks.json`'s `SubagentStop` entry drops `matcher`, so the hook runs for every subagent stop and the script decides. Cost: a `python3 -S` start for stops that are not ours, measured under the 100 ms budget (it exits on the first filter, before any file is read). The trace is written only for our two agent types, so other plugins' agents leave nothing behind.

This is a change of mechanism, not a diagnosis. If the trace later shows cause 1 was not the cause, the matcher stays removed: it was redundant either way.

### 2.5 What the first measured run decides

The plan ends with a maintainer-run scan whose `hook-trace.jsonl` is recorded in `docs/calibration/hook-capture.md` (the keys present in a background agent's payload, the outcomes). Two outcomes are anticipated and each is a follow-up, not part of this ticket:

- `no_message` for background agents: the payload's keys name another field (a transcript path) the script could read the last message from. That is a design change and goes through a spec amendment.
- No lines at all from a source checkout: cause 3. The scan's warning for a source checkout then says the hook is not registered.

## 3. Out of scope

Changing how results reach disk for agents the hook cannot see; the results of a hook that delivered a stale result (#72).

## 4. Degradation

Missing trace file: `--check` prints the first sentence of §2.2. An unreadable or malformed trace line is skipped. A trace from an earlier scan is ignored by its timestamp.

## 5. Test strategy

- The hook, run with a payload per outcome, appends the right line and prints nothing and exits 0 (including with a read-only `.thunderstruck/`).
- A payload for another plugin's agent writes nothing.
- The 64 KiB bound.
- `--check` for the three trace situations, for investigators and for skeptics.
- `hooks.json` has no matcher on `SubagentStop`; the guardrail test that pinned it is changed to pin the absence and the script's filter.
- The hook's latency with the trace still under the budget.
- No test spawns Claude Code. The measured run in §2.5 is the maintainer's.
