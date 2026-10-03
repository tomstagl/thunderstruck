# Stability pattern catalog — tiers A and B

Every finding must map to at least one of these IDs, or to `OTHER` with a justification. A pattern is 'missing' when the code that needs it does not have it — not merely when a detector said so.

## Tier A — highest weight

### S01 — Timeouts on every external call

Failure if absent: Blocked threads or a stalled event loop. One hung dependency holds connections open until the whole app stops serving.
Typical role in a metastable failure: **amplifier**.
References: Nygard, Release It! (2nd ed.), ch. 5 — Timeouts; Amazon Builders' Library — Timeouts, retries and backoff with jitter

### S02 — Capped exponential backoff with full jitter

Failure if absent: Synchronised retries hammer a recovering dependency and hold it down — the classic thundering herd. Uncapped growth parks work for minutes.
Typical role in a metastable failure: **sustaining**.
References: Brooker, Exponential Backoff And Jitter (AWS Architecture Blog); Nygard, Release It! (2nd ed.), ch. 5 — Retries

### S03 — Honor server pushback (Retry-After, 429/503)

Failure if absent: Retries land inside a window the server has already told you is closed, so the limiter never gets a chance to reopen.
Typical role in a metastable failure: **sustaining**.
References: RFC 9110 §10.2.3 — Retry-After; Google SRE Book, ch. 21 — Handling Overload

### S04 — Retry only transient errors

Failure if absent: Retrying a 4xx burns the retry budget on requests that can never succeed, and hides the bug that caused them.
Typical role in a metastable failure: **amplifier**.
References: Amazon Builders' Library — Timeouts, retries and backoff with jitter

### S05 — Client-side rate limiting / budget gating

Failure if absent: A shared quota is exhausted by one caller, and every other caller on that quota starts failing.
Typical role in a metastable failure: **trigger**.
References: Google SRE Book, ch. 21 — Handling Overload; Nygard, Release It! (2nd ed.), ch. 5 — Governor

### S06 — Request prioritization (interactive over background)

Failure if absent: Batch work starves user-facing requests: both queue behind the same limiter, and the batch always wins on volume.
Typical role in a metastable failure: **amplifier**.
References: Google SRE Book, ch. 21 — Criticality; Nygard, Release It! (2nd ed.), ch. 5 — Shed Load

### S07 — Idempotent, resumable jobs

Failure if absent: A crash mid-job restarts from zero or writes duplicates. Every retry pays the full cost again, so the job never gets further than the failure point.
Typical role in a metastable failure: **sustaining**.
References: Nygard, Release It! (2nd ed.), ch. 5 — Handshaking / Steady State; Google SRE Book, ch. 22 — Addressing Cascading Failures

### S08 — Bounded result sets and pagination

Failure if absent: Memory exhaustion, timeouts, and oversized LLM prompts as the data grows. Works fine until one row count crosses a threshold.
Typical role in a metastable failure: **amplifier**.
References: Nygard, Release It! (2nd ed.), ch. 4 — Unbounded Result Sets

### S09 — Single-flight / request coalescing plus caching

