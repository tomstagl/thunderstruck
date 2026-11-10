// FR-015 reproduction (labelling, not part of the upstream suite).
// run: cd apps/webapp && pnpm exec vitest --run test/FR-015.test.ts --reporter=verbose
//      (with the env block of .github/workflows/unit-tests-webapp.yml)
//
// Claim: one module-level EnvironmentSchema.parse(process.env) (env.server.ts:2827)
// throws at import for a single bad value, including an optional knob or a cross-field
// rule, so every process importing it fails to start.
// Each case imports env.server fresh with one setting changed from a valid baseline.
import { describe, expect, it, vi } from "vitest";

const baseline = { ...process.env };

async function importWith(overrides: Record<string, string>) {
  vi.resetModules();
  process.env = { ...baseline, ...overrides };
  try {
    await import("~/env.server");
    return "started";
  } catch (e) {
    const err = e as { name?: string; issues?: Array<{ path: unknown[]; message: string }> };
    return `${err.name}: ${JSON.stringify(err.issues?.map((i) => [i.path.join("."), i.message]))}`;
  } finally {
    process.env = { ...baseline };
  }
}

describe("FR-015", () => {
  it("one bad setting fails the import of env.server", async () => {
    const cases: Record<string, Record<string, string>> = {
      baseline: {},
      optionalKnobNotInteger: { QUERY_GLOBAL_CONCURRENCY_LIMIT: "ten" },
      shardsWithoutNewStore: {
        RUN_OPS_SHARDS: '[{"key":"s1","url":"postgresql://u:p@localhost:5432/s1"}]',
      },
      shardsNotJson: { RUN_OPS_SHARDS: "not json" },
      issuerEqualsOidc: {
        RUN_TOKEN_ISSUER_URL: "https://issuer.example.com",
        OIDC_ISSUER_URL: "https://issuer.example.com",
      },
    };
    const results: Record<string, string> = {};
    for (const [name, overrides] of Object.entries(cases)) {
      results[name] = await importWith(overrides);
      console.log(`FR-015 ${name}: ${results[name].slice(0, 300)}`);
    }
    expect(results.baseline).toBe("started");
    expect(results.optionalKnobNotInteger).toMatch(/^ZodError/);
    expect(results.shardsNotJson).toMatch(/^ZodError/);
    expect(results.issuerEqualsOidc).toMatch(/^ZodError/);
  });
});
