## General

On Spring the thread a call runs on decides what it costs. A Spring MVC controller runs on a servlet thread that expects to block. A WebFlux handler, a Reactor operator or a Netty channel handler runs on an event-loop thread that serves many requests at once. Judge a call by the thread the surrounding code shows it on. Judge retry layers per method, the way Spring binds an annotation to the method it sits on.

## S10

**Counts as protection.** One retry mechanism on a call path: a hand-written loop, Spring Retry's `@Retryable`, resilience4j `Retry` or Failsafe. `maxAttempts` configures that mechanism; it is not a layer. `@Retryable` on one method and `@Retry` on another are one layer each.

**Does not count.** More than one retry mechanism in the same call path with no shared budget, such as `@Retryable` plus a resilience4j `Retry` on one call. A Feign client built with no retryer: `Retryer.Default` makes up to 5 attempts, a layer nobody wrote.

**Baseline.** A `@Configuration` or `@AutoConfiguration` class defines retry beans and never calls through them: two bean definitions are not two layers.

## S27

**Counts as protection.** Blocking work offloaded from the event loop with `subscribeOn` or `publishOn` on `Schedulers.boundedElastic()`.

**Does not count.** A blocking call (JDBC, `Thread.sleep`, a blocking `HttpClient.send`, `RestTemplate`, `JdbcTemplate`) inside a Reactor operator, a WebFlux handler, a Netty channel handler or an Akka Streams stage with no offload: one slow call starves every request the loop serves.

**Baseline.** A blocking call in a Spring MVC controller is correct: the servlet thread model expects it. `.block()` on a `WebClient` from Spring MVC is the documented way to use it; Reactor throws when `block()` runs on a non-blocking thread.

## S28

**Counts as protection.** A `synchronized` block or `lock()` around in-memory work only. A snapshot taken under the lock, with the I/O done after it is released. The timed overloads, `tryLock(long, TimeUnit)` and `await(long, TimeUnit)`.

**Does not count.** A `synchronized` section, or an untimed `lock()` or `lockInterruptibly()`, that makes a blocking call (I/O, `sleep`, JDBC, an untimed `join()`) before it ends: a stalled call holds the lock and every other thread queues behind it. An untimed `Condition.await()` or `Object.wait()`, which waits forever if the signal never comes.

**Baseline.** `synchronized` around in-memory work is idiomatic, correct Java.

## S29

**Counts as protection.** The loop's association fetched eagerly with the collection: `@EntityGraph`, `JOIN FETCH`, `Hibernate.initialize(` or `FetchType.EAGER`. A loop that reads only columns of the row already loaded, such as `order.getId()`.

**Does not count.** A for-each over a JPA, Hibernate or Spring Data result whose body navigates through a getter on the loop element, such as `order.getLineItems().size()`, with no eager fetch: each row loads its association, one query becomes N+1, and under load the fan-out amplifies.
