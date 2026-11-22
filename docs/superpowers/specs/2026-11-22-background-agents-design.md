# The scan skill works when agents return in the background: design

**Requirements:** [#97](https://github.com/tomstagl/thunderstruck/issues/97). The problem, stories, scope and acceptance criteria (AC-n) are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-22-background-agents.md`.
**Evidence:** `skills/thunderstruck-scan/SKILL.md` step 3 ("in the foreground … Their results return inline", "never use … background agents", the fallback `--usage` "with the token usage the `Agent` result reported") and step 6 (the skeptic batches, "foreground, waiting for each batch"); `scripts/save_finding.py:35-58` (`--usage` is optional; absent usage stays absent, never 0); `scripts/usage.py` (`partial` when a figure is missing, named in `missing`).

## 1. What is wrong

The skill is written for one environment: an `Agent` call returns the agent's result inline. In the reporter's environment (Claude Code 2.1.321) every call answered `Async agent launched successfully … You will be notified automatically when it completes`. The skill's sentences then have no referent: there is no result to save at "after each batch", and the usage "the `Agent` result reported" arrives later, in a second notification. One result was saved before its notification and the report shows `usage: partial`.

The skill cannot choose the mode: whether `Agent` runs in the foreground is the host's behaviour. So the skill has to say what to do in both, and the plugin must not be wrong in the one it did not expect.

## 2. Decisions

### 2.1 Two modes, one rule for when a batch is done

The skill names both cases after the launch:

- **Inline:** the call returns the result and its usage. Proceed as today.
- **Background:** the call returns a launch acknowledgement. The orchestrator ends its turn without another tool call (it does not poll, check files or sleep: the rule of step 3 stands). Each agent later produces a result message and a completion notification carrying the usage. **A batch is done when every agent of the batch has produced both**, and only then does the orchestrator run `--check`. The next batch starts after that, as it does inline.

**Why batches and not refilling slots as agents finish.** Refilling still respects the cap of four, and the reporter did it. A batch rule is one sentence, is the same in both modes and keeps "at most four in parallel" checkable by reading the skill. The cost is idle slots while the slowest agent of a batch finishes; the consumption work (#5) found no measurable effect on tokens, since idle waiting is free.

### 2.2 Usage comes from the completion notification, and its absence is stated

A fallback save takes `--usage` from the completion notification (or from the inline result). If, after every agent of the batch has notified, a figure is still not there, the save is made without `--usage`. The save script already accepts that; the report already counts the result as `partial` and `usage.json` names the agent in `missing`. The skill states this instead of leaving the orchestrator to guess, and says never to invent a figure.

### 2.3 The skill's prohibition becomes a prohibition on starting

"Never use … background agents" becomes: never *ask* for a background agent (no `run_in_background`), because the orchestrator must not be the one that makes the scan asynchronous. A host that runs them in the background anyway is handled by §2.1. Agent teams, `SendMessage` and `ListAgents` stay forbidden, and so does polling.

### 2.4 Skeptics, and the repair round

Step 6 (skeptics) and the investigator repair round of step 4 use the same two modes and the same rule; they refer to step 3's text instead of repeating it, so there is one wording to test.

### 2.5 Not designed here

Making the hook deliver results (#96, the likely reason it did nothing here). Recovering usage from transcripts without the orchestrator.

## 3. Degradation

A host that sends notifications out of order or drops one: the batch never completes, the turn ends with agents unfinished, and the skill's existing rule for a missing result applies after the user continues the session: `--check`, then the fallback save without usage. The skill says "if a notification does not arrive, run `--check` when the user continues, and treat the rest as missing". No timer is introduced.

## 4. Test strategy

The change is prose. Tests pin it, as `test_no_execution.py` and `test_skeptic_contract.py` pin other skill sentences:

- the skill names both modes and the rule "every agent of the batch has produced a result and a completion notification";
- it still forbids `run_in_background`, agent teams, `SendMessage`, `ListAgents` and polling;
- steps 4 and 6 point to step 3's rule rather than saying "foreground" alone;
- a fallback save without `--usage` is accepted and yields `usage: partial` with the agent named in `missing` (an executed test of the existing behaviour).
