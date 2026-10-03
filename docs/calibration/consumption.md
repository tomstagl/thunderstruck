# Consumption baseline

The baseline for #5 (Task 0). It records what one `/thunderstruck-scan` costs
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

Investigator tokens per bundle token: 10.9
Read cap: 9
