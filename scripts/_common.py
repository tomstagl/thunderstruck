"""Shared helpers for the thunderstruck scripts.

Deliberately small and dependency-light: everything here is importable from a
`uv run` script with only pyyaml available, and the pieces the guardrail hook
needs (paths, hashing) are stdlib-only so the hook can run on bare python3.
"""

from __future__ import annotations

import errno
import functools
import hashlib
import json
import os
import re
import stat
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
# about fragility. Scanning them wastes subagents on noise. Each entry carries
# the reason the report's "Not scanned" section gives for it; an entry a
# profile adds reports "profile".
_EXCLUDE_GLOB_GROUPS: list[tuple[str, list[str]]] = [
    ("asset", ["*.lock", "*.lockb", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
               "poetry.lock", "uv.lock", "Cargo.lock", "composer.lock", "Gemfile.lock",
               "*.map", "*.snap",
               "*.svg", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.pdf",
               "*.woff", "*.woff2", "*.ttf", "*.eot"]),
    ("build", ["*.min.js", "*.min.css"]),
    ("generated", ["*.generated.*", "*_pb2.py", "*_pb2_grpc.py", "*.pb.go", "*.g.dart",
                   "*.d.ts", "*.pyi", "openapi*.yaml", "openapi*.yml",
                   "swagger*.yaml", "swagger*.yml"]),
    # CI and tooling configuration fails builds, not production. Named tools
    # only: `database.config.ts` or Angular's `app.config.ts` is runtime
    # configuration, and exactly where timeouts and pool sizes live.
    ("tooling", [f"{tool}.config.*" for tool in (
                    "playwright", "vitest", "vite", "jest", "webpack", "rollup",
                    "next", "nuxt", "tailwind", "postcss", "babel", "eslint",
                    "prettier", "cypress", "karma", "svelte", "astro", "tsup",
                    "esbuild", "commitlint", "lint-staged", "stylelint", "metro",
                    "docusaurus", "vue", "remix", "turbo", "wrangler")]
                + ["karma.conf.*", ".gitlab-ci.yml", "docker-compose*.yml",
                   "docker-compose*.yaml", "mkdocs.yml", ".pre-commit-config.yaml"]),
]
_EXCLUDE_DIR_GROUPS: list[tuple[str, list[str]]] = [
    ("vendored", ["node_modules", "vendor", "third_party", ".venv", "venv"]),
    ("build", ["dist", "build", "out", ".next", ".nuxt", "target", "__pycache__",
               ".mypy_cache", ".pytest_cache", "coverage"]),
    ("generated", ["generated", "__generated__"]),
    ("migration", ["migrations"]),
    ("tooling", [".git", ".thunderstruck", ".github", ".circleci", ".gitlab"]),
]
# Test code churns and branches as much as production code, but its failure
# modes are CI failures, not outages. Ranking it spends investigators on the
# wrong files. Opt back in with --include-tests or filters.include_tests.
DEFAULT_EXCLUDE_TEST_GLOBS = [
    "*.test.*", "*.spec.*", "test_*.py", "*_test.py", "*_test.go",
    "conftest.py", "*.fixture.*", "*.stories.*",
    "tests.py", "*_tests.py", "*.cy.*",
]
DEFAULT_EXCLUDE_TEST_DIRS = [
    "tests", "test", "__tests__", "spec", "specs", "e2e", "fixtures",
    "testdata", "__mocks__", "cypress", "benchmarks", "bench",
]
DEFAULT_EXCLUDE_GLOBS = [g for _, group in _EXCLUDE_GLOB_GROUPS for g in group]
DEFAULT_EXCLUDE_DIRS = [d for _, group in _EXCLUDE_DIR_GROUPS for d in group]
_DEFAULT_REASON = {
    **{("glob", g): r for r, group in _EXCLUDE_GLOB_GROUPS for g in group},
    **{("dir", d): r for r, group in _EXCLUDE_DIR_GROUPS for d in group},
    **{("glob", g): "test" for g in DEFAULT_EXCLUDE_TEST_GLOBS},
    **{("dir", d): "test" for d in DEFAULT_EXCLUDE_TEST_DIRS},
}
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


def source_checkout() -> Path | None:
    """The plugin root when it is a git working tree, else None.

    An installed release has no .git. A local-directory marketplace or
    --plugin-dir runs a checkout in place, so its branch and uncommitted edits
    decide what a scan checks.
    """
    root = plugin_root()
    return root if (root / ".git").exists() else None


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



