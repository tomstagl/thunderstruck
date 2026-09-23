# Java Language Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `.java` as a scanned language, with detectors for every Tier A/B pattern (S01–S19) plus three Java-specific patterns (S27 event-loop blocking, S28 unbounded lock/wait acquisition, S29 N+1 query fan-out), covering both core JDK idioms and the Spring/Hibernate/Kafka/resilience4j/gRPC/Akka/JMS/RabbitMQ frameworks.

**Architecture:** Java is a leaf under the existing catalog-driven pipeline, and no stage changes shape. `catalog/stability.yaml` gains `languages.java` and a `java:` detector block per pattern. `scripts/detectors/modules.py` gains a `"java"` branch wherever a module handler dispatches on language. New samples land under `tests/detectors/samples/<ID>/java/`, and the existing test collection discovers them once `tests/detectors/test_detectors.py`'s `EXT_LANG` map knows `.java`. A new dev tool, `scripts/calibrate.py`, sweeps every tracked file of a real repository so each batch's calibration sees every hit, not only the ones in ranked hotspots.

**Tech Stack:** Python ≥ 3.11 stdlib + `pyyaml` + `lizard` (already a dependency; has first-class Java support), pytest. Scripts run via `uv run` with PEP 723 metadata. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-23-java-language-support-design.md`. Requirements and acceptance criteria AC-1…AC-16 are in GitHub issue #8 (`gh issue view 8`).

**Branch:** all work happens on `feat/java-support`, never on `main`. Each task ends in one commit (plus, where calibration forces a fix, the fix is folded into that task's commit). When a task's commit lands, tick its box in the issue's *Implementation progress* checklist (`gh issue edit 8 --body-file …`).

## Revision notes (independent review, 2026-09-23)

A first draft of this plan was reviewed against the spec, the ticket and the real detector engine. Every detector and sample in the draft was run through `run_detectors`. The draft had five sample pairs that failed as written: S05, S06, S13, S18 and S19. Several more passed only by accident. For example, the S09 `@Cacheable` suppression could never match (`\b@` never matches after whitespace), the S13 negative relied on a word that lives in a comment and comments are blanked, and the S17 negative was suppressed by the word `Caffeine` rather than by its expiry. This revision fixes all of those and re-runs the same check. Other changes:

- **Calibration is now a real gate.** `signals.py` only reports hits for the top-N files that changed inside `--since`, so the draft's calibration command could not see most hits. Calibration now uses `scripts/calibrate.py` (added in Task 1) over every tracked file. Repos are named and pinned per batch, and results go in a committed log, `docs/calibration/java.md`. A batch is not done until its log section accounts for every hit. See **Calibration protocol**.
- **Every detector is tested on its own.** The pattern-level sample test passes if *any* of a pattern's detectors fires, and the draft's OkHttp, CompletableFuture, untimed-lock, 503 and RestTemplate/WebClient detectors never fired on any sample. `tests/detectors/test_java_detectors.py` (Task 1) now requires each Java detector to fire alone on its pattern's `positive.java`, and it fails on any Java detector marked `confidence: high`.
- **Confidence discipline.** The draft had two `high` Java detectors (S03, S19) and several framework detectors at `medium`, which breaks spec §5. Framework detectors are now `low`, and JDK/core detectors are at most `medium`.
- **Negative-control fixes.** S28 no longer flags every `synchronized` and every `lock()`, which are both idiomatic and correct. It flags a monitor or lock held across a blocking call, and untimed waits (spec §2 updated). S29 now fires only on a chained getter (`order.getItems().size()`) in a file that touches persistence, so `for (o : orders) ids.add(o.getId())` no longer trips it. S08 now requires a collection-returning finder. S17 requires a cache-named map. S10 ignores `@Configuration` classes and no longer counts `maxAttempts` as a layer of its own.
- **In-scope items the draft had dropped.** Spring `@Retryable` misuse (S02 no jitter, S04 retries every exception), `@Cacheable` without `sync` (S09), `java.net.http.HttpRequest` without `.timeout()` (S01), `Executors.newFixedThreadPool` as an unbounded queue (S14), Kafka `max.poll.records` (S08), and the Akka/JMS/RabbitMQ batch. That batch had no Akka/JMS/RabbitMQ detectors at all and now has four (S01 JMS `receive()`, S07 RabbitMQ auto-ack, S13 Akka blocking on the default dispatcher, S14 RabbitMQ prefetch). The spec-table entries still deferred are listed at the end, with reasons.
- **Correctness.** S27–S29 go after S19 in `patterns:`. S20–S26 live under `tier_c:`, so "after S26" was never a valid place. S18 gains Java validation and external-call vocabularies (`throw new IllegalArgumentException` matched nothing before). The S19 comment-only-catch detector uses window 1: the TS equivalent's window 2 reaches the `}` after a one-statement body and fires on a logged catch. The S29 and S18 regexes were rewritten to avoid nested overlapping quantifiers.

**Execution amendment (Tasks 2–4 review).** The task review found four detectors, as the plan specifies them, that fire on common correct Java. Commit `18e8978` supersedes the YAML in Tasks 2–4 for those detectors (catalog is authoritative):
- The S28 lock/monitor search stops at the section end: the first `}` or `unlock()`.
- The S01 future detector requires a future-named receiver and honours `orTimeout`.
- S27 no longer matches `.block()`.
- S01 OkHttp suppresses only on `callTimeout`.

It adds five required-silent samples.

## Global Constraints

- No new third-party dependencies. Detection is regex/heuristic only, with no Java parser and no AST library (CLAUDE.md: "scripts for anything that must be reproducible", not a compiler).
- No `aliases: java: ...` entry. Java shares no syntax with TS/Python worth inheriting.
- **Confidence:** a detector keyed to a framework or library idiom starts at `low`. A detector keyed to a JDK/core-language primitive starts at `medium` at most. No detector is `high` in this pass. `test_no_java_detector_claims_high_confidence` enforces this.
- Every Tier A pattern-language pair needs both `positive.java` and `negative.java` under `tests/detectors/samples/<ID>/java/`. Any other file stem in that directory is a required-silent case, just like `negative.java`. `test_every_java_detector_fires_on_its_positive_sample` additionally requires that **every** Java detector fire alone on its pattern's `positive.java`. So when a task adds a detector to a pattern that already has samples, it appends a violating class to `positive.java` and the corrected class to `negative.java`. Appended classes are package-private top-level classes, and they use fully qualified names, because imports cannot follow a class body.
- Comments are already blanked language-generically by `_common.strip_comments` (`lang != "python"` → C-style `//`/`/* */`), so no change is needed there for Java. **A sample cannot rely on a comment to suppress a detector.**
- **Match compound identifiers** (CLAUDE.md). Write `(?i)(fallback|…)`, not `\b(fallback)\b`, so that `withFallback` matches. Never put `\b` in front of `@`.
- Module handlers must never raise. A language key is added to a handler's per-language dict (`SLEEP_RES`, `RETRY_LAYERS`) in the same task that gives a pattern its first `java:` catalog entry using that handler, never earlier.
- AC-16: existing TS/Python detectors, samples and tests do not change behaviour. Shared regexes (`VALIDATION`, `EXTERNAL_CALL`, `DECLARATION`, …) are never edited. Java gets its own variant, chosen by `_lang_key`.
- Regenerate `skills/stability-catalog/references/patterns.md` (`uv run scripts/gen_catalog_docs.py`) and `examples/sample-report.md` (`uv run scripts/gen_sample_report.py`) once, at the end. CI's `--check` mode fails the build if they are stale. Three tests in `tests/test_docs_in_sync.py` may fail on intermediate commits for this reason: `test_patterns_reference_is_regenerated`, `test_sample_report_covers_every_scanned_pattern` and `test_catalog_tiers_match_the_documented_split`. Task 12 fixes all three. They are the only failures allowed before Task 12.
- Full suite: `uv run --with pytest --with pyyaml --with lizard pytest tests/ -q`.
- Commit messages are imperative sentences in the repo's style and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Calibration protocol (used by Tasks 5, 6, 7, 8, 9, 10, 11)

Synthetic samples prove a regex matches what it was written for. Calibration checks whether it behaves on code nobody wrote for the test (spec §5). The steps are the same for every batch:

1. **Clone the batch's repos** (listed in the task) shallowly into the scratchpad, never into this repo, and record each HEAD SHA:
   ```bash
   git clone --depth 1 https://github.com/<owner>/<repo> "$SCRATCH/cal/<repo>"
   git -C "$SCRATCH/cal/<repo>" rev-parse HEAD
   ```
   If the network is unavailable, the task is **BLOCKED**. Report it and stop. Never skip calibration or mark it done.
2. **Sweep every tracked file** with only the batch's patterns:
   ```bash
   uv run scripts/calibrate.py --repo "$SCRATCH/cal/<repo>" --lang java --patterns S01,S27 > "$SCRATCH/cal/<repo>.tsv"
   ```
   (`signals.py` is not used here. It reports only the top-N recently churned files, so most hits would never be seen.)
