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

### spring-retry surface (added in Task 7)

None of Batch 1's six repositories uses spring-retry, so Task 7 added one
repository that does. A GitHub code search (`gh search code "@Retryable"
--language=java`) listed it, and it is a non-fork application, not
spring-retry itself. It was swept with `--patterns S02,S04` only.

| Repo | Commit | Java files swept |
|---|---|---|
| iExecBlockchainComputing/iexec-core | `a09dbba123f09ae352410c87bcb3788610536809` | 129 |

| Detector | Hits | TP | FP-fixed | FP-accepted | Deferred | Final |
|---|---|---|---|---|---|---|
| S02-java-backoff | 0 | 0 | 0 | 0 | | 0 |
| S02-java-retryable-no-jitter | 3 | 3 | 0 | 0 | | 3 |
| S04-java-catch-all-retry | 0 | 0 | 0 | 0 | | 0 |
| S04-java-retryable-all-exceptions | 0 | 0 | 0 | 0 | | 0 |

#### Hits

- `S02-java-retryable-no-jitter` iexec-core `src/main/java/com/iexec/core/replicate/ReplicateSupplyService.java:88` — TP: `@Retryable(retryFor = OptimisticLockingFailureException.class, maxAttempts = 5)` has no `backoff`, so spring-retry waits a fixed 1 s between attempts. Workers that collided on the same optimistic lock all retry after the same 1 s, and they collide again. `RetryConfig.java` only declares `@EnableRetry`, and nothing in the repository customises the backoff.
- `S02-java-retryable-no-jitter` iexec-core `src/main/java/com/iexec/core/replicate/ReplicatesService.java:254` — TP: the same optimistic-lock retry on `updateReplicateStatus`, with `maxAttempts = 100` and a fixed 1 s wait. Contending status updates stay in phase for up to 99 s.
- `S02-java-retryable-no-jitter` iexec-core `src/main/java/com/iexec/core/result/ResultService.java:50` — TP: `@Retryable(retryFor = FeignException.class)` around an HTTP call to the result proxy uses the default 3 attempts, 1 s apart, with no jitter. Every caller that saw the proxy fail retries on the same beat.

#### Silences checked

- `S04-java-retryable-all-exceptions`: all three `@Retryable` sites name `retryFor`, so the detector stays silent, which is correct.
- `S04-java-catch-all-retry`: the five `catch (Exception|RuntimeException …)` blocks in `src/main` (`SmsService.java:182,231`, `BlockchainListener.java:70`, `DealWatcherService.java:239`, `Workflow.java:105`) log or return. None is inside a retry, so the detector stays silent, which is correct.
- `S02-java-backoff`: `src/main` contains no sleep-named call, so the detector stays silent, which is correct.

#### Known limitations

- `S04-java-retryable-all-exceptions`: `retryFor = FeignException.class` (`ResultService.java:50`) counts as a narrowed exception list. However, `FeignException` covers 4xx as well as 5xx and I/O errors, so a permanent 4xx from the proxy is retried too. That is a miss, not a false positive.

## Batch 2 — Spring/Hibernate, part 1 (Task 7): S01 Spring clients, S09, S16, S17

The sweep ran `--patterns S01,S09,S16,S17`. Only the two new S01 detectors
(`S01-java-resttemplate-no-timeout`, `S01-java-webclient-no-timeout`) are
inspected here, because Batch 1 already calibrated the other five. None of
those five fired in any repository below. The four repositories listed in
the brief come first. The last five were also swept: iexec-core because it
is the only one with a real `@Scheduled` fleet, and the four Batch 1
repositories to give S09 and S17 some library-style code.

| Repo | Commit | Java files swept |
|---|---|---|
| spring-projects/spring-petclinic | `818c4136ea971c21674525f9053de0d9c7ad8cfe` | 30 |
| spring-petclinic/spring-petclinic-microservices | `295fa8d5ee10f7b6daddf83a2c65f9051a87564b` | 53 |
| spring-projects/spring-data-examples | `7747029e6157cb780862826b6ae87c88d7a4df3c` | 6504 (6001 are the generated entities of `jpa/deferred`) |
| jhipster/jhipster-sample-app | `6b000b5d23a36c45e01472471b84a44fa2464044` | 81 |
| iExecBlockchainComputing/iexec-core | `a09dbba123f09ae352410c87bcb3788610536809` | 129 |
| jhy/jsoup | `49a15317317970a7ea3f0a5ded303ef319860f4a` | 98 |
| brettwooldridge/HikariCP | `a4d93f4f85517f90e632b795486d7102e933d7ff` | 49 |
| apache/commons-pool | `c4aba65cd8445685f89422b18219ea9853e4306d` | 57 |
| spring-petclinic/spring-petclinic-reactive | `68534cf88a9d022467b9590b953ea4fc7f78bd6b` | 39 |

