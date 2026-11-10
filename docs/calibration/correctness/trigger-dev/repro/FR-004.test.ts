// FR-004 reproduction (labelling, not part of the upstream suite).
// run: cd apps/webapp && pnpm exec vitest --run test/FR-004.test.ts --reporter=verbose
//      (with the env block of .github/workflows/unit-tests-webapp.yml)
//
// Claim: the replication slot is acknowledged from latestCommitEndLsn on a timer,
// independent of whether the batch reached ClickHouse; an insert that fails past
// insertMaxRetries is only logged, so the row never reaches ClickHouse and Postgres
// will not resend it.
// Fault: ClickHouse's target table is renamed away while a run is written (inserts fail
// with UNKNOWN_TABLE, which is not on the permanent-error list, so all retries run),
// then renamed back and a fresh service resubscribes from the slot. No mocks.
import { ClickHouse } from "@internal/clickhouse";
import { replicationContainerTest } from "@internal/testcontainers";
import { setTimeout } from "node:timers/promises";
import { z } from "zod";
import { RunsReplicationService } from "~/services/runsReplicationService.server";
import { TestReplicationClickhouseFactory } from "./utils/testReplicationClickhouseFactory";
import { createInMemoryTracing } from "./utils/tracing";

vi.setConfig({ testTimeout: 120_000 });

describe("FR-004", () => {
  replicationContainerTest(
    "a batch that fails past the retry budget is acknowledged and never replayed",
    async ({ clickhouseContainer, redisOptions, postgresContainer, prisma }) => {
      await prisma.$executeRawUnsafe(`ALTER TABLE public."TaskRun" REPLICA IDENTITY FULL;`);
      const clickhouse = new ClickHouse({
        url: clickhouseContainer.getConnectionUrl(),
        name: "runs-replication",
        logLevel: "warn",
      });
      const make = () =>
        new RunsReplicationService({
          clickhouseFactory: new TestReplicationClickhouseFactory(clickhouse),
          pgConnectionUrl: postgresContainer.getConnectionUri(),
          serviceName: "runs-replication",
          slotName: "task_runs_to_clickhouse_v1",
          publicationName: "task_runs_to_clickhouse_v1_publication",
          redisOptions,
          maxFlushConcurrency: 1,
          flushIntervalMs: 100,
          flushBatchSize: 1,
          leaderLockTimeoutMs: 5000,
          leaderLockExtendIntervalMs: 1000,
          ackIntervalSeconds: 5,
          insertMaxRetries: 3, // the RUN_REPLICATION_INSERT_MAX_RETRIES default
          tracer: createInMemoryTracing().tracer,
          logLevel: "warn",
        });

      const exec = (query: string) =>
        clickhouse.writer.query({ name: "fr004", query, schema: z.any() })({});

      const service = await (async () => {
        const s = make();
        await s.start();
        return s;
      })();

      const organization = await prisma.organization.create({ data: { title: "t", slug: "t" } });
      const project = await prisma.project.create({
        data: { name: "t", slug: "t", organizationId: organization.id, externalRef: "t" },
      });
      const env = await prisma.runtimeEnvironment.create({
        data: {
          slug: "t",
          type: "PRODUCTION",
          projectId: project.id,
          organizationId: organization.id,
          apiKey: "t",
          pkApiKey: "t",
          shortcode: "t",
        },
      });
      const runData = (friendlyId: string) => ({
        friendlyId,
        taskIdentifier: "my-task",
        payload: "{}",
        traceId: friendlyId,
        spanId: friendlyId,
        queue: "test",
        runtimeEnvironmentId: env.id,
        projectId: project.id,
        organizationId: organization.id,
        environmentType: "PRODUCTION" as const,
        engine: "V2" as const,
      });

      // Baseline: replication works.
      const ok = await prisma.taskRun.create({ data: runData("run_ok") });
      const countOf = async (id: string) => {
        const [err, rows] = await clickhouse.reader.query({
          name: "fr004",
          query: "SELECT count() AS c FROM trigger_dev.task_runs_v2 FINAL WHERE run_id = {id:String}",
          params: z.object({ id: z.string() }),
          schema: z.object({ c: z.coerce.number() }),
        })({ id });
        if (err) throw err;
        return rows[0].c;
      };
      await vi.waitFor(async () => expect(await countOf(ok.id)).toBe(1), { timeout: 30_000 });

      // Outage: the table is gone while a run is written.
      const [renameErr] = await exec("RENAME TABLE trigger_dev.task_runs_v2 TO trigger_dev.task_runs_v2_off");
      expect(renameErr).toBeNull();
      const lost = await prisma.taskRun.create({ data: runData("run_lost") });
      const [{ lsn: lsnAfterWrite }] = await prisma.$queryRawUnsafe<{ lsn: string }[]>(
        "SELECT pg_current_wal_lsn()::text AS lsn"
      );

      // Retries (100/200/400 ms + jitter) are exhausted, then the 1 s ack timer runs.
      await setTimeout(5_000);
      const [slot] = await prisma.$queryRawUnsafe<{ confirmed: string; passed: boolean }[]>(
        `SELECT confirmed_flush_lsn::text AS confirmed,
                confirmed_flush_lsn >= '${lsnAfterWrite}'::pg_lsn AS passed
           FROM pg_replication_slots WHERE slot_name = 'task_runs_to_clickhouse_v1'`
      );
      console.log(
        `FR-004 slot confirmed_flush_lsn=${slot.confirmed} lsnAfterLostWrite=${lsnAfterWrite} passed=${slot.passed}`
      );
      expect(slot.passed).toBe(true);

      // Recovery: table back, a fresh service resubscribes from the slot.
      await service.stop();
      const [backErr] = await exec("RENAME TABLE trigger_dev.task_runs_v2_off TO trigger_dev.task_runs_v2");
      expect(backErr).toBeNull();
      const second = make();
      await second.start();
      const after = await prisma.taskRun.create({ data: runData("run_after") });
      await vi.waitFor(async () => expect(await countOf(after.id)).toBe(1), { timeout: 30_000 });
      await setTimeout(2_000);

      const lostCount = await countOf(lost.id);
      console.log(
        `FR-004 after recovery: run_after in ClickHouse=1, run_lost in ClickHouse=${lostCount}, run_lost in Postgres=${
          (await prisma.taskRun.count({ where: { id: lost.id } })) === 1
        }`
      );
      expect(lostCount).toBe(0);
      await second.stop();
    }
  );
});
