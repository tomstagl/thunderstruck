// FR-005 reproduction (labelling, not part of the upstream suite).
// run: cd internal-packages/run-engine && pnpm run test src/engine/tests/FR-005.test.ts --run
//
// Claim: if enqueueSystem.publishRun throws after the run row and its initial QUEUED
// snapshot are committed, trigger() rethrows, the run stays PENDING/QUEUED in Postgres
// and nothing ever enqueues it; executionSnapshotCreated has already fired.
// Fault: a real Redis rejects writes (maxmemory 1 + noeviction -> OOM) during trigger,
// then is restored. No mocks.
import { containerTest, assertNonNullable } from "@internal/testcontainers";
import { trace } from "@internal/tracing";
import { createRedisClient } from "@internal/redis";
import { RunEngine } from "../index.js";
import { setTimeout } from "timers/promises";
import { setupAuthenticatedEnvironment, setupBackgroundWorker } from "./setup.js";

vi.setConfig({ testTimeout: 120_000 });

describe("FR-005", () => {
  containerTest(
    "a trigger whose enqueue fails leaves a committed run that is never queued",
    async ({ prisma, redisOptions }) => {
      const env = await setupAuthenticatedEnvironment(prisma, "PRODUCTION");
      const engine = new RunEngine({
        prisma,
        worker: { redis: redisOptions, workers: 1, tasksPerWorker: 10, pollIntervalMs: 100 },
        queue: {
          redis: { ...redisOptions, maxRetriesPerRequest: 1 },
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
        tracer: trace.getTracer("test", "0.0.0"),
      });
      const admin = createRedisClient(redisOptions);
      const snapshotEvents: string[] = [];
      engine.eventBus.on("executionSnapshotCreated", ({ snapshot }) => {
        snapshotEvents.push(snapshot.executionStatus);
      });

      try {
        await setupBackgroundWorker(engine, env, "test-task");

        await admin.config("SET", "maxmemory-policy", "noeviction");
        await admin.config("SET", "maxmemory", "1");

        const triggerError = await engine
          .trigger(
            {
              number: 1,
              friendlyId: "run_fr005",
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
          )
          .then(
            () => null,
            (e: Error) => e
          );

        await admin.config("SET", "maxmemory", "0");

        expect(triggerError).not.toBeNull();
        console.log(`FR-005 trigger rejected: ${triggerError?.message}`);

        const row = await prisma.taskRun.findFirst({ where: { friendlyId: "run_fr005" } });
        assertNonNullable(row);
        const snapshots = await prisma.taskRunExecutionSnapshot.findMany({
          where: { runId: row.id },
          orderBy: { createdAt: "asc" },
        });
        console.log(
          `FR-005 committed: status=${row.status} snapshots=${snapshots
            .map((s) => s.executionStatus)
            .join(",")} events=${snapshotEvents.join(",")}`
        );
        expect(row.status).toBe("PENDING");
        expect(snapshots.at(-1)?.executionStatus).toBe("QUEUED");
        expect(snapshotEvents).toContain("QUEUED");

        // Redis is healthy again. Give the engine's workers time to notice anything.
        await setTimeout(10_000);
        const dequeued = await engine.dequeueFromWorkerQueue({
          consumerId: "c",
          workerQueue: "main",
        });
        const after = await prisma.taskRun.findUniqueOrThrow({ where: { id: row.id } });
        const queueKeys = await admin.keys("*run_fr005*");
        const msgKeys = await admin.keys(`*${row.id}*`);
        console.log(
          `FR-005 after recovery: dequeued=${dequeued.length} status=${after.status} redisKeys=${[
            ...queueKeys,
            ...msgKeys,
          ].join(",")}`
        );
        expect(dequeued.length).toBe(0);
        expect(after.status).toBe("PENDING");
        expect(msgKeys.filter((k) => k.includes("message"))).toEqual([]);
      } finally {
        await admin.config("SET", "maxmemory", "0").catch(() => {});
        await admin.quit();
        await engine.quit();
      }
    }
  );
});
