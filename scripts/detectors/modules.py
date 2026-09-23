"""Structural detectors: the ones a regex cannot see.

Each handler takes a DetectorContext and returns [(line_no, note), ...].
Handlers must be cheap and must never raise — a detector is a lead generator,
not a compiler.

The bar these were tuned against: a *correct* retry client (capped exponential
backoff with jitter, clamped Retry-After, transient-only retry, one retry
layer) must produce zero hits. Tests in tests/detectors/ pin that.
"""

from __future__ import annotations

import re
from typing import Callable

Result = list[tuple[int, str]]

# --------------------------------------------------------------------------
# shared vocabulary
# --------------------------------------------------------------------------

RETRY_CONTEXT = re.compile(
    r"(?i)\b(retry|retries|retrying|attempt|attempts|backoff|back_off)\b")
# A loop that reacts to a failure status by `continue`-ing is a retry loop even
# when it never uses the word. Without this, the most common hand-rolled retry
# in the wild reads as "just a sleep" and S02 stays silent on it.
ERROR_STATUS = re.compile(
    r"(?i)(\b(429|4\d\d|5\d\d)\b|status(_code)?\s*(>=|===?|==)|\bcatch\b|\bexcept\b)")
RESUME = re.compile(r"(?m)^\s*continue\b|\bcontinue\s*;")


def _has_retry_context(ctx) -> bool:
    if RETRY_CONTEXT.search(ctx.code_text):
        return True
    return bool(ERROR_STATUS.search(ctx.code_text) and RESUME.search(ctx.code_text))
GROWTH = re.compile(
    r"(\*\*|Math\s*\.\s*pow|\bpow\s*\(|<<|\*\s*2\b|2\s*\*\*|\bexponential\b)", re.I)
CAP = re.compile(
    r"(Math\s*\.\s*min|\bmin\s*\(|\bcap(ped)?\b|MAX_[A-Z_]*|[A-Z_]*_MAX\b"
    r"|max_?(delay|backoff|wait|interval)|ceiling)", re.I)
JITTER = re.compile(r"(?i)(jitter|random|rand\s*\(|uniform\s*\(|splay|stagger)")

_LITERAL_MS = re.compile(r"^\s*[\d_]+(\.\d+)?(\s*[*]\s*[\d_]+(\.\d+)?)*\s*$")
# `const SLEEP_MS = 2000;` then `setTimeout(resolve, SLEEP_MS)` is how a fixed
# retry wait is usually written. Reading only the call site would miss it.
_CONST_ASSIGN = re.compile(
    r"^\s*(?:const|let|var|final)?\s*([A-Za-z_]\w*)\s*(?::\s*\w+\s*)?="
    r"\s*([\d_]+(?:\.\d+)?(?:\s*\*\s*[\d_]+(?:\.\d+)?)*)\s*;?\s*$")


def _numeric_constants(code_lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in code_lines:
        m = _CONST_ASSIGN.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out

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
        # Any sleep-named call: Thread.sleep(ms), TimeUnit.SECONDS.sleep(n), a
        # bare inherited sleep(ms), helpers like quietlySleep(ms) and
        # sleepUninterruptibly(d, unit). The first argument is the wait.
        # Accessors (setMaxSleepMs, getSleepTime, isSleeping, hasSleep…)
        # configure or read a wait; they do not perform one.
        re.compile(r"\b(?!(?:set|get|is|has)[A-Z])\w*[Ss]leep\w*\s*\(\s*(?P<arg>[^),]*)"),
    ],
}


def _lang_key(ctx) -> str:
    if ctx.lang == "python":
        return "python"
    if ctx.lang == "java":
        return "java"
    return "typescript"


# --------------------------------------------------------------------------
# S02 — capped exponential backoff with full jitter
# --------------------------------------------------------------------------


