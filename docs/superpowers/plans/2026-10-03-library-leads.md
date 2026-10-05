# Library Leads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every boundary and detector lead in a briefing is one a reviewer would accept as real, on library code as on services, and the report never presents what the detectors looked for as what the code does.

**Architecture:** Detectors gain one catalog key, `absent_before`, which corrects the three false-lead shapes found on Celery with negative samples. Boundary matching moves out of `bundle.py` into the catalog as per-language, call-shaped rules run by `detectors.find_boundaries`, with samples like detectors. The report's *Pattern coverage* section is reworded for every repository, and a Celery calibration log records every hit and the before/after figures.

**Tech Stack:** Python 3.11+, PyYAML, `uv`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-03-library-leads-design.md` (§n below refers to it). Requirements AC-1…AC-7 and the product decisions are in GitHub issue #58, part of #54.

**Branch:** `feat/library-leads`. One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

**Celery copy.** Tasks 2–4 and 8 measure against celery/celery at the benchmark commit. Make a private copy once, outside the repository (never scan a checkout someone else uses: the pipeline writes `.thunderstruck/` into it):

```bash
mkdir -p /tmp/thunderstruck-58
git clone https://github.com/celery/celery "/tmp/thunderstruck-58/celery" && git -C "/tmp/thunderstruck-58/celery" checkout 508c1129269d2b1baffc516d8f5c05da06273ef0
printf '[context]\nenabled = false\n' > "/tmp/thunderstruck-58/celery/.thunderstruck.toml"
```

Every command in this plan uses the fixed scratch path `/tmp/thunderstruck-58`, written out in full, because shell variables do not persist between commands. It is outside the repository and nothing in it is committed.

## Global Constraints

- The catalog is the source of truth: every boundary rule and every detector correction is a catalog entry plus samples (CLAUDE.md). `BOUNDARY_PATTERNS` is deleted from `bundle.py` (§2.5).
- A false positive on correct code is worse than a miss: every existing positive detector sample still fires after every task (§3.2).
- `S07-py-insert-without-upsert` keeps `confidence: medium` (§3.2).
- Bundles stay byte-identical across runs on an unchanged repository: no timestamp, no absolute path, output in line order (§6).
- `VALIDATION_RULES` does not change (§6).
- `report.json` keys are not renamed: `pattern_coverage` and `coverage_rows` stay (§4).
- The coverage section's heading, intro and footnote are the exact strings of §4, held once as constants in `report.py`, and `templates/report.html` carries the same strings (§4).
- No model calls are added (§10).
- `docs/calibration/correctness/celery/` is evidence and is not edited.
- Public repository: no organisation-specific names, hosts, credentials or local paths in any file.

## Review Focus

1. **A Python file that imports `requests` and also has a local dict named `requests`** (Celery's worker state imported into a file that also calls the library). `requests.pop(…)` is still not HTTP, because `pop` is not an HTTP verb; `requests.get(url)` is. Pinned in Task 5 (`test_library_name_with_a_non_http_method_is_not_http`).
2. **A Windows checkout with CRLF line endings.** `absent_before` and boundary rules match per line; a stray `\r` must not stop `try:\s*$` or `.add(task)` from matching. Pinned in Task 1 (`test_absent_before_tolerates_crlf`) and Task 5 (`test_crlf_lines_still_match`).
3. **A `file_absent` detector whose every anchor is excused.** No hit at all, never a hit on the first anchor. Pinned in Task 1.
4. **A JavaScript file (`.js`, `.mjs`).** It uses the TypeScript rules through the catalog's `aliases`, never "Not looked for". Pinned in Task 5.
5. **A library scanned as itself** (Celery). Every file imports `celery`, so a gate on that import must not open on Celery's own imports: `self.apply_async(` in `celery/canvas.py` is Celery calling itself. An application that owns `proj` and imports `celery` still opens it. Pinned in Task 5 (`negative_own_package_apply_async.py`, `positive_celery_delay.py`, `test_an_import_of_the_projects_own_package_never_satisfies_a_gate`).
6. **A config file ranked as a hotspot** (the fixture's `deploy/releases-virtualservice.yaml`). Its bundle says boundaries were not looked for, naming the language, instead of "None detected". Pinned in Task 6 (`test_bundle_says_when_a_language_has_no_boundary_rules`).

---

### Task 1: `absent_before` in the detector engine

**Satisfies:** AC-3 (the mechanism every correction uses).

**Files:**
- Modify: `scripts/detectors/__init__.py` (module docstring; `_run_regex`; `_run_file_absent`)
- Modify: `catalog/stability.yaml` (header comment, "Detector kinds")
- Modify: `tests/test_engine_v2.py`
- Modify: `tests/detectors/test_detectors.py` (`test_every_catalog_regex_compiles`, new window test)

**Interfaces:**
- Produces: detector keys `absent_before` (regex, `MULTILINE`) and `absent_before_window` (int ≥ 1); private helper `_excused_before(lines: list[str], idx: int, det: dict) -> bool` where `idx` is the hit's 0-based line index.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_engine_v2.py`:

```python
# --- #58: absent_before ------------------------------------------------------
def test_absent_before_excuses_a_regex_hit_within_its_window():
    det = {"id": "SX-py", "kind": "regex", "pattern": r"except\s*:",
           "absent_before": r"guarded\(", "absent_before_window": 3}
    near = "guarded()\ntry:\n    y()\nexcept:\n    pass\n"
    far = "guarded()\nx = 1\ntry:\n    y()\nexcept:\n    pass\n"
    assert run_detectors(_cat(det), "a.py", near, "python") == []
    assert [h.line for h in run_detectors(_cat(det), "a.py", far, "python")] == [5]


def test_absent_before_includes_the_hits_own_line():
    det = {"id": "SX-py", "kind": "regex", "pattern": r"\.add\(",
           "absent_before": r"if not (\w+):\n[^\n]*\.add\(\1\)", "absent_before_window": 1}
    assert run_detectors(_cat(det), "a.py", "if not row:\n    s.add(row)\n", "python") == []
    assert len(run_detectors(_cat(det), "a.py", "if not flag:\n    s.add(row)\n", "python")) == 1


def test_absent_before_moves_a_file_absent_hit_to_the_first_unexcused_anchor():
    det = {"id": "SX-py", "kind": "file_absent", "anchor": r"\.add\(", "absent": r"UPSERT",
           "absent_before": r"if not (\w+):\n[^\n]*\.add\(\1\)", "absent_before_window": 1}
    src = "if not row:\n    s.add(row)\nx = 1\ns.add(other)\n"
    assert [h.line for h in run_detectors(_cat(det), "a.py", src, "python")] == [4]


def test_absent_before_excusing_every_anchor_leaves_no_hit():
    det = {"id": "SX-py", "kind": "file_absent", "anchor": r"\.add\(", "absent": r"UPSERT",
           "absent_before": r"if not (\w+):\n[^\n]*\.add\(\1\)", "absent_before_window": 1}
    src = "if not row:\n    s.add(row)\nif not job:\n    s.add(job)\n"
    assert run_detectors(_cat(det), "a.py", src, "python") == []


def test_a_detector_without_absent_before_is_unchanged():
    det = {"id": "SX-py", "kind": "file_absent", "anchor": r"\.add\(", "absent": r"UPSERT"}
    src = "if not row:\n    s.add(row)\ns.add(other)\n"
    assert [h.line for h in run_detectors(_cat(det), "a.py", src, "python")] == [2]


def test_absent_before_tolerates_crlf():
    det = {"id": "SX-py", "kind": "regex", "pattern": r"except\s*:",
           "absent_before": r"try\s*:[ \t]*\n[^\n]*except", "absent_before_window": 1}
    assert run_detectors(_cat(det), "a.py", "try:\r\nexcept:\r\n    pass\r\n", "python") == []
```

Append to `tests/detectors/test_detectors.py`:

```python
def test_absent_before_always_has_a_window(catalog):
    bad = []
    for pattern in catalog["patterns"]:
        for dets in (pattern.get("detectors") or {}).values():
            for det in dets or []:
                if "absent_before" in det:
                    w = det.get("absent_before_window")
                    if not isinstance(w, int) or w < 1:
                        bad.append(det["id"])
    assert not bad, f"absent_before without an integer absent_before_window >= 1: {bad}"
```

and in `test_every_catalog_regex_compiles` change the key tuple to:

```python
                for key in ("pattern", "absent_within", "present_within", "anchor", "absent",
                            "require", "absent_before"):
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_engine_v2.py tests/detectors/test_detectors.py -q -k "absent_before or unchanged or compiles"`
Expected: FAIL in `test_absent_before_excuses_a_regex_hit_within_its_window`, `test_absent_before_includes_the_hits_own_line`, both `file_absent` tests and the CRLF test (the key is ignored today). `test_a_detector_without_absent_before_is_unchanged` and the catalog tests PASS.

- [ ] **Step 3: Write the implementation.** In `scripts/detectors/__init__.py`, add after `_snippet`:

```python
def _excused_before(lines: list[str], idx: int, det: dict) -> bool:
    """`absent_before`: drop the hit when this regex matches the
    `absent_before_window` lines before it together with its own line. A
    separate window from `window_before`, which `absent_within` and
    `present_within` share, so excusing a hit never widens what counts as one."""
    rx = det.get("absent_before")
    if not rx:
        return False
    n = max(1, int(det.get("absent_before_window", 1)))
    chunk = "\n".join(line.rstrip("\r") for line in lines[max(0, idx - n):idx + 1])
    return _rx(rx, True).search(chunk) is not None
```

In `_run_regex`, directly before `hits.append(Hit(`, add:

```python
        if _excused_before(lines, i, det):
            continue
```

In `_run_file_absent`, replace

```python
    m = anchor.search(text)
    if not m:
        return []
    line_no = text.count("\n", 0, m.start()) + 1
```

with

```python
    lines = text.split("\n")
    line_no = None
    for m in anchor.finditer(text):
        n = text.count("\n", 0, m.start()) + 1
        if not _excused_before(lines, n - 1, det):
            line_no = n  # the first anchor nothing before it excuses
            break
    if line_no is None:
        return []
```

In the module docstring, after the `module` paragraph, add:

```
Any regex or file_absent detector may set `absent_before` with
`absent_before_window`: a hit (for file_absent, an anchor) is dropped when
the regex matches that many lines before it together with its own line.
```

In `catalog/stability.yaml`'s header, after the `module` entry under "Detector kinds", add:

```yaml
#   absent_before  (regex and file_absent) a regex, with absent_before_window
#                N: the hit is dropped when it matches the N lines before the
#                hit plus the hit's own line. For file_absent each anchor is
#                tried in turn and the hit lands on the first one not excused.
#                Its window is its own, so excusing a hit never widens what
#                present_within accepts.
```

- [ ] **Step 4: Run the tests to verify they pass** (same command as Step 2), then the detector suite:

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors tests/test_engine_v2.py -q`
Expected: PASS. No catalog detector uses the key yet, so every existing sample is unchanged.

- [ ] **Step 5: Commit**

```bash
git add scripts/detectors/__init__.py catalog/stability.yaml tests/test_engine_v2.py tests/detectors/test_detectors.py
git commit -m "Detectors: absent_before excuses a hit by what precedes it (#58)"
```

---

### Task 2: S04 — a hook's except inside a discriminating retry branch

**Satisfies:** AC-3 (shape 1: `celery/backends/base.py:773`).

**Files:**
- Create: `tests/detectors/samples/S04/python/negative_hook_in_retry_branch.py`
- Modify: `catalog/stability.yaml` (`S04-py-bare-except-retry`)

- [ ] **Step 1: Write the negative sample**, reproducing Celery's `_ensure_retryable` (spec §3.2):

```python
import logging
import time

logger = logging.getLogger(__name__)


class Backend:
    max_retries = 3

    def ensure_retryable(self, func):
        retries = 0
        while True:
            try:
                return func()
            except Exception as exc:
                if self.exception_safe_to_retry(exc):
                    if retries < self.max_retries:
                        retries += 1
                        sleep_amount = min(2 ** retries, 30)
                        delay = sleep_amount / 1000
                        logger.warning("Retrying %s more times.", self.max_retries - retries)
                        try:
                            self.on_retryable_error(exc)
                        except Exception:
                            logger.exception("hook failed; continuing retry loop")
                        time.sleep(delay)
                    else:
                        raise
                else:
                    raise
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -q -k "S04-python"`
Expected: FAIL on `S04-python-negative_hook_in_retry_branch` (line 24 fires: the predicate is 8 lines above it, outside today's `window_before: 6`).

- [ ] **Step 3: Correct the detector.** In `catalog/stability.yaml`, under `S04-py-bare-except-retry`, after `window_before: 6` add:

```yaml
          # The retry decision belongs to the except whose handler checks a
          # retryability predicate. A catch-all further down that branch
          # guards something else (a hook, a log call) inside a retry that
          # already discriminates (celery backends/base.py, #58). Its own
          # window, so present_within's look-behind stays at 6.
          absent_before: '\b\w*(?:safe_to_retry|is_retryable|is_transient|should_retry)\w*\s*\('
          absent_before_window: 12
```

- [ ] **Step 4: Run the detector suite and the Celery check**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -q`
Expected: PASS, every S04 positive included.

Run: `uv run scripts/calibrate.py --repo "/tmp/thunderstruck-58/celery" --lang python --patterns S04`
Expected: exactly one hit, `S04-py-bare-except-retry celery/app/builtins.py:71`; `celery/backends/base.py:773` is gone.

- [ ] **Step 5: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S04/python/negative_hook_in_retry_branch.py
git commit -m "S04: an except inside a discriminating retry branch is not the retry decision (#58)"
```

---

### Task 3: S19 — best-effort teardown after a logged failure

**Satisfies:** AC-3 (shape 2: `celery/worker/consumer/consumer.py:435`).

**Files:**
- Create: `tests/detectors/samples/S19/python/negative_teardown_after_logged_error.py`
- Create: `tests/detectors/samples/S19/python/positive_write_after_logged_error.py`
- Create: `tests/detectors/samples/S19/python/positive_teardown_without_log.py`
- Create: `tests/detectors/samples/S19/python/positive_errback_loop.py`
- Create: `tests/detectors/samples/S19/python/positive_decode_swallow.py`
- Modify: `catalog/stability.yaml` (`S19-py-except-pass`)

- [ ] **Step 1: Write the samples.** `negative_teardown_after_logged_error.py`:

```python
import logging

logger = logging.getLogger(__name__)


class Consumer:
    def on_connection_error(self, exc):
        logger.warning("connection lost, reconnecting", exc_info=True)
        try:
            self.connection.collect(socket_timeout=2)
        except Exception:
            pass
        self.restart()
```

`positive_write_after_logged_error.py` (logged, but the swallowed call is a write, not teardown):

```python
import logging

logger = logging.getLogger(__name__)


def handle(event, store):
    logger.warning("event arrived late", exc_info=True)
    try:
        store.save(event)
    except Exception:
        pass
```

`positive_teardown_without_log.py` (teardown, but nothing logged the failure):

```python
def finish(conn):
    try:
        conn.close()
    except Exception:
        pass
```

Celery's two true S19 leads at the benchmark commit, cut down from the real code, so a correction that silences them fails the suite instead of a manual `calibrate.py` run (spec §9). `positive_errback_loop.py`:

```python
# celery/backends/base.py at 508c112 (#58): one task's errback failing is
# swallowed with no trace, and the loop goes on to the next task.
def fail_group_tasks(backend, frozen_group, group_callback, original_exc):
    for result in frozen_group.results:
        fake_request = make_request(
            task_id=result.id,
            errbacks=group_callback.options.get("link_error", []),
        )
        try:
            backend._call_task_errbacks(fake_request, original_exc, None)
        except Exception:  # pylint: disable=broad-except
            # continue on exception to be sure to iter to all the group tasks
            pass
        backend.fail_from_current_stack(result.id, exc=original_exc)
```

`positive_decode_swallow.py`:

```python
# celery/backends/database/__init__.py at 508c112 (#58): a stored value that
# fails to decode is dropped without a trace, and the result is returned
# without it.
def meta_from_row(self, data):
    raw_stamps = data.pop("stamps", None)
    if raw_stamps is not None:
        try:
            stamps_info = self.decode(raw_stamps)
            if isinstance(stamps_info, dict):
                if "stamped_headers" in stamps_info:
                    data["stamped_headers"] = stamps_info["stamped_headers"]
        except Exception:
            pass
    return self.meta_from_decoded(data)
```

- [ ] **Step 2: Run them to verify the negative fails**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -q -k "S19-python"`
Expected: FAIL on `S19-python-negative_teardown_after_logged_error`; all four new positives PASS (the two Celery ones fire on line 11 and line 12).

- [ ] **Step 3: Correct the detector.** In `catalog/stability.yaml`, under `S19-py-except-pass`, after its `note:` line add:

```yaml
          # Best-effort teardown in an error path that already logged the
          # failure with a traceback: a `try:` whose one statement closes,
          # collects or releases something, right after an exc_info log
          # (celery worker/consumer/consumer.py, #58). Both are needed: a
          # swallowed write after a log, or a swallowed close() with nothing
          # logged, still fires.
          absent_before: '(?:exc_info\s*=\s*True|\.\s*exception\s*\()[^\n]*\n(?:[^\n]*\n)*?[ \t]*try\s*:[ \t]*\n[^\n]*\b(?:close|collect|release|shutdown|cleanup|clean_up|disconnect|stop|terminate|dispose|settimeout)\w*\s*\([^\n]*\n[ \t]*except\b[^\n]*\Z'
          absent_before_window: 8
```

- [ ] **Step 4: Run the detector suite and the Celery check**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -q`
Expected: PASS.

Run: `uv run scripts/calibrate.py --repo "/tmp/thunderstruck-58/celery" --lang python --patterns S19`
Expected: 8 hits; `celery/worker/consumer/consumer.py:435` is gone, `celery/backends/base.py:489` and `celery/backends/database/__init__.py:240` remain, as their samples already show.

- [ ] **Step 5: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S19/python/
git commit -m "S19: best-effort teardown after a logged failure is not a silent swallow (#58)"
```

---

### Task 4: S07 — get-or-create is not a duplicate insert

**Satisfies:** AC-3 (shape 3: `celery/backends/database/__init__.py:168`).

**Files:**
- Create: `tests/detectors/samples/S07/python/negative_get_or_create.py`
- Create: `tests/detectors/samples/S07/python/positive_add_unguarded.py`
- Create: `tests/detectors/samples/S07/python/positive_guard_on_other_name.py`
- Modify: `catalog/stability.yaml` (`S07-py-insert-without-upsert`)

- [ ] **Step 1: Write the samples.** `negative_get_or_create.py`:

```python
def store_result(session, task_cls, task_id, result):
    task = session.query(task_cls).filter(task_cls.task_id == task_id).first()
    if not task:
        task = task_cls(task_id)
        task.task_id = task_id
        session.add(task)
        session.flush()
    task.result = result
    session.commit()
```

`positive_add_unguarded.py`:

```python
def record_payment(session, order_id, amount):
    payment = Payment(order_id=order_id, amount=amount)
    session.add(payment)
    session.commit()
```

`positive_guard_on_other_name.py` (the guard is on a flag, not on the row added):

```python
def import_rows(session, rows, dry_run):
    for row in rows:
        event = Event(**row)
        if not dry_run:
            session.add(event)
    session.commit()
```

- [ ] **Step 2: Run them to verify the negative fails**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -q -k "S07-python"`
Expected: FAIL on `S07-python-negative_get_or_create`; both new positives PASS.

- [ ] **Step 3: Correct the detector.** In `catalog/stability.yaml`, under `S07-py-insert-without-upsert`, after its `absent:` line add (leave `confidence: medium` as it is; spec §3.2):

```yaml
          # Get-or-create: the row is added only after a lookup of it found
          # nothing (`if not task:` ... `session.add(task)`), so a replay finds
          # the row (celery backends/database, #58). Per anchor: another, plain
          # insert in the same file still fires.
          absent_before: '^[ \t]*if\s+(?:not\s+(\w+)|(\w+)\s+is\s+None)\s*:[^\n]*\n(?:[^\n]*\n)*?[^\n]*\.\s*add\s*\(\s*(?:\1|\2)\s*\)[^\n]*\Z'
          absent_before_window: 4
```

- [ ] **Step 4: Run the detector suite and the Celery check**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -q`
Expected: PASS.

Run: `uv run scripts/calibrate.py --repo "/tmp/thunderstruck-58/celery" --lang python --patterns S07`
Expected: two hits, `celery/backends/cassandra.py:40` and `celery/backends/database/__init__.py:295` (the lead moved off the get-or-create at 168; 295 is the accepted unique-constraint case, spec §3.2).

- [ ] **Step 5: Commit**

```bash
git add catalog/stability.yaml tests/detectors/samples/S07/python/
git commit -m "S07: a get-or-create on the row's own key is not a duplicate insert (#58)"
```

---

### Task 5: Boundary rules in the catalog, and the matcher

**Satisfies:** AC-1 (no boundary from a comment, docstring or import), AC-2 (a variable named like a library is not a boundary, nor is a library calling its own code; a real call through the library is).

**Files:**
- Modify: `scripts/detectors/__init__.py` (add `Boundary`, `find_boundaries`, `_without_own_imports`)
- Modify: `scripts/_common.py` (add `own_packages`)
- Modify: `scripts/signals.py` (`build`: `own_packages` in `hotspots.json`, its warning in `warnings`)
- Modify: `catalog/stability.yaml` (append the `boundaries:` section)
- Create: `tests/boundaries/test_boundaries.py`
- Create: `tests/boundaries/samples/**` (50 files, Step 1)
- Create: `tests/test_own_packages.py`

**Interfaces:**
- Produces: `Boundary(label: str, rule_id: str, line: int, snippet: str)` (frozen dataclass); `find_boundaries(catalog: dict, rel_path: str, text: str, lang: str, own: dict[str, list[str]] | None) -> list[Boundary] | None` (`None`: the language has no rules; otherwise every line that matches, in line order, one rule per line; `own` as in spec §2.4); `_common.own_packages(repo_root: Path, index: dict[str, str]) -> tuple[dict[str, list[str]], list[str]]`; `hotspots.json` key `own_packages` (`{"python": [...], "typescript": [...], "java": [...]}`, sorted).
- Consumes: `build_context`, `_rx`, `_snippet` and `_common.detector_language` from the same module; `_common.tracked_index`.

- [ ] **Step 1: Write the samples.** Each path is under `tests/boundaries/samples/`. In a `positive_*` sample every line that must be tagged ends with a `boundary: <label>` comment, and exactly those lines must be tagged, with exactly those labels; any other stem carries no marker and must not be tagged with its directory's label; files under `none/` must cross no boundary. An `own-packages: …` comment names the packages the sample's project owns (spec §9).

`http/python/positive_requests_get.py`:
```python
import requests


def fetch_profile(user_id):
    return requests.get(f"https://api.example.com/users/{user_id}", timeout=5).json()  # boundary: HTTP
```

`http/python/negative_dict_named_requests.py` (Celery's worker state, AC-2):
```python
from celery.worker.state import requests


def forget(r):
    requests.pop(r.id, None)
```

`database/python/positive_session_query.py`:
```python
from sqlalchemy.orm import Session


def load(session: Session, task_id):
    return session.query(Task).filter(Task.task_id == task_id).first()  # boundary: database
```

`database/python/negative_execute_definition.py`:
```python
class Request:
    def execute(self, loglevel=None):
        """Select a subset of queues and run the task."""
        return self.run(loglevel)
```

`queue-messaging/python/positive_producer_publish.py`:
```python
def send(producer, body, routing_key):
    return producer.publish(body, routing_key=routing_key, retry=True)  # boundary: queue/messaging
```

`queue-messaging/python/negative_pool_apply_async.py`:
```python
from celery import signals


def run(pool, fn, args):
    return pool.apply_async(fn, args)
```

`queue-messaging/python/negative_own_package_apply_async.py` (Celery's own canvas, spec §2.2; fails without the own-package rule):
```python
# own-packages: celery
# Celery's own canvas: inside the library, `self.apply_async(` calls Celery's
# own code, so its import of itself is not a client import (#58).
from celery._state import current_app
from celery.utils.functional import maybe_list


class Signature(dict):
    def delay(self, *partial_args, **partial_kwargs):
        return self.apply_async(partial_args, partial_kwargs)
```

`queue-messaging/python/positive_celery_delay.py` (an application that owns `proj` still calls through `celery`):
```python
# own-packages: proj
from celery import shared_task

from proj.models import User


@shared_task
def send_welcome(user_id):
    return user_id


def register(email):
    user = User.create(email)
    send_welcome.delay(user.id)  # boundary: queue/messaging
    return user
```

`llm/python/positive_messages_create.py`:
```python
def ask(client, prompt):
    return client.messages.create(model="m", max_tokens=100, messages=[{"role": "user", "content": prompt}])  # boundary: LLM
```

`llm/python/negative_message_list.py`:
```python
def summarise(messages):
    created = [m for m in messages if m.created]
    return len(created)
```

`cloud-sdk/python/positive_boto3_client.py`:
```python
import boto3


def table():
    return boto3.client("dynamodb", region_name="eu-west-1")  # boundary: cloud SDK
```

`cloud-sdk/python/negative_boto3_in_string.py`:
```python
def explain():
    return "use boto3.client('s3') in production"
```

`filesystem/python/positive_open.py`:
```python
def read_pid(path):
    with open(path) as fh:  # boundary: filesystem
        return int(fh.read())
```

`filesystem/python/negative_open_method.py`:
```python
class Pidfile:
    def open(self):
        return self.lock.open()
```

`scheduler/python/positive_call_later.py`:
```python
def arm(hub, job, timeout, on_timeout):
    return hub.call_later(timeout, on_timeout, job)  # boundary: scheduler
```

`scheduler/python/negative_schedule_identifier.py`:
```python
def add_periodic_task(self, schedule, sig, name=None):
    scheduled_requests.clear()
    return self._entries.setdefault(name, (schedule, sig))
```

`none/python/negative_comment.py`:
```python
def noop():
    # requests.get(url) and session.query(Task) would cross a boundary here
    return None
```

`none/python/negative_docstring.py`:
```python
def noop():
    """Calls requests.get(url), producer.publish(body) and open(path)."""
    return None
```

`none/python/negative_import.py`:
```python
import requests
from sqlalchemy.orm import Session
from celery import current_app
```

`none/python/negative_definition.py`:
```python
def urlopen(url):
    return url


def open(path):
    return path
```

`http/typescript/positive_fetch.ts`:
```typescript
export async function getRelease(id: string) {
  const res = await fetch(`https://api.example.com/releases/${id}`);  // boundary: HTTP
  return res.json();
}
```

`http/typescript/negative_fetch_in_name.ts`:
```typescript
export async function batch(ids: string[]) {
  return Promise.all(ids.map(id => fetchRelease(id)));
}
```

`database/typescript/positive_prisma.ts`:
```typescript
export async function save(item: Item) {
  await db.release.create({ data: item });  // boundary: database
}
```

`database/typescript/negative_create_factory.ts`:
```typescript
export function build() {
  return Factory.create(Config.create());
}
```

`queue-messaging/typescript/positive_publish.ts`:
```typescript
export async function enqueue(message: unknown): Promise<void> {
  await broker.publish({ body: JSON.stringify(message) });  // boundary: queue/messaging
}
```

`queue-messaging/typescript/negative_enqueue_call.ts`:
```typescript
export async function retry(job: Job) {
  await enqueue({ type: "sync", id: job.id });
}
```

`llm/typescript/positive_completions.ts`:
```typescript
export async function ask(client: OpenAI, prompt: string) {
  return client.chat.completions.create({ model: "m", messages: [{ role: "user", content: prompt }] });  // boundary: LLM
}
```

`llm/typescript/negative_create_message.ts`:
```typescript
export function draft(text: string) {
  return createMessage({ text });
}
```

`cloud-sdk/typescript/positive_aws_send.ts`:
```typescript
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";

export async function get(client: S3Client, key: string) {
  return client.send(new GetObjectCommand({ Bucket: "b", Key: key }));  // boundary: cloud SDK
}
```

`cloud-sdk/typescript/negative_send_without_sdk.ts`:
```typescript
export function notify(bus: Bus) {
  bus.send(new RefreshCommand());
}
```

`filesystem/typescript/positive_read_file.ts`:
```typescript
import { readFile } from "node:fs/promises";

export async function load(path: string) {
  return JSON.parse(await readFile(path, "utf8"));  // boundary: filesystem
}
```

`filesystem/typescript/negative_reader_method.ts`:
```typescript
export function parse(reader: Reader) {
  return reader.readFileHeader();
}
```

`scheduler/typescript/positive_set_interval.ts`:
```typescript
export function start(poll: () => void) {
  return setInterval(poll, 60_000);  // boundary: scheduler
}
```

`scheduler/typescript/negative_sleep.ts`:
```typescript
export async function sleep(ms: number) {
  await new Promise(resolve => setTimeout(resolve, ms));
}
```

`none/typescript/negative_comment.ts`:
```typescript
/**
 * Calls fetch(url) and broker.publish(msg) on the caller's behalf.
 */
export function noop() {
  // await fetch(url)
  return null;
}
```

`none/typescript/negative_import.ts`:
```typescript
import axios from "axios";
import { PrismaClient } from "@prisma/client";
export { fetchRelease } from "./releases";
```

`http/java/positive_rest_template.java`:
```java
import org.springframework.web.client.RestTemplate;

class Client {
    private final RestTemplate rest;

    Profile get(String id) {
        return rest.getForObject("https://api.example.com/users/" + id, Profile.class);  // boundary: HTTP
    }
}
```

`http/java/negative_exchange_without_client.java`:
```java
class Market {
    Rate rate(Currency a, Currency b) {
        return ledger.exchange(a, b);
    }
}
```

`database/java/positive_jdbc.java`:
```java
import org.springframework.jdbc.core.JdbcTemplate;

class Repo {
    private final JdbcTemplate jdbc;

    int count() {
        return jdbc.queryForObject("SELECT count(*) FROM orders", Integer.class);  // boundary: database
    }
}
```

`database/java/negative_update_without_db.java`:
```java
class Counter {
    void tick() {
        stats.update(1);
    }
}
```

`queue-messaging/java/positive_kafka_template.java`:
```java
import org.springframework.kafka.core.KafkaTemplate;

class Publisher {
    private final KafkaTemplate<String, String> kafka;

    void publish(String event) {
        kafka.send("events", event);  // boundary: queue/messaging
    }
}
```

`queue-messaging/java/negative_send_without_broker.java`:
```java
class Mailer {
    void notify(Message m) {
        outbox.send(m);
    }
}
```

`cloud-sdk/java/positive_aws_builder.java`:
```java
import software.amazon.awssdk.services.s3.S3Client;

class Storage {
    S3Client client() {
        return S3Client.builder().build();  // boundary: cloud SDK
    }
}
```

`cloud-sdk/java/negative_builder_without_sdk.java`:
```java
class Http {
    HttpClient client() {
        return HttpClient.builder().build();
    }
}
```

`filesystem/java/positive_files_read.java`:
```java
import java.nio.file.Files;
import java.nio.file.Path;

class Config {
    String load(Path p) throws Exception {
        return Files.readString(p);  // boundary: filesystem
    }
}
```

`filesystem/java/negative_file_type.java`:
```java
class Upload {
    String name(FileInfo file) {
        return file.getName();
    }
}
```

`scheduler/java/positive_scheduled.java`:
```java
import org.springframework.scheduling.annotation.Scheduled;

class Cleanup {
    @Scheduled(fixedRate = 60000)  // boundary: scheduler
    void run() {
        purge();
    }
}
```

`scheduler/java/negative_schedule_field.java`:
```java
class Plan {
    Schedule schedule() {
        return this.schedule;
    }
}
```

`none/java/negative_comment.java`:
```java
class Noop {
    /** Calls restTemplate.getForObject(url) for the caller. */
    void run() {
        // kafka.send("events", e);
    }
}
```

`none/java/negative_import.java`:
```java
import org.springframework.web.client.RestTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import java.nio.file.Files;

class Imports {}
```

- [ ] **Step 2: Write the failing tests.** Create `tests/boundaries/test_boundaries.py`:

```python
"""Boundary rules (#58): a boundary is a call, never a name.

Samples live in tests/boundaries/samples/<label-slug>/<language>/. In a
positive_<shape> sample every line that must be tagged ends with a
`boundary: <label>` comment, and the matcher must tag exactly those lines
with exactly those labels. Any other stem must not be tagged with the
directory's label, and samples under none/ must not be tagged at all. An
`own-packages: a, b` comment names the packages the sample's project owns;
without it the project owns none. Comments are blank to the matcher, so
neither marker can change what it finds. Samples are discovered from the
tree; there is no list to update.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from detectors import find_boundaries

SAMPLES = Path(__file__).parent / "samples"
EXT_LANG = {".py": "python", ".ts": "typescript", ".java": "java"}
LABELS = {"http": "HTTP", "database": "database", "queue-messaging": "queue/messaging",
          "llm": "LLM", "cloud-sdk": "cloud SDK", "filesystem": "filesystem",
          "scheduler": "scheduler"}
NONE_SHAPES = {"python": ("comment", "docstring", "import"),
               "typescript": ("comment", "import"), "java": ("comment", "import")}


MARK = re.compile(r"(?:#|//)\s*boundary:\s*(.+?)\s*$")
OWN = re.compile(r"^\s*(?:#|//)\s*own-packages:\s*(.+?)\s*$", re.M)


def _marked(text: str) -> set[tuple[int, str]]:
    return {(i, m.group(1)) for i, line in enumerate(text.split("\n"), 1)
            if (m := MARK.search(line))}


def _own(text: str, lang: str) -> dict[str, list[str]]:
    m = OWN.search(text)
    return {lang: m.group(1).replace(",", " ").split()} if m else {}


def _cases() -> list[tuple[str, str, str, Path]]:
    return [(p.parent.parent.name, p.parent.name, p.stem, p)
            for p in sorted(SAMPLES.glob("*/*/*")) if p.suffix in EXT_LANG]


CASES = _cases()


@pytest.mark.parametrize("slug,lang,stem,path", CASES,
                         ids=[f"{s}-{lang}-{stem}" for s, lang, stem, _ in CASES])
def test_sample(catalog, slug, lang, stem, path):
    text = path.read_text(encoding="utf-8")
    found = find_boundaries(catalog, f"src/{path.name}", text, lang, _own(text, lang))
    assert found is not None, f"no boundary rules for {lang}"
    got = {(b.line, b.label) for b in found}
    seen = [(b.label, b.rule_id, b.line) for b in found]
    marked = _marked(text)
    if slug == "none":
        assert not found and not marked, f"{path} must cross no boundary, got {seen}"
    elif stem.startswith("positive"):
        assert any(label == LABELS[slug] for _, label in marked), (
            f"{path} marks no line {LABELS[slug]!r}")
        assert got == marked, f"{path}: marked {sorted(marked)}, tagged {seen}"
    else:
        assert not marked, f"{path}: a negative sample marks no line"
        assert LABELS[slug] not in {b.label for b in found}, (
            f"{path} is wrongly tagged {LABELS[slug]!r}: {seen}")


def test_every_label_with_a_rule_has_both_samples(catalog):
    missing = []
    for lang, rules in catalog["boundaries"].items():
        for label in sorted({r["label"] for r in rules}):
            slug = next(s for s, lb in LABELS.items() if lb == label)
            for polarity in ("positive", "negative"):
                if not any(c[0] == slug and c[1] == lang and c[2].startswith(polarity)
                           for c in CASES):
                    missing.append(f"{slug}/{lang}/{polarity}")
        for shape in NONE_SHAPES.get(lang, ()):
            if not any(c[0] == "none" and c[1] == lang and c[2] == f"negative_{shape}"
                       for c in CASES):
                missing.append(f"none/{lang}/negative_{shape}")
    assert not missing, "boundary rules without samples: " + ", ".join(missing)


def test_boundary_rules_are_well_formed(catalog):
    seen, bad = set(), []
    for lang, rules in catalog["boundaries"].items():
        for rule in rules:
            if rule["id"] in seen:
                bad.append(f"duplicate id {rule['id']}")
            seen.add(rule["id"])
            if rule.get("label") not in LABELS.values():
                bad.append(f"{rule['id']}: unknown label {rule.get('label')!r}")
            for key in ("pattern", "require"):
                if key in rule:
                    try:
                        re.compile(rule[key])
                    except re.error as exc:
                        bad.append(f"{rule['id']}.{key}: {exc}")
    assert not bad, "\n".join(bad)


def test_a_language_without_rules_is_not_looked_at(catalog):
    assert find_boundaries(catalog, "deploy/values.yaml", "url: http://x\n", "yaml", {}) is None


def test_javascript_uses_the_typescript_rules(catalog):
    found = find_boundaries(catalog, "a.mjs", "const r = await fetch(url);\n", "javascript", {})
    assert [(b.label, b.line) for b in found] == [("HTTP", 1)]


def test_one_label_per_line_and_line_order(catalog):
    src = ("import requests\n"
           "def sync(session):\n"
           "    rows = session.query(Row).all()\n"
           "    requests.post('https://x', json=rows, timeout=3)\n")
    found = find_boundaries(catalog, "a.py", src, "python", {})
    assert [(b.label, b.line, b.rule_id) for b in found] == [
        ("database", 3, "B-py-session"), ("HTTP", 4, "B-py-requests")]
    assert found[1].snippet == "requests.post('https://x', json=rows, timeout=3)"


def test_library_name_with_a_non_http_method_is_not_http(catalog):
    src = ("import requests\n"
           "from celery.worker.state import requests as active\n"
           "active.pop(r.id, None)\n"
           "requests.pop(r.id, None)\n"
           "requests.get(url, timeout=3)\n")
    found = find_boundaries(catalog, "a.py", src, "python", {})
    assert [(b.label, b.line) for b in found] == [("HTTP", 5)]


def test_crlf_lines_still_match(catalog):
    src = "import requests\r\nrequests.get(url, timeout=3)\r\n"
    found = find_boundaries(catalog, "a.py", src, "python", {})
    assert [(b.label, b.line) for b in found] == [("HTTP", 2)]


def test_a_malformed_rule_is_skipped(catalog):
    broken = {"boundaries": {"python": [{"id": "B-x", "label": "HTTP", "pattern": "("},
                                        *catalog["boundaries"]["python"]]},
              "aliases": {}}
    found = find_boundaries(broken, "a.py", "import requests\nrequests.get(u)\n", "python", {})
    assert [b.rule_id for b in found] == ["B-py-requests"]


@pytest.mark.parametrize("lang,src,own", [
    ("python", "import celery\nfrom celery.app import task\nx.apply_async()\n", ["celery"]),
    ("python", "import celery.app.task as t\nx.delay()\n", ["celery"]),
    ("python", "import celery, os\nx.delay()\n", ["celery"]),
    ("python", "import celery\r\nx.delay()\r\n", ["celery"]),
    ("typescript", 'import { S3Client } from "@aws-sdk/client-s3";\n'
                   'await client.send(new GetObjectCommand({}));\n', ["@aws-sdk/client-s3"]),
    ("typescript", 'const s3 = require("@aws-sdk/client-s3");\n'
                   'await client.send(new GetObjectCommand({}));\n', ["@aws-sdk/client-s3"]),
    ("java", "import org.springframework.web.client.RestTemplate;\n"
             "class A { P g() { return rest.getForObject(u, P.class); } }\n",
     ["org.springframework.web.client"]),
    ("java", "import org.springframework.web.client.*;\n"
             "class A { P g() { return rest.getForObject(u, P.class); } }\n",
     ["org.springframework.web.client"]),
])
def test_an_import_of_the_projects_own_package_never_satisfies_a_gate(catalog, lang, src, own):
    assert find_boundaries(catalog, "a", src, lang, {lang: own}) == []
    assert find_boundaries(catalog, "a", src, lang, {}), "the gate opens without own packages"


def test_a_library_import_beside_an_own_import_still_satisfies_the_gate(catalog):
    src = "import proj, requests\nfrom proj import api\nrequests.get(u, timeout=3)\n"
    found = find_boundaries(catalog, "a.py", src, "python", {"python": ["proj"]})
    assert [(b.label, b.line) for b in found] == [("HTTP", 3)]


def test_unknown_own_packages_skip_gated_rules_only(catalog):
    src = "import requests\nrequests.get(u, timeout=3)\ncur.execute(q)\n"
    found = find_boundaries(catalog, "a.py", src, "python", None)
    assert [(b.rule_id, b.line) for b in found] == [("B-py-execute", 3)]
```

Create `tests/test_own_packages.py`:

```python
"""The scanned project's own package names (#58): an import of one never
opens a boundary rule's `require` gate, so a library calling its own code is
not a call through that library."""

from __future__ import annotations

import json
import subprocess
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


def test_own_packages_come_from_tracked_files(tmp_path):
    repo = _git_repo(tmp_path / "repo", {
        "celery/__init__.py": "",
        "celery/app/__init__.py": "",
        "src/kit/__init__.py": "",
        "examples/requests/__init__.py": "",   # an example named like a library
        "docs/conf.py": "",
        "package.json": '{"name": "@acme/web"}',
        "packages/db/package.json": '{"name": "@acme/db", "private": true}',
        "broken/package.json": "{not json",
        "src/main/java/com/acme/A.java": (
            "/*\r\n * package com.wrong;\r\n */\r\npackage com.acme;\r\n\r\nclass A {}\r\n"),
        "Default.java": "class Default {}\n",
    })
    (repo / "untracked").mkdir()
    (repo / "untracked" / "__init__.py").write_text("")
    # a tracked symlink is never followed, even to a well-formed package.json
    (tmp_path / "outside.json").write_text('{"name": "leaked"}')
    (repo / "link").mkdir()
    (repo / "link" / "package.json").symlink_to(tmp_path / "outside.json")
    subprocess.run(["git", "add", "link"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "link"], cwd=repo, check=True)
    own, warnings = _common.own_packages(repo, _common.tracked_index(repo))
    assert own == {"python": ["celery", "kit"], "typescript": ["@acme/db", "@acme/web"],
                   "java": ["com.acme"]}
    assert len(warnings) == 1 and "broken/package.json" in warnings[0], warnings


def test_a_repository_with_no_packages_owns_none(tmp_path):
    repo = _git_repo(tmp_path / "repo", {"app.py": "print(1)\n"})
    assert _common.own_packages(repo, _common.tracked_index(repo)) == (
        {"python": [], "typescript": [], "java": []}, [])


def test_hotspots_record_own_packages(scanned_repo):
    data = json.loads((scanned_repo / ".thunderstruck" / "hotspots.json").read_text())
    assert data["own_packages"] == {"python": [], "typescript": ["fixture"], "java": []}
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/boundaries tests/test_own_packages.py -q`
Expected: collection error, `ImportError: cannot import name 'find_boundaries' from 'detectors'`; `tests/test_own_packages.py` fails with `AttributeError: module '_common' has no attribute 'own_packages'` and `KeyError: 'own_packages'`.

- [ ] **Step 4: Write the matcher.** Append to `scripts/detectors/__init__.py`:

```python
# ------------------------------------------------------------- boundaries --
# An import statement is never a boundary, whatever a rule says.
_IMPORT_LINE = re.compile(
    r"""^\s*(?:import\b|from\s+[\w.]+\s+import\b|export\s+[^=]*\bfrom\s+['"])""")


@dataclass(frozen=True)
class Boundary:
    label: str
    rule_id: str
    line: int
    snippet: str


# An import of the scanned project's own package never opens a `require`
# gate: inside Celery every file imports `celery`, and `self.apply_async(` there
# is Celery calling itself, not a client sending a message (#58).
_PY_FROM = re.compile(r"^[ \t]*from[ \t]+([\w.]+)[ \t]+import\b")
_PY_IMPORT = re.compile(r"^([ \t]*import[ \t]+)([\w. \t,]+?)[ \t]*$")
_JAVA_IMPORT = re.compile(r"^[ \t]*import[ \t]+(?:static[ \t]+)?([\w.]+?)(?:\.\*)?[ \t]*;")
_TS_SPECIFIER = re.compile(r"""(\b(?:from|import|require)\s*\(?\s*)(['"])([^'"\n]+)\2""")


def _own_module(module: str, own: frozenset[str]) -> bool:
    return module.split(".")[0] in own


def _without_own_imports(code: str, det_lang: str, own: frozenset[str]) -> str:
    """`code` with every import of the project's own packages removed: what a
    boundary rule's `require` is searched in."""
    if not own:
        return code
    if det_lang == "typescript":
        def blank(m: re.Match) -> str:
            spec = m.group(3)
            if any(spec == n or spec.startswith(n + "/") for n in own):
                return m.group(1) + "''"
            return m.group(0)
        return _TS_SPECIFIER.sub(blank, code)
    out = []
    for line in code.split("\n"):
        line = line.rstrip("\r")
        if det_lang == "python":
            m = _PY_FROM.match(line)
            if m and _own_module(m.group(1), own):
                line = ""
            elif (m := _PY_IMPORT.match(line)):
                # `import celery, os` keeps `import os`
                items = [x.strip() for x in m.group(2).split(",") if x.strip()]
                kept = [x for x in items if not _own_module(x.split()[0], own)]
                if len(kept) < len(items):
                    line = m.group(1) + ", ".join(kept) if kept else ""
        elif det_lang == "java":
            m = _JAVA_IMPORT.match(line)
            if m:
                parts = m.group(1).split(".")
                if any(".".join(parts[:k]) in own for k in range(1, len(parts) + 1)):
                    line = ""
        out.append(line)
    return "\n".join(out)


def find_boundaries(catalog: dict[str, Any], rel_path: str, text: str,
                    lang: str, own: dict[str, list[str]] | None) -> list[Boundary] | None:
    """Every line that calls across a boundary, by the catalog's `boundaries`
    rules, in line order and one rule per line (the first that matches).
    None when the language has no rules, so a caller can say it never looked.

    `own` is hotspots.json's `own_packages`. None means the project's own
    package names are unknown: every rule with a `require` is skipped rather
    than opened by the project's imports of itself."""
    det_lang = _common.detector_language(catalog, lang)
    rules = (catalog.get("boundaries") or {}).get(det_lang)
    if not rules:
        return None
    ctx = build_context(rel_path, text, lang)
    gate = (None if own is None else
            _without_own_imports(ctx.code_text, det_lang, frozenset(own.get(det_lang) or ())))
    active: list[tuple[str, str, re.Pattern]] = []
    for rule in rules:
        try:
            if rule.get("require") and (gate is None
                                        or not _rx(rule["require"], True).search(gate)):
                continue  # the call goes through a library this file never imports
            active.append((rule["label"], rule["id"], _rx(rule["pattern"])))
        except re.error:
            continue  # a malformed catalog regex must not sink the scan
    out: list[Boundary] = []
    for i, line in enumerate(ctx.code_lines, 1):
        line = line.rstrip("\r")
        if not line.strip() or _IMPORT_LINE.match(line):
            continue
        for label, rule_id, rx in active:
            if rx.search(line):
                out.append(Boundary(label, rule_id, i, _snippet(ctx, i)[:120]))
                break
    return out
```

- [ ] **Step 5: Work out the project's own packages (spec §2.3).** Append to `scripts/_common.py` (it already imports `json` and `re`):

```python
# ---------------------------------------------------------- own packages --
# The scanned project's own package names, per detector language (#58): an
# import of one never opens a boundary rule's `require` gate, so a library
# calling its own code (`self.apply_async(` inside Celery) is not a call
# through that library. Worked out from tracked files only, so it is a
# function of the commit.
_JAVA_PACKAGE = re.compile(r"^package[ \t]+([\w.]+)[ \t]*;")
_REGULAR_FILE = ("100644", "100755")


def own_packages(repo_root: Path, index: dict[str, str]) -> tuple[dict[str, list[str]], list[str]]:
    """({"python": [...], "typescript": [...], "java": [...]}, warnings), each
    list sorted.

    python      every directory at the root, or directly under a root src/,
                that holds a tracked __init__.py
    typescript  the "name" of every tracked package.json
    java        the first `package <name>;` line of every tracked .java file

    Only regular files are read; a symlink is never followed. A file that
    cannot be read or parsed is skipped, and one warning names the first.
    """
    py: set[str] = set()
    ts: set[str] = set()
    java: set[str] = set()
    unreadable: list[str] = []
    for rel in sorted(index):
        parts = rel.split("/")
        if parts[-1] in ("__init__.py", "__init__.pyi"):
            if (len(parts) == 2 or (len(parts) == 3 and parts[0] == "src")) \
                    and parts[-2].isidentifier():
                py.add(parts[-2])
            continue
        if index[rel] not in _REGULAR_FILE:
            continue
        if parts[-1] == "package.json":
            try:
                doc = json.loads((repo_root / rel).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                unreadable.append(rel)
                continue
            name = doc.get("name") if isinstance(doc, dict) else None
            if isinstance(name, str) and name.strip():
                ts.add(name.strip())
        elif rel.endswith(".java"):
            try:
                with open(repo_root / rel, encoding="utf-8", errors="replace") as fh:
                    m = next((m for m in map(_JAVA_PACKAGE.match, fh) if m), None)
            except OSError:
                unreadable.append(rel)
                continue
            if m:
                java.add(m.group(1))
    warnings = []
    if unreadable:
        warnings.append(
            f"{len(unreadable)} tracked file(s) could not be read for the project's own "
            f"package names (first: {unreadable[0]}); a call through a package one of "
            f"them declares may be listed as a library boundary.")
    return {"python": sorted(py), "typescript": sorted(ts), "java": sorted(java)}, warnings
```

In `scripts/signals.py`, in `build`, directly after `index = c.tracked_index(repo)` add:

```python
    own, own_warnings = c.own_packages(repo, index)
    warnings.extend(own_warnings)
```

and in the returned dict, directly after `"warnings": warnings,` add `"own_packages": own,`.

- [ ] **Step 6: Add the rules.** Append to the end of `catalog/stability.yaml`:

```yaml

# ------------------------------------------------------------- boundaries --
# Where a file calls out of the process: the "External boundaries" section of
# every bundle. A boundary is a CALL, never a name: a rule matches one line of
# comment-stripped text (comments and Python docstrings blank, strings kept),
# an import line never counts, and the first rule in this order wins a line.
# A call through a library's own name (`requests.get(`) carries a `require`
# on that library's import, so a variable that shares the name
# (`requests.pop(...)` on a dict) is not a boundary. A method only a boundary
# client has (`.execute(`, `.publish(`) carries none, because services reach
# it through an injected client. Samples: tests/boundaries/samples/.
boundaries:
  python:
    - id: B-py-requests
      label: HTTP
      pattern: '\b(?:requests|httpx)\s*\.\s*(?:get|post|put|patch|delete|head|options|request|stream)\s*\('
      require: '^\s*(?:import|from)\s+(?:requests|httpx)\b'
    - id: B-py-urlopen
      label: HTTP
      pattern: '(?<!def )\burlopen\s*\('
      require: '^\s*(?:import|from)\s+urllib\b'
    - id: B-py-aiohttp
      label: HTTP
      pattern: '\baiohttp\s*\.\s*(?:ClientSession|request)\s*\('
      require: '^\s*(?:import|from)\s+aiohttp\b'
    - id: B-py-execute
      label: database
      pattern: '\.\s*(?:execute|executemany|executescript)\s*\('
    - id: B-py-session
      label: database
      pattern: '\b\w*session\s*\.\s*(?:query|scalars?|commit|flush|add|add_all|merge)\s*\('
    - id: B-py-django-orm
      label: database
      pattern: '\.objects\s*\.\s*\w+\s*\('
      require: '^\s*(?:import|from)\s+django\b'
    - id: B-py-sql
      label: database
      pattern: '\b(?:SELECT\s[^\n]*\bFROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b'
    - id: B-py-broker
      label: queue/messaging
      pattern: '\.\s*(?:publish|basic_publish|basic_consume|basic_get|drain_events|send_message|send_messages|receive_message)\s*\('
    - id: B-py-celery-send
      label: queue/messaging
      # Not a process pool's apply_async: that is multiprocessing.
      pattern: '(?<!pool)(?<!Pool)\s*\.\s*(?:apply_async|send_task|delay)\s*\('
      require: '^\s*(?:import|from)\s+celery\b'
    - id: B-py-llm
      label: LLM
      pattern: '\.\s*(?:chat\s*\.\s*)?(?:completions|messages|embeddings|responses)\s*\.\s*create\s*\(|\.\s*generate_content\s*\('
    - id: B-py-boto3
      label: cloud SDK
      pattern: '\bboto3\s*\.\s*(?:client|resource|Session)\s*\('
      require: '^\s*import\s+boto3\b'
    - id: B-py-file
      label: filesystem
      pattern: '(?<![\w.])(?<!def )open\s*\(|\.\s*(?:read_text|write_text|read_bytes|write_bytes)\s*\('
    - id: B-py-scheduler
      label: scheduler
      pattern: '\bschedule\s*\.\s*every\s*\(|\b(?:Background|Blocking|AsyncIO)Scheduler\s*\(|\.\s*add_job\s*\(|\bthreading\s*\.\s*Timer\s*\(|\.\s*call_later\s*\(|\.\s*add_periodic_task\s*\('
  typescript:
    - id: B-ts-fetch
      label: HTTP
      pattern: '(?<![\w.$])(?<!function )(?<!async )fetch\s*\('
    - id: B-ts-axios
      label: HTTP
      pattern: '\baxios\s*(?:\.\s*(?:get|post|put|patch|delete|head|request)\s*)?\('
      require: '[''"]axios[''"]'
    - id: B-ts-http-clients
      label: HTTP
      pattern: '\b(?:got|superagent|ky)\s*(?:\.\s*(?:get|post|put|patch|delete)\s*)?\('
      require: '[''"](?:got|superagent|ky)[''"]'
    - id: B-ts-undici
      label: HTTP
      pattern: '\b(?:undici\s*\.\s*)?request\s*\('
      require: '[''"]undici[''"]'
    - id: B-ts-node-http
      label: HTTP
      pattern: '\bhttps?\s*\.\s*(?:get|request)\s*\('
      require: '[''"](?:node:)?https?[''"]'
    - id: B-ts-prisma
      label: database
      pattern: '\b(?:db|prisma|tx)\s*\.\s*\w+\s*\.\s*(?:create|createMany|findMany|findUnique|findFirst|update|updateMany|upsert|delete|deleteMany|count|aggregate)\s*\(|\$(?:queryRaw|executeRaw)\w*'
    - id: B-ts-query
      label: database
      pattern: '\.\s*query\s*\('
    - id: B-ts-sql
      label: database
      pattern: '\b(?:SELECT\s[^\n]*\bFROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b'
    - id: B-ts-broker
      label: queue/messaging
      pattern: '\.\s*(?:publish|sendMessage|sendMessageBatch)\s*\(|\bnew\s+(?:SendMessage|SendMessageBatch|Publish)Command\s*\('
    - id: B-ts-llm
      label: LLM
      pattern: '\.\s*(?:chat\s*\.\s*)?(?:completions|messages|embeddings|responses)\s*\.\s*create\s*\(|\.\s*generateContent\s*\('
    - id: B-ts-aws-sdk
      label: cloud SDK
      pattern: '\.\s*send\s*\(\s*new\s+\w+Command\s*\('
      require: '[''"]@aws-sdk/[\w-]+[''"]'
    - id: B-ts-file
      label: filesystem
      pattern: '\bfs(?:Promises)?\s*\.\s*(?:promises\s*\.\s*)?(?:read|write|append)\w*\s*\(|(?<![\w.])(?:readFile|writeFile|appendFile)(?:Sync)?\s*\('
    - id: B-ts-scheduler
      label: scheduler
      # Not setTimeout: in the code this tool reads it is a sleep (S02's job).
      pattern: '\bsetInterval\s*\(|\bcron\s*\.\s*schedule\s*\(|\bnew\s+CronJob\s*\(|@Cron\s*\(|@Interval\s*\('
  java:
    - id: B-java-http
      label: HTTP
      pattern: '\.\s*(?:getForObject|getForEntity|postForObject|postForEntity|patchForObject|exchange)\s*\(|\.\s*retrieve\s*\(\s*\)|\.\s*newCall\s*\(|\bhttpClient\s*\.\s*send(?:Async)?\s*\('
      require: '^\s*import\s+(?:org\.springframework\.web\.(?:client|reactive)|java\.net\.http|okhttp3|org\.apache\.hc|org\.apache\.http|feign)\b'
    - id: B-java-db
      label: database
      pattern: '\.\s*(?:query|queryForObject|queryForList|queryForMap|update|batchUpdate|executeQuery|executeUpdate|execute|createQuery|createNativeQuery|find|persist|merge)\s*\('
      require: '^\s*import\s+(?:java\.sql|javax\.sql|org\.springframework\.jdbc|jakarta\.persistence|javax\.persistence|org\.hibernate|org\.jooq)\b'
    - id: B-java-sql
      label: database
      pattern: '\b(?:SELECT\s[^\n]*\bFROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b'
    - id: B-java-messaging
      label: queue/messaging
      pattern: '\.\s*(?:send|convertAndSend|publish|basicPublish|sendMessage)\s*\(|@(?:KafkaListener|RabbitListener|JmsListener|SqsListener)\b'
      require: '^\s*import\s+(?:org\.springframework\.(?:kafka|amqp|jms)|org\.apache\.kafka|com\.rabbitmq|software\.amazon\.awssdk\.services\.sq[sn]|io\.awspring|jakarta\.jms|javax\.jms)\b'
    - id: B-java-aws-sdk
      label: cloud SDK
      pattern: '\b\w+Client\s*\.\s*builder\s*\(\s*\)'
      require: '^\s*import\s+software\.amazon\.awssdk\b'
    - id: B-java-file
      label: filesystem
      pattern: '\bFiles\s*\.\s*(?:read|write|newBuffered|newInput|newOutput|lines|copy|move|delete)\w*\s*\(|\bnew\s+File(?:Input|Output)Stream\s*\(|\bnew\s+File(?:Reader|Writer)\s*\('
      require: '^\s*import\s+java\.(?:nio\.file|io)\b'
    - id: B-java-scheduler
      label: scheduler
      pattern: '@Scheduled\b|\.\s*schedule(?:AtFixedRate|WithFixedDelay)?\s*\('
      require: '^\s*import\s+(?:org\.springframework\.scheduling|java\.util\.concurrent)\b'
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/boundaries tests/test_own_packages.py tests/detectors -q`
Expected: PASS (50 sample cases plus the rule and own-package tests; the detector suite is unaffected, since `run_detectors` reads only `patterns`).

- [ ] **Step 8: Commit**

```bash
git add scripts/detectors/__init__.py scripts/_common.py scripts/signals.py catalog/stability.yaml tests/boundaries/ tests/test_own_packages.py
git commit -m "Boundaries: call-shaped catalog rules with samples, not vocabularies (#58)"
```

---

### Task 6: The bundle uses the catalog's boundaries

**Satisfies:** AC-1.

**Files:**
- Modify: `scripts/bundle.py` (delete `BOUNDARY_PATTERNS`; rewrite `section_boundaries`; its call in `build_bundle`; a warning in `main`; the import block)
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `detectors.find_boundaries`, `detectors.Boundary`, `hotspots.json`'s `own_packages` (Task 5).
- Produces: `section_boundaries(text: str, rel: str, lang: str, catalog: dict, own: dict[str, list[str]] | None) -> str`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_pipeline.py`:

```python
def _boundaries_section(scanned_repo, rel: str) -> str:
    index = json.loads((scanned_repo / ".thunderstruck" / "bundles" / "index.json").read_text())
    entry = next(b for b in index["bundles"] if b["file"] == rel)
    body = (scanned_repo / ".thunderstruck" / "bundles" / f"{entry['id']}.md").read_text()
    return body.split("## External boundaries", 1)[1].split("\n## ", 1)[0]


def test_bundle_lists_calls_not_sleeps_as_boundaries(scanned_repo):
    section = _boundaries_section(scanned_repo, "src/client/releases.ts")
    assert "fetch(`https://api.example.com/releases/" in section
    assert "setTimeout" not in section and "**scheduler**" not in section
    assert "A call through a wrapper or an injected client" in section


def test_bundle_says_when_a_language_has_no_boundary_rules(catalog):
    # The fixture's VirtualService ranks only with a larger --top than
    # scanned_repo uses, so the section is built directly.
    import bundle
    text = "kind: VirtualService\nspec:\n  http:\n    - route: []\n"
    section = bundle.section_boundaries(text, "deploy/releases-virtualservice.yaml", "yaml",
                                       catalog, {})
    assert section == ("## External boundaries\n\nNot looked for: no boundary rules exist "
                       "for yaml files.\n\n")


def test_bundle_shows_no_boundary_from_a_comment(scanned_repo):
    section = _boundaries_section(scanned_repo, "src/sync/scheduler.ts")
    assert "None detected in this file." in section


def test_bundle_says_when_own_packages_are_unknown(catalog):
    import bundle
    text = "import requests\n\n\ndef get(u):\n    return requests.get(u, timeout=3)\n"
    assert bundle.section_boundaries(text, "src/a.py", "python", catalog, None) == (
        "## External boundaries\n\nNone detected in this file.\n\n"
        "Calls through a library's own name were not looked for: the project's "
        "own package names are not recorded with the hotspots.\n\n")
    assert "requests.get(u, timeout=3)" in bundle.section_boundaries(
        text, "src/a.py", "python", catalog, {})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_pipeline.py -q -k "boundar"`
Expected: FAIL on all four (today `releases.ts` lists `setTimeout` under **scheduler**, `section_boundaries` takes two arguments, and `scheduler.ts` tags `fetchRelease(` and a comment).

- [ ] **Step 3: Rewrite the section.** In `scripts/bundle.py`:

1. Delete the whole `BOUNDARY_PATTERNS: list[tuple[str, re.Pattern]] = [ … ]` assignment.
2. After `import _common as c  # noqa: E402` add `from detectors import Boundary, find_boundaries  # noqa: E402`.
3. Replace `section_boundaries` entirely with:

```python
def section_boundaries(text: str, rel: str, lang: str, catalog: dict,
                       own: dict[str, list[str]] | None) -> str:
    found = find_boundaries(catalog, rel, text, lang, own)
    if found is None:
        return (f"## External boundaries\n\nNot looked for: no boundary rules exist "
                f"for {lang} files.\n\n")
    gap = ([] if own is not None else
           ["Calls through a library's own name were not looked for: the project's "
            "own package names are not recorded with the hotspots.", ""])
    shown: dict[str, list[Boundary]] = {}
    for b in found:
        shown.setdefault(b.label, [])
        if len(shown[b.label]) < 4:
            shown[b.label].append(b)
    if not shown:
        return "\n".join(["## External boundaries", "", "None detected in this file.", "",
                          *gap, ""])
    out = ["## External boundaries crossed in this file", "",
           "Calls that match a boundary rule: a client library's call, or a method "
           "only a boundary client has. A call through a wrapper or an injected "
           "client of another name is not listed.", "", *gap]
    for label, entries in shown.items():
        out.append(f"**{label}**")
        for b in entries:
            out.append(f"- `{rel}:{b.line}` — `{b.snippet}`")
        out.append("")
    return "\n".join(out)
```

4. In `build_bundle`, directly after `text = c.read_text(repo / hs["file"]) or ""` add

```python
    own = data.get("own_packages")
    own = own if isinstance(own, dict) else None  # None: gated boundary rules skipped
```

and change `section_boundaries(text, hs["file"]),` to `section_boundaries(text, hs["file"], hs["language"], catalog, own),`.
5. In `main`, directly before `dest_dir = c.out_dir(repo) / "bundles"` add (spec §8):

```python
    if not isinstance(data.get("own_packages"), dict):
        print("warning: hotspots.json records no own package names (written before "
              "#58); calls through a library's own name are not listed as boundaries. "
              "Re-run signals.py.", file=sys.stderr)
```

6. In the module docstring, change "the boundaries it crosses" to "the boundary calls the catalog's rules find".

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_pipeline.py -q`
Expected: PASS, including `test_bundles_are_within_budget_and_deterministic` and `test_bundle_contains_the_sections_the_investigator_needs`.

- [ ] **Step 5: Measure Celery (AC-1).** Save as `/tmp/thunderstruck-58/count_boundaries.py` (not in the repository):

```python
"""Count the boundary lines in a scan's bundles, and how many come from a
comment, a docstring or an import (#58 AC-1).

    uv run --no-project --with pyyaml python count_boundaries.py <plugin> <repo> <bundles-dir>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "scripts"))
import _common as c  # noqa: E402

IMPORT = re.compile(r"""^\s*(?:import\b|from\s+[\w.]+\s+import\b|export\s+[^=]*\bfrom\s+['"])""")
REF = re.compile(r"^- `([^`:]+):(\d+)` — ")
LANG = {".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "typescript",
        ".java": "java"}

repo, bundles = Path(sys.argv[2]), Path(sys.argv[3])
total = bad = 0
for md in sorted(bundles.glob("H*.md")):
    body = md.read_text()
    section = body.split("## External boundaries", 1)[1].split("\n## ", 1)[0]
    shown = noise = 0
    for line in section.splitlines():
        m = REF.match(line)
        if not m:
            continue
        rel, n = m.group(1), int(m.group(2))
        text = (repo / rel).read_text()
        lang = LANG.get(Path(rel).suffix)
        code = c.strip_comments(text, lang).split("\n") if lang else text.split("\n")
        shown += 1
        if not code[n - 1].strip() or IMPORT.match(text.split("\n")[n - 1]):
            noise += 1
    print(f"{md.name}: {shown} shown, {noise} from a comment, docstring or import")
    total, bad = total + shown, bad + noise
print(f"total: {total} shown, {bad} from a comment, docstring or import")
```

Run:

```bash
uv run --no-project --with pyyaml python "/tmp/thunderstruck-58/count_boundaries.py" . "/tmp/thunderstruck-58/celery" docs/calibration/correctness/celery/scan/bundles
rm -rf "/tmp/thunderstruck-58/celery/.thunderstruck"
uv run scripts/signals.py --repo "/tmp/thunderstruck-58/celery" --top 10 --since 2025-10-03
uv run scripts/bundle.py --repo "/tmp/thunderstruck-58/celery"
uv run --no-project --with pyyaml python "/tmp/thunderstruck-58/count_boundaries.py" . "/tmp/thunderstruck-58/celery" "/tmp/thunderstruck-58/celery/.thunderstruck/bundles"
```

Expected: `total: 68 shown, 51 from a comment, docstring or import` for the frozen bundles, and `total: 11 shown, 0 from a comment, docstring or import` after, with `hotspots.json`'s `own_packages` `{"python": ["celery", "t"], "typescript": [], "java": []}` and the ten bundles at 48,637 estimated tokens in total (`index.json`'s `tokens_estimated`; spec §2.6). Keep both outputs for Task 8 and the PR.

- [ ] **Step 6: Commit**

```bash
git add scripts/bundle.py tests/test_pipeline.py
git commit -m "Bundle: boundaries from the catalog, and say when none were looked for (#58)"
```

---

### Task 7: The coverage section says what a lead means

**Satisfies:** AC-5.

**Files:**
- Modify: `scripts/report.py` (constants; the section in `render_markdown`; docstrings at the top and in `coverage_rows`)
- Modify: `templates/report.html` (the Overview section and the rail's summary line)
- Modify: `skills/thunderstruck-scan/references/report-format.md` (`coverage_rows` line)
- Modify: `README.md` (the `report.md` row of the output table)
- Modify: `tests/test_pipeline.py`, `tests/test_coverage_gaps.py`, `tests/test_report_json_fields.py`, `tests/test_report_html_browser.py`
- Create: `tests/test_lead_wording.py`
- Regenerate: `examples/sample-report.md`, `examples/sample-report.html`

**Interfaces:**
- Produces: `report.LEADS_HEADING`, `report.LEADS_INTRO`, `report.LEADS_FOOTNOTE` (str).

- [ ] **Step 1: Write the failing tests.** Create `tests/test_lead_wording.py`:

```python
"""The lead table states what a lead and no lead mean (#58 AC-5)."""

from __future__ import annotations

import report

TEMPLATE = report.c.plugin_root() / "templates" / "report.html"


def test_the_wording_says_what_a_lead_and_no_lead_mean():
    assert report.LEADS_HEADING == "Detector leads by pattern"
    assert "never proof that the pattern is missing" in report.LEADS_INTRO
    assert "a lead describes the default the code ships with" in report.LEADS_INTRO
    assert "does not mean the pattern is present" in report.LEADS_FOOTNOTE
    for text in (report.LEADS_HEADING, report.LEADS_INTRO, report.LEADS_FOOTNOTE):
        assert "coverage" not in text.lower() and "covered" not in text.lower()


def test_the_html_template_carries_the_same_words():
    template = TEMPLATE.read_text(encoding="utf-8")
    for text in (report.LEADS_HEADING, report.LEADS_INTRO, report.LEADS_FOOTNOTE):
        assert text in template, text
    assert "Pattern coverage" not in template
    assert "Run, coverage," not in template

```

(`report.py` imports `_common as c`, and the tests import `report` from `scripts/` through `conftest.py`'s `sys.path`, as `tests/test_report_json_fields.py` does.)

In `tests/test_pipeline.py`, in `test_report_renders_and_indexes`, replace `assert "## Pattern coverage" in report` with:

```python
    import report as report_py
    section = report.split(f"## {report_py.LEADS_HEADING}", 1)[1].split("\n## ", 1)[0]
    assert report_py.LEADS_INTRO in section and report_py.LEADS_FOOTNOTE in section
    assert "coverage" not in section.lower() and "## Pattern coverage" not in report
```
 In `tests/test_coverage_gaps.py` change `report.index("## Pattern coverage")` to `report.index("## Detector leads by pattern")`. In `tests/test_report_json_fields.py` change `markdown.split("## Pattern coverage", 1)` to `markdown.split("## Detector leads by pattern", 1)`. In `tests/test_report_html_browser.py` change `"Pattern coverage",` in the expected section list to `"Detector leads by pattern",`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_lead_wording.py tests/test_pipeline.py tests/test_coverage_gaps.py tests/test_report_json_fields.py -q`
Expected: FAIL (`AttributeError: module 'report' has no attribute 'LEADS_HEADING'`, and the renamed heading is not found).

- [ ] **Step 3: Change `report.py`.** Near the other module constants add:

```python
# The lead table's words (#58). templates/report.html carries the same strings;
# tests/test_lead_wording.py keeps the two identical.
LEADS_HEADING = "Detector leads by pattern"
LEADS_INTRO = ("Each row is a stability pattern the detectors searched for. A lead is a line "
               "where a detector's text rule matched: a place to read, never a finding, and "
               "never proof that the pattern is missing. Where code leaves a setting to its "
               "caller, as a library's configurable timeout does, a lead describes the default "
               "the code ships with, not every deployment. Leads read counts the leads inside "
               "investigated hotspots; leads confirmed counts those a validated finding cites.")
LEADS_FOOTNOTE = ("No lead means no line matched a detector's rule. It does not mean the "
                  "pattern is present: a detector sees only the shapes its rule describes.")
```

In `render_markdown`, replace

```python
    L += ["## Pattern coverage", "",
          "Leads are detector hits — mechanical, noisy, and never a finding on "
          "their own. Findings are what survived an investigator reading the code. "
          "*Leads read* counts the hits inside investigated hotspots; *Leads "
          "confirmed* counts those a validated finding cites.",
          "",
```

with

```python
    L += [f"## {LEADS_HEADING}", "", LEADS_INTRO, "",
```

and replace

```python
    L += ["", "<sub>“0” leads means no file matched the detector's anchor. It "
          "does not mean the pattern is present.</sub>", ""]
```

with

```python
    L += ["", f"<sub>{LEADS_FOOTNOTE}</sub>", ""]
```

Change the comment `# ---- coverage table` to `# ---- lead table`, the module docstring's "run header, pattern coverage, ranked findings" to "run header, detector leads by pattern, ranked findings", and `coverage_rows`'s docstring to `"""The **Detector leads by pattern** table, one dict per row in report.md order.`.

- [ ] **Step 4: Change the template.** In `templates/report.html`, replace the block

```javascript
        el.appendChild(section("Pattern coverage", [
          para("Leads are detector hits — mechanical, noisy, and never a finding on their own. Findings are what " +
            "survived an investigator reading the code. Leads read counts the hits inside investigated hotspots; " +
            "leads confirmed counts those a validated finding cites."),
```

with

```javascript
        el.appendChild(section("Detector leads by pattern", [
          para("Each row is a stability pattern the detectors searched for. A lead is a line where a detector's text rule matched: a place to read, never a finding, and never proof that the pattern is missing. Where code leaves a setting to its caller, as a library's configurable timeout does, a lead describes the default the code ships with, not every deployment. Leads read counts the leads inside investigated hotspots; leads confirmed counts those a validated finding cites."),
```

replace

```javascript
          para("“0” leads means no file matched the detector's anchor. It does not mean the pattern is present.", "foot-note")
```

with

```javascript
          para("No lead means no line matched a detector's rule. It does not mean the pattern is present: a detector sees only the shapes its rule describes.", "foot-note")
```

and replace `"Run, coverage, hotspots, and what was not analysed"` with `"Run, leads, hotspots, and what was not analysed"`. Each string stays on one source line so the template test finds it verbatim.

- [ ] **Step 5: Change the docs.** In `skills/thunderstruck-scan/references/report-format.md` change `- \`coverage_rows\`: the **Pattern coverage** table, in order:` to `- \`coverage_rows\`: the **Detector leads by pattern** table, in order:`.

In `README.md`, in the table of files written to `.thunderstruck/`, change the `report.md` row's text `pattern coverage with leads read and confirmed` to `detector leads by pattern (what a lead and no lead mean, leads read and confirmed)`.

- [ ] **Step 6: Regenerate the samples and run the tests**

```bash
uv run scripts/gen_sample_report.py
uv run --with pytest --with pyyaml --with lizard pytest tests/test_lead_wording.py tests/test_pipeline.py tests/test_coverage_gaps.py tests/test_report_json_fields.py tests/test_report_html.py tests/test_sample_report.py -q
THUNDERSTRUCK_REQUIRE_BROWSER=1 uv run --with pytest --with pyyaml --with lizard --with playwright==1.56.0 pytest tests/test_report_html_browser.py -q
```

Expected: PASS. `git diff examples/` shows only the heading, intro and footnote in `sample-report.md`, and the same text plus the rail line and the script hash in `sample-report.html`.

- [ ] **Step 7: Commit**

```bash
git add scripts/report.py templates/report.html skills/thunderstruck-scan/references/report-format.md README.md tests/ examples/sample-report.md examples/sample-report.html
git commit -m "Report: the lead table says what a lead and no lead mean (#58)"
```

---

### Task 8: The Celery calibration log and the measurements

**Satisfies:** AC-1 (count recorded), AC-3 (no true positive lost elsewhere), AC-4, AC-6.

**Files:**
- Create: `docs/calibration/celery.md`
- Modify: `docs/calibration/python.md` (one pointer line under **Known limitations**)

- [ ] **Step 1: Sweep Celery before and after.**

The "before" side is this branch's merge base with `main` (the code before any task of this plan), unpacked into a scratch directory (no stash, no second checkout of this worktree):

```bash
mkdir -p "/tmp/thunderstruck-58/before" && git archive "$(git merge-base HEAD origin/main)" | tar -x -C "/tmp/thunderstruck-58/before"
uv run --directory "/tmp/thunderstruck-58/before" scripts/calibrate.py --repo "/tmp/thunderstruck-58/celery" --lang all --patterns all > "/tmp/thunderstruck-58/celery-before.txt"
uv run scripts/calibrate.py --repo "/tmp/thunderstruck-58/celery" --lang all --patterns all > "/tmp/thunderstruck-58/celery-after.txt"
diff "/tmp/thunderstruck-58/celery-before.txt" "/tmp/thunderstruck-58/celery-after.txt"
```

Expected: 27 hits before and 25 after, all Python. The diff removes `S04 … celery/backends/base.py:773` and `S19 … celery/worker/consumer/consumer.py:435`, and moves `S07 … database/__init__.py:168` to `:295`.

- [ ] **Step 2: Sweep the five `python.md` repositories for lost true positives.** Clone each at the commit `python.md` pins (fastapi/full-stack-fastapi-template `cb740b6…`, netbox-community/netbox `785d0b9…`, httpie/cli `5b604c3…`, celery/celery `eb3dfa3…`, rq/rq `90a67a1…`; full SHAs in `python.md`'s table) into `/tmp/thunderstruck-58/py/<name>`, then for each:

```bash
uv run --directory "/tmp/thunderstruck-58/before" scripts/calibrate.py --repo "/tmp/thunderstruck-58/py/<name>" --lang python --patterns S04,S07,S19 > "/tmp/thunderstruck-58/py/<name>.before"
uv run scripts/calibrate.py --repo "/tmp/thunderstruck-58/py/<name>" --lang python --patterns S04,S07,S19 > "/tmp/thunderstruck-58/py/<name>.after"
diff "/tmp/thunderstruck-58/py/<name>.before" "/tmp/thunderstruck-58/py/<name>.after"
```

Every line that disappears is looked up in `python.md`'s judgments. Then:

- **It was judged FP** (fixed or accepted): list it under **Silences checked** in Step 3.
- **It has no judgment in `python.md`:** stop. Do not judge it yourself; label the ticket `agent:blocked` and comment with the detector, repository, `file:line` and the code, so the maintainer judges it.
- **It was judged TP:** add a `positive_<shape>` sample reproducing it to the task that silenced it (Task 2, 3 or 4), tighten that `absent_before` until the sample fires and the Celery negative stays silent, and re-run this step. If that cannot be done for S04 or S19, record the hit under **Lost** in Step 3 and lower that detector's `confidence` one step in the same commit (AC-3). If it cannot be done for **S07**, stop and label the ticket `agent:blocked`: S07 must stay `medium` (spec §3.2), so the trade between the lost lead and the ranking is the maintainer's call.

- [ ] **Step 3: Write `docs/calibration/celery.md`** in the form of `python.md`, with these sections, every hit of `celery-after.txt` listed under its detector, and every judgment re-checked by reading the code at `508c112` (line numbers moved since `python.md`'s commit):

```markdown
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
| celery/celery | library and worker | `508c1129269d2b1baffc516d8f5c05da06273ef0` | <`files_swept.python` from `calibrate.py --repo /tmp/thunderstruck-58/celery --lang python --patterns all --summary`> |

## Detectors

| Detector | Hits | TP | FP-fixed | FP-accepted | Surfaced | Lost | Final |
|---|---|---|---|---|---|---|---|
| S04-py-bare-except-retry | 2 | 1 | 1 | 0 | 0 | 0 | 1 |
| S07-py-insert-without-upsert | 2 | 0 | 1 | 1 | 1 | 0 | 2 |
| S19-py-except-pass | 9 | 2 | 1 | 6 | 0 | 0 | 8 |
| … every other detector with a hit, from celery-before/after.txt … |

### Hits
(one `####` per detector, every final hit as `- celery \`path:line\` — TP|FP-accepted: reason`)

### Fixed during calibration
- `S04-py-bare-except-retry` `celery/backends/base.py:773` → `S04/python/negative_hook_in_retry_branch.py`
- `S19-py-except-pass` `celery/worker/consumer/consumer.py:435` → `S19/python/negative_teardown_after_logged_error.py`
- `S07-py-insert-without-upsert` `celery/backends/database/__init__.py:168` → `S07/python/negative_get_or_create.py`; the file's lead moves to `:295` (Surfaced, FP-accepted)

### Silences checked
(Step 2's five repositories: what disappeared, and that none was a TP)

### Known limitations
- S07 at `:295`: `taskset_id` is unique in `models.py`, which a file-local rule cannot see. Lowering the detector to `low` drops the database backend out of the top 10 at this commit (spec §3.2), so it stays `medium`.
- S04: a retryability predicate on an unrelated value 7–12 lines above a real catch-all retry now hides it.

## Boundaries
(Task 6 Step 5's two outputs, per bundle, and every after-line)

## Lead precision
| | Before | After |
|---|---|---|
| Leads in the ten investigated bundles | 5, 2 true | 3, 2 true |
| All detector hits at the commit | 27, 6 true | 25, 6 true |
```

Replace each placeholder line in parentheses or angle brackets with the measured content before committing; the committed log contains no placeholder. If Step 1 or 2 produced figures other than the expected ones, the log records the measured figures and the PR says why they differ.

- [ ] **Step 4: Point `python.md` at it.** Under `python.md`'s **Known limitations**, add a first bullet:

```markdown
- Three accepted false positives in this log are corrected since #58, with negative samples: S04 `celery/backends/base.py:757` (now `:773`), S19 `celery/worker/consumer/consumer.py:427` (now `:435`) and S07 `celery/backends/database/__init__.py:168`. See [celery.md](celery.md).
```

- [ ] **Step 5: Run the docs checks**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_docs_in_sync.py tests/test_links.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/calibration/celery.md docs/calibration/python.md
git commit -m "Calibration: every Celery detector hit and boundary line, judged (#58)"
```

---

### Task 9: Documentation, version and the release checks

**Satisfies:** AC-7.

**Files:**
- Modify: `CLAUDE.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`
- Regenerate if stale: `skills/stability-catalog/references/patterns.md`

- [ ] **Step 1: CLAUDE.md.** In "The catalog is the source of truth", replace the sentence beginning "Three detector kinds:" with:

```markdown
Three detector kinds: `regex` (line match with a look-ahead/behind window),
`file_absent` (anchor present *and* absent-regex matching nowhere, optionally
gated by a `require` regex so it only fires on files that do the thing the
pattern guards), `module`
(dispatches to a handler in `scripts/detectors/modules.py`). `regex` and
`file_absent` may add `absent_before` with its own `absent_before_window`:
the hit is excused by what precedes it, without widening what counts as one.

The bundle's **External boundaries** also come from the catalog
(`boundaries:`, per language, matched by `detectors.find_boundaries`), with
samples under `tests/boundaries/samples/`. A boundary is a call, never a
name: a call through a library's own name needs that library's import, so a
dict called `requests` is not HTTP. An import of the scanned project's own
package never counts (`own_packages` in `hotspots.json`), so a library
calling itself is not a call through it.
```

- [ ] **Step 2: Version and CHANGELOG.** Bump the minor version in all four places (the next minor above `main`'s at the time; `0.10.0` if `main` is still `0.9.x`), and add, with `<version>` the version just set:

```markdown
## <version>

Detector and boundary leads that hold up on library code (#58).

### Changed

- **External boundaries are calls, not names.** The bundle's boundaries come from per-language rules in the catalog, matched on comment-stripped code: no comment, docstring, import or definition is listed, and a variable that shares a library's name (`requests.pop(…)` on a dict) is not a call through that library. An import of the scanned project's own package never counts as importing a library, so a library calling its own code is not a boundary. On Celery's benchmark scan the ten bundles list 11 lines instead of 68, none from a comment, docstring or import. A language without rules says so. **Every bundle changes once, so cached findings are re-investigated on the first scan after upgrading.**
- **Three false-lead shapes from Celery are corrected**, each with a negative sample: an `except` guarding a hook inside a retry branch that already discriminates (S04), best-effort teardown after a logged failure (S19), and a get-or-create on the row's own key (S07). Detectors gain `absent_before`.
- **The report's lead table says what it means.** *Pattern coverage* is now *Detector leads by pattern*: a lead is a place to read, never proof a pattern is missing, and describes the default when code leaves a setting to its caller; no lead does not mean the pattern is present.

### Added

- **`docs/calibration/celery.md`**: every detector hit and boundary line on Celery at the benchmark commit, judged, with lead precision before and after.
```

- [ ] **Step 3: Run the full suite and the generated-file checks**

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
uv run scripts/gen_catalog_docs.py --check; echo "exit=$?"
uv run scripts/gen_sample_report.py --check; echo "exit=$?"
```

Expected: all three `exit=0`. If `gen_catalog_docs.py --check` reports stale, run `uv run scripts/gen_catalog_docs.py` and include `skills/stability-catalog/references/patterns.md` in the commit.

- [ ] **Step 4: Validate and install the plugin**

```bash
claude plugin validate . --strict
claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck
claude plugin list
```

Expected: validate passes; `claude plugin list` shows thunderstruck `enabled`, not "failed to load".

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md CHANGELOG.md .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml skills/stability-catalog/references/patterns.md
git commit -m "Library leads: docs and release note (#58)"
```

The PR description states, from Tasks 6 and 8: the boundary count before and after (AC-1), lead precision before and after in the investigated bundles and across the repository (AC-6), and the hotspot list before and after with the two rank swaps (spec §3.3).

## Acceptance criteria coverage

| AC | Tasks |
|---|---|
| AC-1 | 5 (no comment, docstring or import is ever a boundary), 6 (the bundle uses it; Celery count), 8 (recorded) |
| AC-2 | 5 (`negative_dict_named_requests` and `positive_requests_get`; `negative_own_package_apply_async` and `positive_celery_delay`) |
| AC-3 | 1 (mechanism), 2, 3, 4 (one shape each), 8 (no true positive lost elsewhere) |
| AC-4 | 8 |
| AC-5 | 7 |
| AC-6 | 8, and the PR description (Task 9) |
| AC-7 | 9 |