| Detector | Hits | TP | FP-fixed | FP-accepted | Deferred | Final |
|---|---|---|---|---|---|---|
| S01-java-resttemplate-no-timeout | 1 | 1 | 0 | 0 | | 1 |
| S01-java-webclient-no-timeout | 2 | 2 | 0 | 0 | | 2 |
| S09-java-cache-aside-no-singleflight | 0 | 0 | 0 | 0 | | 0 |
| S09-java-cacheable-no-sync | 7 | 5 | 2 | 0 | | 5 |
| S16-java-scheduled-no-jitter | 17 | 1 | 16 | 0 | | 1 |
| S17-java-unbounded-cache | 0 | 0 | 0 | 0 | | 0 |

The largest count in one repository was 16, for S16 in iexec-core, which is
under the 25-hit tripwire.

### Tightened before calibration

Before the sweep, each detector was run against common shapes of correct
Java. Every shape that fired became a required-silent sample, and the
detector was then tightened until the sample passed. None of these fixes
came from a calibration hit, so none is counted in the table above.

- `S01-java-resttemplate-no-timeout`: `setRequestFactory(<configured factory>)` now counts as configured, but `setRequestFactory(new …())` does not. A timeout setter only counts when it has an argument, so a zero-arg getter like `props.connectTimeout()` no longer silences the detector → `S01/java/negative_resttemplate_request_factory.java`
- `S01-java-webclient-no-timeout`: `window_before: 8` is added so that a Reactor `HttpClient` configured just above the builder counts. `.clientConnector(<variable or injected connector>)` also counts as configured, but `.clientConnector(new …(…))` inline does not. `timeout(` and `responseTimeout(` must have an argument → `S01/java/negative_webclient_configured_connector.java` (Fix round 1 replaced this window form with a file-wide check; see below.)
- `S09-java-cache-aside-no-singleflight`:
  - The receiver must be *named* a cache: a name ending in `cache`, `caches` or `cachemap`, or starting with `cached`. A name like `cacheConfigurations` does not count.
  - `get(` needs an argument, so `ThreadLocal.get()` no longer counts.
  - The file must also write to the cache (`require: put`), so a read-only lookup table no longer counts.
  - `synchronized` or `lock()` in the file suppresses the hit, because that already serialises the load.

  → `S09/java/negative_synchronized_load.java`, `negative_read_only_cache.java` and `negative_non_cache_maps.java`
- `S09-java-cacheable-no-sync`: the window is now 8 (from 3), so `sync = true` on the fifth line of a multi-line annotation is seen → `S09/java/negative_multiline_sync.java`
- `S16-java-scheduled-no-jitter`: `@SchedulerLock` (ShedLock), on either side of `@Scheduled`, now suppresses the hit, because only one instance runs the job (`window_before: 3`) → `S16/java/negative_scheduler_lock.java`. The detector also has a sample that pins `fixedDelay` as silent: `S16/java/negative_fixed_delay.java`. A later probe, run after the first sweep, found a second false positive. With `window_before`, a `fixedRate` job declared within 3 lines of a cron job picked up that job's `cron =` through `present_within`. `cron =` is now part of the line pattern (`@Scheduled([^)]*cron =`), so the look-behind window can only suppress a hit, never cause one. A re-sweep of all nine repositories was byte-identical → `S16/java/negative_fixed_rate_after_cron.java`
- `S17-java-unbounded-cache`:
  - The same cache-name rule applies, and `memo(?!ry)` means `inMemoryUsers` is no longer a memo.
  - The file must construct an in-process map or a Caffeine builder (`require`).
  - Several constructs now count as a bound or as someone else's bound: `removeIf(`, a `size() >` check, `softValues`/`weakKeys`/`weakValues`, `Class`-keyed maps (bounded by the number of classes), and a Spring `CacheManager`/`getCache(` (the provider's configuration bounds it).

  → `S17/java/negative_explicit_eviction.java`, `negative_soft_values.java`, `negative_class_keyed.java`, `negative_cache_config_map.java`, `negative_in_memory_repository.java` and `negative_spring_cache_manager.java`

### Fix round 1 (review probes)

The Task 7 review ran fresh probes of common correct Spring code, and four of
them fired. Each shape now has a required-silent sample, and a re-sweep of all
nine repositories was byte-identical (9 hits).