def s02_backoff(ctx) -> Result:
    """Flag a retry wait that is constant, uncapped, or unjittered.

    The sleep argument decides how far to look. A numeric literal is judged on
    its own: a fixed wait in a retry loop is a fixed wait. A variable or an
    expression is judged against the whole file, because the growth, the cap
    and the jitter are usually computed in a helper (`calculateBackoff`) far
    from the `setTimeout` that consumes it — looking only at neighbouring
    lines would flag every well-written client.
    """
    if not _has_retry_context(ctx):
        return []  # a sleep outside any retry construct is not a backoff

    file_growth = bool(GROWTH.search(ctx.code_text))
    file_cap = bool(CAP.search(ctx.code_text))
    file_jitter = bool(JITTER.search(ctx.code_text))
    constants = _numeric_constants(ctx.code_lines)

    out: Result = []
    reported: set[str] = set()

    for i, line in enumerate(ctx.code_lines):
        near = "\n".join(ctx.code_lines[max(0, i - 12):i + 13])
        if not (RETRY_CONTEXT.search(near)
                or (ERROR_STATUS.search(near) and RESUME.search(near))):
            continue
        for rx in SLEEP_RES[_lang_key(ctx)]:
            m = rx.search(line)
            if not m:
                continue
            arg = (m.group("arg") or "").strip()
            if not arg:
                continue

            literal = arg if _LITERAL_MS.match(arg) else constants.get(arg)
            if literal is not None:
                if not file_growth and "constant" not in reported:
                    reported.add("constant")
                    shown = arg if literal == arg else f"{arg} ({literal})"
                    out.append((i + 1, (
                        f"retry waits a constant {shown} — no exponential growth, "
                        f"so every client retries on the same schedule")))
                break

            inline_growth = bool(GROWTH.search(arg))
            if not (inline_growth or file_growth):
                break  # cannot tell what this wait is; say nothing

            if not file_cap and "cap" not in reported:
                reported.add("cap")
                out.append((i + 1,
                            "backoff grows with no cap — late attempts park the worker"))
            if not file_jitter and "jitter" not in reported:
                reported.add("jitter")
                out.append((i + 1, (
                    "backoff has no jitter — every retrying client wakes at the "
                    "same moment and the herd re-forms")))
            break
    return out


# --------------------------------------------------------------------------
# S07 — idempotent, resumable jobs
# --------------------------------------------------------------------------

# Substring rather than word-boundary matching: real code says `nextCursor`,
# `page_size` and `saveCursor`, and \b never fires inside a compound
# identifier. Boundaries here cost more in missed checkpoints (false S07 hits
# on correct code) than loose matching costs in noise.
PAGING = re.compile(
    r"(?i)(page|cursor|offset|next_?token|has_?more|has_?next|per_?page"
    r"|page_?size|paginat|\bskip)")
PERSIST = re.compile(
    r"(?i)(save|persist|upsert|checkpoint|commit|store|flush|record_progress"
    r"|last_?sync|last_?seen|progress|set_?state|resume_?from)"
    r"|\.update\s*\(|UPDATE\s+\w+\s+SET")
# Mentioning a page is not walking pages. `for (const item of pageItems)` is an
# item loop that happens to contain the substring; a real paging loop advances
# the position or tests a more-pages flag.
PAGE_ADVANCE = re.compile(
    r"(?i)((page|cursor|offset|skip|start_?at)\s*(\+\+|\+=|=\s*[^=])"
    r"|has_?more|has_?next|next_?(page|cursor|token|url)|is_?last_?page)")
LOOP_TS = re.compile(r"^\s*(?:\}\s*)?(?:do\b|while\s*\(|for\s*(?:await\s*)?\()")
LOOP_PY = re.compile(r"^\s*(?:while|for)\b.*:")


def _ts_block_end(lines: list[str], start: int, limit: int = 200) -> int:
    depth, seen = 0, False
    for i in range(start, min(len(lines), start + limit)):
        depth += lines[i].count("{") - lines[i].count("}")
        if lines[i].count("{"):
            seen = True
        if seen and depth <= 0:
            return i
    return min(len(lines) - 1, start + limit)


def _py_block_end(lines: list[str], start: int, limit: int = 200) -> int:
    base = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start + 1, min(len(lines), start + limit)):
        if not lines[i].strip():
            continue
        indent = len(lines[i]) - len(lines[i].lstrip())
        if indent <= base:
            return i - 1
    return min(len(lines) - 1, start + limit)


