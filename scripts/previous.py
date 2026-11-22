#!/usr/bin/env python3
"""Keep the finished scan a new scan replaces (#98).

`signals.py` calls `archive` just before it writes the new `hotspots.json`. The
live files stay where they are, because `bundle.py` reuses `findings/` for
unchanged bundles; the copy under `.thunderstruck/previous/` is for reading the
old scan. No model, no network, nothing of the scanned project is run. Nothing
a scan reads ever reads `previous/`, so a bundle cannot depend on it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import _common as c

KEEP = 3
# What is copied from `.thunderstruck/` (spec 2.2): files, then directories.
FILES = ("hotspots.json", "report.json", "report.md", "report.html", "index.json",
         "validation.json", "usage.json", "checks/verdicts.json", "checks/run.json")
DIRS = ("findings",)
# The only directories under previous/ this module may remove.
ARCHIVE_NAME = c.ARCHIVE_NAME
DIRNAME = c.PREVIOUS_DIRNAME

_IDS = "Finding ids (FR-001) are numbered per scan: refer to a finding by its key."


def _label(earlier: dict[str, Any]) -> str:
    return (f"the earlier scan of {str(earlier['generated_at'])[:10]} "
            f"(head {str(earlier['head'])[:7]}, since {earlier['since_date']})")


def warning_for(earlier: dict[str, Any], reason: str | None = None) -> str:
    """The sentence a replaced scan adds to the run warnings, from stored values only."""
    if earlier.get("archived"):
        return (f"{_label(earlier)} was replaced; a copy is in "
                f".thunderstruck/{DIRNAME}/{earlier['archived']}/. {_IDS}")
    return f"{_label(earlier)} was replaced and a copy could not be kept ({reason}). {_IDS}"


def _free_name(prev: Path, base: str) -> str:
    name, n = base, 1
    while (prev / name).exists() or (prev / name).is_symlink():
        n += 1
        name = f"{base}-{n}"
    return name


def _copy_into(out: Path, dest: Path) -> None:
    dest.mkdir()
    for rel in FILES:
        src = out / rel
        if src.is_symlink() or not src.is_file():
            continue
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel)
    for rel in DIRS:
        src = out / rel
        if c.is_real_dir(src):
            shutil.copytree(src, dest / rel, symlinks=True)


def _prune(prev: Path) -> None:
    names = sorted(p.name for p in prev.iterdir()
                   if ARCHIVE_NAME.match(p.name) and c.is_real_dir(p))
    for name in names[:-KEEP]:
        shutil.rmtree(prev / name, ignore_errors=True)


def archive(repo: Path, new_identity: tuple | None) -> dict[str, Any]:
    """Copy the finished earlier scan when the scan about to replace it differs.

    Returns `{"archived": name | None, "warning": str | None, "previous": {...} | None}`.
    `previous` is what `hotspots.json` records; it is None when nothing was replaced.
    """
    nothing = {"archived": None, "warning": None, "previous": None}
    out = c.out_dir(repo)
    hotspots = c.load_json(out / "hotspots.json", None)
    report = c.load_json(out / "report.json", None)
    stored = report.get("schema") if isinstance(report, dict) else None
    # the schema the stored report was written with, so a version bump is a different scan
    old_identity = c.scan_identity(hotspots, stored if isinstance(stored, str) else None)
    if old_identity is None or not c.scan_finished(out) or old_identity == new_identity:
        return nothing
    earlier = {"archived": None, "generated_at": hotspots["generated_at"],
               "head": hotspots["repo"]["head"], "since_date": hotspots["window"]["since_date"]}

    prev = out / DIRNAME
    if prev.is_symlink() or (prev.exists() and not prev.is_dir()):
        return {"archived": None, "previous": earlier,
                "warning": warning_for(earlier, f"{DIRNAME} is not a plain directory")}
    base = f"{earlier['generated_at'][:10].replace('-', '')}-{earlier['head'][:7]}"
    try:
        prev.mkdir(exist_ok=True)
        name = _free_name(prev, base)
        try:
            _copy_into(out, prev / name)
        except BaseException:
            shutil.rmtree(prev / name, ignore_errors=True)
            raise
    except OSError as exc:
        return {"archived": None, "previous": earlier,
                "warning": warning_for(earlier, exc.strerror or exc)}
    earlier["archived"] = name
    try:
        _prune(prev)
    except OSError:
        pass
    return {"archived": name, "warning": warning_for(earlier), "previous": earlier}

