# TypeScript detector calibration

Synthetic samples prove that a detector's regex matches what it was written
for. They do not prove it behaves on code nobody wrote for the test. This log
applies the protocol of the [Java calibration](java.md) to every TypeScript
detector (which also runs on JavaScript through the catalog's `aliases`):
each is swept with `scripts/calibrate.py` over real public repositories,
every hit is read and judged against the pattern's `failure_if_absent`, and
each false positive either tightens the detector, with a
`negative_<shape>.ts` sample reproducing the real-world shape written and
seen failing first, or is recorded here with a reason. This log is what a
TypeScript detector's `confidence` rests on (#19, AC-18; the rule is in the
[design spec, §9](../superpowers/specs/2026-09-24-lead-precision-and-coverage-design.md#9-evidence-from-repositories-we-cannot-see)).

Column meanings: **Hits** counts every hit of the first sweep, at `main`
`42641b0`, before any fix. **FP-fixed** counts the first sweep's hits that
the final catalog no longer reports. **Moved in** counts final hits that
were not in the first sweep: a `file_absent` detector reports the first
anchor line of a file, so when an anchor is tightened the same file can be
reported at a later line, and a regex detector reports at most five hits per
file, so a silenced line can let a sixth one through. **Final** is the sweep
with the final catalog (`claude/tick-19-prd-false-positives-4o5xvs` at
`76d3bea`, which already carries the Task 3–5 precision changes, plus this
calibration), so Hits − FP-fixed + Moved in = Final. Every final hit is
judged under **Hits** below, and TP + FP-accepted = Final. `TP (test code)`
counts as TP, as in the Java log.

## Repositories

At least one web service, one worker/queue codebase and one HTTP-client
library, as the spec asks.

| Repo | Commit | Kind | Scope swept | TS files | JS files |
|---|---|---|---|---|---|
| sindresorhus/got | `e1d87d2ced01d5b7d855a7dc8b091bf7b014a1e4` | HTTP-client library | whole tree | 29 | 6 |
| taskforcesh/bullmq | `736262fd07ec08e497f254181b7f3bbdb7b269c7` | worker/queue library | whole tree | 122 | 6 |
| immich-app/immich | `520a70891b0e0fdb3f7d3fbca18232bfee322916` | web service with job workers | `server/` | 356 | 0 |
| actualbudget/actual | `bfa850ca618ca78c556ded61274602f1fca7a4a4` | web service (sync server) | `packages/sync-server/` | 84 | 21 |

File counts are what `calibrate.py`'s shared filter leaves at the final
catalog; the first sweep, under `main`'s filter, also swept one more bullmq
TypeScript file, two more bullmq JavaScript files and two more actual
TypeScript files (tooling configs the #19 filter now skips).

Two repositories are restricted to a subtree, because a hand judgement of
every hit is only possible on a scope of a few hundred:

- **immich**: `server/` is the NestJS API and the job workers. `web/`,
  `mobile/`, `e2e/`, `cli/`, `docs/` and the other packages are a Svelte
  client, test harnesses and tooling. The whole tree gave 329 TypeScript hits
  at `main`, 134 of them outside `server/`.
- **actual**: `packages/sync-server/` is the Express service. The desktop
  client, `loot-core` (a browser/Electron app's local engine) and the other
  packages gave 553 of the tree's 634 hits at `main`, mostly S08 SQL and S19
  in client code. They are a different product surface from the web
  service this batch is about, and too many to judge by hand.

Each repository was swept twice per catalog, with
`calibrate.py --lang typescript --patterns all` and
`--lang javascript --patterns all` (the JavaScript files run the TypeScript
detectors through the alias), and the hits outside the scope were dropped.
The pinned clones were shallow (`--depth 1`); `calibrate.py` needs no
history.

`calibrate.py` skips test directories using the shared filter. Two test
setup files that it does not recognise, `packages/sync-server/vitest.globalSetup.js`
(actual) and `vitest.postgres.global-setup.ts` (bullmq), are swept and
judged like any other file. got's `benchmark/` and `documentation/examples/`
are swept too. A benchmark hang is recorded as `TP (test code)`, as in the
Java log; widening the filter is a shared-filter change (AC-16).

## Per-detector results

| Detector | Confidence | Hits | FP-fixed | Moved in | Final | TP | FP-accepted | Final per repository |
|---|---|---|---|---|---|---|---|---|
| S01-ts-fetch-no-signal | medium | 11 | 2 | 0 | 9 | 8 | 1 | actual 5, immich 4 |
| S01-ts-axios-no-timeout | medium | 0 | 0 | 0 | 0 | 0 | 0 | — |
| S01-ts-node-http-no-timeout | medium | 2 | 0 | 0 | 2 | 1 | 1 | got 2 |
| S02-ts-backoff | medium | 1 | 0 | 0 | 1 | 0 | 1 | got 1 |
| S03-ts-429-ignores-retry-after | high | 0 | 0 | 0 | 0 | 0 | 0 | — |
| S03-ts-503-ignores-retry-after | low | 0 | 0 | 0 | 0 | 0 | 0 | — |
| S04-ts-retry-without-discrimination | medium | 6 | 5 | 1 | 2 | 0 | 2 | got 1, immich 1 |
| S05-ts-http-without-limiter | medium | 10 | 1 | 0 | 9 | 1 | 8 | got 4, immich 3, actual 2 |
| S05-ts-ratelimit-headers-unread | low | 10 | 2 | 0 | 8 | 0 | 8 | actual 4, bullmq 4 |
| S06-ts-single-queue-no-priority | low | 82 | 80 | 3 | 5 | 0 | 5 | actual 2, bullmq 1, got 1, immich 1 |
| S07-ts-uncheckpointed-loop | medium | 10 | 0 | 0 | 10 | 0 | 10 | bullmq 7, actual 1, got 1, immich 1 |
| S07-ts-create-without-upsert | medium | 43 | 19 | 1 | 25 | 1 | 24 | immich 19, actual 5, bullmq 1 |
| S08-ts-unbounded-promise-all | medium | 44 | 3 | 0 | 41 | 7 | 34 | immich 23, bullmq 12, actual 4, got 2 |
| S08-ts-findmany-without-take | medium | 0 | 0 | 0 | 0 | 0 | 0 | — |
| S08-ts-select-without-limit | low | 36 | 22 | 5 | 19 | 1 | 18 | actual 14, immich 5 |
| S09-ts-cache-aside-no-singleflight | medium | 10 | 4 | 1 | 7 | 1 | 6 | bullmq 3, got 2, immich 2 |
| S10-ts-nested-retry | medium | 0 | 0 | 0 | 0 | 0 | 0 | — |
| S10-ts-aws-sdk-default-retries | low | 0 | 0 | 0 | 0 | 0 | 0 | — |
| S11-ts-no-deadline-propagation | low | 14 | 5 | 0 | 9 | 4 | 5 | actual 3, got 3, immich 3 |
| S12-ts-no-breaker | low | 8 | 7 | 3 | 4 | 1 | 3 | got 2, bullmq 1, immich 1 |
| S13-ts-shared-pool | low | 9 | 9 | 4 | 4 | 0 | 4 | bullmq 3, immich 1 |
| S14-ts-unbounded-queue | medium | 0 | 0 | 2 | 2 | 1 | 1 | got 1, immich 1 |
| S15-ts-no-fallback | low | 16 | 2 | 0 | 14 | 1 | 13 | actual 5, got 5, immich 4 |
| S16-ts-setinterval-no-jitter | medium | 1 | 0 | 0 | 1 | 0 | 1 | immich 1 |
| S16-ts-fixed-cron | low | 0 | 0 | 0 | 0 | 0 | 0 | — |
| S17-ts-cache-without-ttl | medium | 16 | 11 | 8 | 13 | 0 | 13 | immich 6, bullmq 3, actual 2, got 2 |
| S18-ts-validate-after-call | low | 3 | 0 | 0 | 3 | 0 | 3 | actual 2, got 1 |
| S19-ts-empty-catch | medium | 8 | 0 | 0 | 8 | 1 | 7 | got 5, actual 2, bullmq 1 |
| S19-ts-catch-only-comment | medium | 118 | 93 | 0 | 25 | 0 | 25 | bullmq 21, got 2, immich 2 |
| **Total** | | **458** | **265** | **28** | **221** | **28** | **193** | |

### The tripwire

A detector with more than 25 hits in one repository is a precision failure
in itself, and is tightened before its hits are judged. The first sweep
tripped it six times, in four detectors:

| Detector | Repository | First sweep | Final |
|---|---|---|---|
| S19-ts-catch-only-comment | immich | 48 | 2 |
| S19-ts-catch-only-comment | bullmq | 41 | 21 |
| S06-ts-single-queue-no-priority | immich | 43 | 1 |
| S06-ts-single-queue-no-priority | bullmq | 38 | 1 |
| S07-ts-create-without-upsert | immich | 37 | 19 |
| S08-ts-unbounded-promise-all | immich | 26 | 23 |

S08-ts-select-without-limit sat exactly at the limit in actual (25) and was
tightened as well (14 final). In the final sweep no detector exceeds 23 hits
in one repository.

### Confidence

- **S19-ts-empty-catch: `high` → `medium`.** Eight hits, one TP (actual's
  `util/mutex.ts`, where a swallowed synchronous throw leaves a promise
  unsettled). The other seven are deliberate best-effort swallows during
  cleanup, body decoding and path probing. They are explained, but a
  detector whose hits are mostly deliberate cannot claim `high`, and no
  regex separates cleanup from a write path.
- **S03-ts-429-ignores-retry-after stays `high`.** It has no hit in any of
  the four repositories, whole trees included. Its silences were checked:
  got lists 429 and 503 among its retry status codes and reads `retry-after`
  (`maxRetryAfter`, `calculate-retry-delay.ts`); actual's GoCardless and
  Enable Banking services map 429 to an error without retrying, which the
  `require` gate leaves alone. This is evidence of no false positive, not of
  recall: the batch found no TypeScript code that retries a 429 without
  reading Retry-After.
- No other confidence changes here. As in Java Batch 6, a detector whose
  final sweep has no TP, or mostly FP-accepted hits, is listed for the
  controller rather than demoted in this pass:
  - `medium` with no TP in scope: S02-ts-backoff (0 of 1),
    S04-ts-retry-without-discrimination (0 of 2), S07-ts-uncheckpointed-loop
    (0 of 10), S16-ts-setinterval-no-jitter (0 of 1),
    S17-ts-cache-without-ttl (0 of 13), S19-ts-catch-only-comment (0 of 25),
    and S01-ts-node-http-no-timeout (its one TP is benchmark code).
  - `medium` with a TP but mostly FP-accepted: S05-ts-http-without-limiter
    (1 of 9), S07-ts-create-without-upsert (1 of 25),
    S08-ts-unbounded-promise-all (7 of 41), S09-ts-cache-aside-no-singleflight
    (1 of 7), S14-ts-unbounded-queue (1 of 2).
  - Holding up: S01-ts-fetch-no-signal (8 of 9 TP) and, among the `low`
    detectors, S11-ts-no-deadline-propagation (4 of 9).

## Hits

Every hit of the final sweep, by detector. Paths are relative to the
repository root.

### S01-ts-fetch-no-signal

- actual `packages/sync-server/src/app-cors-proxy.js:207` — TP: the CORS proxy forwards to an arbitrary allow-listed URL with no signal or timeout, so one slow upstream pins the Express request indefinitely.
- actual `packages/sync-server/src/app-cors-proxy.js:43` — TP: the plugin allowlist is fetched from raw.githubusercontent.com inside a request handler with no signal or timeout. A GitHub stall holds the proxied request open for as long as the socket lives.
- actual `packages/sync-server/src/app-simplefin/app-simplefin.js:359` — TP: the SimpleFIN token claim POST has no timeout; a bridge that accepts and never answers hangs the setup request.
- actual `packages/sync-server/src/app-simplefin/app-simplefin.js:447` — TP: each redirect hop of the account fetch is an untimed `fetch`, up to five in a row.
- actual `packages/sync-server/src/scripts/health-check.ts:21` — FP-accepted: the container health-check script. Its caller is Docker, whose `healthcheck.timeout: 10s` (`packages/sync-server/docker-compose.yml`) kills it; a timeout inside the script would add nothing.
- immich `server/src/repositories/machine-learning.repository.ts:171` — TP: the ML `predict` POST has no timeout. A machine-learning server that accepts the upload and stalls parks the job (thumbnail, face, CLIP) forever; only the separate `ping` health check carries `AbortSignal.timeout`.
- immich `server/src/repositories/oauth.repository.ts:133` — TP: the OAuth profile picture is fetched from a provider-supplied URL with no timeout during login. The caller catches errors but not a hang.
- immich `server/src/repositories/server-info.repository.ts:72` — TP: the GitHub release check has no timeout; a stalled connection holds the version-check job slot.
- immich `server/src/services/workflow-execution.service.ts:101` — TP: the host `fetch` exposed to workflow plugins forwards the plugin's arguments unchanged, so nothing on the server side bounds a plugin's request.

### S01-ts-node-http-no-timeout

- got `benchmark/index.ts:159` — TP (test code): the benchmark's raw `https.request` has no timeout, so a stalled local server hangs the run.
- got `source/core/utils/http2-client.ts:1694` — FP-accepted: got's own transport. The `ClientRequest` it returns is wrapped by `timedOut()` (`source/core/index.ts:1663`), which enforces every configured phase timeout. Regex cannot see a timeout applied by the caller of the returned request.

### S02-ts-backoff

- got `source/core/index.ts:588` — FP-accepted: the note claims a constant 0 ms wait, but `backoff = 0` (line 569) is the do-not-retry branch and the `setTimeout` runs only `if (backoff && …)`. The real delay comes from `calculate-retry-delay.ts`: exponential with up to 100 ms of noise. The shared `s02_backoff` handler resolves the variable to its first literal assignment (AC-16, shared across languages).

### S04-ts-retry-without-discrimination

- got `source/as-promise/index.ts:47` — FP-accepted: `request.retryCount = retryCount` copies the counter. got discriminates in `source/core/calculate-retry-delay.ts` (methods, error codes and status codes, 413 excluded, Retry-After honoured). A file-level detector cannot see discrimination in another file.
- immich `server/src/repositories/storage.repository.ts:176` — FP-accepted: `fs.rm(folder, { maxRetries: 5, retryDelay: 100 })`. Node retries only `EBUSY`, `EMFILE`, `ENFILE`, `ENOTEMPTY` and `EPERM`, all transient; the discrimination lives in Node.

### S05-ts-http-without-limiter

- actual `packages/sync-server/src/app-enablebanking/services/enablebanking-service.ts:159` — TP: `getAllTransactions` (same file, line 432) pages through a bank's transactions back to back, up to 100 requests with no pacing, against ASPSPs the file itself notes enforce per-day quotas.
- actual `packages/sync-server/src/app-simplefin/app-simplefin.js:359` — FP-accepted: the only loop around a `fetch` in the file follows at most five redirects; `require` matched unrelated `.map(` calls.
- got `benchmark/index.ts:69` — FP-accepted: a benchmark is meant to saturate its local server.
- got `documentation/examples/uppercase-headers.js:58` — FP-accepted: a documentation example calling a local server once.
- got `source/core/options.ts:1293` — FP-accepted: the anchor is the default User-Agent string `'got (https://github.com/sindresorhus/got)'`. String literals are not blanked, by design.
- got `source/create.ts:227` — FP-accepted: `paginate` is sequential and bounded by `pagination.requestLimit` with a `pagination.backoff` delay between pages. Those names are not in `absent`.
- immich `server/src/repositories/machine-learning.repository.ts:133` — FP-accepted: the loop pings the configured ML servers (a handful, internal), each with `AbortSignal.timeout`. There is no shared quota.
- immich `server/src/repositories/server-info.repository.ts:72` — FP-accepted: one GitHub call per scheduled version check; nothing fans it out.
- immich `server/src/services/workflow-execution.service.ts:101` — FP-accepted: the loop walks allowed host patterns and returns after the first match, so it issues one request per plugin call.

### S05-ts-ratelimit-headers-unread

- actual `packages/sync-server/src/app-account.js:2` — FP-accepted: `express-rate-limit` limits *incoming* requests to this server. There is no upstream whose rate-limit headers could be read.
- actual `packages/sync-server/src/app-cors-proxy.js:2` — FP-accepted: `express-rate-limit` limits *incoming* requests to this server. There is no upstream whose rate-limit headers could be read.
- actual `packages/sync-server/src/app-openid.ts:2` — FP-accepted: `express-rate-limit` limits *incoming* requests to this server. There is no upstream whose rate-limit headers could be read.
- actual `packages/sync-server/src/app.ts:7` — FP-accepted: `express-rate-limit` limits *incoming* requests to this server. There is no upstream whose rate-limit headers could be read.
- bullmq `src/classes/errors/index.ts:3` — FP-accepted: re-exports BullMQ's own `RateLimitError`; the library implements the limiter.
- bullmq `src/classes/queue.ts:518` — FP-accepted: `Queue.rateLimit()` is BullMQ's own limiter API.
- bullmq `src/classes/worker.ts:760` — FP-accepted: `Worker.rateLimit()` is BullMQ's own limiter API.
- bullmq `src/enums/telemetry-attributes.ts:18` — FP-accepted: a telemetry attribute name, `'bullmq.queue.rate.limit'`.

### S06-ts-single-queue-no-priority

- actual `packages/sync-server/src/app-account.js:26` — FP-accepted: a per-client `express-rate-limit` on the login routes. It serves one kind of request; there is no batch work to starve anything.
- actual `packages/sync-server/src/app-openid.ts:19` — FP-accepted: the same per-client limiter on the OpenID config route.
- bullmq `src/classes/async-fifo-queue.ts:63` — FP-accepted: the worker's in-process buffer of fetched jobs. BullMQ prioritises in Redis (`priority` job option), before a job reaches this buffer.
- got `source/core/utils/http2-client.ts:646` — FP-accepted: the HTTP/2 agent's queue of requests waiting for a session. An HTTP client has no notion of which caller is interactive.
- immich `server/src/main.ts:20` — FP-accepted: `workers` is a registry of child processes keyed by worker type, not a queue of work.

### S07-ts-uncheckpointed-loop

- actual `packages/sync-server/src/app-akahu/app-akahu.ts:167` — FP-accepted: read-only paging into one response. Nothing is written per page, so there is no progress to checkpoint; a failed request simply starts again.
- bullmq `src/classes/bun-redis-client.ts:1115` — FP-accepted: a `SCAN` stream adapter; the cursor belongs to the consumer.
- bullmq `src/classes/queue.ts:846` — FP-accepted: each batch runs as a server-side script whose effect (obliterate, retry, promote) persists in Redis; a restart resumes from what is left.
- bullmq `src/classes/queue.ts:880` — FP-accepted: each batch runs as a server-side script whose effect (obliterate, retry, promote) persists in Redis; a restart resumes from what is left.
- bullmq `src/classes/queue.ts:910` — FP-accepted: each batch runs as a server-side script whose effect (obliterate, retry, promote) persists in Redis; a restart resumes from what is left.
- bullmq `src/classes/redis-queue-backend.ts:2228` — FP-accepted: read-only paging for `getJobs`.
- bullmq `src/classes/redis-queue-backend.ts:2354` — FP-accepted: a `SCAN`-and-delete loop. Deleted keys stay deleted, so a restart re-scans only what is left.
- bullmq `src/classes/valkey-glide-client.ts:997` — FP-accepted: a `SCAN` stream adapter.
- got `source/create.ts:210` — FP-accepted: `paginate` is a library generator; the caller owns the state.
- immich `server/src/services/ocr.service.ts:60` — FP-accepted: an in-memory loop over OCR results; `boxOffset = i * 8` reads as a page advance to the shared `PAGE_ADVANCE` regex (AC-16).

### S07-ts-create-without-upsert

- actual `packages/sync-server/src/accounts/openid.ts:65` — FP-accepted: the insert runs in a transaction right after `DELETE FROM auth WHERE method = 'openid'`, so a replay replaces the row.
- actual `packages/sync-server/src/accounts/password.js:53` — FP-accepted: the same delete-then-insert in one transaction for the password method.
- actual `packages/sync-server/src/app-sync/services/files-service.ts:151` — FP-accepted: the file row's primary key is the client-supplied `file.id`, so a replay fails on the key instead of duplicating.
- actual `packages/sync-server/src/services/user-service.ts:64` — FP-accepted: creating a user is an admin request, not a job, and the route (`app-admin.js`) answers `user-already-exists` when `getUserByUsername` finds the name.
- actual `packages/sync-server/vitest.globalSetup.js:30` — FP-accepted: test setup seeding users (the shared test filter does not recognise `vitest.globalSetup.js`).
- bullmq `src/postgres/migrator.ts:349` — FP-accepted: the migration ledger row is written in the same transaction as the migration, keyed by version.
- immich `server/src/schema/functions.ts:90` — FP-accepted: an audit trigger writes one row per deleted user, by design.
- immich `server/src/services/activity.service.ts:61` — FP-accepted: guarded by the `if (!activity)` lookup above it, and a user action rather than a job.
- immich `server/src/services/album.service.ts:121` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.
- immich `server/src/services/api-key.service.ts:20` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.
- immich `server/src/services/auth.service.ts:622` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.
- immich `server/src/services/base.service.ts:326` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.
- immich `server/src/services/database-backup.service.ts:70` — FP-accepted: `cronRepository.create` registers an in-process cron timer; it inserts nothing. Regex cannot tell a repository that stores rows from one that does not.
- immich `server/src/services/integrity.service.ts:79` — FP-accepted: `cronRepository.create` registers an in-process cron timer; it inserts nothing. Regex cannot tell a repository that stores rows from one that does not.
- immich `server/src/services/library.service.ts:57` — FP-accepted: `cronRepository.create` registers an in-process cron timer; it inserts nothing. Regex cannot tell a repository that stores rows from one that does not.
- immich `server/src/services/memory.service.ts:72` — TP: the nightly `MemoryGenerate` job checkpoints per day (`lastOnThisDayDate`) but not per user. A crash part-way through a day's users re-creates the memories of users already processed, as the job's own comment ("to minimize the chance of duplicates") concedes.
- immich `server/src/services/notification-admin.service.ts:13` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.
- immich `server/src/services/notification.service.ts:93` — FP-accepted: one admin notification per `JobFailed` event; in-process events are not redelivered.
- immich `server/src/services/partner.service.ts:25` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.
- immich `server/src/services/queue.service.ts:58` — FP-accepted: `cronRepository.create` registers an in-process cron timer; it inserts nothing. Regex cannot tell a repository that stores rows from one that does not.
- immich `server/src/services/session.service.ts:37` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.
- immich `server/src/services/shared-link.service.ts:91` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.
- immich `server/src/services/stack.service.ts:24` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.
- immich `server/src/services/version.service.ts:49` — FP-accepted: `cronRepository.create` registers an in-process cron timer; it inserts nothing. Regex cannot tell a repository that stores rows from one that does not.
- immich `server/src/services/workflow.service.ts:49` — FP-accepted: a request handler creating one user-requested entity (album, key, session, link…). No job replays it; a new row per request is the intended semantics.

### S08-ts-unbounded-promise-all

- actual `packages/sync-server/src/app-enablebanking/app-enablebanking.ts:65` — FP-accepted: one balance call per account of a single bank session, a handful.
- actual `packages/sync-server/src/app-gocardless/app-gocardless.ts:138` — FP-accepted: hashes IBANs in memory; no I/O per element.
- actual `packages/sync-server/src/app-gocardless/services/gocardless-service.ts:167` — FP-accepted: one detail call per account of one requisition, a handful.
- actual `packages/sync-server/src/app-gocardless/services/gocardless-service.ts:175` — FP-accepted: one call per distinct institution of those accounts, usually one.
- bullmq `src/classes/async-fifo-queue.ts:118` — FP-accepted: waits on in-flight jobs, bounded by the worker's concurrency.
- bullmq `src/classes/bun-redis-client.ts:1407` — FP-accepted: deliberate pipelining of the caller's pipeline, as ioredis does.
- bullmq `src/classes/bun-redis-client.ts:693` — FP-accepted: loads the library's fixed set of Lua scripts.
- bullmq `src/classes/child-pool.ts:119` — FP-accepted: kills the pool's children, bounded by the pool.
- bullmq `src/classes/flow-producer.ts:490` — FP-accepted: builds commands into one MULTI transaction; no round trip per node.
- bullmq `src/classes/flow-producer.ts:579` — FP-accepted: the same MULTI for child nodes.
- bullmq `src/classes/flow-producer.ts:601` — FP-accepted: children are fetched with `count: node.maxChildren`, which defaults to 20 (line 286).
- bullmq `src/classes/job-scheduler.ts:481` — TP: `getJobSchedulers(start = 0, end = -1)` defaults to every scheduler and fetches each one's data concurrently.
- bullmq `src/classes/queue-getters.ts:522` — TP: `getJobs` defaults to `start = 0, end = -1` and loads every matching job concurrently, the well-known way to pull a large queue into memory.
- bullmq `src/classes/redis-queue-backend.ts:2012` — FP-accepted: one call per cluster node.
- bullmq `src/classes/valkey-glide-client.ts:1114` — FP-accepted: the fixed set of Lua scripts.
- bullmq `src/utils/index.ts:235` — FP-accepted: awaits pipelines already issued as the `SCAN` stream delivered keys; it adds no concurrency.
- got `source/core/utils/dns-cache.ts:464` — FP-accepted: at most two address families.
- got `source/core/utils/dns-cache.ts:593` — FP-accepted: in-memory expiry of cache entries, no I/O.
- immich `server/src/repositories/database.repository.ts:211` — FP-accepted: one reindex per vector index, a fixed set.
- immich `server/src/repositories/job.repository.ts:227` — FP-accepted: one `addBulk` per queue, bounded by the `QueueName` enum.
- immich `server/src/repositories/job.repository.ts:236` — FP-accepted: the queues passed as arguments.
- immich `server/src/repositories/map.repository.ts:325` — FP-accepted: explicitly bounded at nine in-flight inserts (`if (futures.length >= 9)`), which the keyword list cannot read.
- immich `server/src/repositories/map.repository.ts:336` — FP-accepted: the final flush of at most nine.
- immich `server/src/repositories/storage.repository.ts:187` — TP: `removeEmptyDirs` recurses over every directory entry concurrently. A large library issues thousands of simultaneous `stat`/`readdir` calls (EMFILE).
- immich `server/src/services/database-backup.service.ts:306` — FP-accepted: one `stat` per retained backup file, bounded by the retention setting.
- immich `server/src/services/database-backup.service.ts:325` — FP-accepted: deletes the backups an admin selected.
- immich `server/src/services/database.service.ts:127` — FP-accepted: a fixed set of prewarm calls.
- immich `server/src/services/duplicate.service.ts:195` — FP-accepted: the assets kept from one duplicate group, a few.
- immich `server/src/services/integrity.service.ts:718` — TP: unlinks every untracked path of an integrity report concurrently; the report can hold thousands of entries.
- immich `server/src/services/library.service.ts:266` — TP: processes every path of a library-import job at once, so concurrency equals the job's batch size.
- immich `server/src/services/library.service.ts:286` — TP: emits `AssetCreate` for the whole batch at once; its handlers queue follow-up work per asset.
- immich `server/src/services/library.service.ts:339` — FP-accepted: validates the import paths an admin configured.
- immich `server/src/services/library.service.ts:565` — FP-accepted: the few bulk updates built in the lines above it.
- immich `server/src/services/media.service.ts:370` — FP-accepted: the thumbnail outputs of one asset, at most three.
- immich `server/src/services/media.service.ts:379` — FP-accepted: two XMP copies, a literal array built two lines above.
- immich `server/src/services/memory.service.ts:70` — FP-accepted: one memory per year that has photos on this day.
- immich `server/src/services/memory.service.ts:96` — FP-accepted: the people with a birthday in the window, a few.
- immich `server/src/services/person.service.ts:758` — FP-accepted: the tables passed as arguments.
- immich `server/src/services/transcoding.service.ts:380` — FP-accepted: inactive HLS sessions of this process, bounded by concurrent viewers.
- immich `server/src/services/transcoding.service.ts:395` — TP: every expired session from the database is cleaned up at once (directory removal plus a delete). After downtime the backlog is unbounded.
- immich `server/src/utils/tasks.ts:11` — FP-accepted: a helper running the few tasks its caller pushed.

### S08-ts-select-without-limit

- actual `packages/sync-server/src/account-db.js:250` — FP-accepted: `server_prefs` is a small key/value table.
- actual `packages/sync-server/src/account-db.js:28` — FP-accepted: `auth` holds one row per login method (two today).
- actual `packages/sync-server/src/account-db.js:34` — FP-accepted: the same `auth` table.
- actual `packages/sync-server/src/accounts/openid.ts:188` — FP-accepted: a single-row read, `accountDb.first(` on the line before the SQL string. The merged detector sees `.first(` only on the SELECT's own line (see Known limitations).
- actual `packages/sync-server/src/accounts/openid.ts:208` — FP-accepted: a single-row read, `accountDb.first(` on the line before the SQL string. The merged detector sees `.first(` only on the SELECT's own line (see Known limitations).
- actual `packages/sync-server/src/accounts/openid.ts:257` — FP-accepted: a single-row read, `accountDb.first(` on the line before the SQL string. The merged detector sees `.first(` only on the SELECT's own line (see Known limitations).
- actual `packages/sync-server/src/accounts/openid.ts:287` — FP-accepted: a single-row read, `accountDb.first(` on the line before the SQL string. The merged detector sees `.first(` only on the SELECT's own line (see Known limitations).
- actual `packages/sync-server/src/accounts/openid.ts:345` — FP-accepted: a single-row read, `accountDb.first(` on the line before the SQL string. The merged detector sees `.first(` only on the SELECT's own line (see Known limitations).
- actual `packages/sync-server/src/accounts/password.js:100` — FP-accepted: a single-row read, `accountDb.first(` on the line before the SQL string. The merged detector sees `.first(` only on the SELECT's own line (see Known limitations).
- actual `packages/sync-server/src/accounts/password.js:118` — FP-accepted: a single-row read, `accountDb.first(` on the line before the SQL string. The merged detector sees `.first(` only on the SELECT's own line (see Known limitations).
- actual `packages/sync-server/src/services/user-service.ts:163` — FP-accepted: a correlated `EXISTS (` subquery whose `(` ends the line before.
- actual `packages/sync-server/src/services/user-service.ts:49` — FP-accepted: a single-row read, `accountDb.first(` on the line before the SQL string. The merged detector sees `.first(` only on the SELECT's own line (see Known limitations).
- actual `packages/sync-server/src/sync-simple.js:60` — FP-accepted: `messages_merkles` holds one row.
- actual `packages/sync-server/src/sync-simple.js:74` — TP: `SELECT * FROM messages_binary WHERE timestamp > ?` returns every message since the client's last sync. A client that has been offline for months pulls the whole log into one response.
- immich `server/src/repositories/database.repository.ts:167` — FP-accepted: `pg_indexes` filtered to the named indexes.
- immich `server/src/repositories/database.repository.ts:222` — FP-accepted: the columns of one table.
- immich `server/src/repositories/database.repository.ts:44` — FP-accepted: `pg_available_extensions` filtered to a fixed list.
- immich `server/src/schema/functions.ts:130` — FP-accepted: a statement trigger reading its `OLD` transition table, bounded by the triggering statement.
- immich `server/src/schema/functions.ts:190` — FP-accepted: the same, for memories.

### S09-ts-cache-aside-no-singleflight

- bullmq `src/classes/ioredis-client.ts:63` — FP-accepted: a WeakMap of proxy wrappers built in memory; no upstream call.
- bullmq `src/commands/script-loader.ts:291` — FP-accepted: synchronous file reads; there is no concurrent miss to coalesce.
- bullmq `src/postgres/sql-loader.ts:50` — FP-accepted: `readFileSync`, synchronous.
- got `source/core/response.ts:180` — FP-accepted: a per-response WeakMap of the decoded body, computed in memory.
- got `source/core/utils/http2-client.ts:139` — FP-accepted: the ALPN protocol cache. Concurrent misses each open the TLS socket the request then reuses, so nothing is wasted.
- immich `server/src/dtos/config.dto.ts:460` — FP-accepted: memoised schema derivation in memory.
- immich `server/src/services/search.service.ts:332` — TP: the CLIP embedding cache (`LRUMap`, 100 entries) has no in-flight map. N identical smart-search queries arriving together make N `encodeText` calls to the ML server.

### S11-ts-no-deadline-propagation

- actual `packages/sync-server/src/app-cors-proxy.js:43` — TP: the allowlist fetch runs inside a request handler, but the client's disconnect does not cancel it.
- actual `packages/sync-server/src/app-simplefin/app-simplefin.js:359` — TP: neither the claim nor the account fetches take the request's lifetime or a deadline.
- actual `packages/sync-server/src/scripts/health-check.ts:21` — FP-accepted: a standalone script with no inbound request to propagate from.
- got `benchmark/index.ts:69` — FP-accepted: benchmark; no inbound deadline exists.
- got `documentation/examples/runkit-example.js:5` — FP-accepted: a top-level documentation example.
- got `documentation/examples/uppercase-headers.js:58` — FP-accepted: a top-level documentation example.
- immich `server/src/repositories/oauth.repository.ts:133` — TP: the login request's lifetime is not passed to the profile-picture fetch.
- immich `server/src/repositories/server-info.repository.ts:72` — FP-accepted: runs from a scheduled job; there is no caller deadline to propagate.
- immich `server/src/services/workflow-execution.service.ts:101` — TP: a workflow run's lifetime is not passed to the plugin's outbound call.

### S12-ts-no-breaker

- bullmq `src/classes/worker.ts:1421` — TP: `retryIfFailed` retries connection errors `Infinity` times on a fixed delay with no breaker, so a dead Redis is polled forever at the same rate.
- got `source/as-promise/index.ts:47` — FP-accepted: an HTTP client library; a breaker belongs to the application that knows the dependency.
- got `source/core/index.ts:309` — FP-accepted: the same, the `retryCount` field.
- immich `server/src/repositories/storage.repository.ts:176` — FP-accepted: Node's `fs.rm` retries on a local filesystem; there is no remote dependency.

### S13-ts-shared-pool

- bullmq `src/classes/worker.ts:343` — FP-accepted: the sandboxed-processor pool of one worker; all of its work is background by definition.
- bullmq `src/postgres/postgres-connection.ts:243` — FP-accepted: the library's connection pool for queue commands; the LISTEN client is built separately (the comment saying so is blanked, so `dedicated` does not count).
- bullmq `vitest.postgres.global-setup.ts:18` — FP-accepted: test setup (not recognised by the shared test filter).
- immich `server/src/repositories/plugin.repository.ts:253` — FP-accepted: each plugin gets its own pool (`pluginMap`), which is already a bulkhead.

### S14-ts-unbounded-queue

- got `source/core/utils/http2-client.ts:646` — TP: requests beyond the session limit wait in this FIFO with no cap; only each request's own timeout drains it under overload.
- immich `server/src/repositories/map.repository.ts:322` — FP-accepted: `bufferGeodata = []` resets a batch buffer right after it is flushed at 5000 rows. The bound (`if (bufferGeodata.length >= 5000)`) sits above the reset, outside the forward window.

### S15-ts-no-fallback

- actual `packages/sync-server/src/app-cors-proxy.js:43` — TP: when the allowlist fetch fails, the catch sets `allowlistedRepos = []`, throwing away the list it already had. A GitHub blip denies every plugin until the next successful fetch, where serving the stale list would have kept them working.
- actual `packages/sync-server/src/app-enablebanking/services/enablebanking-service.ts:159` — FP-accepted: a generic API wrapper that maps errors; a fallback belongs to its callers, and a bank sync has no meaningful degraded answer.
- actual `packages/sync-server/src/app-gocardless/services/gocardless-api.ts:113` — FP-accepted: the same, for GoCardless.
- actual `packages/sync-server/src/app-simplefin/app-simplefin.js:359` — FP-accepted: a token claim has no degraded form.
- actual `packages/sync-server/src/scripts/health-check.ts:21` — FP-accepted: a health check exists to fail.
- got `benchmark/index.ts:69` — FP-accepted: benchmark.
- got `documentation/examples/runkit-example.js:5` — FP-accepted: documentation example.
- got `documentation/examples/uppercase-headers.js:58` — FP-accepted: documentation example.
- got `source/core/options.ts:1293` — FP-accepted: the anchor is the User-Agent string literal.
- got `source/create.ts:227` — FP-accepted: library pagination; the caller decides what to do on failure.
- immich `server/src/repositories/machine-learning.repository.ts:133` — FP-accepted: the file falls back across every configured ML URL, healthy ones first (line 165).
- immich `server/src/repositories/oauth.repository.ts:133` — FP-accepted: the caller (`AuthService.syncProfilePicture`) catches the failure and keeps the old picture.
- immich `server/src/repositories/server-info.repository.ts:72` — FP-accepted: a failed version check is logged and retried on the next schedule; nothing user-facing depends on it.
- immich `server/src/services/workflow-execution.service.ts:101` — FP-accepted: returns `{ ok, status }` to the plugin, which owns the fallback.

### S16-ts-setinterval-no-jitter

- immich `server/src/services/transcoding.service.ts:84` — FP-accepted: the interval starts when this process creates its first HLS session, so instances are not phase-aligned, and the work is local cleanup.

### S17-ts-cache-without-ttl

- actual `packages/sync-server/src/app-gocardless/services/gocardless-service.ts:44` — FP-accepted: one client per configured credential set; it grows only when the admin rotates secrets.
- actual `packages/sync-server/src/app-pluggyai/pluggyai-service.js:5` — FP-accepted: one client per budget file on the server.
- bullmq `src/classes/ioredis-client.ts:318` — FP-accepted: bound methods cached per property name of the client, a fixed set.
- bullmq `src/classes/node-redis-client.ts:196` — FP-accepted: the library's Lua scripts, a fixed set.
- bullmq `src/postgres/sql-loader.ts:46` — FP-accepted: one entry per bundled SQL file.
- got `source/core/response.ts:12` — FP-accepted: a constant map of two decoders.
- got `source/core/utils/weakable-map.ts:3` — FP-accepted: the backing field of a `WeakableMap` data structure; its owner bounds it.
- immich `server/src/dtos/config.dto.ts:430` — FP-accepted: keyed by schema object, a fixed set.
- immich `server/src/repositories/oauth.repository.ts:141` — FP-accepted: one JWKS client per configured issuer.
- immich `server/src/repositories/plugin.repository.ts:45` — FP-accepted: one entry per installed plugin.
- immich `server/src/services/hls.service.ts:25` — FP-accepted: entries are deleted when a session ends (lines 34 and 40).
- immich `server/src/services/transcoding.service.ts:41` — FP-accepted: swept by `removeInactiveSessions` on an interval.
- immich `server/src/utils/event.ts:4` — FP-accepted: each pending entry carries its own timeout and is removed on completion or expiry.

### S18-ts-validate-after-call

- actual `packages/sync-server/src/app-account.js:88` — FP-accepted: the shared `EXTERNAL_CALL` regex counts Express's `res.send(` on line 85 as an external call; the header is validated before the login call.
- actual `packages/sync-server/src/app-sync.ts:535` — FP-accepted: `JSON.parse` of a stored value counts as validation, and `res.send(` as the call (shared handler, AC-16).
- got `source/create.ts:233` — FP-accepted: `assert.array(parsed)` checks the *response*, which can only be done after the call.

### S19-ts-empty-catch

- actual `packages/sync-server/src/app-gocardless/services/gocardless-api.ts:136` — FP-accepted: best-effort parse of an error body; the error is thrown and logged either way (`'(no body)'`).
- actual `packages/sync-server/src/util/mutex.ts:11` — TP: `try { return operation().then(resolve, reject); } catch {}`. If `operation()` throws synchronously the error is swallowed and neither `resolve` nor `reject` is called, so the caller's promise never settles and the mutex chain moves on silently.
- bullmq `src/commands/script-loader.ts:610` — FP-accepted: probing candidate paths with `accessSync`; not found means try the next one.
- got `source/core/index.ts:1621` — FP-accepted: best-effort caching of the decoded body.
- got `source/core/index.ts:1626` — FP-accepted: `catch {} finally {…}` around best-effort decoding; the `finally` resets state.
- got `source/core/index.ts:1751` — FP-accepted: cancelling a body reader during cleanup.
- got `source/core/index.ts:2130` — FP-accepted: `iterable.return()` during cleanup.
- got `source/core/index.ts:2281` — FP-accepted: documented in the comment above it; the rejection is handled where the request is awaited in `_makeRequest`.

### S19-ts-catch-only-comment

- bullmq `src/classes/bun-redis-client.ts:1471` — FP-accepted: a failed `DISCARD` after a failed `MULTI`; the original error is rethrown on the next line.
- bullmq `src/classes/job-scheduler.ts:521` — FP-accepted: `interval.next()` throws when a cron schedule has no next run; returning `undefined` is the "no next run" signal the caller checks.
- bullmq `src/classes/job-scheduler.ts:565` — FP-accepted: the same, in `getNextMillis`.
- bullmq `src/classes/node-redis-client.ts:230` — FP-accepted: closing a connection that may already be closed.
- bullmq `src/classes/node-redis-client.ts:353` — FP-accepted: closing a connection that may already be closed.
- bullmq `src/classes/node-redis-client.ts:390` — FP-accepted: closing a connection that may already be closed.
- bullmq `src/classes/node-redis-client.ts:394` — FP-accepted: closing a connection that may already be closed.
- bullmq `src/classes/redis-connection.ts:528` — FP-accepted: best-effort reconnect; the original command error is rethrown.
- bullmq `src/classes/redis-connection.ts:92` — FP-accepted: an optional-module probe that falls through to a thrown, explanatory error.
- bullmq `src/classes/redis-queue-backend.ts:2851` — FP-accepted: the next `waitForJob` retries the reconnect, as the comment says.
- bullmq `src/classes/redis-queue-backend.ts:2919` — FP-accepted: the next `readEvents` retries the reconnect.
- bullmq `src/classes/sandbox.ts:143` — FP-accepted: signalling a child process that may already have exited.
- bullmq `src/classes/valkey-glide-client.ts:1193` — FP-accepted: a failed `DISCARD`; the original error is rethrown.
- bullmq `src/classes/valkey-glide-client.ts:496` — FP-accepted: clearing a connection name, cosmetic.
- bullmq `src/classes/valkey-glide-client.ts:564` — FP-accepted: closing a connection that may already be closed.
- bullmq `src/commands/script-loader.ts:638` — FP-accepted: a stack-inspection helper that restores `Error.prepareStackTrace` in `finally`.
- bullmq `src/postgres/postgres-connection.ts:402` — FP-accepted: naming the LISTEN connection is best-effort discovery.
- bullmq `src/postgres/postgres-connection.ts:438` — FP-accepted: tearing down an already-broken client.
- bullmq `src/postgres/postgres-connection.ts:64` — FP-accepted: an optional-module probe that falls through to a thrown error.
- bullmq `src/postgres/postgres-queue-backend.ts:350` — FP-accepted: best-effort connection naming.
- bullmq `src/postgres/sql-loader.ts:15` — FP-accepted: searching stack frames for a module path; a frame that does not parse means try the next.
- got `source/core/index.ts:526` — FP-accepted: decoding the body of an already-failed request; the original error is preserved.
- got `source/core/utils/http2-client.ts:279` — FP-accepted: falls back to hostname normalisation for bare IPv6 addresses.
- immich `server/src/repositories/machine-learning.repository.ts:139` — FP-accepted: a failed ping leaves `isHealthy = false`, which is recorded on the next line.
- immich `server/src/utils/maintenance.ts:50` — FP-accepted: a failure leaves `isReadable`/`isWritable` false, and those flags are the function's result.
## Fixed during calibration

Each fix below names its samples. Every `negative_<shape>.ts` was written
from the real-world shape (minimal, not copied code) and seen failing before
the catalog changed; a `positive_<shape>.ts` guards a real case the
tightening must keep. Some first-sweep hits were already removed by the
Task 3–5 precision changes on the branch; those are marked as such. After
each detector's fix, the first-sweep hits it removed are listed, with any
line a `file_absent` hit moved to.

- **S01-ts-fetch-no-signal** (this calibration): `fetch(` must be the global
  fetch, bare or as `globalThis`/`window`/`self.fetch`, and not a method
  definition (`async fetch(): Promise<T> {`). bullmq's `AsyncFifoQueue` has
  its own `fetch()` method, and the worker calls `asyncFifoQueue.fetch()`.
  → `S01/typescript/negative_fetch_method.ts`, guard
  `positive_global_fetch.ts`. The options-variable alternative of
  `absent_within` was rewritten to an equivalent linear form (two adjacent
  `[^,()]*` made it quadratic on a long unclosed `fetch(` line).
- **S04-ts-retry-without-discrimination** (this calibration): the anchor
  skips a type annotation (`retryCount: number`, `maxRetries?: number`) and a
  hyphenated event name (`'retries-exhausted'`), so a file of type
  declarations is no longer a retry construct; and a predicate named for the
  error class it retries (`isNotConnectionError(`, `is…Transient…(`) counts
  as discrimination, as bullmq's `retryIfFailed` does. →
  `S04/typescript/negative_type_declarations.ts`,
  `negative_connection_error_check.ts`. (The branch's Task 4 added `bail(`,
  `AbortError`, `onFailedAttempt` and cockatiel's `handleWhen`.)
- **S05-ts-http-without-limiter, S11-ts-no-deadline-propagation,
  S15-ts-no-fallback** (this calibration): the same global-fetch anchor as
  S01. → `S05/`, `S11/`, `S15/typescript/negative_fetch_method.ts`.
- **S05-ts-ratelimit-headers-unread** (this calibration): `absent` required
  `x-<something>-ratelimit`, so reading `x-ratelimit-limit` itself (GitHub's
  and GoCardless's header) did not count. It now accepts `x-ratelimit-*` and
  `x-<vendor>-ratelimit-*`, in a bounded form (the old `x-.*-ratelimit` was
  quadratic on a long hyphenated line). → `S05/typescript/negative_ratelimit_headers_read.ts`.
- **S06-ts-single-queue-no-priority**: the anchor matched any word `queue`,
  `worker`, `pool`, `limiter` or `throttle`: imports, re-exports, type
  fields, strings, `jobRepository.queue(` calls, `@OnJob({ queue: … })`
  options. The branch's Task 4 made it a module-level or class-field
  declaration. This calibration then removed what that still let through:
  the declared name must end in the noun (`QUEUE_EVENT_SUFFIX`,
  `QueueNameSchema`, `WORKER_TYPES` do not), the value must not be a string
  or a component (`IWorker = 'IWorker'`, `SvgQueue = (props) =>`), and an
  `=` that opens an arrow or a comparison is not an assignment
  (`worker.stdout?.on('data', (data) => …)`, `Pool: new (…) => PgPool`,
  `queues: Object.values(QueueName).map((name) => …)`, all shapes the
  branch's plain-field alternative let in). An arrow inside a type
  annotation is skipped, so the fixture's
  `const queue: Array<() => Promise<unknown>> = []` still fires. →
  `S06/typescript/negative_mentions_only.ts`, `negative_named_constants.ts`,
  `negative_arrow_and_type_member.ts`, guard `positive_function_type_queue.ts`.
- **S07-ts-create-without-upsert** (this calibration): `.create(` no longer
  anchors on a controller delegating to its service (`this.service.create(`;
  the service's file is swept on its own), on `this.create(`, on a static
  factory (`NestFactory.create`, `BaseConfig.create`, `SomeDto.create`,
  `StorageCore.create`) or on a no-argument `create()` (`sha1.create()`). →
  `S07/typescript/negative_delegation_and_factories.ts`, guards
  `positive_repository_create.ts` (`this.assetRepository.create(row)` in a
  loop) and `positive_model_create.ts` (Mongoose-style `Order.create({…})`).
  (The branch's Task 4 added unique-violation handling — `P2002`, `E11000`,
  `23505`… — to `absent`.)
- **S08-ts-unbounded-promise-all** (this calibration): a fan-out over the
  members of an enum (`Promise.all(Object.values(QueueName).map(…))`) is
  bounded by the code, and a method under immich's `@Chunked()` decorator
  sees one chunk at a time (`\bchunk\b` missed the compound `Chunked`). →
  `S08/typescript/negative_enum_fanout.ts`, `negative_chunked_decorator.ts`.
  (The branch's Task 4 added UPPER_CASE constants.)
- **S08-ts-select-without-limit**: a subquery (`IN (SELECT …`,
  `EXISTS (SELECT …`) is bounded by its outer statement, a SELECT passed to
  `.first(` on the same line reads one row, and `COALESCE(MAX(…))` is an
  aggregate (this calibration); aggregates and lookups by `id` in the
  matched statement were the branch's Task 3/4 rule. →
  `S08/typescript/negative_single_row_select.ts`,
  `negative_aggregate_select.ts`, `negative_subquery_select.ts`, guards
  `positive_unbounded_select.ts` (actual's `messages_binary WHERE timestamp > ?`),
  `positive_neighbour_select.ts` and `positive_where_id_any.ts` (the two
  shapes the branch's Python samples guard, now also held for TypeScript).
  Before the rebase this calibration also looked two lines back for
  `.first(`; that window would have broken the branch's statement-scoped
  rules, so it was dropped and the multi-line `.first(` reads are
  FP-accepted instead (see Known limitations).
- **S09-ts-cache-aside-no-singleflight** (this calibration): the anchor's
  `fromCache` matched the flag `isFromCache: boolean`; `getCached…(` and
  `fromCache…(` now count only as calls. A map of pending promises
  (`#pending = new Map`, got's DNS cache) is in-flight deduplication,
  whatever it is called. → `S09/typescript/negative_from_cache_flag.ts`,
  `negative_pending_map.ts`.
- **S11-ts-no-deadline-propagation** (this calibration): `absent` had
  `signal\s*[:,)]` inside `\b(…)\b`, and a `\b` after `:` never matches
  before a space, so `{ signal: controller.signal }` never counted. →
  `S11/typescript/negative_signal_option.ts`.
- **S12-ts-no-breaker** (this calibration): the anchor skips type
  annotations and event names, as S04's does. →
  `S12/typescript/negative_type_declarations.ts`, guard `positive.ts`.
- **S13-ts-shared-pool** (this calibration): the anchor was any word
  `pool`: imports, re-exports, a type member, an error-message string and a
  test file list. It is now a pool the file builds or uses: `new …Pool(`,
  `createPool(`, `pool.query/connect/acquire/getConnection/execute(`, or a
  pool-size option. → `S13/typescript/negative_mentions_only.ts`, guard
  `positive.ts`.
- **S17-ts-cache-without-ttl**: the branch's Task 4 anchor (a module-level
  or class-field Map, or `…Cache.set(`) removed the function-local index
  Maps. This calibration made `absent` see compound names (`LRUMap`,
  `maxProtocolCacheSize`, `COMPLETED_AUTH_TTL_MS`, `cacheTtlMs`, but not
  `throttle`), and moved `clear(` out of the `\b(…)\b` group, where the
  trailing `\b` after `(` never matched `clear()`. actual's Enable Banking
  auth maps, which carry a `setTimeout(…, COMPLETED_AUTH_TTL_MS)` expiry,
  appeared under the branch's anchor and are silenced by this. The anchor's
  `\w*[Cc]ache\.set` became `[Cc]ache\.set` (same matches, no longer
  quadratic on a long word). → `S17/typescript/negative_lru_map.ts`,
  `negative_max_size_constant.ts`, `negative_ttl_constant.ts`,
  `negative_default_param_map.ts`, the local-index shapes added to the
  branch's `negative_local_index.ts`, guard `positive_class_field.ts`.
- **S19-ts-catch-only-comment** (this calibration; #17, item 2):
  `present_within: '^\s*\}'` over the next two lines fired on every
  one-statement catch, a logged one included. Comments are blanked before
  matching, so a body of comments only is whitespace: the closing `}` must
  now be the first thing after the catch line (`\A\s*\}`, window 4). A
  catch parameter named `_…`, `ignored`, `expected` or `unused` marks a
  deliberate swallow, as for S19-ts-empty-catch and S19-java-*. →
  `S19/typescript/negative_logged_catch.ts` (the sample #17 asks for),
  `negative_underscore_param.ts`, guard `positive_comment_only.ts` (a
  two-line comment body, which the old window missed).

The first-sweep hits each fix removed:

### S01-ts-fetch-no-signal

FP-fixed: bullmq `src/classes/async-fifo-queue.ts:180`, `src/classes/worker.ts:675`.

### S04-ts-retry-without-discrimination

FP-fixed: bullmq `src/classes/queue-events.ts:200`, `src/classes/worker.ts:1416`; got `source/as-promise/index.ts:45`, `source/core/diagnostics-channel.ts:74`, `source/core/response.ts:99`.

Moved in: got `source/as-promise/index.ts:47`.

### S05-ts-http-without-limiter

FP-fixed: bullmq `src/classes/async-fifo-queue.ts:180`.

### S05-ts-ratelimit-headers-unread

FP-fixed: actual `packages/sync-server/src/app-gocardless/app-gocardless.ts:291`; got `documentation/examples/gh-got.js:10`.

### S06-ts-single-queue-no-priority

FP-fixed: bullmq `docs/.vitepress/config.mts:12`, `src/classes/backoffs.ts:79`, `src/classes/child-pool.ts:77`, `src/classes/child.ts:3`, `src/classes/flow-producer.ts:19`, `src/classes/index.ts:1`, `src/classes/job-scheduler.ts:15`, `src/classes/lock-manager.ts:28`, `src/classes/queue-base.ts:13`, `src/classes/queue-events-producer.ts:2`, `src/classes/queue-events.ts:9`, `src/classes/queue-getters.ts:3`, `src/classes/queue-keys.ts:22`, `src/classes/queue.ts:19`, `src/classes/sandbox.ts:4`, `src/classes/worker.ts:26`, `src/enums/telemetry-attributes.ts:2`, `src/interfaces/flow-job.ts:2`, `src/interfaces/index.ts:10`, `src/interfaces/minimal-queue.ts:3`, `src/interfaces/parent-options.ts:11`, `src/interfaces/parent.ts:12`, `src/interfaces/script-queue-context.ts:2`, `src/interfaces/worker-options.ts:2`, `src/postgres/create-postgres-backend.ts:6`, `src/postgres/index.ts:7`, `src/postgres/pg-types.ts:115`, `src/postgres/postgres-connection.ts:70`, `src/utils/create-backend.ts:7`, `src/utils/index.ts:249`, `vitest.bun.config.ts:20`, `vitest.config.ts:17`, `vitest.coverage.config.ts:68`, `vitest.ioredis.config.ts:18`, `vitest.node-redis.config.ts:20`, `vitest.postgres.global-setup.ts:13`, `vitest.valkey-glide.config.ts:10`; immich `server/src/app.common.ts:9`, `server/src/app.module.ts:16`, `server/src/controllers/index.ts:30`, `server/src/controllers/job.controller.ts:6`, `server/src/controllers/library.controller.ts:119`, `server/src/controllers/queue.controller.ts:12`, `server/src/dtos/queue-legacy.dto.ts:3`, `server/src/dtos/queue.dto.ts:21`, `server/src/enum.ts:310`, `server/src/main.ts:5`, `server/src/maintenance/maintenance-auth.guard.ts:6`, `server/src/maintenance/maintenance-health.repository.ts:13`, `server/src/maintenance/maintenance-worker.controller.ts:30`, `server/src/repositories/config.repository.ts:184`, `server/src/repositories/plugin.repository.ts:3`, `server/src/services/asset-file.service.ts:46`, `server/src/services/asset-media.service.ts:122`, `server/src/services/asset.service.ts:275`, `server/src/services/auth.service.ts:398`, `server/src/services/base.service.ts:264`, `server/src/services/cluster-group.service.ts:78`, `server/src/services/database-backup.service.ts:73`, `server/src/services/duplicate.service.ts:302`, `server/src/services/index.ts:31`, `server/src/services/integrity.service.ts:84`, `server/src/services/job.service.ts:82`, `server/src/services/library.service.ts:60`, `server/src/services/media.service.ts:68`, `server/src/services/memory.service.ts:28`, `server/src/services/metadata.service.ts:215`, `server/src/services/ocr.service.ts:13`, `server/src/services/person.service.ts:237`, `server/src/services/session.service.ts:18`, `server/src/services/smart-info.service.ts:67`, `server/src/services/storage-template.service.ts:140`, `server/src/services/sync.service.ts:237`, `server/src/services/tag.service.ts:155`, `server/src/services/transcoding.service.ts:60`, `server/src/services/trash.service.ts:38`, `server/src/services/user-admin.service.ts:114`, `server/src/services/user.service.ts:117`, `server/src/services/version.service.ts:76`, `server/src/workers/maintenance.ts:5`.

Moved in: actual `packages/sync-server/src/app-account.js:26`, actual `packages/sync-server/src/app-openid.ts:19`, immich `server/src/main.ts:20`.

### S07-ts-create-without-upsert

FP-fixed: immich `server/src/controllers/activity.controller.ts:47`, `server/src/controllers/album.controller.ts:48`, `server/src/controllers/api-key.controller.ts:24`, `server/src/controllers/job.controller.ts:42`, `server/src/controllers/library.controller.ts:41`, `server/src/controllers/memory.controller.ts:44`, `server/src/controllers/notification-admin.controller.ts:31`, `server/src/controllers/partner.controller.ts:35`, `server/src/controllers/person.controller.ts:68`, `server/src/controllers/session.controller.ts:29`, `server/src/controllers/shared-link.controller.ts:121`, `server/src/controllers/stack.controller.ts:37`, `server/src/controllers/user-admin.controller.ts:45`, `server/src/controllers/video-stream.controller.ts:60`, `server/src/controllers/workflow.controller.ts:33`, `server/src/services/base.service.ts:188`, `server/src/services/cluster-group.service.ts:95`, `server/src/services/transcoding.service.ts:219`, `server/src/workers/microservices.ts:18`.

Moved in: immich `server/src/services/base.service.ts:326`.

### S08-ts-unbounded-promise-all

FP-fixed: immich `server/src/services/person.service.ts:279`, `server/src/services/queue.service.ts:147`, `server/src/utils/maintenance.ts:35`.

### S08-ts-select-without-limit

FP-fixed: actual `packages/sync-server/src/account-db.js:177`, `packages/sync-server/src/account-db.js:51`, `packages/sync-server/src/account-db.js:68`, `packages/sync-server/src/accounts/openid.ts:115`, `packages/sync-server/src/accounts/openid.ts:129`, `packages/sync-server/src/accounts/openid.ts:251`, `packages/sync-server/src/accounts/password.js:107`, `packages/sync-server/src/accounts/password.js:181`, `packages/sync-server/src/accounts/password.js:77`, `packages/sync-server/src/app-sync/services/files-service.ts:269`, `packages/sync-server/src/services/secrets-service.js:58`, `packages/sync-server/src/services/user-service.ts:20`, `packages/sync-server/src/services/user-service.ts:29`, `packages/sync-server/src/services/user-service.ts:41`, `packages/sync-server/src/services/user-service.ts:9`, `packages/sync-server/vitest.globalSetup.js:46`; bullmq `src/postgres/migrator.ts:308`; immich `server/src/repositories/asset.repository.ts:350`, `server/src/repositories/asset.repository.ts:470`, `server/src/schema/functions.ts:131`, `server/src/schema/functions.ts:144`, `server/src/schema/functions.ts:32`.

Moved in: actual `packages/sync-server/src/account-db.js:250`, actual `packages/sync-server/src/accounts/openid.ts:257`, actual `packages/sync-server/src/accounts/openid.ts:287`, actual `packages/sync-server/src/accounts/openid.ts:345`, actual `packages/sync-server/src/services/user-service.ts:163`.

### S09-ts-cache-aside-no-singleflight

FP-fixed: got `source/core/diagnostics-channel.ts:51`, `source/core/index.ts:1044`, `source/core/response.ts:53`, `source/core/utils/dns-cache.ts:79`.

Moved in: got `source/core/response.ts:180`.

### S11-ts-no-deadline-propagation

FP-fixed: actual `packages/sync-server/src/app-enablebanking/services/enablebanking-service.ts:159`; bullmq `src/classes/async-fifo-queue.ts:180`; got `source/core/index.ts:2296`, `source/core/utils/http2-client.ts:666`, `source/create.ts:227`.

### S12-ts-no-breaker

FP-fixed: bullmq `src/classes/queue-events.ts:200`, `src/classes/worker.ts:1416`; got `source/as-promise/index.ts:45`, `source/core/diagnostics-channel.ts:74`, `source/core/index.ts:158`, `source/core/options.ts:143`, `source/core/response.ts:99`.

Moved in: bullmq `src/classes/worker.ts:1421`, got `source/as-promise/index.ts:47`, got `source/core/index.ts:309`.

### S13-ts-shared-pool

FP-fixed: bullmq `src/classes/index.ts:4`, `src/classes/sandbox.ts:4`, `src/classes/worker.ts:28`, `src/postgres/pg-types.ts:115`, `src/postgres/postgres-connection.ts:70`, `src/postgres/postgres-queue-backend.ts:506`, `vitest.bun.config.ts:32`, `vitest.postgres.global-setup.ts:13`; immich `server/src/repositories/plugin.repository.ts:3`.

Moved in: bullmq `src/classes/worker.ts:343`, bullmq `src/postgres/postgres-connection.ts:243`, bullmq `vitest.postgres.global-setup.ts:18`, immich `server/src/repositories/plugin.repository.ts:253`.

### S14-ts-unbounded-queue


Moved in: got `source/core/utils/http2-client.ts:646`, immich `server/src/repositories/map.repository.ts:322`.

### S15-ts-no-fallback

FP-fixed: bullmq `src/classes/async-fifo-queue.ts:180`, `src/classes/worker.ts:675`.

### S17-ts-cache-without-ttl

FP-fixed: bullmq `src/commands/script-loader.ts:318`, `src/postgres/sql-loader.ts:53`; got `source/core/utils/http2-client.ts:143`; immich `server/src/dtos/asset-response.dto.ts:170`, `server/src/dtos/config.dto.ts:456`, `server/src/repositories/album.repository.ts:129`, `server/src/services/download.service.ts:95`, `server/src/services/duplicate.service.ts:239`, `server/src/services/metadata.service.ts:909`, `server/src/services/search.service.ts:338`, `server/src/services/shared/user-methods.ts:22`.

Moved in: actual `packages/sync-server/src/app-gocardless/services/gocardless-service.ts:44`, bullmq `src/classes/node-redis-client.ts:196`, bullmq `src/postgres/sql-loader.ts:46`, got `source/core/utils/weakable-map.ts:3`, immich `server/src/dtos/config.dto.ts:430`, immich `server/src/services/hls.service.ts:25`, immich `server/src/services/transcoding.service.ts:41`, immich `server/src/utils/event.ts:4`.

### S19-ts-catch-only-comment

FP-fixed: actual `packages/sync-server/src/accounts/openid.ts:352`, `packages/sync-server/src/accounts/openid.ts:378`, `packages/sync-server/src/accounts/password.js:31`, `packages/sync-server/src/accounts/password.js:38`, `packages/sync-server/src/app-admin.js:24`, `packages/sync-server/src/app-cors-proxy.js:144`, `packages/sync-server/src/app-enablebanking/app-enablebanking.ts:76`, `packages/sync-server/src/app-enablebanking/services/enablebanking-service.ts:177`, `packages/sync-server/src/app-gocardless/app-gocardless.ts:36`, `packages/sync-server/src/app-gocardless/services/gocardless-service.ts:124`, `packages/sync-server/src/app-simplefin/app-simplefin.js:341`, `packages/sync-server/src/app-sync.ts:290`, `packages/sync-server/src/app.ts:101`, `packages/sync-server/src/app.ts:214`, `packages/sync-server/src/services/user-service.ts:104`, `packages/sync-server/src/services/user-service.ts:124`, `packages/sync-server/src/services/user-service.ts:141`, `packages/sync-server/src/services/user-service.ts:225`, `packages/sync-server/src/util/ssrf.ts:103`, `packages/sync-server/src/util/ssrf.ts:79`; bullmq `src/classes/bun-redis-client.ts:1134`, `src/classes/bun-redis-client.ts:449`, `src/classes/bun-redis-client.ts:476`, `src/classes/child-pool.ts:82`, `src/classes/child-processor.ts:80`, `src/classes/lock-manager.ts:90`, `src/classes/main-base.ts:28`, `src/classes/node-redis-client.ts:832`, `src/classes/redis-queue-backend.ts:2267`, `src/classes/sandbox.ts:123`, `src/classes/sandbox.ts:154`, `src/classes/valkey-glide-client.ts:431`, `src/classes/valkey-glide-client.ts:65`, `src/classes/worker.ts:1252`, `src/classes/worker.ts:1322`, `src/postgres/postgres-connection.ts:98`, `src/postgres/postgres-queue-backend.ts:842`, `src/postgres/postgres-queue-backend.ts:861`, `src/postgres/postgres-queue-backend.ts:909`, `src/postgres/postgres-queue-backend.ts:929`; got `source/core/index.ts:1781`, `source/core/index.ts:1868`, `source/core/index.ts:489`, `source/core/index.ts:731`, `source/core/options.ts:1049`, `source/core/options.ts:3820`, `source/core/options.ts:975`; immich `server/src/bin/sync-sql.ts:161`, `server/src/controllers/sync.controller.ts:33`, `server/src/controllers/video-stream.controller.ts:61`, `server/src/controllers/video-stream.controller.ts:84`, `server/src/cores/storage.core.ts:266`, `server/src/maintenance/maintenance-worker.service.ts:137`, `server/src/maintenance/maintenance-worker.service.ts:251`, `server/src/maintenance/maintenance-worker.service.ts:268`, `server/src/middleware/file-upload.interceptor.ts:141`, `server/src/middleware/file-upload.interceptor.ts:92`, `server/src/repositories/config.repository.ts:164`, `server/src/repositories/config.repository.ts:211`, `server/src/repositories/job.repository.ts:121`, `server/src/repositories/machine-learning.repository.ts:180`, `server/src/repositories/media.repository.ts:89`, `server/src/repositories/metadata.repository.ts:144`, `server/src/repositories/plugin.repository.ts:239`, `server/src/repositories/plugin.repository.ts:260`, `server/src/repositories/process.repository.ts:88`, `server/src/repositories/server-info.repository.ts:29`, `server/src/repositories/server-info.repository.ts:79`, `server/src/repositories/storage.repository.ts:158`, `server/src/services/api.service.ts:45`, `server/src/services/api.service.ts:79`, `server/src/services/api.service.ts:90`, `server/src/services/auth.service.ts:400`, `server/src/services/download.service.ts:118`, `server/src/services/integrity.service.ts:335`, `server/src/services/integrity.service.ts:408`, `server/src/services/integrity.service.ts:447`, `server/src/services/job.service.ts:94`, `server/src/services/library.service.ts:271`, `server/src/services/media.service.ts:609`, `server/src/services/memory.service.ts:54`, `server/src/services/notification-admin.service.ts:33`, `server/src/services/notification.service.ts:267`, `server/src/services/shared-link.service.ts:107`, `server/src/services/shared-link.service.ts:135`, `server/src/services/storage-template.service.ts:262`, `server/src/services/storage.service.ts:149`, `server/src/services/transcoding.service.ts:385`, `server/src/services/workflow-execution.service.ts:144`, `server/src/services/workflow-execution.service.ts:159`, `server/src/services/workflow-execution.service.ts:220`, `server/src/services/workflow-execution.service.ts:280`, `server/src/utils/search-cursor.ts:18`.

### Lost to tightening (recall trade)

- `S07-ts-create-without-upsert`: immich `server/src/services/cluster-group.service.ts:95`
  `clusterGroupRepository.create()` inserts a row of defaults; the
  no-argument rule no longer anchors on it. The file stays reported through
  its `userRepository.create({…})` at line 326, and as a request-scoped
  insert it would have been FP-accepted anyway.
- `S13-ts-shared-pool`: bullmq `src/postgres/postgres-queue-backend.ts:506`
  `this.connection.pool.query<R>(…)`: the explicit type argument between
  `query` and `(` does not match. The pool is built in
  `postgres-connection.ts`, which is still reported.

## Silences checked

- **S03-ts-***: see Confidence. got's retry path honours Retry-After, and
  actual's two 429 mappings do not retry.
- **S01-ts-axios-no-timeout**: none of the four scopes uses axios.
- **S08-ts-findmany-without-take**: no Prisma in scope (immich uses Kysely,
  actual better-sqlite3, bullmq raw SQL).
- **S10-ts-nested-retry**: no scope stacks two retry layers. got's retry
  lives in one place (`calculate-retry-delay.ts` driving the request), and
  bullmq's `retryIfFailed` is the worker's only layer.
  **S10-ts-aws-sdk-default-retries** (`score: false`, inventory only): no
  AWS SDK v3 client in scope.
- **S16-ts-fixed-cron**: immich keeps its cron expressions in configuration
  (`cronExpression`), which the TypeScript detector does not read; each
  installation is a separate deployment, so there is no fleet to fire in
  lockstep.
- Every TypeScript sample, old and new, passes; the fixture's planted S06
  lead (`src/sync/scheduler.ts:1`) still fires, and the sample report is
  unchanged by this calibration.

## Known limitations (noted, not fixed)

- `S08-ts-select-without-limit`: a single-row read split over two lines
  (`accountDb.first(` then the SQL string) and a subquery whose `(` ends the
  previous line are still reported (nine FP-accepted in actual). Only the
  matched line and the lines after it are visible to the branch's
  statement-scoped rules, so a lookback window could not be added without
  breaking them. The pattern `SELECT\s+.*\s+FROM\s+` (unchanged from `main`)
  is quadratic on a pathological line of repeated `SELECT` (about 1.4 s for
  40 KB).
- Shared module handlers (AC-16, not changed here): `s18_fail_fast` counts
  Express's `res.send(` as an external call and `JSON.parse(` as
  validation; `s07_checkpoint`'s `PAGE_ADVANCE` reads `boxOffset = i * 8` as
  a page advance; `s02_backoff` resolves a variable wait to its first literal
  assignment, even when that is the do-not-retry `0`. `FUNC_TS` in
  `s18_fail_fast` is still quadratic on long whitespace runs (#17, item 1);
  the calibration sweeps did not hit it.
- File-level detectors (S04, S05, S11, S12, S15) cannot see a
  discrimination, limiter or fallback that lives in another file, as in got
  (`calculate-retry-delay.ts`) and immich (`AuthService` catching the
  profile-picture failure).
- String literals are not blanked, by design, so got's User-Agent string
  `'got (https://…)'` anchors S05 and S15.
- `S19-ts-catch-only-comment`: a comment-only body longer than three lines
  is missed (window 4), and a typed deliberate parameter (`_e: unknown`) is
  not recognised by the name convention.
- `S06-ts-single-queue-no-priority`: a type annotation containing an `=`
  other than `=>` (a generic default, `<T = Job>`) stops the anchor, which
  is a miss.
- `S07-ts-create-without-upsert`: the receiver tests are name-based. A
  data-layer class named `…Service`, `…Config` or `…Core` that inserts is
  missed, and a repository method that stores nothing (`cronRepository.create`
  registers a timer) is still reported.
- Test setup files outside test directories (`vitest.globalSetup.js`,
  `vitest.postgres.global-setup.ts`) are swept; recognising them is a
  shared-filter change (AC-16).