def _persists_cursor(body_lines: list[str]) -> bool:
    """True only when a persistence call is about the *position*.

    Saving the rows a page returned is not a checkpoint: after a crash the job
    still starts at page 1 and pays for every page again. So a PERSIST match
    counts only when a paging term appears on the same line or the one either
    side of it.
    """
    for i, line in enumerate(body_lines):
        if not PERSIST.search(line):
            continue
        near = "\n".join(body_lines[max(0, i - 1):i + 2])
        if PAGING.search(near):
            return True
    return False


def s07_checkpoint(ctx) -> Result:
    lines = ctx.code_lines
    is_py = _lang_key(ctx) == "python"
    loop_re = LOOP_PY if is_py else LOOP_TS
    end_of = _py_block_end if is_py else _ts_block_end

    out: Result = []
    i = 0
    while i < len(lines):
        if not loop_re.match(lines[i]):
            i += 1
            continue
        end = end_of(lines, i)
        body_lines = lines[i:end + 1]
        body = "\n".join(body_lines)
        if (PAGING.search(body) and PAGE_ADVANCE.search(body)
                and not _persists_cursor(body_lines)):
            out.append((i + 1, (
                "paged loop with no persisted cursor — an interrupted run "
                "restarts from the first page and re-pays the whole cost")))
            if len(out) >= 3:
                break
        i = max(end, i) + 1
    return out


# --------------------------------------------------------------------------
# S10 — retry at one layer plus a retry budget
# --------------------------------------------------------------------------

RETRY_LAYERS: dict[str, list[tuple[str, re.Pattern]]] = {
    "typescript": [
        ("own retry loop", re.compile(
            r"\b(for|while)\s*\(.*\b(attempt|retry|retries|tries)\b", re.I)),
        ("retry wrapper", re.compile(
            r"\b(withRetry|fetchWithRetry|pRetry|p_retry|retryable|asyncRetry"
            r"|retry\s*\(\s*(?:async|\(|function))\b", re.I)),
        ("SDK retry config", re.compile(
            r"\b(maxAttempts|retryStrategy|retryConfig|adaptiveRetry"
            r"|RetryPolicy|retryMode)\b")),
    ],
    "python": [
        ("own retry loop", re.compile(
            r"\b(for|while)\b.*\b(attempt|retry|retries|tries)\b", re.I)),
        ("retry decorator", re.compile(
            r"@\s*(retry|backoff\.on_exception|tenacity|retrying)")),
        ("SDK retry config", re.compile(
            r"\b(max_attempts|Retry\s*\(|retry_strategy|retry_config|urllib3\.Retry)\b")),
    ],
}
BUDGET = re.compile(r"(?i)(retry.?budget|token.?bucket|retry.?quota|budget_remaining)")

# `export async function fetchWithRetry(` is the wrapper's own definition, not
# a call that wraps another retry layer. Counting it turns every correct retry
# helper into a spurious S10 hit.
DECLARATION = re.compile(
    r"^\s*(export\s+)?(default\s+)?(async\s+)?"
    r"(function\s+\w+|def\s+\w+|class\s+\w+"
    r"|const\s+\w+\s*=\s*(async\s*)?(\(|function)"
    r"|(public|private|protected)\s+)")


def s10_retry_layers(ctx) -> Result:
    if BUDGET.search(ctx.code_text):
        return []
    found: list[tuple[str, int]] = []
    for label, rx in RETRY_LAYERS[_lang_key(ctx)]:
        for i, line in enumerate(ctx.code_lines):
            if not rx.search(line):
                continue
            if DECLARATION.match(line):
                continue  # defining a retry helper is not calling one
            found.append((label, i + 1))
            break
    if len(found) < 2:
        return []
    labels = ", ".join(label for label, _ in found)
    line = max(ln for _, ln in found)
    return [(line, (
        f"{len(found)} retry layers in one call path ({labels}) with no shared "
        f"budget — attempts multiply rather than add"))]


# --------------------------------------------------------------------------
# S18 — fail fast (validate before expensive work)
# --------------------------------------------------------------------------