Failure if absent: N concurrent cache misses become N identical upstream calls. After an eviction or an error-driven invalidation, the miss flood keeps the dependency down even once the original trigger is gone.
Typical role in a metastable failure: **sustaining**.
References: Bronson et al., Metastable Failures in Distributed Systems (HotOS '21); Nygard, Release It! (2nd ed.), ch. 5 — Caching

### S10 — Retry at one layer plus a retry budget

Failure if absent: Retry amplification. R retries at each of N nested layers is R^N requests to the dependency that is already struggling.
Typical role in a metastable failure: **amplifier**.
References: Google SRE Book, ch. 22 — Addressing Cascading Failures; Amazon Builders' Library — Timeouts, retries and backoff with jitter

### S27 — No blocking calls on non-blocking/event-loop threads

Failure if absent: A blocking call inside a reactive pipeline or an event-loop handler occupies a thread meant to service many concurrent requests. One slow call starves the whole event loop instead of one request.
Typical role in a metastable failure: **amplifier**.
References: Project Reactor reference docs — Schedulers and blocking calls; Nygard, Release It! (2nd ed.), ch. 4 — Blocked Threads

### S28 — Bounded, timed lock/wait acquisition

Failure if absent: A lock held across a slow call, or a wait with no bound, lets one stalled holder block every other thread indefinitely — a convoy that compounds under load instead of shedding it.
Typical role in a metastable failure: **sustaining**.
References: Nygard, Release It! (2nd ed.), ch. 4 — Blocked Threads; java.util.concurrent.locks.Lock javadoc — tryLock(long, TimeUnit)

### S29 — Bounded query fan-out (no N+1 lazy-loading amplification)

Failure if absent: Iterating a result set and touching a lazy association per row turns one query into N+1. Under load this is a fan-out amplifier — the same mechanism as an unbounded result set, but produced by ORM lazy loading rather than a missing limit.
Typical role in a metastable failure: **amplifier**.
References: Hibernate ORM user guide — Fetching; Nygard, Release It! (2nd ed.), ch. 4 — Unbounded Result Sets

### S30 — Liveness checks only the process itself

Failure if absent: A liveness probe that checks a dependency restarts healthy pods when the dependency slows. Restarts cut capacity, the survivors take more load and fail their probes too: the restart loop outlives the original blip.
Typical role in a metastable failure: **sustaining**.
References: Kubernetes docs — Configure Liveness, Readiness and Startup Probes; Nygard, Release It! (2nd ed.), ch. 4 — Chain Reactions

## Tier B — lower weight

### S11 — Deadline propagation across hops

Failure if absent: Downstream work keeps running after the caller has already given up, spending capacity on results nobody will read.
Typical role in a metastable failure: **amplifier**.
References: Google SRE Book, ch. 22 — Deadlines

### S12 — Circuit breaker or retry token bucket

Failure if absent: The client keeps calling a dependency that is already dead, so the dependency never gets the quiet it needs to come back.
Typical role in a metastable failure: **sustaining**.
References: Nygard, Release It! (2nd ed.), ch. 5 — Circuit Breaker

### S13 — Bulkheads (separate pools, queues, workers)

Failure if absent: Background work exhausts the resources request handling needs, so a batch job takes the web tier down with it.
Typical role in a metastable failure: **amplifier**.
References: Nygard, Release It! (2nd ed.), ch. 5 — Bulkheads

### S14 — Bounded queues with backpressure or load shedding

Failure if absent: Unbounded latency and memory growth under load. The queue absorbs the overload instead of rejecting it, and never drains.
Typical role in a metastable failure: **sustaining**.
References: Nygard, Release It! (2nd ed.), ch. 4 — Blocked Threads; Google SRE Book, ch. 21 — Load Shedding

### S15 — Graceful degradation and fallbacks

Failure if absent: One dependency being down turns the whole feature into an error, instead of a reduced but working response.
Typical role in a metastable failure: **amplifier**.
References: Nygard, Release It! (2nd ed.), ch. 5 — Fail Fast / Decoupling Middleware

### S16 — Jitter on periodic work

Failure if absent: Self-inflicted bursts. Every instance fires at :00 together and the dependency sees its whole day's peak in one second.
Typical role in a metastable failure: **trigger**.
References: Google SRE Book, ch. 24 — Distributed Periodic Scheduling; Brooker, Exponential Backoff And Jitter

### S17 — Steady state (TTLs, cleanup, growth bounds)

Failure if absent: Slow resource exhaustion. Fine for weeks, then the cache or the table crosses a limit and the process dies at 3am.
Typical role in a metastable failure: **trigger**.
References: Nygard, Release It! (2nd ed.), ch. 5 — Steady State

### S18 — Fail fast (validate before expensive work)

Failure if absent: Expensive calls are made for requests that were always going to fail validation, wasting exactly the capacity that is scarce under load.
Typical role in a metastable failure: **amplifier**.
References: Nygard, Release It! (2nd ed.), ch. 5 — Fail Fast

### S19 — No error swallowing; failures stay observable

Failure if absent: Silent data drift. The write path fails, nothing is logged, and the divergence is only discovered months later by a user.
Typical role in a metastable failure: **sustaining**.
References: Nygard, Release It! (2nd ed.), ch. 17 — Transparency; Google SRE Book, ch. 6 — Monitoring Distributed Systems

## Tier C — named but not scanned

Use these IDs if the evidence supports them; nothing detects them.

- **S20** Shuffle sharding — One bad tenant degrades every tenant sharing its shard.
- **S21** Cell-based architecture — Blast radius of any failure is the whole fleet.
- **S22** Static stability across AZs and regions — Recovery depends on the control plane that is itself impaired.
- **S23** Adaptive concurrency limits — A fixed limit is wrong at both ends: throttling when healthy, overloading when degraded.
- **S24** Multi-level criticality shedding — Overload sheds load indiscriminately, dropping critical work with the rest.
- **S25** Hedged requests — Tail latency is set by the slowest replica on every request.
- **S26** Leader-election hardening — Split brain or a stuck leader stalls all coordinated work.

## The metastability question

A metastable failure needs a vulnerable state, a trigger, and a **sustaining effect** that keeps the system failing after the trigger is gone. For every hypothesis, ask: once this is triggered, what keeps it failing? Common answers: retries consuming the budget recovery needs; failed jobs re-queuing at full cost; errors invalidating caches into a miss flood; expensive work regenerated on every failed request. If nothing sustains it, say so — `sustaining_effect` may be null, but it may never be omitted.