- `S01-java-webclient-no-timeout` is now `file_absent`, with the same builder/create anchor. The window form missed a timeout that was set far from the builder: `.timeout(` 14 lines down a call chain, or `responseTimeout` in a separate `HttpClient` bean. Any argument-bearing `.timeout(`/`responseTimeout(`, `ReadTimeoutHandler` or `CONNECT_TIMEOUT_MILLIS` anywhere in the file suppresses the hit. So does a `clientConnector(…)` that is not a default connector (`new X()` or `new X(HttpClient.create())`), so `new ReactorClientHttpConnector(httpClient)` with an injected client counts as configured → `S01/java/negative_webclient_injected_httpclient.java` and `negative_webclient_per_call_timeout.java`
- `S09-java-cache-aside-no-singleflight` and `S17-java-unbounded-cache` now also `require` a field-declared cache: a line that starts with a modifier and assigns `new (Concurrent)HashMap` within one declaration (`[^;=(){}]*`, so the match cannot run from a method signature into its body), or a Caffeine/Guava `newBuilder(`. A map that is local to one method call dies with that call, so it can neither stampede a shared source nor grow without bound → `S09/java/negative_local_memo.java` and `S17/java/negative_local_memo.java`
- `S16-java-scheduled-no-jitter`: the window is now 10 lines, up from 3, so a random sleep at the top of the job body counts as jitter → `S16/java/negative_body_jitter.java`
- `S17/java/negative_explicit_eviction.java` now actually evicts (`nameCache.remove(…)` under the size check), and it still passes.

### Hits

- `S01-java-resttemplate-no-timeout` spring-petclinic-microservices `spring-petclinic-api-gateway/src/main/java/org/springframework/samples/petclinic/api/ApiGatewayApplication.java:56` — TP: the gateway's `@LoadBalanced` `RestTemplate` bean is `new RestTemplate()`, which uses `SimpleClientHttpRequestFactory` with no connect or read timeout. No code in `src/main` injects it today, so the risk is latent: the first caller inherits an unbounded wait.
- `S01-java-webclient-no-timeout` spring-petclinic-microservices `spring-petclinic-api-gateway/src/main/java/org/springframework/samples/petclinic/api/ApiGatewayApplication.java:62` — TP: the `@LoadBalanced` `WebClient.Builder` bean is `WebClient.builder()`, with no `responseTimeout`, and Reactor Netty has no response timeout by default. `CustomersServiceClient.getOwner` uses it with no `.timeout()`. `ApiGatewayController.getOwnerDetails` wraps only the visits call in the 10 s circuit-breaker `TimeLimiter`, not the owner call, so a hung customers-service holds the gateway request open indefinitely.
- `S01-java-webclient-no-timeout` spring-petclinic-microservices `spring-petclinic-genai-service/src/main/java/org/springframework/samples/petclinic/genai/AIBeanConfiguration.java:27` — TP: the same bare builder. `VectorStoreController.loadVetDataToVectorStoreOnStartup` calls `vets-service` through it and `.block()`s with no timeout, so a vets-service that accepts but never answers hangs genai-service startup.
- `S09-java-cacheable-no-sync` spring-petclinic `src/main/java/org/springframework/samples/petclinic/vet/VetRepository.java:45` — TP: `@Cacheable("vets")` on the no-argument `findAll()`. Every request that misses concurrently, on a cold start or after the entry is evicted, runs the same full-table query. The impact is small because the table is small.
- `S09-java-cacheable-no-sync` spring-petclinic `src/main/java/org/springframework/samples/petclinic/vet/VetRepository.java:55` — TP: the same, for `findAll(Pageable)`.
- `S09-java-cacheable-no-sync` spring-petclinic-microservices `spring-petclinic-vets-service/src/main/java/org/springframework/samples/petclinic/vets/web/VetResource.java:45` — TP: `@Cacheable("vets")` on the controller's `showResourcesVetList()`. Concurrent misses each call `vetRepository.findAll()`.
- `S09-java-cacheable-no-sync` spring-data-examples `jdbc/howto/caching/src/main/java/example.springdata/jdbc/howto/caching/MinionRepository.java:31` — TP: `@Cacheable("minions")` on `findById`, next to a `@CacheEvict` on `save`. After each save evicts an id, concurrent reads of that id all go to the database.
- `S09-java-cacheable-no-sync` spring-data-examples `jpa/example/src/main/java/example/springdata/jpa/caching/CachingUserRepository.java:35` — TP: `@Cacheable("byUsername")` on `findByUsername`, with the same evict-on-save shape.
- `S16-java-scheduled-no-jitter` jhipster-sample-app `src/main/java/io/github/jhipster/sample/service/UserService.java:290` — TP: `@Scheduled(cron = "0 0 1 * * ?")` `removeNotActivatedUsers` has no lock and no splay. Every instance of a scaled-out deployment runs the same find-and-delete against the same database at 01:00:00.

