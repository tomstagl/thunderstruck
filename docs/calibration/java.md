# Java detector calibration

Synthetic samples prove that a detector's regex matches what it was written
for. They do not prove it behaves on code nobody wrote for the test.
Calibration closes that gap: each batch of Java detectors is swept with
`scripts/calibrate.py` over every tracked, non-test Java file of several real
public repositories. Every hit is inspected by hand and judged against the
pattern's `failure_if_absent`, and each false positive either tightens the
detector (with a `negative_<shape>.java` sample reproducing the real-world
shape) or is recorded with a reason. This log is what a detector's
`confidence` rests on. The method is set out in the
[design spec, §5](../superpowers/specs/2026-09-23-java-language-support-design.md#5-test-strategy).

Column meanings: **Hits** counts every hit a detector produced across the
batch's repositories before any fix. **Final** counts the hits left in the
final sweep, the one recorded under **Hits** below. An `FP-fixed` hit is gone
from the final sweep by definition, so it is listed separately under
**Fixed during calibration**.

## Batch 1 — JDK/core (Tasks 5–6): S01, S27, S28, S13, S14, S02, S03, S04

Task 5 covered S01, S27, S28, S13 and S14. Task 6 added S02, S03 and S04,
swept the same five repositories plus spring-petclinic-microservices, and
re-swept the Task 5 detectors after its two rulings below. That re-sweep
matched Task 5's final sweep exactly.

| Repo | Commit | Java files swept |
|---|---|---|
| jhy/jsoup | `49a15317317970a7ea3f0a5ded303ef319860f4a` | 98 |
| brettwooldridge/HikariCP | `a4d93f4f85517f90e632b795486d7102e933d7ff` | 49 |
| apache/commons-pool | `c4aba65cd8445685f89422b18219ea9853e4306d` | 57 |
| spring-petclinic/spring-petclinic-reactive | `68534cf88a9d022467b9590b953ea4fc7f78bd6b` | 39 |
| spring-projects/spring-petclinic | `818c4136ea971c21674525f9053de0d9c7ad8cfe` | 30 |
| spring-petclinic/spring-petclinic-microservices (Task 6 only) | `295fa8d5ee10f7b6daddf83a2c65f9051a87564b` | 53 |

| Detector | Hits | TP | FP-fixed | FP-accepted | Deferred | Final |
|---|---|---|---|---|---|---|
| S01-java-httpclient-no-connect-timeout | 1 | 0 | 1 | 0 | | 0 |
| S01-java-httprequest-no-timeout | 0 | 0 | 0 | 0 | | 0 |
| S01-java-okhttp-no-timeout | 0 | 0 | 0 | 0 | | 0 |
| S01-java-jdbc-no-login-timeout | 0 | 0 | 0 | 0 | | 0 |
| S01-java-future-get-no-timeout | 0 | 0 | 0 | 0 | | 0 |
| S27-java-blocking-in-reactive | 0 | 0 | 0 | 0 | | 0 |
| S28-java-monitor-held-across-io | 0 | 0 | 0 | 0 | | 0 |
| S28-java-untimed-lock-across-io | 0 | 0 | 0 | 0 | | 0 |
| S28-java-untimed-wait | 5 | 1 | 4 | 0 | | 1 |
| S13-java-shared-executor | 0 | 0 | 0 | 0 | | 0 |
| S14-java-unbounded-blocking-queue | 1 | 0 | 1 | 0 | | 0 |
| S14-java-executors-unbounded-queue | 0 | 0 | 0 | 0 | | 0 |
| S02-java-backoff | 0 | 0 | 0 | 0 | | 0 |
| S02-java-retryable-no-jitter | 0 | 0 | 0 | 0 | | 0 |
| S03-java-429-ignores-retry-after | 0 | 0 | 0 | 0 | | 0 |
| S03-java-503-ignores-retry-after | 0 | 0 | 0 | 0 | | 0 |
| S04-java-catch-all-retry | 0 | 0 | 0 | 0 | | 0 |
| S04-java-retryable-all-exceptions | 0 | 0 | 0 | 0 | | 0 |

No detector came near the 25-hits-per-repo tripwire. The largest count was
5, for S28-java-untimed-wait in commons-pool.

### Hits

- `S28-java-untimed-wait` commons-pool `src/main/java/org/apache/commons/pool3/impl/GenericKeyedObjectPool.java:780` — TP: `create(key)` waits on `makeObjectCountLock` with no bound while another thread's `makeObject()` is in flight, so a hung factory call (for example, connecting to an unreachable database) parks every borrower of that key forever, whatever `borrowMaxWaitMillis` says. The non-keyed `GenericObjectPool.create` bounds the same wait with `remainingWaitDuration`.

### Fixed during calibration

- `S01-java-httpclient-no-connect-timeout` jsoup `src/main/java11/org/jsoup/helper/HttpClientExecutor.java:87` — FP-fixed: the client has no `connectTimeout()`, but the request built in the same file gets `HttpRequest.Builder.timeout(...)` from the connection's configured timeout. `HttpClientExecutor.java:108` sets it only `if (req.timeout() > 0)`. A timeout of 0 means infinite, which the caller has to choose explicitly, because jsoup defaults to 30 s (`HttpConnection.java:637`). In `java.net.http` the request timeout starts before the connection is made, so it bounds the connect too. The detector is now `file_absent`: it is silent when the file calls `connectTimeout(` or `.timeout(` with an argument anywhere. (Task 6 changed the alternative to `\.\s*timeout\s*\(\s*[^\s)]` so that a zero-arg getter such as `req.timeout()` no longer silences it. jsoup stays silent through `reqBuilder.timeout(Duration…)`.) → `S01/java/negative_request_timeout.java`
- `S14-java-unbounded-blocking-queue` commons-pool `src/main/java/org/apache/commons/pool3/impl/SoftReferenceObjectPool.java:69` — FP-fixed: `idleReferences = new LinkedBlockingDeque<>()` holds idle pooled objects waiting to be borrowed, not pending work, so it cannot absorb request overload. The detector now skips a line that assigns the queue to an `idle*` name. (Task 5 also skipped `free*`/`spare*`. Task 6 dropped both: no calibration hit supported them, and `free` substring-matched names like `lockFreeQueue`.) → `S14/java/negative_idle_object_pool.java`
- `S28-java-untimed-wait` commons-pool `src/main/java/org/apache/commons/pool3/impl/LinkedBlockingDeque.java:1057` — FP-fixed: `putFirst` implements `BlockingDeque.put*`, whose contract is to block until space is available. The timed variants (`offerFirst(e, timeout, unit)`) are the caller's bounded option. The detector now skips an untimed `await()`/`wait()` that has an `@Override` `put*`/`take*` signature within the 8 lines before it → `S28/java/negative_blocking_queue_contract.java`
- `S28-java-untimed-wait` commons-pool `src/main/java/org/apache/commons/pool3/impl/LinkedBlockingDeque.java:1079` — FP-fixed: `putLast`, same contract as above → `S28/java/negative_blocking_queue_contract.java`
- `S28-java-untimed-wait` commons-pool `src/main/java/org/apache/commons/pool3/impl/LinkedBlockingDeque.java:1319` — FP-fixed: `takeFirst`, the `BlockingDeque.take*` contract (`pollFirst(timeout, unit)` is the bounded variant) → `S28/java/negative_blocking_queue_contract.java`
- `S28-java-untimed-wait` commons-pool `src/main/java/org/apache/commons/pool3/impl/LinkedBlockingDeque.java:1340` — FP-fixed: `takeLast`, same contract → `S28/java/negative_blocking_queue_contract.java`

### Silences checked

- HikariCP: its executors use `new LinkedBlockingQueue<>(queueSize)` (bounded) and `Executors.newCachedThreadPool` (a direct hand-off, not a queued pool), so S14 stays silent, which is correct. There is no `java.net.http`, OkHttp or untimed wait in `src/main`.
- spring-petclinic-reactive: `src/main` has no `block()`, `Thread.sleep` or `synchronized`, so S27 and S28 are silent, which is correct. There is nothing to report.
- spring-petclinic (Spring MVC): S27 is silent as required.
- S02–S04 (Task 6) produced no hits in any of the six repositories. Every candidate construct was checked by hand:
  - No repository has a Java `@Retryable`. spring-petclinic-microservices retries through Spring Cloud Gateway configuration (`spring-petclinic-api-gateway/src/main/resources/application.yml`: `Retry` filter, `retries: 1`, `statuses: SERVICE_UNAVAILABLE`, POST only), which is YAML and outside Java detection. It is also transient-only, so it is correct.
  - spring-petclinic-microservices `FallbackController.java:13` returns `SC_SERVICE_UNAVAILABLE` but retries nothing. S03's `require` gate keeps it silent, which is correct.
  - The `catch (Exception|Throwable …)` blocks in jsoup, HikariCP, commons-pool and the genai service log, rethrow, clean up or return a fallback. None is followed by a retry within 6 lines, so S04 is silent, which is correct.
  - HikariCP `UtilityElf.java:80` `Thread.sleep(millis)` is the body of the generic `quietlySleep` helper, not a retry construct. S02 stays silent, which is correct.

### Known limitations (noted, not fixed)

- `S27-java-blocking-in-reactive`: `absent_within` accepts any `subscribeOn`/`publishOn`, including `Schedulers.parallel()`, which is itself a non-blocking scheduler. None of the batch's repositories exercised this.
- `S28-java-monitor-held-across-io`: the `}` boundary of the locked section also stops at a `}` inside a string literal, so a blocking call after such a literal inside the section is missed.
- `S14-java-unbounded-blocking-queue`: the `idle` exclusion is name-based. A genuine work queue named, say, `idleTasks` would be missed. That is a miss, not a false positive.
- `S01-java-httpclient-no-connect-timeout`: the suppression is file-wide. A file that builds a client with no connect timeout and has an unrelated `.timeout(` call (Reactor `Mono.timeout`, say) is now silent. That is also a miss, not a false positive.
- `S02-java-backoff` misses two real retry waits. Task 6 widened `SLEEP_RES["java"]` to any sleep-named call (`\b\w*[Ss]leep\w*\s*\(`), so both call sites below are now *matched*. A re-sweep of all six repositories with `--patterns S02` still produced 0 hits, because the handler's other gates hold:
  - HikariCP `pool/HikariPool.java:762` `quietlySleep(backoffMs)` sits in the connection-add loop. It doubles and caps (`Math.min(SECONDS.toMillis(5), backoffMs * 2)`) with no jitter. The wait is a variable, so `s02_backoff` judges jitter against the whole file, and the unrelated `ThreadLocalRandom` lifetime/keepalive variance at lines 493 and 501 counts as jitter. This is the shared handler's file-wide design and was not changed.
  - commons-pool `impl/ResilientPooledObjectFactory.java:89` calls a bare inherited `sleep(delay.toMillis())` in a `Thread` subclass. That is a fixed 1 s retry wait after `catch (final Throwable e)`. The file contains no retry vocabulary (`retry`/`attempt`/`backoff`, or a `catch` plus `continue`), so the handler's retry-context gate skips it. `S04-java-catch-all-retry` misses it for the same reason: nothing in its window says `attempt`/`retry`/`retries`.

  Both are misses, not false positives.
- `S02-java-backoff` (shared handler, AC-16): a polling loop that sleeps a literal and `continue`s inside a `try`/`catch` (for example `if (job == null) { Thread.sleep(500); continue; }`) reads as a retry construct, because the handler's `catch` + `continue` retry-context rule is shared with TS/Python. It reports a constant wait on what is only idle polling. This is a known false-positive shape, not fixed.
- `S02-java-backoff` (shared handler, AC-16): Java `long` literals (`Thread.sleep(2000L)`) and typed constants (`private static final long RETRY_DELAY_MS = 2000;`) are not recognised by the shared `_LITERAL_MS`/`_CONST_ASSIGN`. A constant retry wait written that way is missed.
- This batch had few true-positive surfaces: 1 TP across six repositories, and none for S02–S04. The confidence levels (`medium` for the JDK-primitive detectors, `low` otherwise) stay as set and are not raised.
