// FR-009 reproduction (labelling, not part of the upstream suite).
// run: cd internal-packages/run-engine && pnpm run test src/engine/tests/FR-009.test.ts --run
//
// Claim: when the supervisor's workloadManager.create fails, createWorkload only logs,
// and the dequeued run "sits until some heartbeat or timeout elsewhere notices".
// The supervisor side is plain in apps/supervisor/src/index.ts:809-839. This checks the
// engine side: a run dequeued and never started (no container, so no startRunAttempt)
// is recovered by the PENDING_EXECUTING heartbeat timeout (default 60_000 ms,
// apps/webapp/app/env.server.ts:1253) and requeued, then fails after the queue's
// nack budget (run-queue defaultRetrySettings.maxAttempts = 12; webapp passes none).
// Timeouts are scaled down; the behaviour, not the duration, is under test.
import { containerTest, assertNonNullable } from "@internal/testcontainers";
import { trace } from "@internal/tracing";
import { RunEngine } from "../index.js";
import { setTimeout } from "timers/promises";
import { setupAuthenticatedEnvironment, setupBackgroundWorker } from "./setup.js";

vi.setConfig({ testTimeout: 60_000 });

function engineFor(prisma: any, redisOptions: any, maxAttempts?: number) {
  return new RunEngine({
    prisma,
    worker: { redis: redisOptions, workers: 1, tasksPerWorker: 10, pollIntervalMs: 100 },
    queue: {
      redis: redisOptions,
      retryOptions: maxAttempts
        ? { maxAttempts, minTimeoutInMs: 50, maxTimeoutInMs: 50 }
        : { maxTimeoutInMs: 50 },
      masterQueueConsumersDisabled: true,
      processWorkerQueueDebounceMs: 50,
    },
    runLock: { redis: redisOptions },
    machines: {
      defaultMachine: "small-1x",
      machines: {
        "small-1x": { name: "small-1x" as const, cpu: 0.5, memory: 0.5, centsPerMs: 0.0001 },
      },
      baseCostInCents: 0.0001,
    },
    heartbeatTimeoutsMs: { PENDING_EXECUTING: 100 },
    tracer: trace.getTracer("test", "0.0.0"),
  });
}

async function triggerAndDequeue(engine: RunEngine, prisma: any) {
  const env = await setupAuthenticatedEnvironment(prisma, "PRODUCTION");
  await setupBackgroundWorker(engine, env, "test-task");
  const run = await engine.trigger(
    {
      number: 1,
      friendlyId: "run_fr009",
      environment: env,
      taskIdentifier: "test-task",
      payload: "{}",
      payloadType: "application/json",
      context: {},
      traceContext: {},
      traceId: "t1",
      spanId: "s1",
      workerQueue: "main",
      queue: "task/test-task",
      isTest: false,
      tags: [],
    },
    prisma
  );
  await setTimeout(500);
  const dequeued = await engine.dequeueFromWorkerQueue({ consumerId: "c", workerQueue: "main" });
  expect(dequeued.length).toBe(1);
  return run;
}

describe("FR-009", () => {
  containerTest(
    "a dequeued run whose workload is never created is requeued by the PENDING_EXECUTING timeout",
    async ({ prisma, redisOptions }) => {
      const engine = engineFor(prisma, redisOptions);
      try {
        const run = await triggerAndDequeue(engine, prisma);
        // createWorkload failed: nobody calls startRunAttempt.
        const before = await engine.getRunExecutionData({ runId: run.id });
        assertNonNullable(before);
        expect(before.snapshot.executionStatus).toBe("PENDING_EXECUTING");

        await setTimeout(400);
        const after = await engine.getRunExecutionData({ runId: run.id });
        assertNonNullable(after);
        console.log(`FR-009 after timeout: ${after.snapshot.executionStatus} run=${after.run.status}`);
        expect(after.snapshot.executionStatus).toBe("QUEUED");

        await setTimeout(1_000);
        const again = await engine.dequeueFromWorkerQueue({ consumerId: "c", workerQueue: "main" });
        expect(again.length).toBe(1);
        const started = await engine.startRunAttempt({
          runId: again[0].run.id,
          snapshotId: again[0].snapshot.id,
        });
        expect(started.run.status).toBe("EXECUTING");
      } finally {
        await engine.quit();
      }
    }
  );

  containerTest(
    "when create keeps failing the run ends in SYSTEM_FAILURE once the nack budget is spent",
    async ({ prisma, redisOptions }) => {
      const engine = engineFor(prisma, redisOptions, 2);
      try {
        const run = await triggerAndDequeue(engine, prisma);
        await setTimeout(500);
        const second = await engine.dequeueFromWorkerQueue({ consumerId: "c", workerQueue: "main" });
        expect(second.length).toBe(1);
        await setTimeout(400);
        const end = await engine.getRunExecutionData({ runId: run.id });
        assertNonNullable(end);
        console.log(`FR-009 budget spent: ${end.snapshot.executionStatus} run=${end.run.status}`);
        expect(end.snapshot.executionStatus).toBe("FINISHED");
        expect(end.run.status).toBe("SYSTEM_FAILURE");
      } finally {
        await engine.quit();
      }
    }
  );
});
