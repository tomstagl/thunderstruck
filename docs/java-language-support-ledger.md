# SDD ledger — Java language support (issue #8)

Archived record of the subagent-driven-development run that implemented
issue #8 (merged as `a9e14ea`, PR #13). Every controller decision made
during that run is logged here in order, each tagged `Ruling:` with what it
costs if wrong. The calibration evidence itself lives in
`docs/calibration/java.md`; this file is the process trail behind it.

Original ledger header follows.

---

# SDD ledger — plan: docs/superpowers/plans/2026-09-23-java-language-support.md

Branch: feat/java-support (from main 28bce22). Plan+spec revision commit: 398e521.
Spec: docs/superpowers/specs/2026-09-23-java-language-support-design.md

## Pre-flight scan

| Tasks | Shared file / interface | Finding |
|---|---|---|
| 1 → 6,10 | `_lang_key` returns "java"; SLEEP_RES/RETRY_LAYERS keyed by it | consistent — keys added in the same task as first catalog use |
| 1 → all | test_java_detectors.py per-detector check on positive.java | later tasks append classes to positives; plan says so in Global Constraints |
| 1 → 5-11 | scripts/calibrate.py consumed by calibration protocol | CLI flags match (--repo --lang --patterns) |
| 2 ↔ 7 ↔ 11 | S01 java list + S01 positive/negative samples | appends only; appended classes use FQNs; ids unique (harness checked) |
| 5 ↔ 11 | S13/S14 java lists + samples | appends only; consistent |
| 6 ↔ 9 ↔ 11 | S07 samples (created 9, appended 11) | consistent |
| 8 ↔ 9 | S08 java list + samples | appends only; consistent |
| 3,4,8 | patterns S27→S28→S29 order after S19 | consistent |
| 10 ↔ 11 | modules.py s10 guard vs s18 routing | disjoint functions |
| each task | tests vs code within task | verified by scratch harness running every plan detector/sample/module snippet through run_detectors: 50/50 sample cases, all detectors fire solo, no TS/PY regression |

Ruling: work on branch feat/java-support in the main checkout rather than a separate worktree — main is clean and nothing else is in flight — cost if wrong: none beyond branch switch.
Ruling: issue #8 checklist ticked when a task's review is clean (commits land on the branch; no per-task PRs) — the user asked to tick "as each task's PR/commit lands" — cost if wrong: boxes ticked before merge to main.
Ruling: test_docs_in_sync may fail on intermediate commits until Task 12 regenerates — plan Global Constraints allows it — cost if wrong: intermediate commits not CI-green.

