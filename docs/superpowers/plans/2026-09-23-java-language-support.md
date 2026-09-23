# Java Language Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `.java` as a scanned language, with detectors for every Tier A/B pattern (S01–S19) plus three Java-specific patterns (S27 event-loop blocking, S28 untimed lock acquisition, S29 N+1 query fan-out), covering both core JDK idioms and the Spring/Hibernate/Kafka/resilience4j/gRPC/Akka/JMS/RabbitMQ frameworks.

**Architecture:** Java is a leaf under the existing catalog-driven pipeline — no stage changes shape. `catalog/stability.yaml` gains `languages.java` and a `java:` detector block per pattern; `scripts/detectors/modules.py` gains a `"java"` branch wherever a module handler dispatches on language; new samples land under `tests/detectors/samples/<ID>/java/`, discovered automatically by the existing test collection once `tests/detectors/test_detectors.py`'s `EXT_LANG` map knows `.java`.

**Tech Stack:** Python ≥ 3.11 stdlib + `pyyaml` + `lizard` (already a dependency; has first-class Java support), pytest. Scripts run via `uv run` with PEP 723 metadata. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-23-java-language-support-design.md`. Requirements and acceptance criteria AC-1…AC-14 are in GitHub issue #8 (`gh issue view 8`).

## Global Constraints

- No new third-party dependencies. Detection is regex/heuristic only — no Java parser, no AST library (CLAUDE.md: "scripts for anything that must be reproducible," not a compiler).
- No `aliases: java: ...` entry — Java shares no syntax with TS/Python worth inheriting.
- Every new detector's `confidence` starts at `low` (framework-specific idiom) or `medium` (JDK/core-language primitive) — never `high` in this pass. `high` is earned only after a detector has been through its batch's calibration corpus with zero unexplained hits.
- Every Tier A pattern-language pair needs both `positive.java` and `negative.java` under `tests/detectors/samples/<ID>/java/` — `test_every_tier_a_pattern_has_both_samples` enforces this automatically once the catalog entry exists.
- Comments are already blanked language-generically by `_common.strip_comments` (`lang != "python"` → C-style `//`/`/* */`) — no change needed there for Java.
- Module handlers must never raise. A language key is added to a handler's per-language dict (`SLEEP_RES`, `RETRY_LAYERS`, the func-declaration dispatch) in the same task that gives a pattern its first `java:` catalog entry using that handler — never earlier, so an unfinished mapping is never reachable.
- Regenerate `skills/stability-catalog/references/patterns.md` (`uv run scripts/gen_catalog_docs.py`) and `examples/sample-report.md` (`uv run scripts/gen_sample_report.py`) once, at the end — CI's `--check` mode fails the build if they're stale.
- Full suite: `uv run --with pytest --with pyyaml --with lizard pytest tests/ -q`.
- Commit messages are imperative sentences in the repo's style and end with the session's `Co-Authored-By` trailer.

## Review Focus

1. **A `.java` file with no package statement, or with Windows line endings.** `signals.py` must not crash; `lizard` and the detectors must still run. (Task 1 `test_java_file_scans_without_crashing`)
2. **A retry annotation (`@Retryable`) or lock call split across multiple lines by a fluent builder.** Window-based `absent_within` detectors must not falsely fire just because the qualifying keyword sits one line outside the window. (Task 6 `test_retryable_annotation_multiline_still_suppresses_s02`)
3. **A method that *defines* a resilience wrapper (e.g. a `@Bean` factory method named `retryTemplate()`) rather than calling one.** Must not count as a second retry layer, mirroring the TS/Python `DECLARATION` guard. (Task 10 `test_defining_a_retry_bean_is_not_a_retry_layer`)
4. **A JPA repository method annotated `@EntityGraph` or a query using `JOIN FETCH`, iterated in a loop that also touches an association.** Must not fire S29 — the fetch is already eager. (Task 8 `test_entity_graph_suppresses_n_plus_one`)
5. **A blocking JDBC call inside a plain (non-reactive) Spring MVC `@RestController` method.** Must not fire S27 — that thread model expects blocking calls; only Reactor/WebFlux/Netty/Akka-Streams contexts qualify. (Task 3 `test_blocking_call_outside_reactive_context_does_not_fire`)

---

### Task 1: Java language plumbing

Satisfies: AC-1 (`.java` recognized as a language, scans without crashing).

**Files:**
- Modify: `catalog/stability.yaml` — add `languages.java`
- Modify: `scripts/detectors/modules.py:72-73` (`_lang_key`)
- Modify: `tests/detectors/test_detectors.py:18` (`EXT_LANG`)
- Test: `tests/test_java_plumbing.py`

**Interfaces:**
- Consumes: `_common.language_map`, `_common.detect_language` (unchanged signatures).
- Produces: `_lang_key(ctx) -> str` now returns `"java"` for a Java context — every later task's module-handler work depends on this.

- [ ] **Step 1: Write the failing tests**

`tests/test_java_plumbing.py`:

```python
"""Java is a new leaf under the existing pipeline: a language mapping, a
_lang_key branch, and nothing else changes shape. This pins that the
pipeline doesn't crash on Java before any detector exists for it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import _common


def test_java_extension_maps_to_java_language(catalog):
    langmap = _common.language_map(catalog)
    assert _common.detect_language("src/Main.java", langmap) == "java"


def test_java_file_scans_without_crashing(tmp_path, plugin_root):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    java_file = repo / "src" / "Main.java"
    java_file.parent.mkdir(parents=True)
    java_file.write_text(
        "public class Main {\r\n"
        "    public static void main(String[] args) {\r\n"
        "        System.out.println(\"hi\");\r\n"
        "    }\r\n"
        "}\r\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add Main.java"], cwd=repo, check=True)

    result = subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "signals.py"),
         "--repo", str(repo), "--top", "5"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())
    assert data["schema"] == "thunderstruck.hotspots/v1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_java_plumbing.py -v`
Expected: FAIL — `test_java_extension_maps_to_java_language` fails because `.java` isn't in the catalog yet; the scan test may pass already (an unrecognized extension is just skipped, not a crash) but is written now so later tasks can't silently break it.

- [ ] **Step 3: Add `.java` to the catalog**

In `catalog/stability.yaml`, immediately after the `python:` entry under `languages:`:

```yaml
  python:
    extensions: [".py", ".pyi"]
  java:
    extensions: [".java"]
```

- [ ] **Step 4: Add the `java` branch to `_lang_key`**

In `scripts/detectors/modules.py`, replace:

```python
def _lang_key(ctx) -> str:
    return "python" if ctx.lang == "python" else "typescript"
```

with:

```python
def _lang_key(ctx) -> str:
    if ctx.lang == "python":
        return "python"
    if ctx.lang == "java":
        return "java"
    return "typescript"
```

- [ ] **Step 5: Add `.java` to the sample-discovery test harness**

In `tests/detectors/test_detectors.py`, change:

```python
EXT_LANG = {".ts": "typescript", ".py": "python"}
```

to:

```python
EXT_LANG = {".ts": "typescript", ".py": "python", ".java": "java"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_java_plumbing.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py tests/detectors/test_detectors.py tests/test_java_plumbing.py
git commit -m "Add .java as a recognized language

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: S01 timeouts — JDK/core HTTP and JDBC clients

Satisfies: AC-2 (S01 fires on Java clients missing a timeout, stays silent when one is set).

**Files:**
- Modify: `catalog/stability.yaml` (S01 `detectors:` block, add `java:`)
- Create: `tests/detectors/samples/S01/java/positive.java`
- Create: `tests/detectors/samples/S01/java/negative.java`

- [ ] **Step 1: Write the samples first (they double as the detector's spec)**

`tests/detectors/samples/S01/java/positive.java`:

```java
package com.example.client;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.sql.Connection;
import java.sql.DriverManager;