### Fixed during calibration

- `S09-java-cacheable-no-sync` jhipster-sample-app `src/main/java/io/github/jhipster/sample/repository/UserRepository.java:28` — FP-fixed (controller ruling after Task 7's first review): `@Cacheable(cacheNames = USERS_BY_EMAIL_CACHE, unless = "#result == null")`. Spring rejects `sync = true` when `unless` is present, so the lead points at a remedy the code cannot adopt. It is not actionable, and the detector now treats `unless =` in its window as suppressing → `S09/java/negative_cacheable_unless.java`
- `S09-java-cacheable-no-sync` jhipster-sample-app `src/main/java/io/github/jhipster/sample/repository/UserRepository.java:34` — FP-fixed: the same shape, for `USERS_BY_LOGIN_CACHE` → `S09/java/negative_cacheable_unless.java`
- `S16-java-scheduled-no-jitter` iexec-core: 16 hits — FP-fixed. Fifteen are `@Scheduled(fixedRate…)`: `chain/BlockchainListener.java:52`, `chain/DealWatcherService.java:214`, `detector/WorkerLostDetector.java:56`, and in `detector/replicate/`: `ContributionAndFinalizationUnnotifiedDetector.java:51`, `ContributionUnnotifiedDetector.java:51`, `ReplicateResultUploadTimeoutDetector.java:54`, `RevealTimeoutDetector.java:49`, `RevealUnnotifiedDetector.java:51`, and in `detector/task/`: `ConsensusReachedTaskDetector.java:48`, `ContributionTimeoutTaskDetector.java:46`, `FinalDeadlineTaskDetector.java:46`, `FinalizedTaskDetector.java:57`, `InitializedTaskDetector.java:50`, `ReopenedTaskDetector.java:52`, `UnstartedTxDetector.java:42`. The sixteenth is the multi-line `@Scheduled(fixedRateString = …, timeUnit = DAYS)` at `logs/ComputeLogsCronService.java:47`.

  A `fixedRate` schedule is phased from each instance's own start time, not from the wall clock, so separate instances do not fire together the way cron does. The pattern's `failure_if_absent` ("every instance fires at :00 together") applies to cron. It would apply to fixed-rate work only after a synchronised fleet restart. iexec-core is also one scheduler per workerpool. The detector now requires `cron =` in the annotation, and `fixedRate` no longer counts. The brief's own negative sample (a fixed rate with a random `initialDelayString`) stays silent. → `S16/java/negative_fixed_rate.java`

### Silences checked

- S09 cache-aside and S17 have no candidate construct in the nine repositories. No `src/main` file has a map or Caffeine cache *named* as a cache. The `new HashMap<>()` sites are request parameters, aggregate fields and routing tables, for example spring-data-examples `TenantRoutingDatasource.java:36` and jhipster `LoggingConfiguration.java:29`. iexec-core's `jwTokensMap` and `workerStatsMap` (`JwtTokenProvider.java:36`, `WorkerService.java:66`) are not named as caches either. Both detectors therefore stay silent, which is correct, but they have no real-world evidence yet.
- jhipster's cache code (`UserService.clearUserCaches`) goes through `cacheManager.getCache(…)`, and `.evict(` is provider-managed, so neither S09 nor S17 fires, which is correct.
- `@Scheduled(fixedDelay…)` (iexec-core `WorkerService.java:97`) is silent, as required.

### Known limitations (noted, not fixed)

- `S16-java-scheduled-no-jitter` cannot see deployment topology. A cron job on a service that only ever runs as one instance still fires. That is accepted at `confidence: low`, and the investigator judges it. A `cron` attribute that is not on the `@Scheduled(` line itself (`@Scheduled(zone = "UTC",` on one line and `cron = …` on the next) is missed.
- `S16-java-scheduled-no-jitter` no longer reports `fixedRate` jobs. That misses the case where a whole fleet restarts together and stays in phase.
- `S09-java-cacheable-no-sync` is silent whenever `unless =` is present. Concurrent misses on such a method still call through to the source; the fix there is a cache-level loader, not the annotation, and this detector does not report it.
- `S09-java-cacheable-no-sync` reads 8 lines from the annotation, so a `sync = true` on the *next* method's `@Cacheable` can silence it. That is a miss, not a false positive.
- `S09-java-cache-aside-no-singleflight` is silenced by any `synchronized` or `lock()` in the file, even one that does not guard the load. That is a miss.
- `S17-java-unbounded-cache`: the name rule misses caches named, for example, `lookup` or `byId`. The `CacheManager` suppression silences a file that has both a Spring-managed cache and an unbounded hand-rolled one. Both are misses.
- `S01-java-webclient-no-timeout` is file-scoped. One unbounded WebClient in a file that also builds a bounded one, or calls `.timeout(` anywhere, is missed.
- `S09-java-cache-aside-no-singleflight` / `S17-java-unbounded-cache`: enum-keyed cache maps (`Map<Status, X>`) fire even though the enum's cardinality bounds them. The field gate misses a field whose annotation shares its line (`@Getter private final Map… = new HashMap<>()`), and it still counts a method-local `final Map… = new HashMap<>()` as a field.
- `S16-java-scheduled-no-jitter` reads 10 lines, so jitter vocabulary in the next method can silence it. That is a miss.
- `S01-java-webclient-no-timeout`: a builder bean whose consumers apply `.timeout()` in other files, or wrap the call in a Resilience4j `TimeLimiter`, still fires, because file-local regex cannot see the consumer. None of this batch's hits was that shape (the gateway's owner call is not time-limited).
- `S09-java-cache-aside-no-singleflight` / `S17-java-unbounded-cache`: the field gate misses a cache built through a wrapper or factory, for example `private final Map<String,String> cache = Collections.synchronizedMap(new HashMap<>());`. That is a miss.

