# Java language support — design

**Requirements:** [#8](https://github.com/tomstagl/thunderstruck/issues/8). The problem statement, user stories, scope, acceptance criteria (AC-n) and success measures live in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-23-java-language-support.md`

This document describes how Java detection works and how its hit rate is kept trustworthy. Examples use generic package/class names; no organisation-specific code is referenced.

## 1. Architecture

No pipeline stage changes shape. Java is a new leaf under the existing catalog and detector modules — `signals.py`, `bundle.py`, `validate.py`, `report.py` and the investigator prompt are untouched.

```
catalog/stability.yaml     + languages.java, + detectors.java per S01–S19, + patterns S27–S29
scripts/detectors/modules.py   + "java" branch in _lang_key/SLEEP_RES, reuses _ts_block_end for brace scanning
tests/detectors/samples/<ID>/java/{positive,negative}/   new sample pairs, discovered by existing test collection
```

`signals.py` already drives extension-to-language resolution and detector dispatch generically from the catalog; adding `.java` to `languages` and `java:` blocks to existing patterns is sufficient for those patterns to start running on Java files with zero code changes outside the catalog and, where a `module` detector is used, `modules.py`.

## 2. New catalog patterns

Three failure mechanisms have no existing pattern to extend, because they don't occur in TS/Python the way they occur on the JVM. Each follows the same schema as S01–S26 (`id`, `name`, `tier`, `weight`, `metastable_role`, `failure_if_absent`, `references`, `detectors`).

**S27 — No blocking calls on non-blocking/event-loop threads.** `tier: A`, `metastable_role: amplifier`. A blocking call (JDBC, `Thread.sleep`, a blocking `HttpClient`) inside a Reactor operator, WebFlux handler, Netty channel handler, or Akka Streams stage occupies a thread meant to service many concurrent requests; one slow call starves the entire event loop rather than one request. Detector: `kind: regex`, anchored on blocking-call idioms (`Thread.sleep`, JDBC, `.block()`, a blocking `HttpClient.send`, `RestTemplate`/`JdbcTemplate`), with `present_within` requiring a Reactor/Netty/WebFlux/Akka-Streams type within ±12 lines. A blocking call in a plain servlet controller is not a violation of this pattern, because that thread model expects blocking calls. `absent_within` suppresses the hit when the work is offloaded (`subscribeOn`/`publishOn`, `Schedulers.boundedElastic()`). The context check is window-local rather than file-wide. A `regex` detector cannot see the whole file, and a `file_absent` detector could not point at the blocking line, so calibration measures what the window misses.

**S28 — Bounded, timed lock/wait acquisition.** `tier: A`, `metastable_role: sustaining`. A lock held across a slow call, or a wait with no bound, lets one stalled holder block every other thread indefinitely: a convoy that compounds under load instead of shedding it. A `synchronized` block or `lock()` around in-memory work is idiomatic, correct Java. Flagging every one would be exactly the false positive on correct code that the negative-control discipline forbids. So the detectors (`kind: regex`) flag three things. The first is a `synchronized` section, and the second an untimed `lock()`/`lockInterruptibly()`, in each case with a blocking call (I/O, `sleep`, JDBC, an untimed future wait) within the next 15 lines. The third is an untimed `Condition.await()`/`Object.wait()`. Only the timed overloads (`tryLock(long, TimeUnit)`, `await(long, TimeUnit)`) avoid the untimed-acquisition shape.

**S29 — Bounded query fan-out (no N+1 lazy-loading amplification).** `tier: A`, `metastable_role: amplifier`. Iterating a JPA/Hibernate collection result and touching a lazy association per row turns one query into N+1; under load this is a fan-out amplifier structurally identical to the missing-pagination problem S08 already names, but the mechanism (ORM lazy-loading inside a loop) is different enough that stretching S08's description would make it misleading. Detector: `kind: module`, new handler `s29_n_plus_one` — a regex alone cannot see "this getter is called inside a loop over a collection fetched without a fetch join," which is exactly the structural case module handlers exist for (see CLAUDE.md's catalog section on detector kinds).

