# Python detector calibration

Synthetic samples prove that a detector's regex matches what it was written
for. They do not prove it behaves on code nobody wrote for the test.
Calibration closes that gap: every Python detector is swept with
`scripts/calibrate.py` over every tracked, non-test Python file of several
real public repositories. Every hit is inspected by hand and judged against
the pattern's `failure_if_absent`, and each false positive either tightens the
detector (with a `negative_<shape>.py` sample reproducing the real-world
shape) or is recorded with a reason. This log is what a Python detector's
`confidence` rests on, and it satisfies AC-18 of #19 for Python. The protocol
and the log format follow [the Java log](java.md).

Column meanings: **Hits** counts every hit a detector produced across the
repositories in the first sweep, before any fix. **Final** counts the hits in
the final sweep, the one listed under **Hits** below; **TP** and
**FP-accepted** split it. An `FP-fixed` hit is gone from the final sweep by
definition, so it is listed separately under **Fixed during calibration**.
**Surfaced** counts final-sweep hits that the first sweep did not have,
because a fix exposed them (a new anchor, or a hit that had been hidden by
the per-file cap of 5). A `file_absent` hit whose line moved because its
anchor changed is the same lead, not a surfaced one. **Lost** counts true
positives that a fix silenced; they are listed under **Known limitations**.
So `Hits − FP-fixed − Lost + Surfaced = Final`.

**Two catalogs.** The first sweep was taken at `main` 42641b0, before any
calibration fix. Meanwhile the lead-precision branch for #19 (Tasks 1–15 and
17) changed many of the same Python detectors. The calibration fixes were
rebased onto that branch and the two sets of rules merged (see **Merged with
the lead-precision branch** below), so the final sweep, and every judgment
under **Hits**, is at the merged catalog. A hit that the merged catalog
produces and the first sweep did not is counted as Surfaced, whichever side's
rule exposed it.

## Batch — all Python detectors (Task 16)