## Batch 2 — Spring/Hibernate, part 2 (Task 8): S29, S08

The sweep ran `--patterns S29,S08`. S29 is a new pattern (N+1 query
fan-out) with one module detector, `S29-java-n-plus-one`. S08 gains its
first Java detector, `S08-java-repository-no-pageable`. The four
repositories listed in the brief come first. The Task 7 clones of the other
five were swept as well, at no extra cost, and iexec-core, a Spring Data
MongoDB service, is where S29's only real-world hits came from.

| Repo | Commit | Java files swept |
|---|---|---|
| spring-projects/spring-petclinic | `818c4136ea971c21674525f9053de0d9c7ad8cfe` | 30 |
| spring-petclinic/spring-petclinic-microservices | `295fa8d5ee10f7b6daddf83a2c65f9051a87564b` | 53 |
| spring-projects/spring-data-examples | `7747029e6157cb780862826b6ae87c88d7a4df3c` | 6504 (6001 are the generated entities and repositories of `jpa/deferred`) |
| jhipster/jhipster-sample-app | `6b000b5d23a36c45e01472471b84a44fa2464044` | 81 |
| iExecBlockchainComputing/iexec-core | `a09dbba123f09ae352410c87bcb3788610536809` | 129 |
| jhy/jsoup | `49a15317317970a7ea3f0a5ded303ef319860f4a` | 98 |
| brettwooldridge/HikariCP | `a4d93f4f85517f90e632b795486d7102e933d7ff` | 49 |
| apache/commons-pool | `c4aba65cd8445685f89422b18219ea9853e4306d` | 57 |
| spring-petclinic/spring-petclinic-reactive | `68534cf88a9d022467b9590b953ea4fc7f78bd6b` | 39 |

| Detector | Hits | TP | FP-fixed | FP-accepted | Deferred | Final |
|---|---|---|---|---|---|---|
| S29-java-n-plus-one | 2 | 0 | 2 | 0 | | 0 |
| S08-java-repository-no-pageable | 2023 | 2018 | 0 | 5 | | 2023 |

S08's 2023 hits are 2000 in `jpa/deferred` plus 23 in hand-written code.
Of the 23, 18 are TP and 5 are FP-accepted.

### The tripwire and `jpa/deferred`

S08 has 2018 hits in spring-data-examples, far over the 25-hit tripwire.
2000 of them are in `jpa/deferred`, a bootstrap benchmark whose
`Customer1Repository` … `Customer1999Repository` and `CustomerRepository` are
machine-generated copies of one file:
`List<CustomerN> findByLastName(String lastName);` on a `CrudRepository`.
That is the shape the pattern describes and the shape of the positive
sample. No tightening can separate it from `positive.java`, so under a
literal reading the detector would be deferred. It was not deferred. The
tripwire exists to catch a detector that over-matches, and these hits are
one distinct shape repeated, judged once below. Without `jpa/deferred`,
spring-data-examples has 18 hits, which is under the tripwire. This is
flagged for a controller ruling in the Task 8 report. In a real scan,
`signals.py --top` would surface at most a handful of such files.

