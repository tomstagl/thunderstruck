# Orchestration reference

## The pipeline

```
signals.py   →  hotspots.json          deterministic: churn, complexity, detectors, coupling
bundle.py    →  bundles/*.md           deterministic: one briefing per hotspot
investigator →  findings/*.json        the only LLM step
validate.py  →  validation.json        deterministic: schema + evidence resolution
report.py    →  report.md/.json/index.json
```

Everything except the investigator is reproducible. Rerunning the scripts on
an unchanged repository produces byte-identical output, which is what makes
the cache in step 3 safe.

## Cost control

The subagent count equals the number of non-cached bundles, which `--top`
caps. Each bundle is budgeted at roughly 8k tokens, so `--top 10` is about
80k tokens of input across ten agents.

`--dry-run` prints the plan without spending any of it. Suggest it for a
first run on a large or unfamiliar repository.

To scan one area at a time, `--path src/services` restricts both ranking and
bundling.

## Resuming an interrupted scan

Just run `/thunderstruck-scan` again with the same arguments. `bundle.py`
marks every bundle whose content hash matches an existing finding as
`cached`, and step 3 skips those. An interrupted scan resumes where it
stopped, because each finding is saved the moment it arrives rather than at
the end.

To force a full re-investigation, delete `.thunderstruck/findings/`.

## When things fail

| Situation | What to do |
|---|---|
| `uv` missing | Stop. Tell the user how to install it. |
| Not a git repository | Stop. thunderstruck reads history; there is nothing to read. |
| No commits in the window | `signals.py` says so and suggests a wider `--since`. Relay it. |
| `lizard` missing | The run continues on churn alone and warns. Relay the warning — the ranking is weaker, not wrong. |
| No supported language changed | Stop. Say which languages are supported. |
| An investigator returns prose, not JSON | `save_finding.py` strips a markdown fence automatically. If it still fails, record `--failed`. |
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
as it would if you had asked Claude to read those files directly. No network
calls, no telemetry, no external service.
