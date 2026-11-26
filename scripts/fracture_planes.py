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