EXTERNAL_CALL = re.compile(
    r"\b(fetch|axios|got|requests\s*\.|httpx\s*\.|aiohttp|urlopen"
    r"|\.query\s*\(|\.findMany\s*\(|\.execute\s*\(|generateContent"
    r"|\.send\s*\(|\.invoke\s*\()", re.I)
VALIDATION = re.compile(
    r"(?i)(\bvalidate\w*\s*\(|\bis_?valid\b|\.parse\s*\(|\bschema\b|\bassert\b"
    r"|throw new (Validation|BadRequest|TypeError|RangeError)"
    r"|raise (ValueError|TypeError|ValidationError))")
FUNC_TS = re.compile(
    r"^\s*(export\s+)?(default\s+)?(async\s+)?(function\s+\w+|const\s+\w+\s*=|"
    r"(public|private|protected)?\s*\w+\s*\([^)]*\)\s*[:{])")
FUNC_PY = re.compile(r"^\s*(async\s+)?def\s+\w+")


def s18_fail_fast(ctx) -> Result:
    is_py = _lang_key(ctx) == "python"
    func_re = FUNC_PY if is_py else FUNC_TS
    lines = ctx.code_lines

    starts = [i for i, ln in enumerate(lines) if func_re.match(ln)]
    if not starts:
        return []
    starts.append(len(lines))

    out: Result = []
    for a, b in zip(starts, starts[1:]):
        first_call = first_valid = None
        for i in range(a, b):
            if first_call is None and EXTERNAL_CALL.search(lines[i]):
                first_call = i
            if first_valid is None and VALIDATION.search(lines[i]):
                first_valid = i
        if first_call is not None and first_valid is not None and first_call < first_valid:
            out.append((first_valid + 1, (
                "input is validated after the external call on line "
                f"{first_call + 1} — work is paid for before it is known to be needed")))
            if len(out) >= 3:
                break
    return out


# --------------------------------------------------------------------------
# S29 — bounded query fan-out (no N+1 lazy-loading amplification)
# --------------------------------------------------------------------------

# Only files that touch persistence can lazy-load; a DTO loop elsewhere is not
# a query.
PERSISTENCE_CONTEXT = re.compile(
    r"(javax|jakarta)\.persistence|org\.hibernate|org\.springframework\.data"
    r"|@\s*(Entity|Transactional)\b|\bEntityManager\b|\w+Repository\b")
# Lazy loading is a JPA/Hibernate behaviour. A document or aggregate store
# (Spring Data MongoDB, JDBC, Cassandra, …) loads a nested list with its
# parent, so reading through it per element is not a query — unless the file
# is JPA as well.
NON_ORM_STORE = re.compile(
    r"org\.springframework\.data\.(mongodb|jdbc|cassandra|couchbase"
    r"|elasticsearch|redis|neo4j|r2dbc)|\bcom\.mongodb\.")
JPA_CONTEXT = re.compile(r"(javax|jakarta)\.persistence|org\.hibernate")
# Batch fetching (`@BatchSize`, `FetchMode.SUBSELECT`) and fetch/load graphs
# bound the fan-out as well: N+1 becomes N/size+1, or one query.
EAGER_FETCH_HINT = re.compile(
    r"(?i)@\s*(Named)?EntityGraph\b|JOIN\s+FETCH|Hibernate\s*\.\s*initialize\s*\("
    r"|FetchType\s*\.\s*EAGER|@\s*BatchSize\b|FetchMode\s*\.\s*(SUBSELECT|JOIN)"
    r"|\.(fetch|load)graph\b")
# `for (Order order : orders)` / `for (final Order order : repo.findAll())`.
# One level of nested generics (`Map.Entry<String, List<Order>>`); the two
# alternatives start with disjoint characters, so this cannot backtrack
# catastrophically on a long line.
FOREACH_JAVA = re.compile(
    r"\bfor\s*\(\s*(?:final\s+)?([\w.]+)(?:<(?:[^<>]|<[^<>]*>)*>)?(?:\[\])*"
    r"\s+(\w+)\s*:([^\n]*)")
