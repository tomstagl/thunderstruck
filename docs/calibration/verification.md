# Verification log (#37)

Live skeptic runs that the plan's Tasks 20–22 record. The spec is
`docs/superpowers/specs/2026-10-03-finding-verification-design.md`; the
plan is `docs/superpowers/plans/2026-10-03-finding-verification.md`.

## Fixture

- **Plugin:** this branch at `c264e2e` (0.13.0), installed as a
  local-directory marketplace; `claude plugin list` says enabled.
- **Fixture:** `uv run scripts/gen_sample_report.py --keep <scratch>/fixture`, head `0b72beb`.
- **Session:** a fresh headless Claude Code 2.1.311 session (`claude -p`) in
  the fixture, asked for step 4b of `/thunderstruck-scan` with
  `--verify --verify-model sonnet`, then step 5. Task 21 has not run, so the
  model is `sonnet` as the plan says.
- **Model:** `claude-sonnet-5-5`, 6 skeptics, 0 re-spawned, 0 failed, 0 reused.

| Id | File | Verdict | Reason |
|---|---|---|---|
| FR-001 | `src/util/format.ts` (`OTHER`) | upheld | The comment addressed to automated reviewers is there as described. |
| FR-002 | `src/client/releases.ts` | narrowed | Fixed 2 s sleep and the 5-attempt loop hold; `withRetry` retries only when `fetch` throws, and a 5xx does not throw, so the layers do not multiply to 60 for 5xx (about 5 × 4 = 20). |
| FR-003 | `src/sync/collection.ts` | narrowed | Restart from page 1 and duplicate rows hold; nothing calls `handleSyncFailure`, so an endless same-page loop is not shown. |
| FR-004 | `src/sync/scheduler.ts` | upheld | One module-level FIFO queue runs one job at a time. |
| FR-005 | `src/client/api.ts` | upheld | A 429 waits a fixed 5000 ms and never reads `Retry-After`. |
| — | `src/client/labels.ts` (planted) | refuted | `fetchLabel` passes `withDefaults()`, which sets `AbortSignal.timeout(8000)`; evidence `src/client/labels.ts:4`, `src/client/http-defaults.ts:1-5`. |

- The planted `labels.ts` finding is **refuted**, with evidence in
  `src/client/http-defaults.ts`.
- The `format.ts` `OTHER` finding is **not refuted** (AC-11).
- The `releases.ts` finding, which the plan calls FR-001, is **narrowed, not
  upheld**. Display ids moved: with verification the `OTHER` finding sorts
  first, so `releases.ts` is FR-002 here. The narrowing is correct on the
  fixture's code: `src/client/retry-wrapper.ts:3-11` retries only on a thrown
  error, and `src/client/releases.ts:11-12` checks `res.ok` outside it. The
  canned finding's `amplifier` ("5 x 3 x 4 = 60") overclaims.

**Outcome:** Task 20 Step 3's condition "FR-001 is upheld" does not hold, so
the plan says stop and do not merge. Whether the fixture's canned
`releases.ts` finding should be corrected (and its canned verdict with it),
or AC-13 should accept `narrowed` for it, is the maintainer's call.

**Search inside `.thunderstruck/deps/` (spec §21 question 1).** In a scratch
Python project declaring `vine==5.1.0`, with `.thunderstruck/` in
`.gitignore`, `deps.py` snapshotted `vine@5.1.0`. One `thunderstruck-skeptic`
(sonnet), given the snapshot path explicitly, found
`vine/funtools.py:12:def maybe_promise(p):` with `Grep` and 6 files with
`Glob **/*.py`, matching `grep`/`find`. Both tools search an ignored
directory when given its path.

**Consumption** (`usage.json`, `source: partial`): skeptics 55,642 weighted
tokens, 8,321–10,691 per finding. All six were saved through
`verify.py save --fallback`: the `SubagentStop` hook left no agent record in
the headless session, so per-call output tokens are not in the figure.

**Also seen:** `report.json` warns "No dependency manifest was found" although
the fixture has a `package.json` (it declares no dependencies); PR #87 lists
this.
