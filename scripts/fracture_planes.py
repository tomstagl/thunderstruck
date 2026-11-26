"""Fracture planes (#112): stack-specific guidance, loaded and checked.

Spec: docs/superpowers/specs/2026-11-20-fracture-planes-design.md

A plane is plugin content: `planes/<id>/plane.yaml` says when it applies and
how each Tier A/B pattern is covered, `planes/<id>/rubric.md` says, per
pattern, what counts as protection on that stack. A script selects planes
from tracked files and embeds their text; a model only applies it.

`load_planes` never raises for one bad plane: it returns the planes that
loaded and one problem per failure, so a scan skips a broken plane and names
it in `warnings` instead of stopping.

Stdlib and _common only; pyyaml is imported inside the loader, as
`_common.load_catalog` does. The guardrail hook never imports this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import _common as c

PLANE_SCHEMA = "thunderstruck.plane/v1"
MATURITIES = ("seed", "calibrated")
MAX_RULE_FILES = 25
MAX_READ_BYTES = 65536

CELL_STATES = ("na", "planned")
MANIFEST_KEYS = ("schema", "id", "title", "maturity", "languages", "detect", "supersedes", "cells")
RULE_KEYS = ("file", "contains")

_SECTION = re.compile(r"^## (General|S\d+)\s*$")


@dataclass(frozen=True)
class DetectRule:
    file: str
    contains: str | None


@dataclass(frozen=True)
class RubricEntry:
    pattern_id: str
    text: str


@dataclass(frozen=True)
class Plane:
    id: str
    title: str
    maturity: str
    languages: tuple[str, ...]
    detect: tuple[DetectRule, ...]
    supersedes: tuple[str, ...]
    cells: dict[str, dict[str, str]]
    rubric: dict[str, RubricEntry]
    general: str
    rubric_hash: str


class _Problem(Exception):
    def __init__(self, file: str, text: str):
        super().__init__(text)
        self.file = file
        self.text = text


def planes_dir() -> Path:
    """The plugin's own planes directory. Never the scanned repository's."""
    return c.plugin_root() / "planes"


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _strings(value, file: str, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise _Problem(file, f"{key} must be a list of non-empty strings")
    return tuple(value)


def _parse_manifest(directory: Path) -> dict:
    import yaml  # deferred: the guardrail hook must not need pyyaml

    path = directory / "plane.yaml"
    if not path.is_file():
        raise _Problem("plane.yaml", "missing")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise _Problem("plane.yaml", "not UTF-8")
    except yaml.YAMLError:
        raise _Problem("plane.yaml", "not valid YAML")
    if not isinstance(doc, dict):
        raise _Problem("plane.yaml", "must be a mapping")
    unknown = sorted(str(k) for k in doc if k not in MANIFEST_KEYS)
    if unknown:
        raise _Problem("plane.yaml", f"unknown key '{unknown[0]}'")
    if doc.get("schema") != PLANE_SCHEMA:
        raise _Problem("plane.yaml", f"schema must be '{PLANE_SCHEMA}'")
    if doc.get("id") != directory.name:
        raise _Problem("plane.yaml", f"id '{doc.get('id')}' does not match the directory")
    title = doc.get("title")
    if not isinstance(title, str) or not title.strip() or "\n" in title:
        raise _Problem("plane.yaml", "title must be a non-empty single line")
    if doc.get("maturity") not in MATURITIES:
        raise _Problem("plane.yaml", f"maturity must be one of {', '.join(MATURITIES)}")
    languages = _strings(doc.get("languages"), "plane.yaml", "languages")
    if not languages:
        raise _Problem("plane.yaml", "languages must name at least one language")

    rules = doc.get("detect")
    if not isinstance(rules, list) or not rules:
        raise _Problem("plane.yaml", "detect must be a non-empty list")
    detect = []
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict) or any(k not in RULE_KEYS for k in rule):
            raise _Problem("plane.yaml", f"detect[{i}] may only have 'file' and 'contains'")
        file = rule.get("file")
        if not isinstance(file, str) or not file:
            raise _Problem("plane.yaml", f"detect[{i}] needs a non-empty 'file'")
        contains = rule.get("contains")
        if contains is not None and (not isinstance(contains, str) or not contains):
            raise _Problem("plane.yaml", f"detect[{i}] 'contains' must be a non-empty string")
        detect.append(DetectRule(file=file, contains=contains))

    supersedes = doc.get("supersedes", [])
    supersedes = _strings(supersedes if supersedes is not None else [], "plane.yaml", "supersedes")

    cells_doc = doc.get("cells", {})
    if cells_doc is None:
        cells_doc = {}
    if not isinstance(cells_doc, dict):
        raise _Problem("plane.yaml", "cells must be a mapping")
    cells: dict[str, dict[str, str]] = {}
    for pid, entry in cells_doc.items():
        pid = str(pid)
        if not isinstance(entry, dict) or len(entry) != 1 or next(iter(entry)) not in CELL_STATES:
            raise _Problem("plane.yaml", f"cells.{pid} must be exactly one of na, planned")
        state, reason = next(iter(entry.items()))
        if not isinstance(reason, str) or not reason.strip():
            raise _Problem("plane.yaml", f"cells.{pid} needs a non-empty reason")
        cells[pid] = {state: reason.strip()}

    return {
        "title": title.strip(), "maturity": doc["maturity"], "languages": languages,
        "detect": tuple(detect), "supersedes": supersedes, "cells": cells,
    }


def _parse_rubric(directory: Path) -> tuple[str, dict[str, RubricEntry], str]:
    """The LF-normalised text, the pattern sections and the General text."""
    path = directory / "rubric.md"
    if not path.is_file():
        raise _Problem("rubric.md", "missing")
    try:
        text = _lf(path.read_bytes().decode("utf-8")).rstrip("\n") + "\n"
    except UnicodeDecodeError:
        raise _Problem("rubric.md", "not UTF-8")
    bodies: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.split("\n"):
        m = _SECTION.match(line)
        if m:
            name = m.group(1)
            if name in bodies:
                raise _Problem("rubric.md", f"section '{name}' appears twice")
            current = bodies[name] = []
        elif line.startswith("## "):
            raise _Problem("rubric.md", f"unrecognised heading '{line.rstrip()}'")
        elif current is None:
            if line.strip():
                raise _Problem("rubric.md", "text before the first section")
        else:
            current.append(line)
    rubric = {
        name: RubricEntry(pattern_id=name, text="\n".join(lines).strip())
        for name, lines in sorted(bodies.items()) if name != "General"
    }
    general = "\n".join(bodies.get("General", [])).strip()
    return text, rubric, general


def _load_one(directory: Path) -> Plane:
    manifest = _parse_manifest(directory)
    text, rubric, general = _parse_rubric(directory)
    return Plane(
        id=directory.name,
        rubric=rubric,
        general=general,
        rubric_hash=c.sha256_text(manifest["title"] + "\n" + text),
        **manifest,
    )


def _supersedes_problems(planes: dict[str, Plane]) -> dict[str, str]:
    """Planes to skip for an unknown or cyclic `supersedes`, with the reason.

    Skipping a plane can make another plane's `supersedes` unknown, so this
    runs to a fixed point.
    """
    bad: dict[str, str] = {}
    for pid in sorted(planes):
        path, seen = [pid], {pid}
        stack = [iter(planes[pid].supersedes)]
        while stack:
            nxt = next(stack[-1], None)
            if nxt is None:
                stack.pop()
                path.pop()
                continue
            if nxt == pid:
                bad[pid] = "supersedes cycle: " + " -> ".join(path + [pid])
                break
            if nxt in planes and nxt not in seen:
                seen.add(nxt)
                path.append(nxt)
                stack.append(iter(planes[nxt].supersedes))
    while True:
        live = {k for k in planes if k not in bad}
        added = False
        for pid in sorted(live):
            unknown = [s for s in planes[pid].supersedes if s not in live]
            if unknown:
                bad[pid] = f"supersedes unknown plane '{unknown[0]}'"
                added = True
        if not added:
            return bad


def load_planes(directory: Path | None = None) -> tuple[dict[str, Plane], list[str]]:
    """Every plane under `directory` that loads, and one problem per one that does not.

    Problems read `planes/<dir>/<file>: <problem>`. A missing directory is no
    planes and no problem.
    """
    root = Path(directory) if directory is not None else planes_dir()
    if not root.is_dir():
        return {}, []
    planes: dict[str, Plane] = {}
    problems: list[str] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        try:
            planes[entry.name] = _load_one(entry)
        except _Problem as exc:
            problems.append(f"planes/{entry.name}/{exc.file}: {exc.text}")
    for pid, text in sorted(_supersedes_problems(planes).items()):
        del planes[pid]
        problems.append(f"planes/{pid}/plane.yaml: {text}")
    return dict(sorted(planes.items())), sorted(problems)


# --------------------------------------------------------------------------
# the completeness gate (spec §2.2)
# --------------------------------------------------------------------------

MAX_SECTION_CHARS = 700
MAX_GENERAL_CHARS = 800
LABELS = ("**Counts as protection.**", "**Does not count.**")

# Spec §2.2 writes these with \s; [ \t] is meant, so a match never runs on
# across a line break.
_STRUCTURE = (
    ("a heading", re.compile(r"^[ \t]{0,3}#{1,6}([ \t]|$)", re.MULTILINE)),
    ("a setext underline", re.compile(r"^[ \t]{0,3}(=+|-+)[ \t]*$", re.MULTILINE)),
    ("a code fence", re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})", re.MULTILINE)),
)
_LEDGER_FIELD = re.compile(r"^[ \t>*-]*(?:\*\*)?(Repository|Commit|n):", re.MULTILINE)


def tier_ab_ids(catalog: dict) -> list[str]:
    """Tier A and B pattern ids, in catalog order."""
    return [p["id"] for p in catalog.get("patterns") or []
            if str(p.get("tier", "")).upper() in ("A", "B")]


def cell_state(plane: Plane, pattern_id: str) -> str:
    """`rubric`, `na`, `planned` or `missing`. Both rubric and cell is a gate problem."""
    if pattern_id in plane.rubric:
        return "rubric"
    cell = plane.cells.get(pattern_id)
    if cell:
        return next(iter(cell))
    return "missing"


def _body_problems(where: str, name: str, text: str, limit: int) -> list[str]:
    problems = []
    if len(text) > limit:
        problems.append(f"{where}: {name} is {len(text)} characters, over the {limit} limit")
    for what, pattern in _STRUCTURE:
        if pattern.search(text):
            problems.append(f"{where}: {name} contains {what}")
    return problems


def check_planes(planes: dict[str, Plane], catalog: dict, repo_root: Path | None = None) -> list[str]:
    """Every completeness rule a loaded plane breaks; `[]` when clean.

    `repo_root` is the plugin root, where `docs/calibration/planes/` lives.
    Unknown and cyclic `supersedes` are load problems and never reach here.
    """
    root = Path(repo_root) if repo_root is not None else c.plugin_root()
    ab = tier_ab_ids(catalog)
    known = set(ab)
    languages = catalog.get("languages") or {}
    aliases = catalog.get("aliases") or {}
    problems: list[str] = []
    for pid in sorted(planes):
        plane = planes[pid]
        manifest, rubric = f"planes/{pid}/plane.yaml", f"planes/{pid}/rubric.md"
        for lang in plane.languages:
            if lang in aliases:
                problems.append(f"{manifest}: language '{lang}' is an alias of '{aliases[lang]}'; "
                                f"name '{aliases[lang]}'")
            elif lang not in languages:
                problems.append(f"{manifest}: language '{lang}' is not in the catalog")
        for name in sorted(set(plane.rubric) - known):
            problems.append(f"{rubric}: {name} is not a Tier A/B pattern")
        for name in sorted(set(plane.cells) - known):
            problems.append(f"{manifest}: {name} is not a Tier A/B pattern")
        for name in ab:
            if name in plane.rubric and name in plane.cells:
                problems.append(f"{manifest}: {name} has both a rubric section and a cells entry")
            elif cell_state(plane, name) == "missing":
                problems.append(f"{manifest}: {name} has no rubric section and no cells entry")
        for name, entry in sorted(plane.rubric.items()):
            for label in LABELS:
                if not re.search(r"^" + re.escape(label), entry.text, re.MULTILINE):
                    problems.append(f"{rubric}: {name} lacks a {label} paragraph")
            problems += _body_problems(rubric, name, entry.text, MAX_SECTION_CHARS)
        problems += _body_problems(rubric, "General", plane.general, MAX_GENERAL_CHARS)
        if plane.maturity == "calibrated":
            for name in ab:
                if cell_state(plane, name) == "planned":
                    problems.append(f"{manifest}: calibrated, but {name} is planned")
            ledger = root / "docs" / "calibration" / "planes" / f"{pid}.md"
            text = c.read_text(ledger) if ledger.is_file() else None
            found = set(_LEDGER_FIELD.findall(text or ""))
            if found != {"Repository", "Commit", "n"}:
                problems.append(f"planes/{pid}: calibrated, but docs/calibration/planes/{pid}.md is "
                                f"missing or does not name Repository:, Commit: and n:")
    return problems


# --------------------------------------------------------------------------
# selection (spec §3)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Selected:
    plane_id: str
    matched_by: str
    rubric_hash: str


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`*` within a path segment, `**/` across zero or more directories, the rest literal."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append(r"(?:[^/]+/)*")
            i += 3
        elif pattern[i] == "*":
            out.append(r"[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def head_reader(repo: Path) -> Callable[[str], str | None]:
    """Read the first MAX_READ_BYTES of a tracked file, or None.

    Undecodable bytes are replaced. A path git surrogate-escaped can raise
    UnicodeEncodeError (a ValueError) or FileNotFoundError: both are None.
    """
    def read(rel: str) -> str | None:
        try:
            with open(Path(repo) / rel, "rb") as fh:
                return fh.read(MAX_READ_BYTES).decode("utf-8", errors="replace")
        except (OSError, ValueError):
            return None
    return read


def _depth_order(path: str) -> tuple[int, str]:
    return path.count("/"), path


def _match(plane: Plane, paths: list[str], read: Callable[[str], str | None],
           usable: Callable[[str], bool]) -> tuple[str | None, list[str]]:
    """The first path that matches one of the plane's rules, and warnings."""
    warnings: list[str] = []
    for rule in plane.detect:
        rx = glob_to_regex(rule.file)
        candidates = sorted((p for p in paths if rx.fullmatch(p)), key=_depth_order)
        candidates = [p for p in candidates if usable(p)]
        for path in candidates[:MAX_RULE_FILES]:
            if rule.contains is None:
                return path, warnings
            head = read(path)
            if head is not None and rule.contains in head:
                return path, warnings
        if len(candidates) > MAX_RULE_FILES:
            warnings.append(f"plane {plane.id}: rule {rule.file} had {len(candidates)} "
                            f"candidates, examined {MAX_RULE_FILES}")
    return None, warnings


def select(index: Iterable[str], read: Callable[[str], str | None], planes: dict[str, Plane],
           usable: Callable[[str], bool] = lambda p: True) -> tuple[list[Selected], list[str]]:
    """The active planes, sorted by id, with the first path that matched each.

    A pure function of the paths, what `read` returns for them and the
    planes: index order never matters. `usable` is asked only about paths a
    rule's glob already matched. A plane another active plane supersedes is
    dropped.
    """
    paths = sorted(set(index))
    active: dict[str, str] = {}
    warnings: list[str] = []
    for pid in sorted(planes):
        matched, rule_warnings = _match(planes[pid], paths, read, usable)
        warnings += rule_warnings
        if matched is not None:
            active[pid] = matched
    superseded = {s for pid in active for s in planes[pid].supersedes}
    selected = [Selected(pid, path, planes[pid].rubric_hash)
                for pid, path in sorted(active.items()) if pid not in superseded]
    return selected, warnings
