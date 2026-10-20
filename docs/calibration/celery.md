# Celery detector and boundary calibration

Celery is a library and a worker: much of what a stability pattern asks for is
left to the caller as a setting. This log judges every detector hit and every
boundary line at the commit of the correctness benchmark (#53), so that lead
precision on library code rests on evidence, and it records the corrections
made for #58. Judgments come from the executed review where it judged the lead
(`correctness/celery/verdicts.json`, `detector_leads`) and otherwise from
`python.md`'s judgment of the same code at Celery `eb3dfa3`, re-checked here.
Column meanings are `python.md`'s.

| Repo | Kind | Commit | Python files swept |
|---|---|---|---|
| celery/celery | library and worker | `508c1129269d2b1baffc516d8f5c05da06273ef0` | 250 |

Both sweeps ran `scripts/calibrate.py --lang all --patterns all` over the same
checkout: the first at `main` before #58 (27 hits), the final with #58's
corrections (25 hits). Every hit is Python.

## Detectors

| Detector | Hits | TP | FP-fixed | FP-accepted | Surfaced | Lost | Final |
|---|---|---|---|---|---|---|---|
| S01-py-requests-no-timeout | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| S02-py-backoff | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| S04-py-bare-except-retry | 2 | 1 | 1 | 0 | 0 | 0 | 1 |
| S05-py-http-without-limiter | 1 | 0 | 0 | 1 | 0 | 0 | 1 |
| S06-py-single-queue-no-priority | 2 | 0 | 0 | 2 | 0 | 0 | 2 |
| S07-py-insert-without-upsert | 2 | 0 | 1 | 2 | 1 | 0 | 2 |
| S09-py-cache-aside-no-singleflight | 2 | 0 | 0 | 2 | 0 | 0 | 2 |
| S10-py-boto3-default-retries | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| S11-py-no-deadline-propagation | 3 | 0 | 0 | 3 | 0 | 0 | 3 |
| S13-py-shared-pool | 1 | 0 | 0 | 1 | 0 | 0 | 1 |
| S16-py-fixed-cron | 1 | 0 | 0 | 1 | 0 | 0 | 1 |
| S17-py-cache-without-ttl | 1 | 0 | 0 | 1 | 0 | 0 | 1 |
| S19-py-except-pass | 9 | 2 | 1 | 6 | 0 | 0 | 8 |
| **Total** | **27** | **6** | **3** | **19** | **1** | **0** | **25** |

S07's surfaced hit is `celery/backends/database/__init__.py:295`: the file's
`file_absent` lead moves there once the get-or-create at `:168` is excused.
It is a different statement (`_save_group`, not `_store_result`), so it is
counted as surfaced rather than as the same lead moved.

### Hits

#### S01-py-requests-no-timeout

- celery `examples/gevent/tasks.py:10` — TP (example code): `requests.get(url)` with no timeout. A hung site holds a worker greenlet forever, and users copy examples.

#### S02-py-backoff

- celery `celery/backends/asynchronous.py:152` — TP: after a connection error in `drain_events` the drainer waits a constant `time.sleep(1)` and retries, so every client reconnects on the same 1 s beat after a broker blip.

#### S04-py-bare-except-retry

- celery `celery/app/builtins.py:71` — TP: `chord_unlock` catches `Exception` from `deps.ready()` and `raise self.retry(exc=exc, …)`, with `max_retries=None` by default, so a permanent failure is retried forever.

#### S05-py-http-without-limiter

- celery `celery/backends/gcs.py:109` — FP-accepted: `mget` fans out through `ThreadPoolExecutor().map`, whose default worker count already bounds concurrency.

#### S06-py-single-queue-no-priority

- celery `celery/concurrency/thread.py:39` — FP-accepted: the thread pool's execution backend. Prioritisation is per-queue workers and broker priorities, not inside this executor.
- celery `examples/eventlet/bulk_task_producer.py:65` — FP-accepted: every item in the example producer's `LightQueue` is the same kind of work.

#### S07-py-insert-without-upsert

- celery `celery/backends/cassandra.py:40` — FP-accepted: a CQL `INSERT` is an upsert by primary key (`task_id`).
- celery `celery/backends/database/__init__.py:295` — FP-accepted (surfaced): `_save_group` adds a `TaskSet` whose `taskset_id` is `unique=True` in `celery/backends/database/models.py:109`, so a replay raises rather than duplicating the row. A file-local rule cannot see the constraint in another file.

#### S09-py-cache-aside-no-singleflight

- celery `celery/backends/cache.py:63` — FP-accepted: `DummyClient.get` is the in-memory stand-in for a memcached client; it is the cache, not a cache-aside.
- celery `celery/utils/dispatch/signal.py:275` — FP-accepted: `sender_receivers_cache` memoises a cheap in-process computation with no dependency behind it.

#### S10-py-boto3-default-retries

- celery `celery/backends/dynamodb.py:183` — TP (`score: false`, the retry-layer inventory): `boto3.client('dynamodb', …)` with no `Config(retries=…)`, so botocore's default retries are a layer nobody wrote.

#### S11-py-no-deadline-propagation

- celery `examples/eventlet/tasks.py:10`, `examples/eventlet/webcrawler.py:54`, `examples/gevent/tasks.py:10` — FP-accepted: background tasks have no caller deadline to propagate.

#### S13-py-shared-pool

- celery `celery/concurrency/thread.py:39` — FP-accepted: in a worker every workload is background work, and bulkheads between queues are separate workers.

#### S16-py-fixed-cron

- celery `celery/beat.py:281` — FP-accepted: the built-in `backend_cleanup` entry, `crontab('0', '4', '*')`. `celery beat` is a singleton per deployment, so no herd of instances forms. (`python.md` lists it at `:275`.)

#### S17-py-cache-without-ttl

- celery `celery/utils/time.py:76` — FP-accepted: `_offset_cache` is keyed by UTC offset, bounded by the number of distinct offsets.

#### S19-py-except-pass

- celery `celery/backends/base.py:489` — TP: a group task's errback that raises is swallowed inside the loop with no trace (the executed review judged it a true lead, FR-009; `python.md` lists it at `:473`). Sample: `S19/python/positive_errback_loop.py`.
- celery `celery/backends/database/__init__.py:240` — TP: a stored stamps value that fails to decode is dropped with no trace (executed review, FR-014: real, low impact). Sample: `S19/python/positive_decode_swallow.py`.
- celery `celery/events/cursesmon.py:170` — FP-accepted: `getkey()` raises when no key is pressed; this is a poll.
- celery `celery/platforms.py:554` — FP-accepted: a `sysconf` capability probe.
- celery `celery/utils/serialization.py:63`, `:165` — FP-accepted: probing whether an exception pickles; the exception is the answer.
- celery `celery/utils/threads.py:93`, `:95` — FP-accepted: best-effort `settimeout` on broker sockets while tearing down. No traceback is logged in the eight lines before either, so the S19 correction (which needs one) leaves them.

### Fixed during calibration

Each fix was preceded by a `negative_<shape>.py` sample built from the Celery
code that fired, and is a catalog `absent_before` with its own window.

- `S04-py-bare-except-retry` `celery/backends/base.py:773` → `S04/python/negative_hook_in_retry_branch.py`. The `except Exception:` guards the `on_backend_retryable_error` hook inside a branch already gated by `exception_safe_to_retry` (executed review, FR-007: false lead).
- `S19-py-except-pass` `celery/worker/consumer/consumer.py:435` → `S19/python/negative_teardown_after_logged_error.py`. A swallowed `connection.collect()` while tearing down a connection whose failure was logged with `exc_info` a few lines earlier (executed review, FR-013: false lead). Guards: `positive_write_after_logged_error.py`, `positive_teardown_without_log.py`.
- `S07-py-insert-without-upsert` `celery/backends/database/__init__.py:168` → `S07/python/negative_get_or_create.py`; the file's lead moves to `:295` (Surfaced, FP-accepted). A get-or-create on the unique `task_id` (executed review, FR-014: false lead). Guards: `positive_add_unguarded.py`, `positive_guard_on_other_name.py`.

### Silences checked

`calibrate.py --lang python --patterns S04,S07,S19` over the five repositories
of `python.md`, at their pinned commits, before and after #58:

| Repo | Commit | Hits before | Hits after | Disappeared |
|---|---|---|---|---|
| fastapi/full-stack-fastapi-template | `cb740b6` | 4 | 4 | none |
| netbox-community/netbox | `785d0b9` | 4 | 4 | none |
| httpie/cli | `5b604c3` | 2 | 2 | none |
| celery/celery | `eb3dfa3` | 13 | 11 | the three shapes below |
| rq/rq | `90a67a1` | 9 | 9 | none |

At Celery `eb3dfa3` the three hits that disappear are the shapes corrected
here, each judged FP-accepted in `python.md`: S04 `celery/backends/base.py:757`,
S19 `celery/worker/consumer/consumer.py:427`, and S07
`celery/backends/database/__init__.py:168` (whose lead moves to `:295`). No
true positive is lost in any of the five.

### Known limitations

- S07 at `:295`: `taskset_id` is unique in `models.py`, which a file-local rule cannot see. Lowering the detector to `low` drops the database backend out of the top 10 at this commit (spec §3.2), so it stays `medium`.
- S04: a retryability predicate on an unrelated value 7–12 lines above a real catch-all retry now hides it. No sample, swept file or Celery line has that shape.
- S19: best-effort teardown with nothing logged before it (`celery/utils/threads.py:93`, `:95`) still fires. Silencing it would also silence `positive_teardown_without_log.py`, a swallowed `close()` that hides a real failure.

## Boundaries

Lines in each bundle's *External boundaries* section, for
`signals.py --top 10 --since 2025-10-03` and `bundle.py` over the checkout
above. "Before" is the frozen benchmark scan
(`correctness/celery/scan/bundles/`, which `main` before #58 reproduces
exactly); "after" is #58. "Noise" is a line from a comment, a docstring or an
import.

| File | Before: shown | Before: noise | After: shown | After: noise |
|---|---|---|---|---|
| `celery/canvas.py` | 5 | 5 | 0 | 0 |
| `celery/backends/redis.py` | 8 | 4 | 5 | 0 |
| `celery/app/base.py` | 9 | 6 | 0 | 0 |
| `celery/backends/base.py` | 8 | 6 | 0 | 0 |
| `celery/app/amqp.py` | 5 | 5 | 2 | 0 |
| `celery/worker/request.py` | 6 | 4 | 0 | 0 |
| `celery/worker/consumer/consumer.py` | 10 | 5 | 0 | 0 |
| `celery/backends/database/__init__.py` | 9 | 8 | 4 | 0 |
| `celery/app/task.py` | 4 | 4 | 0 | 0 |
| `celery/app/trace.py` | 4 | 4 | 0 | 0 |
| **Total** | **68** | **51** | **11** | **0** |

`hotspots.json`'s `own_packages` after #58 is
`{"python": ["celery", "t"], "typescript": [], "java": []}`.

Every line shown after #58, each a real call across a boundary:

- `celery/backends/redis.py:712` — queue/messaging — `pipe.publish(key, value)`: a Redis PUBLISH.
- `celery/backends/redis.py:713`, `:794`, `:834`, `:851` — database — `pipe.execute()` / `pipeline.execute()`: a Redis pipeline round trip (labelled `database`; spec §12).
- `celery/app/amqp.py:570` — queue/messaging — `producer.publish(`: kombu publishes the task message.
- `celery/app/amqp.py:608` — queue/messaging — `evd.publish('task-sent', …)`: Celery's own `EventDispatcher.publish`, which publishes through kombu (spec §12).
- `celery/backends/database/__init__.py:143`, `:153` — database — `session.query(…)`: SQLAlchemy reads.
- `celery/backends/database/__init__.py:168`, `:169` — database — `session.add(task)`, `session.flush()`: SQLAlchemy writes.

Bundle size, the ten bundles' `tokens_estimated` from `index.json`:

| Code | Total |
|---|---|
| Frozen benchmark scan (`main` at `3e7bd55`) | 50,076 |
| `main` before #58 (`ddbffa0`), same checkout | 52,950 |
| #58 | 51,511 |

The drop from #58 is 1,439 tokens, the figure spec §2.6 gives. The absolute
totals differ from the spec's because bundle content has grown on `main`
since `3e7bd55`.

The hotspots are the same ten files. Two pairs swap ranks, as spec §3.3
predicts: `celery/backends/base.py` and `celery/app/amqp.py` (H04 ↔ H05), and
`celery/worker/consumer/consumer.py` and
`celery/backends/database/__init__.py` (H07 ↔ H08).

## Lead precision

Lead precision is true leads over leads.

| | Before | After |
|---|---|---|
| Leads in the ten investigated bundles | 5, 2 true (40%) | 3, 2 true (67%) |
| All detector hits at the commit | 27, 6 true (22%) | 25, 6 true (24%) |

The bundle leads before: S04@`base.py:773` (false), S19@`base.py:489` (true),
S19@`consumer.py:435` (false), S07@`database/__init__.py:168` (false),
S19@`database/__init__.py:240` (true). After: S19@`base.py:489`,
S19@`database/__init__.py:240` and S07@`database/__init__.py:295` (false,
see Known limitations). The repository-wide figure barely moves: the
remaining false hits are capability probes, pickling probes, unique
constraints in another file and a singleton beat, each a shape a file-local
rule cannot tell apart.