## Progress
Task 1: dispatched (base 398e521, implementer sonnet)
Task 1: minor (deferred): test_calibrate_sweeps_every_tracked_file is vacuous until a Java S14 detector exists
Ruling: Task 5 (which adds S14 Java detectors) also strengthens test_calibrate_sweeps_every_tracked_file to assert the src/main A.java hit appears — makes the exclusion test non-vacuous at the first point it can be — cost if wrong: one extra assertion in Task 5's diff.
Task 1: complete (commits 398e521..08da311, review clean)
Ruling: Tasks 2-4 dispatched as one batch (one implementer, three commits, one review) — same-shape catalog+sample transcription with no calibration step — cost if wrong: a review finding in one task delays ticking the other two.
Tasks 2-4: dispatched (base 08da311)
Ruling: Task 12 amended in plan to update test_catalog_tiers_match_the_documented_split (Tier A += S27-S29) and README catalog section — the existing test hardcodes Tier A = S01-S10 and fails since S27; plan draft missed it; the test pins documentation, not TS/PY detector behaviour, so AC-16 is not engaged — cost if wrong: an existing test's expectation changes.
Tasks 2-4: review → Needs fixes (4 Important, all plan-mandated FPs on correct Java, confirmed on engine)
Ruling: S28 lock/monitor detectors bound the search to the locked section — tempered-token present_within stops at the first `}` (synchronized) or `.unlock(` (Lock); `.get()`/`.read(`/`.write(` dropped from the blocking-call set — negative-control rule; snapshot-then-I/O is the recommended fix and must be silent — cost if wrong: misses I/O after a nested `}` inside the section.
Ruling: S01 future detector anchors on a *future*-named receiver (or `.join()`), suppressed by orTimeout/completeOnTimeout — Optional.get() and bounded futures are correct code — cost if wrong: misses `.get()` on futures with non-"future" names.
Ruling: S27 drops `.block…(` — Reactor already throws when block() runs on an event-loop thread, so surviving block() calls are on servlet/main threads (correct usage, AC-4) — cost if wrong: misses block() inside Netty handlers.
Ruling: S01 OkHttp suppresses only on callTimeout — OkHttp has 10s per-op defaults, so the only real gap is the whole-call bound the note names; calibration tripwire decides whether it stays — cost if wrong: noisier OkHttp hits at low confidence.
Ruling: minors folded into the same round (Awaitility look-ahead, JDBC Properties form, HttpClient window 10, drop no-op \w* prefixes) — cheap and each removes a confirmed or likely FP — cost if wrong: none.
Tasks 2-4: minor (deferred): S27 absent_within accepts any subscribeOn/publishOn incl. Schedulers.parallel() — missed detection; note in Batch 1 calibration.
Tasks 2-4: fix round 1 applied (18e8978); spec/plan updated ($(git rev-parse --short HEAD))
Tasks 2-4: fix round 1/5 (4 Important + 4 minors addressed, 0 open; commits 8f6d702..18e8978)
Tasks 2-4: minor (deferred): S28 tempered `}` boundary also stops at `}` inside string literals ("{}" log formats) — missed detection only
Task 2: complete (commits 08da311..731ac70 + fix 18e8978, review clean)
Task 3: complete (commits 731ac70..db42489 + fix 18e8978, review clean)
Task 4: complete (commits db42489..eb79cf9 + fix 18e8978, review clean)
Task 5: dispatched (base c94865f, implementer opus — calibration judgment)
Ruling: calibration log format — **Hits** lists exactly the final sweep's hits (gate count = final TSV lines); FPs removed by a detector fix are listed in a separate 'Fixed during calibration' section with the negative sample each produced — protocol step 6 counts final-sweep hits, and fixed FPs cannot appear in a final sweep — cost if wrong: none; both are recorded.
Task 5: review Approved, calibration gate PASS (1 final hit = 1 TSV line; 6 FP-fixed with samples)
Task 5: minor (deferred): S14 `(<[^>]*>)?` misses nested generics `LinkedBlockingQueue<Future<?>>()` — missed detection
Task 5: minor (deferred): S13/S14 zero real-world TPs in batch 1 — watch in later batches
Ruling: Task 5 minors 1-3 folded into Task 6's dispatch (S01 absent `\.\s*timeout\s*\(\s*[^\s)]` so zero-arg getters don't silence; S14 absent_within narrowed to `idle`; fix jsoup rationale wording in java.md) — Task 6 already edits catalog + Batch 1 log; cheap precision/recall wins — cost if wrong: small scope growth in Task 6.
Task 5: complete (commits c94865f..de42c2a, review clean)
Task 6: dispatched (base de42c2a, implementer opus)
Task 6: implementer DONE_WITH_CONCERNS (03f9a97) — S02-S04 0 real hits; SLEEP_RES java misses quietlySleep()/bare sleep()
Ruling: widen SLEEP_RES["java"] to any *sleep*-named call (`\b\w*[Ss]leep\w*\s*\(`), re-sweep batch 1 for S02 — calibration found two real backoff sites the narrow form misses (HikariPool:762, ResilientPooledObjectFactory:89); s02_backoff still gates on retry context and judges growth/cap/jitter, so a wider sleep anchor adds recall without new FP surface beyond what calibration inspects — cost if wrong: extra S02 hits in files with sleep-named helpers.
Ruling: Task 7 adds one public repo that actually uses spring-retry @Retryable (found via gh code search) and sweeps S02,S04 on it, appending to Batch 1 — microservices has no @Retryable, so the @Retryable detectors have no real-world evidence yet — cost if wrong: one extra clone.
Ruling: keep s02_backoff's file-level jitter judgement unchanged; HikariPool:762 stays a known miss — the file-level view is the handler's deliberate guard against FPs on helper-computed backoff, and it is shared with TS/Python (AC-16) — cost if wrong: S02 misses Java files that use Random for unrelated reasons.
Task 6: review → Needs fixes (gate PASS; 4 Important FPs on correct Java via probes: S04 catch-all, @Retryable window, Spring 7 @Retryable, sleep accessors)
Ruling: S04-java-catch-all-retry keys on retry vocabulary around the catch (window_before 6 incl. loop header) and is suppressed by rethrow/classification; confidence medium→low — the canonical transient-only form must be silent and there is zero real-world evidence — cost if wrong: misses catch-all retries with no retry vocabulary nearby.
Ruling: @Retryable detectors window 6→12; accept Spring 7 `jitter=`/`includes=`/`excludes=`/`predicate=` — one-attribute-per-line formatting and the current Spring API are correct code — cost if wrong: may read into the next member (recall loss only).
Ruling: SLEEP_RES["java"] excludes accessor names (set/get/is/has + Capital) — setters of sleep config are not waits — cost if wrong: misses a sleep helper literally named getSleep…(), unlikely.
Ruling: M-1 (S03 fires on server-side 429 throttles) and M-4 (missing negative_maps_status_no_retry) folded into this fix round; M-2, M-3 recorded as Known limitations (shared handler, AC-16).
Task 6: fix round 1/5 (4 Important + M-1..M-4 addressed, 0 open; commits 6f04050..20d122f)
Task 6: complete (commits de42c2a..20d122f, review clean)
Task 7: dispatched (base 20d122f, implementer opus)
Task 7: implementer DONE_WITH_CONCERNS (aa1de7b): 11 TP final hits in batch 2; iexec-core added to batch 1 (3 TP @Retryable no-jitter)
Ruling: S09-java-cacheable-no-sync suppressed when `unless =` is present — Spring forbids sync=true with unless, so the prescribed fix is unavailable and the lead is not actionable — cost if wrong: misses stampede-prone @Cacheable(unless=...) methods.
Ruling: accept S16 dropping fixedRate (cron-only, on the @Scheduled line) — 16 real FPs in iexec-core; fixedRate phases from each instance's start time — cost if wrong: misses whole-fleet simultaneous restarts.
Task 7: review → Needs fixes (gate PASS; 4 Important FPs: WebClient injected connector, per-call timeout, method-local memo maps, S16 in-body jitter [plan-mandated window])
Ruling: S01-java-webclient-no-timeout becomes file-scoped (file_absent) — suppressed by any argument-bearing timeout/responseTimeout/ReadTimeoutHandler/CONNECT_TIMEOUT_MILLIS or a connector that is not `new X()`/`new X(HttpClient.create())` — mirrors the Batch 1 HttpClient precedent; per-call .timeout on a field-held client is idiomatic — cost if wrong: one unbounded WebClient in a file that bounds another is missed.
Ruling: S09 cache-aside and S17 require a field-declared cache (or Caffeine builder) — a method-local memo map lives one call and is single-threaded — cost if wrong: misses static caches declared without modifiers (package-private fields).
Ruling: S16 window 3 → 10 (plan-mandated value) — in-body random sleep is the standard cron remedy; a wider absent-window only suppresses — cost if wrong: jitter in the next method could suppress.
Ruling: minors — enum-keyed map → Known limitation; fix negative_explicit_eviction.java to actually remove; pre-fix TSV evidence not required (log + reviewer verification suffice).
Task 7: fix round 1/5 (4 Important + 2 minors addressed, 0 open; commits 4e69ea6..acf1c0a)
Task 7: minor (deferred): field-gate misses caches built via wrapper (`Collections.synchronizedMap(new HashMap<>())`) — undocumented; folded into Task 8 dispatch as a one-line Known limitation
Task 7: complete (commits 20d122f..acf1c0a, review clean)
Pushed feat/java-support; draft PR #13 opened at user request (Tasks 1-7).
Task 8: dispatched (base acf1c0a, implementer opus)
Task 8: implementer DONE_WITH_CONCERNS (12a1b1a): S08 2023 hits (2000 generated copies in spring-data-examples jpa/deferred); S29 0 real TP; nested for-over-getter N+1 recorded as miss
Ruling: calibration sweeps exclude generated/benchmark fixture trees (spring-data-examples jpa/deferred), documented in the log with the reason and the raw count — 2000 byte-identical generated copies are duplicated input, not a precision signal; tripwire applies to distinct code (18 hits) — cost if wrong: a detector's behaviour on generated code goes unrecorded.
Ruling: S29 must detect the canonical nested for-each over an element's association getter (`for (Author a : authors) { for (Book b : a.getBooks()) ...}`) — it is AC-10's shape; adding coverage for the pattern's defining case is not loosening-to-create-hits — cost if wrong: more S29 hits at low confidence, inspected in the re-sweep.
Task 8: review Approved, calibration gate PASS (25 hits = 25 filtered TSV lines; jpa/deferred exclusion recorded)
Ruling: Task 8 minors 1-6 carried into Task 9 (S29 handler: one var-agnostic compiled regex instead of per-loop compiles; Known-limitations lines for Allman braces, value-type prefix/getter/Dto recall losses, S08 return-type-at-line-start, cross-file FetchType.EAGER; reword CLR.java:81 TP rationale) — Task 9 edits the same log; cheap — cost if wrong: small scope growth in Task 9.
Task 8: minor (deferred): s10_retry_layers raises KeyError on a Java ctx until Task 10 adds RETRY_LAYERS["java"] (unreachable: no S10 java entry yet)
Task 8: complete (commits acf1c0a..047d51a, review clean)
Task 9: dispatched (base 047d51a, implementer opus)
Task 9: implementer DONE_WITH_CONCERNS (e3f1d60): 74→4 hits (66 FP-fixed), Kafka detectors narrowed
Ruling: S07-java-kafka and S08-java-kafka narrowed to async hand-off / auto-commit-off (S07) and blocking per-record work (S08) is accepted as meeting AC-12 — the synchronous auto-commit poll loop is at-least-once (Kafka javadoc's correct usage), so AC-12's "silent on correct usage" requires silence; positive remains a poll loop with no manual commit — cost if wrong: misses sync auto-commit loops whose processing has side effects outside the consumer (duplicates on rebalance).
Task 9: review → Needs fixes (gate PASS; 1 Important: S07-kafka hand-off signal file-scoped → FP on javadoc KafkaConsumerRunner thread)
Ruling: S07-kafka hand-off must take the polled records (`(submit|execute|runAsync|supplyAsync)\s*\([^;]*\brecords?\b` or equivalent), dropping bare `new Thread(`/`.submit(` — starting the poll loop on its own thread is the normal raw-client pattern — cost if wrong: misses hand-offs of records renamed (e.g. `batch`).
Ruling: Task 9 minors folded into the fix round: reclassify the 4 artemis `ignored0` catches as TP lost to name suppression (S19 FP-fixed 10→6); report wording "superset" for the S29 refactor; poll arg regex tolerate nested commas and not span newlines (`[^;\n]*` style); document S19 exact-name suppression.
Task 9: fix round 1/5 (1 Important + 4 minors addressed, 0 open; commits e3f1d60..2cf5fec)
Task 9: complete (commits 047d51a..2cf5fec, review clean)
Task 10: dispatched (base 2cf5fec, implementer opus)
Task 10: implementer DONE_WITH_CONCERNS (983adff): 70→7 final hits; S11 tripwire hit then tightened; S10 per-method for Java
Ruling: S11 exempts files with `main` and gRPC service impls — S11's failure mode is deadline propagation across hops (grpc-java propagates inbound deadlines via Context); a CLI client with no deadline is a missing-timeout (S01) concern, recorded as a known limitation — cost if wrong: misses deadline-less blocking stubs in CLI tools.
Ruling: S12 at exactly 1/2 FP-accepted stays (protocol defers only when MORE than half) — cost if wrong: one noisy low-confidence detector.
Task 10: review → Needs fixes (gate PASS; Important: S15 absent regex catastrophic backtracking [65s on a 60-stmt catch]; S15 FP on @Recover fallback [plan-mandated gap])
Ruling: add a branch-wide guard test — every Java detector runs over a synthetic pathological file (long catch bodies, many loops/methods, long lines) within a time budget — the plugin must not exhibit the stalls it hunts, and per-regex timing was only caught by probing — cost if wrong: a slow CI test (budgeted small).
Ruling: Task 10 minors folded into the fix round: METHOD_JAVA allow `=` inside parameter parens + document remaining owner-split cases; append S10 recall shapes to positive.java and a SPRING_CONFIG-pinning negative; S15 absent += CircuitBreakerFactory; Known limitations for webClientBuilder.build() chain and other-file deadline interceptor.
Task 10: fix round 1/5 (2 Important + 5 minors addressed, 0 open; commits 983adff..a96bf5d)
Task 10: complete (commits 2cf5fec..a96bf5d, review clean)
Task 11: dispatched (base a96bf5d, implementer opus)
Ruling: S01-java-jms-receive-no-timeout window_before widened until the 8 confirmed artemis TPs are caught (inspect any new hits; tripwire applies) — capturing inspected real TPs is not loosening-to-create-hits (same as the Task 6 SLEEP_RES ruling) — cost if wrong: receive() on a non-JMS type in a JMS-heavy file fires at low confidence.
Task 11: review → Needs fixes (gate PASS; Important: S18 FP on response checks after the call; S06 pass-through FP on field/local runnables + static-import second pool — all 4 real-world S06 lines are this class)
Ruling: S18 ignores validation lines that reference the variable assigned on the call line or read getBody()/.body()/statusCode; S06 pass-through only for a method parameter typed Runnable/Callable/Supplier, bare newXxxPool( counts as a second pool — both are FP classes on common correct code — cost if wrong: misses input validation that happens to reuse the response variable / submits of non-parameter tasks.
Ruling: add a committed unit test pinning s18_fail_fast on one TS and one Python snippet (AC-16 guard; S18 is Tier B so no samples existed) — cost if wrong: one small test.
Ruling: Task 11 minors: balanced-paren queue arg for S07/S14 basicConsume; JmsTemplate.receive() recorded as Known limitation (recall); S01 50-line non-JMS receive already documented; S06/S13 overlap parked (cosmetic duplicate leads on one file).
Task 11: parked — S06/S13 duplicate leads on a single-pool file — Ruling: cosmetic; the investigator dedupes per file — cost if wrong: one extra lead.
Task 11: fix round 1/5 (2 Important + 3 minors addressed, 0 open; commits 3f7d183..a22423e)
Task 11: minor (deferred): S18 derived-var not cleared on reassignment; S06 single static-import pool suppressed — both misses; documented in Task 12
Task 11: complete (commits a96bf5d..a22423e, review clean)
Task 12: dispatched (base a22423e, implementer sonnet)
Task 12: complete (commits a22423e..1e63a2d, review clean) — 428 passed/0 failed; plugin validate passed; 0.3.0 enabled
Final review: dispatched (base 28bce22 merge-base, head 1e63a2d, opus)
Final review: Ready after fixes — I-1 S01 httprequest FP on protobuf HttpRequest; I-2 S02 backoff FP on simulated latency near @Retry; I-3 cross-batch hits never inspected, 6/8 medium detectors rest on 0 TPs; I-4 spec §2/§4 stale
Ruling: final fix wave adds "Batch 6 — cross-batch HEAD sweep" (all Java patterns × all 18 clones, same scope filters): every hit of every medium detector inspected; a medium detector ends with ≥1 inspected TP and no unfixed FP, else it is demoted to low; low detectors get per-repo counts, tripwire enforced, up to 10 hits each judged — confidence must rest on evidence (spec §5) — cost if wrong: several detectors end low and weigh less in ranking.
Ruling: I-1 fixed with qualified-name lookbehind + protobuf setter absent + negative sample; I-4 spec §2/§4 brought in line with code.
Ruling: minors — S28 `synchronized` in string literals and S14 nested generics → Known limitations; duplicated look-back helper, PAGE_ADVANCE_JAVA readability, S10 long-line speed gap (shared TS shape) → parked; Java test-source-set filtering, thinner Java bundles, `_run_module` exception guard, pre-existing FUNC_TS quadratic → follow-up tickets for the user (out of this ticket's scope / AC-16 / shared code).
Final review: parked — _prev_nonblank dedupe, PAGE_ADVANCE_JAVA split, S10 27KB-line 1.5s — Ruling: maintainability/negligible impact; fix opportunistically — cost if wrong: minor tech debt.
Final fix wave: dispatched (base 1e63a2d, opus)
Final fix wave: DONE_WITH_CONCERNS (25605c6, b8e4200, ba6c5f9): 436 passed/0 failed; medium kept 4, demoted 4 (S02-backoff, S03-429, both S14)
Ruling: do NOT defer the five low detectors that are >1/2 FP-accepted in the Batch 6 whole-grpc cross-check (S06 2/2, S09 cache-aside 3/3, S17 1/1, S27 2/2, S28 monitor 4/4) — step 4's deferral is a per-batch rule over each batch's chosen corpus; these are 1–4 hits each in library internals previously scoped out; deferring S27's only detector would break AC-3/AC-4 — cost if wrong: five low-confidence detectors emit noisy leads; flagged to the user as an open risk.
Final re-review: dispatched (fix range 1e63a2d..ba6c5f9, sonnet)
Final re-review: clean (436 passed/0 failed); fix wave complete
