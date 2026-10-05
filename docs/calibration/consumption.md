# Consumption baseline and comparison

The baseline for #5 (Task 0), and the comparison after it (Task N, at the end). It records what one `/thunderstruck-scan` costs
before any of the consumption work lands, so Task N can be measured against
it on the same repository, commit and arguments. Two scans were run and
measured from Claude Code's own transcripts. The figures are token counts and
weighted tokens only; there are no money figures here.

| Repo | Commit | Scan arguments |
|---|---|---|
| celery/celery | `508c1129269d2b1baffc516d8f5c05da06273ef0` | `/thunderstruck-scan --since 2025-10-03` |

- Plugin: thunderstruck 0.9.0 at `284e4bd`, installed from a local checkout.
- Session model: `claude-opus-5-5`, for the orchestrator and every
  investigator, in both runs.
- Two runs, each in a fresh session with an empty `findings/`. Both ranked
  10 hotspots and spawned one investigator per hotspot.

## Method

A throwaway script (not committed, §9) read each scan's session transcript
and its `subagents/agent-*.jsonl`.

- **What counts.** Only entries with `type` `assistant`, a `message.usage`
  object and a `message.model` other than `<synthetic>`. Each API response is
  counted once: entries are deduplicated by `message.id`, falling back to
  `requestId`. No line in either run failed to parse as JSON.
- **Token types.** `input_tokens`; `cache_creation_input_tokens`, split into
  5-minute and 1-hour writes by `usage.cache_creation`'s
  `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`;
  `cache_read_input_tokens`; `output_tokens`. Every cache write in both runs
  stated its TTL, so the "TTL not stated" bucket is 0 throughout and is left
  out of the tables.
- **Weighted tokens** (spec §2.3): each token weighted by its published price
  relative to Claude Sonnet 5.5 base input = 1, per model and token type
  (Anthropic pricing page, read 2026-10-03). Every call in both runs was
  `claude-opus-5-5`, whose row is input 2, cache write 5m 2.5, cache write 1h 4,
  cache read 0.1, output 10. The Sonnet 5.5 row is 1, 1.25, 2, 0.1, 5.
- **Orchestrator window.** From `hotspots.json`'s `generated_at` up to and
  including the assistant entry that issues the `report.py` Bash command, and
  nothing after it. This is where Task N's `usage.py` window ends: before
  `report.py` and the step 6 summary. Within the window, any assistant turn
  answering a user message other than the scan command is excluded.
  Subagent hand-back notifications are part of the scan and stay in.
- **Investigators.** Every subagent whose `agentType` contains
  `thunderstruck-investigator`, unwindowed. Each is mapped to its hotspot by
  the `Analyse hotspot` line of its first prompt, and is a repair if that
  prompt says the hotspot failed validation. A second non-repair agent for
  the same hotspot would be a re-spawn.
- **Extra reads.** An investigator's `Read`, `Grep` and `Glob` calls, not
  counting the `Read` of its own bundle or of `catalog-brief.md`. The median
  and 90th percentile cover first-round agents only. The 90th percentile
  interpolates linearly between closest ranks.
- **From the saved outputs.** Bundle tokens are the sum of
  `tokens_estimated` over the entries of `bundles/index.json` that are not
  `cached`. The finding count is `report.json`'s `counts.findings`. The
  validation pass rate before the repair round is the `N/M valid` line of the
  first `validate.py` result in the orchestrator transcript, because the
  repair round overwrites `validation.json`.

Run 1 had 3 extra turns, and all 3 are excluded. During the scan and again
after it, the maintainer typed a shell command to copy the outputs, and the
model replied to each: 1 turn mid-scan and 2 after the scan. The window rule
also drops each run's step 6 summary turns. From `generated_at` to the last
entry, run 1 has 21 orchestrator calls and run 2 has 19; 17 of each are
counted.

## Tokens

All figures are tokens. *Weighted* uses the `claude-opus-5-5` row.

### Run 1

| Role | Model | Calls | Input | Cache write 5m | Cache write 1h | Cache read | Output | Weighted |
|---|---|---|---|---|---|---|---|---|
| Orchestrator | claude-opus-5-5 | 17 | 44 | 0 | 70,129 | 1,536,492 | 28,583 | 720,083.2 |
| Investigators | claude-opus-5-5 | 65 | 130 | 314,155 | 0 | 1,485,255 | 1,122 | 945,393.0 |
| **Total** | | 82 | | | | | | **1,665,476.2** |

### Run 2

| Role | Model | Calls | Input | Cache write 5m | Cache write 1h | Cache read | Output | Weighted |
|---|---|---|---|---|---|---|---|---|
| Orchestrator | claude-opus-5-5 | 17 | 40 | 0 | 68,535 | 1,468,817 | 28,136 | 702,461.7 |
| Investigators | claude-opus-5-5 | 67 | 134 | 310,784 | 0 | 1,507,801 | 942 | 937,428.1 |
| **Total** | | 84 | | | | | | **1,639,889.8** |

### Mean of the two runs

