# Detector and boundary leads that hold up on library code: design

**Requirements:** [#58](https://github.com/tomstagl/thunderstruck/issues/58), part of [#54](https://github.com/tomstagl/thunderstruck/issues/54). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-10-03-library-leads.md`.
**Evidence:** `docs/calibration/correctness/celery/` (#53): `verdicts.json` (`detector_leads` per finding, and the bundle observations in `notes`) and `scan/bundles/`.
**Follows:** #19, `docs/superpowers/specs/2026-09-24-lead-precision-and-coverage-design.md`, which made leads trustworthy on service code. Its rules (comments blanked before matching, a negative sample for every reproduced false positive, a calibration log behind every confidence) apply here unchanged.

Every figure below was measured, not estimated. The benchmark scan was reproduced byte for byte: `signals.py --top 10 --since 2025-10-03` and `bundle.py` on main at `3e7bd55`, run over a copy of celery/celery at `508c1129269d2b1baffc516d8f5c05da06273ef0`, write the ten bundles in `scan/bundles/` exactly. Every proposed rule was then prototyped on a scratch copy of this repository and run over the same Celery copy, the test fixture, spring-petclinic and the full detector sample suite (396 samples, all passing).

## 1. Architecture

No stage changes shape. Two things move into the catalog, and the report changes words.

```
catalog/stability.yaml
  patterns[].detectors[]   + absent_before / absent_before_window   (§3.1)
                           S04-py, S19-py, S07-py corrected          (§3.2)
  boundaries:              NEW · per language, call-shaped rules     (§2)

scripts/detectors/__init__.py
  _run_regex, _run_file_absent   honour absent_before
  find_boundaries()              NEW · the only boundary matcher

scripts/bundle.py
  BOUNDARY_PATTERNS              removed
  section_boundaries()           calls find_boundaries(); says when a language has no rules

scripts/report.py, templates/report.html
  "Pattern coverage"             reworded as "Detector leads by pattern" (§4)

docs/calibration/celery.md       NEW · every detector hit at the benchmark commit, judged (§5)
```

The governing rule holds: everything here is deterministic, and bundles stay byte-identical across runs on an unchanged repository. Bundle *content* changes once, for every repository, because the boundaries section changes (§6).

## 2. Boundaries

### 2.1 What goes wrong today

`bundle.py` matches seven language-agnostic regexes (`BOUNDARY_PATTERNS`) against every raw line that does not start with `#`, `//` or `*`. They are vocabularies, not calls: `\brequests\s*\.` is any attribute of anything named `requests`, `celery` is any line naming the package, `schedule` is any identifier containing the word, `got` is the English word inside an f-string, and nothing stops a docstring line or an import. On the ten Celery bundles:

| | Lines shown | From a comment, docstring or import | A real call through a boundary |
|---|---|---|---|
| Today | 68 | 51 | 4 (`pipe.execute()` in `redis.py`) |

The other 13 are identifiers and strings: `requests.pop(r.id, None)` (a worker-state dict), `scheduled_requests.clear()`, `def execute(self, …)`, `def add_periodic_task(…)`, `f"Instead got: {exc}"`. On the fixture, 20 lines are shown; the wrong ones are `fetchRelease(` matched as `fetch`, `setTimeout` sleeps in retry loops shown as a scheduler, and a JSDoc line.

### 2.2 The rule

A boundary is a **call**: a line where the code invokes a client library, or a method whose name only a boundary client has. Two kinds of rule, and the difference is the whole design:

- **Through a library name** (`requests.get(`, `axios.post(`, `boto3.client(`, `task.delay(`): counts only when the file imports that library (`require`). A variable that happens to share the library's name (`requests.pop(…)` on a dict, AC-2) never matches twice over: the rule names the library's own verbs (`get`, `post`, …, never `pop`), and it runs only in a file that imports `requests`, which Celery's consumer does not. In Java every type is imported, so every Java rule that names a client is gated this way; the one ungated Java rule is upper-case SQL text, which names no library (it is a string, whichever client sends it).
- **A boundary-shaped method on any receiver** (`.execute(`, `session.query(`, `.publish(`, `.drain_events(`, `.chat.completions.create(`, a Prisma-shaped `db.<model>.findMany(`): no import gate, because service code reaches these through an injected client (`self.client`, `this.prisma`, a `broker` passed in) whose file imports nothing recognisable. These method names are rare outside boundary clients; generic ones (`.get(`, `.send(`, `.create(`, `.add(`) are never in this kind.

Then, for both kinds:

- Rules match the comment-stripped text from `_common.strip_comments`, the same text detectors see: comments and Python docstrings are blank, string contents are kept (raw SQL in a string is a database boundary).
- A line that is an import statement is never a boundary (`import …`, `from x import …`, `export … from '…'`), whatever a rule says.
- A definition is not a call: Python rules for bare names carry `(?<!def )`, TypeScript `fetch` excludes `function fetch(` and `async fetch(` and any `.fetch(` or `xfetch(`.
- One label per line: the first rule in catalog order that matches.
- SQL keywords match upper case only (`SELECT … FROM`, `INSERT INTO`, `UPDATE x SET`, `DELETE FROM`), so prose such as "Select a subset of queues" is not a query.
- `setTimeout` is no longer a scheduler. In the code this tool reads it is almost always a sleep inside a retry loop, which S02 already reports. `setInterval`, `cron.schedule`, `CronJob`, `@Cron`, `@Interval`, `@Scheduled`, APScheduler, `schedule.every`, `threading.Timer` and `call_later` remain.

### 2.3 Catalog schema

```yaml
boundaries:
  python:
    - id: B-py-requests
      label: HTTP
      pattern: '\b(?:requests|httpx)\s*\.\s*(?:get|post|put|patch|delete|head|options|request|stream)\s*\('
      require: '^\s*(?:import|from)\s+(?:requests|httpx)\b'
    - id: B-py-execute
      label: database
      pattern: '\.\s*(?:execute|executemany|executescript)\s*\('
  typescript: [...]
  java: [...]
```

| Field | Meaning |
|---|---|
| `id` | Unique across all languages; `B-<lang>-<what>`. Named in test failures, never in a bundle. |
| `label` | One of `HTTP`, `database`, `queue/messaging`, `LLM`, `cloud SDK`, `filesystem`, `scheduler`: today's labels, so the investigator's vocabulary does not change. |
| `pattern` | Matched per line of comment-stripped text. |
| `require` | Optional. Compiled `MULTILINE` and searched in the comment-stripped file; the rule is skipped when it matches nowhere, exactly as `require` on a detector. |

Language resolution uses `_common.detector_language`, so `javascript` uses the `typescript` rules as detectors do. `yaml` and `properties` have no rules: configuration declares boundaries, it does not call them.

The rules per language (exact regexes are in the plan's Task 5; every one was run in the prototype):

| Label | Python | TypeScript / JavaScript | Java (import-gated, except SQL text) |
|---|---|---|---|
| HTTP | `requests`/`httpx` verb calls, `urlopen(`, `aiohttp.ClientSession(`; each gated on its import | global `fetch(`; `axios`, `got`, `superagent`, `ky`, `undici`, `http(s).get/request` gated on their import | `RestTemplate`/`WebClient` verbs, `newCall(`, `httpClient.send(` |
| database | `.execute(`/`.executemany(`/`.executescript(`; `…session.query/scalars/commit/flush/add/add_all/merge(`; Django `.objects.<x>(` gated on `django`; upper-case SQL | `db`/`prisma`/`tx` `.<model>.<prisma verb>(`, `$queryRaw`/`$executeRaw`, `.query(`; upper-case SQL | JDBC/JPA/jOOQ verbs gated on `java.sql`, `jakarta.persistence`, `org.springframework.jdbc`, …; upper-case SQL |
| queue/messaging | `.publish(`, `.basic_publish/consume/get(`, `.drain_events(`, `.send_message(s)(`, `.receive_message(`; Celery `.apply_async/send_task/delay(` gated on `celery`, never on a receiver ending in `pool`/`Pool` | `.publish(`, `.sendMessage(`, `.sendMessageBatch(`, `new SendMessage/SendMessageBatch/PublishCommand(` | `send`/`convertAndSend`/`publish`/`basicPublish` and `@KafkaListener`-style annotations, gated on the messaging packages |
| LLM | `.chat.completions/messages/embeddings/responses.create(`, `.generate_content(` | the same, and `.generateContent(` | none |
| cloud SDK | `boto3.client/resource/Session(` gated on `import boto3` | `.send(new XCommand(` gated on `@aws-sdk/` | AWS SDK v2 `XClient.builder()` gated on `software.amazon.awssdk` |
| filesystem | builtin `open(` (not `def open(`, not `x.open(`), `Path` `read_text/write_text/read_bytes/write_bytes(` | `fs.read*/write*/append*(`, `readFile`/`writeFile`/`appendFile(Sync)(` | `Files.read*/write*/…(`, `new File{Input,Output}Stream(`, `new File{Reader,Writer}(`, gated on `java.nio.file` or `java.io` |
| scheduler | `schedule.every(`, APScheduler schedulers and `.add_job(`, `threading.Timer(`, `.call_later(`, `.add_periodic_task(` | `setInterval(`, `cron.schedule(`, `new CronJob(`, `@Cron(`, `@Interval(` | `@Scheduled`, `schedule*(` gated on `java.util.concurrent` or Spring scheduling |

`.poll(` was in the first prototype and taken out: on Celery it tagged `select.poll()` in `redis.py`. `.apply_async(` on a pool is multiprocessing, not messaging, which is the reason for the pool exclusion.

### 2.4 Matcher

`scripts/detectors/__init__.py` gains:

```python
@dataclass(frozen=True)
class Boundary:
    label: str
    rule_id: str
    line: int
    snippet: str   # the raw line, stripped, at most 120 characters

def find_boundaries(catalog: dict, rel_path: str, text: str, lang: str) -> list[Boundary] | None
```

`None` means the language has no boundary rules; `[]` means rules ran and nothing matched. It reuses `build_context` and `_rx`; a rule whose regex does not compile is skipped, as a detector's is. Hits are in line order. It lives beside the detector engine because it is the same kind of thing: a catalog rule matched against comment-stripped text.

### 2.5 In the bundle

`section_boundaries(text, rel, lang, catalog)` keeps today's headings and its cap of four lines per label, so an unchanged repository with no boundaries still renders `## External boundaries` / `None detected in this file.` It adds one sentence under the heading when lines are shown:

> Calls that match a boundary rule: a client library's call, or a method only a boundary client has. A call through a wrapper or an injected client of another name is not listed.

and, for a language with no rules:

> `## External boundaries` / Not looked for: no boundary rules exist for yaml files.

That is the degradation rule applied to the section: the investigator is told what was not looked at instead of reading "None detected" on a file nobody searched. `BOUNDARY_PATTERNS` is deleted; the catalog is the only source.

### 2.6 Measured effect

| | Celery, 10 bundles | Fixture, 10 code files |
|---|---|---|
| Lines shown, today | 68 (51 from a comment, docstring or import) | 20 |
| Lines shown, after | 27 (0 from a comment, docstring or import) | 7 |

All 27 Celery lines are calls: Celery's own `apply_async`/`delay`/`send_task` (which publish a task message), kombu `producer.publish(`, Redis `pipe.execute()`, SQLAlchemy `session.query/add/flush(`. The fixture keeps every `fetch(`, `broker.publish(` and `db.release.create(`, and loses the `setTimeout` sleeps and `fetchRelease(`. The bundles also shrink: Celery's ten go from 50,076 to 49,085 estimated tokens, with the new explanatory sentence included.

**What this costs.** A call through a wrapper (`withRetry(() => …)` around a `fetch` still matches; a project's own `api.get(` does not), through an injected client with a generic method (`self.client.get(key)`), or through a Spring Data repository method is not listed. On Celery, `consumer.py`, `app/base.py` and `worker/request.py` show no boundary at all. That is the trade the ticket makes: an empty, honest section rather than a full, false one. The detectors (S01, S05, S11, S15) keep their own anchors and are unaffected.

## 3. Detector corrections

### 3.1 Engine: `absent_before`

The three Celery false leads have one thing in common: what excuses the line is *before* it, further back than the detector's window can look without also widening what it looks for. `window_before` already exists but is shared by `absent_within` and `present_within`, so widening it changes both. Each detector may now declare:

| Key | Meaning |
|---|---|
| `absent_before` | A regex, compiled `MULTILINE`. The hit is dropped when it matches the text of the `absent_before_window` lines before the hit together with the hit's own line. |
| `absent_before_window` | Required with `absent_before`, an integer of at least 1. |

For a `regex` detector it applies to each matching line after the existing window checks. For a `file_absent` detector it applies to each anchor match in turn, and the hit lands on the first anchor it does not excuse; when it excuses every anchor, there is no hit. That second part is a small behaviour change to `_run_file_absent`, which today looks only at the first anchor, and it is what makes the S07 correction possible without making one excused insert silence a whole file. The text is the comment-stripped text unless `include_comments` is set, as for every other key. A detector without `absent_before` behaves exactly as today, which the full sample suite and the Celery sweep confirm.

### 3.2 The three shapes

| Lead (verdicts.json) | Why it is false | Correction | Celery |
|---|---|---|---|
| S04-py-bare-except-retry @ `celery/backends/base.py:773` | The `except Exception:` guards the `on_backend_retryable_error` hook inside a retry branch; the retry decision is the outer `except`, gated by `exception_safe_to_retry` ten lines up | `absent_before`: the existing retryability-predicate regex (`safe_to_retry`, `is_retryable`, `is_transient`, `should_retry` called), window 12 | silent |
| S19-py-except-pass @ `celery/worker/consumer/consumer.py:435` | Best-effort `collect()` while tearing down a connection whose failure was logged with `exc_info` six lines earlier | `absent_before`, window 8: a traceback-logging call (`exc_info=True` or `.exception(`), then a `try:` whose single body line calls a teardown verb (`close`, `collect`, `release`, `shutdown`, `cleanup`, `disconnect`, `stop`, `terminate`, `dispose`, `settimeout`), then this `except` | silent |
| S07-py-insert-without-upsert @ `celery/backends/database/__init__.py:168` | A get-or-create: the row is added only after a lookup of its key found nothing, and `task_id` is unique, so a replay updates or raises | `absent_before`, window 4: `if not X:` or `if X is None:` and then `.add(X)` of the same name | moves to line 295 |

Each shape gets a negative sample built from the Celery code, and a positive sample on the boundary the correction must not cross:

- S04: a positive is not needed beyond the existing three; every one still fires. The cost is recorded instead: a retryability predicate on an unrelated value 7 to 12 lines above a real catch-all retry now hides it. No sample, swept file or Celery line has that shape.
- S19: `positive_write_after_logged_error` (a logged warning, then a swallowed `store.save()`: not teardown, still fires) and `positive_teardown_without_log` (a swallowed `conn.close()` with nothing logged: still fires, as today).
- S07: `positive_add_unguarded` and `positive_guard_on_other_name` (`if not dry_run: session.add(event)`: the guard is on a flag, not on the row, still fires).

**S07 keeps `medium`.** After the correction, Celery's database backend still carries an S07 lead, now at line 295 (`_save_group`'s `session.add(group)`), and it is false for the reason #19's log already gave: `taskset_id` is unique in another file, which no file-local rule can see. AC-3's fallback, lowering the detector's confidence, was prototyped and rejected on evidence: at `low` the database backend drops out of the top 10 at the benchmark commit and `celery/app/utils.py` takes its place. The database backend is where FR-014, one of the five correct findings, lives, and where the largest defect the scan missed lives too (the backend does not retry at all on defaults). Lowering a detector's confidence to remove a false lead that ranks a file with real defects trades a visible false lead for an invisible miss. The new log records line 295 as `FP-accepted` with this reason. The get-or-create shape itself is corrected, which is what AC-3 asks.

### 3.3 Effect

| | Before | After |
|---|---|---|
| Leads in the ten investigated bundles | 5, 2 true (S19@489, S19@240) | 3, 2 true (S07@295 false) |
| All detector hits in Celery at the commit (`calibrate.py --lang all --patterns all`) | 27, 6 true | 25, 6 true |
| Hotspots | the ten in `scan/` | the same ten files; `amqp.py`/`backends/base.py` and `database/__init__.py`/`consumer.py` swap ranks, so H04/H05 and H07/H08 swap ids |

The repository-wide figure barely moves, and §5 says why: Celery's remaining false hits are capability probes, pickling tests, unique constraints elsewhere and a singleton beat, each already explained in `docs/calibration/python.md`, and each a shape a file-local rule cannot tell apart. Lead precision is defined here as true leads over leads, in the ten investigated bundles; that is the figure AC-6 asks the PR to report, with the repository-wide one beside it.

## 4. The coverage section

Today it is headed **Pattern coverage**, a word that reads as "these patterns are covered". On library code that is doubly wrong: no lead is read as the pattern being present, and a lead or a finding on a configurable default (Celery's `redis_socket_connect_timeout` defaults to `None`) reads as the library missing a pattern its caller is meant to choose.

The table, its columns and the JSON keys (`pattern_coverage`, `coverage_rows`) stay; the words change, the same for every repository (ticket, product decision):

- Heading: **Detector leads by pattern**.
- Intro: *Each row is a stability pattern the detectors searched for. A lead is a line where a detector's text rule matched: a place to read, never a finding, and never proof that the pattern is missing. Where code leaves a setting to its caller, as a library's configurable timeout does, a lead describes the default the code ships with, not every deployment. Leads read counts the leads inside investigated hotspots; leads confirmed counts those a validated finding cites.*
- Footnote: *No lead means no line matched a detector's rule. It does not mean the pattern is present: a detector sees only the shapes its rule describes.*

The three strings are constants in `report.py`. `templates/report.html` carries the same text, and a test asserts each constant appears verbatim in the template, so the two cannot drift. The Overview rail's "Run, coverage, hotspots, and what was not analysed" becomes "Run, leads, hotspots, and what was not analysed". No reader-facing text in either report uses "coverage" for this table; *Not scanned* keeps its own wording, which is about files, not patterns.

JSON keys are not renamed: `report.json` consumers (the HTML report, `report-format.md`, anyone scripting against it) would break for a word nobody reads there.

## 5. The Celery calibration log

`docs/calibration/celery.md`, in the form of `python.md`: repository, kind (library and worker), commit, files swept; one table per detector with Hits, TP, FP-fixed, FP-accepted, Surfaced, Lost and Final; every hit listed with its judgment; a **Fixed during calibration** section naming each sample; **Silences checked**; **Known limitations**. Judgments come from the executed review where it judged the lead (`verdicts.json`), and otherwise from `python.md`'s judgment of the same code at its earlier Celery commit (`eb3dfa3`), re-checked against the code at `508c112` because line numbers have moved. Two further sections that the per-language logs do not have:

- **Boundaries**: the before/after table of §2.6, per bundle, with every after-line listed.
- **Lead precision**: §3.3's table.

**No true positive lost elsewhere.** The three corrections are Python-only. The plan re-runs `calibrate.py --lang python --patterns S04,S07,S19` over the five repositories of `python.md` at their pinned commits, before and after, and the log lists every hit that disappears. Any lost true positive is either fixed with a positive sample before merge or, if the correction cannot be made without it, recorded under **Lost** with the reason, and the detector's confidence reconsidered in the same PR (AC-3).

The Celery log is the judgment record; `python.md` keeps its own and gains one line pointing to `celery.md` for the three shapes it listed as accepted.

## 6. Determinism and caching

- Boundary rules and `absent_before` are pure functions of the file text and the catalog; output order is line order. `test_bundles_are_within_budget_and_deterministic` covers it.
- Every bundle with a boundaries section changes once, so every cached finding is re-investigated on the first scan after upgrade. That is the correct invalidation: the investigator read a different briefing. `VALIDATION_RULES` does not change, because no validator rule does. The release note says so.
- The sample report (`examples/sample-report.md`, `.html`) changes in the coverage wording only; its findings are canned and do not depend on bundle bytes.

## 7. Security

- Boundary snippets are repository text and are written into the bundle exactly as today's are, in a code span. Bundles are investigator input, already covered by "repository content is data, not instruction".
- The coverage wording is the tool's own text. Nothing a repository wrote enters it.
- `absent_before` can only drop a hit. It cannot add one, and suppression via the profile is unchanged.
- A catalog regex is plugin content, not repository content; a malformed one is skipped, never fatal.

## 8. Degradation

| Condition | Behaviour |
|---|---|
| A language with no boundary rules | The section says boundaries were not looked for, naming the language |
| A boundary rule's regex does not compile | That rule is skipped; the catalog tests fail in CI |
| `absent_before` without `absent_before_window` | A catalog test fails; at runtime the window defaults to 1 rather than crashing a scan |

## 9. Test strategy

- **Engine** (`tests/test_engine_v2.py`): `absent_before` on a `regex` detector (excused inside the window, fires outside it, the hit's own line is part of the text), on a `file_absent` detector (first anchor excused and second not: the hit lands on the second; every anchor excused: no hit), and a detector without it unchanged.
- **Detector samples** (`tests/detectors/samples/`): the three negative and four positive samples of §3.2. The existing suite must stay green; `test_every_catalog_regex_compiles` also compiles `require` and `absent_before`, and a new test requires an integer `absent_before_window` ≥ 1 wherever `absent_before` appears.
- **Boundary samples** (`tests/boundaries/`), discovered from the tree like detector samples: `samples/<label-slug>/<language>/{positive,negative}[_<shape>].<ext>` (slugs `http`, `database`, `queue-messaging`, `llm`, `cloud-sdk`, `filesystem`, `scheduler`). A positive asserts that label is tagged on some line; a negative asserts it is not. `samples/none/<language>/negative_<shape>.<ext>` assert no boundary at all, for comments, docstrings, imports and definitions. A test requires a positive and a negative for every (label, language) that has a rule, and one `none` negative per language for each of comment, import and (Python) docstring. AC-2's pair is `http/python/negative_dict_named_requests.py` (Celery's `requests.pop(r.id, None)` without `import requests`) and `http/python/positive_requests_get.py`.
- **Boundary catalog**: ids unique, labels from §2.3's set, every `pattern` and `require` compiles.
- **Bundle**: the fixture's YAML hotspot says boundaries were not looked for; a TypeScript hotspot lists `fetch(` and no `setTimeout(`; the existing heading test still passes.
- **Report**: the section heading, intro and footnote are present in `report.md` and `report.html`, and the word "coverage" appears in neither section; the constants appear verbatim in the template. The existing coverage-table tests follow the new heading.
- **Celery** is not in CI. The figures of §2.6 and §3.3 are produced by the plan's scratch procedure and recorded in the log and the PR.

## 10. Consumption

No model call is added. The investigator reads slightly less: Celery's ten bundles shrink by about 1,000 estimated tokens in total (50,076 to 49,085).

## 11. Decisions

- **Boundary rules in the catalog, not in `bundle.py`.** They need negative samples (AC-2) and calibration like detectors, and CLAUDE.md makes the catalog the source of truth for anything matched against code. A correction becomes a catalog edit plus a sample.
- **Import-gate calls through a library name; leave boundary-shaped methods ungated.** Gating everything on imports was prototyped first. It removed every false line on Celery, and also `broker.publish(` and `db.release.create(` from the fixture, which are the injected-client shapes services use. Gating only where the receiver is the library's own name is what AC-2 needs and loses neither.
- **Per-language rules.** The language-agnostic list is why `got` (a Node library) matched Python f-strings.
- **`setTimeout` is not a scheduler.** In the fixture and in the TypeScript samples every one is a sleep, and S02 reports sleeps.
- **`absent_before`, a separate window, rather than a wider `window_before`.** Widening the shared window to reach `base.py:763` would also widen what S04's `present_within` accepts as retry vocabulary, the very look-behind `python.md` already records as its main source of false hits.
- **S04 by predicate reach, not by "an `except` nested in another handler is never the retry decision".** The nesting rule is closer to the reviewer's words but silences a real retry loop written inside a handler (`except Exception: for attempt in range(3): try: reconnect() except Exception: sleep(1)`); the predicate rule silences only code that visibly discriminates.
- **S19 needs both the logged traceback and the teardown verb.** Either alone silences true positives: a swallowed write after an unrelated warning, or a swallowed `close()` that hides a real failure with nothing logged (`positive_teardown_without_log`).
- **S07 keeps `medium`** (§3.2): the evidence is that lowering it drops a file with real defects out of the investigated set.
- **Reword the coverage section rather than detect libraries.** A product decision (ticket). The new wording is true for a service too: a lead is never proof a pattern is missing, anywhere.
- **Keep the JSON keys.** Renaming them buys nothing a reader sees and breaks every consumer.

## 12. Open design questions

- Should the boundary section list the calls a detector already anchors on (S01's `requests.get(url)` without a timeout) even when the file reaches them through a wrapper? That needs cross-file resolution, which the matcher deliberately does not do.
- `B-py-execute` is ungated and labels a Redis pipeline's `.execute()` as `database`. A `cache/key-value` label would be more exact; it is left until a repository shows the investigator misreading it.