S29 had 2 hits before its fix and 0 after, well under the tripwire.

### Tightened before calibration

Before the sweep, both detectors were run against common shapes of correct
Java. Every shape that fired became a required-silent sample, and the
detector was then tightened until the sample passed. None of these fixes
came from a calibration hit, so none is counted in the table above.

- `S29-java-n-plus-one`. The brief's handler flagged any `el.getX().` inside a for-each over `el`. It now has these rules:
  - Only a collection operation (`size`, `isEmpty`, `stream`, `forEach`, `contains`, `add`, `iterator`, `get(<index>)`, …) or a further getter counts as navigation. `trim()`, `toLowerCase()`, `equals()`, `compareTo()`, `name()`, `toString()`, `orElse()`, `isPresent()` and `Optional.get()` read a column that is already loaded.
  - Getters that never initialise a proxy or that belong to JDK value types do not count: `getId()` (a Hibernate proxy returns its key without a query), `getClass()`, `getYear()`/`getMonth…`/`getDay…`/`getTime()`/`getEpoch…`, `getBytes()`, `getSimpleName()`.
  - An element of a JDK value type (`String`, boxed and primitive types, `BigDecimal`, `UUID`, `Optional`, `Map.Entry`/`Entry`, `java.time` types, …) is skipped. So is one whose type follows a DTO naming convention (`…Dto`, `…DTO`, `…Request`, `…Response`, `…View`, `…Vm`, `…Projection`, `…Payload`, `…Command`, `…Event`, `…Form`).
  - A loop whose iterable is already mapped (`.map(…)`, or a `Dto` in the source expression) is skipped.
  - One level of nested generics is parsed (`Map.Entry<String, List<Order>>`), so an entry loop is recognised and skipped instead of being missed by accident.
  - The eager-fetch vocabulary also covers `@NamedEntityGraph`, `@BatchSize`, `FetchMode.SUBSELECT`/`JOIN` and a `…fetchgraph`/`…loadgraph` query hint. Batch fetching makes N+1 into N/size+1, and a fetch graph makes it one query.

  The handler catches every exception and returns what it has, and a 50 000-character line or a 30 000-link getter chain runs in milliseconds.

  → `S29/java/negative_dto_element.java`, `negative_map_entry.java`, `negative_value_methods.java`, `negative_batch_size.java` and `negative_named_entity_graph.java`
- `S08-java-repository-no-pageable`:
  - A by-id finder (`findAllById(Iterable)`, `findByIdIn(Collection)`) is bounded by the ids the caller passes, so it no longer satisfies `require`.
  - A `LIMIT n`/`LIMIT :p`/`LIMIT ?` or `FETCH FIRST` in a `@Query`, a Spring Data `Limit` parameter and a `Window<>` (scroll) return type all count as bounded.
  - A `Stream<>` finder still counts as unbounded, because on JDBC and JPA most drivers (MySQL, and PostgreSQL without a fetch size and a transaction) materialise the whole result before the first element arrives. A fetch-size hint (`HINT_FETCH_SIZE`, `fetchSize`) in the file makes it a cursor and suppresses the hit.
  - `Optional<>`-only repositories, `Flux<>` (reactive) finders and `findTopN…`/`findFirstN…` were already silent.

  → `S08/java/negative_find_all_by_id.java`, `negative_query_limit.java`, `negative_limit_param.java` and `negative_stream_fetch_size.java`

### Hits

