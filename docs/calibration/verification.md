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
  cite them as `dependency` evidence. #37's spike needed both. #101 adds
  the packages a declared package pulls in (`reached_via`); the "4 of 73"
  above is the figure measured before it.

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

## Defaults (#57, Task 15)

Measured plugin 0.14.0 at `3900888` against the same frozen Celery checkout
and dependency snapshots as above (4 of 73 available). Claude Code 2.1.327
loaded the local plugin; one Haiku skeptic ran per finding in fresh headless
sessions, at most four concurrent, with no re-spawns. All 21 returned: 9
upheld, 10 narrowed, 2 refuted, 0 inconclusive, 0 unchecked. The actual
skeptic model was `claude-haiku-5-5` in every session; the unmodified export
still reports `claude-haiku-4-5` because of the stale alias table (#100).

**AC-6 did not pass the Task 15 gate.** FR-015 was `refuted` and
`result_backend_max_retries` was `unconfirmed` (`contradicted`). The skeptic
also cited the registered `result_backend_always_retry` default and marked
it `different`, but emitted JSON `false` instead of the required string.
The resolver dropped that item, so the settled result has no confirmation
state or basis for it. Neither the raw verdict nor the exported result was
repaired or retried. No settled check carried the reason prefix “The check
upheld this claim, but it rests on a default no one confirmed”.

`benchmark.py --run` on the exported run:

```text
verdict: same                10/21  (28–68%)  celery/celery@508c112 · n=21 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read)
default matches effective    1/3  (6–79%)  celery/celery@508c112 · n=4 of 21 labelled findings · labels: 4 claude-fable-5-1 (4 executed)
default matches literal only 0/3  (0–56%)  celery/celery@508c112 · n=4 of 21 labelled findings · labels: 4 claude-fable-5-1 (4 executed)
default matches neither      0/3  (0–56%)  celery/celery@508c112 · n=4 of 21 labelled findings · labels: 4 claude-fable-5-1 (4 executed)
default not stated           2/3  (21–94%)  celery/celery@508c112 · n=4 of 21 labelled findings · labels: 4 claude-fable-5-1 (4 executed)
confirmed defaults that are not effective 0/1  (0–79%)  celery/celery@508c112 · n=4 of 21 labelled findings · labels: 4 claude-fable-5-1 (4 executed)
upheld on a default not stated at its effective value 0/1  (0–79%)  celery/celery@508c112 · n=4 of 21 labelled findings · labels: 4 claude-fable-5-1 (4 executed)
```

The scorer includes only findings whose export has preconditions, so its
three discriminating rows do not cover all five named in the plan. Of the
non-discriminating rows it scored, one matched the effective default and
four were not stated. The two zero counters apply to the scored rows only.
The Trigger.dev holdout was not rerun or revealed for this Celery-only task.

The table compares the sessions' own Haiku usage totals, excluding
orchestration (not an isolated measurement of the prompt change):

| Run | Input | Output | Cache read | Cache write |
|---|---:|---:|---:|---:|
| #37 Haiku baseline | 1,736 | 160,374 | 4,374,189 | 588,440 |
| #57 Task 15 | 478 | 201,568 | 5,623,221 | 636,797 |

### Deterministic replay

Reapplied all 21 saved responses unchanged after normalizing JSON scalar
values and counting omitted defaults. No model was rerun. FR-015 remained
`refuted`, and both disputed defaults settled as `unconfirmed` with basis
`contradicted`. The scorer now accounts for all five discriminating settings
(three match the effective value; two were not stated) and 36 other settings
(eight match the effective value; 28 were not stated).

```text
confirmed defaults that are not effective 0/8  (0–32%)  celery/celery@508c112 · n=16 of 21 labelled findings · labels: 16 claude-fable-5-1 (16 executed)
upheld on a default not stated at its effective value 1/7  (3–51%)  celery/celery@508c112 · n=16 of 21 labelled findings · labels: 16 claude-fable-5-1 (16 executed)
```

The latter counter now includes FR-002: the skeptic upheld the finding
without stating the effective `task_acks_on_timeout` default. The previous
scorer omitted this row along with other rows whose findings had no
exported defaults. The same-class verdict count remained 10/21. The gate
is still not met.

For comparison, rescoring the existing Trigger.dev pipeline capture (not a
new skeptic run, no label reveal) gave the following holdout totals:

```text
verdict: same                4/15  (11–52%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
confidence: exact            10/15  (42–85%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
upheld on a default not stated at its effective value 0/11  (0–26%)  triggerdotdev/trigger.dev@8491915 · n=11 of 15 labelled findings · labels: 11 claude-opus-5-5 (4 executed, 7 read)
```

The holdout capture has no discriminating default rows, so that last zero
is not evidence that the verifier handles those defaults correctly.

### Fresh measurement with the branch-condition check

After a read-only synthetic test confirmed that the skeptic traced a
configuration-gated branch to its registered default, ran all 21 frozen
Celery findings with plugin 0.14.0 at `06a2f59`. Same pinned checkout and
four dependency snapshots as before, one fresh headless session per finding,
up to four concurrent, no re-spawns. Every skeptic ran as `claude-haiku-5-5`;
the export still uses the stale alias table (#100). Results: 6 upheld, 13
narrowed, 1 refuted, 1 inconclusive, 0 unchecked.

**Task 15 passed.** FR-015 remained refuted; both disputed defaults settled
as `unconfirmed` (`contradicted`). FR-002 was narrowed after the skeptic
identified the effective `task_acks_on_timeout` default. All five
discriminating settings were counted: four matched and one was not stated.
Of the 36 non-discriminating settings, 13 matched and 23 were not stated.
Neither wrong-default counter was nonzero. FR-006 (label: `partially_correct`)
was the one proposed uphold settled as inconclusive because its retry-policy
default reference did not resolve.

```text
verdict: same                11/20  (34–74%)  celery/celery@508c112 · n=20 of 21 labelled findings · labels: 20 claude-fable-5-1 (19 executed, 1 read)
default matches effective    4/5  (38–96%)  celery/celery@508c112 · n=16 of 21 labelled findings · labels: 16 claude-fable-5-1 (16 executed)
default matches literal only 0/5  (0–43%)  celery/celery@508c112 · n=16 of 21 labelled findings · labels: 16 claude-fable-5-1 (16 executed)
default matches neither      0/5  (0–43%)  celery/celery@508c112 · n=16 of 21 labelled findings · labels: 16 claude-fable-5-1 (16 executed)
default not stated           1/5  (4–62%)  celery/celery@508c112 · n=16 of 21 labelled findings · labels: 16 claude-fable-5-1 (16 executed)
confirmed defaults that are not effective 0/8  (0–32%)  celery/celery@508c112 · n=16 of 21 labelled findings · labels: 16 claude-fable-5-1 (16 executed)
upheld on a default not stated at its effective value 0/4  (0–49%)  celery/celery@508c112 · n=16 of 21 labelled findings · labels: 16 claude-fable-5-1 (16 executed)
```

The verdict scorer excludes the inconclusive result; counted against the
whole frozen set the same-class count is 11/21. The existing Trigger.dev
holdout totals above are a rescore of the captured run, not a measurement of
the changed skeptic prompt.

| Run | Input | Output | Cache read | Cache write |
|---|---:|---:|---:|---:|
| #37 Haiku baseline | 1,736 | 160,374 | 4,374,189 | 588,440 |
| #57 with branch-condition check | 446 | 207,426 | 5,498,841 | 598,863 |

## Missing gate setting (#144)

Spec: `docs/superpowers/specs/2026-11-25-missing-gate-setting-design.md` §7.
The prediction was committed at `0547ded` before any run was scored.

**What ships is the *before* prompt** with the `verify.py` all twelve runs were
settled with. The *after* prompt (`e268b57`, pull request #148) was taken out
again because of the false marks below; #144's AC-1 moved to #150.

- **Arms.** *Before*: plugin 0.20.0 at `0547ded`, whose skeptic prompt is
  `main`'s. *After*: `c5b6b7a`. What a skeptic is given differs in
  `agents/thunderstruck-skeptic.md` alone. All twelve runs are settled with
  the `verify.py` of `c5b6b7a`.
- **Runs.** Three per arm on Celery (`508c1129`, 21 findings) and on the
  holdout (`84919159`, 15 findings), 2026-11-25, Claude Code 2.1.332, each a
  fresh headless session (orchestrator `claude-sonnet-5-5`) that ran step 4b's
  skeptic loop on `verify.py prepare --frozen`. One skeptic per finding, none
  re-spawned, every skeptic on `claude-haiku-5-5`. Runs of a set share the
  frozen scan's `generated_at`, so a run is named by its session and start.
- **Dependency source.** Celery: 8 of 84 packages available (amqp 5.4.0,
  billiard 4.3.0, kombu 5.7.0a1, packaging 26.3, pyyaml 6.0.3, redis 8.1.0,
  SQLAlchemy 2.1.3, vine 5.1.0), four of them reached (#101). Holdout: 0 of
  18. Not comparable with the runs above: the prompt, the plugin and the
  dependency source all changed since 0.14.0.
- **Cost** at list price, orchestrator and skeptics: about $11 for the twelve runs.

| Run | Session | Started (UTC) | Same | Correct refuted | `high` above deserved | Gated verdicts | `preconditions` claims | naming a usable setting |
|---|---|---|---:|---:|---:|---:|---:|---:|
| before 1 | `ca9ca7f7` | 07:55 | 10/21 | 1 | 0 | 0 | 5 | 0 |
| before 2 | `5f904ab8` | 08:07 | 9/21 | 0 | 0 | 0 | 5 | 0 |
| before 3 | `6a5c83f8` | 08:18 | 8/21 | 1 | 0 | 0 | 2 | 0 |
| after 1 | `fe6abd10` | 08:30 | 8/21 | 0 | 0 | 0 | 4 | 4 |
| after 2 | `4e7bc467` | 08:46 | 10/21 | 0 | 0 | 0 | 3 | 3 |
| after 3 | `6ca80128` | 08:57 | 11/21 | 0 | 0 | 1 | 6 | 4 |

A finding without a verdict counts as not agreeing. Labels: 21
`claude-fable-5-1` (20 executed, 1 read). Exports:
`correctness/celery/runs/missing-gate-{before,after}-{1,2,3}.json`.

| Arm, set | Mean same | Range | 95% Wilson of the mean | Correct refuted | Gated | naming a setting |
|---|---|---|---|---|---|---|
| before, Celery | 9.00/21 | 8–10 | 24.5–63.5% | 2 | 0 | 0 of 12 |
| after, Celery | 9.67/21 | 8–11 | 27.0–66.3% | 0 | 1 | 11 of 13 |
| before, holdout | 7.33/15 | 6–8 | 26.5–71.7% | 2 | 0 | 0 of 5 |
| after, holdout | 7.67/15 | 6–10 | 28.3–73.5% | 0 | 1 | 6 of 9 |

The holdout is totals only; nothing was revealed. `high` above deserved is 0
in all twelve runs. Holdout labels: 15 `claude-opus-5-5` (8 executed, 7 read).

**Against the prediction.** (1) and (2) held: the mean moved by +0.67, inside
the spread of either arm, and is below 15. (3) held as worded, and the wording
was too weak: the one gated Celery verdict is on FR-003, labelled
`partially_correct`, so it scores *wrong direction*. 0 of the 4 findings
labelled `correct_but_gated` was scored as gated in any of the six runs. (4)
predicted nothing. The fall in *correct refuted* is not shown to be an effect
at these counts.

**What the marks were.** Any `preconditions` claim with a setting on a narrowed
finding marks the whole finding (#37 §14). The three after runs marked nine
Celery findings:

| Finding | Label | Runs | Setting the check named | Needed, per the executed review |
|---|---|---:|---|---|
| FR-011 | `correct_but_gated` | 2 | `task_acks_late` | yes |
| FR-015 | `wrong` | 3 | `result_backend_always_retry` | yes: wrong on defaults, partly right when opted in |
| FR-003 | `partially_correct` | 1 | `worker_deduplicate_successful_tasks` | yes |
| FR-014 | `correct` | 3 | `result_backend_always_retry` | **no** |

FR-014 is a false mark in every run. Its failure happens on defaults, and the
check's own `holds` says so (run 1: "On default settings, every task result
write … fails"). The setting belongs to one refuted detail, a retry count, not
to the failure. The report would have listed a correct default-path finding after the
gated ones and said it needs a setting changed. With the *before* prompt no check
does that, because none names a setting. The marks cannot be broken down
on the holdout without revealing it.

**`gate_problem`.** Two of 13 kept claims (FR-007 and FR-010, run 3) named no
setting; both checks say so, and neither finding is marked by its check.

**#54 AC-2 is not met, by either prompt.** With the prompt that ships, the mean
same-class count is 9.00 of 21, its interval starts at 24.5%, not 50%, and a
correct finding is refuted in two of the three runs. With the *after* prompt no
correct finding is refuted, but the mean is 9.67 and the interval starts at
27.0%. No `high` is above its deserved confidence in any run. Verification is
also off by default, so a default scan gives no verdict at all.

**Saved results.** On this Claude Code a subagent returns through a
`SubagentHandback` call. The capture hook saved 39 of 216 results (Celery 31 of
126, the holdout 8 of 90) and logged `no_message` in `hook-trace.jsonl` for the
rest; the orchestrator retyped those 177. In the Celery transcripts the 31 are
exactly the skeptics that wrote the result as text before handing it back.
Compared with the skeptics' own messages, 9 of 216 saved results differ (1
before, 8 after), in `evidence` notes, `guarantees`, `not_checked` or evidence
indexes. Settling all twelve runs from the skeptics' own messages gives the same
table.