# Element types that are never managed entities: JDK values, map entries, and
# the DTO naming conventions. Reading through them is not a query.
S29_VALUE_TYPE = re.compile(
    r"(?:^|\.)(?:String|CharSequence|Integer|Long|Short|Byte|Double|Float"
    r"|Boolean|Character|Number|BigDecimal|BigInteger|UUID|Object|Optional"
    r"|Entry|File|Path|URI|URL|Instant|Duration|Date|Local\w*|Zoned\w*"
    r"|Offset\w*|Class|int|long|short|byte|double|float|boolean|char)$"
    r"|(?:Dto|DTO|Request|Response|View|Vm|VM|Projection|Payload|Command"
    r"|Event|Form)$")
# An iterable already mapped (`.map(OrderDto::from)`) yields DTOs, not rows.
S29_MAPPED_SOURCE = re.compile(r"\.\s*map\s*\(|Dto|DTO")
# What follows `el.getX().` — a collection operation or a further getter is
# what touches an association. String/Optional/value calls (`trim`, `orElse`,
# `equals`, `compareTo`, `name`) read a column that is already loaded.
S29_COLLECTION_OPS = frozenset((
    "size", "isEmpty", "stream", "parallelStream", "iterator", "forEach",
    "contains", "containsAll", "containsKey", "add", "addAll", "remove",
    "removeAll", "removeIf", "clear", "toArray", "values", "keySet",
    "entrySet"))
# Getters that never initialise a proxy or that belong to JDK value types.
# `getId()` on a Hibernate proxy returns the key without a query.
S29_VALUE_GETTERS = re.compile(
    r"get(?:Id|Class|Year|Month\w*|Day\w*|Hour|Minute|Second|Nano|Time"
    r"|Epoch\w*|Bytes|SimpleName)$")


def _s29_navigates(body: str, var: str) -> bool:
    chain = re.compile(
        rf"\b{re.escape(var)}\s*\.\s*get[A-Z]\w*\s*\(\s*\)\s*\.\s*(\w+)\s*\(\s*(\S?)")
    for m in chain.finditer(body):
        op, first_arg = m.group(1), m.group(2)
        if op in S29_COLLECTION_OPS:
            return True
        if op == "get" and first_arg and first_arg != ")":
            return True  # `getLineItems().get(0)`, not `Optional.get()`
        if re.fullmatch(r"get[A-Z]\w*", op) and not S29_VALUE_GETTERS.fullmatch(op):
            return True
    return False


def s29_n_plus_one(ctx) -> Result:
    """Flag a for-each whose body navigates *through* a getter on the loop
    element — `order.getLineItems().size()`, `order.getCustomer().getName()`.

    A bare `order.getId()` reads a column of the row already loaded and is not
    flagged; chaining off the getter is what touches an association. This is a
    heuristic, not dataflow: it cannot know the association is lazy, so any
    eager-fetch hint anywhere in the file suppresses it. It also cannot tell an
    `@Embedded` value (`order.getAddress().getCity()`) from an association.
    """
    out: Result = []
    try:
        text = ctx.code_text
        if not PERSISTENCE_CONTEXT.search(text) or EAGER_FETCH_HINT.search(text):
            return []
        if NON_ORM_STORE.search(text) and not JPA_CONTEXT.search(text):
            return []
        lines = ctx.code_lines
        for i, line in enumerate(lines):
            if "for" not in line:
                continue
            m = FOREACH_JAVA.search(line)
            if not m:
                continue
            elem_type, var, source = m.group(1), m.group(2), m.group(3)
            if S29_VALUE_TYPE.search(elem_type) or S29_MAPPED_SOURCE.search(source):
                continue
            end = _ts_block_end(lines, i) if "{" in line else min(i + 1, len(lines) - 1)
            body = "\n".join(lines[i:end + 1])
            if _s29_navigates(body, var):
                out.append((i + 1, (
                    f"loop over `{var}` navigates an association on each element "
                    "with no eager fetch hint (@EntityGraph, JOIN FETCH, "
                    "Hibernate.initialize) in this file — likely N+1 queries")))
                if len(out) >= 3:
                    break
    except Exception:  # a lead generator never breaks the scan
        return out
    return out
