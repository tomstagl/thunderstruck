---
name: stability-catalog
description: Stability patterns for code that calls external systems - timeouts, capped backoff with jitter, honouring Retry-After, transient-only retry, rate limiting, idempotent resumable jobs, bounded result sets, single-flight caching, retry budgets, circuit breakers, bulkheads, backpressure, jitter on periodic work. Use when writing or reviewing code that makes HTTP calls, queries a database, publishes to or consumes from a queue, calls an LLM API, or runs on a schedule - and when asked how code fails under load, what a thundering herd or metastable failure is, or why a retry loop is wrong.
---

# Stability patterns

Reference for code that crosses a process boundary. The patterns come from
Nygard's *Release It!*, the Amazon Builders' Library, the Google SRE book and
the metastable-failure literature.

Use it when writing or reviewing anything that calls an external system. The
question these answer is not "is this correct?" but **"what happens to this
under load, or when the thing it depends on is already struggling?"**

`${CLAUDE_SKILL_DIR}/references/patterns.md` has every pattern with its
failure mode and what the detectors look for. It is generated from
`${CLAUDE_PLUGIN_ROOT}/catalog/stability.yaml`, so it matches what
`/thunderstruck-scan` actually checks.

## The ones that matter most

**Timeouts on every external call (S01).** Connect, read and total. A call
with no timeout is a thread that can be held forever by someone else's
outage.

**Capped exponential backoff with full jitter (S02).** Growth alone is not
enough. Without a cap, late attempts park a worker for minutes; without
jitter, every client that failed together retries together, and the herd
re-forms on the dependency that is trying to recover.

**Honour server pushback (S03).** A 429 or 503 with `Retry-After` is the
server telling you exactly when to come back. Backing off on your own
schedule instead means landing inside a window you were told was closed.

**Retry only transient errors (S04).** Retrying a 400 spends the budget on
requests that can never succeed, and hides the bug that caused them.

**Retry at one layer, with a budget (S10).** Retries at the SDK, the client
and the job multiply: three layers of three attempts is 27 requests, not 9.
Pick one layer. Give it a budget.

**Idempotent, resumable work (S07).** A job that cannot resume restarts from
zero after every crash, paying the full cost again — and if its writes are
not idempotent, duplicating them too.

**Single-flight (S09).** N concurrent cache misses must produce one upstream
call. Without deduplication, an eviction turns into a stampede, and an error
that invalidates a cache turns into a sustained one.

## The question that gets missed

Most reviews ask what triggers a failure. The harder question is what
**sustains** it:

> Once this is failing, what keeps it failing after the trigger is gone?

That is the difference between an incident that drains in seconds and one
that needs a human to break the loop. Retries consuming the capacity recovery
needs, failed jobs re-queuing at full cost, an error path that floods a cold
cache — these are why systems stay down after the cause is fixed.

If the answer is "nothing, it recovers on its own", say so. That is a real
property and worth writing down.

## Applying this

When reviewing, name the pattern and the consequence, not just the smell:
"this retries on any exception (S04), so a 400 burns the budget three times
and the real error is never surfaced" beats "consider narrowing this except".

When writing, the defaults worth reaching for: a timeout on every call, one
retry layer with capped jittered backoff that honours `Retry-After`, a
persisted cursor on anything that loops, an explicit bound on every result
set, and a TTL on every cache.

To find where an existing repository violates these, run
`/thunderstruck-scan`.