3. **Precision tripwire.** If one detector produces more than 25 hits in one repo, that is a precision failure in itself. Tighten the detector first (adding a negative sample for the shape that was over-matching), then re-sweep. If it cannot get under 25 without losing its positive sample, remove it from the catalog and its samples, and record it as *deferred* in the log.
4. **Inspect every remaining hit by hand**: open the file:line and judge it against the pattern's `failure_if_absent`. Each hit gets a verdict:
   - `TP`: a genuine instance.
   - `FP-fixed`: the detector was tightened. Add a negative sample reproducing the shape (a new `negative_<shape>.java` in the pattern's `java/` directory).
   - `FP-accepted`: a genuine false positive that regex cannot distinguish. Allowed only at `confidence: low`, with a one-line reason. If more than half a detector's hits end up `FP-accepted`, the detector is deferred as in step 3.
5. **Re-run** the full detector suite and re-sweep after any fix. The final sweep is the one that gets recorded.
6. **Record** the batch in `docs/calibration/java.md` (create the file in the first calibration task) under a heading per batch:
   ```markdown
   ## Batch 1 — JDK/core (Tasks 5–6): S01, S27, S28, S13, S14, S02, S03, S04

   | Repo | Commit | Java files swept |
   |---|---|---|
   | jhy/jsoup | `<sha>` | 71 |

   | Detector | Hits | TP | FP-fixed | FP-accepted | Deferred |
   |---|---|---|---|---|---|
   | S01-java-httprequest-no-timeout | 3 | 3 | 0 | 0 | |

   ### Hits
   - `S01-java-httprequest-no-timeout` jsoup `src/main/java/…/HttpConnection.java:412` — TP
   - `S28-java-untimed-wait` HikariCP `…/ConcurrentBag.java:88` — FP-fixed: … → `S28/java/negative_<shape>.java`
   ```
   Every hit line from the final sweep appears exactly once under **Hits**.
7. **The gate.** The task's reviewer checks three things: the Hits count equals the final sweep's line count, no hit is missing a verdict, and every `FP-fixed` names a negative sample that exists and passes. The next task does not start until the reviewer approves. The log is committed with the task.

---

### Task 1: Java language plumbing and calibration tooling

Satisfies: AC-1 (`.java` recognized as a language, scans without crashing). Also lays down the tooling every later AC's calibration and per-detector checks rely on.

**Files:**
- Modify: `catalog/stability.yaml`: add `languages.java`
- Modify: `scripts/detectors/modules.py` (`_lang_key`)
- Modify: `tests/detectors/test_detectors.py` (`EXT_LANG`)
- Create: `scripts/calibrate.py`
- Create: `tests/test_java_plumbing.py`
- Create: `tests/detectors/test_java_detectors.py`
- Modify: `CLAUDE.md`: one line under **Commands**

**Interfaces:**
- Consumes: `_common.language_map`, `_common.detect_language`, `_common.load_catalog`, `_common.Filters`, `_common.git`, `detectors.run_detectors` (unchanged signatures).
- Produces: `_lang_key(ctx) -> str`, which now returns `"java"` for a Java context. Also `scripts/calibrate.py --repo P --lang L --patterns IDS [--include-tests]`, which prints `detector_id<TAB>file:line<TAB>snippet` sorted, one line per hit, and a per-detector count on stderr.

- [ ] **Step 1: Write the failing tests**

`tests/test_java_plumbing.py`:

```python
"""Java is a new leaf under the existing pipeline: a language mapping, a
_lang_key branch, and nothing else changes shape. This pins that the
pipeline doesn't crash on Java before any detector exists for it, and that
the calibration sweep sees every tracked file."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import _common


def _git_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, check=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    return root


def test_java_extension_maps_to_java_language(catalog):
    langmap = _common.language_map(catalog)
    assert _common.detect_language("src/Main.java", langmap) == "java"


def test_java_file_scans_without_crashing(tmp_path, plugin_root):
    # No package statement and CRLF line endings: Review Focus #1.
    repo = _git_repo(tmp_path / "repo", {"src/Main.java": (
        "public class Main {\r\n"
        "    public static void main(String[] args) {\r\n"
        "        System.out.println(\"hi\");\r\n"
        "    }\r\n"
        "}\r\n")})
    result = subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "signals.py"),
         "--repo", str(repo), "--top", "5"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())
    assert data["schema"] == "thunderstruck.hotspots/v1"
    ranked = {h["file"]: h["language"] for h in data["hotspots"]}
    assert ranked.get("src/Main.java") == "java"


def test_calibrate_sweeps_every_tracked_file(tmp_path, plugin_root):
    # calibrate.py must see hits outside any hotspot ranking, and must skip
    # test directories by default exactly as signals.py does.
    body = "class A {\n    Object q = new java.util.concurrent.LinkedBlockingQueue<>();\n}\n"
    repo = _git_repo(tmp_path / "cal", {
        "src/main/java/A.java": body,
        "src/test/java/ATest.java": body,
    })
    result = subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "calibrate.py"),
         "--repo", str(repo), "--lang", "java", "--patterns", "S14"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    # No Java S14 detector exists yet in Task 1; the sweep must still run
    # cleanly and print nothing rather than fail.
    assert "ATest.java" not in result.stdout
```

`tests/detectors/test_java_detectors.py`:

```python
"""Java detectors land in batches, and one positive sample per pattern can
hide a detector that never fires: the pattern-level sample test passes as
long as *any* of a pattern's detectors hits. This pins every Java detector
individually, and pins the confidence discipline from the spec (§5): no Java
detector claims `high` until calibration has earned it."""

from __future__ import annotations

from pathlib import Path

from detectors import run_detectors

SAMPLES = Path(__file__).parent / "samples"


def _java_detectors(catalog):
    for pattern in catalog["patterns"]:
        for det in (pattern.get("detectors") or {}).get("java", []) or []:
            yield pattern, det


def test_every_java_detector_fires_on_its_positive_sample(catalog):
    silent = []
    for pattern, det in _java_detectors(catalog):
        sample = SAMPLES / pattern["id"] / "java" / "positive.java"
        if not sample.exists():
            silent.append(f"{det['id']} (no {sample})")
            continue
        solo = {**catalog, "patterns": [{**pattern, "detectors": {"java": [det]}}]}
        hits = run_detectors(solo, f"src/{sample.name}",
                             sample.read_text(encoding="utf-8"), "java")
        if not any(h.detector_id == det["id"] for h in hits):
            silent.append(det["id"])
    assert not silent, (
        "Java detectors that never fire on their pattern's positive sample: "
        + ", ".join(silent))


def test_no_java_detector_claims_high_confidence(catalog):
    high = [det["id"] for _, det in _java_detectors(catalog)
            if det.get("confidence") == "high"]
    assert not high, f"Java detectors at confidence: high before calibration earned it: {high}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_java_plumbing.py tests/detectors/test_java_detectors.py -v`
Expected: `test_java_extension_maps_to_java_language` FAILS (`.java` not in the catalog). `test_java_file_scans_without_crashing` FAILS (`signals.py` exits non-zero with "no files in a supported language changed"). `test_calibrate_sweeps_every_tracked_file` FAILS (no such script). The two `test_java_detectors.py` tests pass vacuously, since no Java detector exists yet.

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

`s07_checkpoint` and `s18_fail_fast` test `== "python"`, so for Java they keep using the brace-language path (`LOOP_TS`, `_ts_block_end`). `s02_backoff` and `s10_retry_layers` index a per-language dict. No Java catalog entry reaches them until Tasks 6 and 10, which add the `"java"` keys in the same commit.

- [ ] **Step 5: Add `.java` to the sample-discovery test harness**

In `tests/detectors/test_detectors.py`, change:

```python
EXT_LANG = {".ts": "typescript", ".py": "python"}
```

to:

```python
EXT_LANG = {".ts": "typescript", ".py": "python", ".java": "java"}
```

- [ ] **Step 6: Write `scripts/calibrate.py`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Detector calibration sweep.

Runs the selected patterns' detectors over *every* tracked file of a
repository in one language, not just the ranked hotspots signals.py keeps,
so a detector batch can be judged against code nobody wrote for the test.

    uv run scripts/calibrate.py --repo /path/to/repo --lang java --patterns S01,S27

stdout: one `detector_id<TAB>file:line<TAB>snippet` line per hit, sorted.
stderr: hit count per detector. Test directories are skipped unless
--include-tests, matching signals.py's defaults.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
from detectors import run_detectors  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--lang", required=True)
    ap.add_argument("--patterns", required=True, help="comma-separated pattern ids")
    ap.add_argument("--include-tests", action="store_true")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    catalog = c.load_catalog(PLUGIN_ROOT)
    langmap = c.language_map(catalog)
    filters = c.Filters(include_tests=args.include_tests)
    wanted = [p.strip() for p in args.patterns.split(",") if p.strip()]

    rows: list[tuple[str, str, int, str]] = []
    for rel in sorted(p for p in c.git(repo, "ls-files").split("\n") if p):
        if c.detect_language(rel, langmap) != args.lang or filters.excludes_path(rel):
            continue
        text = c.read_text(repo / rel)
        if text is None:
            continue
        for h in run_detectors(catalog, rel, text, args.lang, pattern_ids=wanted):
            rows.append((h.detector_id, h.file, h.line, h.snippet))

    rows.sort()
    for det, rel, line, snippet in rows:
        print(f"{det}\t{rel}:{line}\t{snippet}")
    for det, n in sorted(Counter(r[0] for r in rows).items()):
        print(f"{n:5d}  {det}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Document the tool**

In `CLAUDE.md`, under **Commands**, after the `report.py` line in the "Run the deterministic pipeline by hand" block, add:

```bash
uv run scripts/calibrate.py --repo /path/to/repo --lang java --patterns S01,S27   # every hit, every tracked file
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_java_plumbing.py tests/detectors -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py scripts/calibrate.py tests/detectors/test_detectors.py tests/detectors/test_java_detectors.py tests/test_java_plumbing.py CLAUDE.md
git commit -m "Add .java as a recognized language and a calibration sweep

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: S01 timeouts — JDK/core HTTP, JDBC and futures

Satisfies: AC-2 (S01 fires on Java `HttpClient`/OkHttp/JDBC/`CompletableFuture` with no timeout, stays silent when one is set).

**Files:**
- Modify: `catalog/stability.yaml` (S01 `detectors:`, add `java:`)
- Create: `tests/detectors/samples/S01/java/positive.java`
- Create: `tests/detectors/samples/S01/java/negative.java`

HikariCP is deliberately not an anchor. Its `connectionTimeout` defaults to 30 s, so a `HikariConfig` with no explicit timeout still has one, and flagging it would be a false positive on correct code. The negative sample keeps a configured Hikari pool to show it stays silent.

- [ ] **Step 1: Write the samples first (they double as the detector's spec)**

`tests/detectors/samples/S01/java/positive.java`:

```java
package com.example.client;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.concurrent.CompletableFuture;
import okhttp3.OkHttpClient;

public class UserClient {
    private final HttpClient client = HttpClient.newBuilder().build();
    private final OkHttpClient okHttp = new OkHttpClient.Builder().build();

    public String fetchUser(String userId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/users/" + userId))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public Connection openConnection() throws Exception {
        return DriverManager.getConnection("jdbc:postgresql://db/app");
    }

    public String fetchAsync(HttpRequest request) throws Exception {
        CompletableFuture<HttpResponse<String>> future =
                client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
        return future.get().body();
    }
}
```

`tests/detectors/samples/S01/java/negative.java`:

```java
package com.example.client;

import com.zaxxer.hikari.HikariConfig;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.DriverManager;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import okhttp3.OkHttpClient;

public class UserClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    private final OkHttpClient okHttp = new OkHttpClient.Builder()
            .callTimeout(Duration.ofSeconds(10))
            .build();

    public String fetchUser(String userId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/users/" + userId))
                .timeout(Duration.ofSeconds(5))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public Connection openConnection() throws Exception {
        DriverManager.setLoginTimeout(3);
        return DriverManager.getConnection("jdbc:postgresql://db/app");
    }

    public HikariConfig poolConfig() {
        HikariConfig config = new HikariConfig();
        config.setConnectionTimeout(3000);
        return config;
    }

    public String fetchAsync(CompletableFuture<HttpResponse<String>> future) throws Exception {
        return future.get(5, TimeUnit.SECONDS).body();
    }
}
```

- [ ] **Step 2: Confirm the new cases are collected and currently fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S01-java" -q`
Expected: `S01-java-positive` FAILS (no `java:` detectors under S01 yet). `S01-java-negative` passes vacuously.

- [ ] **Step 3: Add the S01 Java detectors**

In `catalog/stability.yaml`, under pattern `S01`'s `detectors:`, add a `java:` sibling after `python:`:

```yaml
      java:
        - id: S01-java-httpclient-no-connect-timeout
          kind: regex
          pattern: '\bHttpClient\s*\.\s*(newBuilder\s*\(\s*\)|newHttpClient\s*\(\s*\))'
          absent_within: '\bconnectTimeout\s*\('
          window: 6
          confidence: medium
          note: "java.net.http.HttpClient built with no connectTimeout()"
        - id: S01-java-httprequest-no-timeout
          kind: regex
          pattern: '\bHttpRequest\s*\.\s*newBuilder\s*\('
          absent_within: '\.\s*timeout\s*\('
          window: 8
          confidence: medium
          note: "HttpRequest with no .timeout() — HttpClient has no default request timeout, so send() can wait forever"
        - id: S01-java-okhttp-no-timeout
          kind: regex
          pattern: '\bOkHttpClient\s*\.\s*Builder\s*\(\s*\)|new\s+OkHttpClient\s*\(\s*\)'
          absent_within: '\b(connectTimeout|readTimeout|writeTimeout|callTimeout)\s*\('
          window: 8
          confidence: low
          note: "OkHttpClient with no timeout configured — per-read defaults only, no bound on the whole call"
        - id: S01-java-jdbc-no-login-timeout
          kind: regex
          pattern: '\bDriverManager\s*\.\s*getConnection\s*\('
          absent_within: '\bsetLoginTimeout\s*\(|[?&;](connectTimeout|loginTimeout|socketTimeout)='
          window: 4
          window_before: 6
          confidence: low
          note: "DriverManager.getConnection with no login timeout — some drivers wait forever for an unreachable host"
        - id: S01-java-future-get-no-timeout
          kind: regex
          pattern: '\.\s*(get|join)\s*\(\s*\)'
          present_within: '\b(CompletableFuture|Future)\b'
          window: 2
          window_before: 6
          confidence: low
          note: "Future.get()/join() with no timeout — blocks forever if the future never completes"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S01-java or java_detector" -v`
Expected: PASS for `S01-java-positive`, `S01-java-negative`, and `test_every_java_detector_fires_on_its_positive_sample`. All five detectors must fire on their own.

- [ ] **Step 5: Run the full detector suite to confirm no regression**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -q`
Expected: all pass, including `test_every_catalog_regex_compiles` and `test_detector_ids_are_unique`.

- [ ] **Step 6: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S01/java
git commit -m "Add S01 Java detectors for HttpClient, OkHttp, JDBC and futures

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: S27 (new pattern) — no blocking calls on non-blocking/event-loop threads

Satisfies: AC-3 (S27 in the catalog with the full schema), AC-4 (fires in a Reactor/WebFlux/Netty/Akka-Streams context, silent in a plain request handler).

**Files:**
- Modify: `catalog/stability.yaml`: insert new pattern `S27` **after `S19`'s block and before the `# ---- Tier C ----` comment**. S20–S26 live in the separate `tier_c:` list; S27 goes in `patterns:` because it is actively detected.
- Create: `tests/detectors/samples/S27/java/positive.java`
- Create: `tests/detectors/samples/S27/java/negative.java` (the same blocking call, offloaded to `boundedElastic`)
- Create: `tests/detectors/samples/S27/java/negative_plain_controller.java` (Review Focus #5)

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S27/java/positive.java`:

```java
package com.example.pipeline;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import reactor.core.publisher.Mono;

public class OrderHandler {
    private final HttpClient httpClient = HttpClient.newHttpClient();

    public Mono<String> loadOrder(String orderId, HttpRequest request) {
        return Mono.fromSupplier(() -> {
            try {
                Thread.sleep(50);
                return httpClient.send(request, HttpResponse.BodyHandlers.ofString()).body();
            } catch (Exception e) {
                throw new IllegalStateException(e);
            }
        });
    }
}
```

`tests/detectors/samples/S27/java/negative.java`:

```java
package com.example.pipeline;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class OrderHandler {
    private final HttpClient httpClient = HttpClient.newHttpClient();

    public Mono<String> loadOrder(String orderId, HttpRequest request) {
        return Mono.fromCallable(() -> {
                    Thread.sleep(50);
                    return httpClient.send(request, HttpResponse.BodyHandlers.ofString()).body();
                })
                .subscribeOn(Schedulers.boundedElastic());
    }
}
```

`tests/detectors/samples/S27/java/negative_plain_controller.java` (Review Focus #5: blocking is expected on a plain MVC thread):

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

Directly after S19's last detector and before `# ---------------------------------------------------------------- Tier C ----`:

```yaml
  # ------------------------------------------- Tier A (JVM-specific) --
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
        - id: S27-java-blocking-in-reactive
          kind: regex
          pattern: '\bThread\s*\.\s*sleep\s*\(|\bDriverManager\s*\.\s*getConnection\s*\(|\.\s*block(First|Last|Optional)?\s*\(|\.\s*execute(Query|Update)\s*\(|\w*[Hh]ttp[Cc]lient\s*\.\s*send\s*\(|\w*(restTemplate|RestTemplate|jdbcTemplate|JdbcTemplate)\s*\.\s*\w+\s*\('
          present_within: '\b(Mono|Flux)\b|reactor\.core|io\.netty|ChannelHandlerContext|akka\.stream'
          absent_within: 'Schedulers\s*\.\s*(boundedElastic|fromExecutor\w*|newBoundedElastic)|\bsubscribeOn\s*\(|\bpublishOn\s*\('
          window: 12
          window_before: 12
          confidence: low
          note: "blocking call inside a Reactor/WebFlux/Netty/Akka-Streams context with no scheduler offload — starves the event loop"
```

The context test is window-local (±12 lines), not file-wide. A `regex` detector cannot see the whole file, and a file-level `file_absent` could not point at the blocking line. Calibration (Task 5) measures what this misses.

- [ ] **Step 3: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S27 or java_detector" -v`
Expected: `S27-java-positive` fires. `S27-java-negative` and `S27-java-negative_plain_controller` stay silent.

- [ ] **Step 4: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S27
git commit -m "Add S27: no blocking calls on non-blocking/event-loop threads

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: S28 (new pattern) — bounded, timed lock/wait acquisition

Satisfies: AC-5 (S28 exists, fires on `synchronized` and untimed `Lock`/`Condition` usage, silent on timed variants).

A `synchronized` block or `lock()` around in-memory work is idiomatic, correct Java. Flagging every one would bury the real hits (CLAUDE.md, negative-control discipline). The failure S28 names is a *stalled holder*: a monitor or lock held across a blocking call, or a wait with no bound. The detectors fire on exactly that (spec §2).

**Files:**
- Modify: `catalog/stability.yaml`: insert `S28` after `S27`
- Create: `tests/detectors/samples/S28/java/positive.java`
- Create: `tests/detectors/samples/S28/java/negative.java`
- Create: `tests/detectors/samples/S28/java/negative_in_memory_monitor.java`

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S28/java/positive.java`:

```java
package com.example.inventory;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class StockLedger {
    private final HttpClient http = HttpClient.newHttpClient();
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition restocked = lock.newCondition();

    public synchronized void reserve(HttpRequest request) throws Exception {
        http.send(request, HttpResponse.BodyHandlers.ofString());
    }

    public void release(HttpRequest request) throws Exception {
        lock.lock();
        try {
            http.send(request, HttpResponse.BodyHandlers.ofString());
        } finally {
            lock.unlock();
        }
    }

    public void awaitStock() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            restocked.await();
        } finally {
            lock.unlock();
        }
    }
}
```

`tests/detectors/samples/S28/java/negative.java`:

```java
package com.example.inventory;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class StockLedger {
    private final HttpClient http = HttpClient.newHttpClient();
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition restocked = lock.newCondition();

    public void release(HttpRequest request) throws Exception {
        if (lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            try {
                http.send(request, HttpResponse.BodyHandlers.ofString());
            } finally {
                lock.unlock();
            }
        }
    }

    public boolean awaitStock() throws InterruptedException {
        if (!lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            return false;
        }
        try {
            return restocked.await(500, TimeUnit.MILLISECONDS);
        } finally {
            lock.unlock();
        }
    }
}
```

`tests/detectors/samples/S28/java/negative_in_memory_monitor.java` (short in-memory critical sections are correct Java):

```java
package com.example.inventory;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.locks.ReentrantLock;

public class Counter {
    private final Map<String, Integer> counts = new HashMap<>();
    private final ReentrantLock lock = new ReentrantLock();

    public synchronized void increment(String key) {
        counts.merge(key, 1, Integer::sum);
    }

    public int read(String key) {
        lock.lock();
        try {
            return counts.getOrDefault(key, 0);
        } finally {
            lock.unlock();
        }
    }
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
      A lock held across a slow call, or a wait with no bound, lets one
      stalled holder block every other thread indefinitely — a convoy that
      compounds under load instead of shedding it.
    references:
      - "Nygard, Release It! (2nd ed.), ch. 4 — Blocked Threads"
      - "java.util.concurrent.locks.Lock javadoc — tryLock(long, TimeUnit)"
    detectors:
      java:
        - id: S28-java-monitor-held-across-io
          kind: regex
          pattern: '\bsynchronized\s*\(|\bsynchronized\s+[\w<]'
          present_within: '\bThread\s*\.\s*sleep\s*\(|\.\s*(send|exchange|executeQuery|executeUpdate|getForObject|getForEntity|postForObject|postForEntity|getConnection|block|read|write)\s*\(|\.\s*(get|join)\s*\(\s*\)'
          window: 15
          confidence: low
          note: "synchronized section makes a blocking call — a stalled call holds the monitor and every other thread queues behind it"
        - id: S28-java-untimed-lock-across-io
          kind: regex
          pattern: '\.\s*(lock|lockInterruptibly)\s*\(\s*\)'
          present_within: '\bThread\s*\.\s*sleep\s*\(|\.\s*(send|exchange|executeQuery|executeUpdate|getForObject|getForEntity|postForObject|postForEntity|getConnection|block|read|write)\s*\(|\.\s*(get|join)\s*\(\s*\)'
          window: 15
          confidence: low
          note: "Lock.lock() with no timed tryLock, held across a blocking call"
        - id: S28-java-untimed-wait
          kind: regex
          pattern: '(\.\s*|^\s*)(await|wait)\s*\(\s*\)'
          confidence: low
          note: "Condition.await()/Object.wait() with no timeout — waits forever if the signal never comes"
```

- [ ] **Step 3: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S28 or java_detector" -v`
Expected: PASS. All three detectors fire alone on `positive.java`. Both negatives stay silent.

- [ ] **Step 4: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S28
git commit -m "Add S28: bounded, timed lock/wait acquisition

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: S13/S14 — bulkheads and bounded queues; calibrate the JDK/core batch

Satisfies: AC-6 (S13/S14 fire on a shared executor and an unbounded queue, silent on correct usage) and AC-7 (JDK/core batch calibrated before the Spring/Hibernate batch starts; the S02–S04 half is calibrated in Task 6).

**Files:**
- Modify: `catalog/stability.yaml` (S13, S14 `detectors:` blocks, add `java:`)
- Create: `tests/detectors/samples/S13/java/positive.java`, `negative.java`
- Create: `tests/detectors/samples/S14/java/positive.java`, `negative.java`
- Create: `docs/calibration/java.md`

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

`tests/detectors/samples/S13/java/negative.java` (the isolation is in the code, not in a comment; comments are blanked before matching):

```java
package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class WorkerRegistry {
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

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class UnboundedPool {
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(
            4, 4, 60, TimeUnit.SECONDS, new LinkedBlockingQueue<>());
    private final ExecutorService fixed = Executors.newFixedThreadPool(4);
}
```

`tests/detectors/samples/S14/java/negative.java`:

```java
package com.example.workers;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedPool {
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(
            4, 4, 60, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(200),
            new ThreadPoolExecutor.CallerRunsPolicy());
    private final LinkedBlockingQueue<Runnable> inbox = new LinkedBlockingQueue<>(1000);
}
```

- [ ] **Step 2: Add the S13 Java detector** (sibling of S13's `typescript:`/`python:` entries)

```yaml
      java:
        - id: S13-java-shared-executor
          kind: file_absent
          anchor: '\bExecutors\s*\.\s*new\w*\s*\(|new\s+ThreadPoolExecutor\s*\('
          require: '(?s)\.\s*(submit|execute|invokeAll|supplyAsync|runAsync)\s*\(.*\.\s*(submit|execute|invokeAll|supplyAsync|runAsync)\s*\('
          absent: '(?i)(bulkhead|dedicated|isolat|partition)|(?s:(Executors\s*\.\s*new\w*|new\s+ThreadPoolExecutor)\s*\(.*(Executors\s*\.\s*new\w*|new\s+ThreadPoolExecutor)\s*\()'
          confidence: low
          note: "one executor serves several submission sites with no second pool — every workload competes for the same threads"
```

`require` limits the detector to files that submit work from more than one place. `absent` treats a file that builds two or more pools as partitioned.

- [ ] **Step 3: Add the S14 Java detectors** (sibling of S14's existing entries)

```yaml
      java:
        - id: S14-java-unbounded-blocking-queue
          kind: regex
          pattern: 'new\s+(LinkedBlockingQueue|LinkedBlockingDeque)\s*(<[^>]*>)?\s*\(\s*\)'
          confidence: medium
          note: "LinkedBlockingQueue() with no capacity — unbounded by default, absorbs overload instead of shedding it"
        - id: S14-java-executors-unbounded-queue
          kind: regex
          pattern: '\bExecutors\s*\.\s*(newFixedThreadPool|newSingleThreadExecutor)\s*\('
          confidence: medium
          note: "Executors.newFixedThreadPool/newSingleThreadExecutor queue on an unbounded LinkedBlockingQueue"
```

- [ ] **Step 4: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S13 or S14 or java_detector" -v`
Expected: PASS.

- [ ] **Step 5: Calibrate the JDK/core batch (S01, S27, S28, S13, S14)**

Follow **Calibration protocol** with `--patterns S01,S27,S28,S13,S14` against:

| Repo | Why |
|---|---|
| `jhy/jsoup` | plain-JDK HTTP client code |
| `brettwooldridge/HikariCP` | JDBC, locks, executors, hand-written concurrency |
| `apache/commons-pool` | locks, waits, executors |
| `spring-petclinic/spring-petclinic-reactive` | Reactor/WebFlux: S27's true-positive surface |
| `spring-projects/spring-petclinic` | plain Spring MVC: S27 must stay silent here |

Create `docs/calibration/java.md` with a one-paragraph preamble (what calibration is, a link to spec §5) and the **Batch 1 — JDK/core** section. The gate in protocol step 7 applies.

- [ ] **Step 6: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples docs/calibration/java.md
git commit -m "Add S13/S14 Java detectors; calibrate the JDK/core batch

Calibrated against <repos@shas>; <n> hits inspected, see docs/calibration/java.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Fill the second paragraph from the log. `tests/detectors/samples` is staged whole because calibration may add negatives to S01/S27/S28.)

---

### Task 6: S02/S03/S04 — backoff, honouring pushback, transient-only retry

Satisfies: AC-8 (constant unjittered retry sleep, 429/503 without `Retry-After`, catch-all retry; silent on the correct forms). Also covers the spec §3 `@Retryable` rows for S02/S04 and closes the JDK/core batch with its calibration.

**Files:**
- Modify: `catalog/stability.yaml` (S02, S03, S04 `detectors:` blocks, add `java:`)
- Modify: `scripts/detectors/modules.py`: add `SLEEP_RES["java"]`
- Create: `tests/detectors/samples/S02/java/{positive,negative,negative_multiline_annotation}.java`
- Create: `tests/detectors/samples/S03/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S04/java/{positive,negative}.java`
- Modify: `docs/calibration/java.md`

**Interfaces:**
- Consumes: `_lang_key` (Task 1), `s02_backoff` (existing, unmodified; it already indexes `SLEEP_RES[_lang_key(ctx)]`).
- Produces: `SLEEP_RES["java"]`.

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S02/java/positive.java` (a constant, unjittered retry wait, and a `@Retryable` with Spring Retry's default fixed 1 s backoff):

```java
package com.example.client;

import org.springframework.retry.annotation.Retryable;

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

    @Retryable(maxAttempts = 3)
    public String callAnnotated() {
        return doCall();
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

`tests/detectors/samples/S02/java/negative_multiline_annotation.java` (Review Focus #2: the jitter flag sits three lines below the annotation):

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

`tests/detectors/samples/S03/java/positive.java` (429 and 503 handled, `Retry-After` never read):

```java
package com.example.client;

import java.net.http.HttpResponse;

public class RetryingClient {
    public void handle(HttpResponse<String> response) {
        if (response.statusCode() == 429 || response.statusCode() == 503) {
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
        if (response.statusCode() == 429 || response.statusCode() == 503) {
            response.headers().firstValue("Retry-After").ifPresent(this::retryAfter);
        }
    }

    private void retryAfter(String value) { }
}
```

`tests/detectors/samples/S04/java/positive.java` (catches everything and retries everything, by hand and by annotation):

```java
package com.example.client;

import org.springframework.retry.annotation.Retryable;

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

    @Retryable(maxAttempts = 3)
    public String callAnnotated() {
        return doCall();
    }

    private String doCall() { return "ok"; }
}
```

`tests/detectors/samples/S04/java/negative.java` (discriminates transient from permanent):

```java
package com.example.client;

import java.io.IOException;
import org.springframework.retry.annotation.Retryable;

public class RetryingClient {
    public String call() throws IOException {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return doCall();
            } catch (IOException e) {
                if (!isTransient(e)) {
                    throw e;
                }
            }
        }
        throw new IllegalStateException("exhausted retries");
    }

    @Retryable(retryFor = IOException.class, maxAttempts = 3)
    public String callAnnotated() throws IOException {
        return doCall();
    }

    private boolean isTransient(IOException e) { return true; }
    private String doCall() throws IOException { return "ok"; }
}
```

- [ ] **Step 2: Add `SLEEP_RES["java"]` in `modules.py`**

Add a third key to the existing `SLEEP_RES` dict, after `"python"`:

```python
    "java": [
        # Thread.sleep(ms), TimeUnit.SECONDS.sleep(n), an injected unit.sleep(n)
        re.compile(r"\b\w+\s*\.\s*sleep\s*\(\s*(?P<arg>[^),]*)"),
    ],
```

- [ ] **Step 3: Add the S02 Java detectors**

```yaml
      java:
        - id: S02-java-backoff
          kind: module
          handler: s02_backoff
          confidence: medium
          note: "retry backoff missing a cap, jitter, or growth"
        - id: S02-java-retryable-no-jitter
          kind: regex
          pattern: '@\s*Retryable\b'
          absent_within: 'random\s*=\s*true|RandomBackOffPolicy|ExponentialRandomBackOffPolicy'
          window: 6
          confidence: low
          note: "@Retryable with no randomised backoff — Spring Retry defaults to a fixed 1s wait, so every client retries in lockstep"
```

- [ ] **Step 4: Add the S03 Java detectors**

```yaml
      java:
        - id: S03-java-429-ignores-retry-after
          kind: file_absent
          anchor: '\b429\b|TOO_MANY_REQUESTS'
          absent: '[Rr]etry-?[Aa]fter|RETRY_AFTER'
          require: '(?i)\b(retry|retries|retrying|attempt|attempts|backoff|sleep|delay)\b|\w+[Rr]etry\w*\s*\('
          confidence: medium
          note: "file handles 429 but never reads Retry-After"
        - id: S03-java-503-ignores-retry-after
          kind: file_absent
          anchor: '\b503\b|SERVICE_UNAVAILABLE|HTTP_UNAVAILABLE'
          absent: '[Rr]etry-?[Aa]fter|RETRY_AFTER'
          require: '(?i)\b(retry|retries|retrying|attempt|attempts|backoff|sleep|delay)\b|\w+[Rr]etry\w*\s*\('
          confidence: low
          note: "file handles 503 but never reads Retry-After"
```

- [ ] **Step 5: Add the S04 Java detectors**

```yaml
      java:
        - id: S04-java-catch-all-retry
          kind: regex
          pattern: 'catch\s*\(\s*(final\s+)?(Exception|Throwable|RuntimeException)\s+\w+\s*\)'
          present_within: '\b(continue|retry|retries|attempt)\b|\w*[Rr]etry\w*\s*\('
          window: 6
          confidence: medium
          note: "catch (Exception e) followed by a retry — retries permanent errors too"
        - id: S04-java-retryable-all-exceptions
          kind: regex
          pattern: '@\s*Retryable\b'
          absent_within: '\b(retryFor|include|value|noRetryFor|exclude|exceptionExpression)\s*=|@\s*Retryable\s*\(\s*\{?\s*[\w.]+\.class'
          window: 6
          confidence: low
          note: "@Retryable with no exception filter — retries every exception, permanent ones included"
```

- [ ] **Step 6: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S02 or S03 or S04 or java_detector" -v`
Expected: PASS, including `S02-java-negative_multiline_annotation` (Review Focus #2: `random = true` sits within the 6-line window of the annotation).

- [ ] **Step 7: Calibrate (JDK/core batch, part 2: S02, S03, S04)**

Follow **Calibration protocol** with `--patterns S02,S03,S04` against Task 5's five repos plus `spring-projects/spring-petclinic` (already in that list) and `spring-petclinic/spring-petclinic-microservices`, which carries `@Retryable` usage. Append the results to the **Batch 1** section of `docs/calibration/java.md`. The gate applies. The Spring/Hibernate batch (Task 7) does not start until both Batch 1 halves are approved.

- [ ] **Step 8: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py tests/detectors/samples docs/calibration/java.md
git commit -m "Add S02/S03/S04 Java detectors for retry loops and @Retryable

Calibrated against <repos@shas>; <n> hits inspected, see docs/calibration/java.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Spring/Hibernate batch, part 1 — S01 Spring clients, S09 caching, S16 jitter, S17 steady state

Satisfies: AC-9 (RestTemplate/WebClient timeouts, `@Cacheable`/`ConcurrentHashMap` cache-aside, `@Scheduled` without jitter, unbounded in-memory cache).

**Files:**
- Modify: `catalog/stability.yaml` (S01 add two `java:` entries; S09, S16, S17 add `java:` blocks)
- Modify: `tests/detectors/samples/S01/java/positive.java`, `negative.java` (append)
- Create: `tests/detectors/samples/S09/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S16/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S17/java/{positive,negative}.java`
- Modify: `docs/calibration/java.md`

- [ ] **Step 1: Write the samples**

Append to `tests/detectors/samples/S01/java/positive.java`:

```java

class SpringClients {
    private final org.springframework.web.client.RestTemplate rest =
            new org.springframework.web.client.RestTemplate();
    private final org.springframework.web.reactive.function.client.WebClient web =
            org.springframework.web.reactive.function.client.WebClient.create("https://api.example.com");
}
```

Append to `tests/detectors/samples/S01/java/negative.java`:

```java

class SpringClients {
    private final org.springframework.web.client.RestTemplate rest = restTemplate();
    private final org.springframework.web.reactive.function.client.WebClient web =
            org.springframework.web.reactive.function.client.WebClient.builder()
                    .clientConnector(new org.springframework.http.client.reactive.ReactorClientHttpConnector(
                            reactor.netty.http.client.HttpClient.create()
                                    .responseTimeout(java.time.Duration.ofSeconds(5))))
                    .build();

    private static org.springframework.web.client.RestTemplate restTemplate() {
        org.springframework.http.client.SimpleClientHttpRequestFactory factory =
                new org.springframework.http.client.SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2000);
        factory.setReadTimeout(5000);
        return new org.springframework.web.client.RestTemplate(factory);
    }
}
```

`tests/detectors/samples/S09/java/positive.java`:

```java
package com.example.catalog;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.cache.annotation.Cacheable;

public class ProductLookup {
    private final Map<String, String> productCache = new ConcurrentHashMap<>();

    public String get(String sku) {
        if (productCache.containsKey(sku)) {
            return productCache.get(sku);
        }
        String value = fetchFromDb(sku);
        productCache.put(sku, value);
        return value;
    }

    @Cacheable("prices")
    public String price(String sku) {
        return fetchFromDb(sku);
    }

    private String fetchFromDb(String sku) { return "product-" + sku; }
}
```

`tests/detectors/samples/S09/java/negative.java`:

```java
package com.example.catalog;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.cache.annotation.Cacheable;

public class ProductLookup {
    private final Map<String, String> productCache = new ConcurrentHashMap<>();

    public String get(String sku) {
        return productCache.computeIfAbsent(sku, this::fetchFromDb);
    }

    @Cacheable(value = "prices", sync = true)
    public String price(String sku) {
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

`tests/detectors/samples/S16/java/negative.java` (the same fixed rate, with a random initial offset per instance):

```java
package com.example.jobs;

import org.springframework.scheduling.annotation.Scheduled;

public class SyncJob {
    @Scheduled(fixedRateString = "PT1H",
               initialDelayString = "#{T(java.util.concurrent.ThreadLocalRandom).current().nextInt(60000)}")
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

`tests/detectors/samples/S17/java/negative_registry_map.java` (a `ConcurrentHashMap` that is not a cache is not S17's business):

```java
package com.example.registry;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class HandlerRegistry {
    private final Map<String, Runnable> handlers = new ConcurrentHashMap<>();

    public void register(String name, Runnable handler) {
        handlers.put(name, handler);
    }
}
```

- [ ] **Step 2: Add the S01 Spring client detectors** (append to S01's `java:` list from Task 2)

```yaml
        - id: S01-java-resttemplate-no-timeout
          kind: regex
          pattern: 'new\s+(\w+\.)*RestTemplate\s*\(\s*\)|new\s+(\w+\.)*SimpleClientHttpRequestFactory\s*\(\s*\)'
          absent_within: '\b(setConnectTimeout|setReadTimeout|setConnectionRequestTimeout|connectTimeout|readTimeout)\s*\('
          window: 8
          confidence: low
          note: "RestTemplate with no connect/read timeout — its default request factory waits forever"
        - id: S01-java-webclient-no-timeout
          kind: regex
          pattern: '\bWebClient\s*\.\s*(builder|create)\s*\('
          absent_within: '\bresponseTimeout\s*\(|\.\s*timeout\s*\(|CONNECT_TIMEOUT_MILLIS|ReadTimeoutHandler'
          window: 10
          confidence: low
          note: "WebClient with no responseTimeout() or per-call timeout()"
```

- [ ] **Step 3: Add the S09 Java detectors**

```yaml
      java:
        - id: S09-java-cache-aside-no-singleflight
          kind: file_absent
          anchor: '(?i)cache\w*\s*\.\s*(get|getIfPresent|containsKey)\s*\('
          absent: '(?i)(single.?flight|coalesc|dedup|computeIfAbsent|LoadingCache|cache\w*\s*\.\s*get\s*\([^,()]+,)'
          confidence: low
          note: "cache-aside read with no in-flight deduplication (no computeIfAbsent, LoadingCache or loader-form get)"
        - id: S09-java-cacheable-no-sync
          kind: regex
          pattern: '@\s*Cacheable\b'
          absent_within: '\bsync\s*=\s*true'
          window: 3
          confidence: low
          note: "@Cacheable without sync = true — concurrent misses all call through to the source"
```

- [ ] **Step 4: Add the S16 Java detector**

```yaml
      java:
        - id: S16-java-scheduled-no-jitter
          kind: regex
          pattern: '@\s*Scheduled\s*\('
          present_within: '\bcron\s*=|\bfixedRate(String)?\s*='
          absent_within: '(?i)(jitter|random|splay|stagger)'
          window: 3
          confidence: low
          note: "@Scheduled cron/fixedRate with no jitter — every instance fires in lockstep"
```

- [ ] **Step 5: Add the S17 Java detector**

```yaml
      java:
        - id: S17-java-unbounded-cache
          kind: file_absent
          anchor: '(?i)(cache|memo)\w*\s*=\s*new\s+(Concurrent)?HashMap\b|cache\w*\s*\.\s*(put|putIfAbsent)\s*\(|Caffeine\s*\.\s*newBuilder\s*\('
          absent: '(?i)(ttl|expire|evict|maximumSize|maximumWeight|removeEldestEntry|\.clear\s*\()'
          confidence: low
          note: "in-memory cache with no TTL, eviction, or size bound"
```

- [ ] **Step 6: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S01 or S09 or S16 or S17 or java_detector" -v`
Expected: PASS, including the TS/Python S01/S09/S16/S17 cases (unchanged).

- [ ] **Step 7: Calibrate (Spring/Hibernate batch, part 1)**

Follow **Calibration protocol** with `--patterns S01,S09,S16,S17`. Inspect only hits from the two new S01 detectors plus every S09/S16/S17 hit, since the other S01 detectors were calibrated in Batch 1. Run against:

| Repo | Why |
|---|---|
| `spring-projects/spring-petclinic` | canonical Spring Boot + JPA + caching |
| `spring-petclinic/spring-petclinic-microservices` | RestTemplate/WebClient between services, scheduled work |
| `spring-projects/spring-data-examples` | repositories, caching idioms |
| `jhipster/jhipster-sample-app` | generated Spring Boot backend with caches and scheduled jobs |

Record as **Batch 2 — Spring/Hibernate (Tasks 7–8)**. The gate applies.

- [ ] **Step 8: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples docs/calibration/java.md
git commit -m "Add Spring Java detectors for S01/S09/S16/S17; calibrate

Calibrated against <repos@shas>; <n> hits inspected, see docs/calibration/java.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: S29 (new pattern) — N+1 query fan-out, plus S08 pagination

Satisfies: AC-10 (S29 fires on a loop that navigates an association per element with no eager-fetch hint, silent with one), AC-11 (S08 fires on a Spring Data repository with no `Pageable` finder, silent when one exists).

**Files:**
- Modify: `catalog/stability.yaml`: insert `S29` after `S28`; S08 add `java:`
- Modify: `scripts/detectors/modules.py`: add `s29_n_plus_one`
- Create: `tests/detectors/samples/S29/java/{positive,negative,negative_plain_getter}.java`
- Create: `tests/detectors/samples/S08/java/{positive,negative}.java`
- Modify: `docs/calibration/java.md`

**Interfaces:**
- Consumes: `Result`, `_ts_block_end` (existing).
- Produces: `s29_n_plus_one(ctx) -> Result`.

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S29/java/positive.java`:

```java
package com.example.orders;

import java.util.List;
import org.springframework.transaction.annotation.Transactional;

public class OrderReportService {
    private final OrderRepository orderRepository;

    public OrderReportService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public int countLineItems() {
        int total = 0;
        for (Order order : orderRepository.findAll()) {
            total += order.getLineItems().size();
        }
        return total;
    }
}
```

`tests/detectors/samples/S29/java/negative.java` (Review Focus #4: the association is fetched eagerly):

```java
package com.example.orders;

import java.util.List;
import org.springframework.data.jpa.repository.Query;
import org.springframework.transaction.annotation.Transactional;

public class OrderReportService {
    private final OrderRepository orderRepository;

    public OrderReportService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public int countLineItems() {
        int total = 0;
        for (Order order : orderRepository.findAllWithLineItems()) {
            total += order.getLineItems().size();
        }
        return total;
    }
}

interface OrderRepository extends org.springframework.data.jpa.repository.JpaRepository<Order, Long> {
    @Query("select distinct o from Order o join fetch o.lineItems")
    List<Order> findAllWithLineItems();
}
```

`tests/detectors/samples/S29/java/negative_plain_getter.java` (reading a column of the row you already have is not a query):

```java
package com.example.orders;

import java.util.ArrayList;
import java.util.List;
import org.springframework.transaction.annotation.Transactional;

public class OrderIdService {
    private final OrderRepository orderRepository;

    public OrderIdService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public List<Long> ids() {
        List<Long> ids = new ArrayList<>();
        for (Order order : orderRepository.findAll()) {
            ids.add(order.getId());
        }
        return ids;
    }
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

import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
    Page<Order> findByStatus(String status, Pageable pageable);
    Optional<Order> findByReference(String reference);
}

class Order { }
```

- [ ] **Step 2: Write the `s29_n_plus_one` module handler**

In `scripts/detectors/modules.py`, add after the S18 section:

```python
# --------------------------------------------------------------------------
# S29 — bounded query fan-out (no N+1 lazy-loading amplification)
# --------------------------------------------------------------------------

# Only files that touch persistence can lazy-load; a DTO loop elsewhere is not
# a query.
PERSISTENCE_CONTEXT = re.compile(
    r"(javax|jakarta)\.persistence|org\.hibernate|org\.springframework\.data"
    r"|@\s*(Entity|Transactional)\b|\bEntityManager\b|\w+Repository\b")
EAGER_FETCH_HINT = re.compile(
    r"(?i)@\s*EntityGraph\b|JOIN\s+FETCH|Hibernate\s*\.\s*initialize\s*\("
    r"|FetchType\s*\.\s*EAGER")
# `for (Order order : orders)` / `for (final Order order : repo.findAll())`
FOREACH_JAVA = re.compile(
    r"\bfor\s*\(\s*(?:final\s+)?[\w.]+(?:<[^>]*>)?(?:\[\])*\s+(\w+)\s*:")


def s29_n_plus_one(ctx) -> Result:
    """Flag a for-each whose body navigates *through* a getter on the loop
    element — `order.getLineItems().size()`, `order.getCustomer().getName()`.

    A bare `order.getId()` reads a column of the row already loaded and is not
    flagged; chaining off the getter is what touches an association. This is a
    heuristic, not dataflow: it cannot know the association is lazy, so any
    eager-fetch hint anywhere in the file suppresses it.
    """
    text = ctx.code_text
    if not PERSISTENCE_CONTEXT.search(text) or EAGER_FETCH_HINT.search(text):
        return []
    lines = ctx.code_lines
    out: Result = []
    for i, line in enumerate(lines):
        m = FOREACH_JAVA.search(line)
        if not m:
            continue
        end = _ts_block_end(lines, i) if "{" in line else min(i + 1, len(lines) - 1)
        body = "\n".join(lines[i:end + 1])
        var = m.group(1)
        if re.search(rf"\b{re.escape(var)}\s*\.\s*get[A-Z]\w*\s*\(\s*\)\s*\.", body):
            out.append((i + 1, (
                f"loop over `{var}` navigates an association on each element "
                "with no eager fetch hint (@EntityGraph, JOIN FETCH, "
                "Hibernate.initialize) in this file — likely N+1 queries")))
            if len(out) >= 3:
                break
    return out
```

- [ ] **Step 3: Add the S29 pattern to the catalog** (after S28)

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
      - "Hibernate ORM user guide — Fetching"
      - "Nygard, Release It! (2nd ed.), ch. 4 — Unbounded Result Sets"
    detectors:
      java:
        - id: S29-java-n-plus-one
          kind: module
          handler: s29_n_plus_one
          confidence: low
          note: "loop navigates an association per row with no eager fetch hint in the file"
```

- [ ] **Step 4: Add the S08 Java detector**

```yaml
      java:
        - id: S08-java-repository-no-pageable
          kind: file_absent
          anchor: 'interface\s+\w+\s+extends\s+[\w<>, .]*Repository\b'
          require: '(?m)^\s*(List|Collection|Set|Iterable|Stream)\s*<[^>]*>\s+(find|read|get|query|stream)\w*\s*\('
          absent: '\bPageable\b|\b(Page|Slice)\s*<|\b(find|read|get|query|stream)\w*?(Top|First)\d+'
          confidence: low
          note: "Spring Data repository with collection finders and no Pageable/Slice/Top-N form — every call returns the whole match set"
```

- [ ] **Step 5: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S29 or S08 or java_detector or module_handlers" -v`
Expected: PASS, including `S29-java-negative` (Review Focus #4), `S29-java-negative_plain_getter`, and `test_module_handlers_exist`.

- [ ] **Step 6: Calibrate (Spring/Hibernate batch, part 2: S29, S08)**

Follow **Calibration protocol** with `--patterns S29,S08` against Task 7's four repos. S29 is the highest-risk heuristic in this plan. Pay particular attention to chained getters on embedded values or DTOs (`order.getAddress().getCity()` where `address` is `@Embedded`), which regex cannot tell apart from a lazy association. Those are expected `FP-accepted` at `low`, and the log should say how many there were. Append to **Batch 2**. The gate applies.

- [ ] **Step 7: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py tests/detectors/samples docs/calibration/java.md
git commit -m "Add S29 (N+1 fan-out) and S08 Java detectors; calibrate

Calibrated against <repos@shas>; <n> hits inspected, see docs/calibration/java.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Messaging batch — S07 idempotent jobs, S08 poll size, S19 error swallowing

Satisfies: AC-12 (Kafka `poll()` loop with no manual commit fires S07; an empty `catch` fires S19; both silent on correct usage). Also covers the PRD's Kafka `max.poll.records` scope item.

**Files:**
- Modify: `catalog/stability.yaml` (S07, S19 add `java:`; S08 add a second `java:` entry)
- Create: `tests/detectors/samples/S07/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S19/java/{positive,negative}.java`
- Modify: `tests/detectors/samples/S08/java/positive.java`, `negative.java` (append)
- Modify: `docs/calibration/java.md`

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S07/java/positive.java`:

```java
package com.example.consumer;

import java.util.List;
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

    public void backfill(OrderApi api) {
        int page = 0;
        boolean hasMore = true;
        while (hasMore) {
            List<String> rows = api.list(page);
            hasMore = !rows.isEmpty();
            for (String row : rows) {
                insertRow(row);
            }
            page++;
        }
    }

    private void process(ConsumerRecords<String, String> records) { }
    private void insertRow(String row) { }
}

interface OrderApi {
    List<String> list(int page);
}
```

`tests/detectors/samples/S07/java/negative.java`:

```java
package com.example.consumer;

import java.util.List;
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

    public void backfill(OrderApi api, int resumeFrom) {
        int page = resumeFrom;
        boolean hasMore = true;
        while (hasMore) {
            List<String> rows = api.list(page);
            hasMore = !rows.isEmpty();
            for (String row : rows) {
                insertRow(row);
            }
            page++;
            saveCursor(page);
        }
    }

    private void process(ConsumerRecords<String, String> records) { }
    private void insertRow(String row) { }
    private void saveCursor(int page) { }
}

interface OrderApi {
    List<String> list(int page);
}
```

Append to `tests/detectors/samples/S08/java/positive.java`:

```java

class OrderEvents {
    void run(org.apache.kafka.clients.consumer.KafkaConsumer<String, String> consumer) {
        while (true) {
            consumer.poll(java.time.Duration.ofMillis(100)).forEach(r -> handle(r.value()));
        }
    }

    private void handle(String value) { }
}
```

Append to `tests/detectors/samples/S08/java/negative.java`:

```java

class OrderEvents {
    static java.util.Properties config() {
        java.util.Properties props = new java.util.Properties();
        props.put(org.apache.kafka.clients.consumer.ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);
        return props;
    }

    void run(org.apache.kafka.clients.consumer.KafkaConsumer<String, String> consumer) {
        while (true) {
            consumer.poll(java.time.Duration.ofMillis(100)).forEach(r -> handle(r.value()));
        }
    }

    private void handle(String value) { }
}
```

`tests/detectors/samples/S19/java/positive.java` (an empty catch, and a catch whose body is only a comment, which is blanked):

```java
package com.example.consumer;

public class OrderConsumer {
    public void handle(Runnable task) {
        try {
            task.run();
        } catch (Exception e) {
        }
    }

    public void handleQuietly(Runnable task) {
        try { task.run(); } catch (RuntimeException e) { }
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

    public void sleepQuietly() {
        try {
            Thread.sleep(10);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
```

- [ ] **Step 2: Add the S07 Java detectors**

```yaml
      java:
        - id: S07-java-uncheckpointed-loop
          kind: module
          handler: s07_checkpoint
          confidence: low
          note: "paged/batched loop with no persisted cursor — a crash restarts from the beginning"
        - id: S07-java-kafka-no-manual-commit
          kind: file_absent
          anchor: '\bKafkaConsumer\b'
          require: '\.\s*poll\s*\('
          absent: '\b(commitSync|commitAsync|acknowledge)\s*\('
          confidence: low
          note: "KafkaConsumer.poll() loop with no manual offset commit — auto-commit can ack a record before it is processed"
```

`s07_checkpoint` needs no change. For `_lang_key == "java"` it takes the brace-language path (`LOOP_TS`, `_ts_block_end`), which the positive and negative samples exercise.

- [ ] **Step 3: Add the S08 Kafka detector** (append to S08's `java:` list from Task 8)

```yaml
        - id: S08-java-kafka-no-max-poll-records
          kind: file_absent
          anchor: '\bKafkaConsumer\b'
          require: '\.\s*poll\s*\('
          absent: 'max\.poll\.records|MAX_POLL_RECORDS'
          confidence: low
          note: "Kafka poll loop with no max.poll.records — a slow batch overruns max.poll.interval.ms and triggers a rebalance storm"
```

- [ ] **Step 4: Add the S19 Java detectors**

```yaml
      java:
        - id: S19-java-empty-catch
          kind: regex
          pattern: 'catch\s*\([^)]*\)\s*\{\s*\}'
          confidence: medium
          note: "empty catch block — the failure leaves no trace"
        - id: S19-java-catch-only-comment
          kind: regex
          pattern: 'catch\s*\([^)]*\)\s*\{\s*$'
          present_within: '^\s*\}'
          window: 1
          window_offset: 1
          confidence: medium
          note: "catch block with no handling beyond a comment"
```

`window: 1` is deliberate. With `window: 2`, the next *two* lines are searched, so a catch with a one-statement body (`log.error(...)` then `}`) matches, which is a false positive.

- [ ] **Step 5: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S07 or S08 or S19 or java_detector" -v`
Expected: PASS, including the TS/Python S07/S08/S19 cases (unchanged).

- [ ] **Step 6: Calibrate (messaging batch: S07, S08, S19)**

Follow **Calibration protocol** with `--patterns S07,S08,S19`. Inspect every hit from S07's and S19's Java detectors, but only `S08-java-kafka-no-max-poll-records` from S08. Run against:

| Repo | Why |
|---|---|
| `spring-projects/spring-kafka` | Kafka consumers, listener containers, acknowledgment |
| `confluentinc/kafka-streams-examples` | plain-client consumer loops |
| `apache/activemq-artemis-examples` | JMS listeners and catch blocks |
| `rabbitmq/rabbitmq-tutorials` | minimal consumers in every style |

Consumers configured in `application.yml`/`.properties` are invisible to a per-file regex (both Kafka detectors). Record them as `FP-accepted: config outside the file`, as a documented limitation. Don't try to cross-reference config files; spec §7 keeps detection per-file. Record as **Batch 3 — Messaging (Task 9)**. The gate applies.

- [ ] **Step 7: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples docs/calibration/java.md
git commit -m "Add S07/S08/S19 Java detectors for Kafka consumers and catch blocks; calibrate

Calibrated against <repos@shas>; <n> hits inspected, see docs/calibration/java.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: resilience4j/gRPC batch — S05, S10, S11, S12, S15

Satisfies: AC-13 (rate limiting, retry-layer stacking, gRPC deadlines, circuit breaking and fallback; S10 must not fire on a method that merely defines a retry bean).

**Files:**
- Modify: `catalog/stability.yaml` (S05, S10, S11, S12, S15 add `java:`)
- Modify: `scripts/detectors/modules.py`: add `RETRY_LAYERS["java"]`, `SPRING_CONFIG`, and a Java guard in `s10_retry_layers`
- Create: `tests/detectors/samples/S05/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S10/java/{positive,negative,negative_defines_retry_bean}.java`
- Create: `tests/detectors/samples/S11/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S12/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S15/java/{positive,negative}.java`
- Modify: `docs/calibration/java.md`

**Interfaces:**
- Consumes: `s10_retry_layers(ctx)` and `DECLARATION` (existing). `DECLARATION` already matches `(public|private|protected)\s+`, so a Java factory method's own declaration line is skipped.
- Produces: `RETRY_LAYERS["java"]`, `SPRING_CONFIG`.

The draft counted `maxAttempts` as its own "SDK retry config" layer. That makes a single `RetryTemplate.builder().maxAttempts(3)` bean definition look like two layers (the wrapper plus its own config), which is exactly the false positive Review Focus #3 names. For Java, a layer is a retry *mechanism*: a hand-written loop, Spring Retry, resilience4j or Failsafe. `maxAttempts` is configuration of one of them. Bean definitions live in `@Configuration` classes, which define retry and never call through it, so the handler skips those files for Java.

- [ ] **Step 1: Write the samples**

`tests/detectors/samples/S05/java/positive.java`:

```java
package com.example.client;

import java.util.List;
import org.springframework.web.client.RestTemplate;

public class BulkClient {
    private final RestTemplate restTemplate;

    public BulkClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public void fetchAll(List<String> ids) {
        for (String id : ids) {
            restTemplate.getForObject("https://api.example.com/items/{id}", String.class, id);
        }
    }
}
```

`tests/detectors/samples/S05/java/negative.java`:

```java
package com.example.client;

import io.github.bucket4j.Bucket;
import java.util.List;
import org.springframework.web.client.RestTemplate;

public class BulkClient {
    private final RestTemplate restTemplate;
    private final Bucket bucket;

    public BulkClient(RestTemplate restTemplate, Bucket bucket) {
        this.restTemplate = restTemplate;
        this.bucket = bucket;
    }

    public void fetchAll(List<String> ids) throws InterruptedException {
        for (String id : ids) {
            bucket.asBlocking().consume(1);
            restTemplate.getForObject("https://api.example.com/items/{id}", String.class, id);
        }
    }
}
```

`tests/detectors/samples/S10/java/positive.java` (Spring Retry stacked on resilience4j retry: 3 × 3 attempts):

```java
package com.example.client;

import io.github.resilience4j.retry.annotation.Retry;
import org.springframework.retry.annotation.Retryable;

public class DoublyRetriedClient {
    @Retryable(maxAttempts = 3)
    @Retry(name = "orders")
    public String call() {
        return doCall();
    }

    private String doCall() { return "ok"; }
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
            } catch (RuntimeException e) {
                if (attempt == 2) {
                    throw e;
                }
            }
        }
        throw new IllegalStateException("exhausted");
    }

    private String sdkCall() {
        return "ok";
    }
}
```

`tests/detectors/samples/S10/java/negative_defines_retry_bean.java` (Review Focus #3: two retry beans *defined*, none stacked):

```java
package com.example.config;

import io.github.resilience4j.retry.RetryConfig;
import io.github.resilience4j.retry.RetryRegistry;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class RetryBeans {
    @Bean
    public RetryTemplate retryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(100, 2, 5000, true)
                .build();
    }

    @Bean
    public RetryRegistry retryRegistry() {
        return RetryRegistry.of(RetryConfig.custom()
                .maxAttempts(3)
                .waitDuration(Duration.ofMillis(200))
                .build());
    }
}
```

`tests/detectors/samples/S11/java/positive.java`:

```java
package com.example.grpc;

import example.OrderServiceGrpc;
import io.grpc.ManagedChannel;

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

import example.OrderServiceGrpc;
import io.grpc.ManagedChannel;
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
        RuntimeException last = null;
        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
            try {
                return doCall();
            } catch (RuntimeException e) {
                last = e;
            }
        }
        throw last;
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

import org.springframework.web.client.RestTemplate;

public class RecommendationClient {
    private final RestTemplate restTemplate;

    public RecommendationClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public String getRecommendations(String userId) {
        return restTemplate.getForObject("https://recs.example.com/{id}", String.class, userId);
    }
}
```

`tests/detectors/samples/S15/java/negative.java`:

```java
package com.example.client;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.decorators.Decorators;
import org.springframework.web.client.RestTemplate;

public class RecommendationClient {
    private final RestTemplate restTemplate;
    private final CircuitBreaker breaker;

    public RecommendationClient(RestTemplate restTemplate, CircuitBreaker breaker) {
        this.restTemplate = restTemplate;
        this.breaker = breaker;
    }

    public String getRecommendations(String userId) {
        return Decorators.ofSupplier(() -> callUpstream(userId))
                .withCircuitBreaker(breaker)
                .withFallback(t -> defaultRecommendations())
                .get();
    }

    private String callUpstream(String userId) {
        return restTemplate.getForObject("https://recs.example.com/{id}", String.class, userId);
    }

    private String defaultRecommendations() { return "default"; }
}
```

- [ ] **Step 2: Add `RETRY_LAYERS["java"]` and the configuration guard in `modules.py`**

Add a third key to `RETRY_LAYERS`, after `"python"`:

```python
    "java": [
        ("own retry loop", re.compile(
            r"\b(for|while)\s*\(.*\b(attempt|attempts|retry|retries|tries)\b", re.I)),
        ("Spring Retry", re.compile(r"@\s*Retryable\b|\bRetryTemplate\b")),
        ("resilience4j retry", re.compile(
            r"@\s*Retry\s*\(|\bRetry\s*\.\s*(of\w*|decorate\w*)\s*\(|\bRetryRegistry\b"
            r"|\bRetryConfig\s*\.\s*(custom|of\w*)\s*\(")),
        ("Failsafe retry", re.compile(r"\bFailsafe\s*\.\s*with\b|\bRetryPolicy\s*\.\s*builder\s*\(")),
    ],
```

After `DECLARATION`, add:

```python
# A Spring @Configuration class defines retry beans; it never calls through
# them. Two bean definitions in one config class are not two stacked layers.
SPRING_CONFIG = re.compile(r"@\s*(Configuration|AutoConfiguration)\b")
```

In `s10_retry_layers`, add a first line so that the function begins:

```python
def s10_retry_layers(ctx) -> Result:
    if _lang_key(ctx) == "java" and SPRING_CONFIG.search(ctx.code_text):
        return []
    if BUDGET.search(ctx.code_text):
        return []
```

(The rest of the function is unchanged. The guard is unreachable for TypeScript and Python.)

- [ ] **Step 3: Add the S05 Java detector**

```yaml
      java:
        - id: S05-java-client-calls-without-limiter
          kind: file_absent
          anchor: '\w*([Hh]ttp[Cc]lient|[Rr]estTemplate|[Ww]ebClient|[Ss]tub)\s*\.\s*\w+\s*\('
          require: '(?m)^\s*(for|while)\s*\(|\.\s*forEach\s*\(|\.\s*parallelStream\s*\(|CompletableFuture\s*\.\s*allOf\s*\('
          absent: '(?i)(ratelimit|rate_limit|limiter|throttle|bucket4j|\bBucket\b|Semaphore|\.acquire\s*\()'
          confidence: low
          note: "outbound calls made in a loop or fan-out with no local rate limiter or concurrency gate in this file"
```

- [ ] **Step 4: Add the S10 Java detector**

```yaml
      java:
        - id: S10-java-nested-retry
          kind: module
          handler: s10_retry_layers
          confidence: low
          note: "more than one retry mechanism in the same call path, with no shared budget"
```

- [ ] **Step 5: Add the S11 Java detector**

```yaml
      java:
        - id: S11-java-grpc-no-deadline
          kind: file_absent
          anchor: 'BlockingStub\b|newBlockingStub\s*\('
          absent: '\bwithDeadline(After)?\s*\(|Context\s*\.\s*current\s*\(\s*\)\s*\.\s*withDeadline'
          confidence: low
          note: "gRPC blocking stub call with no deadline"
```

- [ ] **Step 6: Add the S12 Java detector**

```yaml
      java:
        - id: S12-java-no-breaker
          kind: file_absent
          anchor: '\b(MAX_RETRIES|maxAttempts|retries|retryCount)\b|@\s*Retryable\b'
          absent: '(?i)(circuit.?breaker|breaker|resilience4j|half.?open)'
          confidence: low
          note: "retries with no circuit breaker"
```

- [ ] **Step 7: Add the S15 Java detector**

```yaml
      java:
        - id: S15-java-no-fallback
          kind: file_absent
          anchor: '\w*([Hh]ttp[Cc]lient|[Rr]estTemplate|[Ww]ebClient)\s*\.\s*\w+\s*\('
          absent: '(?i)(fallback|degrade|stale|default(Value|Response)|onErrorReturn|onErrorResume|\.exceptionally\s*\()'
          confidence: low
          note: "external call with no fallback branch"
```

- [ ] **Step 8: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "S05 or S10 or S11 or S12 or S15 or java_detector" -v`
Expected: PASS, including `S10-java-negative_defines_retry_bean` staying silent (Review Focus #3) and every TS/Python case for these patterns (unchanged).

- [ ] **Step 9: Calibrate (resilience4j/gRPC batch)**

Follow **Calibration protocol** with `--patterns S05,S10,S11,S12,S15` against:

| Repo | Why |
|---|---|
| `resilience4j/resilience4j-spring-boot3-demo` | CircuitBreaker, Retry, RateLimiter, Bulkhead, fallbacks |
| `resilience4j/resilience4j-spring-boot2-demo` | the same idioms on the older API |
| `grpc/grpc-java` (sweep `examples/` only: pass `--repo` the `examples` directory's repo root and filter the TSV to `examples/`) | blocking stubs with and without deadlines |
| `spring-petclinic/spring-petclinic-microservices` | resilience4j in a real service mesh |

Record as **Batch 4 — resilience4j/gRPC (Task 10)**. The gate applies.

- [ ] **Step 10: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py tests/detectors/samples docs/calibration/java.md
git commit -m "Add resilience4j/gRPC Java detectors for S05/S10/S11/S12/S15; calibrate

Calibrated against <repos@shas>; <n> hits inspected, see docs/calibration/java.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Akka/JMS/RabbitMQ batch — S06, S18, and the Akka/JMS/RabbitMQ idioms

Satisfies: AC-14 (S06 and S18 fire on Java and stay silent on correct usage). Also covers the PRD's Akka (dispatcher isolation) and JMS/RabbitMQ (ack mode, prefetch/QoS) scope items. Akka event-loop blocking is already S27.

**Files:**
- Modify: `catalog/stability.yaml` (S06, S18 add `java:`; S01, S07, S13, S14 append one Java entry each)
- Modify: `scripts/detectors/modules.py`: add `FUNC_JAVA`, `VALIDATION_JAVA`, `EXTERNAL_CALL_JAVA`, and route `s18_fail_fast`
- Create: `tests/detectors/samples/S06/java/{positive,negative}.java`
- Create: `tests/detectors/samples/S18/java/{positive,negative}.java`
- Modify (append): `tests/detectors/samples/{S01,S07,S13,S14}/java/{positive,negative}.java`
- Modify: `docs/calibration/java.md`

**Interfaces:**
- Consumes: `EXTERNAL_CALL`, `VALIDATION`, `FUNC_TS`, `FUNC_PY` (existing; not edited).
- Produces: `FUNC_JAVA`, `VALIDATION_JAVA`, `EXTERNAL_CALL_JAVA`.

The shared `VALIDATION` regex knows `throw new (Validation|BadRequest|TypeError|RangeError)` and nothing Java-shaped, so a Java method that throws `IllegalArgumentException` after a call would never be seen as validating. Editing the shared regex would change TS/Python behaviour (AC-16), so Java gets its own vocabulary.

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

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class OrderService {
    private final HttpClient client = HttpClient.newHttpClient();

    public String placeOrder(String payload) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create("https://pricing.example.com")).build();
        String quote = client.send(request, HttpResponse.BodyHandlers.ofString()).body();
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("payload required");
        }
        return quote;
    }
}
```

`tests/detectors/samples/S18/java/negative.java` (validates first):

```java
package com.example.orders;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class OrderService {
    private final HttpClient client = HttpClient.newHttpClient();

    public String placeOrder(String payload) throws Exception {
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("payload required");
        }
        HttpRequest request = HttpRequest.newBuilder(URI.create("https://pricing.example.com")).build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }
}
```

Append to `tests/detectors/samples/S01/java/positive.java`:

```java

class JmsReader {
    String next(javax.jms.Session session, javax.jms.Queue queue) throws Exception {
        javax.jms.MessageConsumer consumer = session.createConsumer(queue);
        return ((javax.jms.TextMessage) consumer.receive()).getText();
    }
}
```

Append to `tests/detectors/samples/S01/java/negative.java`:

```java

class JmsReader {
    String next(javax.jms.Session session, javax.jms.Queue queue) throws Exception {
        javax.jms.MessageConsumer consumer = session.createConsumer(queue);
        return ((javax.jms.TextMessage) consumer.receive(5000)).getText();
    }
}
```

Append to `tests/detectors/samples/S07/java/positive.java`:

```java

class RabbitOrders {
    void start(com.rabbitmq.client.Channel channel, com.rabbitmq.client.Consumer consumer) throws Exception {
        channel.basicConsume("orders", true, consumer);
    }
}
```

Append to `tests/detectors/samples/S07/java/negative.java`:

```java

class RabbitOrders {
    void start(com.rabbitmq.client.Channel channel, com.rabbitmq.client.Consumer consumer) throws Exception {
        channel.basicConsume("orders", false, consumer);
    }
}
```

Append to `tests/detectors/samples/S13/java/positive.java`:

```java

class InventoryActor extends akka.actor.AbstractActor {
    @Override
    public Receive createReceive() {
        return receiveBuilder()
                .match(String.class, sku -> {
                    Thread.sleep(100);
                    getSender().tell(sku, getSelf());
                })
                .build();
    }
}
```

Append to `tests/detectors/samples/S13/java/negative.java`:

```java

class InventoryActor extends akka.actor.AbstractActor {
    static akka.actor.Props props() {
        return akka.actor.Props.create(InventoryActor.class).withDispatcher("blocking-io-dispatcher");
    }

    @Override
    public Receive createReceive() {
        return receiveBuilder()
                .match(String.class, sku -> {
                    Thread.sleep(100);
                    getSender().tell(sku, getSelf());
                })
                .build();
    }
}
```

Append to `tests/detectors/samples/S14/java/positive.java`:

```java

class RabbitIntake {
    void start(com.rabbitmq.client.Channel channel, com.rabbitmq.client.Consumer consumer) throws Exception {
        channel.basicConsume("intake", false, consumer);
    }
}
```

Append to `tests/detectors/samples/S14/java/negative.java`:

```java

class RabbitIntake {
    void start(com.rabbitmq.client.Channel channel, com.rabbitmq.client.Consumer consumer) throws Exception {
        channel.basicQos(50);
        channel.basicConsume("intake", false, consumer);
    }
}
```

- [ ] **Step 2: Add the Java S18 vocabulary and route `s18_fail_fast`**

In `scripts/detectors/modules.py`, after `FUNC_PY`:

```python
# A method or constructor header whose opening brace is on the same line.
# Written without nested overlapping quantifiers, so a long non-matching
# line fails in linear time.
FUNC_JAVA = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*"
    r"(?:(?:public|private|protected|static|final|synchronized|abstract|default)\s+)+"
    r"(?:<[^>]*>\s*)?(?:[\w.$]+(?:<[^;{}()]*>)?(?:\[\])*\s+)?"
    r"\w+\s*\([^)]*\)\s*(?:throws\s+[\w.,\s]+)?\{")
VALIDATION_JAVA = re.compile(
    r"\bvalidate\w*\s*\(|\bisValid\w*\s*\(|\bObjects\s*\.\s*requireNonNull\s*\("
    r"|\bPreconditions\s*\.\s*check\w+\s*\(|\bAssert\s*\.\s*\w+\s*\("
    r"|throw\s+new\s+(IllegalArgumentException|\w*Validation\w*Exception"
    r"|ConstraintViolationException|BadRequest\w*|ResponseStatusException)\b")
EXTERNAL_CALL_JAVA = re.compile(
    EXTERNAL_CALL.pattern
    + r"|\.\s*(sendAsync|exchange|retrieve|getForObject|getForEntity|postForObject"
      r"|postForEntity|executeQuery|executeUpdate)\s*\(",
    re.I)
```

Replace the head of `s18_fail_fast`:

```python
def s18_fail_fast(ctx) -> Result:
    is_py = _lang_key(ctx) == "python"
    func_re = FUNC_PY if is_py else FUNC_TS
    lines = ctx.code_lines
```

with:

```python
def s18_fail_fast(ctx) -> Result:
    key = _lang_key(ctx)
    func_re = {"python": FUNC_PY, "java": FUNC_JAVA}.get(key, FUNC_TS)
    call_re = EXTERNAL_CALL_JAVA if key == "java" else EXTERNAL_CALL
    valid_re = VALIDATION_JAVA if key == "java" else VALIDATION
    lines = ctx.code_lines
```

In the loop body of the same function, replace `EXTERNAL_CALL.search(lines[i])` with `call_re.search(lines[i])`, and `VALIDATION.search(lines[i])` with `valid_re.search(lines[i])`. For TypeScript and Python, `call_re`/`valid_re` are the same objects as before, so behaviour is unchanged.

- [ ] **Step 3: Add the S06 Java detector**

```yaml
      java:
        - id: S06-java-single-pool-no-priority
          kind: file_absent
          anchor: '\bExecutors\s*\.\s*new\w*\s*\(|new\s+ThreadPoolExecutor\s*\(|\bExecutorService\b'
          absent: '(?i)(priority|interactive|criticality|urgent|foreground|background|batch)'
          confidence: low
          note: "one executor serves every caller; no priority or criticality separation"
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

- [ ] **Step 5: Add the Akka/JMS/RabbitMQ entries** (each appended to that pattern's existing `java:` list)

S01:

```yaml
        - id: S01-java-jms-receive-no-timeout
          kind: regex
          pattern: '\.\s*receive\s*\(\s*\)'
          present_within: '\b(MessageConsumer|JMSConsumer)\b|\b(javax|jakarta)\s*\.\s*jms\b'
          window: 1
          window_before: 10
          confidence: low
          note: "JMS receive() with no timeout — blocks the thread until a message arrives, forever if none does"
```

S07:

```yaml
        - id: S07-java-rabbitmq-auto-ack
          kind: regex
          pattern: '\.\s*basicConsume\s*\(\s*[^,()]+,\s*true\s*,'
          confidence: low
          note: "RabbitMQ basicConsume with autoAck=true — a crash mid-message loses it"
```

S13:

```yaml
        - id: S13-java-akka-blocking-default-dispatcher
          kind: file_absent
          anchor: '\bAbstractActor\w*\b|\bAbstractBehavior\b|\bBehaviors\s*\.\s*(receive|setup)\b'
          require: '\bThread\s*\.\s*sleep\s*\(|\.\s*execute(Query|Update)\s*\(|\bDriverManager\s*\.\s*getConnection\s*\(|\w*[Rr]estTemplate\s*\.\s*\w+\s*\(|\w*[Hh]ttp[Cc]lient\s*\.\s*send\s*\('
          absent: 'withDispatcher|DispatcherSelector|blocking\S*dispatcher'
          confidence: low
          note: "actor makes blocking calls on the default dispatcher — it starves every other actor sharing it"
```

S14:

```yaml
        - id: S14-java-rabbitmq-no-prefetch
          kind: file_absent
          anchor: '\.\s*basicConsume\s*\('
          absent: '(?i)basicQos\s*\(|prefetch'
          confidence: low
          note: "RabbitMQ consumer with no basicQos prefetch — the broker pushes the whole queue into this process"
```

- [ ] **Step 6: Run tests**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -q`
Expected: PASS, including every `S18-typescript-*` and `S18-python-*` case. `FUNC_JAVA`, `VALIDATION_JAVA` and `EXTERNAL_CALL_JAVA` are only reached when `_lang_key(ctx) == "java"`.

- [ ] **Step 7: Calibrate (Akka/JMS/RabbitMQ batch)**

Follow **Calibration protocol** with `--patterns S06,S18,S01,S07,S13,S14`. Inspect every S06/S18 hit, but only the four new detectors' hits from S01/S07/S13/S14. Run against:

| Repo | Why |
|---|---|
| `spring-projects/spring-amqp-samples` | RabbitMQ consumers, prefetch, ack modes |
| `rabbitmq/rabbitmq-tutorials` | raw-client consumers with and without `basicQos`/autoAck |
| `apache/activemq-artemis-examples` | JMS `receive()` with and without timeouts |
| `akka/akka-samples` (archived; sweep its Java sample directories) | actors, dispatchers |

Record as **Batch 5 — Akka/JMS/RabbitMQ (Task 11)**. The gate applies.

- [ ] **Step 8: Commit**

```bash
git add catalog/stability.yaml scripts/detectors/modules.py tests/detectors/samples docs/calibration/java.md
git commit -m "Add S06/S18 and Akka/JMS/RabbitMQ Java detectors; calibrate

Calibrated against <repos@shas>; <n> hits inspected, see docs/calibration/java.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Regenerate docs, full suite, CHANGELOG, version bump

Satisfies: AC-15 (generated docs in sync, full suite green, plugin validates and loads) and AC-16 (verified here across the whole branch).

**Files:**
- Modify: `skills/stability-catalog/references/patterns.md` (generated)
- Modify: `examples/sample-report.md` (generated)
- Modify: `README.md`: the supported-languages sentence and **The catalog** section
- Modify: `tests/test_docs_in_sync.py`: `test_catalog_tiers_match_the_documented_split`
- Modify: `CHANGELOG.md`
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml` (version bump: `test_versions_agree` requires these three and the `CHANGELOG.md` heading to match)

- [ ] **Step 1: Regenerate the generated artefacts**

```bash
uv run scripts/gen_catalog_docs.py
uv run scripts/gen_sample_report.py
```

- [ ] **Step 2: Verify generation is idempotent and CI-clean**

```bash
uv run scripts/gen_catalog_docs.py --check
```

Expected: exits 0.

- [ ] **Step 3: Verify AC-16 across the branch**

```bash
git diff main --stat -- tests/detectors/samples | grep -v '/java/' || true
git diff main -- catalog/stability.yaml | grep -E '^-' | grep -v '^---' || true
grep -n "confidence: high" <(git diff main -- catalog/stability.yaml | grep '^+') || true
```

Expected: the first command lists no TS/Python sample changes, the second prints no removed catalog lines, and the third prints nothing (no new `high` detector).

- [ ] **Step 4: Update README, bump the version, update the changelog**

In `README.md`, change "Detectors ship for TypeScript, JavaScript and Python." to "Detectors ship for TypeScript, JavaScript, Python and Java." In **The catalog** section, change "19 stability patterns" to "22 stability patterns", and add a paragraph after the Tier B one:

```markdown
Tier A, JVM-specific: no blocking calls on event-loop threads · locks and
waits with a bound · bounded query fan-out (no N+1 lazy loading).
```

`tests/test_docs_in_sync.py::test_catalog_tiers_match_the_documented_split` pins the tier split the README documents. It hardcodes Tier A as S01–S10, so it has failed since Task 3 added S27. Update its Tier A expectation to match the documented split, leaving Tier B untouched:

```python
    assert tier_a == [f"S{n:02d}" for n in (*range(1, 11), 27, 28, 29)], tier_a
```

Bump `0.2.0` → `0.3.0` in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `pyproject.toml`. Add a `## 0.3.0` heading at the top of `CHANGELOG.md`, following the `0.2.0` entry's style, with an **Added** section covering:
- Java as a scanned language, with detectors for S01–S19.
- The new patterns S27–S29.
- The framework coverage: Spring, Hibernate/JPA, Kafka, resilience4j, gRPC, Akka, JMS, RabbitMQ.
- `scripts/calibrate.py` and the calibration log.

Point to `docs/calibration/java.md`.

- [ ] **Step 5: Run the full suite**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/ -q`
Expected: all PASS, including `test_docs_in_sync.py`, `test_versions_agree`, and `test_guardrail.py`. Java adds no code path to `guardrail.py`.

- [ ] **Step 6: Validate the plugin still loads**

```bash
claude plugin validate . --strict
claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck
claude plugin list
```

Expected: `claude plugin list` reports thunderstruck as `enabled`, not `failed to load`.

- [ ] **Step 7: Commit**

```bash
git add skills/stability-catalog/references/patterns.md examples/sample-report.md README.md CHANGELOG.md .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml
git commit -m "Regenerate catalog docs and sample report for Java support; bump to 0.3.0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Review Focus

1. **A `.java` file with no package statement, or with Windows line endings.** `signals.py` must not crash, and `lizard` and the detectors must still run. (Task 1, `test_java_file_scans_without_crashing`)
2. **A `@Retryable` annotation split across lines.** A window-based `absent_within` must still see `random = true` three lines below the annotation. (Task 6, `S02/java/negative_multiline_annotation.java`)
3. **A class that *defines* retry beans (`RetryTemplate`, `RetryRegistry`) rather than calling through them.** It must not count as stacked retry layers. (Task 10, `S10/java/negative_defines_retry_bean.java`)
4. **A loop that navigates an association fetched with `JOIN FETCH` or `@EntityGraph`**, and a loop that only reads a column (`getId()`). Neither may fire S29. (Task 8, `S29/java/negative.java`, `negative_plain_getter.java`)
5. **A blocking call inside a plain (non-reactive) Spring MVC `@RestController` method**, and the same call offloaded with `subscribeOn(Schedulers.boundedElastic())`. Neither may fire S27. (Task 3, `S27/java/negative_plain_controller.java`, `negative.java`)
6. **A short in-memory `synchronized` method or `lock()` section.** It must not fire S28. (Task 4, `S28/java/negative_in_memory_monitor.java`)
7. **A `ConcurrentHashMap` that is a registry, not a cache.** It must not fire S17. (Task 7, `S17/java/negative_registry_map.java`)

## Deferred from the spec §3 table

These rows of the spec's coverage table are not built in this pass. None is named by an acceptance criterion, and each has a concrete reason:

| Spec row | Reason deferred |
|---|---|
| S01 gRPC channel deadline, Kafka `request.timeout.ms` | gRPC deadlines are per-call (S11 covers them). Kafka client timeouts are usually set in external config that a per-file regex cannot see. |
| S03 `Retry-After` in Spring/OkHttp-specific APIs | the S03 file-level detectors already match on status codes and header names, whatever the client |
| S06 `@Async` pool naming, Akka mailbox priority | no reliable single-file signal. `@Async("pool")` naming is not priority separation. |
| S07 JMS ack mode, Spring Batch checkpoint | JMS `AUTO_ACKNOWLEDGE` with a `MessageListener` acks after `onMessage` returns, which is correct. Spring Batch checkpoints by default. |
| S08 RabbitMQ `basicQos` | built under S14, where prefetch belongs (backpressure) |
| S11 chained `WebClient` timeout propagation | needs cross-call dataflow |
| S12 resilience4j threshold sanity | thresholds live in YAML config |
| S14 Akka Streams `OverflowStrategy`, JMS listener concurrency | `Source.queue` requires an overflow strategy argument; listener concurrency is config |
| S16 Quartz | calibration repos contain no Quartz usage to calibrate against. Revisit with a Quartz corpus. |
| S17 Hibernate second-level cache eviction | expiry lives in `ehcache.xml`/provider config, outside the file |
