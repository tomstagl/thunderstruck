// FR-003 reproduction (labelling, not part of the upstream suite).
// run: cd apps/webapp && pnpm exec vitest --run app/v3/services/FR-003.test.ts --reporter=verbose
//      (with the env block of .github/workflows/unit-tests-webapp.yml)
//
// Claim: createWorkerTask catches every non-validation error and returns null, and
// createWorkerTasks drops nulls, so a worker is registered with a partial task set and
// the caller sees success. Both callers pass the plain client, not a transaction
// (createBackgroundWorker.server.ts:195-201, createDeploymentBackgroundWorkerV4.server.ts:174-180).
// Fault: one of five tasks carries a NUL byte in its description, which a real Postgres
// rejects (22021 invalid byte sequence). No mocks.
import { containerTest } from "@internal/testcontainers";
import type { BackgroundWorkerMetadata } from "@trigger.dev/core/v3";
import { describe, expect, vi } from "vitest";
import type { AuthenticatedEnvironment } from "~/services/apiAuth.server";
import { createWorkerResources } from "~/v3/services/createBackgroundWorker.server";

vi.setConfig({ testTimeout: 60_000 });

describe("FR-003", () => {
  containerTest(
    "a non-validation DB error on one task leaves a worker with 4 of 5 tasks and no error",
    async ({ prisma }) => {
      const slug = `fr003_${Math.random().toString(36).slice(2, 10)}`;
      const organization = await prisma.organization.create({ data: { title: slug, slug } });
      const project = await prisma.project.create({
        data: { name: slug, slug, organizationId: organization.id, externalRef: slug },
      });
      const prodEnv = await prisma.runtimeEnvironment.create({
        data: {
          slug: "prod",
          type: "PRODUCTION",
          projectId: project.id,
          organizationId: organization.id,
          apiKey: `tr_prod_${slug}`,
          pkApiKey: `pk_prod_${slug}`,
          shortcode: `p${slug.slice(0, 5)}`,
        },
      });
      const worker = await prisma.backgroundWorker.create({
        data: {
          friendlyId: `worker_${prodEnv.id}`,
          contentHash: "fr003",
          version: "20261109.1",
          metadata: {},
          projectId: project.id,
          runtimeEnvironmentId: prodEnv.id,
        },
      });
      const environment = {
        id: prodEnv.id,
        projectId: project.id,
        organizationId: organization.id,
        type: "PRODUCTION",
        organization: { ...organization, featureFlags: {} },
        project,
      } as unknown as AuthenticatedEnvironment;

      const tasks = [1, 2, 3, 4, 5].map((n) => ({
        id: `task-${n}`,
        description: n === 3 ? "bad\u0000byte" : `task ${n}`,
        filePath: `src/trigger/task-${n}.ts`,
        exportName: `task${n}`,
      }));
      const metadata = { contentHash: "fr003", tasks } as unknown as BackgroundWorkerMetadata;

      const entries = await createWorkerResources(metadata, worker, environment, prisma);
      const rows = await prisma.backgroundWorkerTask.findMany({
        where: { workerId: worker.id },
        select: { slug: true },
        orderBy: { slug: "asc" },
      });
      console.log(
        `FR-003 resolved without error: entries=${entries.map((e) => e.slug).join(",")} rows=${rows
          .map((r) => r.slug)
          .join(",")}`
      );
      expect(entries.map((e) => e.slug).sort()).toEqual(["task-1", "task-2", "task-4", "task-5"]);
      expect(rows.map((r) => r.slug)).toEqual(["task-1", "task-2", "task-4", "task-5"]);
    }
  );
});