public class UserClient {
    private final HttpClient client = HttpClient.newBuilder().build();

    public String fetchUser(String userId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/users/" + userId))
                .build();
        return client.send(request, java.net.http.HttpResponse.BodyHandlers.ofString()).body();
    }

    public Connection openConnection() throws Exception {
        return DriverManager.getConnection("jdbc:postgresql://db/app");
    }
}
```

`tests/detectors/samples/S01/java/negative.java`:

```java
package com.example.client;

import java.net.http.HttpClient;
import java.time.Duration;
import com.zaxxer.hikari.HikariConfig;

public class UserClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    public HikariConfig poolConfig() {
        HikariConfig config = new HikariConfig();
        config.setConnectionTimeout(3000);
        return config;
    }
}
```

- [ ] **Step 2: Run tests to verify the positive sample doesn't yet fire (S01 has no java detector)**

Run: `uv run --with pytest --with pyyaml --with lizard pytest "tests/detectors/test_detectors.py::test_sample[S01-java-positive]" -v`
Expected: FAIL — `test_samples_exist`/parametrize won't even collect this case yet since no `java` key exists under S01; this step is really confirming the files are in place before the catalog entry exists. Skip straight to Step 3 if pytest reports "no tests ran" rather than a failure — that's the same signal.

- [ ] **Step 3: Add the S01 Java detectors**

In `catalog/stability.yaml`, under pattern `S01`'s `detectors:`, add a `java:` sibling to `typescript:`/`python:`:

```yaml
      java:
        - id: S01-java-httpclient-no-timeout
          kind: regex
          pattern: '\bHttpClient\s*\.\s*newBuilder\s*\(\s*\)'
          absent_within: '\bconnectTimeout\s*\('
          window: 6
          confidence: medium
          note: "java.net.http.HttpClient built with no connectTimeout()"
        - id: S01-java-okhttp-no-timeout
          kind: regex
          pattern: '\bOkHttpClient\s*\.\s*Builder\s*\(\s*\)|new\s+OkHttpClient\s*\.\s*Builder\s*\(\s*\)'
          absent_within: '\b(connectTimeout|readTimeout|writeTimeout|callTimeout)\s*\('
          window: 8
          confidence: medium
          note: "OkHttpClient.Builder with no timeout configured"
        - id: S01-java-jdbc-no-timeout
          kind: regex
          pattern: '\bDriverManager\s*\.\s*getConnection\s*\(|new\s+HikariConfig\s*\(\s*\)'
          absent_within: '\b(setConnectionTimeout|setLoginTimeout|connectionTimeout)\b'
          window: 10
          confidence: low
          note: "JDBC/HikariCP connection setup with no connection/login timeout"
        - id: S01-java-completablefuture-no-timeout
          kind: regex
          pattern: '\.\s*(get|join)\s*\(\s*\)'
          present_within: '\bCompletableFuture\b'
          window: 4
          window_before: 4
          confidence: low
          note: "CompletableFuture.get()/join() with no timeout — blocks forever if the future never completes"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest "tests/detectors/test_detectors.py" -k "S01-java" -v`
Expected: PASS for both `S01-java-positive` and `S01-java-negative`.

- [ ] **Step 5: Run the full detector suite to confirm no regression**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -q`
Expected: all pass, including `test_every_catalog_regex_compiles` and `test_detector_ids_are_unique`.

- [ ] **Step 6: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S01/java
git commit -m "Add S01 Java detectors for HttpClient, OkHttp, JDBC/HikariCP

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: S27 (new pattern) — no blocking calls on non-blocking/event-loop threads

Satisfies: AC-3 (new pattern S27 exists, catalogued and detected), AC-4 (S27 stays silent outside a reactive/event-loop context).

