"""Shared helpers for the thunderstruck scripts.

Deliberately small and dependency-light: everything here is importable from a
`uv run` script with only pyyaml available, and the pieces the guardrail hook
needs (paths, hashing) are stdlib-only so the hook can run on bare python3.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

from context_extract import ATTRIBUTE_VALUE, DIRECTIONS, ENTITY_REF, LABEL, RELATION_TYPE

OUTPUT_DIRNAME = ".thunderstruck"
PROFILE_FILENAME = ".thunderstruck.toml"
REPORT_SCHEMA_VERSION = "thunderstruck.report/v1"
FINDING_SCHEMA_VERSION = "thunderstruck.finding/v1"
CONTEXT_SCHEMA = "thunderstruck.context/v1"
CONTEXT_FILENAME = "context.json"
CONTEXT_USABLE = ("fresh", "cached", "stale")
MAX_NEIGHBOURS_PER_DIRECTION = 25

# Files that are churn-heavy or complexity-heavy for reasons that say nothing
# about fragility. Scanning them wastes subagents on noise.
DEFAULT_EXCLUDE_GLOBS = [
    "*.lock", "*.lockb", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "uv.lock", "Cargo.lock", "composer.lock", "Gemfile.lock",
    "*.min.js", "*.min.css", "*.map", "*.snap",
    "*.generated.*", "*_pb2.py", "*_pb2_grpc.py", "*.pb.go", "*.g.dart",
    "*.svg", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.pdf",
    "*.woff", "*.woff2", "*.ttf", "*.eot",
]
# Test code churns and branches as much as production code, but its failure
# modes are CI failures, not outages. Ranking it spends investigators on the
# wrong files. Opt back in with --include-tests or filters.include_tests.
DEFAULT_EXCLUDE_TEST_GLOBS = [
    "*.test.*", "*.spec.*", "test_*.py", "*_test.py", "*_test.go",
    "conftest.py", "*.fixture.*", "*.stories.*",
]
DEFAULT_EXCLUDE_TEST_DIRS = [
    "tests", "test", "__tests__", "spec", "specs", "e2e", "fixtures",
    "testdata", "__mocks__",
]
DEFAULT_EXCLUDE_DIRS = [
    "node_modules", "vendor", "third_party", "dist", "build", "out",
    ".next", ".nuxt", "target", "__pycache__", ".venv", "venv",
    ".git", ".mypy_cache", ".pytest_cache", "coverage", "migrations",
    ".thunderstruck",
]
DEFAULT_EXCLUDE_AUTHORS = [
    "dependabot", "renovate", "github-actions", "greenkeeper",
    "snyk-bot", "imgbot", "pre-commit-ci",
]

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------


def plugin_root() -> Path:
    """Directory the plugin is installed in.

    ${CLAUDE_PLUGIN_ROOT} when Claude Code set it, otherwise the parent of
    scripts/ so the pipeline also runs straight from a checkout.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent


def out_dir(repo_root: Path) -> Path:
    return Path(repo_root) / OUTPUT_DIRNAME


def find_repo_root(start: Path | str | None = None) -> Path:
    start = Path(start or os.getcwd()).resolve()
    try:
        top = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
        return Path(top).resolve()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        raise ThunderstruckError(
            f"{start} is not inside a git repository. thunderstruck reads history, "
            f"so it needs one."
        )


class ThunderstruckError(RuntimeError):
    """A condition the user needs to fix. Printed without a traceback."""


# --------------------------------------------------------------------------
# hashing
# --------------------------------------------------------------------------


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def short_hash(text: str, n: int = 12) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:n]


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------


def git(repo_root: Path, *args: str, check: bool = True, timeout: int = 180) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True, text=True, timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise ThunderstruckError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def commit_touches(repo_root: Path, sha: str, paths: list[str]) -> bool:
    """True when `sha` changed at least one of `paths` (as named today)."""
    if not paths:
        return False
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "diff-tree", "--no-commit-id", "--name-only",
         "-r", "--root", sha, "--", *paths],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode == 0 and bool(proc.stdout.strip())


def commit_exists(repo_root: Path, sha: str) -> bool:
    if not re.fullmatch(r"[0-9a-fA-F]{4,40}", sha or ""):
        return False
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode == 0


# --------------------------------------------------------------------------
# catalog + profile
# --------------------------------------------------------------------------


def load_catalog(root: Path | None = None) -> dict[str, Any]:
    import yaml  # deferred: the guardrail hook must not need pyyaml

    path = Path(root or plugin_root()) / "catalog" / "stability.yaml"
    if not path.is_file():
        raise ThunderstruckError(f"catalog not found at {path}")
    with path.open() as fh:
        catalog = yaml.safe_load(fh)
    catalog["_by_id"] = {p["id"]: p for p in catalog.get("patterns", [])}
    catalog["_tier_c_by_id"] = {p["id"]: p for p in catalog.get("tier_c", [])}
    return catalog


