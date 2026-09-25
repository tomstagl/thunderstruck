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
    m = anchor.search(text)
    if not m:
        return []
    line_no = text.count("\n", 0, m.start()) + 1
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