**Files:**
- Modify: `catalog/stability.yaml` — insert new pattern `S27` after `S26`, before the `tier_c:` section
- Create: `tests/detectors/samples/S27/java/positive.java`
- Create: `tests/detectors/samples/S27/java/negative.java`
- Create: `tests/detectors/samples/S27/java/negative_plain_controller.java` (Review Focus #5)

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S27/java/positive.java`:

```java
package com.example.pipeline;

import reactor.core.publisher.Mono;

public class OrderHandler {
    public Mono<String> loadOrder(String orderId) {
        return Mono.fromSupplier(() -> {
            try {
                Thread.sleep(50);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            return jdbcLookup(orderId);
        });
    }

    private String jdbcLookup(String orderId) {
        return "order-" + orderId;
    }
}
```

`tests/detectors/samples/S27/java/negative.java`:

```java
package com.example.pipeline;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class OrderHandler {
    public Mono<String> loadOrder(String orderId) {
        return Mono.fromCallable(() -> jdbcLookup(orderId))
                .subscribeOn(Schedulers.boundedElastic());
    }

    private String jdbcLookup(String orderId) {
        return "order-" + orderId;
    }
}
```

`tests/detectors/samples/S27/java/negative_plain_controller.java` (Review Focus #5 — blocking is fine on a plain MVC thread):

```java
package com.example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    @GetMapping("/orders/{id}")
    public String getOrder(String id) throws InterruptedException {
        Thread.sleep(50);
        return jdbcLookup(id);
    }

    private String jdbcLookup(String id) {
        return "order-" + id;
    }
}
```

- [ ] **Step 2: Add the S27 pattern to the catalog**

In `catalog/stability.yaml`, after `S26`'s block and before the `tier_c:` comment/section, insert (this stays in the main `patterns:` list, not `tier_c`, since it is actively detected):

```yaml
  - id: S27
    name: No blocking calls on non-blocking/event-loop threads
    tier: A
    weight: 1.0
    metastable_role: amplifier
    failure_if_absent: >-
      A blocking call inside a reactive pipeline or an event-loop handler
      occupies a thread meant to service many concurrent requests. One slow
      call starves the whole event loop instead of one request.
    references:
      - "Project Reactor reference docs — Schedulers and blocking calls"
      - "Nygard, Release It! (2nd ed.), ch. 4 — Blocked Threads"
    detectors:
      java:
        - id: S27-java-blocking-in-reactor
          kind: regex
          pattern: '\bThread\s*\.\s*sleep\s*\(|\bDriverManager\s*\.\s*getConnection\s*\(|\.\s*(get|join)\s*\(\s*\)\s*;'
          present_within: '\b(reactor\.core|Mono|Flux|WebFlux|io\.netty|akka\.stream)\b'
          window: 12
          window_before: 12
          confidence: low
          note: "blocking call inside a Reactor/WebFlux/Netty/Akka-Streams context — starves the event loop"
```

- [ ] **Step 3: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k S27 -v`
Expected: `S27-java-positive` fires, `S27-java-negative` and `S27-java-negative_plain_controller` stay silent.

- [ ] **Step 4: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S27
git commit -m "Add S27: no blocking calls on non-blocking/event-loop threads

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: S28 (new pattern) — bounded, timed lock/wait acquisition

Satisfies: AC-5 (new pattern S28 exists and is detected).

**Files:**
- Modify: `catalog/stability.yaml` — insert new pattern `S28` after `S27`
- Create: `tests/detectors/samples/S28/java/positive.java`
- Create: `tests/detectors/samples/S28/java/negative.java`

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S28/java/positive.java`:

```java
package com.example.inventory;

public class StockLedger {
    public synchronized void reserve(String sku, int qty) {
        deduct(sku, qty);
    }

    private void deduct(String sku, int qty) { }
}
```

`tests/detectors/samples/S28/java/negative.java`:

```java
package com.example.inventory;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class StockLedger {
    private final ReentrantLock lock = new ReentrantLock();

    public void reserve(String sku, int qty) throws InterruptedException {
        if (lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            try {
                deduct(sku, qty);
            } finally {
                lock.unlock();
            }
        }
    }

    private void deduct(String sku, int qty) { }
}
```

- [ ] **Step 2: Add the S28 pattern to the catalog**

```yaml
  - id: S28
    name: Bounded, timed lock/wait acquisition
    tier: A
    weight: 1.0
    metastable_role: sustaining
    failure_if_absent: >-
      A stalled lock holder blocks every other thread indefinitely — a
      convoy that compounds under load instead of shedding it.
    references:
      - "Nygard, Release It! (2nd ed.), ch. 4 — Blocked Threads"
      - "java.util.concurrent.locks.Lock javadoc — tryLock(long, TimeUnit)"
    detectors:
      java:
        - id: S28-java-synchronized-block
          kind: regex
          pattern: '\bsynchronized\s*(\([^)]*\))?\s*\{|\bsynchronized\s+\w'
          confidence: low
          note: "synchronized with no timeout — a stalled holder blocks every other thread indefinitely"
        - id: S28-java-untimed-lock
          kind: regex
          pattern: '\.\s*lock\s*\(\s*\)|\.\s*lockInterruptibly\s*\(\s*\)|\.\s*await\s*\(\s*\)'
          absent_within: '\.\s*tryLock\s*\(\s*\d|\.\s*await\s*\(\s*\d'
          window: 4
          confidence: low
          note: "Lock.lock()/Condition.await() with no timed variant used nearby"
```

- [ ] **Step 3: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k S28 -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S28
git commit -m "Add S28: bounded, timed lock/wait acquisition

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: S13/S14 — bulkheads and bounded queues (JDK/core batch close-out) + calibration

Satisfies: AC-6 (S13/S14 fire on Java thread-pool/queue misuse), AC-7 (JDK/core batch calibrated against real code before Spring work starts).

**Files:**
- Modify: `catalog/stability.yaml` (S13, S14 `detectors:` blocks, add `java:`)
- Create: `tests/detectors/samples/S13/java/positive.java`, `negative.java`
- Create: `tests/detectors/samples/S14/java/positive.java`, `negative.java`

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S13/java/positive.java`:

```java
package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class WorkerRegistry {
    private static final ExecutorService POOL = Executors.newFixedThreadPool(10);

    public void submitInteractive(Runnable r) {
        POOL.submit(r);
    }

    public void submitBatch(Runnable r) {
        POOL.submit(r);
    }
}
```

`tests/detectors/samples/S13/java/negative.java`:

```java
package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class WorkerRegistry {
    // Bulkhead: interactive and batch work never share a pool.
    private static final ExecutorService INTERACTIVE_POOL = Executors.newFixedThreadPool(10);
    private static final ExecutorService BATCH_POOL = Executors.newFixedThreadPool(4);

    public void submitInteractive(Runnable r) {
        INTERACTIVE_POOL.submit(r);
    }

    public void submitBatch(Runnable r) {
        BATCH_POOL.submit(r);
    }
}
```

`tests/detectors/samples/S14/java/positive.java`:

```java
package com.example.workers;

import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class UnboundedPool {
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(
            4, 4, 60, TimeUnit.SECONDS, new LinkedBlockingQueue<>());
}
```

`tests/detectors/samples/S14/java/negative.java`:

```java
package com.example.workers;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedPool {
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(
            4, 4, 60, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(200),
            new ThreadPoolExecutor.CallerRunsPolicy());
}
```

- [ ] **Step 2: Add the S13 Java detector**

```yaml
      java:
        - id: S13-java-single-executor
          kind: file_absent
          anchor: '(?i)\bExecutorService\b|\bExecutors\s*\.\s*new\w+ThreadPool\s*\('
          absent: '(?i)\b(bulkhead|separate|dedicated|isolat|partition)\w*\b'
          confidence: low
          note: "one shared ExecutorService with no isolation between workloads"
```

(add this `java:` block as a sibling of S13's existing `typescript:`/`python:` entries)

- [ ] **Step 3: Add the S14 Java detector**

```yaml
      java:
        - id: S14-java-unbounded-linkedblockingqueue
          kind: regex
          pattern: 'new\s+LinkedBlockingQueue\s*(<[^>]*>)?\s*\(\s*\)'
          confidence: medium
          note: "LinkedBlockingQueue() with no capacity — unbounded by default, absorbs overload instead of shedding it"
```

(add as a sibling of S14's existing `typescript:`/`python:` entries)

- [ ] **Step 4: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S13 or S14" -v`
Expected: PASS.

- [ ] **Step 5: Calibration corpus pass (JDK/core batch — S01, S27, S28, S13, S14)**

Clone 3–5 real, public Java repositories that don't use Spring/Hibernate/Kafka (e.g. a plain JDK HTTP/JDBC utility library, a small concurrency-focused OSS project). Run:

```bash
uv run scripts/signals.py --repo /path/to/each-repo --top 30 --since 24m
```

For every hit from `S01-java-*`, `S27-java-*`, `S28-java-*`, `S13-java-*`, `S14-java-*` in the resulting `.thunderstruck/hotspots.json`, open the cited file:line and judge it by hand.

- An unexpected hit that is not a genuine instance of the pattern becomes a new negative sample under the matching `tests/detectors/samples/<ID>/java/` directory (any filename other than `positive.java`/`negative.java` — the test harness treats any other stem as a required-silent case), and, if it reveals the window or anchor is too loose, fix the detector regex and re-run this task's tests.
- Record which repos were used and how many hits were inspected in the task's commit message. This satisfies AC-7 — it is a manual judgment pass, not a coverage percentage, because there is no ground-truth corpus to compute precision/recall against.

- [ ] **Step 6: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S13/java tests/detectors/samples/S14/java
git commit -m "Add S13/S14 Java detectors; calibrate JDK/core batch against real repos

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: S02/S03/S04 — backoff, honoring pushback, transient-only retry

Satisfies: AC-8 (S02–S04 fire on raw retry loops and misconfigured `@Retryable`/resilience4j retry, stay silent on correct usage).

**Files:**
- Modify: `catalog/stability.yaml` (S02, S03, S04 `detectors:` blocks, add `java:`)
- Modify: `scripts/detectors/modules.py` — add `SLEEP_RES["java"]`
- Create: `tests/detectors/samples/S02/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S03/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S04/java/{positive,negative}.java`

**Interfaces:**
- Consumes: `_lang_key` (Task 1), `s02_backoff` (existing, unmodified — it already dispatches on `_lang_key(ctx)`).
- Produces: `SLEEP_RES["java"]` — a new dict key later tasks do not need, since S02 is the only pattern that reads it.

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S02/java/positive.java` (constant, unjittered retry wait):

```java
package com.example.client;

public class RetryingClient {
    public String call() throws InterruptedException {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return doCall();
            } catch (Exception e) {
                Thread.sleep(2000);
            }
        }
        throw new IllegalStateException("exhausted retries");
    }

    private String doCall() { return "ok"; }
}
```

`tests/detectors/samples/S02/java/negative.java` (capped exponential backoff with jitter):

```java
package com.example.client;

import java.util.concurrent.ThreadLocalRandom;

public class RetryingClient {
    private static final long BASE_MS = 100;
    private static final long MAX_MS = 5000;

    public String call() throws InterruptedException {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return doCall();
            } catch (Exception e) {
                long backoff = Math.min(MAX_MS, BASE_MS * (1L << attempt));
                long jittered = ThreadLocalRandom.current().nextLong(backoff);
                Thread.sleep(jittered);
            }
        }
        throw new IllegalStateException("exhausted retries");
    }

    private String doCall() { return "ok"; }
}
```

`tests/detectors/samples/S03/java/positive.java` (429 handled, `Retry-After` never read):

```java
package com.example.client;

