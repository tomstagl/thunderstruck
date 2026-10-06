# Finding correctness: Celery ground truth

A scan's findings were checked one by one against what the code actually
does. This log records that ground truth and three spikes run against it,
because they decided how the work on finding correctness is split. Everything
here is evidence; the requirements live in the tickets it links.

| | |
|---|---|
| Repository | [celery/celery](https://github.com/celery/celery) at `508c1129269d2b1baffc516d8f5c05da06273ef0` (BSD-3-Clause) |
| Scan | `/thunderstruck-scan --top 10 --since 12m`, 10 hotspots, 21 findings, all valid |
| Ground truth | A per-finding review by Claude Fable 5.1, 20 of 21 verdicts established by executing a reproduction (fakeredis behind a stalling proxy, the memory transport, a real prefork worker, PostgreSQL 16.2) |
| Files | [`correctness/celery/`](correctness/celery/) |

Local absolute paths in the copied files were replaced with `<celery>`,
`<thunderstruck>`, `<site-packages>` and `<reviewer-scratchpad>`. Nothing
else was edited.

## Files

| Path | What it is |
|---|---|
| `celery/scan/` | The scan as produced: `report.json`, `hotspots.json`, `validation.json`, `catalog-brief.md`, every bundle the investigators read, every findings file |
| `celery/verdicts.json` | The ground truth: per finding a verdict, how it was established, the refuting fact and whether it was in the bundle, preconditions with literal and effective defaults, each cited commit's actual role, claimed and deserved confidence, whether `how_to_verify` reproduced, duplicates, detector-lead verdicts; plus the defects the scan missed |
| `celery/spikes/refute/` | Two blind read-only refuters (Spike 2) |
| `celery/spikes/xray/` | Function-level hotspot X-ray, coupling, code age and confidence rules (Spikes 1 and 3). `CELERY_REPO=<a celery checkout at 508c112> uv run --with lizard python xray.py --full`, then `analyze.py`, rebuilds `results.json`, except the churn-only control (rank C), which the spike computed outside these scripts. Re-running was checked: every other value is identical |
| `celery/labels.json`, `celery/runs/` | The same ground truth normalised for `scripts/benchmark.py`, and the two baseline inputs; see [`correctness/labelling.md`](correctness/labelling.md) |

## Ground truth

| Verdict | Findings |
|---|---|
| correct | 5: FR-004, 014, 016, 017, 019 |
| correct, gated behind a non-default setting | 4: FR-002, 007, 011, 018 |
| partially correct | 10 |
| wrong | 2: FR-013, FR-015 |

- 13 of 21 confidences were wrong: 6 too high (FR-001, 003, 006, 009, 013, 015), 7 too low.
- 4 `how_to_verify` recipes did not reproduce what they predicted.
- FR-006 is the same defect as FR-001, found from the other hotspot.
- 3 defects were missed, the largest being that the database result backend
  does not retry at all on defaults, contrary to its code comment and docs.

Where the errors came from, by the reviewer's own account of each:

| Cause | Findings |
|---|---|
| The excerpt showed the most complex function, not the code that mattered | FR-001, 006, 021 |
| Bundles carry commit subjects only, and trim diffs mid-hunk | FR-012, 013 |
| `high` granted for a `[fix]` commit that wrote the code or added the mitigation | FR-001, 003 |
| Required narrative fields filled with a story | FR-021, and the overstatements in FR-001, 005, 017 |
| Dependency source needed and out of reach | FR-013, 018, parts of 001, 002, 003 |
| Literal default trusted over the effective one | FR-015 |
| The fact was in the bundle or one read away and was not checked | FR-005, 008, 009, 010, 020 |

9 of the 12 refuting facts were outside the bundle. The correct findings share
one property: their whole code path was inside the bundle excerpt.

## Spike 1: hotspot X-ray (not supported)

Hypothesis, after Tornhill's *Your Code as a Crime Scene*: ranking functions
inside a hotspot file by their own churn × complexity, plus function-level
temporal coupling, would have put the cited and refuting code in front of the
investigator.

| Excerpt, same line budget | Refuting facts covered (of 9 in the hotspot file) |
|---|---|
| Today: the most complex function | 4 |
| X-ray, churn × complexity | 4 |
| X-ray, fix-weighted | 3 |
| X-ray, full history | 3 |

On H02 complexity still hands 170 of 194 lines to `RedisBackend.__init__`;
the block every H02 finding lives in only wins with complexity removed, and
that loses other findings' code. Budgets of 70–87 lines (H04, H07, H08) hold
no path under any ranking. Function-level coupling found 2 of 28 targets, each
on one shared commit tied with 4–13 others. Code age flags long-standing
deliberate behaviour weakly (the four oldest findings are documented or
opt-in, n=4) and says nothing about correctness (ρ = −0.01).

File-level hotspots pointed at real problems. Function-level ranking does not
choose better excerpts; the line budget is the constraint.

## Spike 2: blind read-only refutation (supported)

Two refuters that never saw `verdicts.json` tried to disprove every finding by
reading: the repository, full commit messages, and dependency source (kombu
5.7.0a1, py-amqp 5.4.0, billiard 4.3.0, redis-py 8.1.0, SQLAlchemy 2.1.3). They
ran no Celery code.

| | Findings |
|---|---|
| Same verdict class as the executed ground truth | 15 of 21 |
| One step off (gated vs plain, narrowed vs correct) | 4 |
| Wrong direction | 2: FR-003, FR-009 upheld |
| Duplicate found unprompted | FR-006 → FR-001 |
| Correct finding refuted | 0 |

8 refutations needed dependency source and 2 needed a full commit message;
each refuter read 4–10 files per finding and used about 220–260k tokens for
10–11 findings.

Effective defaults are the weak spot. The two refuters read the same two lines
of `celery/backends/database/__init__.py` and concluded opposite things: one
that `conf.get('result_backend_always_retry', True)` returns the registered
default `False`, the other that the backend overrides to `True`, the same
mistake the investigator, the docs and Celery's tests make.

## Spike 3: does history predict deserved confidence? (not supported)

| Rule | Agrees with deserved confidence (of 21) |
|---|---|
| Always `medium` | 8 |
| The investigator's claim | 8 |
| Today: `high` iff a cited `[fix]` commit | 11 |
| `high` iff a `[fix]` commit wrote a cited line (blame) | 11 |
| Fix commits on the cited functions | 5 |
| Old code is `high` / young code is `high` | 5 / 7 |

No rule beats the constant baseline by more than 3. The 13 findings with a
cited `[fix]` commit deserved 5 `high`, 2 `medium` and 6 `low`. Every feature
correlates with correctness at |ρ| ≤ 0.21. History measures how fragile an area
is, not whether a hypothesis about it is true. n=21 cannot rule out a weak
effect.

## Consequences

- Confidence has to come from checking the claim, not from history.
- A read-only refuter with the whole repository, full commit messages and
  dependency source reaches the executed verdict on most findings.
- Effective defaults need a mechanical answer; reading is unreliable there.
- Choosing a different excerpt is not the lever; access is.
