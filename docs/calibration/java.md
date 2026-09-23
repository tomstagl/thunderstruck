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
five were swept as well, at no extra cost. iexec-core, a Spring Data MongoDB
service, is where S29's first two hits came from, and both were false
positives.

| Repo | Commit | Java files swept |
|---|---|---|
| spring-projects/spring-petclinic | `818c4136ea971c21674525f9053de0d9c7ad8cfe` | 30 |
| spring-petclinic/spring-petclinic-microservices | `295fa8d5ee10f7b6daddf83a2c65f9051a87564b` | 53 |
| spring-projects/spring-data-examples | `7747029e6157cb780862826b6ae87c88d7a4df3c` | 6504 (6001 are the generated entities and repositories of `jpa/deferred`, whose hits are excluded; see below) |
| jhipster/jhipster-sample-app | `6b000b5d23a36c45e01472471b84a44fa2464044` | 81 |
| iExecBlockchainComputing/iexec-core | `a09dbba123f09ae352410c87bcb3788610536809` | 129 |
| jhy/jsoup | `49a15317317970a7ea3f0a5ded303ef319860f4a` | 98 |
| brettwooldridge/HikariCP | `a4d93f4f85517f90e632b795486d7102e933d7ff` | 49 |
| apache/commons-pool | `c4aba65cd8445685f89422b18219ea9853e4306d` | 57 |
| spring-petclinic/spring-petclinic-reactive | `68534cf88a9d022467b9590b953ea4fc7f78bd6b` | 39 |

| Detector | Hits | TP | FP-fixed | FP-accepted | Deferred | Final |
|---|---|---|---|---|---|---|
| S29-java-n-plus-one | 4 | 1 | 2 | 1 | | 2 |
| S08-java-repository-no-pageable | 23 | 18 | 0 | 5 | | 23 |

S08's counts exclude the 2000 `jpa/deferred` hits (see below).

### Generated fixtures excluded: `jpa/deferred`

The raw sweep of spring-data-examples has 2020 hits: 2018 for S08 and 2
for S29. **2000 hits in generated jpa/deferred, byte-identical copies of one
shape — excluded as duplicated input** (controller ruling after Task 8's
first review). `jpa/deferred` is a bootstrap benchmark. Its
`CustomerRepository` and `Customer1Repository` … `Customer1999Repository` are
machine-generated copies of one file, each declaring
`List<CustomerN> findByLastName(String lastName);` on a `CrudRepository`. The
recorded sweep for that repository is the raw TSV with paths under
`jpa/deferred/` filtered out, which leaves 20 lines (18 S08, 2 S29). The
tripwire therefore applies to 18 distinct S08 hits, which is within the
limit, and S08 stays.

S29 had 4 hits in all: 2 before its document-store fix, and 2 after the
nested-loop rule was added. Both of those numbers are well under the
tripwire.

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

  - (Fix round 1, controller ruling) An inner for-each over a getter of the outer element, `for (Book book : author.getBooks())`, counts as navigation, next to the chained-getter rule. Every suppression above still applies to it. So a DTO- or value-typed outer element, an eager or batch hint, or a document-store file stays silent → `S29/java/positive.java` (appended `AuthorCatalogService`) and `negative_nested_eager.java` (the same nested shape with `join fetch`).

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
- `S08-java-repository-no-pageable` iexec-core `src/main/java/com/iexec/core/task/TaskRepository.java:27` — TP: `findByCurrentStatus(TaskStatus)` and `findChainTaskIdsByFinalDeadlineBefore(Date)` return every task in a status, or every task past a deadline. Terminal statuses accumulate for the life of the deployment.
- `S08-java-repository-no-pageable` iexec-core `src/main/java/com/iexec/core/worker/WorkerRepository.java:25` — FP-accepted: the only collection finder is `findByWalletAddressIn(Collection<String>)`, which looks up a unique key, so the caller's list bounds the result. Regex cannot tell a unique column from a non-unique one, and `…In(Collection)` on a status column really is unbounded.