import java.net.http.HttpResponse;

public class RetryingClient {
    public void handle(HttpResponse<String> response) {
        if (response.statusCode() == 429) {
            retry();
        }
    }

    private void retry() { }
}
```

`tests/detectors/samples/S03/java/negative.java`:

```java
package com.example.client;

import java.net.http.HttpResponse;

public class RetryingClient {
    public void handle(HttpResponse<String> response) {
        if (response.statusCode() == 429) {
            response.headers().firstValue("Retry-After").ifPresent(this::retryAfter);
        }
    }

    private void retryAfter(String value) { }
}
```

`tests/detectors/samples/S04/java/positive.java` (catches everything, retries everything):

```java
package com.example.client;

public class RetryingClient {
    public String call() {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return doCall();
            } catch (Exception e) {
                continue;
            }
        }
        throw new IllegalStateException("exhausted retries");
    }

    private String doCall() { return "ok"; }
}
```

`tests/detectors/samples/S04/java/negative.java` (discriminates transient from permanent):

```java
package com.example.client;

import java.io.IOException;

public class RetryingClient {
    public String call() {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return doCall();
            } catch (IOException e) {
                if (!isTransient(e)) {
                    throw new RuntimeException(e);
                }
            }
        }
        throw new IllegalStateException("exhausted retries");
    }

    private boolean isTransient(IOException e) { return true; }
    private String doCall() { return "ok"; }
}
```

- [ ] **Step 2: Add `SLEEP_RES["java"]` in `modules.py`**

In `scripts/detectors/modules.py`, extend the `SLEEP_RES` dict (currently `"typescript"` and `"python"` keys) with:

```python
SLEEP_RES: dict[str, list[re.Pattern]] = {
    "typescript": [
        re.compile(r"setTimeout\s*\(\s*[^,]+?,\s*(?P<arg>[^),]+)"),
        re.compile(r"\b(?:sleep|delay|wait|pause)\s*\(\s*(?P<arg>[^),]*)"),
    ],
    "python": [
        re.compile(r"\b(?:time|asyncio)\s*\.\s*sleep\s*\(\s*(?P<arg>[^),]*)"),
        re.compile(r"\b(?:sleep|delay)\s*\(\s*(?P<arg>[^),]*)"),
    ],
    "java": [
        re.compile(r"\bThread\s*\.\s*sleep\s*\(\s*(?P<arg>[^),]*)"),
        re.compile(r"\b\w+\s*\.\s*sleep\s*\(\s*(?P<arg>[^),]*)"),
    ],
}
```

- [ ] **Step 3: Add the S02 Java module detector entry**

```yaml
      java:
        - id: S02-java-backoff
          kind: module
          handler: s02_backoff
          confidence: medium
          note: "retry backoff missing a cap, jitter, or growth"
```

- [ ] **Step 4: Add the S03 Java detectors**

```yaml
      java:
        - id: S03-java-429-ignores-retry-after
          kind: file_absent
          anchor: '\b429\b|TOO_MANY_REQUESTS'
          absent: '[Rr]etry-?[Aa]fter|RETRY_AFTER'
          require: '(?i)\b(retry|retries|retrying|attempt|attempts|backoff|sleep)\b'
          confidence: high
          note: "file handles 429 but never reads Retry-After"
        - id: S03-java-503-ignores-retry-after
          kind: file_absent
          anchor: '\b503\b|SERVICE_UNAVAILABLE'
          absent: '[Rr]etry-?[Aa]fter|RETRY_AFTER'
          require: '(?i)\b(retry|retries|retrying|attempt|attempts|backoff|sleep)\b'
          confidence: low
          note: "file handles 503 but never reads Retry-After"
```

- [ ] **Step 5: Add the S04 Java detector**

```yaml
      java:
        - id: S04-java-catch-exception-retry
          kind: regex
          pattern: 'catch\s*\(\s*Exception\s+\w+\s*\)'
          present_within: '\b(continue|retry|attempt)\b'
          window: 6
          confidence: medium
          note: "catch (Exception e) followed by a retry — retries permanent errors too"
```

- [ ] **Step 6: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S02 or S03 or S04" -v`
Expected: PASS. Also add and run the multiline-suppression regression test named in Review Focus #2:

`tests/detectors/samples/S02/java/negative_multiline_annotation.java`:

```java
package com.example.client;

import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;

public class RetryingClient {
    @Retryable(
        maxAttempts = 3,
        backoff = @Backoff(delay = 100, multiplier = 2, maxDelay = 5000, random = true)
    )
    public String call() {
        return doCall();
    }

    private String doCall() { return "ok"; }
}
```

Run: `uv run --with pytest --with pyyaml --with lizard pytest "tests/detectors/test_detectors.py" -k "S02-java" -v`
Expected: PASS — `s02_backoff` requires retry context plus a sleep call to fire at all; this file has neither `Thread.sleep` nor a bare sleep call, so it is silent regardless of the annotation spanning multiple lines. This pins that a future S02 detector addition aimed at `@Retryable`/`@Backoff` config (not planned in this pass, since `s02_backoff` only looks at explicit sleep calls) does not regress on multiline annotations.

- [ ] **Step 7: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py tests/detectors/samples/S02/java tests/detectors/samples/S03/java tests/detectors/samples/S04/java
git commit -m "Add S02/S03/S04 Java detectors for raw retry loops

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Spring/Hibernate batch, part 1 — S01 Spring clients, S09 caching, S16 jitter, S17 steady state

Satisfies: AC-9 (Spring/Hibernate-specific detectors for these four patterns).

**Files:**
- Modify: `catalog/stability.yaml` (S01 add two more `java:` entries; S09, S16, S17 add `java:` blocks)
- Create: `tests/detectors/samples/S09/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S16/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S17/java/{positive,negative}.java`

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S09/java/positive.java`:

```java
package com.example.catalog;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class ProductLookup {
    private final Map<String, String> cache = new ConcurrentHashMap<>();

    public String get(String sku) {
        if (cache.containsKey(sku)) {
            return cache.get(sku);
        }
        String value = fetchFromDb(sku);
        cache.put(sku, value);
        return value;
    }

    private String fetchFromDb(String sku) { return "product-" + sku; }
}
```

`tests/detectors/samples/S09/java/negative.java`:

```java
package com.example.catalog;

import org.springframework.cache.annotation.Cacheable;

public class ProductLookup {
    @Cacheable(value = "products", sync = true)
    public String get(String sku) {
        return fetchFromDb(sku);
    }

    private String fetchFromDb(String sku) { return "product-" + sku; }
}
```

`tests/detectors/samples/S16/java/positive.java`:

```java
package com.example.jobs;

