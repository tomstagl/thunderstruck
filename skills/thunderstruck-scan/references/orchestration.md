# Orchestration reference

## The pipeline

```
signals.py   →  hotspots.json          deterministic: churn, complexity, detectors, coupling
context.py   →  context.json           deterministic: runs the approved catalog command, if configured
bundle.py    →  bundles/*.md           deterministic: one briefing per hotspot
investigator →  (final message)        the only LLM step
capture_finding.py → findings/*.json    SubagentStop hook: saves each result, records agents/*.json
validate.py  →  validation.json        deterministic: schema + evidence resolution
usage.py     →  usage.json             deterministic: what the scan consumed, from transcripts
report.py    →  report.md/.json/index.json
```

Everything except the investigator is reproducible. Rerunning the scripts on
an unchanged repository produces byte-identical output, which is what makes
the cache in step 3 safe.

## Cost control

The subagent count equals the number of non-cached bundles, which `--top`
caps. A bundle is budgeted at roughly 8k tokens, but an investigator costs
far more than its bundle: every call re-sends the whole conversation so far,
and it reads code to confirm its leads.

Consumption is counted in **weighted tokens**: each token weighted by its
published price relative to Claude Sonnet 5.5 base input = 1, per model and
token type. The table is `TOKEN_WEIGHTS` in `${CLAUDE_PLUGIN_ROOT}/scripts/_common.py`:

| Model | input | cache write 5m | cache write 1h | cache read | output |
|---|---|---|---|---|---|
| `claude-sonnet-5-5` | 1 | 1.25 | 2 | 0.1 | 5 |
| `claude-opus-5-5` | 2 | 2.5 | 4 | 0.1 | 10 |
| `claude-haiku-4-5` | 0.5 | 0.625 | 1 | 0.05 | 2.5 |
| `claude-fable-5-1` | 5 | 6.25 | 10 | 0.125 | 25 |

Measured before the consumption work (`docs/calibration/consumption.md`, a
default `--top 10` scan of a real repository, everything on
`claude-opus-5-5`, mean of two runs): about **1.65M weighted tokens**, of
which the orchestrating session was 711k and ten investigators 941k. Weighted
with the Sonnet 5.5 row, one investigator consumed about 10.9 weighted tokens
per bundle token, and read up to 9 extra files.

What keeps it down:

- Investigators run on Sonnet unless you pass `--model`. On the baseline,
  that alone takes the investigators from 941k to about 546k.
- A hook saves each result, so the orchestrator never re-types a finding and
  nothing is investigated twice.
- The orchestrator reads no bundles or findings, never polls, and the scripts
  print summaries only (`--verbose` restores the detail).

`bundle.py` ends with an estimate for the investigators, and every report has
a **Consumption** section with what the scan actually used.

`--dry-run` prints the plan and the estimate without spending any of it. Suggest it for a
first run on a large or unfamiliar repository.

To scan one area at a time, `--path src/services` restricts both ranking and
bundling.

## Resuming an interrupted scan

Just run `/thunderstruck-scan` again with the same arguments. `bundle.py`
marks every bundle whose content hash matches an existing finding as
`cached`, and step 3 skips those. An interrupted scan resumes where it
stopped, because the hook saves each finding the moment its investigator
finishes rather than at the end.

To force a full re-investigation, delete `.thunderstruck/findings/`.

## When things fail

| Situation | What to do |
|---|---|
| `uv` missing | Stop. Tell the user how to install it. |
| Not a git repository | Stop. thunderstruck reads history; there is nothing to read. |
| No commits in the window | `signals.py` says so and suggests a wider `--since`. Relay it. |
| `lizard` missing | The run continues on churn alone and warns. Relay the warning — the ranking is weaker, not wrong. |
| No supported language changed | Stop. Say which languages are supported. |
| Service context command fails or times out | The scan continues. With a cached copy younger than 2 × `max_age_days` it reuses that and warns; otherwise it runs without context and warns. Relay the warning. |
| Service context not approved on this machine | Continue without it and say so. The user approves with `/thunderstruck-context-config`; never approve on their behalf. |
| An investigator returns prose, not JSON | `save_finding.py` strips a markdown fence automatically. If it still fails, record `--failed`. |
| Hook did not save a result | `save_finding.py --check` says `missing`; save it with `--fallback`; the report counts it. |
| Validation fails | Exactly one repair round for that hotspot, then `--failed`. |
| Everything fails | Still run `report.py`. A report that says "6 hotspots, 0 analysed" is information. |

## Bounded concurrency

Four investigators at a time, maximum. The reason is not politeness: a tool
whose own failure mode is "spawn N concurrent workers against a shared quota"
has no standing to report S05 or S06 in anyone else's code.

## What leaves the machine

Nothing that Claude Code was not already going to see. The scripts run
locally and write only into `.thunderstruck/`. The bundles contain source and
commit history from the repository, and those bundles are what the
investigator subagents read — so repository content reaches the model exactly
as it would if you had asked Claude to read those files directly. The scripts
make no network calls, send no telemetry and talk to no external
service. The one opt-in exception: when you configure and approve a service
context command, `context.py` runs it, and that command may call your service
catalog. thunderstruck passes it the entity ref (and, when neighbour
attributes are configured, each neighbour's ref), and it runs with the user's
environment.

`usage.py` reads Claude Code's own transcripts on this machine and writes
counts only: token counts by type and model, ids and timestamps, never any
text from the conversation.
