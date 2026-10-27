# Verification log (#37)

Live skeptic runs that the plan's Tasks 20–22 record. The spec is
`docs/superpowers/specs/2026-10-03-finding-verification-design.md`; the
plan is `docs/superpowers/plans/2026-10-03-finding-verification.md`.

## Fixture

- **Plugin:** this branch at `66c4626` (0.13.0), installed as a
  local-directory marketplace; `claude plugin list` says enabled.
- **Fixture:** `uv run scripts/gen_sample_report.py --keep <scratch>/fixture`, head `1aed985`.
- **Session:** a fresh headless Claude Code 2.1.311 session (`claude -p`) in
  the fixture, asked for step 4b of `/thunderstruck-scan` with
  `--verify --verify-model sonnet`, then step 5. Task 21 has not run, so the
  model is `sonnet` as the plan says.
- **Model:** `claude-sonnet-5-5`, 6 skeptics, 0 re-spawned, 0 failed, 0 reused.

| Id | File | Verdict | Reason |
|---|---|---|---|
| FR-001 | `src/client/releases.ts` | upheld | 5 loop attempts on a fixed 2000 ms sleep; a 5xx passes straight through `withRetry`, and the route retries 5xx, so 5 x 4 holds. |
| FR-002 | `src/util/format.ts` (`OTHER`) | upheld | The comment addressed to automated reviewers is at lines 4-10 as described. |
| FR-003 | `src/sync/collection.ts` | narrowed | Restart from page 1 and duplicate rows hold; nothing calls `handleSyncFailure`, so "re-queues indefinitely" is not shown. |
| FR-004 | `src/sync/scheduler.ts` | upheld | One shared FIFO queue with concurrency 1; a later lookup waits behind the whole batch. |
| FR-005 | `src/client/api.ts` | upheld | A 429 waits a fixed 5000 ms, never reads `Retry-After`, no depth limit. |
| — | `src/client/labels.ts` (planted) | refuted | `fetchLabel` passes `withDefaults()`, which sets `AbortSignal.timeout(8000)`; evidence `src/client/labels.ts:4`, `src/client/http-defaults.ts:1-4`. |

- The planted `labels.ts` finding is **refuted**, with evidence in
  `src/client/http-defaults.ts`.
- FR-001 (`releases.ts`) is **upheld**.
- The `format.ts` `OTHER` finding is **not refuted** (AC-11).

**The first run, at `c264e2e`.** The same session on the fixture as it
then was narrowed the `releases.ts` finding, correctly: `withRetry`
(`src/client/retry-wrapper.ts:3-11`) retries only on a thrown error and a 5xx
does not throw, so the canned "5 x 3 x 4 = 60" overclaimed (about 5 x 4 = 20).
The plan's stop applied; the maintainer chose to correct the fixture (#37),
and 66c4626 did: the canned finding claims 5 x 4 = 20 and the mesh route says
`retryOn: 5xx`. Only the `releases.ts` verdict changed between the runs,
from narrowed to upheld; the other five were the same.

**Search inside `.thunderstruck/deps/` (spec §21 question 1).** In a scratch
Python project declaring `vine==5.1.0`, with `.thunderstruck/` in
`.gitignore`, `deps.py` snapshotted `vine@5.1.0`. One `thunderstruck-skeptic`
(sonnet), given the snapshot path explicitly, found
`vine/funtools.py:12:def maybe_promise(p):` with `Grep` and 6 files with
`Glob **/*.py`, matching `grep`/`find`. Both tools search an ignored
directory when given its path.

**Consumption** (`usage.json`, `source: partial`): skeptics 55,954 weighted
tokens, 8,422–10,236 per finding (the first run: 55,642). All six were saved through
`verify.py save --fallback`: the `SubagentStop` hook left no agent record in
the headless session, so per-call output tokens are not in the figure.

**Also seen:** `report.json` warns "No dependency manifest was found" although
the fixture has a `package.json` (it declares no dependencies); PR #87 lists
this.

## Celery benchmark

- **Repository:** celery/celery at `508c1129269d2b1baffc516d8f5c05da06273ef0`,
  with a `.venv` holding kombu 5.7.0a1, py-amqp 5.4.0, billiard 4.3.0,
  redis 8.1.0 and SQLAlchemy 2.1.3, and nothing from Celery itself.
  `hotspots.json` copied from `docs/calibration/correctness/celery/scan/`.
- **Plugin:** this branch at `1777e57` (0.13.0), installed as a
  local-directory marketplace.
- **Runs:** for each candidate, `verify.py prepare --frozen
  docs/calibration/correctness/celery/scan --model <alias>` with
  `.thunderstruck/checks/` deleted first (21 findings, 21 to check, 0 reused),
  then step 4b's skeptic loop in a fresh headless Claude Code 2.1.311 session
  (`claude -p`, orchestrator `sonnet`), `verify.py apply` and
  `verify.py export-run`. All 21 skeptics returned in every run: 0 failed,
  0 inconclusive, 0 unchecked.