| Role | Model | Calls | Input | Cache write 5m | Cache write 1h | Cache read | Output | Weighted |
|---|---|---|---|---|---|---|---|---|
| Orchestrator | claude-opus-5-5 | 17 | 42 | 0 | 69,332 | 1,502,654.5 | 28,359.5 | 711,272.4 |
| Investigators | claude-opus-5-5 | 66 | 132 | 312,469.5 | 0 | 1,496,528 | 1,032 | 941,410.6 |
| **Total** | | 83 | | | | | | **1,652,683.0** |

The orchestrator writes its cache with a 1-hour TTL and the investigators
with a 5-minute one. In both roles cache reads make up most of the raw
tokens, while output is a large share of the orchestrator's weighted total
(about 40%) and a small share of the investigators'.

The ticket's target (a cut of at least 50%) puts Task N's mean weighted
total at **826,341.5 or less**. For scale: the same investigator tokens
weighted with the Sonnet 5.5 row, the new default, come to 545,531.7 instead
of 941,410.6. That is what the model pin alone would save if nothing else
changed; the rest of the cut has to come from the other changes.

## Agents and reads

| | Run 1 | Run 2 |
|---|---|---|
| Hotspots | 10 | 10 |
| Investigators (first round) | 10 | 10 |
| Agents per hotspot | 1 | 1 |
| Re-spawns | 0 | 0 |
| Repair-round agents | 0 | 0 |
| Validation before repair | 10/10 valid | 10/10 valid |
| Findings | 21 | 21 |
| Bundles (not cached) | 10 | 10 |
| Bundle tokens (`tokens_estimated`) | 50,076 | 50,076 |
| Mean weighted per investigator | 94,539.3 | 93,742.8 |

No hotspot failed validation, so neither run had a repair round. Both runs
bundled the same 10 hotspots at the same commit, so the bundle figures are
identical: a mean of 5,007.6 tokens per bundle.

Extra reads per investigator, first round:

| Hotspot | H01 | H02 | H03 | H04 | H05 | H06 | H07 | H08 | H09 | H10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Run 1 | 9 | 7 | 9 | 7 | 8 | 2 | 5 | 5 | 7 | 4 |
| Run 2 | 5 | 6 | 9 | 9 | 8 | 3 | 8 | 6 | 7 | 4 |

| | Median | 90th percentile | Max |
|---|---|---|---|
| Run 1 | 7 | 9 | 9 |
| Run 2 | 6.5 | 9 | 9 |
| Both runs pooled (20 agents) | 7 | 9 | 9 |

The 90th percentile is 9 per run and pooled, so the read cap is 9. Weighted with the Sonnet 5.5 row (the new default model, as the estimate
assumes), the mean investigator is 54,553.2 tokens against a mean bundle of
5,007.6 tokens: 10.9 per bundle token. With the row of the model they ran on
(`claude-opus-5-5`) it is 94,141.1, or 18.8 per bundle token.

## Task N: comparison after #5

Two scans with #5 merged, on the same repository, commit and arguments as
the baseline.

| Run | Session | `generated_at` |
|---|---|---|
| 1 | `95bd17ab-d880-4aa8-a7f4-f34959c84b74` | 2026-10-05T22:14:52+00:00 |
| 2 | `eab1131d-0c5e-4cc4-a52e-39ea15ecbab3` | 2026-10-05T22:21:32+00:00 |

- Plugin: thunderstruck 0.10.0 at `d22e182` (#69), installed from a local
  checkout. Claude Code 2.1.289.
- Session model: `claude-opus-5-5` at its default effort (`medium`), for the
  orchestrator. Investigators ran on `claude-sonnet-5-5`, the new default.
- Each run used a fresh session, started for the scan, and a fresh clone at
  `508c112` with the baseline's `.thunderstruck.toml` (service context
  disabled). `findings/` was empty. The scan command was the only prompt
  typed, so no turn is excluded from either window. Both ranked the same 10
  hotspots as the baseline, from the same 50,076 bundle tokens, and spawned
  one investigator per hotspot.
- Neither session compacted.

### Method

`usage.json` could not be used. In both runs it says `source: partial` with a
weighted total of 0 and `orchestrator: session transcript not readable`,
because the capture hook never ran (see *The capture hook* below), and
`usage.py` finds transcripts only through the records the hook writes.

Both runs were therefore measured as the baseline was: a throwaway script
read the session transcripts and `subagents/agent-*.jsonl` with the rules
under **Method** above. The same script, run on the baseline's run 2
transcript, reproduces that run's published figures exactly (17
orchestrator calls, 702,461.7 and 937,428.1 weighted), so the two sets of
figures are measured the same way.

### Tokens

*Weighted* uses each call's own model row: `claude-opus-5-5` for the
orchestrator, `claude-sonnet-5-5` for the investigators.

**Run 1**

| Role | Model | Calls | Input | Cache write 5m | Cache write 1h | Cache read | Output | Weighted |
|---|---|---|---|---|---|---|---|---|
| Orchestrator | claude-opus-5-5 | 20 | 52 | 0 | 55,319 | 1,578,370 | 21,381 | 593,027.0 |
| Investigators | claude-sonnet-5-5 | 34 | 68 | 222,570 | 0 | 490,292 | 2,838 | 341,499.5 |
| **Total** | | 54 | | | | | | **934,526.5** |

