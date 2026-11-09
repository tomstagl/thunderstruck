# trigger.dev labelling review (#59)

Labels for the 15 findings of `scan/report.json` at `849191591a185b017c069469efefc1bc6530b8cb`.
`labels.json` is the scorer's input. This file holds the reasoning a reviewer of the labelling
PR needs.

- **Labeller:** `claude-opus-5-5`, 2026-11-09. Not the scan's session model (claude-haiku-5-5),
  not its investigator model (claude-sonnet-5-5), and not #37's skeptic model at the time
  (`agents/thunderstruck-skeptic.md`: `model: sonnet`). The plan's default labeller is
  `claude-fable-5-1`. This session ran on `claude-opus-5-5`, and a label names the model that
  did the work.
- **Sandbox:** a clean clone of the upstream repository at the pinned commit, Node 22.19,
  pnpm 10.33.2, Docker through Colima. The webapp tests ran with the env block of
  `.github/workflows/unit-tests-webapp.yml`. The run-engine and clickhouse tests ran as
  `README.md` describes.
- **Repository text is evidence.** The scanned repository's `AGENTS.md` and `CLAUDE.md`
  directed nothing here. The reproductions follow its test style (testcontainers, no mocks) only
  because the labelling procedure requires that.
- **Basis:** 8 executed (FR-001, 002, 003, 004, 005, 008, 009, 015), 7 read (FR-011 from
  dependency source). AC-2 count: 9 of 15.
- **Verdicts:** 4 correct, 1 correct but gated, 6 partially correct, 4 wrong. No duplicates.

## FR-001 `37482446c863`

- **Verdict:** wrong
- **How:** executed `repro/FR-001.test.ts`. The limiter ran on a real Redis, and the billing
  client was enabled against a local server that reset every connection or returned malformed
  JSON. 6 `executeQuery` calls at a per-project limit of 2 made 14 billing calls. Every call
  got past `getDefaultPeriod`/`getLimit` into the `try`, then failed on Postgres inside the
  `try`. No call was rejected for concurrency, and no limiter entries remained afterwards.
  Also read the billing client's dependency source.