These three are written framework-generically at the pattern level (`failure_if_absent` describes the mechanism, not "Spring" or "Hibernate") so a future language (Kotlin coroutines, Node async) can add its own `detectors.<lang>` block under the same pattern without a new ID — consistent with how S01's `failure_if_absent` already reads generically across TS/Python today.

## 3. Detector coverage map

Every Tier A/B pattern gets a `java:` detector block. Framework-specific idioms are additional detector entries *under the existing pattern*, not new pattern IDs — a pattern names a failure mechanism, and "missing timeout" is the same mechanism whether the client is `RestTemplate`, `WebClient`, or a raw JDBC driver.

| Pattern | Java/framework detectors added |
|---|---|
| S01 Timeouts | `RestTemplate`, `WebClient`, `OkHttpClient`, `java.net.http.HttpClient`, JDBC `DriverManager`/HikariCP `connectionTimeout`, gRPC channel deadline, JMS/RabbitMQ receive timeout, Kafka `request.timeout.ms` |
| S02 Backoff+jitter | `module` (`s02_backoff`, extended `_lang_key`/`SLEEP_RES`), Spring `@Retryable`, resilience4j `Retry` |
| S03 Honor pushback | 429/503 + `Retry-After` header handling in the same client libraries as S01 |
| S04 Transient-only retry | exception-type discrimination in `@Retryable`/resilience4j retry predicates |
| S05 Rate limiting | Bucket4j, resilience4j `RateLimiter` |
| S06 Prioritization | thread-pool/executor priority separation (`@Async` pool naming, Akka mailbox priority) |
| S07 Idempotent jobs | `module` (`s07_checkpoint`), Kafka manual offset commit, JMS ack mode, Spring Batch checkpoint |
| S08 Bounded pagination | Spring Data `Pageable`, Kafka `max.poll.records`, RabbitMQ `basicQos` prefetch |
| S09 Caching | Spring `@Cacheable`, Caffeine |
| S10 Retry layers/budget | `module` (`s10_retry_layers`), resilience4j + `@Retryable` stacking check |
| S11 Deadline propagation | gRPC `Context` deadlines, chained `WebClient` timeout propagation |
| S12 Circuit breaker | resilience4j `CircuitBreaker` configuration presence/threshold sanity |
| S13 Bulkheads | `ExecutorService`/`ThreadPoolExecutor` pool separation, resilience4j `Bulkhead`, Akka dispatcher isolation |
| S14 Backpressure | bounded vs. unbounded `ThreadPoolExecutor` queue, Akka Streams `OverflowStrategy`, Kafka `max.poll.records`, RabbitMQ QoS, JMS listener concurrency |
| S15 Graceful degradation | resilience4j `Fallback` |
| S16 Jitter on periodic work | Spring `@Scheduled`, Quartz |
| S17 Steady state | Hibernate second-level cache eviction, Caffeine `expireAfterWrite` |
| S18 Fail fast | `module` (`s18_fail_fast`) |
| S19 No error swallowing | empty or comment-only `catch` (a catch that logs is observable and is left to the investigator, as for TS/Python) |

Rows the plan defers, each with its reason, are listed at the end of the plan. None of them is named by an acceptance criterion.

Framework batches are phased (see plan) in this order: **JDK/core concurrency and HTTP clients first** (highest confidence, no framework-specific idiom risk), **then Spring/Hibernate/Kafka** (most common stack, moderate idiom risk), **then resilience4j/gRPC**, **then Akka/JMS/RabbitMQ last** (least common, least calibration confidence). A batch's detectors ship independently — a calibration miss in the last batch never blocks the first three.

## 4. Module handler changes

