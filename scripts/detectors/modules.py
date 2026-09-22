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

_LITERAL_MS = re.compile(r"^\s*\d+(\.\d+)?(\s*[*]\s*\d+(\.\d+)?)*\s*$")

SLEEP_RES: dict[str, list[re.Pattern]] = {
    "typescript": [
        re.compile(r"setTimeout\s*\(\s*[^,]+?,\s*(?P<arg>[^),]+)"),
        re.compile(r"\b(?:sleep|delay|wait|pause)\s*\(\s*(?P<arg>[^),]*)"),
    ],
    "python": [
        re.compile(r"\b(?:time|asyncio)\s*\.\s*sleep\s*\(\s*(?P<arg>[^),]*)"),
        re.compile(r"\b(?:sleep|delay)\s*\(\s*(?P<arg>[^),]*)"),
    ],
}


def _lang_key(ctx) -> str:
    return "python" if ctx.lang == "python" else "typescript"


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

            if _LITERAL_MS.match(arg):
                if not file_growth and "constant" not in reported:
                    reported.add("constant")
                    out.append((i + 1, (
                        f"retry waits a constant {arg} — no exponential growth, so "
                        f"every client retries on the same schedule")))
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