import org.springframework.scheduling.annotation.Scheduled;

public class SyncJob {
    @Scheduled(cron = "0 0 * * * *")
    public void syncAll() {
        run();
    }

    private void run() { }
}
```

`tests/detectors/samples/S16/java/negative.java`:

```java
package com.example.jobs;

import org.springframework.scheduling.annotation.Scheduled;

public class SyncJob {
    @Scheduled(fixedDelayString = "${sync.interval}", initialDelayString = "#{new java.util.Random().nextInt(60000)}")
    public void syncAll() {
        run();
    }

    private void run() { }
}
```

`tests/detectors/samples/S17/java/positive.java`:

```java
package com.example.catalog;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class ProductLookup {
    private final Map<String, String> cache = new ConcurrentHashMap<>();

    public void put(String sku, String value) {
        cache.put(sku, value);
    }
}
```

`tests/detectors/samples/S17/java/negative.java`:

```java
package com.example.catalog;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;

public class ProductLookup {
    private final Cache<String, String> cache = Caffeine.newBuilder()
            .expireAfterWrite(Duration.ofMinutes(10))
            .maximumSize(10_000)
            .build();

    public void put(String sku, String value) {
        cache.put(sku, value);
    }
}
```

- [ ] **Step 2: Add the S01 Spring client detectors**

Add to S01's existing `java:` block from Task 2:

```yaml
        - id: S01-java-resttemplate-no-timeout
          kind: regex
          pattern: 'new\s+RestTemplate\s*\(\s*\)|new\s+SimpleClientHttpRequestFactory\s*\(\s*\)'
          absent_within: '\b(setConnectTimeout|setReadTimeout)\s*\('
          window: 8
          confidence: medium
          note: "RestTemplate built with no connect/read timeout"
        - id: S01-java-webclient-no-timeout
          kind: regex
          pattern: '\bWebClient\s*\.\s*builder\s*\(\s*\)|\bWebClient\s*\.\s*create\s*\('
          absent_within: '\bresponseTimeout\s*\(|\.\s*timeout\s*\('
          window: 8
          confidence: medium
          note: "WebClient built with no responseTimeout()"
```

- [ ] **Step 3: Add the S09 Java detector**

```yaml
      java:
        - id: S09-java-cache-aside-no-singleflight
          kind: file_absent
          anchor: '(?i)\bcache\s*\.\s*(get|containsKey)\s*\('
          absent: '(?i)\b(singleflight|coalesc|dedupe|dedup|computeIfAbsent|@Cacheable|LoadingCache)\b'
          confidence: medium
          note: "cache-aside read with no in-flight deduplication (no computeIfAbsent, LoadingCache, or @Cacheable)"
```

- [ ] **Step 4: Add the S16 Java detectors**

```yaml
      java:
        - id: S16-java-scheduled-fixed-no-jitter
          kind: regex
          pattern: '@\s*Scheduled\s*\('
          absent_within: '(?i)\b(jitter|random|fixedDelayString|initialDelayString)\b'
          present_within: '\bcron\s*=|\bfixedRate\s*='
          window: 3
          confidence: medium
          note: "@Scheduled with a fixed cron/fixedRate and no jitter — every instance fires in lockstep"
```

- [ ] **Step 5: Add the S17 Java detector**

```yaml
      java:
        - id: S17-java-cache-without-bound
          kind: file_absent
          anchor: '(?i)new\s+ConcurrentHashMap\s*(<[^>]*>)?\s*\(\s*\)|\bcache\s*\.\s*put\s*\('
          absent: '(?i)\b(ttl|expire|expireAfter|evict|maximumSize|Caffeine|@Cacheable)\b'
          confidence: medium
          note: "in-memory cache (ConcurrentHashMap or similar) with no TTL, eviction, or size bound"
```

- [ ] **Step 6: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S01 or S09 or S16 or S17" -v`
Expected: PASS.

- [ ] **Step 7: Calibration corpus pass (Spring/Hibernate batch part 1)**

Run the batch's detectors (`S01-java-resttemplate-no-timeout`, `S01-java-webclient-no-timeout`, `S09-java`, `S16-java`, `S17-java`) against 3–5 real, public Spring Boot repositories (e.g. the official `spring-petclinic`, a popular Spring Boot starter template, a Spring Cloud sample). Inspect every hit by hand; add negative samples for any false positive found, and note the repos/hit counts inspected in the commit message, per the calibration gate defined in the spec (§5) and Task 5.

- [ ] **Step 8: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S09/java tests/detectors/samples/S16/java tests/detectors/samples/S17/java
git commit -m "Add Spring/Hibernate Java detectors for S01/S09/S16/S17; calibrate

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: S29 (new pattern) — N+1 query fan-out, plus S08 pagination

Satisfies: AC-10 (new pattern S29 detects Hibernate N+1 lazy-loading fan-out and is silent when eagerly fetched), AC-11 (S08 fires on Spring Data/Kafka/RabbitMQ unbounded fetch).

**Files:**
- Modify: `catalog/stability.yaml` — insert new pattern `S29` after `S28`; S08 `detectors:` block add `java:`
- Create: `scripts/detectors/modules.py` — add `s29_n_plus_one` handler
- Create: `tests/detectors/samples/S29/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S08/java/{positive,negative}.java`

**Interfaces:**
- Consumes: `Result = list[tuple[int, str]]` (existing type alias in `modules.py`).
- Produces: `s29_n_plus_one(ctx) -> Result`.

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S29/java/positive.java`:

```java
package com.example.orders;

import java.util.List;

public class OrderReportService {
    public void printLineItemCounts(List<Order> orders) {
        for (Order order : orders) {
            System.out.println(order.getLineItems().size());
        }
    }
}

class Order {
    List<Object> getLineItems() { return List.of(); }
}
```

`tests/detectors/samples/S29/java/negative.java`:

```java
package com.example.orders;

import java.util.List;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public class OrderReportService {
    public void printLineItemCounts(List<Order> orders) {
        for (Order order : orders) {
            System.out.println(order.getLineItems().size());
        }
    }
}

interface OrderRepository extends JpaRepository<Order, Long> {
    @EntityGraph(attributePaths = "lineItems")
    List<Order> findAll();
}

class Order {
    List<Object> getLineItems() { return List.of(); }
}
```

`tests/detectors/samples/S08/java/positive.java`:

```java
package com.example.orders;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByStatus(String status);
}

class Order { }
```

`tests/detectors/samples/S08/java/negative.java`:

```java
package com.example.orders;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
    Page<Order> findByStatus(String status, Pageable pageable);
}

class Order { }
```

- [ ] **Step 2: Write the `s29_n_plus_one` module handler**

In `scripts/detectors/modules.py`, add near the other module handlers:

```python
# --------------------------------------------------------------------------
# S29 — bounded query fan-out (no N+1 lazy-loading amplification)
# --------------------------------------------------------------------------

# A loop variable's getter called inside the loop body, on the loop's own
# element, is the N+1 shape: one call per row instead of one call total.
COLLECTION_LOOP_JAVA = re.compile(
    r"for\s*\(\s*[\w<>\[\],\s]+\s+(\w+)\s*:\s*[\w.]+\s*\)")
GETTER_CALL = re.compile(r"\b(\w+)\s*\.\s*get\w+\s*\(")
EAGER_FETCH_HINT = re.compile(
    r"(?i)@EntityGraph|JOIN\s+FETCH|Hibernate\s*\.\s*initialize\s*\(")