`scripts/detectors/modules.py` currently buckets every non-Python language into a single `"typescript"` key via `_lang_key`. Java gets its own key rather than falling into that bucket, because its idioms genuinely differ (`Thread.sleep`/`TimeUnit.*.sleep` vs. `setTimeout`, `final` locals, no arrow functions):

- `_lang_key` returns `"java"` for `ctx.lang == "java"`.
- `SLEEP_RES["java"]` matches `Thread\.sleep\s*\(`, `\b\w+\s*\.\s*sleep\s*\(` (covers `TimeUnit.SECONDS.sleep(`, and an injected `unit.sleep(`).
- `_numeric_constants`'s `_CONST_ASSIGN` regex already matches Java's `final int X = 2000;` form (it already lists `final` as an optional modifier keyword) — no change needed there.
- Brace-delimited block scanning (`_ts_block_end`) is reused for Java rather than forked, since both are C-family brace syntax. This is verified empirically during implementation (task-level, not a design commitment) rather than assumed correct from the outset — Java's checked-exception `catch` clauses and multi-catch (`catch (IOException | SQLException e)`) are the likely edge case to check against the existing scanner.
- `s29_n_plus_one` is a new handler. It runs only on files that touch persistence (JPA/Hibernate/Spring Data imports, `@Entity`/`@Transactional`, `EntityManager`, a `*Repository` type). It looks for a for-each whose body *navigates through* a getter on the loop element (`order.getLineItems().size()`), and any eager-fetch hint in the file suppresses it (`@EntityGraph`, `JOIN FETCH`, `Hibernate.initialize(`, `FetchType.EAGER`). A bare `order.getId()` reads a column of the row already loaded and is not flagged; chaining off the getter is what touches an association. This is a heuristic, not a real dataflow analysis. False positives are expected and are constrained the same way S07/S10 are: negative samples are required for "loop touches an eagerly fetched association" and for "loop reads a plain column".
- `s18_fail_fast` gains Java-specific vocabularies: `FUNC_JAVA` for method headers, `VALIDATION_JAVA` (`throw new IllegalArgumentException`, `Objects.requireNonNull`, `Preconditions.check*`, …) and `EXTERNAL_CALL_JAVA` (the shared set plus `RestTemplate`/`WebClient`/JDBC call names). They are selected by `_lang_key`. The shared `VALIDATION`/`EXTERNAL_CALL` regexes are not edited, because that would change TS/Python behaviour (AC-16).
- `s10_retry_layers` gets `RETRY_LAYERS["java"]`, which counts retry *mechanisms*: a hand-written loop, Spring Retry, resilience4j and Failsafe. `maxAttempts` is not counted separately, because it configures one of those mechanisms rather than adding a layer. For Java the handler also skips `@Configuration` classes. They define retry beans and never call through them, so two bean definitions are not two stacked layers.

## 5. Test strategy

**Sample-based (as today).** Every new Tier A pattern-language pair gets `tests/detectors/samples/<ID>/java/{positive,negative}/` — discovered automatically by the existing test collection, no test list to update. Negative samples specifically encode the false-positive traps analogous to the two documented TS/Python catches (a method that *defines* a retry helper isn't a second retry layer; saving returned rows isn't checkpointing a cursor) translated to Java idioms, plus new ones specific to the frameworks in play (e.g. a `@Retryable`-annotated method calling a plain `RestTemplate` inside it is one retry layer, not two; an `@EntityGraph`-annotated repository method touching a lazy association afterward is not N+1).

**Calibration corpus (new requirement for this feature).** Synthetic samples prove a regex matches what it was written for; they do not prove it behaves on code nobody wrote for the test. Before any Java detector batch is considered done:

1. Run the batch's detectors with `uv run scripts/calibrate.py --repo <path> --lang java --patterns <ids>` against 3–5 real, public Java repositories. This new dev tool sweeps every tracked file. `signals.py` is not used, because it reports hits only for the top-N recently churned files, so most hits would never be seen. Choose the repositories representative of that batch — e.g. a Spring Boot reference/sample app, a Kafka consumer library, a project using resilience4j — chosen for the Spring/Hibernate/Kafka and resilience4j/gRPC batches; the JDK/core batch can calibrate against any idiomatic Spring/plain-Java service, since it has no framework-specific risk.
2. Every hit is manually inspected. An unexpected hit that isn't a genuine antipattern becomes a new negative sample and, if it reveals the detector's window/anchor is too loose, a detector fix — the same loop that produced the S07/S10 fixes originally.
3. A hit rate is not required to reach a specific number (there is no ground truth corpus to compute precision/recall against); what's required is that the manual pass over real code finds zero *uninvestigated* false positives before the batch ships.
4. This calibration pass is a task in the plan per batch, not a one-time step at the end. A batch is not complete until its own calibration has run.
5. Results are committed to `docs/calibration/java.md`: repos and commit SHAs, per-detector hit counts, and a verdict for every hit. This is what lets a maintainer see what a detector's `confidence` rests on (ticket, user stories). A detector that produces more than 25 hits in one repo is treated as a precision failure and tightened before inspection. If it cannot be tightened, it is deferred rather than shipped uninspected.

**Confidence discipline.** No new Java or framework detector is assigned `confidence: high` in this pass. Framework-specific detectors (anything keyed to a library idiom rather than a JDK primitive) default to `confidence: low`; JDK/core-language detectors (raw `Thread`, `synchronized`, `java.net.http.HttpClient`) may use `confidence: medium`, matching the existing TS/Python precedent for detectors judged to have moderate but unverified precision. `high` is reserved for a pattern that has been through the calibration corpus with zero unexplained hits across all 3–5 calibration repos, and can be upgraded in a later pass once that evidence exists — this spec doesn't claim it upfront.

**Generated artifacts.** `uv run scripts/gen_catalog_docs.py` and `uv run scripts/gen_sample_report.py` are re-run once the catalog changes land; CI's `--check` mode fails the build if they're stale, so this isn't optional cleanup.

## 6. Degradation

No new degradation path. `lizard`'s complexity scoring already works on any file lizard supports, and lizard supports Java; if it doesn't (unlikely — lizard has first-class Java support), Java hotspots rank on churn alone with the existing "missing lizard" warning, unchanged from today's behavior for any language.

## 7. Decisions and rationale

- **No `aliases: java: X` entry.** Aliases exist so a detector written for one syntax can run unmodified against a near-identical one (JS inherits TS's regexes). Java shares no client-library idioms or syntax quirks with TS/Python worth reusing this way; every detector is written for Java specifically.
- **Framework antipatterns are detector entries under existing patterns, not new pattern IDs.** A pattern in this catalog names a stability mechanism (`failure_if_absent` is written mechanism-first, tool-agnostic); "Spring's `@Retryable` misused" and "hand-rolled retry loop misused" are the same mechanism (S02/S04), so they share a pattern ID and differ only in the detector's anchor regex. Only S27–S29 warranted new IDs because their *mechanism*, not just their library, is absent from the current catalog.
- **`s29_n_plus_one` is a module handler, not regex.** Regex can find a getter call or a loop, but "is this getter access inside a loop over a collection this method itself fetched" requires tracking a variable across lines — the same reasoning `s02_backoff`/`s07_checkpoint`/`s10_retry_layers` already establish for when a `module` handler is warranted over `regex`.
- **Confidence starts low/medium everywhere new, never high.** Stated in the test strategy — repeated here because it's a load-bearing decision, not a detail: the negative-control discipline (CLAUDE.md, "a false positive on correct code is a worse bug than a missed detection") means an unearned `high` confidence is actively harmful, since it weights the hit more heavily in `signals.py`'s ranking without evidence it deserves that weight.

## 8. Open design questions

None outstanding — the calibration-corpus requirement (raised during brainstorming) is the piece that would otherwise have been an open question about hit-rate guarantees, and it's now folded into §5 as a per-batch gate rather than left unresolved.