The first sweep ran `--patterns` with every pattern id in the catalog
(S01–S19, S27–S29), and the final sweep ran `--patterns all` (which adds the
branch's S30), so both run every Python detector. The brief asked for at least one
web service, one worker/ETL codebase and one HTTP-client library; the five
repositories below cover each at least twice. All four brief candidates were
kept. rq was added as a second, smaller worker codebase, because celery is
mostly library and CLI code, and rq exercises a job runner's retry and
exception boundaries directly. Nothing was substituted.

| Repo | Kind | Commit | Python files swept |
|---|---|---|---|
| fastapi/full-stack-fastapi-template | web service (FastAPI + SQLModel) | `cb740b656d7a0a6c5e12c7bf8e50343ec94ee9c7` | 28 |
| netbox-community/netbox | web service (Django) with background jobs | `785d0b9085fe723e40eed886c8cfbde01021574a` | 785 |
| httpie/cli | HTTP-client library and CLI | `5b604c37c6c67e18e7c3e9aee6c88a8c22b98345` | 89 |
| celery/celery | worker / task queue | `eb3dfa3844288ee35c94a08267cc5e075d42b278` | 257 (256 in the final sweep) |
| rq/rq | worker / job queue | `90a67a159ef9fa055c6bde12ee1bb3ebd0440b84` | 47 |

celery keeps its tests in `t/`, which the default test-path filter does not
recognise, so `t/integration` and `t/smoke` were swept as source. Their first
sweep hits were all among the S04/S12 false positives fixed below; none
survived to the final sweep.

| Detector | Hits | TP | FP-fixed | FP-accepted | Surfaced | Lost | Final |
|---|---|---|---|---|---|---|---|
| S01-py-requests-no-timeout | 5 | 4 | 2 | 0 | 1 | 0 | 4 |
| S01-py-httpx-no-timeout | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S01-py-urlopen-no-timeout | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| S01-py-socket-no-timeout | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| S02-py-backoff | 7 | 2 | 6 | 1 | 3 | 1 | 3 |
| S03-py-429-ignores-retry-after | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S03-py-503-ignores-retry-after | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S04-py-bare-except-retry | 4 | 1 | 1 | 2 | 1 | 1 | 3 |
| S04-py-retry-without-discrimination | 27 | 1 | 27 | 0 | 1 | 0 | 1 |
| S05-py-http-without-limiter | 17 | 1 | 14 | 1 | 0 | 1 | 2 |
| S06-py-single-queue-no-priority | 123 | 0 | 122 | 2 | 1 | 0 | 2 |
| S07-py-uncheckpointed-loop | 8 | 1 | 6 | 1 | 0 | 0 | 2 |
| S07-py-insert-without-upsert | 6 | 1 | 0 | 5 | 0 | 0 | 6 |
| S08-py-unbounded-gather | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S08-py-query-all-without-limit | 522 | 1 | 521 | 2 | 2 | 0 | 3 |
| S08-py-select-without-limit | 17 | 0 | 15 | 6 | 4 | 0 | 6 |
| S09-py-cache-aside-no-singleflight | 10 | 3 | 5 | 4 | 2 | 0 | 7 |
| S10-py-nested-retry | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S10-py-boto3-default-retries (branch) | 0 | 1 | 0 | 0 | 1 | 0 | 1 |
| S11-py-no-deadline-propagation | 24 | 2 | 15 | 8 | 1 | 0 | 10 |
| S12-py-no-breaker | 28 | 0 | 27 | 2 | 1 | 0 | 2 |
| S13-py-shared-pool | 40 | 0 | 39 | 1 | 0 | 0 | 1 |
| S14-py-unbounded-queue | 2 | 1 | 1 | 0 | 0 | 0 | 1 |
| S15-py-no-fallback | 24 | 0 | 23 | 2 | 1 | 0 | 2 |
| S16-py-fixed-sleep-loop | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S16-py-fixed-cron | 2 | 0 | 1 | 1 | 0 | 0 | 1 |
| S17-py-cache-without-ttl | 25 | 0 | 22 | 3 | 0 | 0 | 3 |
| S18-py-validate-after-call | 10 | 0 | 10 | 0 | 0 | 0 | 0 |
| S19-py-except-pass | 186 | 4 | 174 | 8 | 1 | 1 | 12 |
| S19-py-bare-except | 9 | 4 | 1 | 4 | 0 | 0 | 8 |
| **Total** | **1098** | **27** | **1034** | **53** | **20** | **4** | **80** |

Hit counts are after the engine's cap of 5 hits per detector per file, so the
522 for S08 is a floor: netbox has far more `.all()` calls than that.

### Tripwire

Six detectors produced more than 25 hits in one repository in the first
sweep. Each was a finding in itself, and each was tightened before the final
sweep was judged:

| Detector | Worst repository (first sweep) | Final, same repository |
|---|---|---|
| S08-py-query-all-without-limit | netbox, 517 | 3 |
| S19-py-except-pass | celery, 115 (netbox 55) | 9 |
| S06-py-single-queue-no-priority | celery, 68 (rq 29) | 2 |
| S13-py-shared-pool | celery, 31 | 1 |
| S04-py-retry-without-discrimination | celery, 27 | 0 |
| S12-py-no-breaker | celery, 27 | 1 |

At calibration's own catalog, S19-py-except-pass still had 26 hits in celery
after its first fix and was tightened again (see below). The largest final
count in one repository at the merged catalog is 9, for S19-py-except-pass in
celery. One merged rule tripped the wire again on its way in: Django `.all()`
reported 45 hits in netbox until it was limited to QuerySets evaluated on the
spot.

### Confidence changes

- `S19-py-except-pass`: `high` → `medium`, as the plan names. At the merged
  catalog it fires only on a broad catch (`except:`, `except Exception`,
  `BaseException`), and its final sweep has 4 true positives against 8
  accepted false positives. Each is explained below. In library code, a broad
  `except …: pass` is still more often best-effort teardown or a capability
  probe than a swallowed write.
- `S17-py-cache-without-ttl` is `low` at the merged catalog (the branch set
  it); calibration found no true positive to argue otherwise.
- `S01-py-requests-no-timeout` stays `high`: 4 true positives, and both of its
  false positives were fixed.
- `S01-py-urlopen-no-timeout` and `S03-py-429-ignores-retry-after` stay
  `high`: neither has an unexplained false positive. Their evidence is thin:
  urlopen's one hit was a false positive (fixed), and no repository handles a
  429, so S03 had nothing to fire on.

### Hits

#### S01-py-requests-no-timeout

- httpie `docs/contributors/fetch.py:200` — TP (contributor tooling): `requests.get(url, params=…, headers=…)` to the GitHub API with no timeout. A stalled connection hangs the release script forever.
- httpie `httpie/internal/update_warnings.py:44` — TP (surfaced): the PyPI update check calls `requests.get(PACKAGE_INDEX_LINK, verify=False)` with no timeout. It runs in a background process, but a stalled index connection keeps that process, and the version-file lock it takes afterwards, around indefinitely. The first sweep did not report this line; the merged catalog does.
- celery `examples/gevent/tasks.py:10` — TP (example code): the example task calls `requests.get(url)` with no timeout. A hung site holds a worker greenlet forever, and users copy examples.
- netbox `netbox/core/jobs.py:209` — TP: the system job's release check calls `requests.get(url=settings.RELEASE_CHECK_URL, …)` with no `timeout=`. The census call 100 lines above sets `timeout=3`; this one does not, so a black-holed proxy hangs the RQ worker running the job.

#### S02-py-backoff

- celery `celery/backends/asynchronous.py:152` — TP (surfaced): after a connection error in `drain_events`, the drainer waits a constant `time.sleep(1)` and retries. Every client process reconnects to the broker on the same 1 s beat after a blip.
- rq `rq/worker/base.py:1084` — TP (surfaced): the pubsub exception handler waits a constant `time.sleep(2.0)` on `redis.ConnectionError` before the pubsub thread reconnects. Every worker in the fleet reconnects to Redis in lockstep.
- rq `rq/worker_pool.py:245` — FP-accepted (surfaced): `time.sleep(1); continue` while waiting for workers to shut down is a polling loop, not a retry. This is the shared handler's known false-positive shape (Java log, AC-16: a literal sleep with `continue` and an `except` nearby reads as a retry construct). Not fixed here, for the same reason.

#### S04-py-bare-except-retry

- celery `celery/app/builtins.py:71` — TP: `chord_unlock` catches `Exception` from `deps.ready()` and `raise self.retry(exc=exc, …)`. The task is declared with `max_retries=None`, so a permanent failure (a result that cannot be decoded, say) is retried forever.
- celery `celery/backends/base.py:757` — FP-accepted: the `except Exception:` guards the `on_backend_retryable_error` hook inside a retry branch and only logs. The rule's six-line look-behind (a branch rule, for `for attempt in range(…)` headers) sees the enclosing loop's `self.max_retries - retries`. Its sibling at line 747 is silent through the retryability-predicate rule added in the merge.
- rq `rq/worker/base.py:796` — FP-accepted (surfaced): the handler logs a pipeline failure. The look-behind reads the previous branch's `elif retry and retry_interval …` condition.

#### S04-py-retry-without-discrimination

- httpie `docs/contributors/fetch.py:198` — TP (contributor tooling, surfaced): `for retry in range(1, 6)` catches `requests.exceptions.HTTPError` and `continue`s for every status, not only for the 403 it waits on. A 404 or 401 is retried five times back to back. The old anchor listed only `retries`/`max_retries`-style names, so it never saw a loop variable called `retry`.

#### S05-py-http-without-limiter

- netbox `netbox/core/plugins.py:153` — TP (low impact): `get_pages()` fetches every page of the public plugin catalog back to back with `session.get(…)` in a `for page in range(2, num_pages + 1)` loop, with no pacing. It runs at most once an hour per process because of the cache (but see S09 below). The merged anchor lands on the loop line.
- celery `celery/backends/gcs.py:109` — FP-accepted: `mget` fans out one GET per key through `ThreadPoolExecutor().map`. The branch's anchor counts any `pool.map` as a fan-out; here the executor's default worker count already bounds concurrency, which is the gate this pattern asks for.

#### S06-py-single-queue-no-priority

- celery `celery/concurrency/thread.py:39` — FP-accepted (surfaced): `ThreadPoolExecutor(max_workers=self.limit)` is the thread pool's execution backend. Which work reaches it is decided by the worker's queue subscription, and Celery's documented prioritisation is separate workers per queue plus broker priorities. There is no second kind of caller inside this process to prioritise.
- celery `examples/eventlet/bulk_task_producer.py:65` — FP-accepted: `self.inqueue = LightQueue()` feeds an example bulk producer. Every item is the same kind of work (publishing tasks), so there is nothing to put ahead of anything else.

#### S07-py-uncheckpointed-loop

- httpie `docs/contributors/fetch.py:111` — TP (contributor tooling): `while 'there are issues':` walks GitHub search pages with `page += 1` and keeps the position only in memory. A crash (or the script's own `FinishedForNow` on rate limit) restarts from page 1.
- netbox `netbox/core/plugins.py:153` — FP-accepted: a read-only fetch of the plugin catalog into memory, run inside a view. There is no job and no side effect, so there is nothing to resume.

#### S07-py-insert-without-upsert

- fastapi-template `backend/app/api/routes/items.py:69` — TP: `create_item` does `session.add(item); session.commit()` with no idempotency key. A client that retries a timed-out POST creates a duplicate item.
- fastapi-template `backend/app/api/routes/private.py:35` — FP-accepted: creates a `User`, and `User.email` is `unique=True`, so a replay fails with an integrity error rather than duplicating the row. The detector cannot see the model's constraint.
- fastapi-template `backend/app/api/routes/users.py:97` — FP-accepted: `session.add(current_user)` persists changes to a loaded object (an UPDATE). User creation in this file goes through `crud.create_user`.
- fastapi-template `backend/app/crud.py:14` — FP-accepted: `create_user`, same unique-email constraint as `private.py`.
- celery `celery/backends/cassandra.py:40` — FP-accepted: a CQL `INSERT` is an upsert by primary key (`task_id`), so a replay overwrites.
- celery `celery/backends/database/__init__.py:168` — FP-accepted: a get-or-create on `task_id`, which is `unique=True`. A racing duplicate fails loudly and is not duplicated.

#### S08-py-query-all-without-limit

- netbox `netbox/core/utils.py:176`, `:191` — FP-accepted (surfaced): `cursor.fetchall()` over `information_schema.columns` and `pg_indexes` for the current schema, which is bounded by the size of the schema, not by data.
- netbox `netbox/ipam/management/commands/rebuild_prefixes.py:23` — TP (low impact): `for vrf in VRF.objects.all():` evaluates every VRF into memory in a management command. The row count is modest, but nothing bounds it.

#### S08-py-select-without-limit

- netbox `netbox/netbox/models/ltree.py:167` — FP-accepted: a subquery opened with `(` on the previous line, a unique `(app_label, model)` lookup. The subquery exclusion only sees the `(` when it is on the same line.
- netbox `netbox/netbox/search/backends.py:223` — FP-accepted: `SELECT * FROM ({sql}) t WHERE row_number = 1` wraps a queryset that is already sliced to `[:MAX_RESULTS]`, so the inner SQL carries the LIMIT. The detector cannot see into `{sql}`.
- netbox `netbox/utilities/mptt_to_ltree.py:139`, `:144`, `:149`, `:152` — FP-accepted (surfaced): each is a fragment interpolated into `SELECT count(*) FROM ({root} UNION ALL {child})`, so the rows are counted, not fetched. The detector sees each fragment on its own line.

#### S09-py-cache-aside-no-singleflight

- netbox `netbox/core/plugins.py:233` — TP: `cache.get(CACHE_KEY_CATALOG_FEED)`, and on a miss `make_plugin_dict()` pages through the remote catalog, then `cache.set(…, 3600)`. Concurrent requests after the hourly expiry each page through the catalog.
- netbox `netbox/core/views.py:858` — FP-accepted: reads a negative-cache flag (`CACHE_KEY_CATALOG_ERROR`) that is itself the throttle. The load it guards is the `plugins.py` cache-aside above.
- netbox `netbox/extras/api/customfields.py:66` — FP-accepted: `cache` here is a dict built earlier in the same request to prefetch related objects (`cache = {}` at line 144), not a shared cache.
- netbox `netbox/extras/dashboard/widgets.py:374` — TP: the RSS widget reads `cache.get(self.cache_key)` and on a miss fetches the feed and `cache.set`s it. Every dashboard rendered during the miss fetches the same feed.
- netbox `netbox/netbox/config/__init__.py:78` — TP (low impact): on a miss for `config`/`config_version`, every process queries the latest `ConfigRevision` and writes both keys. The load is one small query.
- celery `celery/backends/cache.py:63` — FP-accepted (surfaced): `DummyClient.get` is the in-memory stand-in for a memcached client, so this *is* the cache, not a cache-aside in front of a dependency.
- celery `celery/utils/dispatch/signal.py:275` — FP-accepted (surfaced): `sender_receivers_cache` memoises which receivers match a sender, which is a cheap in-process computation with no dependency behind it to stampede.

#### S10-py-boto3-default-retries

- celery `celery/backends/dynamodb.py:183` — TP (surfaced; a branch detector with `score: false`, used for the retry-layer inventory): `boto3.client('dynamodb', **client_parameters)` sets no `Config(retries=…)`, so botocore's default retries are a layer nobody wrote.

#### S11-py-no-deadline-propagation

- httpie `docs/contributors/fetch.py:200` — FP-accepted: a standalone script, so it has no caller whose deadline could be passed on.
- httpie `httpie/client.py:161` — FP-accepted: a CLI. The user's own `--timeout` bounds the request, and there is no upstream caller.
- celery `examples/eventlet/tasks.py:10`, `examples/eventlet/webcrawler.py:54`, `examples/gevent/tasks.py:10` — FP-accepted: background tasks have no caller deadline to propagate. The task's own time limit, if set, ends the whole task.
- netbox `netbox/core/jobs.py:102` — FP-accepted: a background system job (the census ping).
- netbox `netbox/core/plugins.py:133` — TP: runs inside the plugins view's request. Up to `num_pages` sequential calls with a 3 s timeout each take no account of how long the browser has left.
- netbox `netbox/extras/dashboard/widgets.py:381` — TP (weak): the RSS fetch runs while the dashboard renders, with a fixed configured timeout that ignores the request's remaining time.
- netbox `netbox/extras/webhooks.py:129` — FP-accepted: webhooks are sent from a background job.
- httpie `httpie/internal/update_warnings.py:44` — FP-accepted (surfaced): a background update check with no caller.

#### S12-py-no-breaker

- httpie `docs/contributors/fetch.py:198` — FP-accepted (surfaced): a one-shot script with five bounded attempts. A breaker protects a long-running client; here the process simply ends.
- celery `celery/contrib/testing/manager.py:119` — FP-accepted (surfaced): test-support code waiting for results, bounded by `max_retries`.

#### S13-py-shared-pool

- celery `celery/concurrency/thread.py:39` — FP-accepted: `self.executor = ThreadPoolExecutor(max_workers=self.limit)` is the thread pool's execution backend, and `on_apply` submits whatever the consumer hands it. In a worker every workload is background work; bulkheads between queues are separate workers.

#### S14-py-unbounded-queue

- celery `celery/contrib/testing/worker.py:49` — TP (test code): the embedded test worker's `billiard.Queue()` for child log records is unbounded. It lives only as long as a test.

#### S15-py-no-fallback

- httpie `httpie/client.py:161` — FP-accepted: a CLI. Reporting the failure to the user is the right degraded behaviour, and there is no reduced response to serve.
- httpie `httpie/internal/update_warnings.py:44` — FP-accepted (surfaced): if the optional update check fails, the only loss is the "new version" notice.

#### S16-py-fixed-cron

- celery `celery/beat.py:275` — FP-accepted: the built-in `backend_cleanup` entry is `crontab('0', '4', '*')`. `celery beat` is a singleton scheduler per deployment, so the herd the pattern describes (every instance firing at once) cannot form. The detector cannot see topology, which is why it is `low`.

#### S17-py-cache-without-ttl

- celery `celery/utils/time.py:76` — FP-accepted: the class-level `_offset_cache` is keyed by UTC offset, which is bounded by the number of distinct offsets.
- netbox `netbox/dcim/models/module_moves.py:105` — FP-accepted: `self._template_cache` lives as long as one module-move plan object (the comment says "per planning pass").
- netbox `netbox/utilities/forms/fields/generic.py:48` — FP-accepted: `self._content_type_cache` on a form field is keyed by content-type pk, which is bounded by the number of content types, and lives as long as the form.

#### S19-py-bare-except

- rq `rq/job.py:1134` — TP: a bare `except:` around `serializer.dumps(self._result)` turns a `KeyboardInterrupt` or `SystemExit` raised during serialisation into the string `'Unserializable return value'`.
- rq `rq/queue.py:1441` — TP: synchronous job execution (`is_async=False`) records any `BaseException` as a job failure and does not re-raise, so the caller's Ctrl-C is swallowed.
- rq `rq/results.py:309` — TP: the same serialisation shape as `job.py:1134`.
- rq `rq/utils.py:211` — TP: `import_attribute` converts any exception, Ctrl-C included, into `ValueError('Invalid attribute name')`.
- rq `rq/worker/base.py:679` — FP-accepted: `SystemExit` is re-raised explicitly just above, and this handler logs with `exc_info` and stops the worker loop, which is the outcome an interrupt should have.
- rq `rq/worker/base.py:1637` — FP-accepted: deliberate and commented. A failing failure-callback replaces the job's exception and is recorded as the failure.
- rq `rq/worker/base.py:1676` — FP-accepted: the job-execution boundary in the work horse records every `BaseException` from user code (including `sys.exit()` in a job) as the job's failure, which is its purpose.
- rq `rq/worker/base.py:1698` — FP-accepted: the forked work horse must never unwind into the parent's stack. `except: os._exit(1)` is the standard pattern.

#### S19-py-except-pass

True positives:

- celery `celery/backends/base.py:473` — TP: an error callback that raises while a group's errbacks are replayed is swallowed with no log, so the errback's own failure leaves no trace.
- celery `celery/backends/database/__init__.py:240` — TP: malformed stamping metadata is dropped from the task meta by `except Exception: pass`. The result silently lacks data it should have.
- netbox `netbox/core/checks.py:156` — TP: the Redis version system check swallows any exception, so an unreachable or misconfigured Redis makes the check pass silently.
- netbox `netbox/netbox/tables/columns.py:732` — TP (weak, surfaced): `CustomLinkColumn.value()` (the export path) swallows any exception from rendering a custom link and exports nothing. The table's own `render()` shows an "Error" badge for the same failure, so an export silently differs from the screen.

Accepted (best-effort teardown, capability probes and a poll):

- celery `celery/events/cursesmon.py:170` — `getkey()` raises when no key is pressed. This is a poll.
- celery `celery/platforms.py:554` — a `sysconf` capability probe on platforms that lack it.
- celery `celery/utils/serialization.py:63`, `:165` — probing whether an exception pickles. The exception is the answer.
- celery `celery/utils/threads.py:93`, `:95` and `celery/worker/consumer/consumer.py:427` — best-effort socket timeouts and `collect()` while tearing down a broken broker connection.
- netbox `netbox/core/apps.py:59` — a debug-mode-only `cache.clear()` on startup.

The 26 narrow-exception handlers that calibration's own catalog accepted
(`OSError` on closing dead pipes, `curses.error`, `ExpatError`,
`InvalidJobOperation`, `interface_errors`, and so on) are silent at the merged
catalog, because it fires only on a broad catch. So is one calibration true
positive (see **Lost** under Known limitations).

### Fixed during calibration

Counts in this section are calibration's own, at its catalog. Where a lead
came back at the merged catalog, the table counts it under Final and the
entry says so. Every fix below was preceded by a `negative_<shape>.py` sample that
reproduced the real shape and failed. Where a tightening could silence a real
case, a `positive_<shape>.py` guard was added too (the branch's test harness
already treats a `positive_<shape>` sample as one that must fire). Where the
merge later replaced a calibration rule, the entry says so and
**Merged with the lead-precision branch** gives the rule that stands.

- `S01-py-requests-no-timeout`, 2 hits:
  - httpie `httpie/client.py:189`: `f'>>> requests.request(**{…})'` is a debug message. The call must now be outside a string literal on its line → `S01/python/negative_request_in_message.py`
  - celery `examples/eventlet/webcrawler.py:54`: `requests.get(url)` inside `with Timeout(5, False):`. A `with …timeout(…)` block within the look-behind window now counts as a bound → `S01/python/negative_timeout_context.py`
- `S01-py-urlopen-no-timeout` celery `examples/gevent/tasks.py:7`: `def urlopen(url):` defines a task named urlopen. The pattern skips `def urlopen(` → `S01/python/negative_defines_urlopen.py`
- `S01-py-socket-no-timeout` celery `celery/contrib/rdb.py:124`: the remote debugger's socket binds and listens. It is a listener, not an outbound call, so a `.bind(` in the window suppresses the hit → `S01/python/negative_listening_socket.py`
- `S02-py-backoff`, 6 hits. The Python handler had two defects, and both are Python-only fixes in `scripts/detectors/modules.py`:
  - `**` counted as exponential growth, and nearly every Python file has `**kwargs`. That made every variable wait read as a growing backoff, so the handler reported "no cap"/"no jitter" on waits that do not grow. `GROWTH_PY` counts `**` only after an operand (`2 ** attempt`). This fixed celery `celery/apps/multi.py:487` (`sleep(float(retry))` polling for nodes to exit), celery `celery/backends/base.py:739` and `celery/backends/database/session.py:98` (jitter is passed positionally, `get_exponential_backoff_interval(…, True)`, and the old report was an artefact of `**kwargs`), and httpie `docs/contributors/fetch.py:212` (`sleep(wait)` with the server's `X-RateLimit-Reset`, capped at 20 s) → `S02/python/negative_shutdown_poll.py`
  - `delay(` counted as a sleep. Celery's `task.delay(…)` sends a task, and `def delay(` defines one. This fixed celery `examples/resultgraph/tasks.py:83` and rq `rq/decorators.py:95`. The bare-call regex is now `(?<![.\w])(?<!def )(?:sleep|delay)(`, and `gevent.sleep`/`eventlet.sleep` were added to the module-qualified form → `S02/python/negative_task_delay.py`

  A third Python-only rule came from a probe of the surfaced hits: `sleep(0)` is a cooperative yield and never a backoff. celery `celery/concurrency/asynpool.py:1413` surfaced once `**kwargs` stopped masking constant waits, and it is now skipped → `S02/python/negative_yield_sleep0.py`
- `S04-py-bare-except-retry`, 2 hits: celery `celery/backends/base.py:757` (the word "retry" inside the log message `"…; continuing retry loop"`) and celery `celery/events/dispatcher.py:159` (the next function's `def send(…, retry=False, …)` fell inside the window). Retry vocabulary now counts only outside a string literal and not on a `def` line, as the Java detector already required → `S04/python/negative_retry_word_in_message.py`, `negative_retry_param_next_def.py`. At the merged catalog `base.py:757` fires again through the branch's look-behind and is accepted under **Hits**.
- `S04-py-retry-without-discrimination` and `S12-py-no-breaker`, 27 + 27 hits in celery (plus rq `rq/cli/cli.py:185` for S12). All of them anchored on a retry *setting*: a `max_retries=` keyword passed on, an `Option(type='int')`, a `retries` column, `'retries': body.get(…)`, a `@property def retries`, a docstring. None was a retry construct. Both detectors now anchor on a retry this file runs, mirroring `S12-java-no-breaker`: a `for`/`while` whose header says attempt/retry with a `try:` within two lines, a `@retry`/`@tenacity.retry` decorator, or `Retrying(`. S04's absent list also gains `Timeout\w*` and `socket.timeout`, because a loop that retries only timeouts discriminates (celery `celery/contrib/testing/manager.py`, whose `except (socket.timeout, TimeoutError)` loop the new anchor reaches) → `S04/python/negative_retry_setting.py`, `negative_timeout_only_retry.py`, `S12/python/negative_retry_setting.py`; guards `S04/python/positive_retry_loop.py`, `S12/python/positive.py`
- `S05-py-http-without-limiter`, 15 hits:
  - 12 anchored on an import, a type annotation, an `except requests.Timeout`, or an adapter construction, not on a request: httpie ×11 and celery `celery/backends/gcs.py:124`, whose only fan-out (`mget`) goes through a `ThreadPoolExecutor`, which already bounds concurrency. The anchor is now a request call or a client construction.
  - 3 made a single request in a file that also loops over something else: netbox `core/jobs.py:102`, `extras/dashboard/widgets.py:381`, `extras/webhooks.py:108`. The `require` is now a fan-out primitive, or a request made within eight lines of a loop header.

  → `S05/python/negative_client_types_only.py`, `negative_single_call_unrelated_loop.py`. The merge kept the branch's anchor instead, which satisfies both samples, and `gcs.py` returns through its `pool.map` alternative (accepted under **Hits**).
- `S06-py-single-queue-no-priority`, 123 hits (celery 68, rq 29, netbox 23, httpie 2, fastapi-template 1). The anchor was any mention of `queue`, `worker`, `pool`, `limiter` or `throttle`: imports (`from kombu import Queue`, `from rq.worker import Worker`), verbose names and labels (`_('Queue')`, `'Is a pool'`), logger names, CLI strings (`'--worker'`), broker queues declared by name (`Queue('celery', exchange)`), `def worker(…)`, and an Alembic `pool` import. The anchor is now an in-process queue, executor or semaphore that the file creates, and a `require` that more than one kind of work reaches it (two submission sites, or a function that submits its caller's job), after the Java detector → `S06/python/negative_broker_queue_names.py`. At the merged catalog one of these files, celery's `examples/eventlet/bulk_task_producer.py`, is a lead again through its `self.inqueue = LightQueue()` (accepted under **Hits**).
- `S07-py-uncheckpointed-loop`, 6 hits: httpie `httpie/cli/nested_json/interpret.py:68` and `parse.py:162`, and netbox `dcim/svg/cables.py:71`, `:130`, `:220` and `dcim/svg/racks.py:312`. In each, `cursor`/`offset` is a parse position or a drawing coordinate (`cursor += LINE_HEIGHT`, `y_offset = …`). Python now has its own `PAGE_ADVANCE_PY`: a cursor counts as advanced only when it is assigned from a response or next-page value, an offset only when it steps by a page or batch size, and a page variable only on reassignment. A later probe of the final sweep found that `homepage_url=…` and `access_token=data[…]` keyword arguments inside a page-consuming loop read as advances, so the page name is now exact (`page`, `next_page`, `page_num`) and an assignment needs whitespace before `=` → `S07/python/negative_layout_cursor.py`, `negative_nested_path_cursor.py`, `negative_page_named_kwarg.py`; guard `positive_next_cursor.py`
- `S08-py-query-all-without-limit`, 522 hits (netbox 517, fastapi-template 3, celery 2):
  - netbox, 517: Django `.all()`. Of these, 450 go through a model manager (`Region.objects.all()`, mostly a view's or form field's `queryset =`, which the framework paginates or slices), and the rest are related managers (`self.tags.all()`, `obj.terminations.all()`) that read one object's children. A QuerySet is lazy, so `.all()` fetches nothing by itself.
  - fastapi-template `api/routes/items.py:27`, `:42`, `users.py:48`: `session.exec(statement).all()` where `statement` ends in `.offset(skip).limit(limit)` on the lines just above.
  - celery `celery/fixups/django.py:179`, `:224`: `connections.all()`, Django's connection handler, not a query.

  The pattern now matches only an eager fetch: DB-API `.fetchall()`, or `.all()` on `query(…)`/`exec(…)`/`execute(…)`/`scalars(…)`. `window_before: 8` lets a `.limit(` on the statement built above count → `S08/python/negative_django_queryset.py`, `negative_limited_statement.py`; guard `positive_sqlalchemy_all.py`. The merge restored Django loads that are evaluated on the spot, so netbox's `rebuild_prefixes.py:23` is a lead again (a TP under **Hits**).
- `S08-py-select-without-limit`, 15 hits. Subqueries (`EXISTS (SELECT 1 …`, `= (SELECT …`), scalar selects (`SELECT COUNT(*)`, `SELECT count(*) INTO`, `SELECT setval(`) and primary-key lookups (`… WHERE id = $1`), in netbox (11) and a fastapi-template Alembic migration (4). The pattern skips a SELECT preceded by `(`, `SELECT 1`, and `SELECT fn(`, and `WHERE id =`/`pk =` counts as bounded → `S08/python/negative_scalar_selects.py`; guard `positive_select_star.py`
- `S09-py-cache-aside-no-singleflight`, 5 hits: netbox `core/models/object_types.py:74` and `extras/models/customfields.py:88` (`query_cache.get()` on a `ContextVar`), `views/misc.py:63` (reads a key that only a background job writes), `utilities/fields.py:319` (Django's `get_cached_value`), and celery `celery/result.py:391` (a task-meta dict called `cache`). The read must now take an argument, the `get_cached`/`from_cache` name alternatives are gone, and the file must also fill the cache (`require`) → `S09/python/negative_read_only_and_contextvar.py`
- `S11-py-no-deadline-propagation` (15 hits) and `S15-py-no-fallback` (23 hits) had the same anchor defect as S05: imports, annotations, `requests.Response` type references, `except requests.Timeout`, and celery's worker-state dict that happens to be named `requests` (`requests.clear()`, `requests.pop(…)`). Both now anchor on a request call or a client construction. S15 also treats an `except` that catches the HTTP client's own exception as the fallback branch. The three celery examples and netbox `core/jobs.py`, `core/plugins.py` and `extras/dashboard/widgets.py` each catch the request's failure and return a degraded value (`None`, `(url, 0)`, an empty catalog, an error panel). netbox `extras/webhooks.py` and httpie `docs/contributors/fetch.py` are silent through the same rule: the webhook job logs a timeout and re-raises, and the script retries. Neither has anything to degrade to, so both were false positives either way → `S11/python/negative_client_types_only.py`, `negative_local_requests_registry.py`, `S15/python/negative_client_types_only.py`, `negative_except_returns_default.py`; guards `S11/python/positive.py`, `S15/python/positive.py`
- `S13-py-shared-pool`, 40 hits (celery 31, netbox 6, rq 2, fastapi-template 1). Every one was the word `pool` in a label (`'Is a pool'`), an airport name in netbox's IATA/UN-LOCODE data files (`'KNJ (Kindamba, Pool, CG)'`), an import, a parameter or a docstring. The anchor is now a worker pool the file creates, the `require` is two submission sites, and a second pool counts as isolation, after the Java detector → `S13/python/negative_pool_mentions.py`; guard `S13/python/positive_two_submission_sites.py`. celery `concurrency/thread.py` is a lead again at the merged catalog, through its `self.executor = ThreadPoolExecutor(…)` and a pass-through `submit` (accepted under **Hits**).
- `S14-py-unbounded-queue` rq `rq/queue.py:210`: `"Queue() missing 1 required positional argument"` is an error message. The match must now be outside a string literal → `S14/python/negative_queue_in_message.py`
- `S16-py-fixed-cron` celery `celery/schedules.py:331`: `class crontab(BaseSchedule):` defines the class. `class `/`def ` before the name now suppresses the hit → `S16/python/negative_defines_crontab.py`; guard `S16/python/positive.py`
- `S17-py-cache-without-ttl`, 22 hits:
  - netbox, 18 hits:
    - Django's shared `cache.set(key, value, timeout)` (an external cache with its own eviction, often with a positional TTL the vocabulary never saw)
    - `ContextVar('query_cache')` and its `.set(`
    - `OP_CACHE = 'cache'`
    - reads such as `cache['object_types'].get(…)`
    - a per-user permission memo (`user_obj._object_perm_cache = …`)
    - two serializer caches keyed by `instance.__class__`
    - a function-local `events_cache = defaultdict(dict)` and a request-local `cache = {}`
    - `utilities/jinja2.py:68`, a `DataFileLoader._template_cache` that lives for one render (a loader is built per `render_jinja2` call) and is filled with `.update(…)`
  - celery, 4 hits: `self._cache = import_module(…)`, `app._backend_cache = None`, and two reads of maps built elsewhere: the rpc backend's result map (an `LRUCache` from `backends/base.py:223`, which `rpc.py:216` also clears) and billiard's pending-job table in `asynpool.py`.

  The anchor is now an in-process dict created to act as a cache (at module level, in a class body or as a `self.`/`cls.` attribute), the `require` is that the file fills it by key, and a class-keyed map counts as bounded → `S17/python/negative_django_cache.py`, `negative_local_memo.py`, `negative_class_keyed.py`; guard `S17/python/positive.py`
- `S18-py-validate-after-call`, 10 hits. All were false positives of the shared TS/Python vocabulary:
  - `assert` (an internal invariant, stripped under `-O`, in rq ×3, httpie ×2 and celery ×1)
  - `.parse(` of the response just fetched (netbox `version.parse(release['tag_name'])`, `feedparser.parse(response.content)`)
  - a `requests.` type reference taken for a call (httpie `isinstance(message, requests.Response)`)
  - the TS client name `got` matching the string `"…but got {datatype}"` (netbox `api/viewsets/mixins.py:489`)

  Python now has its own `EXTERNAL_CALL_PY` (calls only, and a bare `fetch(` but not `.fetch(`) and `VALIDATION_PY` (no `assert`, no `.parse(`). The pinned behaviour in `test_s18_ts_python_unchanged.py` still holds → `S18/python/negative_invariant_asserts.py`
- `S19-py-except-pass`, 152 hits (celery 96, netbox 45, httpie 7, rq 4):
  - 151 name only exceptions that signal an expected absence, a parse miss or a cancellation: `KeyError` 40, `AttributeError` 19, `ValueError` 18, `ImportError` 14, netaddr's `(AddrFormatError, ValueError)` 7, `socket.timeout` in a poll loop 5, `IndexError` 4, plus `LookupError`, `TypeError`, `ModuleNotFoundError`, `FileNotFoundError`, `ObjectDoesNotExist`/`X.DoesNotExist`, `NoReverseMatch`, `NoSuchJobError`, pygments' `ClassNotFound`, `re.error`, `StopIteration`, celery's `StopFiltering` and eventlet's `GreenletExit`. The pattern now skips an `except` whose every named exception is in that family.
  - One (netbox `extras/webhooks.py:72`) logs a warning and then has a redundant `pass`. `pass` must now be the handler's first statement.

  After the first fix celery still had 26 hits, over the tripwire. Cancellation and stop signals (`GreenletExit`, `CancelledError`, `Stop…`) were then added → `S19/python/negative_expected_absence.py`, `negative_parse_miss.py`, `negative_poll_timeout.py`, `negative_cancellation.py`, `negative_logged_then_pass.py`; the merge then narrowed this detector to broad catches (see below), so the family list is gone and these samples stay silent through that rule instead
- `S19-py-bare-except` rq `rq/scheduler.py:359`: `except: log.error(…); raise` re-raises everything it caught, so it is transparent. A bare `raise` in the handler now suppresses the hit → `S19/python/negative_bare_reraise.py`

### Merged with the lead-precision branch

The branch and calibration both changed these Python detectors. Each merged
rule keeps both intents: every sample from both sides passes (the branch's
samples encode reviewed false positives and true positives, and calibration's
encode the shapes above). The final sweep was then run at the merged catalog,
and five more false-positive shapes it found were fixed, each red first.

- `S19-py-except-pass`: the branch's pattern (only `except:`,
  `except Exception`, `except BaseException`, alone or in a tuple) replaces
  calibration's exception-family exclusion. Both exclude every narrow shape
  that calibration found. Calibration's `pass`-must-come-first rule
  (`\A\s*pass`, window 3) is kept, and so is `medium`. Calibration's
  `positive_tuple_with_broad.py` (`(KeyError, OSError)`) contradicted the
  branch's decision that a narrow I/O catch is not this detector's business,
  and the branch's `positive_tuple_exception.py` covers the tuple case, so it
  was dropped.
- `S19-py-bare-except`: the branch's indentation-aware re-raise rule
  replaces calibration's `^\s*raise\s*$`, which would also have silenced a
  bare `raise` in the *next* function (the branch's
  `positive_raise_elsewhere.py`). `negative_bare_reraise.py` passes under
  it.
- `S04-py-bare-except-retry`: the branch's rule (a `for … in range` retry
  loop, or retry vocabulary, with a six-line look-behind) is kept.
  Calibration's condition that the vocabulary be in code (not a string, not a
  `def` line) is applied to the vocabulary alternative. The branch dropped
  `continue` as retry evidence (its `negative_skip_bad_item.py`), which
  silences rq `registry.py:631`. The merged sweep found celery
  `backends/base.py:747`, `except Exception as exc:` followed by
  `if self.exception_safe_to_retry(exc)`, which is discrimination. A
  retryability predicate (`*safe_to_retry(`, `is_retryable(`,
  `is_transient(`, `should_retry(`) in the window now suppresses the hit →
  `S04/python/negative_retryable_predicate.py`
- `S05-py-http-without-limiter`: the branch's anchor (an HTTP call inside a
  loop body, a `gather(*[… for …])`, or `pool.map`) and its import `require`
  are kept. They satisfy calibration's samples, so calibration's
  anchor/require were dropped. The merged sweep hung on netbox
  `extras/dashboard/widgets.py`: `[^\n]*\b\w*[Ss]ession` can split one
  identifier two ways, and a blank line matched both body alternatives. So
  the receiver now starts at an identifier boundary (`[^\n]*?(?<!\w)`), and a
  body line must start with a non-blank. The file now takes milliseconds, and
  every sample still passes.
- `S06-py-single-queue-no-priority` and `S13-py-shared-pool`: the branch
  requires a module-level or `self.` assignment (a pool local to one function
  serves one caller). Calibration requires that the right-hand side
  construct an in-process queue, semaphore or pool, and that more than one
  kind of work reach it. The merged anchor is both: `PLACE = CONSTRUCTOR`.
  The `require` is two submission sites or a function that submits its
  caller's argument, which the branch's S13 `positive.py` (`def
  submit(fn, *a): return executor.submit(fn, *a)`) needs. The branch's
  anchor alone matched `self.queue_class = import_queue_class(…)`,
  `self.queues = prepare_queues(…)` and `DjangoWorkerFixup(…)` in the merged
  sweep → `S06/python/negative_queue_named_call.py`. Calibration's
  `S13/python/positive.py` became `positive_two_submission_sites.py`, next to
  the branch's `positive.py`.
- `S08-py-query-all-without-limit`: the branch reports Django and
  Flask-SQLAlchemy loads (`positive_django_all.py`: `list(Order.objects.all())`,
  `positive_flask_model_query.py`) under an import `require` that keeps
  numpy's `mask.all()` out. Calibration found 517 lazy Django `.all()` calls
  in netbox. Merged: eager DB-API and SQLAlchemy fetches, `Model.query…all()`,
  and a Django manager's `.all()` only when it is evaluated on the spot
  (`list(`/`tuple(`/`set(`/`sorted(`/`len(`, or `for … in`). A first merge
  that excluded only `queryset =` assignments still gave 45 netbox hits: view
  querysets passed to `add_related_count(…)`, `{'queryset': …}`,
  `get_object_or_404(…)` → `S08/python/negative_queryset_passed_on.py`
- `S08-py-select-without-limit`: calibration's pattern (a top-level SELECT of
  rows: no `(SELECT`, `SELECT 1` or `SELECT fn(`) with the branch's
  `absent_within`, which ties `WHERE id =` to the SELECT that owns it (its
  `positive_neighbour_select.py`) and exempts `= ANY(…)`. `pk =` was added.
- `S11-py-no-deadline-propagation` and `S15-py-no-fallback`: the branch
  anchored on any `requests.`/`httpx.`/`aiohttp.` attribute except
  submodules and exception types. Calibration's call-only anchor excludes
  those too, and also a `requests.Response` annotation and a local dict named
  `requests`, so it stands (with aiohttp's `ClientSession(`). S15 keeps
  calibration's catch-the-client's-exception fallback rule.
- `S17-py-cache-without-ttl`: calibration's anchor, `require` and `absent`,
  with the branch's `confidence: low`. The branch's `absent` ended in
  `clear\s*\()\b`, and the trailing `\b` after `(` meant `cache.clear()`
  never counted as a bound. Calibration's `absent` names
  `cache.clear(`/`popitem(`/`pop(` without it →
  `S17/python/negative_cleared_cache.py`

Calibration's other changes (S01, S02, S04-discrimination, S07, S09, S12, S14,
S16, S18, and the Python branches in `scripts/detectors/modules.py`) touched
no branch rule and merged unchanged.

### Silences checked

- `S01-py-httpx-no-timeout`, `S03-py-429-ignores-retry-after`, `S03-py-503-ignores-retry-after`, `S08-py-unbounded-gather`, `S10-py-nested-retry` and `S16-py-fixed-sleep-loop` produced no hits in any repository. No swept file uses httpx or `asyncio.gather`, and no swept file reacts to a 429. netbox *returns* 503 (`api/exceptions.py:5`, `utilities/exceptions.py:63`) but retries nothing, so S03-503's `require` keeps it silent, which is correct. No file has two retry layers for S10 to find. These detectors have no real-world evidence from this batch.
- netbox's other outbound call, the census ping at `core/jobs.py:102`, sets `timeout=3`, and `extras/webhooks.py` passes the webhook's `timeout`. S01 stays silent on both, which is correct.
- The fastapi-template's list endpoints bound every query with `.offset(skip).limit(limit)`, so S08 stays silent after the fix, which is correct.

### Known limitations (noted, not fixed)

- **Lost true positives.** Four rules silenced a real case:
  - `S02-py-backoff` celery `celery/backends/asynchronous.py:102`, `time.sleep(interval)` after a drain error with no jitter. Once `**kwargs` stopped counting as growth, a variable wait in a file with no growth reads as "cannot tell", which is the handler's rule for every language. The constant-wait twin at line 152 still fires, so the drainer still gets a lead.
  - `S05-py-http-without-limiter` celery `examples/eventlet/webcrawler.py:54`. The crawler fans out through `crawl.delay(url)` tasks, not a loop of requests, so no loop-call rule sees it. No file-local regex can.
  - `S04-py-bare-except-retry` rq `rq/registry.py:631`: `except Exception: …; continue` leaves the job in the `ReadyJobRegistry` for the next pass, so a permanent error is retried forever. The branch ruled `continue` out as retry evidence, because in an item loop it usually means "skip" (`negative_skip_bad_item.py`). Here, skipping *is* retrying later.
  - `S19-py-except-pass` httpie `httpie/downloads.py:244`: `except OSError: pass` around `truncate()` also hides a failed truncate of a real file. The merged rule fires only on broad catches.
- `S19-py-except-pass` fires only on broad catches. A narrow catch that swallows a real write failure (`except OSError: pass`, `except IntegrityError: pass`) is a miss.
- `S19-py-except-pass`, precision: best-effort teardown (`close()`, `settimeout()`, `collect()` in a `try`) is the dominant accepted shape. A regex that sees only the `except` line and its body cannot see what the `try` did.
- `S04-py-bare-except-retry`: the six-line look-behind reads retry vocabulary from the enclosing or preceding code, as in the two accepted hits above.
- `S08-py-query-all-without-limit` reports a Django QuerySet only when it is evaluated on the line that builds it. One that is built, returned and then iterated elsewhere is a miss, and so is SQLAlchemy `.all()` split across lines (`session.query(X)` on one line, `.all()` on the next). S29 covers N+1 fan-out, not a whole-table load.
- `S08-py-select-without-limit`: the subquery exclusion sees a `(` only on the SELECT's own line, and a LIMIT inside an interpolated `{sql}` is invisible. Both are accepted above.
- `S15-py-no-fallback` counts any `except` that names the HTTP client's exception as a fallback, including one that logs and re-raises. A call whose failure is caught only to be re-raised is a miss.
- `S11`/`S15` anchor on module-level `requests`/`httpx` calls and client constructions. A file that only receives an injected session (`self.session.get(…)`) is a miss. S05 (the branch's anchor) does see `…session.get(` inside a loop.
- `S06`/`S13`: a pool or queue created in one module and submitted to from another is a miss, because the detectors are file-local. So is one created in a function and stored elsewhere. S13 no longer reports database connection pools (`create_engine(pool_size=…)`), because one engine per app is the norm and a regex cannot tell whether batch and request work share it.
- `S17-py-cache-without-ttl`: an instance attribute on a short-lived object (a form field, a plan) still fires. The detector cannot see the owner's lifetime. A function-local cache in a module-level function (four-space indent) is indistinguishable from a class attribute and still fires.
- `S07-py-insert-without-upsert` cannot see a model's unique constraint or tell an UPDATE of a loaded object from an INSERT (`session.add` does both), and treats a CQL `INSERT`, which is an upsert, as an insert. These account for 5 of its 6 final hits.
- `S02-py-backoff`: the polling-loop shape (`time.sleep(1); continue` near an `except`) still reads as a retry, as recorded in the Java log for the shared handler (AC-16).
- celery's test directory `t/` is not recognised by the default test-path filter.