def s29_n_plus_one(ctx) -> Result:
    if EAGER_FETCH_HINT.search(ctx.code_text):
        return []  # the association this file loads is already eager
    lines = ctx.code_lines
    out: Result = []
    for i, line in enumerate(lines):
        m = COLLECTION_LOOP_JAVA.search(line)
        if not m:
            continue
        var = m.group(1)
        end = _ts_block_end(lines, i)
        body = "\n".join(lines[i:end + 1])
        for gm in GETTER_CALL.finditer(body):
            if gm.group(1) == var:
                out.append((i + 1, (
                    f"loop over `{var}` calls a getter on each element with no "
                    "eager fetch hint (@EntityGraph, JOIN FETCH, Hibernate.initialize) "
                    "in this file — likely N+1 queries")))
                break
        if len(out) >= 3:
            break
    return out
```

- [ ] **Step 3: Add the S29 pattern to the catalog**

```yaml
  - id: S29
    name: Bounded query fan-out (no N+1 lazy-loading amplification)
    tier: A
    weight: 1.0
    metastable_role: amplifier
    failure_if_absent: >-
      Iterating a result set and touching a lazy association per row turns
      one query into N+1. Under load this is a fan-out amplifier — the same
      mechanism as an unbounded result set, but produced by ORM lazy loading
      rather than a missing limit.
    references:
      - "Hibernate reference docs — Association fetching"
      - "Nygard, Release It! (2nd ed.), ch. 4 — Unbounded Result Sets"
    detectors:
      java:
        - id: S29-java-n-plus-one
          kind: module
          handler: s29_n_plus_one
          confidence: low
          note: "loop touches a lazy association per row with no eager fetch hint in the file"
```

- [ ] **Step 4: Add the S08 Java detector**

```yaml
      java:
        - id: S08-java-jparepository-no-pageable
          kind: file_absent
          anchor: '(?i)interface\s+\w+\s+extends\s+\w*Repository\b'
          absent: '(?i)\bPageable\b|\bPage<'
          confidence: low
          note: "Spring Data repository with no Pageable-returning method — every finder returns the full table"
```

- [ ] **Step 5: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S29 or S08" -v`
Also run the Review Focus #4 regression:

`uv run --with pytest --with pyyaml --with lizard pytest "tests/detectors/test_detectors.py" -k "S29-java-negative" -v`

Expected: all PASS; `test_module_handlers_exist` (in `tests/detectors/test_detectors.py`) also passes now that `s29_n_plus_one` exists.

- [ ] **Step 6: Calibration corpus pass (S29, S08)**

Run against 3–5 real Spring Data JPA / Hibernate repositories. S29 is the highest false-positive risk detector in this plan (a heuristic loop+getter scan, not real dataflow) — inspect every hit by hand and expect to add several negative samples (e.g. a loop that calls a getter for a field on the *same* entity that was fetched directly, not a lazy association — this is a known gap the calibration pass must characterize, not silently accept). Record findings in the commit message.

- [ ] **Step 7: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py tests/detectors/samples/S29/java tests/detectors/samples/S08/java
git commit -m "Add S29 (N+1 fan-out) and S08 Java detectors; calibrate

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Messaging batch — S07 idempotent jobs, S19 error swallowing

Satisfies: AC-12 (S07/S19 fire on Kafka/JMS consumer misuse).

**Files:**
- Modify: `catalog/stability.yaml` (S07, S19 `detectors:` blocks, add `java:`)
- Create: `tests/detectors/samples/S07/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S19/java/{positive,negative}.java`

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S07/java/positive.java`:

```java
package com.example.consumer;

import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class OrderConsumer {
    private final KafkaConsumer<String, String> consumer;

    public OrderConsumer(KafkaConsumer<String, String> consumer) {
        this.consumer = consumer;
    }

    public void run() {
        while (true) {
            ConsumerRecords<String, String> records = consumer.poll(java.time.Duration.ofMillis(100));
            process(records);
        }
    }

    private void process(ConsumerRecords<String, String> records) { }
}
```

`tests/detectors/samples/S07/java/negative.java`:

```java
package com.example.consumer;

import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class OrderConsumer {
    private final KafkaConsumer<String, String> consumer;

    public OrderConsumer(KafkaConsumer<String, String> consumer) {
        this.consumer = consumer;
    }

    public void run() {
        while (true) {
            ConsumerRecords<String, String> records = consumer.poll(java.time.Duration.ofMillis(100));
            process(records);
            consumer.commitSync();
        }
    }

    private void process(ConsumerRecords<String, String> records) { }
}
```

`tests/detectors/samples/S19/java/positive.java`:

```java
package com.example.consumer;

public class OrderConsumer {
    public void handle(Runnable task) {
        try {
            task.run();
        } catch (Exception e) {
        }
    }
}
```

`tests/detectors/samples/S19/java/negative.java`:

```java
package com.example.consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderConsumer {
    private static final Logger log = LoggerFactory.getLogger(OrderConsumer.class);

    public void handle(Runnable task) {
        try {
            task.run();
        } catch (Exception e) {
            log.error("task failed", e);
        }
    }
}
```

- [ ] **Step 2: Add the S07 Java detector**

```yaml
      java:
        - id: S07-java-kafka-no-manual-commit
          kind: file_absent
          anchor: '\bKafkaConsumer\b'
          absent: '(?i)\b(commitSync|commitAsync|enable\.auto\.commit\s*=\s*false)\b'
          require: '\.\s*poll\s*\('
          confidence: medium
          note: "KafkaConsumer.poll() loop with no manual offset commit — relies on auto-commit, which can ack a record before it's actually processed"
```

- [ ] **Step 3: Add the S19 Java detector**

```yaml
      java:
        - id: S19-java-empty-catch
          kind: regex
          pattern: 'catch\s*\([^)]*\)\s*\{\s*\}'
          confidence: high
          note: "empty catch block — the failure leaves no trace"
```

- [ ] **Step 4: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S07 or S19" -v`
Expected: PASS.

- [ ] **Step 5: Calibration corpus pass (messaging batch)**

Run against 3–5 real Kafka-consumer or JMS-listener Java repositories. Inspect every hit; add negative samples for false positives (e.g. a consumer that legitimately relies on `enable.auto.commit=false` set only in a properties file the detector can't see — note this as a documented limitation rather than chasing a config-file cross-reference, which is out of scope per the spec's regex-only, no-AST constraint).

- [ ] **Step 6: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S07/java tests/detectors/samples/S19/java
git commit -m "Add S07/S19 Java detectors for Kafka/JMS consumers; calibrate

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: resilience4j/gRPC batch — S05, S10, S11, S12, S15

Satisfies: AC-13 (resilience4j/gRPC-specific detectors for rate limiting, retry-layer stacking, deadline propagation, circuit breaking, and fallback).

