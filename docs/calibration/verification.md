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