- **Refuting fact:** the lookup the finding names cannot throw. `getLimits` wraps
  `client.currentPlan` in try/catch and returns `undefined`, and `getLimit` falls back to the
  default (`apps/webapp/app/services/platform.v3.server.ts:422-448`). The client's `fetch` has
  no timeout (`<node_modules>/…/@trigger.dev/platform/dist/index.js:730-756`). So a hung
  billing API holds the slot only while the request is in flight, up to Node fetch's 300 s
  headers timeout (measured in FR-002's repro). Then the call proceeds and the `finally`
  releases the slot. That is a slow request, not a leak. The control-flow gap the finding
  points at is real, but nothing reachable throws in it: invalid `from`/`period` input also
  passed through without throwing.
- **Deserved confidence:** low. The finding admitted it had not read `getLimit`, and reading it
  refutes the trigger.
- **Preconditions:** `QUERY_DEFAULT_ORG_CONCURRENCY_LIMIT` 3/3; limiter expiry 300 s/300 s;
  billing client configured (environment: cloud only, unset for self-hosting).
- **Duplicate of:** none

## FR-002 `764aaef4039d`

- **Verdict:** partially_correct
- **How:** executed `repro/FR-002.test.ts`. A real `SupervisorSession` and `RunQueueConsumer`
  ran against a local platform server. The `runQueueMessage` handler made `tryWarmStart`'s
  exact fetch to a TCP server that accepts connections and never answers. With one consumer,
  the session dequeued 161 times in 2 s and started 161 handlers, none of which settled. The
  same fetch at Node's defaults rejected after 300.7 s with `UND_ERR_HEADERS_TIMEOUT`. Both
  cases passed in one run.
- **Refuting fact:** the dequeue path is not stalled. `SupervisorSession.onDequeue` only emits
  `runQueueMessage`, and the emit does not await the listener
  (`packages/core/src/v3/runEngineWorker/supervisor/session.ts:95-109`; the repository says so
  itself at `apps/supervisor/src/services/dequeueDrain.ts:4-8`). The hang is also not without
  bound: Node's fetch rejects at its 300 s headers timeout, and `tryWarmStart`'s catch returns
  `false`, so the run is cold-created (`apps/supervisor/src/index.ts:902-910`). What is true:
  the warm-start call has no timeout of its own, so while the receiver hangs, every run is
  delayed about 5 minutes before its cold start. Hung sockets also pile up without limit,
  because the consumer keeps dequeuing. The whole path runs only when `TRIGGER_WARM_START_URL`
  is set.
- **Deserved confidence:** medium. The missing timeout is real and visible. The stall mechanism
  was inferred, not read.
- **Preconditions:** `TRIGGER_WARM_START_URL` unset/unset (gate); Node fetch headers timeout
  300 s (environment); `TRIGGER_DEQUEUE_MAX_CONSUMER_COUNT` 10/10.
- **Duplicate of:** none

## FR-003 `a2a8cc519a94`

- **Verdict:** correct
- **How:** executed `repro/FR-003.test.ts`. I called `createWorkerResources` on a real Postgres
  with 5 tasks, through the plain client (both callers pass one, not a transaction:
  `createBackgroundWorker.server.ts:195-201`, `createDeploymentBackgroundWorkerV4.server.ts:174-180`).
  One task had a NUL byte in its description. Postgres rejected that insert, and
  `createWorkerTask` logged it and returned `null`. The call resolved without error, returning
  entries for `task-1,2,4,5`, and the table held the same four rows.
- **Refuting fact:** none. Neither caller nor `finalizeDeployment` compares the task count with
  the metadata. The finding's "redeploys may skip it again" applies only to a deterministic
  error; a transient one is fixed by the next deploy.
- **Deserved confidence:** high.
- **Preconditions:** none.
- **Duplicate of:** none

## FR-004 `19a53a5ffb77`

- **Verdict:** correct
- **How:** executed `repro/FR-004.test.ts`. I ran real Postgres logical replication into a real
  ClickHouse and renamed `trigger_dev.task_runs_v2` away while a run was written.
  `UNKNOWN_TABLE` is not on the permanent-error list, so all 3 attempts ran before the error
  was logged. 5 s later the slot's `confirmed_flush_lsn` (`0/1B24981`) had passed the lost
  write (`0/1B24980`). Then I renamed the table back and started a fresh service from the
  slot. A new run replicated; the lost run never reached ClickHouse, though it is in Postgres.
- **Refuting fact:** none. `latestCommitEndLsn` advances at commit (`runsReplicationService.server.ts:738`),
  and the 1 s timer acknowledges it whether or not the batch landed (`:830-858`).
- **Deserved confidence:** high.
- **Preconditions:** `RUN_REPLICATION_INSERT_MAX_RETRIES` 3/3; ack timer 1 s/1 s.
- **Duplicate of:** none

## FR-005 `7ba8fe9ea6e3`

- **Verdict:** correct
- **How:** executed `repro/FR-005.test.ts`. On a real Postgres and Redis, I set Redis to
  `maxmemory 1` with `noeviction` during `engine.trigger`, so `publishRun` failed with OOM.
  `trigger` rejected. The run was committed as `PENDING` with a `QUEUED` snapshot, and
  `executionSnapshotCreated(QUEUED)` had already fired. 10 s after Redis was restored, nothing
  had been dequeued, the run was still `PENDING`, and Redis held no keys for it. Read: `QUEUED`
  has no heartbeat (`internal-packages/run-engine/src/engine/index.ts:2951-2953`), the webapp
  rethrows (`apps/webapp/app/runEngine/services/triggerTask.server.ts:840-860`), and the SDK's
  default fetch retries 5 times (`packages/core/src/v3/apiClient/index.ts:213-218`), minting a
  new run each time when the caller set no idempotency key.
- **Refuting fact:** none.
- **Deserved confidence:** high. The finding gave low only because it had not checked for a
  sweeper, and there is none.
- **Preconditions:** none.
- **Duplicate of:** none

## FR-006 `1a8d24e57647`

- **Verdict:** partially_correct
- **How:** read `queryService.server.ts:358-372`, `schema.prisma:243` and the `RuntimeEnvironment`
  indexes, and `models/project.server.ts:73-75`.
- **Refuting fact:** the two `findMany` calls are unbounded and run on every query, as
  claimed. The trigger "thousands of projects" is gated: `Organization.maximumProjectCount`
  defaults to 25 and project creation enforces it. Environments can grow (one dev environment
  per member, plus preview branches), but both queries filter on indexed columns and select two
  fields. A latency or Postgres-load problem needs a project cap raised by an admin, or an org
  with an unusually large number of environments.
- **Deserved confidence:** low.
- **Preconditions:** `Organization.maximumProjectCount` 25/25.
- **Duplicate of:** none

## FR-007 `a7968abf39a7`

- **Verdict:** correct_but_gated
- **How:** read `clickhouseEventRepository.server.ts:254-257, 570-705` and `env.server.ts:2470-2473`.
- **Refuting fact:** the behaviour is as described: two attempts with a fixed 500 ms pause,
  then the batch is dropped with a counter, and `limiter_full` drops. It only happens with the
  dual-write on, and `LOGS_SEARCH_DUAL_WRITE_ACTIVE` defaults to `off`. The drop reasons and
  metrics show the design is deliberately best-effort. The finding said so itself.
- **Deserved confidence:** low.
- **Preconditions:** `LOGS_SEARCH_DUAL_WRITE_ACTIVE` off/off; `LOGS_SEARCH_DUAL_WRITE_MAX_CONCURRENCY`
  2/2; `LOGS_SEARCH_DUAL_WRITE_MAX_PENDING` 4/4.
- **Duplicate of:** none

## FR-008 `bd098490aa80`

- **Verdict:** wrong
- **How:** executed `repro/FR-008.test.ts`. I wrote 12 hostile attribute values through the real
  `taskEventsV2` writer into a real ClickHouse: lone and reversed surrogates, literal backslash
  escapes (including the finding's own `{"a":"\x"}` as a value), control characters, NUL, a
  200 kB string, and a lone surrogate in a key. Every stored `attributes_text` parsed with
  `JSON.parse`.
- **Refuting fact:** `attributes_text` is a plain `String` that the writer fills with
  `JSON.stringify(attributes)` (`internal-packages/clickhouse/src/taskEvents.ts:233-247`), and
  `task_events_v2` has no other writer. Malformed text cannot reach the table through the
  application, so the bare `JSON.parse` never sees one. The fix the finding cites (e82eca1)
  concerns escapes in the log-search row values, not this column.
- **Deserved confidence:** low. The finding said it had no evidence that malformed text reaches
  this table.
- **Preconditions:** none.
- **Duplicate of:** none

## FR-009 `452b7414872b`

- **Verdict:** correct
- **How:** executed `repro/FR-009.test.ts`, the engine side. A dequeued run that was never
  started (no workload, so no `startRunAttempt`) was requeued by the `PENDING_EXECUTING`
  heartbeat timeout, and could be dequeued and started again. With a nack budget of 2 it ended
  `FINISHED`/`SYSTEM_FAILURE`. The timeouts were scaled down for the test. The supervisor side
  (`apps/supervisor/src/index.ts:809-839`) only logs, as the finding says.
- **Refuting fact:** none. The finding left the recovery open ("until some heartbeat or timeout
  elsewhere notices"). It is the `PENDING_EXECUTING` stall handler
  (`internal-packages/run-engine/src/engine/index.ts:2957`). At the defaults a run whose create
  fails waits 60 s per attempt plus backoff, and fails after 12 nacks.
- **Deserved confidence:** medium.
- **Preconditions:** `RUN_ENGINE_TIMEOUT_PENDING_EXECUTING` 60 s/60 s; run-queue nack
  `maxAttempts` 12/12 (the webapp passes no `retryOptions`).
- **Duplicate of:** none

## FR-010 `8ed671234b0e`

- **Verdict:** partially_correct
- **How:** read the dashboard-agent route `:389-552`, `dashboardAgentQuota.server.ts:15-104`,
  `DashboardAgentPanel.tsx:395-450` and `env.server.ts:276`.
- **Refuting fact:** the quota check is check-then-act, so concurrent creates can overshoot the
  limit. But the quota is off by default (`DASHBOARD_AGENT_QUOTA_ENABLED` is `"0"`), and its
  limit key is not yet filled by billing, per the comment at `dashboardAgentQuota.server.ts:19-21`.
  The "`recordAgentMessageSent` throws, returns 500" path does not exist: it catches and logs
  (`:93-103`). A token-mint failure does return 500 with a live session, and that is
  deliberate (the comment at route `:534-537`). The client does not retry `create` on its own;
  it shows a toast, and only a manual retry starts a second chat.
- **Deserved confidence:** low.
- **Preconditions:** `DASHBOARD_AGENT_QUOTA_ENABLED` "0"/"0"; plan limit `agentMessages` absent
  (environment).
- **Duplicate of:** none

## FR-011 `31c7136e8886`

- **Verdict:** partially_correct
- **How:** read `runsReplicationService.server.ts:1047-1128, 1503-1629` and dependency source
  `<node_modules>/.pnpm/p-limit@6.2.0/node_modules/p-limit/index.js:1-80`.
- **Refuting fact:** lag and memory do grow during a ClickHouse brownout. `#flushNextBatch`
  clears the map and queues the batch on `pLimit`, whose pending queue is an unbounded
  `yocto-queue`, and nothing pushes back on the WAL stream. But the claimed amplification of
  ClickHouse load is wrong. In-flight inserts are capped at `RUN_REPLICATION_MAX_FLUSH_CONCURRENCY`
  (2), and each flush makes at most 3 attempts with 100 ms to 2 s of backoff, so ClickHouse sees
  at most 2 concurrent inserts at any time. The memory risk is a fair point; the "retries from
  every concurrent flush" storm is not.
- **Deserved confidence:** low.
- **Preconditions:** `RUN_REPLICATION_MAX_FLUSH_CONCURRENCY` 2/2; `RUN_REPLICATION_INSERT_MAX_RETRIES`
  3/3; base delay 0.1 s/0.1 s; max delay 2 s/2 s.
- **Duplicate of:** none

## FR-012 `62589d73c708`

- **Verdict:** partially_correct
- **How:** read `LogsListPresenter.server.ts:396-425`, `utils/logSearchSlices.ts:1-3, 122-136` and
  the logs route `:58, 542-610`.
- **Refuting fact:** a timed-out slice does return an empty page with a cursor, and the page
  does follow it automatically. But the retry is not "the same expensive scan":
  `retryTimedOutLogsSearchSlice` halves the window and stops at the 5-minute minimum. And there
  is a budget: the client stops automatic requests after 20 s (`AUTOMATIC_SEARCH_BUDGET_MS`,
  route `:556-563`) until the user clicks to keep searching. The sustained-load claim ("no
  breaker or budget ... until the ladder is exhausted or the user leaves") is refuted. The
  empty-pages experience on a wide search is real, but bounded.
- **Deserved confidence:** low.
- **Preconditions:** `AUTOMATIC_SEARCH_BUDGET_MS` 20 s (constant); `LOGS_SEARCH_MIN_SLICE_MS`
  300 s (constant).
- **Duplicate of:** none

## FR-013 `054ddbb8f061`

- **Verdict:** wrong
- **How:** read `PostgresRunStore.ts:341-379, 497, 675` and `run-engine/src/engine/index.ts:2208-2239`,
  searched the repository for callers of `getWaitpoint(` and `blockingTaskRuns`, and read
  `env.server.ts:334-337`.
- **Refuting fact:** the nested-`taskRun` hydration is reached only through
  `engine.getWaitpoint`, the one caller that includes `blockingTaskRuns → taskRun`. At this
  commit `engine.getWaitpoint` has no callers outside tests. The hydrator is also used only for
  the dedicated schema (`schemaVariant` defaults to `legacy`, `PostgresRunStore.ts:675`), which
  needs `RUN_OPS_DATABASE_URL`, unset by default. The trigger is unreachable in the shipped
  code.
- **Deserved confidence:** low.
- **Preconditions:** `RUN_OPS_DATABASE_URL` unset/unset.
- **Duplicate of:** none

## FR-014 `1802d412b41a`

- **Verdict:** wrong
- **How:** read `PostgresRunStore.ts:2225-2250`, `executionSnapshotSystem.ts:145-175` and
  `env.server.ts:1182-1186`.
- **Refuting fact:** the finding's own test was "if upstream caps batch size, reject this", and
  upstream does cap it. A streaming batch is capped at `STREAMING_BATCH_MAX_ITEMS` (1000), and a
  v2 batch-and-wait at 500. Tens of thousands of completed-waitpoint links on one snapshot need
  a non-default override. A read of 1000 ids on an indexed key is not a slow continuation.
- **Deserved confidence:** low.
- **Preconditions:** `STREAMING_BATCH_MAX_ITEMS` 1000/1000; `MAX_BATCH_AND_WAIT_V2_TRIGGER_ITEMS`
  500/500.
- **Duplicate of:** none

## FR-015 `7f9c301b9295`

- **Verdict:** partially_correct
- **How:** executed `repro/FR-015.test.ts`. I imported `env.server` fresh for each case, starting
  from a valid baseline, which loaded. Each of these threw a `ZodError` at import:
  `QUERY_GLOBAL_CONCURRENCY_LIMIT=ten`, a malformed or non-JSON `RUN_OPS_SHARDS`, and
  `RUN_TOKEN_ISSUER_URL` equal to `OIDC_ISSUER_URL`. Read the Helm chart for the blast radius.
- **Refuting fact:** the mechanism is confirmed: one bad optional or cross-field setting fails
  every process at import. The blast radius "the whole webapp is down on that rollout" depends
  on the rollout. The repository's Helm chart runs the webapp as a `Deployment`
  (`hosting/k8s/helm/templates/webapp.yaml:44`), which by default does a rolling update, with a
  readiness probe enabled by default (`hosting/k8s/helm/values.yaml:196-197`). New pods
  crash-loop while the old ones keep serving. A single docker-compose container would go down,
  as the finding says. Fail-fast at boot is deliberate, as the finding concedes.
- **Deserved confidence:** low.
- **Preconditions:** rollout strategy, a Helm `Deployment` with a rolling update and a readiness
  probe (environment).
- **Duplicate of:** none