- `S08-java-repository-no-pageable` spring-petclinic `src/main/java/org/springframework/samples/petclinic/owner/PetTypeRepository.java:30` — FP-accepted: `findPetTypes()` reads a reference table of pet types that the domain keeps to a handful of rows. Regex cannot tell a lookup table from a growing one.
- `S08-java-repository-no-pageable` spring-petclinic-microservices `spring-petclinic-customers-service/src/main/java/org/springframework/samples/petclinic/customers/model/PetRepository.java:35` — FP-accepted: the same `findPetTypes()` lookup table.
- `S08-java-repository-no-pageable` spring-petclinic-microservices `spring-petclinic-visits-service/src/main/java/org/springframework/samples/petclinic/visits/model/VisitRepository.java:33` — TP: `findByPetIdIn(Collection<Integer>)` returns every visit of every pet passed in, and the API gateway calls it for all of an owner's pets. The result grows with visit history and has no bound.
- `S08-java-repository-no-pageable` spring-data-examples `cassandra/example/src/main/java/example/springdata/cassandra/projection/CustomerRepository.java:28` — TP: `findAllProjectedBy()`/`findAllSummarizedBy()` read the whole table into a `Collection`.
- `S08-java-repository-no-pageable` spring-data-examples `cassandra/example/src/main/java/example/springdata/cassandra/streamoptional/PersonRepository.java:29` — FP-accepted: the only collection finder is `Stream<Person> findAll()`, and the Cassandra driver pages a stream by its default page size. The detector cannot tell the store's paging behaviour from the file.
- `S08-java-repository-no-pageable` spring-data-examples `couchbase/example/src/main/java/example/springdata/couchbase/repository/AirlineRepository.java:32` — TP: `findAllBy()` returns every airline document.
- `S08-java-repository-no-pageable` spring-data-examples `jdbc/aot-optimization/src/main/java/example/springdata/aot/CategoryRepository.java:28` — TP: `findAllByNameContaining` is an unbounded substring search.
- `S08-java-repository-no-pageable` spring-data-examples `jdbc/basics/src/main/java/example/springdata/jdbc/basics/aggregate/LegoSetRepository.java:30` — TP: `reportModelForAge(int)` and `findByName` return every match, with no limit in either `@Query`.
- `S08-java-repository-no-pageable` spring-data-examples `jdbc/howto/bidirectionalexternal/src/main/java/example/springdata/jdbc/howto/bidirectionalexternal/MinionRepository.java:23` — TP: `findByEvilMaster` returns all of a master's minions, a child set that only grows.
- `S08-java-repository-no-pageable` spring-data-examples `jpa/example/src/main/java/example/springdata/jpa/custom/UserRepository.java:31` — TP: `findByLastname`/`findByFirstname` return every user with that name.
- `S08-java-repository-no-pageable` spring-data-examples `jpa/jpa21/src/main/java/example/springdata/jpa/resultsetmappings/SubscriptionRepository.java:28` — TP: `findAllSubscriptionSummaries()`/`findAllSubscriptionProjections()` aggregate the whole table.
- `S08-java-repository-no-pageable` spring-data-examples `jpa/multiple-datasources/src/main/java/example/springdata/jpa/multipleds/order/OrderRepository.java:30` — TP: `findByCustomer` returns a customer's entire order history.
- `S08-java-repository-no-pageable` spring-data-examples `jpa/security/src/main/java/example/springdata/jpa/security/SecureBusinessObjectRepository.java:28` — TP: `findBusinessObjectsForCurrentUser()` matches `like '%'` for an admin, which is the whole table.
- `S08-java-repository-no-pageable` spring-data-examples `jpa/showcase/src/main/java/example/springdata/jpa/showcase/after/AccountRepository.java:30` — TP: `findByCustomer` returns all of a customer's accounts, with no bound.
- `S08-java-repository-no-pageable` spring-data-examples `jpa/showcase/src/snippets/java/example/springdata/jpa/showcase/snippets/AccountRepository.java:33` — TP: the same finder in the snippet copy.
- `S08-java-repository-no-pageable` spring-data-examples `ldap/example/src/main/java/example/springdata/ldap/PersonRepository.java:29` — TP: `findByLastnameStartsWith` is an unbounded prefix search over the directory.
- `S08-java-repository-no-pageable` spring-data-examples `map/src/main/java/example/springdata/map/PersonRepository.java:28` — TP: `findByAgeGreaterThan` is an open range.
- `S08-java-repository-no-pageable` spring-data-examples `mongodb/example/src/main/java/example/springdata/mongodb/advanced/AdvancedRepository.java:30` — TP: `findByFirstname` returns every match.
- `S08-java-repository-no-pageable` spring-data-examples `mongodb/geo-json/src/main/java/example/springdata/mongodb/geojson/StoreRepository.java:29` — TP: `findByLocationWithin(Polygon)` grows with the polygon and with store density.
- `S08-java-repository-no-pageable` spring-data-examples `mongodb/text-search/src/main/java/example/springdata/mongodb/textsearch/BlogPostRepository.java:26` — TP: the full-text `findAllBy(TextCriteria)` returns every matching post.
- `S08-java-repository-no-pageable` spring-data-examples `neo4j/example/src/main/java/example/springdata/neo4j/ActorRepository.java:29` — FP-accepted: `findAllByRolesMovieTitle` returns one film's cast, which the domain bounds and which does not grow over time.
- `S08-java-repository-no-pageable` spring-data-examples `jpa/deferred/src/main/java/example/repo/CustomerRepository.java:9` and `Customer1Repository.java:9` … `Customer1999Repository.java:9` (2000 hits, one per generated file) — TP: each is `List<CustomerN> findByLastName(String)` on a `CrudRepository`, the unbounded derived finder the pattern describes. See the tripwire note above.
- `S08-java-repository-no-pageable` iexec-core `src/main/java/com/iexec/core/task/TaskRepository.java:27` — TP: `findByCurrentStatus(TaskStatus)` and `findChainTaskIdsByFinalDeadlineBefore(Date)` return every task in a status, or every task past a deadline. Terminal statuses accumulate for the life of the deployment.
- `S08-java-repository-no-pageable` iexec-core `src/main/java/com/iexec/core/worker/WorkerRepository.java:25` — FP-accepted: the only collection finder is `findByWalletAddressIn(Collection<String>)`, which looks up a unique key, so the caller's list bounds the result. Regex cannot tell a unique column from a non-unique one, and `…In(Collection)` on a status column really is unbounded.

