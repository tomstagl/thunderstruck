#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0", "packaging>=24"]
# ///
"""Dependency source for verification (spec 2026-10-03-finding-verification-design.md §4).

Finds the packages a project declares, the version each is locked, pinned or
installed at, and copies the source of each available one into
.thunderstruck/deps/<ecosystem>/<name>@<version>/ so a skeptic can read it and
validate.py can resolve a `dependency` ref against it.

Reads manifests, lock files, package metadata and archives as data. Never
downloads, never runs a package manager or anything from a package.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402

DEPS_SCHEMA = "thunderstruck.deps/v1"
ECOSYSTEMS = ("pypi", "npm", "maven")
BASES = ("locked", "pinned", "declared_range")
# [0-9] and \Z, as validate.CODE_REF: no other digits, no trailing newline
DEP_REF = re.compile(
    r"^(?P<eco>pypi|npm|maven):(?P<name>(?:@[^/@:\s]+/)?[^@:\s]+)@(?P<version>[^:@\s]+)"
    r":(?P<path>[^:]+):(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?\Z")
SAFE_NAME = re.compile(r"^@?[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)?\Z")
SAFE_VERSION = re.compile(r"^[A-Za-z0-9._+-]+\Z")
REF_FORM = "ecosystem:name@version:path:line, e.g. pypi:kombu@5.7.0a1:kombu/utils/functional.py:318-332"


@dataclass(frozen=True)
class Limits:
    per_package_bytes: int = 30_000_000
    per_package_files: int = 20_000
    total_bytes: int = 300_000_000


LIMITS = Limits()


def index_path(repo: Path) -> Path:
    return c.out_dir(repo) / c.DEPS_DIRNAME / "index.json"


def load_index(repo: Path) -> dict | None:
    doc = c.load_json(index_path(repo), None)
    return doc if isinstance(doc, dict) and doc.get("schema") == DEPS_SCHEMA else None


def write_index(repo: Path, index: dict) -> None:
    c.write_json(index_path(repo), index)


def _safe(name: str, version: str) -> bool:
    return (bool(SAFE_NAME.match(name)) and bool(SAFE_VERSION.match(version))
            and ".." not in name.split("/") and version not in (".", ".."))


def snapshot_rel(eco: str, name: str, version: str) -> str:
    return f"{c.OUTPUT_DIRNAME}/{c.DEPS_DIRNAME}/{eco}/{name}@{version}"


def snapshot_dir(repo: Path, eco: str, name: str, version: str) -> Path:
    return repo / snapshot_rel(eco, name, version)


def _refuse(dest: Path, reason: str) -> str:
    shutil.rmtree(dest, ignore_errors=True)
    return reason


def copy_tree(files: list[tuple[str, Path]], dest: Path, limits: Limits) -> str | None:
    """Copy (relative path, source file) pairs under dest. All or nothing."""
    if len(files) > limits.per_package_files:
        return f"too large to snapshot ({len(files)} files > {limits.per_package_files})"
    total = 0
    for rel, src in files:
        if (why := c.path_problem(rel)):
            return f"refused {rel!r}: {why}"
        if src.is_symlink() or not src.is_file():
            return f"refused {rel!r}: a symlink or not a regular file"
        total += src.stat().st_size
    if total > limits.per_package_bytes:
        return f"too large to snapshot ({total // 1_000_000} MB > {limits.per_package_bytes // 1_000_000} MB)"
    for rel, src in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target, follow_symlinks=False)
    return None


def copy_jar(jar: Path, dest: Path, suffixes: tuple[str, ...], limits: Limits) -> str | None:
    """Extract the source entries of a sources jar under dest. All or nothing."""
    try:
        with zipfile.ZipFile(jar) as z:
            entries = [i for i in z.infolist() if not i.is_dir() and i.filename.endswith(suffixes)]
            if len(entries) > limits.per_package_files:
                return f"too large to snapshot ({len(entries)} files > {limits.per_package_files})"
            if sum(i.file_size for i in entries) > limits.per_package_bytes:
                return "too large to snapshot"
            for i in entries:
                if (why := c.path_problem(i.filename)):
                    return _refuse(dest, f"refused {i.filename!r}: {why}")
            for i in entries:
                data = z.read(i)
                if len(data) != i.file_size:
                    return _refuse(dest, f"refused {i.filename!r}: its size disagrees with the archive")
                target = dest / i.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    except (OSError, zipfile.BadZipFile) as exc:
        return _refuse(dest, f"could not read {jar.name}: {exc}")
    return None


def snapshot(repo: Path, index: dict, limits: Limits = LIMITS) -> dict:
    """Copy every available package's source into its snapshot directory.

    A package record from a discoverer carries `source` and, for a directory
    source, `files` (paths relative to `source`); a jar source carries `jar`.
    `files` and `jar` are dropped from the written index.
    """
    used = 0
    for p in index.get("packages", []):
        files = p.pop("files", None)
        jar = p.pop("jar", None)
        if p.get("status") != "available":
            continue
        name, version = p.get("name", ""), p.get("version") or ""
        if not _safe(name, version):
            p.update(status="unavailable", reason="unsafe package name or version", snapshot=None)
            continue
        dest = snapshot_dir(repo, p["ecosystem"], name, version)
        marker = dest / ".snapshot.json"
        prior = c.load_json(marker, None)
        if isinstance(prior, dict) and prior.get("id") == p["id"] and prior.get("version") == version:
            p["snapshot"] = snapshot_rel(p["ecosystem"], name, version)
            continue
        shutil.rmtree(dest, ignore_errors=True)
        if jar:
            why = copy_jar(Path(jar), dest, (".java", ".kt"), limits)
            count = sum(1 for f in dest.rglob("*") if f.is_file()) if why is None else 0
        else:
            pairs = [(rel, Path(p["source"]) / rel) for rel in (files or [])]
            why = copy_tree(pairs, dest, limits)
            count = len(pairs)
        size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) if why is None else 0
        if why is None and used + size > limits.total_bytes:
            why = _refuse(dest, "too large to snapshot (the scan's 300 MB total is spent)")
        if why:
            p.update(status="unavailable", reason=why, snapshot=None)
            continue
        used += size
        c.write_json(marker, {"id": p["id"], "version": version, "files": count})
        p["snapshot"] = snapshot_rel(p["ecosystem"], name, version)
    return index


def _count_lines(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for _ in fh) or 1


def resolve_dependency_ref(repo: Path, index: dict | None, ref: str) -> tuple[dict | None, str | None]:
    """Resolve `ecosystem:name@version:path:line[-end]` inside a snapshot."""
    m = DEP_REF.match(ref.strip()) if isinstance(ref, str) else None
    if not m:
        return None, f"{ref!r} is not {REF_FORM}"
    if index is None:
        return None, "no dependency source was read in this scan"
    pid = f"{m['eco']}:{m['name']}"
    pkg = next((p for p in index.get("packages", []) if p.get("id") == pid
                and p.get("status") == "available" and p.get("snapshot")), None)
    if pkg is None:
        return None, f"{pid} is not an available dependency in this scan (see .thunderstruck/deps/index.json)"
    if pkg["version"] != m["version"]:
        return None, f"{pid} was read at {pkg['version']}, not {m['version']}"
    if (why := c.path_problem(m["path"])):
        return None, f"{m['path']!r} {why}"
    root = (repo / pkg["snapshot"]).resolve()
    target = (root / m["path"]).resolve()
    if root not in target.parents or target.is_symlink() or not target.is_file():
        return None, f"{m['path']!r}: no such file in {pid}@{pkg['version']}"
    start, end = int(m["start"]), int(m["end"] or m["start"])
    total = _count_lines(target)
    if not 1 <= start <= end <= total:
        return None, f"lines {start}-{end} are outside {m['path']}, which has {total} lines"
    return {"id": pid, "version": pkg["version"], "path": m["path"], "start": start, "end": end}, None