def catalog_ids(catalog: dict[str, Any]) -> set[str]:
    """Every ID a finding may legitimately reference."""
    return set(catalog["_by_id"]) | set(catalog["_tier_c_by_id"]) | {"OTHER"}


def load_profile(repo_root: Path) -> dict[str, Any]:
    """Read .thunderstruck.toml from the target repo. Absent is normal."""
    import tomllib

    path = Path(repo_root) / PROFILE_FILENAME
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ThunderstruckError(f"could not read {path}: {exc}")


def _well_formed_edge(edge: Any) -> bool:
    if not isinstance(edge, dict):
        return False
    if not all(isinstance(edge.get(k), str) for k in ("ref", "type", "direction", "neighbour")):
        return False
    if not (RELATION_TYPE.match(edge["type"]) and ENTITY_REF.match(edge["neighbour"])
            and edge["direction"] in DIRECTIONS
            and edge["ref"] == f"{edge['type']} {edge['neighbour']}"):
        return False
    attrs = edge.get("attributes")
    return isinstance(attrs, dict) and all(
        isinstance(k, str) and LABEL.match(k) and isinstance(v, str) and ATTRIBUTE_VALUE.match(v)
        for k, v in attrs.items())


def _well_formed_context(doc: dict[str, Any]) -> bool:
    """True when context.json holds only what the extractor could have produced.

    The same allow-lists as context_extract, because a hand-written or
    tampered file must not smuggle free text past them into a bundle."""
    ref = doc.get("entity_ref")
    if not isinstance(ref, str) or not ENTITY_REF.match(ref) \
            or not isinstance(doc.get("context_hash"), str):
        return False
    edges = doc.get("edges")
    if not isinstance(edges, list) or not all(_well_formed_edge(e) for e in edges):
        return False
    truncated = doc.get("truncated")
    return isinstance(truncated, dict) and all(
        isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in truncated.values())


def load_service_context(repo_root: Path) -> dict[str, Any] | None:
    """context.json when it holds edges a bundle may show, else None."""
    doc = load_json(out_dir(repo_root) / CONTEXT_FILENAME)
    if isinstance(doc, dict) and doc.get("status") in CONTEXT_USABLE and _well_formed_context(doc):
        return doc
    return None


def effective_patterns(catalog: dict[str, Any], profile: dict[str, Any]) -> dict[str, dict]:
    """Catalog patterns with the repo profile's tier/weight overrides applied."""
    overrides = profile.get("patterns", {}) or {}
    result: dict[str, dict] = {}
    for pid, pattern in catalog["_by_id"].items():
        merged = dict(pattern)
        ov = overrides.get(pid)
        if isinstance(ov, dict):
            if "tier" in ov:
                merged["tier"] = str(ov["tier"]).upper()
            if "weight" in ov:
                try:
                    merged["weight"] = float(ov["weight"])
                except (TypeError, ValueError):
                    pass
        elif isinstance(ov, str):
            merged["tier"] = ov.upper()
        result[pid] = merged
    return result


# --------------------------------------------------------------------------
# language + filtering
# --------------------------------------------------------------------------


def language_map(catalog: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for lang, spec in (catalog.get("languages") or {}).items():
        for ext in spec.get("extensions", []):
            mapping[ext.lower()] = lang
    return mapping


def detect_language(path: str | Path, langmap: dict[str, str]) -> str | None:
    return langmap.get(Path(path).suffix.lower())


def detector_language(catalog: dict[str, Any], lang: str) -> str:
    """Resolve a language to the one its detectors are written under."""
    return (catalog.get("aliases") or {}).get(lang, lang)


def _glob_to_re(glob: str) -> re.Pattern:
    out = []
    for ch in glob:
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
    return re.compile("^" + "".join(out) + "$")


@dataclass
class Filters:
    exclude_globs: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_GLOBS))
    exclude_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_DIRS))
    exclude_authors: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_AUTHORS))
    path_prefix: str | None = None
    include_tests: bool = False

    @classmethod
    def from_profile(cls, profile: dict[str, Any], path_prefix: str | None = None,
                     include_tests: bool | None = None) -> "Filters":
        section = (profile.get("filters") or {}) if isinstance(profile, dict) else {}
        if include_tests is None:
            include_tests = bool(section.get("include_tests", False))
        f = cls(path_prefix=path_prefix, include_tests=include_tests)
        for key, attr in (
            ("exclude_globs", "exclude_globs"),
            ("exclude_dirs", "exclude_dirs"),
            ("exclude_authors", "exclude_authors"),
        ):
            extra = section.get(key)
            if isinstance(extra, list):
                # Profiles add to the defaults rather than replacing them: a repo
                # that wants to ignore one more directory should not silently
                # start scanning node_modules.
                getattr(f, attr).extend(str(x) for x in extra)
        return f

    def __post_init__(self) -> None:
        globs = list(self.exclude_globs)
        dirs = list(self.exclude_dirs)
        if not self.include_tests:
            globs += DEFAULT_EXCLUDE_TEST_GLOBS
            dirs += DEFAULT_EXCLUDE_TEST_DIRS
        self._glob_res = [_glob_to_re(g) for g in globs]
        self._dirs = set(dirs)
        self._authors = [a.lower() for a in self.exclude_authors]

    def excludes_path(self, rel_path: str) -> bool:
        parts = Path(rel_path).parts
        if any(p in self._dirs for p in parts):
            return True
        name = Path(rel_path).name
        if any(r.match(name) for r in self._glob_res):
            return True
        if self.path_prefix:
            prefix = self.path_prefix.strip("/")
            if prefix and not (rel_path == prefix or rel_path.startswith(prefix + "/")):
                return True
        return False

    def excludes_author(self, author: str) -> bool:
        a = (author or "").lower()
        return any(bot in a for bot in self._authors)


