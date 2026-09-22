---
name: thunderstruck-verify
description: Turn a thunderstruck finding into a failing test or a reproduction script, so the hypothesis can be proved before anything is fixed. Use when asked to verify, reproduce, prove or test a thunderstruck finding, or when given a finding ID like FR-001.
---

# thunderstruck-verify

Take one finding and produce the thing that proves it: a failing test, or a
reproduction script where a test cannot reach.

Invoked as `/thunderstruck-verify FR-003`, or with a stable key.

## Step 1 — load the finding

```bash
cat .thunderstruck/report.json
```

Find the entry whose `id` or `key` matches. If there is no `report.json`, say
so and suggest `/thunderstruck-scan`. If the ID does not exist, list the IDs
that do rather than guessing.

Read its `how_to_verify` — that is the investigator's own proposal, and it is
the starting point, not a script to transcribe blindly.

## Step 2 — check the finding is still current

Compare the finding's `content_hash` against the file now:

```bash
sha256sum <the finding's location.file>
```

If they differ, the file changed since the scan. Say so, re-read the code, and
decide whether the finding still holds before writing anything. A test written
against a failure mode that was already fixed is worse than no test.

## Step 3 — find the project's test conventions

Look at how this repository already tests things: the runner, where tests
live, how external calls are faked. Match it. Read two or three existing tests
near the hotspot before writing one.

Never introduce a new test framework to verify a finding.

## Step 4 — write the failing test

The test must fail **for the reason the finding names**, and pass once the
missing pattern is present. Aim at the mechanism, not the symptom:

| Missing pattern | What the test asserts |
|---|---|
| S01 timeouts | A dependency that never responds does not hang the caller past a bound. |
| S02 backoff | Successive retry delays grow, are capped, and are not identical across clients. |
| S03 pushback | A 429 with `Retry-After: 60` produces a wait of at least 60s, not the client's own backoff. |
| S04 transient-only | A 400 is not retried. |
| S05 rate limiting | N calls in a window do not exceed the documented budget. |
| S07 resumability | Killing the job mid-run and restarting it does not redo completed work or duplicate rows. |
| S08 bounded results | A large result set does not load unbounded into memory or fan out unbounded concurrency. |
| S09 single-flight | N concurrent misses produce one upstream call, not N. |
| S10 retry layers | Total attempts against the dependency equal the budget, not the product of the layers. |

Prefer a fake or a local stub over the network. A verification test that needs
the real dependency is one more thing that fails for unrelated reasons.

## Step 5 — run it and report honestly

Run the test. Then say plainly which happened:

- **It fails as predicted** — the hypothesis holds. Show the failure output.
  The finding is now evidence, not conjecture.
- **It passes** — the hypothesis does not hold as stated, or the code already
  handles this. Say so directly. A finding that fails to reproduce is a useful
  result and belongs in the summary; do not quietly reshape the test until it
  goes red.
- **It cannot be written** — say what blocks it and what would unblock it.

## Scope

This skill writes tests. It does not fix the code. If the user wants the fix
too, that is a separate request — diagnosis and remedy are kept apart on
purpose, so the test stays an honest check rather than something shaped to
match a patch you already wrote.
