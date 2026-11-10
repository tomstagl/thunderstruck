// FR-001 reproduction (labelling, not part of the upstream suite).
// run: cd apps/webapp && pnpm exec vitest --run test/FR-001.test.ts --reporter=verbose
//      (with the env block of .github/workflows/unit-tests-webapp.yml)
//
// Claim: executeQuery acquires a concurrency slot, then awaits getDefaultPeriod/getLimit
// (a billing-platform lookup) outside the try/finally that releases it; if that lookup
// throws or times out the slot leaks and later queries are rejected at the limit.
// Setup: a real Redis (testcontainers) for the limiter; the billing client enabled
// (cloud origin + BILLING_API_URL) against a local HTTP server that resets every
// connection or returns malformed JSON. No mocks.
import { redisTest } from "@internal/testcontainers";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import Redis from "ioredis";
import { describe, expect, vi } from "vitest";

vi.setConfig({ testTimeout: 120_000 });

describe("FR-001", () => {
  redisTest(
    "a failing billing lookup leaves no slot behind and no query is rejected",
    async ({ redisOptions }) => {
      let mode: "reset" | "garbage" = "reset";
      let billingCalls = 0;
      const billing = createServer((req, res) => {
        billingCalls++;
        if (mode === "reset") req.socket.destroy();
        else {
          res.writeHead(200, { "content-type": "application/json" });
          res.end("{not json");
        }
      });
      await new Promise<void>((r) => billing.listen(0, "127.0.0.1", r));
      const { port } = billing.address() as AddressInfo;

      process.env.LOGIN_ORIGIN = "https://fr001.triggerlabs.dev"; // isCloud() -> true
      process.env.BILLING_API_URL = `http://127.0.0.1:${port}`;
      process.env.BILLING_API_KEY = "fr001";
      process.env.RATE_LIMIT_REDIS_HOST = redisOptions.host;
      process.env.RATE_LIMIT_REDIS_PORT = String(redisOptions.port);
      process.env.RATE_LIMIT_REDIS_PASSWORD = redisOptions.password ?? "";
      process.env.RATE_LIMIT_REDIS_TLS_DISABLED = "true";
      process.env.QUERY_DEFAULT_ORG_CONCURRENCY_LIMIT = "2";

      // env.server parses process.env at import, so these modules load after the env is set.
      const { getLimit } = await import("~/services/platform.v3.server");
      const { executeQuery } = await import("~/services/queryService.server");
      const redis = new Redis(redisOptions);

      const slots = async () => {
        const keys = await redis.keys("query:concurrency*");
        let total = 0;
        for (const k of keys) if ((await redis.type(k)) === "zset") total += await redis.zcard(k);
        return { keys: keys.length, total };
      };

      try {
        // The lookup the finding names does not throw: getLimits catches and getLimit falls back.
        for (const m of ["reset", "garbage"] as const) {
          mode = m;
          expect(await getLimit("org_fr001", "queryPeriodDays", 30)).toBe(30);
        }

        const outcomes: string[] = [];
        for (let i = 0; i < 6; i++) {
          mode = i % 2 === 0 ? "reset" : "garbage";
          const r = await executeQuery({
            organizationId: "org_fr001",
            projectId: "proj_fr001",
            environmentId: "env_fr001",
            scope: "environment",
            query: "SELECT run_id FROM runs LIMIT 1",
            ...(i === 4 ? { from: "not-a-date" } : {}),
            ...(i === 5 ? { period: "garbage" } : {}),
          } as any).then(
            (res: any) =>
              res.success ? "ok" : `fail:${String(res.error?.message).slice(0, 60)}`,
            (e: Error) => `threw:${e.message.split("\n").filter(Boolean)[0]?.slice(0, 60)}`
          );
          outcomes.push(r);
        }
        const after = await slots();
        console.log(`FR-001 billingCalls=${billingCalls} outcomes=${JSON.stringify(outcomes)}`);
        console.log(`FR-001 limiter entries after 6 calls at limit 2: ${JSON.stringify(after)}`);

        expect(billingCalls).toBeGreaterThanOrEqual(12);
        expect(outcomes.some((o) => o.includes("concurrency"))).toBe(false);
        expect(after.total).toBe(0);
      } finally {
        await redis.quit();
        await new Promise((r) => billing.close(r));
      }
    }
  );
});