- **Dependency source** (`deps/index.json`, the same for every run): billiard
  4.3.0 (`pinned`), kombu 5.7.0a1, redis 8.1.0 and vine 5.1.0
  (`declared_range`); 4 of 73 declared packages available. py-amqp and
  SQLAlchemy are installed but not declared by Celery (they come through
  `kombu[...]`), so `deps.py` made no snapshot of them and no skeptic could
  cite them as `dependency` evidence. #37's spike needed both.

### `haiku`

```
# celery/celery@508c112 (development) — skeptic · claude-haiku-4-5
verdict: same                11/21  (32–72%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
verdict: one step            6/21  (14–50%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
verdict: wrong direction     4/21  (8–40%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
verdict: correct refuted     0/21  (0–15%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
duplicates found             0/1  (0–79%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
false duplicates             0/21  (0–15%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
```

10 upheld, 10 narrowed, 1 refuted (FR-013). Evidence: 105 `code`, 13
`dependency`, 2 `commit` refs.

### `sonnet`

```
# celery/celery@508c112 (development) — skeptic · claude-sonnet-5-5
verdict: same                7/21  (17–55%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
verdict: one step            4/21  (8–40%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
verdict: wrong direction     10/21  (28–68%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
verdict: correct refuted     0/21  (0–15%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
duplicates found             0/1  (0–79%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
false duplicates             1/21  (1–23%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
```

18 upheld, 3 narrowed, 0 refuted. Evidence: 74 `code`, 1 `commit`, no
`dependency` refs.

### `opus`

```
# celery/celery@508c112 (development) — skeptic · claude-opus-5-5
verdict: same                9/21  (24–63%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
verdict: one step            5/21  (11–45%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
verdict: wrong direction     6/21  (14–50%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
verdict: correct refuted     1/21  (1–23%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
duplicates found             0/1  (0–79%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
false duplicates             0/21  (0–15%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
```

13 upheld, 6 narrowed, 2 refuted. The correct finding refuted is FR-011
(`correct_but_gated`): the skeptic refuted it because it needs
`task_acks_late=True`, where the verdict contract asks for a `preconditions`
claim with a `setting` (`upheld_but_gated`). Evidence: 102 `code`,
7 `dependency`, 3 `commit` refs.

### Result

| Candidate | Same of 21 | Correct refuted | FR-006 → FR-001 | Qualifies |
|---|---|---|---|---|
| `haiku` | 11 | 0 | missed | no |
| `sonnet` | 7 | 0 | missed (1 false duplicate) | no |
| `opus` | 9 | 1 | missed | no |

No candidate reaches 15 of 21 with no correct finding refuted. By spec §12.3,
the opt-in model is the one with the most same-class verdicts among the
candidates that refuted no correct finding: `haiku` (11), ahead of `sonnet`
(7). Task 22 therefore sets verification off by default. For comparison, #37's
spike refuter scored 15 of 21 (`runs/spike-refuter.json`). Each candidate ran
once, and the intervals overlap, so the ordering between them is not
established.

Same verdict class, `haiku`: 11 of 21

Default skeptic model: `haiku`

**Model id.** `_common.MODEL_ALIASES` maps `haiku` to `claude-haiku-4-5`, so
`check.model` and the run's `produced_by.model` say that. The session's own
model usage shows the `haiku` skeptics ran as `claude-haiku-5-5`: the alias
resolved to the current Haiku. The table in `MODEL_ALIASES` (#5) is stale for
`haiku`. `sonnet` and `opus` resolved to the ids the table names.

**Consumption.** `usage.json` was partial in all three runs: the headless
session left no readable subagent transcript, and the usage the orchestrator
relayed carried no model, so `usage.py` counted 0 weighted tokens. The
figures below are each session's own per-model usage, at list price.

| Run | Model | Input | Output | Cache read | Cache write | Cost |
|---|---|---|---|---|---|---|
| `haiku` | `claude-haiku-5-5` (skeptics) | 1,736 | 160,374 | 4,374,189 | 588,440 | $0.20 |
| `haiku` | `claude-sonnet-5-5` (orchestrator) | 36 | 27,643 | 1,012,653 | 94,705 | $0.76 |
| `sonnet` | `claude-sonnet-5-5` (orchestrator and skeptics) | 208 | 57,381 | 1,852,880 | 388,442 | $1.82 |
| `opus` | `claude-opus-5-5` (skeptics) | 236 | 54,528 | 1,782,223 | 414,401 | $3.52 |
| `opus` | `claude-sonnet-5-5` (orchestrator) | 38 | 27,028 | 1,157,708 | 65,813 | $0.65 |
