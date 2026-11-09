// FR-002 reproduction (labelling, not part of the upstream suite).
// run: cd apps/supervisor && pnpm exec vitest --run src/FR-002.test.ts
//
// Claim under test: a warm-start receiver that accepts and never answers stalls
// the supervisor's dequeue path ("each stuck message holds its slot"), so runs
// stop starting and the warm_start phase climbs without bound.
//
// 1. Real SupervisorSession + RunQueueConsumer against a local platform HTTP
//    server. The runQueueMessage listener performs the same fetch tryWarmStart
//    makes (POST, JSON body, no signal) to a TCP server that accepts and never
//    replies. We check whether the consumer keeps dequeuing while it hangs.
// 2. The same fetch, left to Node's built-in fetch defaults, to see whether it
//    hangs forever or rejects (tryWarmStart's catch then returns false and the
//    handler falls through to createWorkload).
import { createServer, type Server } from "node:http";
import { createServer as createTcpServer, type Server as TcpServer, type Socket } from "node:net";
import type { AddressInfo } from "node:net";
import { SupervisorSession } from "@trigger.dev/core/v3/workers";
import { afterEach, describe, expect, it } from "vitest";
import { z } from "zod";

async function startPlatform() {
  let dequeueCount = 0;
  let id = 0;
  const server = createServer((req, res) => {
    const reply = (body: unknown) => {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(body));
    };
    if (req.url?.endsWith("/connect")) {
      reply({ ok: true, workerGroup: { type: "MANAGED", name: "test" } });
    } else if (req.url?.endsWith("/dequeue")) {
      dequeueCount++;
      reply([{ id: `message_${++id}` }]);
    } else {
      reply({ ok: true });
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return { server, url: `http://127.0.0.1:${port}`, dequeues: () => dequeueCount };
}

/** Accepts TCP connections, reads the request, never writes a byte back. */
async function startBlackhole() {
  const sockets: Socket[] = [];
  const server = createTcpServer((s) => {
    sockets.push(s);
    s.on("data", () => {});
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return { server, sockets, url: `http://127.0.0.1:${port}` };
}

/** The request tryWarmStart makes (apps/supervisor/src/index.ts:873-877). */
function warmStartFetch(base: string, dequeuedMessage: unknown) {
  return fetch(new URL("/warm-start", base).href, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dequeuedMessage }),
  });
}

let platform: Server | undefined;
let blackhole: TcpServer | undefined;
let blackholeSockets: Socket[] = [];
let session: SupervisorSession | undefined;

afterEach(async () => {
  await session?.stop();
  session = undefined;
  platform?.closeAllConnections();
  if (platform) await new Promise((r) => platform!.close(r));
  blackholeSockets.forEach((s) => s.destroy());
  if (blackhole) await new Promise((r) => blackhole!.close(r));
  platform = undefined;
  blackhole = undefined;
});

describe("FR-002", () => {
  it("keeps dequeuing while every warm-start call hangs", async () => {
    const api = await startPlatform();
    platform = api.server;
    const hole = await startBlackhole();
    blackhole = hole.server;
    blackholeSockets = hole.sockets;

    session = new SupervisorSession({
      apiUrl: api.url,
      workerToken: "test-token",
      instanceName: "test",
      heartbeatIntervalSeconds: 60,
      dequeueIntervalMs: 10,
      dequeueIdleIntervalMs: 10,
      runNotificationsEnabled: false,
      scaling: { strategy: "none", maxConsumerCount: 1 },
      resolveResponseSchema: <T>(_schema: T) => z.any() as unknown as T,
    });

    let started = 0;
    let settled = 0;
    session.on("runQueueMessage", async ({ message }) => {
      started++;
      try {
        await warmStartFetch(hole.url, message);
      } catch {
        // tryWarmStart's catch: return false, then createWorkload
      } finally {
        settled++;
      }
    });

    await session.start();
    await new Promise((r) => setTimeout(r, 2_000));

    console.log(
      `FR-002 one consumer, 2s: dequeues=${api.dequeues()} handlersStarted=${started} handlersSettled=${settled} openWarmStartSockets=${hole.sockets.length}`
    );
    // The consumer loop does not wait on the handler: many dequeues with one consumer.
    expect(api.dequeues()).toBeGreaterThan(10);
    expect(started).toBeGreaterThan(10);
    // ...and every warm-start call is still hanging.
    expect(settled).toBe(0);
  });

  it(
    "a hung warm-start fetch rejects at Node's default headers timeout",
    async () => {
      const hole = await startBlackhole();
      blackhole = hole.server;
      blackholeSockets = hole.sockets;

      const t0 = performance.now();
      const error = await warmStartFetch(hole.url, { id: "m" }).then(
        () => null,
        (e: unknown) => e as Error & { cause?: { code?: string } }
      );
      const seconds = (performance.now() - t0) / 1000;
      console.log(
        `FR-002 hung fetch: rejected after ${seconds.toFixed(1)}s with ${error?.message} cause=${error?.cause?.code}`
      );
      expect(error?.cause?.code).toBe("UND_ERR_HEADERS_TIMEOUT");
      expect(seconds).toBeGreaterThan(290);
      expect(seconds).toBeLessThan(320);
    },
    400_000
  );
});
