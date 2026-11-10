# trigger.dev: second correctness ground truth (#59)

A scan of a TypeScript service, labelled finding by finding for the
correctness benchmark (`scripts/benchmark.py`, #55). Everything here is
evidence; nothing in the pipeline reads it.

Role: **holdout** (spec `docs/superpowers/specs/2026-10-03-second-ground-truth-design.md`
§6). Its labels and `review.md` are not read while changing a stage, and
figures on it are reported as totals.

| | |
|---|---|
| Repository | https://github.com/triggerdotdev/trigger.dev |
| Commit | `849191591a185b017c069469efefc1bc6530b8cb` |
| Window from | `2025-10-22` |
| Role | holdout |
| Licence | Apache-2.0 (root); MIT for the package directories listed in `LICENSES/` |
| Tests at the pinned commit | `pnpm run test --run` in `internal-packages/run-engine`: `Tests  1390 passed \| 2 skipped (1392)`; see below |
| Picked | recorded on #59 by the maintainer before 2026-10-12 |
| Scan | `/thunderstruck-scan --top 10 --since 2025-10-22`, profile `scan/profile.toml` (UI and the published SDK/CLI excluded, spec §3.1) |
| Plugin | 0.10.1 from a clean clone at `4dff62c` (the newest `main` commit with #55 and none of #56/#37/#57), installed as a local marketplace |
| Session model | claude-haiku-5-5 (orchestrator, a fresh `claude -p` session) |
| Investigator model | claude-sonnet-5-5 (10 investigators, one per hotspot) |
| Findings | 15 from 10 hotspots; incomplete: none |
| Labelled by | claude-opus-5-5, 2026-11-09; #37 default skeptic model: sonnet (`agents/thunderstruck-skeptic.md`); not the default claude-fable-5-1 because the labelling session ran on claude-opus-5-5, which the maintainer accepted as labeller; it is neither the session, the investigator nor the skeptic model. A scored run on claude-opus-5-5 has every finding of this set excluded |
| Basis | 8 executed, 7 read (1 from dependency source), 0 reasoned; AC-2 count 9 of 15 |
| Verdicts | 4 correct, 1 correct but gated, 6 partially correct, 4 wrong |
| Labelling cost | 4,333,242.3 weighted tokens (126 calls, all claude-opus-5-5, no subagents), measured as in `docs/calibration/consumption.md` from the labelling session's transcript, up to the end of the labelling turn |

Copied files under `scan/` and `repro/` are unchanged except that local
absolute paths were replaced with `<repo>`, `<thunderstruck>`,
`<labeller-scratchpad>` and `<node_modules>` (Apache-2.0 §4(b)).

## Running the test check

Run on 2026-10-30 at the commit above (committed 2026-10-22), with Node 22 and
pnpm 10, from a clone of the upstream repository:

1. `pnpm install --frozen-lockfile`
2. `pnpm run generate --filter @trigger.dev/database --filter @internal/run-ops-database`.
   pnpm 10 does not run Prisma's generate on install, and without it the
   build fails with `TS2307: Cannot find module '../generated/prisma'`.
3. `pnpm run build --filter @internal/run-engine` (7 tasks, all successful)
4. `cd internal-packages/run-engine && pnpm run test --run`

The tests start containers, so Docker must be running. On macOS with Colima
the run also needs `DOCKER_HOST=unix://$HOME/.colima/default/docker.sock`,
`TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock` and
`TESTCONTAINERS_RYUK_DISABLED=true`, and a Docker config without a credential
helper if none is installed (`DOCKER_CONFIG` pointing at a directory holding
`{}`); the images are public.

The full run reported `Test Files  1 failed | 158 passed (159)` and
`Tests  1390 passed | 2 skipped (1392)`. The one failed file,
`src/engine/tests/checkpointSystem.controlPlaneResolver.test.ts`, failed in
its container warm-up (`Hook timed out in 300000ms`; the run's total time was
5.4 hours because the machine slept during it) and had 1 of its 2 tests
skipped; the other skipped test is elsewhere. Run alone the file reports
`Tests  2 passed (2)`.

## Today's pipeline on this set

The baseline #56, #37 and #57 are measured against (spec §7). Totals only;
this set is a holdout.

```
# triggerdotdev/trigger.dev@8491915 (holdout) — pipeline · claude-sonnet-5-5
## verdicts
verdict: same                4/15  (11–52%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
verdict: one step            1/15  (1–30%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
verdict: wrong direction     10/15  (42–85%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
verdict: correct refuted     0/15  (0–20%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
## duplicates
duplicates found             0/0  (0–100%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
false duplicates             0/15  (0–20%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
## confidence
confidence: exact            10/15  (42–85%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
confidence: within one       14/15  (70–99%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
confidence: over             1/15  (1–30%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
confidence: under            4/15  (11–52%)  triggerdotdev/trigger.dev@8491915 · n=15 findings · labels: 15 claude-opus-5-5 (8 executed, 7 read)
## bundles
refuting fact shown          0/3  (0–56%)  triggerdotdev/trigger.dev@8491915 · n=11 of 15 labelled findings · labels: 11 claude-opus-5-5 (4 executed, 7 read)
shown, partly elsewhere      0/3  (0–56%)  triggerdotdev/trigger.dev@8491915 · n=11 of 15 labelled findings · labels: 11 claude-opus-5-5 (4 executed, 7 read)
refuting fact elsewhere      8/11  (43–90%)  triggerdotdev/trigger.dev@8491915 · n=11 of 15 labelled findings · labels: 11 claude-opus-5-5 (4 executed, 7 read)
refuting fact not in repository 0/11  (0–26%)  triggerdotdev/trigger.dev@8491915 · n=11 of 15 labelled findings · labels: 11 claude-opus-5-5 (4 executed, 7 read)
refuting fact unreadable     0/11  (0–26%)  triggerdotdev/trigger.dev@8491915 · n=11 of 15 labelled findings · labels: 11 claude-opus-5-5 (4 executed, 7 read)

## pooled verdicts
verdict: same                9/36  (14–41%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
verdict: one step            5/36  (6–29%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
verdict: wrong direction     22/36  (45–75%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
verdict: correct refuted     0/36  (0–10%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
## pooled duplicates
duplicates found             0/1  (0–79%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
false duplicates             0/36  (0–10%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
## pooled confidence
confidence: exact            18/36  (34–66%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
confidence: within one       34/36  (82–98%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
confidence: over             7/36  (10–35%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
confidence: under            11/36  (18–47%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=36 findings · labels: 21 claude-fable-5-1 (20 executed, 1 read); 15 claude-opus-5-5 (8 executed, 7 read)
## pooled bundles
refuting fact shown          4/12  (14–61%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=23 of 36 labelled findings · labels: 12 claude-fable-5-1 (11 executed, 1 read); 11 claude-opus-5-5 (4 executed, 7 read)
shown, partly elsewhere      2/12  (5–45%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=23 of 36 labelled findings · labels: 12 claude-fable-5-1 (11 executed, 1 read); 11 claude-opus-5-5 (4 executed, 7 read)
refuting fact elsewhere      11/23  (29–67%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=23 of 36 labelled findings · labels: 12 claude-fable-5-1 (11 executed, 1 read); 11 claude-opus-5-5 (4 executed, 7 read)
refuting fact not in repository 0/23  (0–14%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=23 of 36 labelled findings · labels: 12 claude-fable-5-1 (11 executed, 1 read); 11 claude-opus-5-5 (4 executed, 7 read)
refuting fact unreadable     0/23  (0–14%)  celery/celery + triggerdotdev/trigger.dev@pooled · n=23 of 36 labelled findings · labels: 12 claude-fable-5-1 (11 executed, 1 read); 11 claude-opus-5-5 (4 executed, 7 read)
```

With about 20 findings each interval spans 30–40 points: a change that drops
outside it on this set has not generalised; one that stays inside has not
been shown to.

Reproduce: `uv run scripts/benchmark.py --run docs/calibration/correctness/celery/runs/pipeline.json --run docs/calibration/correctness/trigger-dev/runs/pipeline.json`
