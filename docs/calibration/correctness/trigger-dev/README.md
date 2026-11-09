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
