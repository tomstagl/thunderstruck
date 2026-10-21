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

import argparse
import json
import os
import re
import shutil
import sys
import tomllib
import xml.etree.ElementTree as ET
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



def pep503(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_lines(repo: Path, path: Path, seen: set[Path]) -> list[tuple[str, str]]:
    """(requirement text, repo-relative file) from a requirements file, following -r inside the repo."""
    if path in seen or not path.is_file():
        return []
    seen.add(path)
    out: list[tuple[str, str]] = []
    rel = path.relative_to(repo).as_posix()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ")):
            child = (path.parent / line.split(None, 1)[1]).resolve()
            if repo.resolve() in child.parents:
                out += _requirement_lines(repo, child, seen)
            continue
        if line.startswith("-") or "://" in line:
            continue  # options, editables and URLs name no released version
        out.append((line, rel))
    return out


def pypi_declared(repo: Path) -> dict[str, tuple[str, list[str]]]:
    from packaging.requirements import InvalidRequirement, Requirement

    texts: list[tuple[str, str]] = []
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        doc = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = doc.get("project") or {}
        groups = [project.get("dependencies") or []]
        groups += list((project.get("optional-dependencies") or {}).values())
        groups += [[x for x in g if isinstance(x, str)] for g in (doc.get("dependency-groups") or {}).values()]
        for group in groups:
            texts += [(t, "pyproject.toml") for t in group if isinstance(t, str)]
        poetry = (doc.get("tool") or {}).get("poetry") or {}
        tables = [poetry.get("dependencies") or {}, poetry.get("dev-dependencies") or {}]
        tables += [(g or {}).get("dependencies") or {} for g in (poetry.get("group") or {}).values()]
        for table in tables:
            for name, spec in table.items():
                if name.lower() == "python":
                    continue
                version = spec if isinstance(spec, str) else (spec or {}).get("version", "")
                texts.append((f"{name}{_poetry_spec(version)}", "pyproject.toml"))
    seen: set[Path] = set()
    for path in sorted([*repo.glob("requirements*.txt"), *(repo / "requirements").rglob("*.txt")]):
        texts += _requirement_lines(repo, path.resolve(), seen)
    declared: dict[str, tuple[str, list[str]]] = {}
    for text, where in texts:
        try:
            req = Requirement(text)
        except InvalidRequirement:
            continue
        key = pep503(req.name)
        spec, files = declared.get(key, (str(req.specifier), []))
        declared[key] = (spec or str(req.specifier), sorted({*files, where}))
    return declared


def _poetry_spec(version: str) -> str:
    """Poetry's ^ and ~ as PEP 440; anything else unchanged."""
    v = version.strip()
    if v in ("", "*"):
        return ""
    if v.startswith("^"):
        parts = v[1:].split(".")
        major = int(parts[0]) if parts[0].isdigit() else 0
        return f">={v[1:]},<{major + 1}" if major else f">={v[1:]}"
    if v.startswith("~"):
        return f"~={v[1:]}" if v.count(".") >= 1 else f">={v[1:]}"
    return v if v[0] in "<>=!~" else f"=={v}"


def pypi_locked(repo: Path) -> dict[str, str]:
    locked: dict[str, str] = {}
    for name in ("uv.lock", "poetry.lock", "pdm.lock"):
        path = repo / name
        if path.is_file():
            for pkg in tomllib.loads(path.read_text(encoding="utf-8")).get("package") or []:
                if isinstance(pkg, dict) and pkg.get("name") and pkg.get("version"):
                    locked.setdefault(pep503(pkg["name"]), str(pkg["version"]))
    pipfile = repo / "Pipfile.lock"
    if pipfile.is_file():
        doc = json.loads(pipfile.read_text(encoding="utf-8"))
        for section in ("default", "develop"):
            for name, spec in (doc.get(section) or {}).items():
                version = str((spec or {}).get("version", ""))
                if version.startswith("=="):
                    locked.setdefault(pep503(name), version[2:])
    return locked


def site_packages(repo: Path, env: dict[str, str]) -> list[Path]:
    roots = [repo / ".venv", repo / "venv"]
    if env.get("VIRTUAL_ENV"):
        roots.append(Path(env["VIRTUAL_ENV"]))
    out: list[Path] = []
    for root in roots:
        out += sorted(root.glob("lib/python3*/site-packages")) + sorted(root.glob("Lib/site-packages"))
    return [p for p in out if p.is_dir()]


def _installed(sites: list[Path], key: str) -> tuple[Path, Path] | None:
    """(site-packages, dist-info) of the first environment holding the package."""
    for site in sites:
        for dist in sorted(site.glob("*.dist-info")):
            meta = dist / "METADATA"
            if meta.is_file():
                head = meta.read_text(encoding="utf-8", errors="replace").split("\n\n", 1)[0]
                name = next((l.split(":", 1)[1].strip() for l in head.splitlines()
                             if l.lower().startswith("name:")), "")
                if pep503(name) == key:
                    return site, dist
    return None


def _metadata_version(dist: Path) -> str:
    head = (dist / "METADATA").read_text(encoding="utf-8", errors="replace").split("\n\n", 1)[0]
    return next((l.split(":", 1)[1].strip() for l in head.splitlines()
                 if l.lower().startswith("version:")), "")


def discover_pypi(repo: Path, env: dict[str, str]) -> tuple[list[dict], list[str]]:
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version

    declared = pypi_declared(repo)
    if not declared:
        return [], []
    locked, sites = pypi_locked(repo), site_packages(repo, env)
    packages: list[dict] = []
    for key, (spec, where) in sorted(declared.items()):
        p = {"id": f"pypi:{key}", "ecosystem": "pypi", "name": key, "declared": spec,
             "declared_in": where, "version": None, "basis": None, "status": "unavailable",
             "reason": None, "source": None, "snapshot": None}
        packages.append(p)
        found = _installed(sites, key)
        if found is None:
            p["reason"] = "no installed copy in .venv, venv or $VIRTUAL_ENV"
            continue
        site, dist = found
        installed = _metadata_version(dist)
        p["version"] = installed
        direct = c.load_json(dist / "direct_url.json", None)
        if isinstance(direct, dict) and (direct.get("dir_info") or {}).get("editable"):
            p["reason"] = "editable install, not a released version"
            continue
        if key in locked:
            p["basis"] = "locked"
            if locked[key] != installed:
                p["reason"] = f"installed {installed}, the lock says {locked[key]}"
                continue
        elif spec.startswith("==") and "," not in spec and "*" not in spec:
            p["basis"] = "pinned"
            if spec[2:] != installed:
                p["reason"] = f"installed {installed}, pinned at {spec[2:]}"
                continue
        else:
            p["basis"] = "declared_range"
            try:
                ok = Version(installed) in SpecifierSet(spec, prereleases=True)
            except (InvalidSpecifier, InvalidVersion):
                p["reason"] = f'declared range "{spec}" could not be checked'
                continue
            if not ok:
                p["reason"] = f'installed {installed} does not satisfy the declared "{spec}"'
                continue
        files = []
        for line in (dist / "RECORD").read_text(encoding="utf-8", errors="replace").splitlines():
            rel = line.split(",", 1)[0]
            if rel.endswith((".py", ".pyi")) and not rel.startswith("..") and ".dist-info/" not in rel:
                files.append(rel)
        p.update(status="available", source=str(site), files=sorted(files))
    return packages, []


NPM_SUFFIXES = (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts")
_SEMVER = re.compile(r"^v?(\d+)(?:\.(\d+|x|\*))?(?:\.(\d+|x|\*))?(?:-[0-9A-Za-z.-]+)?\Z")


def _ver(v: str) -> tuple[int, int, int] | None:
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", v.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _bounds(token: str) -> list[tuple[str, tuple[int, int, int]]] | None:
    """One comparator set token as (op, version) pairs; None when unsupported."""
    t = token.strip()
    if t in ("*", "x", ""):
        return []
    op = re.match(r"^(>=|<=|>|<|=|\^|~)?", t)[0]
    m = _SEMVER.match(t[len(op):])
    if not m:
        return None
    major = int(m[1])
    minor = None if m[2] in (None, "x", "*") else int(m[2])
    patch = None if m[3] in (None, "x", "*") else int(m[3])
    lo = (major, minor or 0, patch or 0)
    if op in (">=", ">", "<=", "<"):
        return [(op, lo)]
    if op == "^":
        hi = (major + 1, 0, 0) if major else ((0, (minor or 0) + 1, 0) if minor else (0, 0, (patch or 0) + 1))
        return [(">=", lo), ("<", hi)]
    if op == "~" or minor is None or patch is None:
        hi = (major + 1, 0, 0) if minor is None else (major, minor + 1, 0)
        return [(">=", lo), ("<", hi)]
    return [("=", lo)]


def npm_satisfies(version: str, rng: str) -> bool | None:
    v = _ver(version)
    if v is None or " - " in rng or ":" in rng or "/" in rng:
        return None
    for alt in rng.split("||"):
        pairs: list[tuple[str, tuple[int, int, int]]] = []
        for token in alt.split():
            b = _bounds(token)
            if b is None:
                return None
            pairs += b
        cmp = {">=": v.__ge__, ">": v.__gt__, "<=": v.__le__, "<": v.__lt__, "=": v.__eq__}
        if all(cmp[op](bound) for op, bound in pairs):
            return True
    return False


def _npm_locked(repo: Path) -> dict[str, str]:
    lock = repo / "package-lock.json"
    if lock.is_file():
        doc = json.loads(lock.read_text(encoding="utf-8"))
        if isinstance(doc.get("packages"), dict):
            return {k[len("node_modules/"):]: str(v.get("version")) for k, v in doc["packages"].items()
                    if k.startswith("node_modules/") and "/node_modules/" not in k and isinstance(v, dict)
                    and v.get("version")}
        return {k: str(v.get("version")) for k, v in (doc.get("dependencies") or {}).items()
                if isinstance(v, dict) and v.get("version")}
    pnpm = repo / "pnpm-lock.yaml"
    if pnpm.is_file():
        import yaml
        doc = yaml.safe_load(pnpm.read_text(encoding="utf-8")) or {}
        root = ((doc.get("importers") or {}).get(".") or doc)
        out: dict[str, str] = {}
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            for name, spec in (root.get(section) or {}).items():
                version = spec.get("version") if isinstance(spec, dict) else spec
                if isinstance(version, str):
                    out[name] = version.split("(", 1)[0]
        return out
    return {}


def discover_npm(repo: Path) -> tuple[list[dict], list[str]]:
    manifest = repo / "package.json"
    if not manifest.is_file():
        return [], []
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    declared: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        for name, rng in (doc.get(section) or {}).items():
            declared.setdefault(name, str(rng))
    locked = _npm_locked(repo)
    packages: list[dict] = []
    for name, rng in sorted(declared.items()):
        p = {"id": f"npm:{name}", "ecosystem": "npm", "name": name, "declared": rng,
             "declared_in": ["package.json"], "version": None, "basis": None, "status": "unavailable",
             "reason": None, "source": None, "snapshot": None}
        packages.append(p)
        d = repo / "node_modules" / name
        meta = c.load_json(d / "package.json", None)
        if not isinstance(meta, dict) or not meta.get("version"):
            p["reason"] = "no installed copy in node_modules"
            continue
        installed = str(meta["version"])
        p["version"] = installed
        if name in locked:
            p["basis"] = "locked"
            if locked[name] != installed:
                p["reason"] = f"installed {installed}, the lock says {locked[name]}"
                continue
        else:
            ok = npm_satisfies(installed, rng)
            p["basis"] = "pinned" if _ver(rng) and rng.strip() == installed else "declared_range"
            if ok is None:
                p["reason"] = f'declared range "{rng}" could not be checked'
                continue
            if not ok:
                p["reason"] = f'installed {installed} does not satisfy the declared "{rng}"'
                continue
        files = sorted(f.relative_to(d).as_posix() for f in d.rglob("*")
                       if f.is_file() and not f.is_symlink() and f.name.endswith(NPM_SUFFIXES)
                       and "node_modules" not in f.relative_to(d).parts)
        p.update(status="available", source=str(d), files=files)
    return packages, []


_GRADLE_COORD = re.compile(r"""["']([A-Za-z0-9_.-]+):([A-Za-z0-9_.-]+):([A-Za-z0-9_.+-]+)["']""")


def _maven_declared(repo: Path) -> dict[str, tuple[str | None, str]]:
    """groupId/artifactId → (version or None, declared_in)."""
    out: dict[str, tuple[str | None, str]] = {}
    pom = repo / "pom.xml"
    if pom.is_file():
        root = ET.fromstring(pom.read_text(encoding="utf-8"))
        ns = {"m": root.tag[1:].split("}")[0]} if root.tag.startswith("{") else {}
        q = (lambda t: f"m:{t}") if ns else (lambda t: t)
        props = {e.tag.split("}")[-1]: (e.text or "").strip()
                 for e in root.findall(f"{q('properties')}/*", ns)}
        for dep in root.findall(f".//{q('dependencies')}/{q('dependency')}", ns):
            g = (dep.findtext(q("groupId"), "", ns) or "").strip()
            a = (dep.findtext(q("artifactId"), "", ns) or "").strip()
            v = (dep.findtext(q("version"), "", ns) or "").strip() or None
            if v and v.startswith("${") and v.endswith("}"):
                v = props.get(v[2:-1])
            if g and a:
                out.setdefault(f"{g}/{a}", (v, "pom.xml"))
    for name in ("build.gradle", "build.gradle.kts"):
        path = repo / name
        if path.is_file():
            for g, a, v in _GRADLE_COORD.findall(path.read_text(encoding="utf-8")):
                out.setdefault(f"{g}/{a}", (v, name))
    catalog = repo / "gradle" / "libs.versions.toml"
    if catalog.is_file():
        doc = tomllib.loads(catalog.read_text(encoding="utf-8"))
        versions = doc.get("versions") or {}
        for lib in (doc.get("libraries") or {}).values():
            if not isinstance(lib, dict) or ":" not in str(lib.get("module", "")):
                continue
            g, a = lib["module"].split(":", 1)
            v = lib.get("version")
            if isinstance(v, dict):
                v = versions.get(v.get("ref")) if v.get("ref") else v.get("strictly") or v.get("require")
            out.setdefault(f"{g}/{a}", (str(v) if v else None, "gradle/libs.versions.toml"))
    return out


def _gradle_locked(repo: Path) -> dict[str, str]:
    lock = repo / "gradle.lockfile"
    out: dict[str, str] = {}
    if lock.is_file():
        for line in lock.read_text(encoding="utf-8").splitlines():
            coord = line.split("=", 1)[0].strip()
            if coord.count(":") == 2 and not coord.startswith("#"):
                g, a, v = coord.split(":")
                out[f"{g}/{a}"] = v
    return out


def _sources_jar(home: Path, group: str, artifact: str, version: str) -> Path | None:
    m2 = home / ".m2" / "repository" / Path(*group.split(".")) / artifact / version / f"{artifact}-{version}-sources.jar"
    if m2.is_file():
        return m2
    cache = home / ".gradle" / "caches" / "modules-2" / "files-2.1" / group / artifact / version
    hits = sorted(cache.glob(f"*/{artifact}-{version}-sources.jar")) if cache.is_dir() else []
    return hits[0] if hits else None


def discover_maven(repo: Path, home: Path) -> tuple[list[dict], list[str]]:
    declared, locked = _maven_declared(repo), _gradle_locked(repo)
    packages: list[dict] = []
    for name, (version, where) in sorted(declared.items()):
        p = {"id": f"maven:{name}", "ecosystem": "maven", "name": name, "declared": version or "",
             "declared_in": [where], "version": None, "basis": None, "status": "unavailable",
             "reason": None, "source": None, "snapshot": None}
        packages.append(p)
        if name in locked:
            p["version"], p["basis"] = locked[name], "locked"
        elif version and not any(ch in version for ch in "[](),+$"):
            p["version"], p["basis"] = version, "pinned"
        else:
            p["reason"] = (f"no version declared in this {where}" if not version
                           else f'declared version "{version}" is a range, which is not resolved')
            continue
        group, artifact = name.split("/", 1)
        jar = _sources_jar(home, group, artifact, p["version"])
        if jar is None:
            p["reason"] = "no sources jar in the local Maven or Gradle cache"
            continue
        p.update(status="available", source=str(jar), jar=str(jar))
    return packages, []


NO_MANIFEST = ("No dependency manifest was found (pyproject.toml, requirements*.txt, package.json, "
               "pom.xml, build.gradle); verification reads the repository only.")


def discover(repo: Path, env: dict[str, str] | None = None, home: Path | None = None) -> dict:
    env = dict(os.environ) if env is None else env
    home = Path.home() if home is None else home
    packages: list[dict] = []
    warnings: list[str] = []
    for found, warns in (discover_pypi(repo, env), discover_npm(repo), discover_maven(repo, home)):
        packages += found
        warnings += warns
    if not packages:
        warnings.append(NO_MANIFEST)
    return {"schema": DEPS_SCHEMA, "packages": sorted(packages, key=lambda p: p["id"]),
            "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="deps.py", description="snapshot declared dependency source")
    ap.add_argument("--repo", default=None)
    args = ap.parse_args(argv)
    try:
        repo = c.find_repo_root(args.repo)
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2
    index = snapshot(repo, discover(repo))
    write_index(repo, index)
    ok = sum(1 for p in index["packages"] if p["status"] == "available")
    print(f"dependency source: {ok} of {len(index['packages'])} declared packages available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
