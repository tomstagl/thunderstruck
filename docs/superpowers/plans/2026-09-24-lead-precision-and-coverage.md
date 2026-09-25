# Lead Precision and Visible Coverage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make detector leads trustworthy on everyday Java/TypeScript/Python
code, make the report honest about what it did not look at, and extend
scanning to the configuration where timeouts, retries and probes actually
live.

**Architecture:** No stage changes shape. See the spec, §1.

**Spec:** `docs/superpowers/specs/2026-09-24-lead-precision-and-coverage-design.md`.
Requirements and acceptance criteria AC-1…AC-19 are in
[#19](https://github.com/tomstagl/thunderstruck/issues/19).

**Tech stack:** Python ≥ 3.11 stdlib + `pyyaml` + `lizard`, pytest, `uv run`.
No new dependencies.

**Base:** `main` at `67736da` (after #36). The prerequisites in the #19
comment (#25 before Tasks 8–9, #26 before the sample-changing tasks) have
all merged.

**Branch:** implement on a feature branch, one commit per task. Tick the
issue checklist as each task merges.

## Global constraints

- Detector changes are catalog edits plus samples. `signals.py` changes only
  for the pipeline features (coverage gaps, dormant sweep, suppression,
  inventory), never to special-case one pattern.
- Every precision change adds the reproduced false positive as
  `negative_<shape>.<ext>` **before** the catalog edit. Run it and watch it
  fail, then fix.
- Bundles stay byte-identical on an unchanged repo: sort every new list, no
  timestamps, no absolute paths.
- The guardrail stays stdlib-only, always exits 0, and stays under 100 ms.
- Regenerate, never hand-edit: `patterns.md` (`gen_catalog_docs.py`) and
  `examples/sample-report.md` (`gen_sample_report.py`). CI checks both.
- Every value in `report.md` that the scanned repository or a model wrote
  (commit subjects, suppression reasons, config paths) goes through
  `md.text`/`md.code` (#34). Only the tool builds links.
- A new field the validator owns (`evidence_hashes`, Task 9) is stripped by
  `save_finding.py`, like `key` and `content_hash`.

Full suite, used as the exit check of every task:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 \
  --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q
uv run scripts/gen_catalog_docs.py --check
uv run scripts/gen_sample_report.py --check   # once a task changes the sample
```

## Verification already done

Twice, on a scratch copy with the Task 1 engine change and the Task 3, 4 and
5 catalog edits applied as written below. The second run was on `67736da`
(after #36):

- the baseline is `803 passed, 222 skipped`. After the edits it is
  `830 passed, 222 skipped` (4 engine tests and 23 sample cases added, 0
  failures). `tests/detectors` goes from 237 to 260 passed.
  `gen_catalog_docs.py --check` passes once `patterns.md` is regenerated;
- all 18 new negative samples fired before the edits and are silent after;
- all 5 added positives fire, including `positive_django_all.py` (the
  `\.objects\b` in S08's `require`) and `positive_while_attempts.py`, which
  didn't fire before;
- S27 `negative_long_chain_offload.java` fires at `window: 12` and is silent
  at 20;
- `gen_sample_report.py` still validates, but the sample changes (Task 4,
  Step 4).

The second run found three things the first missed. Each is now part of the
task it belongs to:

1. `tests/detectors/test_detectors.py` reads polarity from the file stem and
   compares it with `== "positive"`, so `positive_<shape>.py` ran as a
   negative. That is fixed in Task 3.
2. The first docstring rule missed multi-line signatures and attribute
   docstrings. Spec §6.1 changed, and so did Task 1.
3. The Task 4 S06 anchor changes the sample report. Task 4 regenerates it.

Treat the snippets as known to work, not as untested suggestions. Rerun them
anyway if the base moves again.

---

### Task 1: Engine — `require` on regex detectors, and the Python docstring rule

Satisfies: AC-8.

**Files:**
- Modify: `scripts/detectors/__init__.py` (`_run_regex`, module docstring)
- Modify: `scripts/_common.py` (`_strip_python`)
- Modify: `catalog/stability.yaml` header comment (document `require` for `regex`)
- Create: `tests/test_engine_v2.py`

- [x] **Step 1: Failing tests** in `tests/test_engine_v2.py`

```python
from __future__ import annotations

import _common
from detectors import run_detectors


def _cat(det: dict) -> dict:
    return {"patterns": [{"id": "SX", "tier": "A", "detectors": {"python": [det]}}],
            "aliases": {}}


def test_regex_require_skips_files_without_the_construct():
    det = {"id": "SX-py", "kind": "regex", "pattern": r"\.all\(\)",
           "require": r"^\s*import\s+sqlite3\b"}
    assert run_detectors(_cat(det), "a.py", "x = mask.all()\n", "python") == []
    hits = run_detectors(_cat(det), "a.py", "import sqlite3\nrows = q.all()\n", "python")
    assert [h.line for h in hits] == [2]


def test_triple_quoted_argument_is_a_string_not_a_docstring():
    src = 'def f(cur):\n    cur.execute(\n        """\n        SELECT id FROM t\n        """\n    )\n'
    assert "SELECT id FROM t" in _common.strip_comments(src, "python")


def test_function_and_module_docstrings_are_still_blanked():
    src = '"""Module talks about Retry-After."""\ndef f():\n    """Honours Retry-After."""\n    return 1\n'
    out = _common.strip_comments(src, "python")
    assert "Retry-After" not in out and "return 1" in out


def test_docstring_after_multiline_signature_is_blanked():
    src = 'def f(\n    a,\n) -> int:\n    """Honours Retry-After."""\n    return a\n'
    out = _common.strip_comments(src, "python")
    assert "Retry-After" not in out and "return a" in out


def test_attribute_docstring_is_blanked():
    src = 'TIMEOUT = 5\n"""Retry-After is read elsewhere."""\n'
    assert "Retry-After" not in _common.strip_comments(src, "python")


def test_string_after_assignment_operator_is_kept():
    src = 'Q = \\\n    """\nSELECT id FROM t\n"""\n'
    assert "SELECT id FROM t" in _common.strip_comments(src, "python")


def test_hash_inside_multiline_string_is_kept():
    src = 'Q = """\nSELECT 1 # not a comment\n"""\n'
    assert "# not a comment" in _common.strip_comments(src, "python")
```

- [x] **Step 2: Run and confirm they fail**

```bash
uv run --with pytest --with pyyaml --with lizard pytest tests/test_engine_v2.py -q
```

- [x] **Step 3: `require` in `_run_regex`.** Insert before the line loop:

```python
    req = det.get("require")
    if req and not _rx(req, True).search(
            ctx.raw_text if det.get("include_comments") else ctx.code_text):
        return []  # the file never does the thing the pattern guards
```

- [x] **Step 4: Docstring rule in `_strip_python`** (spec §6.1). Track
  `depth` (open brackets outside strings and comments), `prev_code` (the
  last non-blank line after stripping) and `in_string`. At a line matching
  `_PY_DOCSTRING_START`:
  - if `depth > 0`, or `prev_code` ends (after trailing whitespace) with
    `=`, `,`, `\` or a binary operator (`+ - * / % | & ^ < >`, including
    `and`/`or`): it is a string. Copy lines verbatim until the closing quote,
    set `in_string = quote`, and skip `#` stripping while inside;
  - otherwise: it is a docstring (current behaviour). This covers the first
    statement, `) -> int:` and `x = 1`.

  A helper `_py_scan_line(line, in_string) -> (depth_delta, open_quote)`
  scans one line for brackets and triple quotes. It also handles a triple
  quote opening mid-line (`Q = """`), which then copies the following lines
  verbatim until it closes.

- [x] **Step 5:** Tests green, then the full suite. S08-py samples must not
  change.

- [x] **Step 6: Commit** `engine: require on regex detectors; triple-quoted arguments are strings (AC-8)`

---

### Task 2: Path defaults and `exclusion_reason`

Satisfies: AC-12, and the filter half of AC-1.

**Files:**
- Modify: `scripts/_common.py` (`DEFAULT_EXCLUDE_*`, `Filters.exclusion_reason`, `excludes_path`)
- Create: `tests/test_filters_v2.py`

Coordinate with #14, which covers JVM source sets (`integrationTest`,
`testFixtures`, `jmh`). Do not duplicate them here. If #14 has merged,
rebase and keep its entries.

- [x] **Step 1: Failing test**, table-driven:

```python
import pytest
import _common as c

F = c.Filters()

@pytest.mark.parametrize("path,reason", [
    ("app/tests.py", "test"), ("app/api_tests.py", "test"),
    ("cypress/support/commands.ts", "test"),
    ("playwright.config.ts", "tooling"), ("vitest.config.mts", "tooling"),
    ("src/types/api.d.ts", "generated"), ("stubs/requests.pyi", "generated"),
    ("src/__generated__/graphql.ts", "generated"), ("api/generated/Client.java", "generated"),
    ("benchmarks/load.py", "test"),
    (".github/workflows/ci.yml", "tooling"), ("docker-compose.dev.yml", "tooling"),
    ("openapi.yaml", "generated"),
    ("db/migrations/001.py", "migration"), ("node_modules/x/index.js", "vendored"),
    ("dist/app.js", "build"), ("yarn.lock", "asset"),
    ("src/client/releases.ts", None), ("src/app.config/loader.ts", None),
])
def test_exclusion_reason(path, reason):
    assert F.exclusion_reason(path) == reason
    assert F.excludes_path(path) == (reason is not None)
```

- [x] **Step 2: Implement.** Split the default lists into
  `(reason, entries)` groups. Additions:
  - test: globs `tests.py`, `*_tests.py`, `*.cy.*`; dirs `cypress`,
    `benchmarks`, `bench`;
  - tooling: globs `<tool>.config.*` for named tools (spec §7.1; not a
    blanket `*.config.*`, which drops runtime config), `.gitlab-ci.yml`, `docker-compose*.yml`,
    `docker-compose*.yaml`, `mkdocs.yml`, `.pre-commit-config.yaml`; dirs
    `.github`, `.circleci`, `.gitlab`;
  - generated: globs `*.d.ts`, `*.pyi`, `openapi*.yaml`, `openapi*.yml`,
    `swagger*.yaml`, `swagger*.yml`; dirs `generated`, `__generated__`.

  Profile additions report `profile`, and `--path` reports `path`.
  `excludes_path` becomes `return self.exclusion_reason(rel_path) is not None`.

- [x] **Step 3:** Full suite. `test_pipeline` fixture paths are unaffected.

- [x] **Step 4: Commit** `filters: tests.py, cypress, tooling configs, generated dirs; exclusion reasons (AC-12)`

---

### Task 3: Python precision

Satisfies: AC-9.

**Files:**
- Modify: `catalog/stability.yaml`
- Modify: `tests/detectors/test_detectors.py`: polarity is
  `"positive" if stem.startswith("positive") else "negative"`, so
  `positive_<shape>` files run as positives. The Tier A pair check still
  needs the plain `positive`/`negative` files.
- Create: samples below under `tests/detectors/samples/<ID>/python/`

- [x] **Step 1: Negative samples (the reproduced false positives).**

`S19/python/negative_optional_import.py`
```python
try:
    import orjson as json
except ImportError:
    pass
```
`S19/python/negative_missing_file.py`
```python
import os

def remove(p):
    try:
        os.remove(p)
    except FileNotFoundError:
        pass
```
`S19/python/negative_reraise.py`
```python
import os

def write(path, data):
    f = open(path + ".tmp", "w")
    try:
        f.write(data)
    except:
        os.unlink(path + ".tmp")
        raise
```
`S04/python/negative_skip_bad_item.py`
```python
import logging
log = logging.getLogger(__name__)

def parse_all(lines):
    out = []
    for line in lines:
        try:
            out.append(int(line))
        except Exception:
            log.warning("skipping malformed line %r", line)
            continue
    return out
```
`S07/python/negative_unique_constraint.py`
```python
from sqlalchemy.exc import IntegrityError

def signup(session, email):
    user = User(email=email)
    try:
        session.add(user)
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    return user
```
`S08/python/negative_numpy_all.py`
```python
import numpy as np

def check(a, b):
    mask = np.isclose(a, b)
    return mask.all()
```
`S08/python/negative_single_row_select.py`
```python
def load(conn, user_id):
    row = conn.execute("SELECT id, name FROM users WHERE id = %s", (user_id,)).fetchone()
    n = conn.execute("SELECT count(*) FROM users").fetchone()
    return row, n
```
`S05/python/negative_session_no_loop_call.py`
```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504],
              respect_retry_after_header=True)
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=retry))

def get_user(uid):
    r = session.get(f"https://api.example.com/users/{uid}", timeout=(3, 10))
    r.raise_for_status()
    return r.json()

def names(users):
    for u in users:
        yield u["name"]
```
`S06/python/negative_local_pool.py` (pattern-level test; S13 is Tier B,
so there's no pair requirement, but add the same file under `S13/python/`)
```python
from concurrent.futures import ThreadPoolExecutor

def render_thumbnails(paths):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(make_thumb, paths))
```

- [x] **Step 2: Positives that guard against over-correction.**

`S04/python/positive_while_attempts.py`
```python
def call():
    attempts = 0
    while attempts < 5:
        try:
            return post()
        except Exception:
            attempts += 1
```
`S08/python/positive_django_all.py`
```python
from myapp.models import Order

def export():
    return list(Order.objects.all())
```
`S13/python/positive.py`
```python
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=8)

def submit(fn, *a):
    return executor.submit(fn, *a)
```

The existing `positive.py` files for S04, S05, S06, S07, S08 and S19 must
keep firing.

- [x] **Step 3: Run. The negatives fail.**

```bash
uv run --with pytest --with pyyaml --with lizard pytest tests/detectors -k "python" -q
```

- [x] **Step 4: Catalog edits** (verified; see "Verification already done").

```yaml
# S19-py-except-pass — narrow typed swallows are deliberate
pattern: '^\s*except\s*(?:\(?\s*(?:Exception|BaseException)\b[^:]*)?:\s*$'
# S19-py-bare-except — cleanup then re-raise is correct
absent_within: '^\s*raise\s*$'
window: 8
window_offset: 1
# S04-py-bare-except-retry — `continue` alone is skipping, not retrying
present_within: '^\s*for\s+(?:_\w*|\w*(?:attempt|retr|tries|try)\w*)\s+in\s+range\b|^\s*while\b|\b(?:retry|retries|retrying|attempts?|backoff)\b'
window_before: 6
# S07-py-insert-without-upsert — append to `absent`
|IntegrityError|UniqueViolation|DuplicateKey
# S08-py-query-all-without-limit — only in files that talk to a database
require: '^\s*(?:from|import)\s+(?:sqlalchemy|sqlmodel|django|psycopg2?|sqlite3|pymysql|MySQLdb|asyncpg|aiosqlite|peewee|tortoise|pymongo|motor|databases|records)\b|\.objects\b|\b(?:cursor|cur|conn|connection|session|db)\w*\s*\.\s*execute\s*\('
# S08-py-select-without-limit (and S08-ts-select-without-limit, Task 4)
absent_within: '(?i)\bLIMIT\b|\bFETCH\s+FIRST\b|\bTOP\s*\(?\s*\d|SELECT\s+(?:COUNT|MAX|MIN|SUM|AVG|EXISTS)\s*\(|\bWHERE\s+(?:\w+\.)?id\s*='
# S05-py-http-without-limiter — the call must be inside the loop
anchor: '^([ \t]*)(?:async\s+)?(?:for|while)\b[^\n]*:[ \t]*\n(?:\1[ \t]+[^\n]*\n|[ \t]*\n){0,8}?\1[ \t]+[^\n]*\b(?:requests|httpx|session|client|http)\w*\s*\.\s*(?:get|post|put|patch|delete|head|request)\s*\(|\b(?:asyncio\s*\.\s*gather|\.map)\s*\([^\n]*\b(?:requests|httpx|session|client)\w*\s*\.\s*(?:get|post|put|patch|delete|head|request)\b'
# S11-py-no-deadline-propagation and S15-py-no-fallback — anchor
anchor: '\b(?:requests|httpx|aiohttp)\s*\.\s*(?!(?:exceptions|adapters|codes|status_codes|structures|utils|auth|HTTPError|RequestException|Timeout|TimeoutException|ConnectionError|HTTPStatusError|ClientError|ClientTimeout)\b)\w+'
# S06-py-single-queue-no-priority — a shared queue/pool, not a local one
anchor: '(?im)^\w+\s*(?::[^=\n]+)?=\s*[\w.]*(?:queue|limiter|throttle|worker|pool|executor|semaphore)\w*\s*\(|\bself\.\w+\s*(?::[^=\n]+)?=\s*[\w.]*(?:queue|limiter|throttle|worker|pool|executor|semaphore)\w*\s*\('
# S13-py-shared-pool
anchor: '(?im)^\w+\s*(?::[^=\n]+)?=\s*[\w.]*(?:pool|executor)\w*\s*\(|\bself\.\w+\s*(?::[^=\n]+)?=\s*[\w.]*(?:pool|executor)\w*\s*\('
# S17-py-cache-without-ttl — boundedness of the key domain is undecidable
confidence: low
```

Update each detector's `note` where its meaning narrowed (for example,
S19-py-except-pass: "`except:`/`except Exception:` with only `pass` — the
failure leaves no trace").

- [x] **Step 5:** Samples green, then the full suite, then
  `gen_catalog_docs.py`.
- [x] **Step 6: Commit** `python detectors: silence reproduced false positives (AC-9)`

---

### Task 4: TypeScript precision

Satisfies: AC-10.

**Files:** `catalog/stability.yaml`; samples under `tests/detectors/samples/<ID>/typescript/`.

Coordinate with #17 (S19-ts catch-only-comment firing on a *logged* catch).
Do not overlap: this task touches `S19-ts-empty-catch` only.

- [x] **Step 1: Negatives.**

`S19/typescript/negative_ignored_param.ts`
```ts
import * as fs from 'fs';
export function tryUnlink(p: string) {
  try { fs.unlinkSync(p); } catch (_ignored) {}
}
```
`S17/typescript/negative_local_index.ts`
```ts
export function group(rows: Row[]) {
  const m = new Map();
  for (const r of rows) m.set(r.k, r);
  return m;
}
```
`S14/typescript/negative_reducer_state.ts`
```ts
export function reducer(state = { buffer: [] as string[] }, action: Action) {
  const buffer = [];
  return state;
}
```
`S08/typescript/negative_const_fanout.ts`
```ts
const REGIONS = ['eu', 'us', 'ap'] as const;
export async function healthAll() {
  return Promise.all(REGIONS.map((r) => ping(r)));
}
```
`S04/typescript/negative_async_retry_bail.ts`
```ts
import retry from 'async-retry';
export async function load(url: string) {
  return retry(async (bail) => {
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (res.status === 404) { bail(new Error('not found')); return; }
    return res.json();
  }, { retries: 3, factor: 2, randomize: true, maxTimeout: 10_000 });
}
```
`S07/typescript/negative_unique_constraint.ts`
```ts
export async function register(email: string) {
  try {
    return await prisma.user.create({ data: { email } });
  } catch (e) {
    if (e.code === 'P2002') return prisma.user.findUnique({ where: { email } });
    throw e;
  }
}
```
`S06/typescript/negative_lodash_throttle.ts`
```ts
import throttle from 'lodash/throttle';
export function useScroll(cb: () => void) {
  useEffect(() => {
    const h = throttle(cb, 100);
    window.addEventListener('scroll', h);
    return () => window.removeEventListener('scroll', h);
  }, [cb]);
}
```

- [x] **Step 2: Positives.**

`S17/typescript/positive.ts`
```ts
const cache = new Map<string, User>();
export async function getUser(id: string) { cache.set(id, await load(id)); }
```
`S14/typescript/positive.ts`
```ts
class Svc {
  private queue: Job[] = [];
}
```
The existing S06, S08 and S19 TS positives must keep firing.

- [x] **Step 3: Catalog edits** (verified).

```yaml
# S19-ts-empty-catch — same deliberate-swallow convention as Java
pattern: 'catch\s*(?:\((?![^)]*\b(?:_\w*|ignored?|expected|unused)\s*\))[^)]*\))?\s*\{\s*\}'
# S17-ts-cache-without-ttl — module-level or class field; also fixes new Map<K,V>() never matching
anchor: '^(?:export\s+)?(?:const|let|var)\s+\w+[^=\n]*=\s*new\s+Map\b|^[ \t]+(?:(?:private|protected|public|readonly|static)\s+)+#?\w+[^=\n]*=\s*new\s+Map\b|\b[Cc]ache\s*\.\s*set\s*\('
# S14-ts-unbounded-queue
pattern: '(?i)^(?:export\s+)?(?:const|let|var)\s+\w*(?:queue|buffer|backlog)\w*\s*(?::[^=]+)?=\s*(?:\[\]|new\s+Array)|^\s+(?:(?:private|protected|public|readonly|static)\s+)*#?\w*(?:queue|buffer|backlog)\w*\s*(?::[^=]+)?=\s*(?:\[\]|new\s+Array)|\bthis\.\w*(?:queue|buffer|backlog)\w*\s*=\s*(?:\[\]|new\s+Array)'
# S08-ts-unbounded-promise-all — scope (?i) so [A-Z] stays case-sensitive
absent_within: '(?i:\b(slice|chunk|batch|limit|pLimit|p-limit|concurrency|take|semaphore)\b)|Promise\s*\.\s*(all|allSettled)\s*\(\s*\[(?![^\]]*(?:\.\.\.|\.map\s*\())|Promise\s*\.\s*(?:all|allSettled)\s*\(\s*[A-Z][A-Z0-9_]*\s*\.\s*map\s*\('
# S04-ts-retry-without-discrimination — append to `absent`
|\bbail\s*\(|\bAbortError\b|\bonFailedAttempt\b|\bhandle(?:When|Type|Result)\s*\(
# S07-ts-create-without-upsert — append to `absent`
|P2002|E11000|ER_DUP_ENTRY|23505|UniqueViolation|DuplicateKey
# S06-ts-single-queue-no-priority — a declaration, never an import
anchor: '(?i)^(?:export\s+)?(?:const|let|var)\s+\w*(?:queue|limiter|throttle|worker|pool)\w*\b[^=\n]*=|^[ \t]+(?:(?:private|protected|public|readonly|static)\s+)+#?\w*(?:queue|limiter|throttle|worker|pool)\w*\b[^=\n]*='
```
Plus the S08-ts-select `absent_within` from Task 3.

- [x] **Step 4:** The fixture still produces FR-004's `S06@src/sync/scheduler.ts:1`
  (`const queue:` at column 0). The sample report changes, as intended:
  S06 leads go from 4 files to 2. `collection.ts` loses S06, because its
  only anchor was an `import { enqueue }`, and `artists.ts` loses it too,
  because its only anchor was a `limiter.acquire()` call. H02's score goes
  from 0.7111 to 0.615, and H04's from 0.0663 to 0.0537. Run
  `uv run scripts/gen_sample_report.py`, check that the diff is only that,
  commit the regenerated sample in this task (CI checks freshness), then
  run the full suite.
- [x] **Step 5: Commit** `typescript detectors: silence reproduced false positives; S17 now sees generic Maps (AC-10)`

---

### Task 5: Java — S27 window

Satisfies: AC-11.

- [x] Create `S27/java/negative_long_chain_offload.java`:

```java
class UserService {
    Mono<User> find(long id) {
        return Mono.fromCallable(() -> jdbcTemplate.queryForObject(SQL, MAPPER, id))
            .map(this::enrich)
            .map(this::audit)
            .filter(Objects::nonNull)
            .map(this::a)
            .map(this::b)
            .map(this::c)
            .map(this::d)
            .map(this::e)
            .map(this::f)
            .map(this::g)
            .map(this::h)
            .subscribeOn(Schedulers.boundedElastic());
    }
}
```
- [x] Run it and watch it fail. Set `S27-java-blocking-in-reactive.window: 20`,
  then rerun `pytest tests/detectors -k "S27 or java" -q`.
- [x] Recalibrate: rerun the batch-1 repositories from `docs/calibration/java.md`
  with `calibrate.py --lang java --patterns S27`. Record the delta (expected
  0 new hits) in a "Batch 7" section.
- [x] **Commit** `S27: widen offload window to 20 lines (AC-11)`

---

### Task 6: Suppression

Satisfies: AC-13.

**Files:** `scripts/_common.py` (`load_suppressions`, `path_glob_to_re`),
`scripts/signals.py`, `scripts/report.py`, `examples/thunderstruck.toml.example`,
`tests/test_suppress.py`.

- [x] **Failing tests:**
  - `path_glob_to_re("src/**/batch/*.java")` matches
    `src/main/java/a/batch/X.java` and not `src/batch/sub/X.java`;
  - `load_suppressions({"suppress": [{"detector": "S16", "path": "*.java"}]})`
    → no rules, one warning `…has no reason…`;
  - a pipeline test over a temp repo: with a rule for
    `S14-py-unbounded-queue` on `jobs.py`, `hotspots.json` has no S14 hit on
    that file, `suppressed == [{"detector": …, "path": …, "reason": …,
    "hits": 1}]`, and the report contains `Suppressed leads`.
- [x] **Implement.** A `Suppression(detector, path_re, reason)` dataclass.
  A rule matches a hit when `rule.detector in (hit.detector_id,
  hit.pattern_id)` and `path_re` matches `hit.file`. Apply it in `build()`
  right after `run_detectors`, in the dormant sweep too (Task 11), and
  never in `calibrate.py`. Warnings go to `payload["warnings"]`.
- [x] Document it in `thunderstruck.toml.example`, including why there are
  no inline markers (spec §8).
- [x] **Commit** `profile [[suppress]]: reasoned, visible lead suppression (AC-13)`

---

### Task 7: Commit classification v2

Satisfies: AC-6.

**Files:** `scripts/_common.py` (`classify_commit` and its keyword sets move
here from `bundle.py`/`signals.py`; spec §4), `scripts/signals.py`,
`scripts/bundle.py` (imports it; label rendering),
`agents/thunderstruck-investigator.md` (one sentence on `resilience`),
`tests/test_classify.py`.

- [x] **Failing test:**

```python
import pytest
from _common import classify_commit

@pytest.mark.parametrize("subject,expected", [
    ("Add retry with exponential backoff and jitter", "resilience"),
    ("feat: honour Retry-After on 429", "feature"),
    ("Introduce rate limiting for partner API", "resilience"),
    ("chore: patch version bump", "refactor"),
    ("fix typo in README", "fix"),
    ("Add timeout to payment client", "resilience"),
    ("Handle 429 from upstream", "resilience"),
    ("fix: handle hang in release fetch", "fix"),
    ('Revert "add cache"', "fix"),
    ("Release 1.2.3", "feature"),
    ("Fehler behoben", "feature"),
    ("refactor: tidy imports", "refactor"),
])
def test_classify(subject, expected):
    assert classify_commit(subject) == expected

def test_profile_keywords():
    assert classify_commit("Fehler behoben", extra_fix=("behoben",)) == "fix"
```
- [x] **Implement** the rules in spec §4. `collect_history` counts `fix` only
  and adds `resilience_commits`. `[history] fix_keywords` is read from the
  profile and compiled once with `re.escape`.
- [x] Every fixture commit uses a Conventional Commits prefix, so the
  fixture's fix counts do not change. Assert that `gen_sample_report.py`
  output differs only where later tasks intend it to.
- [x] **Commit** `history: resilience work is not a fix; profile fix keywords (AC-6)`

---

### Task 8: `high` needs a corroborating commit; commit subjects in the report

Satisfies: AC-5, AC-3.

**Files:** `scripts/_common.py` (`VALIDATION_RULES = 3`), `scripts/validate.py`,
`scripts/report.py`, `agents/thunderstruck-investigator.md`,
`skills/thunderstruck-scan/SKILL.md` (if it restates the rule),
`scripts/gen_sample_report.py`, `tests/test_pipeline.py`,
`tests/test_inert_report_text.py` (or wherever #34's renderer tests live).

- [x] **Failing tests** in `tests/test_pipeline.py`:
  - a finding with `confidence: high` whose only commit is
    `refactor: tidy imports` (it touches the file) → an error containing
    `no cited commit is a fix`;
  - the same finding with a `fix:` commit → valid;
  - an `OTHER`-only `high` finding citing the commit that introduced its
    cited lines (per `git blame`) → valid;
  - the same `OTHER` finding citing a commit that touched the file but not
    those lines → rejected, and the message mentions `introduced the cited
    lines`;
  - the introducing commit on a finding with `missing_patterns:
    ["OTHER", "S01"]` → rejected (the exception is `OTHER`-only);
  - a cited line that is uncommitted in the working tree never matches;
  - a findings file stamped `validated_with: 2` is not cached by
    `bundle.py` (it already isn't: assert the bump reaches it);
  - the report for a valid finding contains the commit's subject in quotes
    and `(fix)`.
- [x] **Failing test** in #34's inert-text suite: a fixture commit with the
  subject `[x](https://evil.example) <img src=x> # h` renders as literal
  text under both renderers when cited.
- [x] **Implement.**
  - `Validator._subject(sha)` is cached and runs `git log -1 --format=%s`
    through `c.git_paths`.
  - `Validator._introduced(rel, start, end) -> set[str]` is cached, runs
    `git blame --porcelain -L start,end -- rel`, and drops the all-zero SHA.
  - In `check_finding`, when `conf == "high"`, a commit ref that already
    passed `check_commits_touch` corroborates if
    `classify_commit(self._subject(sha), extra_fix) == "fix"`, or if the
    finding's `missing_patterns == ["OTHER"]` and the SHA is a prefix of
    one returned by `_introduced` for a cited code range. Otherwise error
    as in spec §3.
  - `VALIDATION_RULES = 3`.
  - `report.py collect()` attaches `subject` and `kind` to each commit
    evidence item. `_evidence_ref` renders `md.text(subject)` and the class
    after the link (spec §2.3).
- [x] **Sample report:** FR-003 keeps `high`. Its commit evidence must be
  the commit that introduced `src/util/format.ts:4-14`. Check that with
  `git blame` on the built fixture, and fix the ref in
  `gen_sample_report.py` if it differs. Check that FR-002, FR-004 and FR-005
  cite a `fix:` commit where they claim `high`.
- [x] Investigator prompt: *"The most recent change to a file is not
  corroboration. `high` needs a commit the bundle labels `fix`, or, for an
  `OTHER`-only finding, the commit that introduced the cited lines."*
- [x] **Commit** `validate: high confidence needs a corroborating commit; report shows commit subjects (AC-5, AC-3)`

---

### Task 9: Findings that span files

Satisfies: AC-4.

**Files:** `scripts/validate.py` (`evidence_hashes`), `scripts/save_finding.py`
(strip it from model output), `scripts/report.py` (`render_index`, *Hotspots
investigated with no finding*), `scripts/guardrail.py` (`build_context`),
`tests/test_guardrail.py`, `tests/test_pipeline.py`.

- [x] **Failing tests:**
  - after the fixture pipeline, `index.json.files["src/client/retry-wrapper.ts"]`
    holds FR-001 with `via == "evidence"`. For that, FR-001 in
    `gen_sample_report.py` must cite `src/client/retry-wrapper.ts:<withRetry line>`
    as `code` evidence;
  - the guardrail on `retry-wrapper.ts` prints `cited as evidence; finding
    is on src/client/releases.ts`;
  - the report's *Hotspots investigated with no finding* line for H06 says
    `no finding of its own; cited as evidence by FR-001`, and keeps its #35
    file link;
  - editing `retry-wrapper.ts` marks the secondary entry stale. Editing
    `releases.ts` marks only the primary entry stale;
  - `save_finding.py` strips a model-supplied `evidence_hashes`;
  - the guardrail latency test still passes.
- [x] **Implement** per spec §2.4. Paths are already canonical (#31), so
  there is no normalisation in `render_index`. The guardrail change is one
  conditional in the line format, still stdlib-only.
- [x] **Commit** `index: file findings under every file cited as code evidence (AC-4)`

---

### Task 10: Not scanned, and lead precision

Satisfies: AC-1, AC-2.

**Files:** `scripts/signals.py` (`coverage_gaps`), `scripts/report.py`,
`tests/test_pipeline.py`.

- [ ] **Failing tests** (fixture plus two planted files: `mobile/App.kt` and
  `db/migrations/001.py`):
  - `hotspots.json.coverage_gaps` has `unsupported[".kt"] == 1`,
    `excluded["migration"] == 1`, and
    `tracked == considered + unchanged + not_citable + sum(excluded) + sum(unsupported)`;
  - a tracked symlink to a `.ts` file, planted unchanged, counts in
    `not_citable`, not `unchanged`;
  - `report.md` has a `## Not scanned` section and the run warning
    `1 Kotlin files (.kt) were not scanned`;
  - the coverage table header is
    `| ID | Pattern | Tier | Files with an unconfirmed lead | Leads read | Leads confirmed | Findings |`,
    followed by the footnote;
  - `report.json.lead_precision["S02"] == {"read": n, "confirmed": 1}`.
- [ ] **Implement** per spec §2.1–2.2. `coverage_gaps` is computed from the
  `c.tracked_index(repo)` that `build()` already loads (#36), with the same
  `is_utf8`/`path_problem`/`tracked_file_problem` test for `not_citable`.
  Render through `md.text`/`md.code`, as with every value in the report. Keep `unsupported` to 8 keys plus
  `other`. Sort all keys for determinism.
- [ ] **Commit** `report: Not scanned section and per-pattern lead precision (AC-1, AC-2)`

---

### Task 11: Dormant integration points

Satisfies: AC-7.

**Files:** `catalog/stability.yaml` (`dormant: true` on S01, S02, S03, S04,
S05, S10, S27, S28, and S30 after Task 13), `scripts/signals.py`
(`--dormant`, `--dormant-limit`, `dormant_sweep()`), `scripts/bundle.py`
(D bundles), `scripts/report.py`, `skills/thunderstruck-scan/SKILL.md`
(`--investigate-dormant N`), `tests/test_dormant.py`.

- [ ] **Failing tests:**
  - a temp repo with an old commit adding `src/legacy_client.py`
    (`requests.get(url)`, no timeout), then 5 later commits touching other
    files, run with `--since 30d` (use `GIT_COMMITTER_DATE` and
    `GIT_AUTHOR_DATE` to backdate). The legacy file is not in `hotspots`,
    is `dormant[0]` with id `D01`, and its `detector_hits` include
    `S01-py-requests-no-timeout`;
  - `--dormant 0` → `dormant == []`;
  - `--dormant-limit 1` with two dormant files → a warning naming the
    skipped count;
  - `bundle.py --dormant 1` writes `bundles/D01.md`, and its history
    section reads `No commits in the window. Last change:`. Two runs give
    identical bytes;
  - speed guard: 500 generated dormant Python files sweep in < 10 s.
- [ ] **Implement** per spec §5. Reuse `stability_weight` and apply
  suppressions (Task 6). Qualification is at least one `medium`/`high`
  hit, or `low` hits from two different patterns.
- [ ] Report section **Dormant integration points** comes after *Ranked
  hotspots*, with one line explaining why these files are here.
- [ ] Scan skill: document `--investigate-dormant N` (default 0), which
  counts against the ≤4-parallel cap.
- [ ] **Commit** `signals: list dormant integration points; opt-in investigation (AC-7)`

---

### Task 12: Configuration languages

Satisfies: AC-14.

**Files:** `catalog/stability.yaml` (`languages.yaml`, `languages.properties`,
`rank_only_with_leads`), `scripts/_common.py` (`strip_comments` for
`yaml`/`properties`), `scripts/signals.py` (rank gate),
`tests/detectors/test_detectors.py` (`EXT_LANG`), `tests/test_config_langs.py`.

- [ ] **Failing tests:**
  - `detect_language("k8s/deploy.yaml") == "yaml"` and
    `detect_language("src/main/resources/application.properties") == "properties"`;
  - YAML: `a: "x # y"  # comment` → `# comment` is blanked, the quoted `#` is
    kept;
  - properties: `! comment` and `# comment` lines are blanked,
    `url=http://x#frag` is kept;
  - in a temp repo, a `values.yaml` changed 10 times with no detector hit is
    **not** in `hotspots`, while a churned `.py` file is;
  - a YAML file lizard cannot parse produces no warning.
- [ ] **Implement.** Add `_strip_hash(text, lang)`. Apply the rank gate in
  `build()` before sorting: drop rows whose language has
  `rank_only_with_leads` and `detector_hits == []`. Set
  `EXT_LANG[".yaml"] = EXT_LANG[".yml"] = "yaml"` and
  `EXT_LANG[".properties"] = "properties"`.
- [ ] **Commit** `catalog: yaml and properties as scanned languages, ranked only with leads (AC-14)`

---

### Task 13: Config detectors and S30

Satisfies: AC-15.

**Files:** `catalog/stability.yaml`, samples under
`tests/detectors/samples/{S01,S10,S30}/{yaml,properties}/`, and
`tests/detectors/test_detectors.py` if Tier A discovery needs the new
languages.

- [ ] **Samples** (the regexes were checked by hand against these):

`S01/yaml/positive.yaml`
```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: releases
spec:
  hosts: [releases]
  http:
    - route:
        - destination: {host: releases}
      retries:
        attempts: 3
        perTryTimeout: 2s
```
`S01/yaml/negative.yaml`: the same, with `      timeout: 5s` before `retries:`.

`S30/yaml/positive.yaml`
```yaml
spec:
  containers:
    - name: app
      livenessProbe:
        httpGet:
          path: /actuator/health
          port: 8080
```
`S30/yaml/positive_db.yaml`: the same, with `path: /health/db`.
`S30/yaml/negative.yaml`: `path: /actuator/health/liveness`.
`S30/yaml/negative_healthz.yaml`: `path: /healthz`.

`S10/yaml/positive.yaml`: the VirtualService above (a mesh retry layer is a lead).
`S10/yaml/negative.yaml`: `retries: {attempts: 0}` written as a block with `attempts: 0`.
`S10/properties/positive.properties`: `resilience4j.retry.instances.payments.maxAttempts=3`.
`S10/properties/negative.properties`: `resilience4j.retry.instances.payments.maxAttempts=1`.

- [ ] **Catalog:** add the detectors from spec §7.2 and pattern S30 from spec
  §7.3, placed after S29. Mark the S10 config detectors `inventory:
  retry_layer`.
- [ ] **Calibrate** (a new log `docs/calibration/config.md`) against 3 public
  repositories with Kubernetes, Istio or Spring config, for example
  `GoogleCloudPlatform/microservices-demo`, `istio/istio` samples, and
  `spring-petclinic/spring-petclinic-microservices`. Pin SHAs and judge every
  hit.
- [ ] `gen_catalog_docs.py` → `patterns.md` gains S30.
- [ ] **Commit** `catalog: S30 liveness probes; mesh and resilience4j retry layers; VirtualService timeouts (AC-15)`

---

### Task 14: Retry-layer inventory

Satisfies: AC-16.

**Files:** `catalog/stability.yaml` (`inventory`, `score: false`, three
library-default detectors), `scripts/signals.py` (`stability_weight` skips
`score: false`; `retry_layers` built from the ranked set, the dormant sweep,
and **all** tracked config files), `scripts/bundle.py` (section),
`tests/test_retry_inventory.py`, and samples for the library-default
detectors.

- [ ] **Library-default samples:**

`S10/python/positive_boto3_default.py`
```python
import boto3
s3 = boto3.client("s3")
```
`S10/python/negative_boto3_configured.py`
```python
import boto3
from botocore.config import Config
s3 = boto3.client("s3", config=Config(retries={"max_attempts": 2, "mode": "standard"}))
```
Java: `Feign.builder()` with no `.retryer(` → positive. `.retryer(Retryer.NEVER_RETRY)` → negative.
TS: `import { S3Client } from '@aws-sdk/client-s3'; new S3Client({})` → positive. `new S3Client({ maxAttempts: 2 })` → negative.

- [ ] **Failing tests:**
  - fixture plus `deploy/releases-virtualservice.yaml` (the S01 positive
    above) → `retry_layers` contains `{kind: "config", file:
    "deploy/releases-virtualservice.yaml", detector_id:
    "S10-yaml-mesh-retry"}` and the code layers from `releases.ts` and
    `retry-wrapper.ts`;
  - `bundles/H01.md` has a `Retry layers in this repository` section
    listing all three;
  - a `score: false` hit does not change a file's `stability.weight`;
  - the bundle determinism test still passes.
- [ ] **Commit** `signals: repo-wide retry-layer inventory across code, config and library defaults (AC-16)`

---

### Task 15: `calibrate.py --summary`

Satisfies: AC-17.

- [ ] **Failing test:** in a temp repo, plant the file
  `src/acme_secret_pricing/engine.py`, containing
  `requests.get(ACME_INTERNAL_URL)`. Then:
  - `calibrate.py --repo R --lang all --patterns all --summary` → valid JSON
    with `schema == "thunderstruck.calibration-summary/v1"`;
  - `detectors["S01-py-requests-no-timeout"]["hits"] == 1`;
  - none of `acme`, `secret_pricing`, `engine.py`, `ACME_INTERNAL_URL`, the
    repo's path, or any commit SHA appear in the output.
- [ ] **Implement** per spec §9. `--lang all` iterates the catalog
  languages, and `--patterns all` uses every scanned pattern.
- [ ] Add to CONTRIBUTING.md: "Found noise on a private repo? Paste
  `calibrate.py --summary` into an issue."
- [ ] **Commit** `calibrate: --summary, counts only, safe to share (AC-17)`

---

### Task 16: TypeScript and Python calibration

Satisfies: AC-18.

- [ ] Follow the protocol in `docs/calibration/java.md`. Per language, pick
  3–5 public repositories: ≥1 web service, ≥1 worker/ETL, ≥1 HTTP-client
  library. Pin their SHAs.
  - Python candidates: `netbox-community/netbox`, `fastapi/full-stack-fastapi-template`, `httpie/cli`, `celery/celery`.
  - TS candidates: `immich-app/immich` (server), `actualbudget/actual`, `sindresorhus/got`, `bullmq`'s examples.

  Record the final choice in the log.
- [ ] Run `calibrate.py --lang {typescript,python} --patterns all` and judge
  every hit. Each false positive becomes a `negative_<shape>` sample and a
  fix, or is logged with a reason.
- [ ] A detector at `confidence: high` whose log shows any unexplained
  false positive drops to `medium`. Today that means S19-py-except-pass,
  S19-ts-empty-catch, S01-py-requests-no-timeout, S01-py-urlopen-no-timeout
  and the S03 429 detectors.
- [ ] Write `docs/calibration/typescript.md` and `docs/calibration/python.md`.
- [ ] **Commit** per language: `calibration: typescript (AC-18)`, `calibration: python (AC-18)`

---

### Task 17: Fixture, sample report, docs, version

Satisfies: AC-19.

- [ ] Fixture (`tests/fixtures/build_fixture.py`):
  - add `deploy/releases-virtualservice.yaml` (mesh retries, no timeout);
  - add an old, unchanged `src/client/legacy.ts` with a bare `fetch()`
    before the window (dormant);
  - add a YAML comment shaped like an instruction (repository content is
    data).
- [ ] `gen_sample_report.py`:
  - FR-001 cites the VirtualService as `code` evidence. It is now three
    retry layers: loop ×5, `withRetry` ×3, and the mesh's `attempts: 3`,
    which is up to 4 tries per request. The Verify line's expected count
    becomes 600 for 10 clients;
  - FR-003 stays `high`, corroborated by the commit that introduced the
    comment (Task 8);
  - FR-001 cites `src/client/retry-wrapper.ts` as `code` evidence (Task 9).
- [ ] Regenerate `patterns.md` and `examples/sample-report.md`. Confirm the
  report shows all of these: Not scanned, lead precision, commit subjects,
  the dormant list, suppressed leads (via a fixture profile rule), and the
  retry-layer mention.
- [ ] Update README ("What you get", the catalog count of 23 patterns, config
  scanning) and CLAUDE.md (new commands and "Things that will bite you":
  config ranks only with leads; `score: false` detectors).
- [ ] Bump the version in `plugin.json`, `marketplace.json`,
  `pyproject.toml` and `CHANGELOG.md`.
- [ ] Final checks:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 \
  --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q
uv run scripts/gen_catalog_docs.py --check
uv run scripts/gen_sample_report.py --check
claude plugin validate . --strict
claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck && claude plugin list
```
- [ ] **Commit** `release: lead precision and visible coverage (AC-19)`

---

## Review focus

1. Does any Task 3/4 edit silence a real positive that the samples do not
   cover? Calibration (Task 16) is the backstop, so run it before release.
2. Bundle determinism after Tasks 11 and 14 (new sections, sorted inputs).
3. Guardrail latency after Task 9.
4. `--summary` redaction (Task 15). This is the one output meant to leave a
   private machine.