**Run 2**

| Role | Model | Calls | Input | Cache write 5m | Cache write 1h | Cache read | Output | Weighted |
|---|---|---|---|---|---|---|---|---|
| Orchestrator | claude-opus-5-5 | 20 | 52 | 0 | 52,265 | 1,541,136 | 19,704 | 560,317.6 |
| Investigators | claude-sonnet-5-5 | 33 | 66 | 190,302 | 0 | 485,150 | 2,805 | 300,483.6 |
| **Total** | | 53 | | | | | | **860,801.2** |

**Mean of the two runs, beside the baseline's mean**

| Role | Baseline | Task N | Change |
|---|---|---|---|
| Orchestrator | 711,272.4 | 576,672.3 | −18.9% |
| Investigators | 941,410.6 | 320,991.6 | −65.9% |
| **Total** | **1,652,683.0** | **897,663.9** | **−45.7%** |

The investigators' share fell by two thirds: Sonnet instead of Opus, and far
fewer extra reads (median 1 per investigator against 7). The orchestrator's
barely moved, and it is now most of the total. Part of it is the fallback
save: with no hook, the orchestrator re-typed every investigator's result
into `save_finding.py --fallback`. The calls that issued those saves produced
13,967 output tokens in run 1 and 9,419 in run 2, about 117,000 weighted on
average, before counting the cache reads of those turns. Without the
re-typing the mean would likely be under the target, but that was not
measured.

### Agents, reads and findings

| | Baseline (mean) | Run 1 | Run 2 |
|---|---|---|---|
| Investigators (first round) | 10 | 10 | 10 |
| Re-spawns | 0 | 0 | 0 |
| Repair-round agents | 0 | 0 | 0 |
| Fallback saves | — | 10 | 10 |
| Validation before repair | 10/10 valid | 10/10 valid | 10/10 valid |
| Findings | 21 | 18 | 15 |
| Weighted per investigator (Sonnet 5.5 row) | 54,553.2 | 34,150.0 | 30,048.3 |

Extra reads per investigator, first round:

| Hotspot | H01 | H02 | H03 | H04 | H05 | H06 | H07 | H08 | H09 | H10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Run 1 | 0 | 5 | 1 | 3 | 1 | 1 | 2 | 1 | 3 | 0 |
| Run 2 | 0 | 3 | 1 | 2 | 3 | 1 | 1 | 1 | 2 | 1 |

### Verdict

Against #5's success measures:

| Measure | Target | Result | |
|---|---|---|---|
| Weighted total | ≤ 826,341.5 (50% of baseline) | 897,663.9 (54.3%) | **fail** |
| Re-spawned investigators | 0 | 0 in both runs | pass |
| Finding count | down by at most 2 (1 per 5 hotspots): ≥ 19 | 18 and 15 | **fail** |
| Validation pass rate before repair | not lower than 10/10 | 10/10 in both runs | pass |

The finding count is blocking. Which change lowered it is not separated
here: the investigator model, the read cap and the shorter prompt all
changed at once. Per the plan, the failure goes to a follow-up ticket with
these numbers rather than being tuned in place.

### The capture hook

The `SubagentStop` hook did not run in either scan. Two causes, each enough
on its own, both shown on Claude Code 2.1.289 with a test project that
registered four matchers and spawned one investigator:

- **Matcher form.** Only `thunderstruck:thunderstruck-investigator` (and `*`)
  fired. `hooks/hooks.json` registers the bare `thunderstruck-investigator`,
  which never fired, and `plugin:thunderstruck:thunderstruck-investigator`
  did not fire either. This answers spec §11's open question: the matcher
  needs the plugin-name prefix, without `plugin:`.
- **Payload.** The payload carried `agent_id`, `agent_transcript_path`,
  `agent_type`, `background_tasks`, `cwd`, `effort`, `hook_event_name`,
  `permission_mode`, `prompt_id`, `session_crons`, `session_id`,
  `stop_hook_active` and `transcript_path`, but no `last_assistant_message`,
  which `capture_finding.py` needs. With the matcher fixed, every result
  would still fall back.

Both scans also spawned their investigators as background agents
(`requestShape: background` in each agent's metadata), although the skill
asks for foreground calls; the orchestrator said the harness did that. The
saves were all accounted for (10 fallback saves per run, counted in the
report), so no result was lost.

### Estimate

Weighted with the Sonnet 5.5 row, the mean investigator is 32,099.2 tokens
against a mean bundle of 5,007.6 tokens: 6.4 per bundle token (6.8 in run
1, 6.0 in run 2). `INVESTIGATOR_TOKENS_PER_BUNDLE_TOKEN` moves from 10.9 to
6.4. The read cap stays at 9: it comes from the baseline's reads, and no
investigator came near it here (maximum 5).

Investigator tokens per bundle token: 6.4
Read cap: 9