**Files:**
- Modify: `catalog/stability.yaml` (S05, S10, S11, S12, S15 `detectors:` blocks, add `java:`)
- Modify: `scripts/detectors/modules.py` — add `RETRY_LAYERS["java"]`
- Create: `tests/detectors/samples/S05/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S10/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S10/java/negative_defines_retry_bean.java` (Review Focus #3)
- Create: `tests/detectors/samples/S11/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S12/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S15/java/{positive,negative}.java`

**Interfaces:**
- Consumes: `s10_retry_layers(ctx)`, `DECLARATION` regex (existing — already matches `(public|private|protected)\s+`, which covers a Java method's modifier, so a Java factory-method declaration line is already excluded without changes to `DECLARATION` itself).
- Produces: `RETRY_LAYERS["java"]`.

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S05/java/positive.java`:

```java
package com.example.client;

import java.util.List;

public class BulkClient {
    public void fetchAll(List<String> ids) {
        for (String id : ids) {
            call(id);
        }
    }

    private void call(String id) { }
}
```

`tests/detectors/samples/S05/java/negative.java`:

```java
package com.example.client;

import io.github.bucket4j.Bucket;
import java.util.List;

public class BulkClient {
    private final Bucket bucket;

    public BulkClient(Bucket bucket) {
        this.bucket = bucket;
    }

    public void fetchAll(List<String> ids) {
        for (String id : ids) {
            bucket.asBlocking().consumeUninterruptibly(1);
            call(id);
        }
    }

    private void call(String id) { }
}
```

`tests/detectors/samples/S10/java/positive.java` (two independent retry layers, no shared budget):

```java
package com.example.client;

public class DoublyRetriedClient {
    public String call() {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return sdkCall();
            } catch (Exception e) {
                // retry loop layer one
            }
        }
        throw new IllegalStateException("exhausted");
    }

    private String sdkCall() {
        int maxAttempts = 3;
        return "ok";
    }
}
```

`tests/detectors/samples/S10/java/negative.java`:

```java
package com.example.client;

public class SingleLayerClient {
    public String call() {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return sdkCall();
            } catch (Exception e) {
                // one retry layer only
            }
        }
        throw new IllegalStateException("exhausted");
    }

    private String sdkCall() {
        return "ok";
    }
}
```

`tests/detectors/samples/S10/java/negative_defines_retry_bean.java` (Review Focus #3 — defining a wrapper is not a second layer):

```java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.retry.support.RetryTemplate;

public class RetryConfig {
    @Bean
    public RetryTemplate retryTemplate() {
        return new RetryTemplate();
    }
}
```

`tests/detectors/samples/S11/java/positive.java`:

```java
package com.example.grpc;

import io.grpc.ManagedChannel;
import example.OrderServiceGrpc;

public class OrderClient {
    private final OrderServiceGrpc.OrderServiceBlockingStub stub;

    public OrderClient(ManagedChannel channel) {
        this.stub = OrderServiceGrpc.newBlockingStub(channel);
    }

    public String getOrder(String id) {
        return stub.getOrder(id);
    }
}
```

`tests/detectors/samples/S11/java/negative.java`:

```java
package com.example.grpc;

import io.grpc.ManagedChannel;
import example.OrderServiceGrpc;
import java.util.concurrent.TimeUnit;

public class OrderClient {
    private final OrderServiceGrpc.OrderServiceBlockingStub stub;

    public OrderClient(ManagedChannel channel) {
        this.stub = OrderServiceGrpc.newBlockingStub(channel);
    }

    public String getOrder(String id) {
        return stub.withDeadlineAfter(2, TimeUnit.SECONDS).getOrder(id);
    }
}
```

`tests/detectors/samples/S12/java/positive.java`:

```java
package com.example.client;

public class RetryingClient {
    private static final int MAX_RETRIES = 3;

    public String call() {
        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
            try {
                return doCall();
            } catch (Exception e) {
                // no circuit breaker — keeps calling a dependency that is already dead
            }
        }
        throw new IllegalStateException("exhausted");
    }

    private String doCall() { return "ok"; }
}
```

`tests/detectors/samples/S12/java/negative.java`:

```java
package com.example.client;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;

public class RetryingClient {
    private static final int MAX_RETRIES = 3;
    private final CircuitBreaker breaker;

    public RetryingClient(CircuitBreaker breaker) {
        this.breaker = breaker;
    }

    public String call() {
        return breaker.executeSupplier(this::doCall);
    }

    private String doCall() { return "ok"; }
}
```

`tests/detectors/samples/S15/java/positive.java`:

```java
package com.example.client;

import java.net.http.HttpClient;

public class RecommendationClient {
    private final HttpClient client = HttpClient.newBuilder().build();

    public String getRecommendations(String userId) throws Exception {
        return client.send(null, null).body().toString();
    }
}
```

`tests/detectors/samples/S15/java/negative.java`:

```java
package com.example.client;

import io.github.resilience4j.decorators.Decorators;
import java.net.http.HttpClient;

public class RecommendationClient {
    private final HttpClient client = HttpClient.newBuilder().build();

    public String getRecommendations(String userId) {
        return Decorators.ofSupplier(() -> callUpstream(userId))
                .withFallback(t -> defaultRecommendations())
                .get();
    }

    private String callUpstream(String userId) { return "recs"; }
    private String defaultRecommendations() { return "default"; }
}
```

- [ ] **Step 2: Add `RETRY_LAYERS["java"]` in `modules.py`**

```python
    "java": [
        ("own retry loop", re.compile(
            r"\b(for|while)\s*\(.*\b(attempt|retry|retries|tries)\b", re.I)),
        ("retry annotation/wrapper", re.compile(
            r"@\s*Retryable\b|RetryTemplate\b|Failsafe\s*\.\s*with", re.I)),
        ("SDK retry config", re.compile(
            r"\bmaxAttempts\b|\bMAX_RETRIES\b|RetryConfig\b|RetryPolicy\b")),
    ],
```

(added as a third key in `RETRY_LAYERS`, alongside `"typescript"` and `"python"`)

- [ ] **Step 3: Add the S05 Java detector**

```yaml
      java:
        - id: S05-java-loop-without-limiter
          kind: file_absent
          anchor: '(?i)for\s*\([^)]*:\s*\w+\s*\)|\.\s*forEach\s*\('
          absent: '(?i)\b(ratelimit|rate_limit|limiter|throttle|bucket4j|Bucket\b|Semaphore)\b'
          require: '(?i)\.\s*(get|post|put|delete|call|send|execute)\s*\('
          confidence: low
          note: "loop makes calls with no local rate limiter or concurrency gate in this file"
```

- [ ] **Step 4: Add the S10 Java detector**

```yaml
      java:
        - id: S10-java-nested-retry
          kind: module
          handler: s10_retry_layers
          confidence: medium
          note: "more than one retry layer in the same call path, with no shared budget"
```

- [ ] **Step 5: Add the S11 Java detector**

```yaml
      java:
        - id: S11-java-grpc-no-deadline
          kind: file_absent
          anchor: '(?i)BlockingStub\b|newBlockingStub\s*\('
          absent: '(?i)\bwithDeadline(After)?\s*\('
          confidence: low
          note: "gRPC blocking stub call with no deadline propagated"
```

- [ ] **Step 6: Add the S12 Java detector**

```yaml
      java:
        - id: S12-java-no-breaker
          kind: file_absent
          anchor: '\b(MAX_RETRIES|maxAttempts|retries|retryCount)\b'
          absent: '(?i)\b(CircuitBreaker|circuit.?breaker|resilience4j)\b'
          confidence: low
          note: "retries with no circuit breaker"
```

- [ ] **Step 7: Add the S15 Java detector**

```yaml
      java:
        - id: S15-java-no-fallback
          kind: file_absent
          anchor: '\bHttpClient\b|\bRestTemplate\b|\bWebClient\b'
          absent: '(?i)\b(fallback|degrade|stale|default(Value|Response)|Decorators\s*\.\s*ofSupplier)\b'
          confidence: low
          note: "external call with no fallback branch"