- `S29-java-n-plus-one` spring-data-examples `jpa/graalvm-native/src/main/java/com/example/data/jpa/CLR.java:81` — TP: `listAllAuthors()` loads `authorRepository.findAll()` and then iterates `author.getBooks()` for each author. `Author.books` is a `@OneToMany` with the default LAZY fetch, and neither `AuthorRepository` nor `CLR` has an entity graph or fetch join. That is the N+1 shape: whenever this loop runs in a fresh persistence context, it costs one select for the authors and one more for each author's books. (Whether the demo's own run issues those selects depends on what its earlier steps left in the persistence context. The verdict is about the code shape, not about a measured run.)
- `S29-java-n-plus-one` spring-data-examples `jdbc/graalvm-native/src/main/java/example/springdata/jdbc/graalvmnative/CLR.java:81` — FP-accepted: the same code on Spring Data JDBC. A JDBC aggregate loads its `books` with the author inside `findAll()`, so the loop issues no query. The file imports no store package (the dependency is only in the module's `pom.xml`), so file-local regex cannot tell it from the JPA twin above.

### Fixed during calibration

- `S29-java-n-plus-one` iexec-core `src/main/java/com/iexec/core/replicate/ReplicatesList.java:94` — FP-fixed: `replicate.getStatusUpdateList().stream()` in a loop over a MongoDB `@Document`'s embedded list. A document store loads the nested list with its parent, so there is nothing to lazy-load.
- `S29-java-n-plus-one` iexec-core `src/main/java/com/iexec/core/worker/WorkerService.java:105` — FP-fixed: `worker.getComputingChainTaskIds().isEmpty()` over `Worker` documents read through `MongoTemplate`, the same shape.

  Lazy loading is a JPA/Hibernate behaviour. A file that imports a Spring Data document or aggregate store (`org.springframework.data.mongodb`, `jdbc`, `cassandra`, `couchbase`, `elasticsearch`, `redis`, `neo4j`, `r2dbc`) or `com.mongodb`, and does not also import `javax`/`jakarta.persistence` or `org.hibernate`, is now skipped → `S29/java/negative_document_store.java`

### Silences checked

- `S29-java-n-plus-one` has one real-world true positive, the nested loop in jpa/graalvm-native `CLR.java`. The four brief repositories contain 12 for-each loops outside tests. Apart from the two `CLR.java` hits, none reads through a getter on the loop element. In petclinic, `Owner.getPet` loops over `getPets()` and reads `pet.getName()`, a column. jhipster's `UserMapper` passes each `User` to a mapper. So silence is correct there.
- No `@Embedded` value or DTO getter chain appears in any swept repository, so the expected class of accepted false positives (`order.getAddress().getCity()` through an embeddable) has **0** instances in this batch. A probe confirms it still fires, and that is accepted at `confidence: low`. DTO-named element types are suppressed, so they account for 0 as well.
- `S08-java-repository-no-pageable` is silent on jhipster-sample-app, whose `UserRepository` finders return `Optional` or take a `Pageable`, and on the reactive petclinic, whose finders return `Flux`.

### Known limitations (noted, not fixed)

- `S29-java-n-plus-one` misses stream and lambda forms (`orders.forEach(o -> o.getItems().size())`, `.map(o -> o.getCustomer().getName())`) and indexed loops.
- `S29-java-n-plus-one` is file-scoped. An `@EntityGraph` or `JOIN FETCH` on a repository interface in another file does not suppress it, and that is the usual layout. Nor does `FetchType.EAGER` declared on the association in the entity's own file: a loop in a service over an eagerly fetched association still fires. Conversely, one hint anywhere in the file silences every loop in it.
- `S29-java-n-plus-one` misses Allman-style loops, where the `{` sits on the line after `for (…)`. The body is then read as the header line and the brace line alone.
- `S29-java-n-plus-one` trades recall for precision in its value filters, and each of them can suppress a real association: the element-type prefixes `Local\w*`, `Zoned\w*` and `Offset\w*` (meant for `java.time`, but they also match entities named `LocalBranch` or `OffsetAgreement`), the value getters `getDay\w*`, `getMonth\w*` and `getTime` (the prefixes also match association getters such as `getDaySchedules()` or `getMonthlyInvoices()`), and any `Dto` substring anywhere in the loop's source expression.
- `S29-java-n-plus-one` cannot tell an `@Embedded` value, an enum (`getStatus().getLabel()`) or a DTO without a conventional suffix from a lazy association. It also skips a real entity that happens to be named `…Event` or `…Request`. A Spring Data JDBC or MongoDB file that also imports JPA is treated as JPA. A JDBC or Mongo file that imports no store package at all is also treated as JPA (1 FP-accepted, `jdbc/graalvm-native/…/CLR.java:81`).
- `S08-java-repository-no-pageable`'s `require` matches a collection return type only at the start of a line. It misses finders declared with a modifier (`public List<…>`, `default List<…>`) and a one-line `@Query("…") List<…> find…(…)`.
- `S08-java-repository-no-pageable` is file-scoped. One `Pageable`, `Limit`, `Top`/`First`-N or `LIMIT` anywhere in the repository silences its other, unbounded finders. It only sees finders declared in the interface, so an inherited `findAll()` is not reported. It misses return types written fully qualified (`java.util.List<…>`) or with nested generics (`List<Map<String, Object>>`).
- `S08-java-repository-no-pageable` cannot see selectivity. Lookup tables (`PetType`), cast lists and `…In(Collection)` on a unique key fire (4 of this batch's 5 FP-accepted). It cannot see store paging either: a `Stream<>` finder fires unless the file sets a fetch size, even on stores whose driver pages streams (Cassandra: 1 FP-accepted).

## Batch 3 — Messaging (Task 9): S07, S08 (Kafka), S19

The sweep ran `--patterns S07,S08,S19`. S07 gains two Java detectors,
`S07-java-uncheckpointed-loop` (the shared `s07_checkpoint` module) and
`S07-java-kafka-no-manual-commit`. S08 gains `S08-java-kafka-no-max-poll-records`;
only that S08 detector is recorded here, because `S08-java-repository-no-pageable`
was calibrated in Batch 2. S19 gains `S19-java-empty-catch` and
`S19-java-catch-only-comment`. The four repositories listed in the brief come
first. The nine clones from Batches 1 and 2 were swept as well, because the
brief's four gave S19 and the S07 loop detector little code to work on. The
`jpa/deferred` exclusion from Batch 2 applies to spring-data-examples, but none
of this batch's detectors hit there.

| Repo | Commit | Java files swept |
|---|---|---|
| spring-projects/spring-kafka | `fff33914d4e450a33e17195e11a79937c3505605` | 387 |
| confluentinc/kafka-streams-examples | `3c40c0e27dd988d8b2d72951802d8fd9c9940a64` | 58 |
| apache/activemq-artemis-examples | `37a1052bad9928f04f983fb6619088d43855f4a2` | 194 |
| rabbitmq/rabbitmq-tutorials | `586f18f75693d7fffe16ff3d29775f4176ba4ecc` | 90 |
| jhy/jsoup | `49a15317317970a7ea3f0a5ded303ef319860f4a` | 98 |
| brettwooldridge/HikariCP | `a4d93f4f85517f90e632b795486d7102e933d7ff` | 49 |
| apache/commons-pool | `c4aba65cd8445685f89422b18219ea9853e4306d` | 57 |
| iExecBlockchainComputing/iexec-core | `a09dbba123f09ae352410c87bcb3788610536809` | 129 |
| spring-projects/spring-petclinic | `818c4136ea971c21674525f9053de0d9c7ad8cfe` | 30 |
| spring-petclinic/spring-petclinic-microservices | `295fa8d5ee10f7b6daddf83a2c65f9051a87564b` | 53 |
| spring-projects/spring-data-examples | `7747029e6157cb780862826b6ae87c88d7a4df3c` | 6504 (6001 in `jpa/deferred`; no hits there) |
| jhipster/jhipster-sample-app | `6b000b5d23a36c45e01472471b84a44fa2464044` | 81 |
| spring-petclinic/spring-petclinic-reactive | `68534cf88a9d022467b9590b953ea4fc7f78bd6b` | 39 |

| Detector | Hits | TP | FP-fixed | FP-accepted | Deferred | Final |
|---|---|---|---|---|---|---|
| S07-java-uncheckpointed-loop | 38 | 0 | 38 | 0 | | 0 |
| S07-java-kafka-no-manual-commit | 11 | 0 | 11 | 0 | | 0 |
| S08-java-kafka-no-max-poll-records | 11 | 0 | 11 | 0 | | 0 |
| S19-java-empty-catch | 4 | 2 | 2 | 0 | | 2 |
| S19-java-catch-only-comment | 10 | 6 | 4 | 0 | | 2 |

**Hits** here is the first sweep, made with the brief's detectors unchanged.
No detector had more than 25 hits in one repository; the most was
`S07-java-uncheckpointed-loop` with 18 in jsoup. The brief's four repositories
account for 15 of the loop detector's hits, all 11 of each Kafka detector's,
and 9 of S19's. No true positive for S07 or for the S08 Kafka detector exists
in any of the 13 repositories. Every Kafka consumer in them is either a
synchronous print loop in a demo driver or a framework container that commits
through its own acknowledgment machinery. Those two detectors are proven only
by their samples and the recall probes listed under **Silences checked**.

`S19-java-catch-only-comment`'s 6 TP include 4 that are not in the final
sweep: the artemis `catch (Throwable ignored0) {}` blocks, which are real
swallows but are silenced by the `ignored`-name suppression. That is a
recorded recall trade (see **Lost to the `ignored`-name suppression** and
Known limitations), not a detector fix, so they are not counted as FP-fixed.

### Tightened before calibration

The detectors were run against common shapes of correct Java at the same time
as the first sweep. The shapes below fired under the brief's detectors and
had no instance in the corpus. Each became a required-silent sample.

- `S07-java-kafka-no-manual-commit` and `S08-java-kafka-no-max-poll-records`:
  - `require` accepts only a `poll(…)` with an argument and no `TimeUnit`, closed on the same line: Kafka's `poll(Duration)` (including `Duration.of(100, ChronoUnit.MILLIS)`, whose nested comma the first version rejected) or `poll(long)`. A `BlockingQueue`'s `poll()` or `poll(timeout, TimeUnit)` in a `@Configuration` class that only builds a `KafkaConsumer` bean does not satisfy it → `S07/java/negative_factory_only.java`. Keeping the argument match to one line (`[^;\n]*`) also removed a superlinear case: 5000 unclosed `q.poll(a` lines took 725 ms and now take 1 ms.
  - The anchor skips the `import` line, so a hit lands on the field, the parameter or the `new KafkaConsumer<>(…)`, which is where the consumer is used.
- `S07-java-kafka-no-manual-commit`: offsets kept in the application's own store (`consumer.seek(partition, stored)`) count as a commit → `S07/java/negative_external_offsets.java`. A commit made in a helper method in the same file was already silent, and so was a Spring `@KafkaListener` that calls `Acknowledgment.acknowledge()` (no `KafkaConsumer` anchor) → `negative_commit_helper.java`, `negative_spring_listener.java`.
- `S07-java-uncheckpointed-loop`: `s07_checkpoint` now takes Java variants of its three regexes (`PAGING_JAVA`, `PAGE_ADVANCE_JAVA`, `PERSIST_JAVA`, chosen by `_lang_key`). The shared TS/Python regexes are unchanged (AC-16). A setter that records the position on a progress object (`state.setLastOffset(offset)`, and likewise `setResume…`, `setCheckpoint…`, `setCommitted…` and `setSaved…`) counts as persisting it. A setter that builds the next request (`request.setPageToken(t)`) does not → `S07/java/negative_setter_checkpoint.java`.
- `S19-java-empty-catch` and `S19-java-catch-only-comment`: a catch whose body is one statement on the next line and then `}` was already silent, because `window: 1` is kept from the brief. So were a one-line rethrow inside a lambda and a try-with-resources with a handled catch → `S19/java/negative_one_statement_body.java`. The parameter list is bounded to 200 characters. A pathological line of 20 000 unclosed `catch (` took 76 s with an unbounded `[^)]*` and now takes 0.3 s.

### Hits

- `S19-java-catch-only-comment` activemq-artemis-examples `examples/features/standard/management-notifications/src/main/java/org/apache/activemq/artemis/jms/example/ManagementNotificationExample.java:72` — TP: a `JMSException` thrown while the notification listener reads the message properties is swallowed. The listener prints half a notification and nothing says why.
- `S19-java-catch-only-comment` activemq-artemis-examples `examples/features/standard/management-notifications/src/main/java/org/apache/activemq/artemis/jms/example/ManagementNotificationExample.java:90` — TP: the example provokes a security failure with bad credentials and swallows every `JMSException`. A broker that is down or refusing connections is swallowed exactly the same way, so the run cannot tell the failure it wanted from one it did not.
- `S19-java-empty-catch` spring-data-examples `couchbase/transactions/src/main/java/com/example/demo/CmdRunner.java:42` — TP: `catch (Exception e) {}` around `template.removeById(…).one("1")`. The expected failure is document-not-found, but a timeout or a lost connection on this delete is swallowed too, and the leftover document then collides with the `save` that follows.
- `S19-java-empty-catch` spring-data-examples `couchbase/transactions/src/main/java/com/example/demo/CmdRunner.java:45` — TP: the same catch-all around the second delete.

### Fixed during calibration

- `S07-java-uncheckpointed-loop`, 18 hits on an `Iterator.hasNext()` walk: spring-kafka `KafkaMessageListenerContainer.java:2898`, `:2953`, `:2981`; kafka-streams-examples `WordCountInteractiveQueriesRestService.java:175`, `:241`, `PriorityQueueSerializer.java:50`; jsoup `StringUtil.java:51`, `Attributes.java:728`, `:738`, `Node.java:205`, `Safelist.java:355`, `HasEvaluator.java:152`, `Nodes.java:305`, `:324`, `StreamParser.java:359`; commons-pool `EvictionTimer.java:82`, `GenericKeyedObjectPool.java:988`, `GenericObjectPool.java:696` — FP-fixed. The shared `PAGING`/`PAGE_ADVANCE` treat any `hasNext` as a more-pages test. In Java it is the in-memory iterator protocol. A more-pages test now counts only on a page or slice receiver (`page.hasNext()`, `slice.hasNext()`, `page.nextPageable()`) → `S07/java/negative_iterator_loops.java`
- `S07-java-uncheckpointed-loop`, 6 hits on `Enumeration.hasMoreElements()`: spring-kafka `DefaultKafkaConsumerFactory.java:419`; activemq-artemis-examples `QueueBrowserExample.java:73`, `LastValueQueueExample.java:72`, `ManagementNotificationExample.java:68`; HikariCP `HikariJNDIFactory.java:44`, `DriverDataSource.java:66` — FP-fixed. `has_?more` matched `hasMoreElements`/`hasMoreTokens`, and it no longer does → `S07/java/negative_iterator_loops.java`
- `S07-java-uncheckpointed-loop` jsoup `src/main/java/org/jsoup/internal/ControllableInputStream.java:245` — FP-fixed: `truncated = buff.hasMore()` asks a read buffer whether bytes remain. `hasMore` now counts as a flag (`while (hasMore)`) or as a call on a page, response, result, batch, chunk, slice or list receiver, and not on a buffer → `S07/java/negative_buffer_has_more.java` (this hit survived the first round of Java variants and was fixed in a second)
- `S07-java-uncheckpointed-loop`, 11 hits on an `offset` that is not a page position: spring-kafka `ShareKafkaMessageListenerContainer.java:509` (`long offset = e.offset()`), `:732` (`offset=%d` in a log format); kafka-streams-examples `ConsumeCustomers.java:66`, `ConsumeOrders.java:66`, `ConsumePayments.java:65` (`"offset = %d"` in a `printf`); jsoup `Element.java:1849`, `:1857`, `Entities.java:204`, `CharacterReader.java:323`, `:581`, `:600` (character offsets in a parser) — FP-fixed. The shared `PAGE_ADVANCE` counts any `offset =`/`offset++`. An offset now advances a page only as `offset += <limit|pageSize|batchSize|fetchSize>`, and an assignment counts only at the start of a statement, so `String page = it.next()` and `long offset = …` are declarations, not steps → `S07/java/negative_record_offset.java`, `negative_iterator_loops.java` (byte-offset parser)
- `S07-java-uncheckpointed-loop` jsoup `src/main/java/org/jsoup/parser/HtmlTreeBuilder.java:1183`, `:1192` — FP-fixed: a `boolean skip` flag in the adoption-agency algorithm. `skip =` no longer counts as an advance in Java → `S07/java/negative_record_offset.java` (`reconstruct`)
- `S07-java-kafka-no-manual-commit` and `S08-java-kafka-no-max-poll-records`, 10 hits each in kafka-streams-examples: `GlobalKTablesAndStoresExampleDriver.java:29`, `JsonToAvroExampleDriver.java:32`, `PageViewRegionExampleDriver.java:26`, `SessionWindowsExampleDriver.java:23`, `SumLambdaExampleDriver.java:21`, `TopArticlesExampleDriver.java:25`, `WikipediaFeedAvroExampleDriver.java:23`, `microservices/util/ConsumeCustomers.java:12`, `ConsumeOrders.java:12`, `ConsumePayments.java:12`. All 20 landed on the `import` line. FP-fixed. Each is a synchronous loop that polls and prints every record, which is the KafkaConsumer javadoc's own auto-commit example:
  - S07: `poll()` auto-commits only the offsets the *previous* poll returned, and a synchronous loop has already processed those. That is at-least-once delivery, the same guarantee a manual `commitSync()` after processing gives. Auto-commit acks an unprocessed record only when records are handed to another thread. When auto-commit is off and nothing commits, every restart re-reads from the reset point. `require` now asks for one of those two shapes in the file. The first is a hand-off of the polled records: a `submit`/`execute`/`runAsync`/`supplyAsync` call whose arguments name the records (`records`, `record`, `consumerRecords`, `rec`), or `records.forEach(…)` feeding one of those calls. The second is `enable.auto.commit` set to `false`. (Fix round 1: the first version accepted any `new Thread(`, `.submit(` or `.parallelStream(` in the file, so the javadoc's own `KafkaConsumerRunner`, which starts its synchronous loop with `new Thread(runner)`, fired → `S07/java/negative_consumer_runner_thread.java`. A parallel stream over the records finishes before the next `poll()`, so it is not a hand-off.) `positive.java`'s `run()` now hands the batch to an executor, which is a deviation from the brief's sample (see the Task 9 report) → `S07/java/negative_sync_auto_commit.java`
  - S08: the default `max.poll.records` (500) is already a bound. A batch overruns `max.poll.interval.ms` only when each record's work is slow, and printing is not. `require` now asks for blocking per-record work in the file: an HTTP client (`RestTemplate`, `RestClient`, `WebClient`, `HttpClient`, `OkHttpClient`, `postForObject`/`postForEntity`/`exchange`), a JDBC or repository write (`JdbcTemplate`, `executeUpdate`, `executeBatch`, `batchUpdate`, `save`, `saveAll`), `Thread.sleep`, a blocking `send(…).get()` or `.block()`. A raised `max.poll.interval.ms` or a `…MaxPollRecords(n)` setter also suppresses it. The brief's appended `OrderEvents` in `S08/java/positive.java` and `negative.java` now posts each record over HTTP → `S08/java/negative_kafka_print_loop.java`, `negative_max_poll_interval.java`, `negative_max_poll_records_string.java`
- `S07-java-kafka-no-manual-commit` and `S08-java-kafka-no-max-poll-records` kafka-streams-examples `src/main/java/io/confluent/examples/streams/microservices/OrderDetailsService.java:53` — FP-fixed:
  - S07: with exactly-once enabled, the offsets are committed inside the producer transaction (`producer.sendOffsetsToTransaction(…)`), so there is no `commitSync()`. `sendOffsetsToTransaction(` now counts as a commit → `S07/java/negative_transactional_offsets.java`
  - S08: the per-record work is an asynchronous `producer.send(…)`, which is not blocking, so the new `require` excludes it → `S08/java/negative_kafka_print_loop.java`
- `S19-java-empty-catch` and `S19-java-catch-only-comment`, 6 hits on a parameter named `ignored`: kafka-streams-examples `KafkaMusicExample.java:275` (an optional numeric system property), `MicroserviceUtils.java:210` (`service.stop()` in a shutdown hook); spring-kafka `EndpointHandlerMethod.java:92` (falls through to a default); jsoup `CharacterReader.java:68` (`reader.close()`), `Cleaner.java:224` (a malformed link URL that only decides `rel=nofollow`), `HttpClientExecutor.java:173` (closing a response body). 2 of these are `S19-java-empty-catch` hits and 4 are `S19-java-catch-only-comment` hits. FP-fixed. A catch parameter named `ignored`, `ignore`, `expected` or `unused` (optionally followed by digits), or the unnamed `_`, is the Java convention for a deliberate swallow. IntelliJ's empty-catch inspection honours it, and so does Error Prone's. Every one of these is a close, a best-effort parse, a shutdown or a fall-back where nothing is lost → `S19/java/negative_ignored_param.java`

### Lost to the `ignored`-name suppression

- `S19-java-catch-only-comment` activemq-artemis-examples `examples/features/broker-connection/ha-with-dual-mirror/src/main/java/org/apache/artemis/jms/example/Consumer.java:57`, `Producer.java:64`, and `ha-with-mesh-mirror/…/Consumer.java:57`, `Producer.java:64` — TP, lost to the ignored-name suppression (recall trade). `catch (Throwable ignored0) {}` around the `Thread.sleep(5000)` of a reconnect loop also swallows an `InterruptedException` and clears the thread's interrupt status, so the loop cannot be stopped by interruption. The suppression keeps the 6 correct `ignored` swallows above silent, and costs these 4.

### Silences checked

- rabbitmq-tutorials produced no hit from any detector of this batch, before or after the fixes. It has no Kafka consumer, and its RabbitMQ consumers (`basicConsume` with `autoAck` or an explicit `basicAck`) use an API none of these detectors reads.
- spring-kafka's own consumer loop (`KafkaMessageListenerContainer`) uses the `Consumer` interface and commits with `commitSync`/`commitAsync`. Its `ShareKafkaMessageListenerContainer` acknowledges each record. Neither produces a hit.
- No Spring Boot consumer configured in `application.yml`/`.properties` appears as a Kafka hit. The expected `FP-accepted: config outside the file` class therefore has **0** instances in this batch. The corpus's Spring consumers are `@KafkaListener` methods, which have no `KafkaConsumer` anchor.
- Recall probes, all firing under the final detectors: a Spring Data `do { page = repo.findAll(pageable); … pageable = page.nextPageable(); } while (page.hasNext());` reindex with no saved position (`S07-java-uncheckpointed-loop`); a poll loop with `ENABLE_AUTO_COMMIT_CONFIG, false` and no commit, and `records.forEach(r -> pool.submit(…))` after a `poll(Duration.of(100, ChronoUnit.MILLIS))` (`S07-java-kafka-no-manual-commit`); a poll loop that `Thread.sleep`s per record (`S08-java-kafka-no-max-poll-records`); `catch (InterruptedException e) {}` and a two-line empty multi-catch (`S19`).

### Known limitations (noted, not fixed)

- `S19-java-catch-only-comment` keeps the brief's `window: 1`, so it sees only the line after `catch (…) {`. A catch whose body is a comment on its own line, followed by `}` on the next line, is **missed**: the blanked comment line is not `}`. A one-line `catch (E e) { /* reason */ }` still fires, because blanking the comment leaves `{ }`, and `S19/java/positive.java` pins that case. This is deliberate. A justification written as a comment is not something the detector can read, and a parameter named `ignored` is the documented way to mark a swallow as intended.
- An `ignored`-named parameter silences S19 even where the swallow is itself a defect. The artemis reconnect loops catch `Throwable ignored0` around `Thread.sleep`, which also discards an `InterruptedException` and the thread's interrupt status (4 TP lost in this batch).
- The name suppression is exact-name only: `ignored`, `ignore`, `expected` and `unused`, optionally followed by digits, or `_`. A compound name such as `ignoredException` or `expectedFailure` still fires.
- `S07-java-kafka-no-manual-commit` does not see the two other ways auto-commit loses a synchronous loop's records. The first is a processing exception caught inside the loop, after which the next `poll()` commits past the failed record. The second is an exception that escapes to `close()` (for example in try-with-resources), which commits the position of the whole unfinished batch. Both need control-flow reasoning.
- `S07-java-kafka-no-manual-commit` sees a hand-off only when the `submit`/`execute`/`runAsync`/`supplyAsync` call names the records on the same line, or when `records.forEach(…)` feeds one. A hand-off of the batch under another name (`var batch = consumer.poll(…); pool.submit(() -> handle(batch));`), or a submit on its own line inside a multi-line `for` body, is missed.
- Both Kafka detectors are file-scoped. Consumer properties built in another class (or in `application.yml`) are invisible. So is a commit made by a collaborator, or per-record work done in a handler class. `S08-java-kafka-no-max-poll-records` knows only the blocking-work vocabulary listed above, so a slow call through any other client is missed.
- Neither Kafka detector reads the Spring Kafka listener container, Reactor Kafka or Kafka Streams APIs. Their commit and batching settings live in container properties.
- `S07-java-uncheckpointed-loop` has no real-world true positive in this batch. It recognises a Java paging loop only through a `page`/`cursor`-named step, a `hasMore` flag, a page or slice receiver's `hasNext()`/`nextPageable()`, a `next…Page/Cursor/Token` name, or an offset stepped by a limit or page size. A paging loop written with other names (`from += 100`, `while (resp.getNextLink() != null)`) is missed.

## Batch 4 — resilience4j/gRPC (Task 10): S05, S10, S11, S12, S15

The sweep ran `--patterns S05,S10,S11,S12,S15`. Each pattern gains its first
Java detector: `S05-java-client-calls-without-limiter`, `S10-java-nested-retry`
(the shared `s10_retry_layers` module, with `RETRY_LAYERS["java"]` and a
Java-only per-method grouping), `S11-java-grpc-no-deadline`,
`S12-java-no-breaker` and `S15-java-no-fallback`. The brief's four
repositories come first. The twelve clones from Batches 1–3 were swept as
well, because the two resilience4j demos are ten files each.

**grpc-java is swept on `examples/` only.** `calibrate.py` ran over the whole
repository (1132 Java files), and its TSV was then filtered with
`grep -P "\texamples/"`, the same kind of scope rule as the `jpa/deferred`
exclusion in Batch 2. Every count and every hit below is for `examples/` only
(98 files). For the record, the unfiltered sweep had 132 lines under the
brief's detectors (52 in `examples/`) and 10 under the final detectors
(4 in `examples/`). The 6 final lines outside `examples/` are benchmarks,
interop-test harnesses, the `AbstractBlockingStub` class itself and a Jetty
smoke test, and they are not judged here.

| Repo | Commit | Java files swept |
|---|---|---|
| resilience4j/resilience4j-spring-boot3-demo | `6c3e644d53174182fb79c0e49770b191a1d7287c` | 10 |
| resilience4j/resilience4j-spring-boot2-demo | `85590a025d1ff6ecf97f26502a14ab595a664305` | 10 |
| grpc/grpc-java | `9e0ff283e9a727546c46d889e02a9376c36ab411` | 98 in `examples/` (1132 in the repository) |
| spring-petclinic/spring-petclinic-microservices | `295fa8d5ee10f7b6daddf83a2c65f9051a87564b` | 53 |
| spring-projects/spring-kafka | `fff33914d4e450a33e17195e11a79937c3505605` | 387 |
| confluentinc/kafka-streams-examples | `3c40c0e27dd988d8b2d72951802d8fd9c9940a64` | 58 |
| apache/activemq-artemis-examples | `37a1052bad9928f04f983fb6619088d43855f4a2` | 194 |
| rabbitmq/rabbitmq-tutorials | `586f18f75693d7fffe16ff3d29775f4176ba4ecc` | 90 |
| jhy/jsoup | `49a15317317970a7ea3f0a5ded303ef319860f4a` | 98 |
| brettwooldridge/HikariCP | `a4d93f4f85517f90e632b795486d7102e933d7ff` | 49 |
| apache/commons-pool | `c4aba65cd8445685f89422b18219ea9853e4306d` | 57 |
| iExecBlockchainComputing/iexec-core | `a09dbba123f09ae352410c87bcb3788610536809` | 129 |
| spring-projects/spring-petclinic | `818c4136ea971c21674525f9053de0d9c7ad8cfe` | 30 |
| spring-projects/spring-data-examples | `7747029e6157cb780862826b6ae87c88d7a4df3c` | 6504 (no hits anywhere, so the `jpa/deferred` exclusion does not arise) |
| jhipster/jhipster-sample-app | `6b000b5d23a36c45e01472471b84a44fa2464044` | 81 |
| spring-petclinic/spring-petclinic-reactive | `68534cf88a9d022467b9590b953ea4fc7f78bd6b` | 39 |

| Detector | Hits | TP | FP-fixed | FP-accepted | Deferred | Final |
|---|---|---|---|---|---|---|
| S05-java-client-calls-without-limiter | 19 | 0 | 19 | 0 | | 0 |
| S10-java-nested-retry | 0 | 0 | 0 | 0 | | 0 |
| S11-java-grpc-no-deadline | 34 | 4 | 30 | 0 | | 4 |
| S12-java-no-breaker | 12 | 1 | 11 (+1) | 1 | | 2 |
| S15-java-no-fallback | 5 | 1 | 4 | 0 | | 1 |

**Hits** is the first sweep, made with the brief's detectors unchanged.

- **Precision tripwire.** `S11-java-grpc-no-deadline` had 34 hits in grpc-java
  `examples/`, which is over the limit of 25. The tightening that brought it to 4 is
  described under **Fixed during calibration**.
- **S12's extra hits.** The tightened S12 anchor (the retry mechanism, not retry
  vocabulary) surfaced two lines the brief's anchor never reached:
  - spring-kafka `ExponentialBackOffWithMaxRetries.java:80`, which was fixed in
    a further round. That is the "(+1)" in the table.
  - spring-kafka `KafkaStreamsInteractiveQueryService.java:94`, which is
    FP-accepted.

  So S12 has 1 FP-accepted hit out of 2 final hits. That is half, not more than
  half, so the detector is not deferred.
- **No S10 hit.** Nothing in the 16 repositories stacks two retry mechanisms on
  one method, and nothing does so file-wide either: the brief's file-scoped
  handler found nothing too. S10 is proven by its samples and the recall probes
  under **Silences checked**.
- **No S05 true positive.** No repository has one. Every first-sweep hit was a
  loop that shared a file with a client call but did not contain it.

### Tightened before calibration

Common shapes of correct Java were run against the brief's detectors at the
same time as the first sweep. The shapes below fired, and each one became a
required-silent sample.

- `S05-java-client-calls-without-limiter`:
  - **Locality.** The brief's `require` accepted a loop anywhere in the file. The
    anchor is now the loop with the call inside it: a `for`/`while` header
    followed, within 8 lines and before a line that is only `}`, by a client
    call. The other accepted form is a `.forEach(…)`, or a
    `.parallelStream()…map/forEach(…)`, whose lambda makes the call within 300
    characters with no `;` in between. The hit lands on the loop.
    → `S05/java/negative_unrelated_loop.java` (a header-building loop before a
    single call)
  - **Fixed literal list.** A loop over a `List.of(…)`, `Set.of(…)`,
    `Stream.of(…)` or `Arrays.asList(…)` literal is not a fan-out.
    → `S05/java/negative_fixed_list.java`
  - **Construction is not a call.** `HttpClient.newBuilder()`,
    `WebClient.builder()`, `.create(`, `.newHttpClient(` and `.mutate(` no
    longer count as a call. → `S05/java/negative_client_factory_loop.java`
  - **Paced loops.** A `sleep(` anywhere in the file suppresses the detector: a
    loop paced by a sleep is a governor. → `S05/java/negative_polling_sleep.java`
  - **Performance.** The span of the `forEach` alternative is bounded. Unbounded,
    5000 unclosed `xs.forEach(` lines took 37 s. They now take 0.17 s.
- `S10-java-nested-retry`:
  - **Per-method grouping.** Java layers are grouped by the method that owns
    them:
    - an annotation binds to the next method or constructor declaration;
    - a statement belongs to the nearest declaration above it.

    Two different mechanisms must share an owner. Before this, `@Retryable` on
    one method and resilience4j `@Retry` on another fired as "2 layers".
    → `S10/java/negative_separate_methods.java`
  - **Import lines** never count as a layer.
  - **Instance calls count as Spring Retry.** `retryTemplate.execute(…)`, on the
    instance, now counts. The brief's case-sensitive `\bRetryTemplate\b` saw only
    the type name, so resilience4j `@Retry` wrapped around a
    `retryTemplate.execute(…)` body was silent. That was a recall fix, not a
    precision one.
  - **The `@Configuration` guard.** The brief's guard is kept.
    `negative_defines_retry_bean.java` is silent even without it, because its
    two bean methods are now two owners. The guard remains as defence in depth.
- `S11-java-grpc-no-deadline`:
  - **Import lines.** The anchor skips the `import` line.
  - **Broader `absent`.** It is now any `deadline` substring
    (case-insensitive). The brief's `absent` required a `withDeadline…(` call in
    the same file, so a stub whose deadline an interceptor sets
    (`ClientInterceptors.intercept(channel, new DeadlineInterceptor(…))`) fired.
    → `S11/java/negative_deadline_interceptor.java`
- `S12-java-no-breaker`:
  - **Holder and config classes.** A constant holder (`MAX_RETRIES = 3` and
    nothing else) fired, and so did an `@ConfigurationProperties` class with a
    `maxAttempts` field and a `@Configuration` class building a `RetryTemplate`
    bean. None of them retries anything.
    - `@Configuration`, `@AutoConfiguration` and `@ConfigurationProperties` now
      suppress the detector.
    - The anchor was rewritten during calibration (below), so a constant alone
      no longer anchors.

    → `S12/java/negative_constant_holder.java`, `negative_properties_holder.java`,
    `negative_retry_bean_config.java`
- `S15-java-no-fallback`:
  - **Configuration classes.** A client configuration class
    (`WebClient.builder()` and a `RestTemplateBuilder` bean) fired. The anchor
    now ignores the same construction calls as S05.
    → `S15/java/negative_client_config.java`
  - **A catch that returns a value.** `catch (RestClientException e) { return
    Collections.emptyList(); }` is a fallback. Such a catch now suppresses the
    detector if `return` is its first statement or comes after at most three
    brace-free statements. A `return` after four statements does not count. The catch must be
    of a client, IO or generic exception: `Exception`, `RuntimeException`,
    `Throwable`, or a `…RestClient/WebClient/Http/IO/Rpc/StatusRuntime/Feign/`
    `Timeout/Connect/Socket/ResourceAccess/CallNotPermitted…Exception`.
    → `S15/java/negative_catch_returns_default.java`
  - **Why the exception list.** The first version accepted any catch. On
    petclinic-microservices, an unrelated `catch (JacksonException e) { return
    null; }` in `VectorStoreController` then hid a TP (see Hits).
    `S15/java/positive.java` now appends a class with exactly that shape, so the
    TP cannot be lost again.

### Fix round 1 (review findings)

- **`S15-java-no-fallback`: catastrophic backtracking.** The catch-return
  fragment `\)\s*\{\s*(?:[^{}]*?;\s*){0,3}?return\b` could split one
  statement run in many ways. A catch body of 50 brace-free statements took
  about 7 s, and one of 60 took 65 s. The fragment is now
  `\)\s*\{(?:[^{};]*;){0,3}\s*return\b`, where each statement is consumed
  exactly one way, so a 2000-statement body takes 0.004 s. Its meaning is
  unchanged: `return` first, or after up to three statements, suppresses the
  detector. A new branch-wide guard, `test_java_detectors_are_fast_on_pathological_input`
  in `tests/detectors/test_java_detectors.py`, runs every Java detector on
  its own against five synthetic inputs, with a 1.0 s budget for each:
  - a 50-statement catch;
  - 2000 annotated methods;
  - 500 retry loops;
  - a 40 000-character line of `for (`/`catch (`/`poll(`/`.get(`/`.forEach(`;
  - 5000 unclosed `q.poll(a` lines.

  Before the fix it failed on S15 alone ("S15-java-no-fallback on long catch
  body: 6.95s"), and it passes after.
- **`S15-java-no-fallback`: Spring fallbacks.** Spring Retry's `@Recover`
  method is a fallback, and so is Spring Cloud CircuitBreaker's
  `CircuitBreakerFactory…create(…).run(supplier, fallback)`, whose fallback
  lambda need not use the word. Both now suppress the detector.
  → `S15/java/negative_recover.java`, `negative_circuit_breaker_factory.java`
- **`S10-java-nested-retry`: parameter annotations.** `METHOD_JAVA` rejected
  `=` anywhere after the opening parenthesis. So
  `page(@RequestParam(defaultValue = "1") String page) {` was not a
  declaration, and its retry loop merged into the previous method's
  `@Retryable`. The parameter list now allows one level of nested
  parentheses containing `=`, and stays linear.
  → `S10/java/negative_param_annotation_merge.java`
- **`S10-java-nested-retry`: qualified annotations.** The Java layer regexes
  missed fully qualified annotations (`@org.springframework.retry.annotation.Retryable`,
  `@io.github.resilience4j.retry.annotation.Retry(`). They now accept a
  qualified name.
- **`S10-java-nested-retry`: recall pins.** `S10/java/positive.java` now also
  holds `@Retryable` over a method with its own attempt loop, and resilience4j
  `@Retry` over `retryTemplate.execute(…)`. Each fires on its own.
- **The `@Configuration` guard is exercised.**
  `S10/java/negative_config_stack.java` stacks `Retry.decorateSupplier` and
  `retryTemplate.execute` in one `@Bean` method. It is silent only because of
  `SPRING_CONFIG`: with the guard disabled it fires "2 retry layers (Spring
  Retry, resilience4j retry)".
- **Re-sweep.** `--patterns S05,S10,S11,S12,S15` over all 16 repositories, with
  grpc-java filtered to `examples/`, is byte-identical to the sweep recorded
  above. The Hits section is unchanged.

### Hits

- `S11-java-grpc-no-deadline` grpc-java `examples/android/clientcache/app/src/main/java/io/grpc/clientcacheexample/ClientCacheExampleActivity.java:136` — TP: `stub.sayHello(request)` runs in an Android `AsyncTask` with no deadline. If the server stalls, the task never finishes. The server keeps working on a call that the user has already abandoned by leaving the screen.
- `S11-java-grpc-no-deadline` grpc-java `examples/android/helloworld/app/src/main/java/io/grpc/helloworldexample/HelloworldActivity.java:95` — TP: the same shape. The call gets no deadline, and the send button stays disabled until `onPostExecute`, which a hung call never reaches.
- `S11-java-grpc-no-deadline` grpc-java `examples/android/routeguide/app/src/main/java/io/grpc/routeguideexample/RouteGuideActivity.java:157` — TP: the blocking stub is handed to the `GetFeature` runnable, and `blockingStub.getFeature(request)` (line 200) is called with no deadline anywhere in the file.
- `S11-java-grpc-no-deadline` grpc-java `examples/android/strictmode/app/src/main/java/io/grpc/strictmodehelloworldexample/StrictModeHelloworldActivity.java:125` — TP: the same `AsyncTask` shape, over OkHttp, with no deadline.
- `S12-java-no-breaker` iexec-core `src/main/java/com/iexec/core/result/ResultService.java:50` — TP: `@Retryable(retryFor = FeignException.class)` retries calls to the result proxy (`resultProxyClient.getJwt(…)`, a Feign client) with Spring Retry's default 3 attempts. There is no breaker. While the proxy is down, every task check makes three calls into it.
- `S12-java-no-breaker` spring-kafka `spring-kafka/src/main/java/org/springframework/kafka/streams/KafkaStreamsInteractiveQueryService.java:94` — FP-accepted: `retryTemplate.execute(() -> kafkaStreams.store(…))` waits for a *local* state store to become queryable during a rebalance. No remote dependency is being called, so a breaker has no meaning. A regex cannot tell what the retried lambda does.
- `S15-java-no-fallback` spring-petclinic-microservices `spring-petclinic-genai-service/src/main/java/org/springframework/samples/petclinic/genai/VectorStoreController.java:68` — TP: on `ApplicationStartedEvent`, when no pre-built `vectorstore.json` exists, the listener calls `vets-service` through `WebClient…block()`. There is no fallback. If vets-service is down at that moment, the exception escapes the listener, and the genai service fails to start rather than starting with an empty vet index.

### Fixed during calibration

- `S11-java-grpc-no-deadline`: 29 hits on single-file CLI programs that declare `public static void main`, which is over the tripwire together with the next item. All in `examples/`:
  - `example-alts/…/HelloWorldAltsClient.java:88`, `example-debug/…/HelloWorldDebuggableClient.java:47`, `example-dualstack/…/DualStackClient.java:42`, `example-gauth/…/GoogleAuthClient.java:48`
  - `example-gcp-csm-observability/…/CsmObservabilityClient.java:44`, `example-gcp-observability/…/GcpObservabilityClient.java:39`, `example-jwt-auth/…/AuthClient.java:37`, `example-oauth/…/AuthClient.java:38`
  - `example-opentelemetry/…/OpenTelemetryClient.java:44`, `…/logging/LoggingOpenTelemetryClient.java:46`, `example-orca/…/CustomBackendMetricsClient.java:42`, `example-tls/…/HelloWorldClientTls.java:38`, `example-xds/…/XdsHelloWorldClient.java:41`
  - `src/main/java/io/grpc/examples/`: `cancellation/CancellationClient.java:118`, `customloadbalance/CustomLoadBalanceClient.java:45`, `errordetails/ErrorDetailsExample.java:38`, `errorhandling/DetailErrorSample.java:38`, `errorhandling/ErrorHandlingClient.java:36`
  - `src/main/java/io/grpc/examples/`: `experimental/CompressingHelloWorldClient.java:42`, `header/CustomHeaderClient.java:41`, `healthservice/HealthServiceClient.java:48`, `hedging/HedgingHelloWorldClient.java:50`, `helloworld/HelloWorldClient.java:34`
  - `src/main/java/io/grpc/examples/`: `keepalive/KeepAliveClient.java:37`, `loadbalance/LoadBalanceClient.java:34`, `multiplex/SharingClient.java:52`, `nameresolve/NameResolveClient.java:31`, `retrying/RetryingHelloWorldClient.java:49`, `routeguide/RouteGuideClient.java:27`

  FP-fixed. S11 is about propagating a deadline across hops: downstream work should not keep running after the caller has given up. A one-shot command-line client is the originating caller. When its user gives up, the process exits, and closing the channel cancels the server-side call, so the failure S11 describes cannot occur. A missing timeout on such a program is an S01 question. A `static void main(` in the file now suppresses the detector. → `S11/java/negative_cli_main.java`

  The line numbers are the first sweep's. The brief's anchor put four of these (`ErrorDetailsExample`, `DetailErrorSample`, `ErrorHandlingClient`, `RouteGuideClient`) on the `import` line, and it did the same to the `RouteGuideActivity` TP (`:33` in the first sweep, `:157` in the final one). The anchor now skips `import` lines.
- `S11-java-grpc-no-deadline` grpc-java `examples/src/main/java/io/grpc/examples/deadline/DeadlineServer.java:49` — FP-fixed. This is grpc-java's deadline-propagation demo. Its `SlowGreeter` service implementation calls a blocking stub from inside the request handler. grpc-java carries the inbound call's deadline in `io.grpc.Context` and applies it to outgoing calls made in that context, so the call has the caller's deadline without any `withDeadline`. A file that implements a gRPC service (`extends …ImplBase`, `implements …AsyncService`, `BindableService`) now suppresses the detector. (This file also has `main`, and a `Deadline…` identifier.) → `S11/java/negative_grpc_server_hop.java`
- `S05-java-client-calls-without-limiter`, 17 hits in grpc-java `examples/`:
  - `android/routeguide/…/RouteGuideActivity.java:200`, `example-alts/…/HelloWorldAltsClient.java:89`, `example-debug/…/HelloWorldDebuggableClient.java:60`, `example-dualstack/…/DualStackClient.java:88`
  - `example-gcp-csm-observability/…/CsmObservabilityClient.java:57`, `example-opentelemetry/…/OpenTelemetryClient.java:57`, `…/logging/LoggingOpenTelemetryClient.java:59`
  - `src/main/java/io/grpc/examples/`: `customloadbalance/CustomLoadBalanceClient.java:55`, `healthservice/HealthServiceClient.java:59`, `hedging/HedgingHelloWorldClient.java:86`, `loadbalance/LoadBalanceClient.java:44`
  - `src/main/java/io/grpc/examples/`: `manualflowcontrol/BidiBlockingClient.java:106`, `manualflowcontrol/ManualFlowControlClient.java:114`, `multiplex/SharingClient.java:76`, `nameresolve/NameResolveClient.java:76`, `retrying/RetryingHelloWorldClient.java:93`, `routeguide/RouteGuideClient.java:67`

  FP-fixed. In every one of these files, the stub call is outside every loop in the file. The loops are of four kinds:
  - fixed 5–50-iteration demo loops in `main` that drive a `greet()` helper;
  - `while (sendRpcs.get()) { client.greet(user); Thread.sleep(1000); }`, which is paced;
  - iteration over a streaming response or over a list of requests;
  - a 2000-task fan-out onto a `ForkJoinPool` (the hedging and retrying demos), whose parallelism is bounded by the core count.

  → `S05/java/negative_unrelated_loop.java` (locality) and `negative_polling_sleep.java` (the three paced loops)
- `S05-java-client-calls-without-limiter` jsoup `src/main/java11/org/jsoup/helper/HttpClientExecutor.java:87` and activemq-artemis-examples `examples/features/standard/security-oidc/src/main/java/org/apache/activemq/artemis/jms/example/OIDCSecurityExample.java:73` — FP-fixed. The anchor was `HttpClient.newBuilder()`, which builds a client and makes no call. → `S05/java/negative_client_factory_loop.java`
- `S15-java-no-fallback` jsoup `HttpClientExecutor.java:87` and activemq-artemis-examples `OIDCSecurityExample.java:73` (same lines), and spring-petclinic-microservices `spring-petclinic-api-gateway/…/ApiGatewayApplication.java:62` and `spring-petclinic-genai-service/…/AIBeanConfiguration.java:27` (`return WebClient.builder();` in a `@Bean` method) — FP-fixed. All four anchor on client construction, not on a call. → `S15/java/negative_client_config.java`
- `S12-java-no-breaker` iexec-core `src/main/java/com/iexec/core/replicate/ReplicateSupplyService.java:88` and `ReplicatesService.java:254` — FP-fixed. `@Retryable(retryFor = OptimisticLockingFailureException.class, …)` retries a conflicting write to the service's own database. That is contention, not a dead dependency, and a breaker would turn a harmless write conflict into an outage. A line that names `OptimisticLock` no longer anchors. → `S12/java/negative_optimistic_lock_retry.java`
- `S12-java-no-breaker` iexec-core `src/main/java/com/iexec/core/chain/IexecHubService.java:121` — FP-fixed. `MAX_RETRIES` is passed to `web3jService.repeatCheck(…)`, which waits for a chain state to appear, and nothing in this file retries. The anchor is now a retry mechanism in the file:
  - a `for`/`while` whose header names an attempt/retries/retryCount/tries/retry counter and which has a `try {` within 3 lines;
  - `@Retryable`;
  - `retryTemplate.execute(`;
  - `Failsafe.with`.

  → `S12/java/negative_constant_holder.java`
- `S12-java-no-breaker`, 4 hits anchored on the word "retries" in a string: grpc-java `examples/src/main/java/io/grpc/examples/retrying/RetryingHelloWorldClient.java:118` (a log message); spring-kafka `spring-kafka/src/main/java/org/springframework/kafka/listener/ErrorHandlingUtils.java:173` (`"Container stopped during retries"`), `listener/KafkaMessageListenerContainer.java:2209` (`"Commit retries exhausted"`), `retrytopic/ListenerContainerFactoryConfigurer.java:136` (`"Blocking retries back off has already been set…"`) — FP-fixed by the mechanism anchor. ErrorHandlingUtils's `while (retryable && nextBackOff != STOP)` names no counter. KafkaMessageListenerContainer's real commit retry is recursive (`doCommitSync(commits, retries + 1)`), which the anchor does not see (Known limitations). → `S12/java/negative_retry_word_in_message.java`
- `S12-java-no-breaker` spring-kafka `annotation/RetryableTopicAnnotationProcessor.java:172` (`builder.maxAttempts(attempts)`), `retrytopic/DestinationTopic.java:138`, `retrytopic/DestinationTopicPropertiesFactory.java:58` and `retrytopic/RetryTopicConfigurationBuilder.java:61` (`maxAttempts` fields) — FP-fixed. These classes compute retry-topic configuration and call nothing. `DestinationTopicPropertiesFactory`'s `for (… < this.retryTopicsAmount; …)` no longer counts as a retry loop: `retryTopicsAmount` is not a counter name, and the loop has no `try`. → `S12/java/negative_retry_topic_properties.java`
- `S12-java-no-breaker` spring-kafka `spring-kafka/src/main/java/org/springframework/kafka/support/ExponentialBackOffWithMaxRetries.java:80` — FP-fixed, found in the intermediate sweep after the mechanism anchor went in. `for (int i = 1; i < this.maxRetries; i++)` computes a backoff schedule. The loop-form anchor now requires a `try {` within 3 lines of the header. → `S12/java/negative_backoff_schedule_loop.java`

### Silences checked

- **The two resilience4j demos** produced no hit from any detector, before or after
  the fixes.
  - Their services stack `@CircuitBreaker`, `@Bulkhead`, `@Retry` and
    `@RateLimiter` on the same methods. That is one retry mechanism (S10), and
    its breaker is visible (S12).
  - Their controllers fall back with `.onErrorResume(…, fallback)` and
    `Try…recover(this::fallback)`.
  - They make no outbound HTTP call, so S05 and S15 have no anchor.
- **Probes of correct code** are silent under the final detectors
  (`$SCRATCH/t10/probes/`):
  - S05: a resilience4j `@RateLimiter` method called in a loop; a `@Scheduled`
    single call; a bounded `Flux.flatMap(…, 4)`.
  - S10: a resilience4j `@Retry` over a plain `RestTemplate`; a Feign `Retryer`
    bean.
  - S11: a deadline set with `CallOptions`/`Deadline.after`; a stub given a
    deadline at construction (see Known limitations); a future stub.
  - S12: resilience4j `@CircuitBreaker` beside `@Retryable`; Spring Cloud
    `CircuitBreakerFactory`.
  - S15: `@CircuitBreaker(fallbackMethod = …)`; Reactor `.onErrorResume`;
    `CompletableFuture.exceptionally`.
- **Recall probes** fire under the final detectors (`$SCRATCH/t10/recall/`):
  - S05: `ids.forEach(id -> { restTemplate.postForObject(…); })`, and a
    blocking-stub call inside a `for` loop's `try`.
  - S10: `@Retryable` on a method whose body runs its own `for (attempt …)`
    loop; resilience4j `@Retry` around `retryTemplate.execute(…)`.
  - S11: a blocking stub in a plain client class.
  - S12: a bare `@Retryable` method.
  - S15: a `WebClient` call beside an unrelated `JacksonException` catch (pinned
    in `positive.java`).

### Known limitations (noted, not fixed)

- **S05 is local to one loop body.**
  - It misses a loop in one method that drives a helper which makes the call.
    The grpc hedging and retrying demos' `ForkJoinPool` fan-outs have this
    shape.
  - It misses a call more than 8 lines below the loop header, or one that
    follows a line holding only `}` (the close of an inner block).
  - Any `sleep(` in the file suppresses it.
  - Only receivers named `…HttpClient`, `…RestTemplate`, `…WebClient` or `…Stub`
    count, so a `java.net.http.HttpClient` held in a variable called `client` is
    invisible.
  - An unbounded reactive fan-out (`Flux.flatMap` at its default concurrency of
    256) has no loop and is missed.
- **S10 groups layers by method** (grouping rules under **Tightened before
  calibration**). It misses stacking across methods (a `@Retryable` method that
  calls a helper with its own retry loop) and across files (a `@Retryable`
  method that calls another class's `@Retryable` method, or a Feign client
  whose `Retryer` is a bean). Any `@Configuration` class is silent. The
  declaration heuristic splits methods wrongly in three shapes:
  - a `throws` clause that continues onto the next line;
  - a lambda assigned to a field (`Supplier<String> b = () -> { … }`), whose
    body is attributed to the previous method;
  - a call statement whose arguments continue onto the next line
    (`log("starting",` followed by `"x");`). Its first line looks like the
    start of a multi-line declaration, so the statements after it get a new
    owner. `@Retryable` plus a loop below such a call is missed.

  In each shape, layers from two methods can merge into one owner (a false
  positive) or be separated (a miss).
- **S11 is file-scoped, and any identifier containing `deadline` suppresses it.**
  A business field such as `finalDeadline` can hide a real miss.
  - **Construction-time deadlines are silent.**
    `newBlockingStub(ch).withDeadlineAfter(2, SECONDS)` stored in a field is a
    known gRPC defect: the deadline is absolute, so every call made more than
    two seconds after construction fails with `DEADLINE_EXCEEDED`. The detector
    is silent on it anyway, because this is a wrong deadline, not a missing one.
    This was decided deliberately. The shape is not distinguishable from a
    per-call `stub.withDeadlineAfter(…)` without data flow.
  - **Interceptors in another file.** The detector still fires when a
    `ClientInterceptor` defined in another file sets the deadline, which is a
    common production setup. The `deadline` substring suppression only works
    when the interceptor is named in the same file.
  - **Async stubs are not anchored.** Future and async stubs (`newFutureStub`,
    `newStub`) are missed.
  - **Two file-wide exemptions.**
    - A `main` method anywhere in the file exempts it.
    - So does implementing a gRPC service, even when the blocking call is made
      outside a handler's `Context` (from a constructor or a background thread,
      where no deadline is inherited).
- **S12 misses several kinds of retry.**
  - Recursive retries (`doCommitSync(…, retries + 1)`).
  - `do { … } while (attempt < max)` loops.
  - Retry loops without a `try` within 3 lines.
  - Retries on a line that also names `OptimisticLock`.
  - A fully qualified `@org.springframework.retry.annotation.Retryable` (the
    anchor matches only the simple name; S10 was widened in fix round 1, and
    S12 was not).
  - A retry in a file that mentions resilience4j at all, as in the brief: an
    `@Retry` with no breaker is silent.
  - `retryTemplate.execute(…)` around local work fires. There is 1
    FP-accepted instance of this.
- **S15 is file-scoped.**
  - A thin client wrapper that catches the client exception and rethrows a
    domain exception still fires. That was decided deliberately. The wrapper
    delegates degradation to its callers, which the detector cannot see,
    exactly as a client that lets `RestClientException` propagate does. The
    hit is a lead for the investigator to follow to the call sites. There is
    no instance in this corpus.
  - A qualifying `catch … return` anywhere in the file suppresses it, even
    around a different call.
  - A call made only through a chain that starts with construction
    (`WebClient.create(url).get()…`) is missed. So is a chain that starts
    from a builder (`webClientBuilder.build().get()…`), because the receiver
    before the call is `build()`, not a client name.

## Batch 5 — Akka/JMS/RabbitMQ (Task 11): S06, S18, and the S01/S07/S13/S14 messaging idioms

The sweep ran `--patterns S06,S18,S01,S07,S13,S14`. S06 and S18 gain their
first Java detectors: `S06-java-single-pool-no-priority` and
`S18-java-validate-after-call` (the shared `s18_fail_fast` module, with
Java-only `FUNC_JAVA`, `VALIDATION_JAVA` and `EXTERNAL_CALL_JAVA`). Four
detectors are appended to patterns calibrated earlier:
`S01-java-jms-receive-no-timeout`, `S07-java-rabbitmq-auto-ack`,
`S13-java-akka-blocking-default-dispatcher` and `S14-java-rabbitmq-no-prefetch`.
Only those four are judged here. The sweep's other S01/S07/S13/S14 lines come
from detectors calibrated in Batches 1–3, so the TSVs were filtered to this
batch's six detector ids before counting.

The brief's four repositories come first. akka/akka-samples is archived and
mostly Scala; only its 39 Java files are swept (`--lang java`). The fourteen
clones from Batches 1–4 were swept as well, because the brief's four gave S06
and S18 almost nothing to work on (S06: 0 hits, S18: 1). The Batch 4 scope
rules apply: grpc-java is judged on `examples/` only, and spring-data-examples
excludes `jpa/deferred`. For the record, grpc-java outside `examples/` has 23
first-sweep lines (20 S06, 3 S18) and 4 final ones, all
`S06-java-single-pool-no-priority` in benchmarks, interop-test harnesses and a
JMH benchmark; they are not judged.

| Repo | Commit | Java files swept |
|---|---|---|
| spring-projects/spring-amqp-samples | `eee2e80577d2e22415ace5ad6a69dfd0ec2e6789` | 38 |
| rabbitmq/rabbitmq-tutorials | `586f18f75693d7fffe16ff3d29775f4176ba4ecc` | 90 |
| apache/activemq-artemis-examples | `37a1052bad9928f04f983fb6619088d43855f4a2` | 194 |
| akka/akka-samples | `eab644e38375553bafe1742baaa5a5aaff270621` | 39 (Java only) |
| resilience4j/resilience4j-spring-boot3-demo | `6c3e644d53174182fb79c0e49770b191a1d7287c` | 10 |
| resilience4j/resilience4j-spring-boot2-demo | `85590a025d1ff6ecf97f26502a14ab595a664305` | 10 |
| grpc/grpc-java | `9e0ff283e9a727546c46d889e02a9376c36ab411` | 98 in `examples/` (1132 in the repository) |
| spring-petclinic/spring-petclinic-microservices | `295fa8d5ee10f7b6daddf83a2c65f9051a87564b` | 53 |
| spring-projects/spring-kafka | `fff33914d4e450a33e17195e11a79937c3505605` | 387 |
| confluentinc/kafka-streams-examples | `3c40c0e27dd988d8b2d72951802d8fd9c9940a64` | 58 |
| jhy/jsoup | `49a15317317970a7ea3f0a5ded303ef319860f4a` | 98 |
| brettwooldridge/HikariCP | `a4d93f4f85517f90e632b795486d7102e933d7ff` | 49 |
| apache/commons-pool | `c4aba65cd8445685f89422b18219ea9853e4306d` | 57 |
| iExecBlockchainComputing/iexec-core | `a09dbba123f09ae352410c87bcb3788610536809` | 129 |
| spring-projects/spring-petclinic | `818c4136ea971c21674525f9053de0d9c7ad8cfe` | 30 |
| spring-projects/spring-data-examples | `7747029e6157cb780862826b6ae87c88d7a4df3c` | 6504 (6001 in `jpa/deferred`; no hits there) |
| jhipster/jhipster-sample-app | `6b000b5d23a36c45e01472471b84a44fa2464044` | 81 |
| spring-petclinic/spring-petclinic-reactive | `68534cf88a9d022467b9590b953ea4fc7f78bd6b` | 39 |

| Detector | Hits | TP | FP-fixed | FP-accepted | Deferred | Final |
|---|---|---|---|---|---|---|
| S06-java-single-pool-no-priority | 13 | 0 | 13 | 0 | | 0 |
| S18-java-validate-after-call | 8 | 0 | 8 | 0 | | 0 |
| S01-java-jms-receive-no-timeout | 3 | 3 (+9) | 0 | 0 | | 12 |
| S07-java-rabbitmq-auto-ack | 18 | 6 | 12 | 0 | | 6 |
| S13-java-akka-blocking-default-dispatcher | 0 | 0 | 0 | 0 | | 0 |
| S14-java-rabbitmq-no-prefetch | 18 | 0 | 18 | 0 | | 0 |

**Hits** is the first sweep, made with the brief's detectors unchanged.

- **No tripwire.** No detector had more than 25 hits in one repository. The
  most was 18 each for the two RabbitMQ detectors in rabbitmq-tutorials, which
  holds the same six consumers three times (`java/`, `java-mvn/`,
  `java-gradle/`).
- **S01's extra hits.** The final `present_within` also recognises
  `TopicSubscriber`/`createDurableSubscriber`, which the brief's did not, so
  artemis `DurableSubscriptionExample.java:95` appears only in the final sweep.
  Fix round 1 widened the look-back from 10 to 50 lines, which reaches 8 more
  untimed `receive()` calls whose consumer is created 12–43 lines above. All 9
  are TP. That is the "(+9)".
- **No S06, S13 or S14 true positive, and no S18 one.** None of the 18
  repositories mixes interactive and background work on one pool, blocks
  inside an actor, or runs a manual-ack RabbitMQ consumer without `basicQos`,
  and every S18 hit was a cross-method or non-call pairing. These four
  detectors are proven by their samples and the recall probes under
  **Silences checked**.

### Tightened before calibration

Common shapes of correct Java were run against the brief's detectors at the
same time as the first sweep (`$SCRATCH/t11/probes/`). The shapes below fired
and had no instance in the corpus. Each became a required-silent sample.

- `S06-java-single-pool-no-priority`:
  - **Virtual threads.** `Executors.newVirtualThreadPerTaskExecutor()` (and
    `newThreadPerTaskExecutor`) no longer anchors: a thread per task queues
    nothing behind a fixed set of workers. → `S06/java/negative_virtual_threads.java`
  - **Injected executors.** The brief's anchor included the bare type name
    `ExecutorService`, so a class handed its executor through the constructor,
    or a `shutdownQuietly(ExecutorService)` helper, fired. The anchor is now a
    pool the file creates. → `S06/java/negative_injected_executor.java`
- `S18-java-validate-after-call`:
  - **`ResponseStatusException` counts only with `BAD_REQUEST`.** After a
    call, `throw new ResponseStatusException(HttpStatus.BAD_GATEWAY)` or
    `.orElseThrow(() -> new ResponseStatusException(NOT_FOUND))` reports what
    the dependency returned, not a request that was never valid.
    → `S18/java/negative_response_status.java`
- `S01-java-jms-receive-no-timeout`: a JMS `import` no longer counts as
  evidence. `inbox.receive()` on the application's own `Inbox` type fired
  because `import javax.jms.Session;` was within 10 lines. `present_within`
  now needs a non-import line naming `MessageConsumer`, `JMSConsumer`,
  `QueueReceiver`, `TopicSubscriber`, a `create…Consumer/Receiver/Subscriber(`
  call or a qualified `javax.jms`/`jakarta.jms` name.
  `socket.receive(packet)` and `receiveNoWait()` were already silent.
  → `S01/java/negative_jms_custom_receive.java`
- `S07-java-rabbitmq-auto-ack`: direct reply-to
  (`basicConsume("amq.rabbitmq.reply-to", true, …)`) *requires* autoAck and is
  exempt. → `S07/java/negative_rabbitmq_exclusive_queue.java` (`replies`)
- `S13-java-akka-blocking-default-dispatcher`: a launcher whose `main` sleeps
  after `ActorSystem.create(Behaviors.setup(…))` blocks the main thread, not an
  actor. `static void main(` in the file now suppresses the detector.
  → `S13/java/negative_akka_main_sleep.java`. The other direction, a recall
  fix: `Patterns.ask(…).toCompletableFuture().get()` (or `.join()`) inside an
  actor blocks its dispatcher thread, and the brief's `require` did not see
  it. It is now one of the blocking calls.

### Fix round 1 (controller ruling)

- `S01-java-jms-receive-no-timeout`: `window_before` 10 → 50. The first
  recorded sweep left 8 inspected, genuine untimed `receive()` calls in artemis
  silent because the consumer was created 12–43 lines above the call. This is
  coverage for inspected TPs, not loosening to create hits, and the
  non-import evidence requirement is unchanged, so an import alone still does
  not qualify. `S01/java/positive.java` appends `JmsBatchReader`, whose
  `consumer.receive()` is 16 lines below `createConsumer` with no other JMS
  name in between; it fires alone under the new window and not under the old
  one. Every S01 negative stays silent, and the speed guard passes.
- **Re-sweep.** `--patterns S01` over all 18 repositories, filtered to this
  detector (grpc-java `examples/` and spring-data-examples without
  `jpa/deferred` as before): 12 lines, all in artemis — the 4 recorded before
  plus exactly the 8 former misses. No other repository gains a hit, and the
  tripwire is not reached. The Batch 5 final sweep is now 18 lines
  (12 S01 + 6 S07; S06, S13, S14 and S18 unchanged at 0).

### Fix round 2 (review findings)

- `S18-java-validate-after-call`: a check after the call that reads the
  call's result is response handling. It no longer counts as validation when
  it (or the `if (…)` line above a bare `throw`) names the variable the call
  line assigned, a variable later assigned from it (`Price body =
  r.getBody();`), or reads `getBody()`, `body()`, `getStatusCode()` or
  `statusCode()`. The reviewer's shapes: `Assert.notNull(p, …)` after
  `p = rest.getForObject(…)`, `Objects.requireNonNull(r.getBody())`,
  `Objects.requireNonNull(body, …)`, `validator.validate(result)`, and
  `if (resp.statusCode() >= 400) throw new IllegalArgumentException(…)`.
  Java-only; the TypeScript/Python path is unchanged and is now pinned by
  `tests/detectors/test_s18_ts_python_unchanged.py`.
  → `S18/java/negative_response_check.java`
- `S06-java-single-pool-no-priority`: a pass-through now needs the submitted
  identifier to be a `Runnable`/`Callable<…>`/`Supplier<…>` parameter,
  submitted before the method's first `}` (bounded to 600 characters, so the
  back-reference scan stays linear: 5000 unclosed `m(Runnable r) {` lines take
  0.2 s, and the case joins the speed guard). A Runnable field or a loader
  built in a loop is the class's own job. A bare `newFixedThreadPool(…)` (and
  `newCached…`, `newScheduled…`, `newSingleThread…`, `newWorkStealing…`) from a
  static import counts as a second pool.
  → `S06/java/negative_field_runnable.java`, `negative_local_runnable.java`
  (the ruling's two shapes are split across two files, because in one file
  the second pool alone would silence both), `negative_static_import_pools.java`
