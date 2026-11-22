# Skeptic model id: the alias table, the weights and the recorded model agree

**Requirements:** [#100](https://github.com/tomstagl/thunderstruck/issues/100). The problem, stories, scope and acceptance criteria (AC-n) are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-22-skeptic-model-id.md`.
**Evidence:** `scripts/_common.py:36-48` (`TOKEN_WEIGHTS`, `MODEL_ALIASES`); `scripts/usage.py:133-146` (`_weights`, `weighted`) and `:150-166` (`tally`); `scripts/verify.py:735,790,860` (where the alias becomes `check.model` and `run.json`); `docs/calibration/verification.md` "Model id" and `docs/calibration/consumption.md` "With verification", which measured the mismatch.

## 1. What is wrong

`agents/thunderstruck-skeptic.md` says `model: haiku`. Claude Code resolves that alias to the current Haiku, which in every measured run (#37 Task 21 and 22, #57 Task 15) was `claude-haiku-5-5`. `MODEL_ALIASES["haiku"]` still says `claude-haiku-4-5`, so:

- `check.model` and `run.json` `model` name a model that did not run (`verify.py:735,790,860`).
- A skeptic saved from the orchestrator's relayed usage is weighted by the 4.5 row (`usage.py:170`).
- A skeptic measured from a transcript carries its real model, `claude-haiku-5-5`, which `TOKEN_WEIGHTS` has no row for. `usage.weighted` returns `None`, the tokens fall out of the total, and `missing` names the model.

## 2. Decisions

### 2.1 The alias follows the model that runs

`MODEL_ALIASES["haiku"]` becomes `claude-haiku-5-5`. `claude-haiku-4-5` stays in `TOKEN_WEIGHTS`: it is a real model, an explicit `--model claude-haiku-4-5` transcript can still contain it, and old run files name it.

**Why not resolve the alias from the transcript at report time.** The alias is the plugin's statement of what it asked for. `usage.py` already measures what ran, from the transcript. Making `check.model` depend on transcripts would put a transcript, which a headless or background run may not leave, on the verification path. Measured honestly, the two can differ, and `usage.json` shows it (§2.3).

### 2.2 Haiku 5.5 is priced by prompt length, so one row is not enough

Anthropic's pricing page (read 2026-11-22) lists Haiku 5.5 twice: up to 100,000 prompt tokens, and over. A request's prompt length counts all its input tokens including cache reads and cache writes; the higher price applies to the whole request, per request.

| USD per million | input | 5m write | 1h write | cache read | output |
|---|---|---|---|---|---|
| Haiku 5.5, up to 100,000 | 0.10 | 0.125 | 0.20 | 0.01 | 0.50 |
| Haiku 5.5, over 100,000 | 0.50 | 0.625 | 1 | 0.05 | 2.50 |
| Haiku 4.5 (the existing row's source) | 1 | 1.25 | 2 | 0.10 | 5 |

The table's unit is Claude Sonnet 5.5 base input = 1, which the existing rows make equal to 2 USD per million (Haiku 4.5's 0.5 is 1 / 2). Haiku 5.5's rows are therefore the dollar rows divided by 2:

- `claude-haiku-5-5`: `{"input": 0.05, "cache_write_5m": 0.0625, "cache_write_1h": 0.1, "cache_read": 0.005, "output": 0.25}`.
- Over 100,000: `{"input": 0.25, "cache_write_5m": 0.3125, "cache_write_1h": 0.5, "cache_read": 0.025, "output": 1.25}`.

`TOKEN_WEIGHTS` keeps its flat shape (the rows the pinned test and the orchestration table read). A new constant `LONG_PROMPT_WEIGHTS: dict[str, tuple[int, dict]]` holds `claude-haiku-5-5: (100_000, <over row>)`. A model without an entry is never tiered. `_common.weights_for(model, prompt_tokens)` returns the row to use; `usage.py` calls it and `bundle.py`'s estimate keeps reading the flat row (a bundle is far under the threshold).

### 2.3 Tiering needs a request, and only a transcript has one

`usage.read_entries` returns one entry per API response, so a transcript entry knows its prompt length: `input + cache_write_5m + cache_write_1h + cache_read` of that entry. `tally` weights each entry by the row `weights_for` picks and sums, instead of weighting per-model bucket sums. The bucket totals printed in `usage.json` do not change.

A relayed usage (a fallback save) is an agent's total over many requests. Its per-request prompt lengths are unknown. It is weighted with the up-to-100,000 row, and `missing` says so ("weighted at the up-to-100k rate; per-request lengths unknown"). That is a lower bound. The report already marks usage `partial` for any relayed figure, so no new status is needed.

**What this changes in `usage.json`.** `by_model[m].weighted` becomes the sum of per-request weights for a tiered model; for every other model it is the figure it was. A scan on a model with no tier entry is byte-identical.

### 2.4 Nothing may drift again

A test pins the agreement, in three directions:

1. Every `MODEL_ALIASES` value has a `TOKEN_WEIGHTS` row.
2. The skeptic agent's `model:` and the scan's `--model` default for skeptics are keys of `MODEL_ALIASES`.
3. The weights table in `skills/thunderstruck-scan/references/orchestration.md` equals `TOKEN_WEIGHTS`, and says which model is tiered, from `LONG_PROMPT_WEIGHTS`.

The existing `test_token_weights_equal_the_spec_table` reads the table in `2026-10-03-reduce-consumption-design.md` §2.3. That table gains the `claude-haiku-5-5` row, with a note pointing here, so the test needs no change of shape. This is the only edit to an older spec, and it adds a row.

## 3. Out of scope

- Detecting at report time that the model in the transcript differs from the alias, and warning. The mismatch this ticket found would then have been visible; it is a separate ticket if wanted.
- Rewriting figures in `docs/calibration/` that used the 4.5 row. They are measurements of a run and stay as recorded. One sentence beside the first of them says the row was replaced by #100.
- The frozen correctness runs (`docs/calibration/correctness/**/runs/*.json`) name `claude-haiku-4-5`. Their labels and totals are pinned by the baseline tests and are not edited.

## 4. Degradation

A model that is in no table is still counted raw and named in `missing`, as today. A malformed `LONG_PROMPT_WEIGHTS` is a bug caught by the pinning test, not handled at run time.

## 5. Test strategy

- Unit: `weights_for` at 100,000 and 100,001 prompt tokens, and for an untiered model.
- Unit: `tally` over two entries of `claude-haiku-5-5` (one each side of the threshold) gives the sum of the two rows, and the buckets are unchanged.
- A relayed haiku usage is weighted by the lower row and `missing` says so.
- `check.model` and `run.json` `model` say `claude-haiku-5-5` for `haiku`.
- The three pinning tests of §2.4.
- The sample report is regenerated; the suite's `--check` of it passes.

## 6. Decisions the builder may not change

The unit (Sonnet 5.5 input = 1 = 2 USD per million), the choice to keep the flat `TOKEN_WEIGHTS` shape, and the lower-bound rule for relayed usage.

## 7. Open design questions

Whether Claude Code's `haiku` alias will move again (to a later Haiku). The pinning test fails when `MODEL_ALIASES` and the table disagree, but it cannot know what Claude Code resolves. A later model needs its row added by hand.
