<!-- Generated from catalog/stability.yaml by scripts/gen_catalog_docs.py. Do not edit by hand. -->

# Stability patterns

The failure each pattern prevents, and what its absence looks like in code. Tiers are defaults; a repository re-prioritises them in `.thunderstruck.toml`.

## Tier A

Scanned and reasoned about by default, at full weight.

### S01 — Timeouts on every external call

**Failure if absent.** Blocked threads or a stalled event loop. One hung dependency holds connections open until the whole app stops serving.

**Role in a metastable failure.** Usually the *amplifier*.

**What the detectors look for.**

- fetch() with no AbortSignal or timeout in the request options
- axios call with no timeout option
- node http(s) request with no timeout option
- requests call with no timeout= (requests blocks forever by default)
- httpx call with no explicit timeout= (httpx does default to 5s)
- urlopen() with no timeout=
- raw socket with no settimeout()

**References.** Nygard, Release It! (2nd ed.), ch. 5 — Timeouts; Amazon Builders' Library — Timeouts, retries and backoff with jitter

### S02 — Capped exponential backoff with full jitter

**Failure if absent.** Synchronised retries hammer a recovering dependency and hold it down — the classic thundering herd. Uncapped growth parks work for minutes.

**Role in a metastable failure.** Usually the *sustaining*.

**What the detectors look for.**

- retry backoff missing a cap, jitter, or growth

**References.** Brooker, Exponential Backoff And Jitter (AWS Architecture Blog); Nygard, Release It! (2nd ed.), ch. 5 — Retries

### S03 — Honor server pushback (Retry-After, 429/503)

**Failure if absent.** Retries land inside a window the server has already told you is closed, so the limiter never gets a chance to reopen.

**Role in a metastable failure.** Usually the *sustaining*.

**What the detectors look for.**

- file handles 429 but never reads Retry-After
- file handles 503 but never reads Retry-After

**References.** RFC 9110 §10.2.3 — Retry-After; Google SRE Book, ch. 21 — Handling Overload

### S04 — Retry only transient errors

**Failure if absent.** Retrying a 4xx burns the retry budget on requests that can never succeed, and hides the bug that caused them.

**Role in a metastable failure.** Usually the *amplifier*.

**What the detectors look for.**

- retry construct with no visible transient/permanent discrimination
- catch-all except followed by a retry — retries permanent errors too

**References.** Amazon Builders' Library — Timeouts, retries and backoff with jitter

### S05 — Client-side rate limiting / budget gating

**Failure if absent.** A shared quota is exhausted by one caller, and every other caller on that quota starts failing.

**Role in a metastable failure.** Usually the *trigger*.

**What the detectors look for.**

- HTTP calls made in a loop or fan-out with no local rate limiter or concurrency gate in this file
- rate limiting mentioned but server rate-limit headers are never read

**References.** Google SRE Book, ch. 21 — Handling Overload; Nygard, Release It! (2nd ed.), ch. 5 — Governor

### S06 — Request prioritization (interactive over background)

**Failure if absent.** Batch work starves user-facing requests: both queue behind the same limiter, and the batch always wins on volume.

**Role in a metastable failure.** Usually the *amplifier*.

**What the detectors look for.**

- one queue/limiter serves all callers; no priority or criticality field

**References.** Google SRE Book, ch. 21 — Criticality; Nygard, Release It! (2nd ed.), ch. 5 — Shed Load

### S07 — Idempotent, resumable jobs

**Failure if absent.** A crash mid-job restarts from zero or writes duplicates. Every retry pays the full cost again, so the job never gets further than the failure point.

**Role in a metastable failure.** Usually the *sustaining*.

**What the detectors look for.**

- paged/batched loop with no persisted cursor — a crash restarts from the beginning
- inserts with no upsert / ON CONFLICT — a replayed job duplicates rows

**References.** Nygard, Release It! (2nd ed.), ch. 5 — Handshaking / Steady State; Google SRE Book, ch. 22 — Addressing Cascading Failures

### S08 — Bounded result sets and pagination

**Failure if absent.** Memory exhaustion, timeouts, and oversized LLM prompts as the data grows. Works fine until one row count crosses a threshold.

**Role in a metastable failure.** Usually the *amplifier*.

**What the detectors look for.**

- Promise.all over an unbounded collection — concurrency equals input size
- Prisma findMany with no take: — result set grows with the table
- SELECT with no LIMIT
- asyncio.gather over an unbounded collection — concurrency equals input size
- full result-set fetch with no limit

**References.** Nygard, Release It! (2nd ed.), ch. 4 — Unbounded Result Sets

### S09 — Single-flight / request coalescing plus caching

**Failure if absent.** N concurrent cache misses become N identical upstream calls. After an eviction or an error-driven invalidation, the miss flood keeps the dependency down even once the original trigger is gone.

**Role in a metastable failure.** Usually the *sustaining*.

**What the detectors look for.**

- cache-aside read with no in-flight deduplication