- `S07-java-rabbitmq-auto-ack` and `S14-java-rabbitmq-no-prefetch`: the queue
  argument may contain one level of parentheses. `basicConsume(props.getQueue(),
  true, cb)` now fires S07 (pinned by `RabbitConfiguredConsumer` in
  `S07/java/positive.java`, which fires alone) and is skipped by S14 as an
  autoAck consumer. → `S14/java/negative_auto_ack_call_arg.java`
- **Re-sweep.** `--patterns S06,S18,S07,S14` over all 18 repositories: in
  scope, S06, S18 and S14 remain at 0 and S07 at the same 6 lines; S01 is
  unchanged at 12. The final sweep is still 18 lines and **Hits** is unchanged.
  As a probe outside the recorded scope, grpc-java's 4 non-`examples/` S06
  lines drop to 2: `LoadClient.java:117` and `StressTestClient.java:239` go
  silent, and `UdsTcpEndpointConnector.java:45` and
  `SerializingExecutorBenchmark.java:43` remain through the two-site rule
  (see Known limitations).

### Hits

- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/broker-connection/ha-with-dual-mirror/src/main/java/org/apache/artemis/jms/example/Consumer.java:49` — TP: the consumer thread loops on `consumer.receive()` over a `failover:` URL with `maxReconnectAttempts=-1`. While the failover transport reconnects forever, `receive()` neither returns nor throws, so the loop never reaches its error handling and the thread cannot report that it has stopped consuming. A timed `receive(ms)` would let it notice.
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/broker-connection/ha-with-mesh-mirror/src/main/java/org/apache/artemis/jms/example/Consumer.java:49` — TP: the same consumer.
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/durable-subscription/src/main/java/org/apache/activemq/artemis/jms/example/DurableSubscriptionExample.java:74` — TP: a single `subscriber.receive()` for the message just published to the topic. If it is lost, the program hangs forever instead of failing (the subscriber is created 12 lines up; reached since fix round 1).
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/durable-subscription/src/main/java/org/apache/activemq/artemis/jms/example/DurableSubscriptionExample.java:95` — TP: a single `subscriber.receive()` for one expected message. If the message is lost or the subscription was not durable after all, the program hangs forever instead of failing.
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/request-reply/src/main/java/org/apache/activemq/artemis/jms/example/RequestReplyExample.java:100` — TP: the requester waits on `replyConsumer.receive()` for the reply with no timeout. A responder that is down or drops the request blocks the requester forever, the textbook request-reply hang (consumer created 20 lines up; fix round 1).
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/topic/src/main/java/org/apache/activemq/artemis/jms/example/TopicExample.java:73` — TP: `messageConsumer1.receive()` for the one published message; a lost message hangs the program (consumer created 17 lines up; fix round 1).
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/topic/src/main/java/org/apache/activemq/artemis/jms/example/TopicExample.java:78` — TP: the same for `messageConsumer2` (19 lines up; fix round 1).
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/scheduled-message/src/main/java/org/apache/activemq/artemis/jms/example/ScheduledMessageExample.java:78` — TP: `receive()` waits for a message scheduled 5 s ahead. If the broker drops or never delivers the scheduled message, the program blocks forever; a timeout of the schedule plus a margin would bound it.
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/xa-receive/src/main/java/org/apache/activemq/artemis/jms/example/XAReceiveExample.java:91` — TP: `xaConsumer.receive()` inside an open XA transaction branch. If the message never arrives, the thread blocks forever with the branch still open, so the transaction manager can neither commit nor time it out cleanly (consumer created 20 lines up; fix round 1).
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/xa-receive/src/main/java/org/apache/activemq/artemis/jms/example/XAReceiveExample.java:93` — TP: the second receive in the same branch (fix round 1).
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/xa-receive/src/main/java/org/apache/activemq/artemis/jms/example/XAReceiveExample.java:112` — TP: the same shape after the rollback, waiting for redelivery (41 lines up; fix round 1).
- `S01-java-jms-receive-no-timeout` activemq-artemis-examples `examples/features/standard/xa-receive/src/main/java/org/apache/activemq/artemis/jms/example/XAReceiveExample.java:114` — TP: the second redelivery receive (43 lines up; fix round 1).
- `S07-java-rabbitmq-auto-ack` rabbitmq-tutorials `java/Recv.java:25` — TP: autoAck on a durable quorum queue (`queueDeclare(QUEUE_NAME, true, …)`). A message is acked on delivery, so a crash while it is printed loses it although the queue was made durable to keep it.
- `S07-java-rabbitmq-auto-ack` rabbitmq-tutorials `java-mvn/src/main/java/Recv.java:25` — TP: the same file.
- `S07-java-rabbitmq-auto-ack` rabbitmq-tutorials `java-gradle/src/main/java/Recv.java:25` — TP: the same file.
- `S07-java-rabbitmq-auto-ack` rabbitmq-tutorials `java/ReceiveLogHeader.java:54` — TP: autoAck on a named durable queue (`queueDeclare(queueInputName, true, …)`), which outlives the consumer. Messages acked on delivery are lost on a crash.
- `S07-java-rabbitmq-auto-ack` rabbitmq-tutorials `java-mvn/src/main/java/ReceiveLogHeader.java:54` — TP: the same file.
- `S07-java-rabbitmq-auto-ack` rabbitmq-tutorials `java-gradle/src/main/java/ReceiveLogHeader.java:54` — TP: the same file.

### Fixed during calibration

- `S06-java-single-pool-no-priority`, 7 hits on a pool that is built and handed on, with no submission in the file: HikariCP `src/main/java/com/zaxxer/hikari/util/UtilityElf.java:188` (a `createThreadPoolExecutor` factory); resilience4j-spring-boot2-demo and resilience4j-spring-boot3-demo `src/main/java/io/github/robwin/controller/BackendBController.java:64` (a scheduled pool passed to resilience4j's `TimeLimiter`/`Retry` decorators); grpc-java `examples/example-alts/src/main/java/io/grpc/examples/alts/HelloWorldAltsClient.java:25`, `examples/example-alts/src/main/java/io/grpc/examples/alts/HelloWorldAltsServer.java:88`, `examples/src/main/java/io/grpc/examples/helloworld/HelloWorldServer.java:26` (`.executor(pool)` on a channel or server builder), `examples/example-orca/src/main/java/io/grpc/examples/orca/CustomBackendMetricsServer.java:55` (a scheduler passed to `OrcaServiceImpl.createService`) — FP-fixed. A pool with no submission site in the file has no callers here to prioritise; a gRPC server's executor runs only its RPCs. `require` now asks for more than one kind of work reaching a pool: two submission sites (`submit`/`invokeAll`/`invokeAny`/`supplyAsync`/`runAsync`, or `execute` on an executor-, pool-, worker- or scheduler-named receiver), or a pass-through of a caller's task (`pool.submit(task)`). → `S06/java/negative_executor_bean.java` (`ExecutorConfig`, `GreeterServer`). Two of these anchored on the `import` line, which the creation-only anchor also fixes.
- `S06-java-single-pool-no-priority`, 4 hits on a pool that runs one job of its own: iexec-core `src/main/java/com/iexec/core/chain/BlockchainConnectionHealthIndicator.java:77` (a scheduled connection check) and `src/main/java/com/iexec/core/task/TaskService.java:42` (one `submit(this::initializeCurrentTaskStatusesCount)`); kafka-streams-examples `src/main/java/io/confluent/examples/streams/microservices/OrderDetailsService.java:22` (one `execute(() -> startService(…))`); grpc-java `examples/src/main/java/io/grpc/examples/cancellation/CancellationServer.java:55` (one service's echo timers and a single `execute`) — FP-fixed by the same `require`. `schedule*` calls are periodic background work by nature and do not count as a submission site. → `S06/java/negative_single_purpose.java`
- `S06-java-single-pool-no-priority` HikariCP `src/main/java/com/zaxxer/hikari/pool/HikariPool.java:545` — FP-fixed. The brief's anchor matched the `ExecutorService` parameter type of `abortActiveConnections`. HikariPool creates its pools through a helper and already keeps them apart (connection adder, connection closer, housekeeping). → `S06/java/negative_injected_executor.java`
- `S06-java-single-pool-no-priority` HikariCP `src/main/java/com/zaxxer/hikari/pool/PoolBase.java:627` — FP-fixed. The network-timeout pool is handed to `Connection.setNetworkTimeout`. It survived the first `require` because the file's two JDBC `statement.execute(sql)` calls counted as submission sites; `execute(` now counts only on an executor-, pool-, worker- or scheduler-named receiver. → `S06/java/negative_statement_execute.java`
- `S18-java-validate-after-call` akka-samples `akka-sample-sharding-java/killrweather/src/main/java/sample/killrweather/WeatherRoutes.java:59` — FP-fixed. The "validation" is `default: throw new IllegalArgumentException(…)` in an unmarshaller lambda assigned to a field, and the "call" was `ref.ask(… new WeatherStation.Query(…))` in the method above: `EXTERNAL_CALL`'s case-insensitive `\.query\s*\(` matched `.Query(`. Three changes: a field line is a member boundary; a switch label that throws is an exhaustiveness check, not validation; and `EXTERNAL_CALL_JAVA` is now Java's own case-sensitive list. → `S18/java/negative_switch_default.java`, `negative_method_boundaries.java`
- `S18-java-validate-after-call` HikariCP `src/main/java/com/zaxxer/hikari/util/PropertyElf.java:239` — FP-fixed. The "call" was the reflective `method.invoke(target)` 147 lines up. HikariCP puts method braces on their own line, which the brief's `FUNC_JAVA` (brace on the header line, modifier required) never saw, so the whole class was one "method". Boundaries now use `METHOD_JAVA` (the S10 declaration regex, which takes Allman braces, package-private methods, multi-line parameter lists and annotated parameters) plus any line opening with `public`/`protected`/`private`/`static` or a type keyword. `.invoke(` is reflection and no longer a call. → `S18/java/negative_method_boundaries.java`, `negative_not_external.java`
- `S18-java-validate-after-call` spring-kafka `spring-kafka/src/main/java/org/springframework/kafka/config/MethodKafkaListenerEndpoint.java:177` — FP-fixed. The "call" was the word `got` inside an exception message (`"… (got " + …`), which the shared list matches case-insensitively; the "validation" was `Assert.state` in the next method, whose header spans four lines (two annotations and a two-line parameter list). → `S18/java/negative_not_external.java` (`check`), `negative_method_boundaries.java`
- `S18-java-validate-after-call` spring-kafka `spring-kafka/src/main/java/org/springframework/kafka/listener/adapter/HandlerAdapter.java:82` — FP-fixed. `invokerHandlerMethod.invoke(…)` dispatches to a local handler method, and `Objects.requireNonNull(this.delegatingHandler)` in the `else` branch checks internal state. → `S18/java/negative_not_external.java` (`dispatch`)
- `S18-java-validate-after-call` spring-data-examples `mongodb/transactions/src/main/java/example/springdata/mongodb/imperative/TransitionService.java:80`, `mongodb/transactions/src/main/java/example/springdata/mongodb/reactive/ReactiveManagedTransitionService.java:80`, `mongodb/transactions/src/main/java/example/springdata/mongodb/reactive/ReactiveTransitionService.java:78` — FP-fixed. `Assert.state` in the package-private `verify(…)` merged into `start(…)` above it, because the brief's `FUNC_JAVA` required a modifier; the "call" was `Query.query(Criteria…)`, which builds a query object. `Query.query(` no longer counts as a call. → `S18/java/negative_method_boundaries.java` (`reload`/`rename`), `negative_not_external.java`
- `S18-java-validate-after-call` jsoup `src/main/java11/org/jsoup/helper/HttpClientExecutor.java:144` — FP-fixed. `catch (URISyntaxException e) { throw new IllegalArgumentException("Malformed URL: " …) }` translates a failure of `req.url.toURI()`, which runs before `client.send(…)`. A validation-shaped throw on a `catch` line, or within two code lines below one, no longer counts. → `S18/java/negative_catch_translation.java`
- `S07-java-rabbitmq-auto-ack`, 12 hits on a server-named queue: rabbitmq-tutorials `ReceiveLogs.java:22`, `ReceiveLogsDirect.java:30`, `ReceiveLogsTopic.java:31` and `RPCClient.java:51`, each in `java/`, `java-mvn/src/main/java/` and `java-gradle/src/main/java/` — FP-fixed. `channel.queueDeclare().getQueue()` declares an exclusive, auto-delete queue that is deleted with the consumer's connection, so after a crash there is nothing left to redeliver whether the consumer acked or not. `absent_within` (25 lines back) now takes `queueDeclare()`, a `queueDeclare(name, durable, true, …)` with `exclusive=true`, and direct reply-to. → `S07/java/negative_rabbitmq_exclusive_queue.java`
- `S14-java-rabbitmq-no-prefetch`, 18 hits on autoAck consumers: rabbitmq-tutorials `Recv.java:25`, `ReceiveLogHeader.java:54`, `ReceiveLogs.java:22`, `ReceiveLogsDirect.java:30`, `ReceiveLogsTopic.java:31` and `RPCClient.java:51`, each in the three directories — FP-fixed. RabbitMQ ignores `basicQos` prefetch for a consumer in automatic-acknowledgement mode, so the control this detector says is missing would change nothing; the autoAck itself is `S07-java-rabbitmq-auto-ack`'s finding. The anchor now skips a `basicConsume` whose second argument is `true`. The two manual-ack consumers in the corpus (`Worker.java`, `RPCServer.java`) set `basicQos(1)` and were silent before and after. → `S14/java/negative_rabbitmq_auto_ack.java`

### Silences checked

- **spring-amqp-samples** produced no hit from any detector of this batch. Its
  consumers are Spring listener containers (`@RabbitListener`,
  `SimpleMessageListenerContainer` with `AcknowledgeMode.AUTO`, which acks
  after the listener returns), with the container's default prefetch; no raw
  `basicConsume`, no JMS.
- **akka-samples** (39 Java files) produced no S13 hit. No Java sample blocks
  inside an actor: they use `ask` with `pipeToSelf`/`CompletionStage`, and no
  `Thread.sleep`, JDBC, `RestTemplate`, `HttpClient.send` or `ask(…).get()`
  appears in the Java sources.
- **artemis's other JMS consumers** call `receive(timeout)` and are silent.
  After fix round 1, every untimed `receive()` in artemis's non-test sources
  is a hit.
- **TypeScript/Python S18 is unchanged (AC-16).** `s18_fail_fast` at HEAD and
  after this task were run on every TypeScript, JavaScript and Python file under
  `tests/`, `scripts/` and the built fixture repository (101 files, 10 S18
  hits): the output is identical for every file. The Java regexes are reached
  only when `_lang_key` is `java`.
- **Probes of correct code** are silent under the final detectors
  (`$SCRATCH/t11/probes/`):
  - S06: `ForkJoinPool.commonPool()`; `CompletableFuture.runAsync` with the
    default pool; a pool that only runs `submit(this)`.
  - S18: `Objects.requireNonNull` first, then the call; `@Valid` on a
    parameter; a builder chain before an `IllegalArgumentException`.
  - S13: an actor that offloads `Thread.sleep` to a `DispatcherSelector`
    executor.
  - S14: `basicQos` in a separate channel-setup method of the same file;
    Spring AMQP `setPrefetchCount(50)`.
- **Recall probes** fire under the final detectors (`$SCRATCH/t11/probes/r*.java`):
  - S06: one fixed pool fed by `userRequest(…)` and `nightlyExport()`.
  - S18: a package-private method, and a method with a multi-line parameter
    list, each validating after `client.send`/`postForObject`; JDBC
    `executeUpdate` then `Assert.hasText`.
  - S01: `JMSConsumer.receive()`.
  - S13: `Patterns.ask(…).toCompletableFuture().get()` in `AbstractActor`.
  - S14: the two-argument `basicConsume(queue, consumer)` (manual ack by
    default) with no `basicQos`.

### Known limitations (noted, not fixed)

- **S06 is file-scoped and keyword-suppressed.**
  - It anchors only `Executors.new…(` and `new ThreadPoolExecutor(`. Spring's
    `ThreadPoolTaskExecutor`, `new ForkJoinPool(…)`, `new
    ScheduledThreadPoolExecutor(…)` and a pool built by a helper method are
    invisible.
  - Any `priority`/`interactive`/`criticality`/`urgent`/`foreground`/
    `background`/`batch` substring suppresses it, including `executeBatch`.
    So does a second pool creation anywhere in the file.
  - A pool fed only through `schedule…` calls never fires, and `execute(` on a
    receiver not named like an executor, pool, worker or scheduler is not a
    submission.
  - Two submission sites of the *same* kind of work (two interactive
    endpoints, or a benchmark's own tasks) still fire. Deciding which work is
    interactive needs the investigator. Of the 4 grpc-java lines outside
    `examples/`, 2 remain for this reason (`UdsTcpEndpointConnector.java:45`,
    two stream pumps; `SerializingExecutorBenchmark.java:43`, a JMH benchmark).
  - A pass-through counts only as a `Runnable`/`Callable<…>`/`Supplier<…>`
    parameter submitted within 600 characters and before the method's first
    `}`. A wrapper that checks its argument in an `if` block first, or takes
    a task of its own interface type, is missed.
- **S18 recognises a fixed vocabulary.**
  - A call counts only as `send`, `sendAsync`, `exchange`, `retrieve`,
    `get/postForObject/Entity`, `executeQuery`, `executeUpdate`, `query`,
    `queryFor…`, `execute` on a non-executor receiver, or `generateContent`. A
    call through a domain client (`pricingClient.quote(…)`), a Feign interface
    or a repository is missed. `.send(` counts on any receiver, including an
    `SseEmitter`.
  - A check after the call is treated as response handling, and ignored,
    when it (or the `if (…)` line directly above a bare `throw`) names the
    variable the call line assigned, a variable later assigned from it, or a
    `getBody()`/`body()`/`getStatusCode()`/`statusCode()` read. A response
    check that reads the result some other way (a field the call stored into
    through a setter, or a helper's return value) still fires. Conversely, a
    genuine input check that happens to name the result variable is ignored.
  - A validation-shaped throw within two code lines below any `catch (` is
    ignored, even when the catch block has already closed.
  - The member boundary inherits `METHOD_JAVA`'s limitations (Batch 4): a call
    statement whose arguments continue onto the next line starts a spurious
    member, which can only split a method (a miss).
- **S01's JMS detector looks 50 lines back for the consumer.** A consumer
  created further up, or held in a field declared further up, is missed; so
  is one passed in as a parameter of a type not named on a line in reach. A
  non-JMS `x.receive()` within 50 lines of a JMS consumer would fire; there is
  no instance in the corpus. Spring's `JmsTemplate.receive()`/`receive(dest)`,
  which waits indefinitely under the default `receiveTimeout`, is missed. JMS 2.0 `receiveBody(Class)`, which also blocks
  forever, is not matched. A dedicated consumer thread that relies on
  `connection.close()` at shutdown to unblock `receive()` will fire.
- **S07's autoAck detector reads only a literal `true`.** `boolean autoAck =
  true; channel.basicConsume(q, autoAck, cb)` (the RabbitMQ client javadoc's
  style) and an `AUTO_ACK` constant are missed, and so is Spring AMQP's
  `AcknowledgeMode.NONE`. The exclusive-queue exemption looks 25 lines back,
  not at the queue actually consumed, so a durable queue consumed within 25
  lines of a `queueDeclare()` is silenced. The queue argument may contain one
  level of parentheses (`props.getQueue()`); deeper nesting is not matched.
- **S13's Akka detector is file-scoped.** A dispatcher assigned in
  `application.conf` (`akka.actor.deployment`) is invisible, so such an actor
  still fires. `static void main(` anywhere in the file suppresses it, so a
  single-file demo with a blocking actor and its launcher is missed. The
  blocking vocabulary is fixed (sleep, JDBC, `DriverManager`, `RestTemplate`,
  `HttpClient.send`, `toCompletableFuture().get()/join()`).
- **S14's RabbitMQ detector** fires on a consumer whose autoAck argument is a
  variable, even when it is `true`. `basicQos` set in another class (a channel
  factory) is invisible, and any `prefetch` substring suppresses it. An autoAck
  consumer on a server-named queue still receives an unbounded push, and
  neither S14 nor S07 reports it.