### Fixed during calibration

- `S29-java-n-plus-one` iexec-core `src/main/java/com/iexec/core/replicate/ReplicatesList.java:94` — FP-fixed: `replicate.getStatusUpdateList().stream()` in a loop over a MongoDB `@Document`'s embedded list. A document store loads the nested list with its parent, so there is nothing to lazy-load.
- `S29-java-n-plus-one` iexec-core `src/main/java/com/iexec/core/worker/WorkerService.java:105` — FP-fixed: `worker.getComputingChainTaskIds().isEmpty()` over `Worker` documents read through `MongoTemplate`, the same shape.

  Lazy loading is a JPA/Hibernate behaviour. A file that imports a Spring Data document or aggregate store (`org.springframework.data.mongodb`, `jdbc`, `cassandra`, `couchbase`, `elasticsearch`, `redis`, `neo4j`, `r2dbc`) or `com.mongodb`, and does not also import `javax`/`jakarta.persistence` or `org.hibernate`, is now skipped → `S29/java/negative_document_store.java`

### Silences checked

- `S29-java-n-plus-one` has no hit in the final sweep, so it has no real-world true positive yet. The four brief repositories contain 12 for-each loops outside tests. None of them reads through a getter on the loop element in a JPA file. In petclinic, `Owner.getPet` loops over `getPets()` and reads `pet.getName()`, a column. jhipster's `UserMapper` passes each `User` to a mapper. So silence is correct there. The brief's unmodified handler also had zero hits on those four repositories.
- No `@Embedded` value or DTO getter chain appears in any swept repository, so the expected class of accepted false positives (`order.getAddress().getCity()` through an embeddable) has **0** instances in this batch. A probe confirms it still fires, and that is accepted at `confidence: low`. DTO-named element types are suppressed, so they account for 0 as well.
- `S08-java-repository-no-pageable` is silent on jhipster-sample-app, whose `UserRepository` finders return `Optional` or take a `Pageable`, and on the reactive petclinic, whose finders return `Flux`.

### Known limitations (noted, not fixed)

- `S29-java-n-plus-one` misses a nested for-each over the association itself, `for (Book book : author.getBooks())` inside `for (Author author : authors)` (spring-data-examples `jpa/graalvm-native/…/CLR.java:83`). That is the textbook N+1 shape, but adding it would loosen the detector to create a hit, which the calibration rules forbid in this pass. It also misses stream and lambda forms (`orders.forEach(o -> o.getItems().size())`, `.map(o -> o.getCustomer().getName())`) and indexed loops.
- `S29-java-n-plus-one` is file-scoped. An `@EntityGraph` or `JOIN FETCH` on a repository interface in another file does not suppress it, and that is the usual layout. Conversely, one hint anywhere in the file silences every loop in it.
- `S29-java-n-plus-one` cannot tell an `@Embedded` value, an enum (`getStatus().getLabel()`) or a DTO without a conventional suffix from a lazy association. It also skips a real entity that happens to be named `…Event` or `…Request`. A Spring Data JDBC or MongoDB file that also imports JPA is treated as JPA.
- `S08-java-repository-no-pageable` is file-scoped. One `Pageable`, `Limit`, `Top`/`First`-N or `LIMIT` anywhere in the repository silences its other, unbounded finders. It only sees finders declared in the interface, so an inherited `findAll()` is not reported. It misses return types written fully qualified (`java.util.List<…>`) or with nested generics (`List<Map<String, Object>>`).
- `S08-java-repository-no-pageable` cannot see selectivity. Lookup tables (`PetType`), cast lists and `…In(Collection)` on a unique key fire (4 of this batch's 5 FP-accepted). It cannot see store paging either: a `Stream<>` finder fires unless the file sets a fetch size, even on stores whose driver pages streams (Cassandra: 1 FP-accepted).
