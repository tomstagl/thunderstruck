# Skeptic model id Implementation Plan

> For agentic workers: build task by task, test first. Steps use checkbox (`- [x]`) syntax.

**Ticket:** #100. **Spec:** `docs/superpowers/specs/2026-11-22-skeptic-model-id-design.md`. Every task names the `AC-n` of the ticket it satisfies. A design change goes in the spec first.

**Goal:** `MODEL_ALIASES`, `TOKEN_WEIGHTS`, the recorded model and the documented table agree with the model the skeptics run as, and a test keeps them agreeing.

**Branch:** named by whoever builds it; the agent uses `agent/100-skeptic-model-id`. Stage explicit paths only, never `git add tests/`.

**Tests, whole suite:** the command at the top of CLAUDE.md "Commands". One file: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_usage.py -q`.

---

## Task 0: anchors (no AC)

- [x] Read the spec. Confirm in the tree: `_common.py` has `TOKEN_WEIGHTS` and `MODEL_ALIASES` with `haiku -> claude-haiku-4-5`; `usage.py` has `_weights`, `weighted`, `tally`; `verify.py` writes `c.MODEL_ALIASES.get(plan["model"], …)` at three places; `agents/thunderstruck-skeptic.md` says `model: haiku`.
- [x] Open the pricing page `https://platform.claude.com/docs/en/about-claude/pricing`. If Haiku 5.5's rows differ from spec §2.2, stop and report which: the spec's numbers are the design and a changed price changes them.
- [x] Confirm `grep -n "claude-haiku-5-5" scripts/` finds nothing. If something already handles it, stop: the ticket is partly done.
- [x] Run the usage tests and note they pass: `tests/test_usage.py`.

## Task 1: the tiered weights table (AC-2, AC-3)

**Files:** `scripts/_common.py`, `tests/test_usage.py`.

- [x] Write the failing test in `tests/test_usage.py`:

```python
def test_weights_for_switches_tier_above_100k_prompt_tokens():
    low = c.weights_for("claude-haiku-5-5", 100_000)
    high = c.weights_for("claude-haiku-5-5", 100_001)
    assert low["input"] == 0.05 and low["output"] == 0.25
    assert high["input"] == 0.25 and high["output"] == 1.25
    assert c.weights_for("claude-sonnet-5-5", 10_000_000) == c.TOKEN_WEIGHTS["claude-sonnet-5-5"]
    assert c.weights_for("claude-unknown-1", 5) is None
```