def git_paths(repo_root: Path, *args: str, check: bool = True, timeout: int = 180) -> str:
    """git output that carries file names, decoded exactly.

    Bytes are decoded as UTF-8 with surrogateescape, so a name that isn't
    valid UTF-8 survives as a string instead of crashing the run.
    """
    proc = subprocess.run(["git", "-C", str(repo_root), *args],
                          capture_output=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise ThunderstruckError(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout.decode("utf-8", "surrogateescape")

def commit_touches(repo_root: Path, sha: str, paths: list[str]) -> bool:
    """True when `sha` changed at least one of `paths` (as named today)."""
    if not paths:
        return False
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "--literal-pathspecs", "diff-tree", "--no-commit-id",
         "--name-only", "-r", "--root", sha, "--", *paths],
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
        f.__post_init__()  # recompile with the profile's additions
        return f

    def __post_init__(self) -> None:
        globs = list(self.exclude_globs)
        dirs = list(self.exclude_dirs)
        if not self.include_tests:
            globs += DEFAULT_EXCLUDE_TEST_GLOBS
            dirs += DEFAULT_EXCLUDE_TEST_DIRS
        # First entry wins, so a profile repeating a default keeps its reason.
        self._globs: list[tuple[re.Pattern, str]] = []
        for g in dict.fromkeys(globs):
            self._globs.append((_glob_to_re(g), _DEFAULT_REASON.get(("glob", g), "profile")))
        self._dirs: dict[str, str] = {}
        for d in dirs:
            self._dirs.setdefault(d, _DEFAULT_REASON.get(("dir", d), "profile"))
        self._authors = [a.lower() for a in self.exclude_authors]

    def exclusion_reason(self, rel_path: str) -> str | None:
        """Why a path is not scanned, or None if it is.

        One of test, generated, vendored, build, migration, asset, tooling,
        profile or path. `excludes_path` is defined by this, so the ranking
        and the report's "Not scanned" counts can never disagree.
        """
        for part in Path(rel_path).parts:
            if part in self._dirs:
                return self._dirs[part]
        name = Path(rel_path).name
        for rx, reason in self._globs:
            if rx.match(name):
                return reason
        if self.path_prefix:
            prefix = self.path_prefix.strip("/")
            if prefix and not (rel_path == prefix or rel_path.startswith(prefix + "/")):
                return "path"
        return None

    def excludes_path(self, rel_path: str) -> bool:
        return self.exclusion_reason(rel_path) is not None

    def excludes_author(self, author: str) -> bool:
        a = (author or "").lower()
        return any(bot in a for bot in self._authors)


# --------------------------------------------------------------------------
# commit classification
# --------------------------------------------------------------------------

# Intent, not vocabulary. "Add retry with backoff" is resilience work, and
# counting it as a fix makes hardening a file look like fragility.
_CC_PREFIX = re.compile(r"^\s*([A-Za-z]+)(?:\([^)]*\))?!?:")
_CC_KIND = {
    **dict.fromkeys(("fix", "hotfix", "bugfix", "revert"), "fix"),
    **dict.fromkeys(("refactor", "style", "chore", "build", "ci", "deps"), "refactor"),
    **dict.fromkeys(("feat", "feature", "perf", "docs", "doc", "test", "tests"), "feature"),
}
_REVERT = re.compile(r'^\s*Revert\s+"')
FIX_INTENT = re.compile(
    r"(?i)\b(fix(e[ds]|ing)?|bug(s|fix)?|hotfix|revert(ed|s)?|regress\w*|"
    r"crash(e[ds])?|outage|incident|deadlock\w*|hang(ing|s)?|stall\w*|"
    r"leak(s|ed|ing)?|oom|broken|repair\w*)\b")
RESILIENCE_KEYWORDS = re.compile(
    r"(?i)\b(retry|retries|retrying|backoff|jitter|timeouts?|429|rate.?limit\w*|"
    r"throttl\w*|circuit.?breaker\w*|idempoten\w*|dedupe?\w*)\b")
REFACTOR_KEYWORDS = re.compile(
    r"(?i)\b(refactor\w*|cleanup|clean.?up|rename[ds]?|tidy|reformat|lint|style|"
    r"move[ds]?|extract\w*|simplif\w*)\b")
COMMIT_KINDS = ("fix", "resilience", "refactor", "feature")


@functools.lru_cache(maxsize=32)
def _extra_fix_re(words: tuple[str, ...]) -> re.Pattern | None:
    words = tuple(w.strip() for w in words if isinstance(w, str) and w.strip())
    if not words:
        return None
    return re.compile(r"(?i)(?<!\w)(?:" + "|".join(map(re.escape, words)) + r")(?!\w)")


def profile_fix_keywords(profile: dict[str, Any]) -> tuple[str, ...]:
    """`[history] fix_keywords` from the profile: extra fix words for teams
    that don't write commit subjects in English."""
    history = profile.get("history") if isinstance(profile, dict) else None
    words = history.get("fix_keywords") if isinstance(history, dict) else None
    if not isinstance(words, list):
        return ()
    return tuple(w for w in words if isinstance(w, str) and w.strip())


def classify_commit(subject: str, extra_fix: tuple[str, ...] = ()) -> str:
    """fix, resilience, refactor or feature (spec §4 of the #19 design).

    A Conventional Commits prefix wins. Otherwise fix intent beats resilience
    vocabulary, which beats refactor vocabulary; anything else is a feature.
    """
    subject = subject or ""
    m = _CC_PREFIX.match(subject)
    if m and m.group(1).lower() in _CC_KIND:
        return _CC_KIND[m.group(1).lower()]
    extra = _extra_fix_re(tuple(extra_fix))
    if _REVERT.match(subject) or FIX_INTENT.search(subject) or (extra and extra.search(subject)):
        return "fix"
    if RESILIENCE_KEYWORDS.search(subject):
        return "resilience"
    if REFACTOR_KEYWORDS.search(subject):
        return "refactor"
    return "feature"


def path_glob_to_re(glob: str) -> re.Pattern:
    """A repo-relative path glob: `*` and `?` stay inside one directory,
    `**` crosses directories (`src/**/batch/*.java` matches `src/batch/X.java`
    and `src/a/b/batch/X.java`)."""
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


@dataclass(frozen=True)
class Suppression:
    """A profile `[[suppress]]` rule. It silences a detector (or every
    detector of a pattern) on matching paths, and always carries a reason,
    which the report prints. There are no inline suppression comments: a
    marker in the code would be the repository steering its own audit."""
    detector: str
    path: str
    reason: str
    path_re: re.Pattern

    def matches(self, detector_id: str, pattern_id: str, file: str) -> bool:
        return self.detector in (detector_id, pattern_id) and bool(self.path_re.match(file))


def load_suppressions(profile: dict[str, Any]) -> tuple[list[Suppression], list[str]]:
    """The profile's `[[suppress]]` rules, plus a warning for each one that is
    ignored. A malformed rule never aborts the run."""
    raw = profile.get("suppress") if isinstance(profile, dict) else None
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [f"{PROFILE_FILENAME}: `suppress` must be an array of tables "
                    f"([[suppress]]); ignored."]
    rules: list[Suppression] = []
    warnings: list[str] = []
    for n, entry in enumerate(raw, 1):
        where = f"{PROFILE_FILENAME}: [[suppress]] rule {n}"
        if not isinstance(entry, dict):
            warnings.append(f"{where} is not a table; ignored.")
            continue
        detector, path, reason = (entry.get(k) for k in ("detector", "path", "reason"))
        if not isinstance(detector, str) or not detector.strip():
            warnings.append(f"{where} has no detector; ignored.")
        elif not isinstance(path, str) or not path.strip():
            warnings.append(f"{where} ({detector}) has no path; ignored.")
        elif not isinstance(reason, str) or not reason.strip():
            warnings.append(f"{where} ({detector} on {path}) has no reason; ignored. "
                            f"A suppression must say why.")
        else:
            rules.append(Suppression(detector.strip(), path.strip(), reason.strip(),
                                     path_glob_to_re(path.strip())))
    return rules, warnings


# --------------------------------------------------------------------------
# text handling
# --------------------------------------------------------------------------


# Bumped whenever validate.py's rules tighten. A findings file carries the
# version that validated it; older ones are re-checked before they are reused
# (bundle.py) and never reported unchecked (report.py).
VALIDATION_RULES = 2


def ref_path(path: Any) -> str:
    """A cited path in canonical form: leading `./` segments removed, nothing else.

    Shared so that the validator, the report and its links agree on one path.
    `.github/x.yml` stays itself; `../x` and `/x` stay as written, so that
    path_problem rejects them instead of this function rewriting them.
    """
    rel = str(path)
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


_DRIVE = re.compile(r"^[A-Za-z]:[/\\]")   # C:/ or C:\ — a POSIX name like a:b.ts is fine


def path_problem(rel: str) -> str | None:
    """Why a canonical cited path can't name a file in the repository, or None."""
    if not rel:
        return "is empty"
    if rel.startswith("/") or _DRIVE.match(rel):
        return "is absolute"
    if "\\" in rel:
        return "contains a backslash"
    parts = rel.split("/")
    if ".." in parts:
        return "climbs out of the repository with '..'"
    if "" in parts or "." in parts:
        return "is not in canonical form (empty or '.' segment, or a trailing '/')"
    return None


def tracked_index(repo_root: Path) -> dict[str, str]:
    """{path: mode} for every entry in the git index.

    Read as bytes and decoded leniently: a file name that isn't valid in the
    locale's encoding must not crash validation.
    """
    proc = subprocess.run(["git", "-C", str(repo_root), "ls-files", "-s", "-z"],
                          capture_output=True, timeout=180)
    if proc.returncode != 0:
        raise ThunderstruckError(
            f"git ls-files failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    index: dict[str, str] = {}
    for entry in proc.stdout.decode("utf-8", "surrogateescape").split("\0"):
        meta, _, path = entry.partition("\t")
        if path:
            index.setdefault(path, meta.split(" ", 1)[0])   # unmerged: first stage wins
    return index




def is_utf8(text: str) -> bool:
    """False for a string holding bytes that weren't UTF-8 (surrogate-escaped
    by git_paths). No output file can be written with it, and no finding can
    spell such a file name."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True

def _resolves_to_itself(repo_root: Path, rel: str) -> bool:
    try:
        return (repo_root / rel).resolve() == repo_root.resolve() / rel
    except (OSError, RuntimeError):  # a symlink loop raises on Python 3.11
        return False


def tracked_file_problem(repo_root: Path, rel: str, mode: str) -> str | None:
    """Why the index entry `rel` (with its git mode) isn't a regular file in
    the working tree, or None. Opens nothing: lstat and readlink only.

    The one rule for "a file": the validator applies it to every cited path
    and the ranking to every candidate, so a hotspot is always citable.
    """
    if mode == "120000":
        return "is a symbolic link; cite the file it points to"
    if mode == "160000":
        return "is a submodule, not a file"
    if not _resolves_to_itself(repo_root, rel):
        # a tracked path replaced locally by a link, even to a file inside
        # the repository such as an ignored .env, is not what git tracks
        return "passes through a symbolic link in the working tree"
    try:
        st = os.lstat(repo_root / rel)
    except OSError as exc:
        if exc.errno == errno.ELOOP:   # Python 3.13+ resolves loops without raising
            return "passes through a symbolic link in the working tree"
        return ("is tracked but missing from the working tree (deleted locally, "
                "or outside a sparse checkout)")
    if not stat.S_ISREG(st.st_mode):
        return "is not a regular file in the working tree"
    return None

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


# A triple quote that opens a line continues an expression, and is a string
# rather than a docstring, when the previous code line leaves one open.
_PY_CONTINUES = re.compile(r"(?:[=,\\+\-*/%|&^<>~@]|\b(?:and|or|not|in|is))\s*$")


def _py_code(segment: str, depth: int) -> tuple[str, int, str | None]:
    """Strip a `#` comment from one line of code, keeping string literals.

    Returns the processed text, the bracket depth after it, and the triple
    quote left open at its end (None if every string closed on this line).
    """
    result: list[str] = []
    i, n, quote = 0, len(segment), None
    while i < n:
        ch = segment[i]
        if quote:
            if ch == "\\":
                result.append(segment[i:i + 2])
                i += 2
                continue
            if segment.startswith(quote, i):
                result.append(quote)
                i += len(quote)
                quote = None
                continue
            result.append(ch)
            i += 1
        elif ch in "\"'":
            triple = segment[i:i + 3]
            quote = triple if triple in ('"""', "'''") else ch
            result.append(quote)
            i += len(quote)
        elif ch == "#":
            result.append(_blank(segment[i:]))
            break
        else:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            result.append(ch)
            i += 1
    # A single-quoted string can't span lines; only a triple quote stays open.
    open_triple = quote if quote in ('"""', "'''") else None
    return "".join(result), depth, open_triple


def _strip_python(text: str) -> str:
    """Blank comments and docstrings; keep every other string verbatim.

    A triple quote that opens a line is a docstring unless it continues an
    expression: an open bracket, or a previous code line ending in `=`, `,`,
    a backslash or an operator. So SQL passed on its own lines to
    `cur.execute(` stays visible to detectors, while a docstring after a
    multi-line signature or after `x = 1` is still blanked.
    """
    out: list[str] = []
    in_string: str | None = None  # open triple quote
    in_doc = False                # ...and whether it is a docstring
    depth = 0
    prev_code = ""
    for line in text.split("\n"):
        if in_string is not None:
            end = line.find(in_string)
            if end == -1:
                out.append(_blank(line) if in_doc else line)
                continue
            head = line[: end + 3]
            in_string = None
            code, depth, in_string = _py_code(line[end + 3:], depth)
            out.append((_blank(head) if in_doc else head) + code)
            in_doc = False
            if code.strip():
                prev_code = code
            continue

        m = _PY_DOCSTRING_START.match(line)
        if m and not (depth > 0 or _PY_CONTINUES.search(prev_code.rstrip())):
            quote = m.group(1)
            rest = line[m.end():]
            if quote in rest:  # single-line docstring
                cut = m.end() + rest.find(quote) + 3
                code, depth, in_string = _py_code(line[cut:], depth)
                out.append(_blank(line[:cut]) + code)
            else:
                out.append(_blank(line))
                in_string, in_doc = quote, True
            prev_code = '"""'  # a docstring is a complete statement
            continue

        code, depth, in_string = _py_code(line, depth)
        in_doc = False
        out.append(code)
        if code.strip():
            prev_code = code
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
