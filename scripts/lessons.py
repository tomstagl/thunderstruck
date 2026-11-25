"""Lessons a repository keeps (#106): read, validate, match and render.

Spec: docs/superpowers/specs/2026-11-12-repo-lessons-design.md

A lesson is a hint a repository's maintainers wrote after a review: what to
check in code like this. It reaches the investigator's bundle and the
skeptic's brief for the hotspots it applies to, and nowhere else. It is
repository-authored text going into a model prompt, so it is validated,
flattened to one line per field, capped, shown inside a fence longer than any
backtick run in it, and framed as data. It is never evidence: nothing here
touches ranking, confidence, suppression or a citation.

signals.py calls `scan` once and records the result in hotspots.json.
bundle.py, verify.py and report.py only read that record (`for_hotspot`,
`summary`), so one scan sees one snapshot of the file.

Stdlib and _common only.
"""

from __future__ import annotations

import os
import re
import stat
import tomllib
import unicodedata
from pathlib import Path
from typing import Any

import _common as c

NAME = c.LESSONS_FILENAME
EVERY = "all"                 # applies_to value: every hotspot, whatever it carries
MAX_FILE_BYTES = 64 * 1024    # larger: the file is not read at all
MAX_ENTRIES = 40              # entries read; later ones are skipped
MAX_APPLIES_TO = 12
TEXT_CAPS = {"statement": 600, "how_to_check": 400, "source": 200, "confirmed_by": 120}
ENTRY_KEYS = ("id", "applies_to", *TEXT_CAPS)
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}\Z")
PATTERN_RE = re.compile(r"^[A-Z]{1,5}[0-9]{1,3}\Z")


def _shown(value: Any, limit: int = 40) -> str:
    """A received value, quoted and short: repr escapes controls and invisibles."""
    text = repr(value)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _invisible(text: str) -> str | None:
    """The first control or invisible formatting character, as U+XXXX."""
    for ch in text:
        if unicodedata.category(ch) in ("Cc", "Cf"):
            return f"U+{ord(ch):04X}"
    return None


# --------------------------------------------------------------------------
# reading and validating
# --------------------------------------------------------------------------


def _read(repo: Path) -> tuple[str | None, str | None]:
    """(text, why not). (None, None) when there is no lessons file."""
    path = Path(repo) / NAME
    if not os.path.lexists(path):
        return None, None
    # the one rule for "a regular file the working tree really holds": no
    # symlink anywhere on the path, no directory, no device. Mode 100644 is
    # a stand-in: the file may not be tracked yet.
    if (why := c.tracked_file_problem(Path(repo), NAME, "100644")):
        return None, why
    # Opened without blocking and checked again on the descriptor: a FIFO put at
    # the name after the check above must not hang the scan.
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as fh:
            if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                return None, "is not a regular file in the working tree"
            raw = fh.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        return None, f"could not be read ({exc.strerror or type(exc).__name__})"
    if len(raw) > MAX_FILE_BYTES:
        return None, f"is larger than {MAX_FILE_BYTES // 1024} KiB"
    try:
        return raw.decode("utf-8-sig"), None   # an editor's byte order mark is not content
    except UnicodeDecodeError:
        return None, "is not valid UTF-8"


def _applies_to(value: Any, catalog: dict | None) -> tuple[list[str] | None, str | None]:
    if not isinstance(value, list) or not value:
        return None, f'applies_to must be a non-empty list of pattern ids, or ["{EVERY}"]'
    if len(value) > MAX_APPLIES_TO:
        return None, f"applies_to has {len(value)} items; the limit is {MAX_APPLIES_TO}"
    for item in value:
        if not isinstance(item, str):
            return None, f"applies_to item {_shown(item)} is not a string"
    items = list(dict.fromkeys(value))
    for item in items:
        if item == EVERY:
            if len(items) > 1:
                return None, f'"{EVERY}" must be the only item of applies_to'
        elif catalog is None:
            if not PATTERN_RE.match(item):
                return None, f"applies_to item {_shown(item)} is not a pattern id"
        elif item not in catalog["_by_id"]:
            if item == "OTHER":
                return None, f'OTHER is never carried by a hotspot; use ["{EVERY}"]'
            if item in catalog["_tier_c_by_id"]:
                return None, f"{item} is Tier C: no detector produces it, so no hotspot carries it"
            hint = f" (did you mean {item.upper()}?)" if item.upper() in catalog["_by_id"] else ""
            return None, f"unknown pattern id {_shown(item)}{hint}"
    return items, None