- [x] Run it: fails with `module '_common' has no attribute 'weights_for'`.
- [x] In `_common.py` add the `claude-haiku-5-5` row to `TOKEN_WEIGHTS` (spec §2.2's up-to-100k row), then:

```python
# Haiku 5.5 is priced by prompt length (spec 2026-11-22 §2.2): a request whose
# prompt (all input tokens, cache reads and writes included) is over the
# threshold pays the second row for the whole request.
LONG_PROMPT_WEIGHTS: dict[str, tuple[int, dict[str, float]]] = {
    "claude-haiku-5-5": (100_000, {"input": 0.25, "cache_write_5m": 0.3125,
                                   "cache_write_1h": 0.5, "cache_read": 0.025,
                                   "output": 1.25}),
}


def weights_for(model: str, prompt_tokens: int) -> dict[str, float] | None:
    """The weights row one request of `model` is priced at, or None if unknown."""
    base = TOKEN_WEIGHTS.get(model)
    tier = LONG_PROMPT_WEIGHTS.get(model)
    if base is not None and tier is not None and prompt_tokens > tier[0]:
        return tier[1]
    return base
```

- [x] Run the test: passes. Commit `_common.py` and `tests/test_usage.py` by path. Body: `AC-3`, `Task: 1`, the red line.

## Task 2: usage weights each request by its tier (AC-2, AC-3)

**Files:** `scripts/usage.py`, `tests/test_usage.py`.

- [x] Write failing tests:

```python
def test_a_tiered_model_is_weighted_per_request(scan):
    _jsonl(scan["subagents"] / "agent-t1.jsonl", [
        _assistant("t1", "2026-10-03T09:10:00Z", {"input_tokens": 1000}, "claude-haiku-5-5"),
        _assistant("t2", "2026-10-03T09:11:00Z",
                   {"input_tokens": 1000, "cache_read_input_tokens": 100_000}, "claude-haiku-5-5")])
    entries = usage.read_entries(scan["subagents"] / "agent-t1.jsonl")
    doc = usage.tally(entries)
    row = doc["by_model"]["claude-haiku-5-5"]
    # t1 at the low row, t2 (prompt 101,000) at the high row
    assert row["weighted"] == round(0.05 * 1000 + 0.25 * 1000 + 0.025 * 100_000)
    assert row["input"] == 2000 and row["cache_read"] == 100_000


def test_a_relayed_haiku_is_weighted_low_and_says_so(scan):
    _skeptic(scan, "dddddddddddd", [{"kind": "fallback"}], fallback=True,
             relayed_usage={"input_tokens": 1000, "model": "haiku"})
    doc = _build(scan)
    assert doc["skeptics"]["by_model"]["claude-haiku-5-5"]["weighted"] == 50
    assert any("up-to-100k" in m for m in doc["missing"])
```

- [x] Run them: fail (`KeyError`/no weights).
- [x] In `usage.py` replace `_weights`/`weighted`/`tally` with a per-tier grouping: for each entry compute `b = split(e["usage"])`, `prompt = b["input"] + b["cache_write_5m"] + b["cache_write_1h"] + b["cache_read"]`, `row = c.weights_for(model, prompt)`; group bucket sums by `(model, id(row))`, weight each group with its row, round once per model after summing the groups' unrounded values. A model with no row (`None`) keeps today's behaviour: weight `None`, named in `missing`. Keep `weighted(model, buckets)` for the callers that exist, now using `c.weights_for(model, 0)` and the dated-id strip.
- [x] A relayed entry is marked `{"relayed": True}` by `_relayed`; `tally`'s caller (`_measure`) appends to `missing` the line `"<label>: relayed usage weighted at the up-to-100k rate; per-request lengths unknown"` only when the model is in `c.LONG_PROMPT_WEIGHTS`.
- [x] Both tests pass, and every test already in `tests/test_usage.py` still passes unchanged (an untiered model is byte-identical).
- [x] Commit `scripts/usage.py` and `tests/test_usage.py`. Body: `AC-2, AC-3`, `Task: 2`, the red line.

## Task 3: the alias and the recorded model (AC-1)

**Files:** `scripts/_common.py`, `tests/test_verification.py`.

- [x] Write the failing test (beside `test_verification.py:286`):

```python
def test_the_haiku_alias_names_the_model_that_runs():
    assert c.MODEL_ALIASES["haiku"] == "claude-haiku-5-5"
```

and leave the test at `:286` as it is (it reads `MODEL_ALIASES`, so it follows). The test at `:699`, `test_the_default_skeptic_model_is_the_measured_one`, compares the frozen `skeptic-haiku.json` run, which is not edited (spec §2.5): change its last assertion to `assert run["produced_by"]["model"] == "claude-haiku-4-5"`, with a comment that a frozen run records the model it ran as when made. The alias is pinned by the test above, not by this one.
- [x] Run: fails with `'claude-haiku-4-5' == 'claude-haiku-5-5'`.
- [x] Change `MODEL_ALIASES["haiku"]` to `"claude-haiku-5-5"`.
- [x] Run `tests/test_verification.py tests/test_usage.py tests/test_report_consumption.py`: the 4.5 literals in those tests are arbitrary model strings and keep passing. `tests/test_usage.py::test_a_skeptic_fallback_save_is_weighted_by_its_alias` asserts the alias: read its model from `c.MODEL_ALIASES["haiku"]` and its weighted figure as 50 (the Haiku 5.5 up-to-100k input row, 0.05 × 1000), never a literal id. The one test allowed a literal is the one at `:699`, above, which asserts a recorded fact, not the alias.
- [x] Commit by path. Body: `AC-1`, `Task: 3`, the red line.

## Task 4: the pinning tests and the documented table (AC-4)

**Files:** `tests/test_model_ids.py` (new), `skills/thunderstruck-scan/references/orchestration.md`, `docs/superpowers/specs/2026-10-03-reduce-consumption-design.md`.

- [x] Write `tests/test_model_ids.py` with three tests (spec §2.4): every `MODEL_ALIASES` value is a `TOKEN_WEIGHTS` key; the skeptic agent's front-matter `model:` and `verify.py`'s `--model` default are `MODEL_ALIASES` keys; the table in `orchestration.md` equals `TOKEN_WEIGHTS` and contains a line naming each key of `LONG_PROMPT_WEIGHTS` with its threshold. Use the table-parsing code of `test_token_weights_equal_the_spec_table` for the first parse.
- [x] Run: the orchestration test fails (no 5.5 row).
- [x] Add the `claude-haiku-5-5` row (`0.05 | 0.0625 | 0.1 | 0.005 | 0.25`) to the table in `orchestration.md`, and under it one sentence: "`claude-haiku-5-5` is priced by prompt length: a request over 100,000 prompt tokens (cache reads and writes included) is weighted `0.25 | 0.3125 | 0.5 | 0.025 | 1.25`, as a whole." Add the same row to §2.3 of `2026-10-03-reduce-consumption-design.md` with the note "added by #100; see 2026-11-22-skeptic-model-id-design.md". `test_token_weights_equal_the_spec_table` must pass.
- [x] Put one sentence in `docs/calibration/consumption.md` after the "Skeptic model" bullet (around line 310): "The alias table was corrected by #100; the figures here keep the 4.5 row they were weighted with."
- [x] Run the three new tests, `tests/test_usage.py`, and `tests/test_docs*` if present. Commit these paths explicitly. Body: `AC-4`, `Task: 4`.

## Task 5: generated files, changelog (AC-5)

- [x] Run `uv run scripts/gen_sample_report.py`, then `--check`; `uv run scripts/gen_catalog_docs.py --check`. Review the diff of `examples/`: only the model name may change. Anything else: stop.
- [x] Do not bump the version (maintainer's call, 2026-11-22: versions are bumped at release, not per ticket). Add under an `## Unreleased` heading in `CHANGELOG.md`, `### Fixed`: "The skeptic's model is `claude-haiku-5-5` where it runs as that, so `check.model` and `run.json` name it and its tokens are weighted, by prompt length (#100)."
- [x] Run the full suite (CLAUDE.md command, with the browser tests as in CI), `uv run scripts/validate_plugin.py`, and the plugin install check. All must pass before any push.
- [x] Commit by explicit path. Body: `AC-5`, `Task: 5`.

## Task 6: finish (AC-1 to AC-5)

- [ ] Open the PR "Refs/Closes #100", with the table: each AC and the commit and test that satisfy it. State that no model was run and that the 4.5 price row is unchanged.
