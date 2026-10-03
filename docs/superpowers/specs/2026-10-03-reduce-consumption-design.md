# Reduce and measure scan consumption: design

**Requirements:** [#5](https://github.com/tomstagl/thunderstruck/issues/5). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-10-03-reduce-consumption.md`.

## 1. Architecture

```
signals.py         →  hotspots.json         generated_at marks the scan window start (exists today)
bundle.py          →  bundles/*.md          unchanged bytes; quieter stdout
investigator       →  (final message)       model: sonnet; reads less; terser JSON
capture_finding.py →  findings/<ID>.json    NEW · SubagentStop hook · stdlib only
                      agents/<ID>.json       which agents delivered, for usage.py
save_finding.py    →  --check, and today's --from as the fallback
validate.py        →  validation.json       quieter stdout
usage.py           →  usage.json            NEW · deterministic · reads Claude Code transcripts
report.py          →  report.md/.json       + Consumption
```

Three changes, each aimed at one cost the ticket measured:

| Cost in the ticket | Change |
|---|---|
| Results lost between agent and orchestrator, then re-spawned | A hook writes each result to disk; nothing model-driven sits in that path (§3) |
| The orchestrator's growing context: polling, reading bundles, re-typing findings | Explicit orchestration rules, quiet scripts, no re-typing (§4) |
| Investigators inheriting an expensive model and re-reading the bundle | `model: sonnet` with an override, tighter reading rules (§5) |

Measurement (§2) is what proves them. It is a deterministic script, so CLAUDE.md's governing rule holds: no model output decides a number.

## 2. Measurement

### 2.1 Sources

Claude Code writes one JSONL transcript per session, `<project dir>/<session id>.jsonl`, and one per subagent, `<project dir>/<session id>/subagents/agent-<agent id>.jsonl` (documented in the sub-agents docs). Every assistant entry carries `message.model`, `message.usage` and a `timestamp`.

`usage.py` never derives the project directory from the repository path. It takes the session transcript path from `agents/*.json` (§3.2), where the hook recorded the `transcript_path` it was given. That is the only way the script learns which session ran the scan.

### 2.2 What is counted

- **Orchestrator:** entries in the session transcript with `timestamp` ≥ `hotspots.json`'s `generated_at` and ≤ the moment `usage.py` runs. Earlier conversation in the same session is not charged to the scan. The skill's preflight and the step 6 summary fall outside the window; the Consumption line says "signals to report".
- **Investigators:** every subagent transcript whose `agent_id` appears in an `agents/<ID>.json` of this run. Each one lists every agent that delivered for that hotspot, and the hook marks every delivery after the first as `repair` or `respawn` (§3.2). An agent whose result never reached the hook leaves no record, so it is not counted; the hook is what removes that case.
- **Deduplication:** a single API response can appear as several transcript entries (content blocks are written separately with the same usage). Entries are deduplicated by `message.id`, falling back to `requestId`.
- Entries whose `message.model` is `<synthetic>` (Claude Code's locally generated messages, which made no API call) are skipped.
- An agent record counts only if its `bundle_hash` equals the current `bundles/index.json` entry's, so records left by an earlier scan in the same directory are ignored.
- Per entry: `input_tokens`, `cache_creation_input_tokens` (split into `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens` when present), `cache_read_input_tokens`, `output_tokens`.

### 2.3 Input-equivalent tokens

One number that tracks cost without naming a price:

| Token type | Weight |
|---|---|
| input | 1 |
| cache write, 5-minute | 1.25 |
| cache write, 1-hour | 2 |
| cache write, TTL not stated | 1.25 |
| cache read | 0.1 |
| output | 5 |

The ratios are Anthropic's published price ratios and are the same for Haiku, Sonnet and Opus. They live in one constant, `INPUT_EQUIVALENT_WEIGHTS` in `_common.py`, with a comment naming the pricing page. Cost in money is never computed.

### 2.4 `usage.json`

```json
{
  "schema": "thunderstruck.usage/v1",
  "source": "transcripts",
  "window": {"from": "2026-10-03T09:00:00+00:00", "to": "2026-10-03T09:21:40+00:00"},
  "orchestrator": {"calls": 41, "by_model": {"claude-opus-5-5": {"input": 120, "cache_write_5m": 0, "cache_write_1h": 90211, "cache_read": 1402220, "output": 9120, "input_equivalent": 366382}}},
  "investigators": {
    "agents": 10, "respawns": 0, "repairs": 1, "fallback_saves": 0,
    "by_model": {"claude-sonnet-5-5": {"...": "same shape"}},
    "by_hotspot": {"H01": {"agents": 1, "calls": 7, "input_equivalent": 41200}}
  },
  "total_input_equivalent": 811004,
  "missing": []
}
```

`missing` lists, in words, every part that could not be measured and why: `"orchestrator: session transcript not found at the recorded path"`, `"H04: no agent record, the hook did not fire"`.

### 2.5 Fallback (AC-2)

When a transcript cannot be read, or an entry has no recognisable `usage`, that part falls back:

- **An investigator without a readable transcript** uses the usage the orchestrator relayed from the `Agent` result: `save_finding.py --id H01 --usage '<json>'` stores whatever of `input_tokens`, `output_tokens`, `cache_creation_input_tokens` and `cache_read_input_tokens` the result carried in `agents/<ID>.json`. Fields that are absent stay absent, never zero.
- **The orchestrator without a readable transcript** is not measured. There is no fallback for it.
- `source` becomes `"partial"`, and `missing` says what is missing. If nothing could be read, `source` is `"unavailable"`.

The report never prints a total that silently leaves something out. With `source: partial` the Consumption line says which parts the total covers.

### 2.6 Report

`report.md` gets one section after Run warnings:

```
## Consumption

Signals to report: 811k input-equivalent tokens. Orchestrator 366k (claude-opus-5-5, 41 calls).
Investigators 445k across 10 agents (claude-sonnet-5-5), 1 repair, 0 re-spawns.
Input-equivalent weights: input 1, cache write 1.25 (5 min) or 2 (1 h), cache read 0.1, output 5.
```

The per-hotspot breakdown goes in `report.json` only. Model names go through `mdtext.code`. `report.py` uses `usage.json` only if its `window.from` equals this scan's `hotspots.json` `generated_at`; an older one is ignored with a run warning. Without a current `usage.json`, the section is omitted and `report.md` is byte-identical to today's, which keeps the sample report reproducible (§7).

### 2.7 Estimate in `--dry-run` (AC-3)

`bundle.py`'s summary always ends with an estimate line, so the skill's `--dry-run` (which stops after `bundle.py`) shows it:

```
estimate: ~450k input-equivalent tokens for 10 investigators, plus the orchestrator
  assumes ~45k per investigator per 8k-token bundle (calibration 2026-10, docs/calibration/consumption.md)
```

The per-bundle multiplier is one constant, `INVESTIGATOR_TOKENS_PER_BUNDLE_TOKEN`, set from Task 0 and Task N's measurements and cited to the calibration doc. The orchestrator's share is not estimated, because it depends on the session more than on the scan.

## 3. Saving results with a hook (AC-5, AC-6, AC-10)

### 3.1 Registration

`hooks/hooks.json` gains:

```json
"SubagentStop": [
  {
    "matcher": "thunderstruck-investigator",
    "hooks": [{"type": "command",
               "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/capture_finding.py\" 2>/dev/null || exit 0",
               "timeout": 5}]
  }
]
```

The docs' examples disagree on whether a plugin agent's name in the matcher carries the `plugin:<plugin>:` prefix. So the script also checks `agent_type` itself and does nothing unless it ends in `thunderstruck-investigator`.

### 3.2 Behaviour

1. Read the payload from stdin; give up silently if it is over 1 MB or not JSON.
2. Find the repository root: `cwd` or the nearest parent holding `.git` (a session may start in a subdirectory). Return unless `agent_type` ends in `thunderstruck-investigator` and `<root>/.thunderstruck/bundles/index.json` exists. `<root>` replaces `<cwd>` everywhere below.
3. Take `last_assistant_message`. Strip one markdown fence, as `save_finding.py` does. Parse it as JSON.
4. Read `hotspot_id`. Return unless it is the `id` of an entry in `bundles/index.json`. The destination path is built from the index entry, never from the payload, so repository content steering the investigator cannot make the hook write anywhere else.
5. If `findings/<ID>.json` exists with the same `bundle_hash`, it is a previous attempt from this run: move it to `agents/<ID>.attempt1.json` (overwriting an older one). This delivery is a `repair` if `validation.json` lists `<ID>` as invalid, otherwise a `respawn`.
6. Run the shared normalising and stamping (§3.4) and write `findings/<ID>.json` atomically (write to a temp file, then rename).
7. Write `bundle_hash` and append `{agent_id, session_id, transcript_path, stop_reason, kind}` (`kind` is `first`, `repair` or `respawn`) to the `agents` list in `agents/<ID>.json`. A record whose `bundle_hash` differs from the current one is replaced, not appended to.

The agent record and the first attempt live in `.thunderstruck/agents/`, not `findings/`: `validate.py` reads every `findings/*.json` as a finding.

If the message does not parse, or has no valid `hotspot_id`, nothing is written. The orchestrator's check (§4) then shows the hotspot as missing.

### 3.3 Constraints

The same as the guardrail's, and tested the same way:

- always exits 0;
- imports the stdlib and `finding_shape.py` only (an AST test, extended from the guardrail's);
- prints nothing, so nothing reaches the model;
- a no-op outside a scan;
- median runtime under 100 ms on the fixture's largest finding.

### 3.4 Shared module

`normalise()` and the bundle-hash stamping move out of `save_finding.py` into `scripts/finding_shape.py`, which imports the stdlib only. `save_finding.py` and `capture_finding.py` both call it, so a finding saved by the hook and one saved by hand are byte-identical. `save_finding.py`'s behaviour and output do not change.

### 3.5 Version floor

`last_assistant_message` and `agent_type` are recent hook fields. On a Claude Code without them the hook writes nothing, every hotspot shows as missing in the check, and the orchestrator uses the fallback (§4.2). The report counts `fallback_saves`, so the cost of the older version is visible rather than silent.

## 4. Orchestration (AC-6, AC-7)

### 4.1 Rules added to `SKILL.md` step 3

- Run each batch as up to four `Agent` calls in **one message**, foreground, with `subagent_type: thunderstruck-investigator` and `model: <the --model value>`. Their results return inline.
- Never use agent teams, `SendMessage`, `ListAgents` or background agents for investigators. Never poll.
- Never read a bundle, a finding file or `catalog-brief.md`. Read `bundles/index.json` for ids and paths, and the last lines of each script's output.
- After each batch, run `save_finding.py --check <ids>`.
- Never re-spawn an investigator. A hotspot gets one investigation and at most one repair round.

### 4.2 `save_finding.py --check`

For each id it prints `saved`, `missing` or `failed`. `saved` means `findings/<ID>.json` exists and its `bundle_hash` equals the current index entry's. A finding from an earlier run cannot count: a non-cached bundle's hash differs from any older finding's by definition.

For each `missing` id, the orchestrator saves the result it already holds with today's `save_finding.py --id <ID> --from <file>`, adding `--fallback` so `agents/<ID>.json` records it, and `--usage` with the `Agent` result's usage. If that also fails, it records `--failed`. That is the only path in which the orchestrator re-types a finding.

### 4.3 Repair round

Unchanged in substance: step 4 re-runs only invalid hotspots, once. The hook captures the repaired output and keeps the first attempt as `agents/<ID>.attempt1.json` (§3.2). Then `--check` and the same fallback apply.

### 4.4 Quieter scripts

Every line a script prints lands in the orchestrator's context and is paid for again on every later call.

- `bundle.py` prints the summary lines only (counts, cache reuse, re-checked findings, total tokens). Its per-bundle lines move behind `--verbose`.
- `validate.py` prints only invalid hotspots and their errors (the repair round needs them verbatim) plus the summary line. `✓` lines move behind `--verbose`.
- `signals.py` and `report.py` already end in a summary. They are unchanged.

Step 6 summarises from `report.json`'s summary block and the Consumption numbers, not from `report.md`.

### 4.5 Step 5

Step 5 runs `usage.py` immediately before `report.py`. A failure of `usage.py` never stops the report (§7).

### 4.6 `orchestration.md`

The Cost control section is rewritten with Task 0 and Task N's measured figures, replacing "~8k tokens per bundle, so `--top 10` is about 80k".

## 5. Investigator (AC-4, AC-8)

### 5.1 Model

- `agents/thunderstruck-investigator.md` frontmatter gets `model: sonnet`.
- The scan takes `--model haiku|sonnet|opus`, default `sonnet`, and passes it to each `Agent` call. A per-call model takes precedence over frontmatter, which takes precedence over `CLAUDE_CODE_SUBAGENT_MODEL` and the session's model (sub-agents docs). The frontmatter is what makes the default hold if a future orchestrator forgets to pass it.
- The repair round uses the same model.
- The model actually used is read from the transcript (`message.model`) and appears in the Consumption line. The finding file is not changed for it.

### 5.2 Reading

The prompt's "Your inputs" changes:

- Do not Read a file whose full source is already in the bundle. The bundle's source section states whether it holds the whole file or was trimmed (`bundle.py` already writes that note). Re-read a trimmed file only for the line range a lead needs.
- Up to **5** additional files instead of 10. Prefer `Grep` with a narrow pattern over a full `Read`.
- If five are not enough to settle a lead, say so in `confidence_rationale` (unchanged wording, new number).

The cap is a prompt rule, as today. Task 0's baseline reports the median and the 90th percentile of extra reads per investigator. If the 90th percentile is under 5, the cap stays at 5; otherwise the plan sets it to that 90th percentile, rounded up.

### 5.3 Output

The JSON shape does not change and `VALIDATION_RULES` does not move. The prompt adds: each evidence `note` is one short sentence, and `confidence_rationale` is at most two sentences.

### 5.4 What does not change

Bundle bytes, `bundle_hash`, the cache, the validator and the finding contract. A finding cached from before this change remains valid. `test_bundles_are_within_budget_and_deterministic` and `test_investigator_contract.py` are unchanged except where they quote the read cap.

## 6. Security

- `last_assistant_message` is model output that read repository content. The hook treats it as data: parsed as JSON, never executed, never used as a path. The destination comes from `bundles/index.json` (§3.2).
- The hook writes only inside `<cwd>/.thunderstruck/findings/` and `<cwd>/.thunderstruck/agents/`, and refuses to follow a symlink there (`O_NOFOLLOW` on the temp file, and checking the directory is not a link).
- `usage.py` reads transcripts, which contain the whole conversation. It extracts only `timestamp`, `message.id`, `requestId`, `message.model` and `message.usage`. Nothing else from a transcript is written anywhere, and `usage.json` contains no text from the conversation.
- `usage.py` reads only paths recorded by the hook, and only if they resolve under the Claude Code projects directory (`$CLAUDE_CONFIG_DIR/projects/`, by default `~/.claude/projects/`) and end in `.jsonl`.

## 7. Degradation

| Situation | Result |
|---|---|
| Hook fields missing (older Claude Code) | Every hotspot `missing` at the check; fallback saves; `fallback_saves` counted in the report |
| Hooks disabled | Same as above |
| A transcript unreadable or in an unknown format | That part falls back or is listed under `missing` (§2.5) |
| No agent record at all | `usage.json` has `source: unavailable`; the report says consumption was not measured, and why |
| Headless or CI run without transcripts | Same as above |
| `usage.py` itself fails | `report.py` runs anyway, without the section (it cannot tell a failure from a scan without measurement); the skill's step 6 summary says consumption was not measured, and why |
| Sample report generation | `gen_sample_report.py` writes no `usage.json`, so the sample has no Consumption section and stays byte-reproducible |

## 8. Test strategy

- **`capture_finding.py`**, from recorded hook payloads in `tests/fixtures/hook_payloads/`: a valid result; a fenced result; a `hotspot_id` not in the index; a path-shaped `hotspot_id`; another agent type; unparsable JSON; a payload over 1 MB; no `.thunderstruck/`; a second delivery moving the first to `agents/<ID>.attempt1.json`; no file other than `<ID>.json` ever written to `findings/`. Plus exit-0 on every one, stdlib-only by AST, and the latency budget.
- **Byte-identity**: the same result saved by the hook and by `save_finding.py --from` produces identical files.
- **`save_finding.py --check`**: saved, missing, a stale finding from an older bundle hash counting as missing, and `--failed`.
- **`usage.py`**, from synthetic transcripts in `tests/fixtures/transcripts/`: a normal scan; entries before the window excluded; duplicated entries counted once; a re-spawn; a repair; a missing subagent transcript falling back to relayed usage; an unknown entry shape; nothing readable. Plus: no conversation text in `usage.json`, and paths outside `~/.claude/projects/` refused.
- **Report**: the Consumption section for `transcripts`, `partial` and `unavailable`, and byte-identity with no `usage.json`.
- **Manifest**: `hooks.json` declares each event once; `plugin.json` still declares no `hooks`; CI's install check still loads the plugin.
- **Prompt**: `test_investigator_contract.py` asserts the frontmatter model and the read cap.
- **Quiet scripts**: `bundle.py` and `validate.py` default output has no per-hotspot success lines; `--verbose` restores them; errors are always printed.

## 9. Measurement tasks

These are what the ticket's success measures ask for. Both use one real repository, results recorded in `docs/calibration/consumption.md` with no organisation-specific names.

- **Task 0, baseline, before any change.** A default `--top 10` scan with the current plugin, from a fresh session, with an empty `findings/`. A throwaway script (not committed) applies §2.2 and §2.3 to the session's transcripts. Recorded: input-equivalent totals for orchestrator and investigators, by token type; agents per hotspot; extra reads per investigator (median, 90th percentile); finding count; validation pass rate.
- **Task N, after the build.** The same repository at the same commit, same arguments, fresh session, empty `findings/`, measured with `usage.py`. The same numbers, side by side, against the ticket's thresholds.

Runs vary. Each task records two scans, and the comparison uses the mean.

## 10. Decisions

| Decision | Rationale |
|---|---|
| A `SubagentStop` hook saves results | It removes the model from the path where results were lost, and the orchestrator no longer pays output tokens to re-type each finding. |
| The hook's destination comes from the index, never the payload | The payload is model output that read repository content. |
| A shared stdlib `finding_shape.py` | The hook has the guardrail's constraints, so it cannot import `_common`. One implementation keeps hook and manual saves byte-identical. |
| Transcripts first, relayed `Agent` usage as fallback | Transcripts are exact and include the orchestrator, the ticket's biggest cost. Relayed usage is a stable interface but misses the orchestrator. |
| The session located through the hook's `transcript_path` | Deriving Claude Code's project directory name from a path is guesswork. |
| Input-equivalent tokens, not money | The weights are stable across models. Prices change and depend on the plan. |
| `model: sonnet` in frontmatter and passed per call | The ticket's decision. Frontmatter is the backstop when the call omits it. |
| `--top 10` unchanged | The ticket's decision. Fewer hotspots is less coverage, not efficiency. |
| Usage kept out of findings and bundles | It is volatile; bundles must stay byte-identical. |
| Quieter scripts by default | Script output is re-charged on every later orchestrator call. |
| Consumption in `report.md` and `report.json`, not yet in `report.html` | The HTML page (#3) reads `report.json`, so showing it there later is a template change with no new data. |

## 11. Open design questions

- **Matcher form.** Whether `SubagentStop`'s matcher needs the `plugin:thunderstruck:` prefix. The script's own check makes this harmless either way. The plugin install check records which form fires.
- **Compaction.** A compacted session transcript still holds the pre-compaction entries in the docs' description, but this is not tested. If Task N's scan compacts, the plan checks the totals against the `Agent` results.