def check_entry(raw: Any, catalog: dict | None) -> tuple[dict | None, list[str]]:
    """One lesson, or every reason it is rejected. With no catalog only the
    form of a pattern id is checked: that is for a record this module wrote."""
    if not isinstance(raw, dict):
        return None, ["is not a table"]
    problems: list[str] = []
    extra = sorted(str(k) for k in set(raw) - set(ENTRY_KEYS))
    if extra:
        problems.append("unknown key(s) " + ", ".join(_shown(k) for k in extra[:5]))
    lesson: dict[str, Any] = {}
    lid = raw.get("id")
    if isinstance(lid, str) and ID_RE.match(lid):
        lesson["id"] = lid
    else:
        problems.append(f"id {_shown(lid)} must be 1 to 40 letters, digits, '.', '_' or '-', "
                        f"starting with a letter or digit")
    applies, why = _applies_to(raw.get("applies_to"), catalog)
    if why:
        problems.append(why)
    else:
        lesson["applies_to"] = applies
    for key, cap in TEXT_CAPS.items():
        value = raw.get(key)
        flat = _flat(value) if isinstance(value, str) else None
        if flat is None:
            problems.append(f"{key} is missing or not a string")
        elif not flat:
            problems.append(f"{key} is empty")
        elif len(flat) > cap:
            problems.append(f"{key} is {len(flat)} characters; the limit is {cap}")
        elif (bad := _invisible(flat)):
            problems.append(f"{key} contains a control or invisible character ({bad})")
        else:
            lesson[key] = flat
    if problems:
        return None, problems
    return {k: lesson[k] for k in ENTRY_KEYS}, []


def _label(raw: Any, n: int) -> str:
    lid = raw.get("id") if isinstance(raw, dict) else None
    return f"{lid} (entry {n})" if isinstance(lid, str) and ID_RE.match(lid) else f"entry {n}"


def load(repo: Path, catalog: dict) -> tuple[dict | None, list[str]]:
    """The repository's lessons file, validated: (None, []) when there is none,
    else the record's first half and one warning per problem. Never raises
    for anything the file contains."""
    text, why = _read(repo)
    if text is None and why is None:
        return None, []
    block: dict[str, Any] = {"file": NAME, "status": "not_loaded", "accepted": [], "skipped": 0}
    if text is None:
        return block, [f"{NAME} {why}; no lessons were applied."]
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return block, [f"{NAME} is not valid TOML ({_shown(_flat(str(exc)), 120)}); "
                       f"no lessons were applied."]
    block["status"] = "loaded"
    warnings: list[str] = []
    stray = sorted(str(k) for k in set(doc) - {"lesson"})
    if stray:
        warnings.append(f"{NAME}: unknown top-level key(s) {', '.join(_shown(k) for k in stray[:5])}; "
                        f"only [[lesson]] is read.")
    entries = doc.get("lesson")
    if entries is None:
        warnings.append(f"{NAME} has no [[lesson]] entry; there is nothing to apply.")
        return block, warnings
    if not isinstance(entries, list):
        block["status"] = "not_loaded"
        return block, warnings + [f"{NAME}: `lesson` must be an array of tables ([[lesson]]); "
                                  f"no lessons were applied."]
    first: dict[str, int] = {}
    for n, raw in enumerate(entries[:MAX_ENTRIES], 1):
        lesson, problems = check_entry(raw, catalog)
        if lesson and lesson["id"] in first:
            lesson, problems = None, [f"duplicate id (first used at entry {first[lesson['id']]})"]
        if lesson:
            first[lesson["id"]] = n
            block["accepted"].append(lesson)
        else:
            block["skipped"] += 1
            warnings.append(f"{NAME}: lesson {_label(raw, n)} skipped: {'; '.join(problems)}.")
    if len(entries) > MAX_ENTRIES:
        block["skipped"] += len(entries) - MAX_ENTRIES
        warnings.append(f"{NAME} has {len(entries)} lessons; only the first {MAX_ENTRIES} are read "
                        f"and {len(entries) - MAX_ENTRIES} were skipped.")
    return block, warnings