**References.** Bronson et al., Metastable Failures in Distributed Systems (HotOS '21); Nygard, Release It! (2nd ed.), ch. 5 — Caching

### S10 — Retry at one layer plus a retry budget

**Failure if absent.** Retry amplification. R retries at each of N nested layers is R^N requests to the dependency that is already struggling.

**Role in a metastable failure.** Usually the *amplifier*.

**What the detectors look for.**

- more than one retry layer in the same call path, with no shared budget

**References.** Google SRE Book, ch. 22 — Addressing Cascading Failures; Amazon Builders' Library — Timeouts, retries and backoff with jitter

## Tier B

Scanned and reasoned about by default, at lower weight.

### S11 — Deadline propagation across hops

**Failure if absent.** Downstream work keeps running after the caller has already given up, spending capacity on results nobody will read.

**Role in a metastable failure.** Usually the *amplifier*.

**What the detectors look for.**

- outbound calls with no deadline or cancellation passed through

**References.** Google SRE Book, ch. 22 — Deadlines

### S12 — Circuit breaker or retry token bucket

**Failure if absent.** The client keeps calling a dependency that is already dead, so the dependency never gets the quiet it needs to come back.

**Role in a metastable failure.** Usually the *sustaining*.

**What the detectors look for.**

- retries with no circuit breaker or retry token bucket

**References.** Nygard, Release It! (2nd ed.), ch. 5 — Circuit Breaker

### S13 — Bulkheads (separate pools, queues, workers)

**Failure if absent.** Background work exhausts the resources request handling needs, so a batch job takes the web tier down with it.

**Role in a metastable failure.** Usually the *amplifier*.

**What the detectors look for.**

- one shared pool with no isolation between workloads

**References.** Nygard, Release It! (2nd ed.), ch. 5 — Bulkheads

### S14 — Bounded queues with backpressure or load shedding

**Failure if absent.** Unbounded latency and memory growth under load. The queue absorbs the overload instead of rejecting it, and never drains.

**Role in a metastable failure.** Usually the *sustaining*.

**What the detectors look for.**

- in-memory queue with no capacity bound or rejection path
- Queue() with no maxsize — unbounded by default

**References.** Nygard, Release It! (2nd ed.), ch. 4 — Blocked Threads; Google SRE Book, ch. 21 — Load Shedding

### S15 — Graceful degradation and fallbacks

**Failure if absent.** One dependency being down turns the whole feature into an error, instead of a reduced but working response.

**Role in a metastable failure.** Usually the *amplifier*.

**What the detectors look for.**

- external call with no fallback branch

**References.** Nygard, Release It! (2nd ed.), ch. 5 — Fail Fast / Decoupling Middleware

### S16 — Jitter on periodic work

**Failure if absent.** Self-inflicted bursts. Every instance fires at :00 together and the dependency sees its whole day's peak in one second.

**Role in a metastable failure.** Usually the *trigger*.

**What the detectors look for.**

- setInterval with no jitter or offset — every instance fires in lockstep
- cron schedule pinned to a fixed minute with no splay
- periodic loop with a fixed sleep and no jitter

**References.** Google SRE Book, ch. 24 — Distributed Periodic Scheduling; Brooker, Exponential Backoff And Jitter

### S17 — Steady state (TTLs, cleanup, growth bounds)

**Failure if absent.** Slow resource exhaustion. Fine for weeks, then the cache or the table crosses a limit and the process dies at 3am.

**Role in a metastable failure.** Usually the *trigger*.

**What the detectors look for.**

- in-memory cache with no TTL, eviction, or size bound

**References.** Nygard, Release It! (2nd ed.), ch. 5 — Steady State

### S18 — Fail fast (validate before expensive work)

**Failure if absent.** Expensive calls are made for requests that were always going to fail validation, wasting exactly the capacity that is scarce under load.

**Role in a metastable failure.** Usually the *amplifier*.

**What the detectors look for.**

- validation appears after an expensive external call

**References.** Nygard, Release It! (2nd ed.), ch. 5 — Fail Fast

### S19 — No error swallowing; failures stay observable

**Failure if absent.** Silent data drift. The write path fails, nothing is logged, and the divergence is only discovered months later by a user.

**Role in a metastable failure.** Usually the *sustaining*.

**What the detectors look for.**

- empty catch block — the failure leaves no trace
- catch block with no handling beyond a comment
- except: pass — the failure leaves no trace
- bare except catches SystemExit and KeyboardInterrupt too

**References.** Nygard, Release It! (2nd ed.), ch. 17 — Transparency; Google SRE Book, ch. 6 — Monitoring Distributed Systems

## Tier C — named, not scanned

No detectors ship for these. They are here so that a finding whose evidence supports one has an ID to use.

- **S20 Shuffle sharding** — One bad tenant degrades every tenant sharing its shard.
- **S21 Cell-based architecture** — Blast radius of any failure is the whole fleet.
- **S22 Static stability across AZs and regions** — Recovery depends on the control plane that is itself impaired.
- **S23 Adaptive concurrency limits** — A fixed limit is wrong at both ends: throttling when healthy, overloading when degraded.
- **S24 Multi-level criticality shedding** — Overload sheds load indiscriminately, dropping critical work with the rest.
- **S25 Hedged requests** — Tail latency is set by the slowest replica on every request.
- **S26 Leader-election hardening** — Split brain or a stuck leader stalls all coordinated work.

## The metastability lens

A metastable failure needs three things: a **vulnerable state**, a **trigger**, and a **sustaining effect** that keeps the system failing after the trigger is gone. The third is the one that gets missed, and it is the reason an incident outlives its cause.

Typical sustaining effects:

- Retries consuming exactly the capacity recovery needs.
- Failed jobs re-queuing at full cost, so the backlog never drains.
- Errors invalidating caches, turning recovery into a miss flood.
- Expensive work regenerated on every failed request.

When reviewing code that calls an external system, ask the question explicitly: *once this fails, what keeps it failing?* A clean answer of "nothing — it drains and recovers" is worth stating.