# --------------------------------------------------------------------------
# text handling
# --------------------------------------------------------------------------


def read_text(path: Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return None


def estimate_tokens(text: str) -> int:
    """Cheap token estimate. Four characters per token is close enough for a
    budget whose only job is to stop a bundle running away."""
    return max(1, len(text) // 4)


def strip_comments(text: str, lang: str) -> str:
    """Blank out comments, preserving line and column structure.

    String *contents* are kept: header names and SQL live in strings, and the
    detectors need to see them. Python docstrings are treated as comments,
    because a docstring describing a behaviour is not that behaviour — the
    whole point of an absence detector is to notice when a file talks about
    Retry-After without ever reading it.
    """
    if lang == "python":
        return _strip_python(text)
    return _strip_cstyle(text)


def _blank(segment: str) -> str:
    return "".join("\n" if c == "\n" else " " for c in segment)


def _strip_cstyle(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        two = text[i:i + 2]
        if two == "//":
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(_blank(text[i:j]))
            i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(_blank(text[i:j]))
            i = j
        elif c in "\"'`":
            quote = c
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                if quote != "`" and text[j] == "\n":
                    break  # unterminated single-line string; bail out
                j += 1
            out.append(text[i:j])
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


_PY_DOCSTRING_START = re.compile(r'^[ \t]*[rbuRBU]{0,2}("""|\'\'\')')


def _strip_python(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    in_doc: str | None = None
    for line in lines:
        if in_doc is not None:
            end = line.find(in_doc)
            if end == -1:
                out.append(_blank(line))
            else:
                out.append(_blank(line[: end + 3]) + line[end + 3:])
                in_doc = None
            continue

        m = _PY_DOCSTRING_START.match(line)
        if m:
            quote = m.group(1)
            rest = line[m.end():]
            if quote in rest:  # single-line docstring
                cut = m.end() + rest.find(quote) + 3
                out.append(_blank(line[:cut]) + line[cut:])
            else:
                out.append(_blank(line))
                in_doc = quote
            continue

        # Strip a trailing # comment, but not a # inside a string literal.
        result, i, n_l, quote = [], 0, len(line), None
        while i < n_l:
            ch = line[i]
            if quote:
                result.append(ch)
                if ch == "\\":
                    if i + 1 < n_l:
                        result.append(line[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
                result.append(ch)
            elif ch == "#":
                result.append(_blank(line[i:]))
                i = n_l
                break
            else:
                result.append(ch)
            i += 1
        out.append("".join(result))
    return "\n".join(out)


# --------------------------------------------------------------------------
# misc
# --------------------------------------------------------------------------


def write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # ValueError covers json.JSONDecodeError and UnicodeDecodeError alike.
        return default


def die(message: str, code: int = 2) -> None:
    print(f"thunderstruck: {message}", file=sys.stderr)
    raise SystemExit(code)


NORMALIZE_FLOOR = 0.05


def normalize(values: list[float], floor: float = NORMALIZE_FLOOR) -> list[float]:
    """Min-max normalise into [floor, 1].

    The floor matters because the score is a product. Plain min-max puts the
    least-churned file at exactly 0, which annihilates its complexity and its
    missing patterns too — so a complex file with three Tier A gaps would tie
    with an empty one at 0.0 purely for being the least-changed thing in the
    window. The floor keeps ordering intact while letting the other axis and
    the stability weight still separate the tail.

    All-equal input maps to 1.0 across the board, so a repo where every file
    has identical churn ranks on its other axis rather than collapsing.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0] * len(values)
    return [floor + (1.0 - floor) * ((v - lo) / (hi - lo)) for v in values]