```

- [ ] **Step 8: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S05 or S10 or S11 or S12 or S15" -v`
Expected: PASS, including `S10-java-negative_defines_retry_bean` staying silent.

- [ ] **Step 9: Calibration corpus pass (resilience4j/gRPC batch)**

Run against 3–5 real repositories using resilience4j and/or gRPC (e.g. the official resilience4j samples repo, a gRPC Java quickstart). Inspect every hit; add negative samples for false positives found; record repos and counts in the commit message.

- [ ] **Step 10: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py tests/detectors/samples/S05/java tests/detectors/samples/S10/java tests/detectors/samples/S11/java tests/detectors/samples/S12/java tests/detectors/samples/S15/java
git commit -m "Add resilience4j/gRPC Java detectors for S05/S10/S11/S12/S15; calibrate

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: Akka/JMS/RabbitMQ batch close-out — S06, S18

Satisfies: AC-14 (S06/S18 fire on Java prioritization and fail-fast violations, including Akka/JMS idioms).

**Files:**
- Modify: `catalog/stability.yaml` (S06, S18 `detectors:` blocks, add `java:`)
- Modify: `scripts/detectors/modules.py` — add `FUNC_JAVA` and route `s18_fail_fast` to it
- Create: `tests/detectors/samples/S06/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S18/java/{positive,negative}.java`

**Interfaces:**
- Consumes: `EXTERNAL_CALL`, `VALIDATION` (existing, already language-generic regexes — no change needed).
- Produces: `FUNC_JAVA: re.Pattern`.

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S06/java/positive.java`:

```java
package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RequestQueue {
    private final ExecutorService pool = Executors.newFixedThreadPool(8);

    public void submit(Runnable task) {
        pool.submit(task);
    }
}
```

`tests/detectors/samples/S06/java/negative.java`:

```java
package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RequestQueue {
    private final ExecutorService interactivePool = Executors.newFixedThreadPool(8);
    private final ExecutorService batchPool = Executors.newFixedThreadPool(2);

    public void submitInteractive(Runnable task) {
        interactivePool.submit(task);
    }

    public void submitBatch(Runnable task) {
        batchPool.submit(task);
    }
}
```

`tests/detectors/samples/S18/java/positive.java` (validates after the expensive call):

```java
package com.example.orders;

import java.net.http.HttpClient;

public class OrderService {
    private final HttpClient client = HttpClient.newBuilder().build();

    public String placeOrder(String payload) throws Exception {
        String response = client.send(null, null).body().toString();
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("payload required");
        }
        return response;
    }
}
```

`tests/detectors/samples/S18/java/negative.java` (validates first):

```java
package com.example.orders;

import java.net.http.HttpClient;

public class OrderService {
    private final HttpClient client = HttpClient.newBuilder().build();

    public String placeOrder(String payload) throws Exception {
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("payload required");
        }
        return client.send(null, null).body().toString();
    }
}
```

- [ ] **Step 2: Add `FUNC_JAVA` and route `s18_fail_fast` in `modules.py`**

Add near `FUNC_TS`/`FUNC_PY`:

```python
FUNC_JAVA = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:public|private|protected|static|final|synchronized|abstract)\s+"
    r"[\w<>\[\],.\s]+?\s+\w+\s*\([^)]*\)\s*(?:throws\s+[\w.,\s]+)?\s*\{")
```

Change:

```python
def s18_fail_fast(ctx) -> Result:
    is_py = _lang_key(ctx) == "python"
    func_re = FUNC_PY if is_py else FUNC_TS
```

to:

```python
def s18_fail_fast(ctx) -> Result:
    key = _lang_key(ctx)
    func_re = {"python": FUNC_PY, "java": FUNC_JAVA}.get(key, FUNC_TS)
```

- [ ] **Step 3: Add the S06 Java detector**

```yaml
      java:
        - id: S06-java-single-pool-no-priority
          kind: file_absent
          anchor: '(?i)\bExecutorService\b|\bExecutors\s*\.\s*new\w+ThreadPool\s*\('
          absent: '(?i)\b(priority|interactive|criticality|tier|urgent|foreground|batch)\b'
          confidence: low
          note: "one ExecutorService serves all callers; no priority/criticality naming"
```

- [ ] **Step 4: Add the S18 Java detector**

```yaml
      java:
        - id: S18-java-validate-after-call
          kind: module
          handler: s18_fail_fast
          confidence: low
          note: "validation appears after an expensive external call"
```

- [ ] **Step 5: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S06 or S18" -v`
Expected: PASS. Also confirm no regression on the existing TS/Python S18 samples:

Run: `uv run --with pytest --with pyyaml --with lizard pytest "tests/detectors/test_detectors.py" -k S18 -v`
Expected: PASS for `S18-typescript-*` and `S18-python-*` too — `FUNC_JAVA` is only reached when `_lang_key(ctx) == "java"`.

- [ ] **Step 6: Calibration corpus pass (Akka/JMS/RabbitMQ batch)**

Run against 3–5 real repositories using Akka, JMS, or RabbitMQ (or, if none are readily found for S06/S18 specifically since these two detectors are JDK-primitive-based rather than framework-specific, substitute any real Java service repository — these two detectors don't depend on Akka/JMS idioms directly, only the batch's ordering in the spec's phase list does). Inspect hits by hand; add negative samples for false positives; record repos and counts in the commit message.

- [ ] **Step 7: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py tests/detectors/samples/S06/java tests/detectors/samples/S18/java
git commit -m "Add S06/S18 Java detectors closing out the framework batches; calibrate

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 12: Regenerate docs, full suite, CHANGELOG, version bump

Satisfies: AC-15 (generated docs and sample report reflect the new catalog and stay in sync with CI's `--check`).

**Files:**
- Modify: `skills/stability-catalog/references/patterns.md` (generated)
- Modify: `examples/sample-report.md` (generated)
- Modify: `CHANGELOG.md`
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml` (version bump — `test_versions_agree` requires all four, including the `CHANGELOG.md` heading, to match)

- [ ] **Step 1: Run the full test suite**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/ -q`
Expected: PASS, including `tests/test_docs_in_sync.py` (may fail here — that's expected before regeneration, see Step 2) and `tests/test_guardrail.py` (Java detectors add no new code paths to `guardrail.py`, so its latency budget is unaffected).

- [ ] **Step 2: Regenerate the generated artefacts**

```bash
uv run scripts/gen_catalog_docs.py
uv run scripts/gen_sample_report.py
```

- [ ] **Step 3: Verify generation is idempotent and CI-clean**

```bash
uv run scripts/gen_catalog_docs.py --check
```

Expected: exits 0 (no stale diff after the regeneration in Step 2).

- [ ] **Step 4: Bump the plugin version and update the changelog**

Follow the existing convention (see `git log` for the prior `Bump plugin version` commit): increment the minor version in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `pyproject.toml`, and add a heading to `CHANGELOG.md` for this version describing Java language support (S01–S19 Java detectors, new patterns S27–S29, framework coverage for Spring/Hibernate/Kafka/resilience4j/gRPC/Akka/JMS/RabbitMQ).

- [ ] **Step 5: Validate the plugin still loads**

```bash
claude plugin validate . --strict
claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck
claude plugin list
```

Expected: `claude plugin list` reports thunderstruck as `enabled`, not `failed to load`.

- [ ] **Step 6: Run the full suite one final time**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add skills/stability-catalog/references/patterns.md examples/sample-report.md CHANGELOG.md .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml
git commit -m "Regenerate catalog docs and sample report for Java support; bump version

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
