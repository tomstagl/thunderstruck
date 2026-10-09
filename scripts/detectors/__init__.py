"""Catalog-driven stability detectors.

A detector produces a *lead*, never a finding. Every hit carries a concrete
file:line so the investigator can confirm or reject it against the real code,
and so validate.py can check that a `detector` evidence ref resolves.

Three kinds, declared in catalog/stability.yaml:

  regex        a line matches `pattern`; optionally a regex must be absent
               (`absent_within`) or present (`present_within`) in the next
               `window` lines. An optional `require` skips files it matches
               nowhere, exactly as for file_absent.
  file_absent  `anchor` matches somewhere in the file and `absent` matches
               nowhere. An optional `require` must also match somewhere in
               the file, so a whole-file absence can be scoped to files that
               show the construct the pattern is about (a fan-out, a retry).
               The hit lands on the first anchor line.
  module       dispatches to a handler in detectors/modules.py, for structure
               a regex cannot see.

Any regex or file_absent detector may set `absent_before` with
`absent_before_window`: a hit (for file_absent, an anchor) is dropped when
the regex matches that many lines before it together with its own line.

Comments are blanked before matching (see _common.strip_comments) so that a
file which *describes* honouring Retry-After but never reads it still trips
the S03 detector. String literals are kept: header names and SQL live there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Iterable

try:  # package-relative when imported as scripts.detectors
    from .. import _common  # type: ignore
except ImportError:  # plain sys.path use, which is how the scripts run
    import _common  # type: ignore

MAX_HITS_PER_DETECTOR_PER_FILE = 5
_RE_CACHE: dict[str, re.Pattern] = {}


def _rx(pattern: str, multiline: bool = False) -> re.Pattern:
    """Compile and cache. Window and whole-file regexes are MULTILINE so that
    a catalog author's `^` and `$` mean line boundaries, not the boundaries of
    whatever chunk the engine happened to slice."""
    key = f"{int(multiline)}\x00{pattern}"
    cached = _RE_CACHE.get(key)
    if cached is None:
        flags = re.MULTILINE if multiline else 0
        cached = _RE_CACHE[key] = re.compile(pattern, flags)
    return cached


@dataclass(frozen=True)
class Hit:
    pattern_id: str
    detector_id: str
    file: str
    line: int
    note: str
    confidence: str
    snippet: str

    @property
    def ref(self) -> str:
        """The form a finding cites: S05@src/lib/http.ts:12"""
        return f"{self.pattern_id}@{self.file}:{self.line}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ref"] = self.ref
        return d


@dataclass
class DetectorContext:
    rel_path: str
    lang: str
    raw_text: str
    code_text: str
    raw_lines: list[str]
    code_lines: list[str]


def build_context(rel_path: str, text: str, lang: str) -> DetectorContext:
    code = _common.strip_comments(text, lang)
    return DetectorContext(
        rel_path=rel_path,
        lang=lang,
        raw_text=text,
        code_text=code,
        raw_lines=text.split("\n"),
        code_lines=code.split("\n"),
    )


def _snippet(ctx: DetectorContext, line_no: int) -> str:
    idx = line_no - 1
    if 0 <= idx < len(ctx.raw_lines):
        return ctx.raw_lines[idx].strip()[:200]
    return ""


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


def _run_regex(ctx: DetectorContext, pattern: dict, det: dict) -> list[Hit]:
    lines = ctx.raw_lines if det.get("include_comments") else ctx.code_lines
    main = _rx(det["pattern"])
    absent = _rx(det["absent_within"], True) if det.get("absent_within") else None
    present = _rx(det["present_within"], True) if det.get("present_within") else None
    window = int(det.get("window", 1))
    offset = int(det.get("window_offset", 0))
    before = int(det.get("window_before", 0))
    req = det.get("require")
    if req and not _rx(req, True).search(
            ctx.raw_text if det.get("include_comments") else ctx.code_text):
        return []  # the file never does the thing the pattern guards

    hits: list[Hit] = []
    for i, line in enumerate(lines):
        if not main.search(line):
            continue
        if absent is not None or present is not None:
            start = i + offset
            lo = max(0, start - before)
            chunk = "\n".join(lines[lo:start + max(window, 1)])
            if absent is not None and absent.search(chunk):
                continue
            if present is not None and not present.search(chunk):
                continue
        if _excused_before(lines, i, det):
            continue
        hits.append(Hit(
            pattern_id=pattern["id"], detector_id=det["id"], file=ctx.rel_path,
            line=i + 1, note=det.get("note", ""),
            confidence=det.get("confidence", "medium"), snippet=_snippet(ctx, i + 1),
        ))
        if len(hits) >= MAX_HITS_PER_DETECTOR_PER_FILE:
            break
    return hits


def _run_file_absent(ctx: DetectorContext, pattern: dict, det: dict) -> list[Hit]:
    text = ctx.raw_text if det.get("include_comments") else ctx.code_text
    anchor = _rx(det["anchor"], True)
    absent = _rx(det["absent"], True)
    require = _rx(det["require"], True) if det.get("require") else None
    if require is not None and not require.search(text):
        return []  # the file never does the thing the pattern guards
    if absent.search(text):
        return []
    lines = text.split("\n")
    line_no = None
    for m in anchor.finditer(text):
        n = text.count("\n", 0, m.start()) + 1
        if not _excused_before(lines, n - 1, det):
            line_no = n  # the first anchor nothing before it excuses
            break
    if line_no is None:
        return []
    return [Hit(
        pattern_id=pattern["id"], detector_id=det["id"], file=ctx.rel_path,
        line=line_no, note=det.get("note", ""),
        confidence=det.get("confidence", "medium"), snippet=_snippet(ctx, line_no),
    )]


def _run_module(ctx: DetectorContext, pattern: dict, det: dict) -> list[Hit]:
    from . import modules

    handler = getattr(modules, det["handler"], None)
    if handler is None:
        return []
    out: list[Hit] = []
    for line_no, note in handler(ctx)[:MAX_HITS_PER_DETECTOR_PER_FILE]:
        out.append(Hit(
            pattern_id=pattern["id"], detector_id=det["id"], file=ctx.rel_path,
            line=line_no, note=note or det.get("note", ""),
            confidence=det.get("confidence", "medium"), snippet=_snippet(ctx, line_no),
        ))
    return out


_RUNNERS = {
    "regex": _run_regex,
    "file_absent": _run_file_absent,
    "module": _run_module,
}


def run_detectors(
    catalog: dict[str, Any],
    rel_path: str,
    text: str,
    lang: str,
    pattern_ids: Iterable[str] | None = None,
) -> list[Hit]:
    """Run every catalog detector for `lang` against one file."""
    det_lang = _common.detector_language(catalog, lang)
    ctx = build_context(rel_path, text, lang)
    wanted = set(pattern_ids) if pattern_ids is not None else None

    seen: set[tuple[str, str, int]] = set()
    hits: list[Hit] = []
    for pattern in catalog.get("patterns", []):
        if wanted is not None and pattern["id"] not in wanted:
            continue
        for det in (pattern.get("detectors") or {}).get(det_lang, []) or []:
            runner = _RUNNERS.get(det.get("kind", "regex"))
            if runner is None:
                continue
            try:
                found = runner(ctx, pattern, det)
            except re.error:
                continue  # a malformed catalog regex must not sink the scan
            for hit in found:
                key = (hit.pattern_id, hit.file, hit.line)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(hit)
    return hits


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
