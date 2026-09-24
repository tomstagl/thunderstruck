#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0", "lizard>=1.17"]
# ///
"""Deterministic signal layer: churn x complexity, coupling, detector hits.

Everything here must be reproducible. No model output reaches this file — the
ranking a rerun produces on an unchanged repo is byte-identical, which is what
makes the checkpointing in the scan skill safe.

    uv run scripts/signals.py --top 10 --since 12m

Writes .thunderstruck/hotspots.json in the target repo.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
from detectors import run_detectors  # noqa: E402

HOTSPOTS_SCHEMA = "thunderstruck.hotspots/v1"

TIER_FACTOR = {"A": 1.0, "B": 0.5, "C": 0.0}
CONFIDENCE_FACTOR = {"high": 1.0, "medium": 0.6, "low": 0.25}
MAX_STABILITY_WEIGHT = 2.0

# A commit touching more than this is a rename, a reformat or a merge. Letting
# it into the coupling matrix couples everything to everything.
COUPLING_MAX_FILES_PER_COMMIT = 50
COUPLING_MIN_SHARED = 5
COUPLING_MIN_RATIO = 0.30

FIX_KEYWORDS = re.compile(
    r"(?i)\b(fix(e[ds])?|bug(fix)?|hotfix|revert(ed|s)?|regress\w*|patch|"
    r"timeout|hang(ing|s)?|deadlock|stall\w*|429|rate.?limit\w*|throttl\w*|"
    r"retry|retries|backoff|duplicate[sd]?|dupe|race|flake|flaky|oom|"
    r"leak|crash(e[ds])?|outage|incident)\b")
REFACTOR_KEYWORDS = re.compile(
    r"(?i)\b(refactor\w*|cleanup|clean.?up|rename[ds]?|tidy|reformat|lint|style|"
    r"move[ds]?|extract\w*|simplif\w*|dedup\w*)\b")

_RECORD_SEP = "\x1e"


# --------------------------------------------------------------------------
# window parsing
# --------------------------------------------------------------------------


def parse_since(spec: str) -> tuple[str, str]:
    """'12m' / '90d' / '2y' / '2025-01-01' -> (git --since arg, iso date)."""
    spec = (spec or "12m").strip()
    m = re.fullmatch(r"(\d+)\s*([dwmy])", spec, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days = {"d": 1, "w": 7, "m": 30, "y": 365}[unit] * n
        date = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        return date, date
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", spec):
        return spec, spec
    raise c.ThunderstruckError(
        f"--since {spec!r} not understood. Use 12m, 90d, 2y or an ISO date.")


# --------------------------------------------------------------------------
# churn
# --------------------------------------------------------------------------


def collect_history(repo: Path, since: str, filters: c.Filters) -> dict[str, Any]:
    """One `git log --numstat` pass feeds churn, fix-ratio and coupling."""
    fmt = f"{_RECORD_SEP}%H%x00%an%x00%aI%x00%s"
    raw = c.git(repo, "log", f"--since={since}", "--numstat", "--no-merges",
                f"--pretty=format:{fmt}", "--", ".")

    per_file: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"commits": 0, "insertions": 0, "deletions": 0,
                 "authors": set(), "fix_commits": 0, "refactor_commits": 0,
                 "last_modified": None, "shas": []})
    commit_files: list[list[str]] = []
    total_commits = 0
    skipped_bot = 0

    for record in raw.split(_RECORD_SEP):
        record = record.strip("\n")
        if not record:
            continue
        header, _, body = record.partition("\n")
        parts = header.split("\x00")
        if len(parts) < 4:
            continue
        sha, author, when, subject = parts[0], parts[1], parts[2], parts[3]
        if filters.excludes_author(author):
            skipped_bot += 1
            continue
        total_commits += 1
        is_fix = bool(FIX_KEYWORDS.search(subject))
        is_refactor = bool(REFACTOR_KEYWORDS.search(subject))

        touched: list[str] = []
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            adds, dels, path = cols
            path = _unrename(path)
            if filters.excludes_path(path):
                continue
            touched.append(path)
            entry = per_file[path]
            entry["commits"] += 1
            entry["insertions"] += int(adds) if adds.isdigit() else 0
            entry["deletions"] += int(dels) if dels.isdigit() else 0
            entry["authors"].add(author)
            entry["fix_commits"] += int(is_fix)
            entry["refactor_commits"] += int(is_refactor)
            if entry["last_modified"] is None:
                entry["last_modified"] = when  # log is newest-first
            if len(entry["shas"]) < 30:
                entry["shas"].append(sha)

        if 1 < len(touched) <= COUPLING_MAX_FILES_PER_COMMIT:
            commit_files.append(touched)

    for entry in per_file.values():
        entry["authors"] = len(entry["authors"])
    return {"per_file": dict(per_file), "commit_files": commit_files,
            "total_commits": total_commits, "skipped_bot_commits": skipped_bot}


def _unrename(path: str) -> str:
    """`git log --numstat` renders a rename as `old/{a => b}/file`."""
    if "=>" not in path:
        return path
    m = re.match(r"^(.*)\{(.*) => (.*)\}(.*)$", path)
    if m:
        return re.sub(r"//+", "/", f"{m.group(1)}{m.group(3)}{m.group(4)}")
    return path.split("=>")[-1].strip()


# --------------------------------------------------------------------------
# coupling
# --------------------------------------------------------------------------


def temporal_coupling(commit_files: list[list[str]], keep: set[str]) -> list[dict]:
    shared: Counter[tuple[str, str]] = Counter()
    touching: Counter[str] = Counter()
    for files in commit_files:
        relevant = sorted({f for f in files if f in keep})
        for f in relevant:
            touching[f] += 1
        for i, a in enumerate(relevant):
            for b in relevant[i + 1:]:
                shared[(a, b)] += 1

    out = []
    for (a, b), n in shared.items():
        if n < COUPLING_MIN_SHARED:
            continue
        either = touching[a] + touching[b] - n
        ratio = n / either if either else 0.0
        if ratio >= COUPLING_MIN_RATIO:
            out.append({"files": [a, b], "shared_commits": n,
                        "commits_touching_either": either, "ratio": round(ratio, 3)})
    out.sort(key=lambda d: (-d["ratio"], -d["shared_commits"]))
    return out


# --------------------------------------------------------------------------
# complexity
# --------------------------------------------------------------------------


def analyse_complexity(repo: Path, paths: list[str]) -> tuple[dict[str, dict], str | None]:
    try:
        import lizard  # type: ignore
    except ImportError:
        return {}, ("lizard is not installed, so complexity could not be measured. "
                    "Ranking fell back to churn only — install it with "
                    "`uv run --with lizard` or `pip install lizard` for the full signal.")

    out: dict[str, dict] = {}
    for rel in paths:
        full = repo / rel
        if not full.is_file():
            continue
        try:
            info = lizard.analyze_file(str(full))
        except Exception:  # a parser failure on one file must not sink the scan
            continue
        funcs = list(info.function_list)
        if funcs:
            worst = max(funcs, key=lambda f: f.cyclomatic_complexity)
            top = {"name": worst.name, "ccn": worst.cyclomatic_complexity,
                   "nloc": worst.nloc,
                   "lines": f"{worst.start_line}-{worst.end_line}"}
            ccn_max = max(f.cyclomatic_complexity for f in funcs)
            ccn_avg = sum(f.cyclomatic_complexity for f in funcs) / len(funcs)
        else:
            top, ccn_max, ccn_avg = None, 1, 1.0
        out[rel] = {"nloc": info.nloc, "functions": len(funcs),
                    "ccn_max": ccn_max, "ccn_avg": round(ccn_avg, 2),
                    "top_function": top}
    return out, None


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def stability_weight(hits: list, patterns: dict[str, dict]) -> tuple[float, dict[str, float]]:
    """Weight each *pattern* once per file, at its strongest hit.

    Five S01 hits in one file is one missing timeout habit, not five. Counting
    them separately would rank a long file above a fragile one.
    """
    best: dict[str, float] = {}
    for hit in hits:
        pattern = patterns.get(hit.pattern_id)
        if not pattern:
            continue
        tier = TIER_FACTOR.get(str(pattern.get("tier", "A")).upper(), 0.0)
        if tier <= 0:
            continue
        contribution = (float(pattern.get("weight", 1.0)) * tier
                        * CONFIDENCE_FACTOR.get(hit.confidence, 0.6))
        best[hit.pattern_id] = max(best.get(hit.pattern_id, 0.0), contribution)
    total = min(MAX_STABILITY_WEIGHT, sum(best.values()))
    return total, {k: round(v, 3) for k, v in best.items()}


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def build(args: argparse.Namespace) -> dict[str, Any]:
    repo = c.find_repo_root(args.repo)
    warnings: list[str] = []

    head = c.git(repo, "rev-parse", "HEAD").strip()
    try:
        branch = c.git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except c.ThunderstruckError:
        branch = "(detached)"

    catalog = c.load_catalog()
    profile = c.load_profile(repo)
    patterns = c.effective_patterns(catalog, profile)
    filters = c.Filters.from_profile(profile, path_prefix=args.path,
                                     include_tests=args.include_tests or None)
    langmap = c.language_map(catalog)

    since_arg, since_date = parse_since(args.since)
    history = collect_history(repo, since_arg, filters)
    per_file = history["per_file"]

    if history["total_commits"] == 0:
        raise c.ThunderstruckError(
            f"no commits since {since_date} (after filtering). Widen the window "
            f"with --since, e.g. --since 24m.")
    if history["total_commits"] < 20:
        warnings.append(
            f"only {history['total_commits']} commits since {since_date} — churn "
            f"ranking is weak on this little history. Widen the window with a "
            f"longer --since than {args.since!r}, if the repository has one.")

    tracked = {p for p in c.git(repo, "ls-files").split("\n") if p}
    candidates = [
        p for p in per_file
        if p in tracked and (repo / p).is_file()
        and c.detect_language(p, langmap) is not None
    ]
    if not candidates:
        raise c.ThunderstruckError(
            "no files in a supported language changed in this window. "
            f"Supported: {', '.join(sorted(catalog['languages']))}.")

    complexity, complexity_warning = analyse_complexity(repo, candidates)
    degraded = {"complexity": complexity_warning is not None}
    if complexity_warning:
        warnings.append(complexity_warning)

    # detector pass
    hits_by_file: dict[str, list] = {}
    for rel in candidates:
        text = c.read_text(repo / rel)
        if text is None:
            continue
        lang = c.detect_language(rel, langmap)
        hits_by_file[rel] = run_detectors(catalog, rel, text, lang)

    churn_raw = [float(per_file[p]["commits"]) for p in candidates]
    comp_raw = [float(complexity.get(p, {}).get("ccn_max", 1) or 1) for p in candidates]
    churn_norm = c.normalize(churn_raw)
    comp_norm = ([1.0] * len(candidates) if degraded["complexity"]
                 else c.normalize(comp_raw))

    rows = []
    for i, rel in enumerate(candidates):
        hits = hits_by_file.get(rel, [])
        weight, per_pattern = stability_weight(hits, patterns)
        raw = churn_norm[i] * comp_norm[i]
        score = raw * (1.0 + weight)
        churn = per_file[rel]
        rows.append({
            "file": rel,
            "language": c.detect_language(rel, langmap),
            "content_hash": c.sha256_file(repo / rel),
            "churn": {
                "commits": churn["commits"],
                "insertions": churn["insertions"],
                "deletions": churn["deletions"],
                "authors": churn["authors"],
                "fix_commits": churn["fix_commits"],
                "refactor_commits": churn["refactor_commits"],
                "fix_ratio": round(churn["fix_commits"] / churn["commits"], 3)
                             if churn["commits"] else 0.0,
                "last_modified": churn["last_modified"],
                "recent_shas": churn["shas"][:15],
            },
            "complexity": complexity.get(rel),
            "detector_hits": [h.to_dict() for h in hits],
            "stability": {"weight": round(weight, 3), "per_pattern": per_pattern,
                          "patterns": sorted({h.pattern_id for h in hits})},
            "scores": {"churn_norm": round(churn_norm[i], 4),
                       "complexity_norm": round(comp_norm[i], 4),
                       "raw": round(raw, 4), "score": round(score, 4)},
        })

    rows.sort(key=lambda r: (-r["scores"]["score"], r["file"]))
    top = rows[: args.top] if args.top else rows
    for n, row in enumerate(top, 1):
        row["id"] = f"H{n:02d}"

    keep = {r["file"] for r in top}
    coupling = temporal_coupling(history["commit_files"], set(r["file"] for r in rows))
    by_file: dict[str, list[dict]] = defaultdict(list)
    for entry in coupling:
        a, b = entry["files"]
        by_file[a].append({"file": b, "shared_commits": entry["shared_commits"],
                           "ratio": entry["ratio"]})
        by_file[b].append({"file": a, "shared_commits": entry["shared_commits"],
                           "ratio": entry["ratio"]})
    for row in top:
        row["coupled_files"] = sorted(
            by_file.get(row["file"], []), key=lambda d: -d["ratio"])[:5]

    coverage: dict[str, dict] = {}
    for pid, pattern in patterns.items():
        files = [f for f, hs in hits_by_file.items() if any(h.pattern_id == pid for h in hs)]
        coverage[pid] = {"name": pattern["name"], "tier": pattern["tier"],
                         "files": len(files), "scanned": pattern["tier"] in ("A", "B")}

    return {
        "schema": HOTSPOTS_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": {"root": str(repo), "head": head, "branch": branch},
        "window": {"since": args.since, "since_date": since_date,
                   "commits": history["total_commits"],
                   "skipped_bot_commits": history["skipped_bot_commits"]},
        "config": {"top": args.top, "path": args.path,
                   "include_tests": bool(args.include_tests),
                   "profile": bool(profile), "profile_file": c.PROFILE_FILENAME if profile else None},
        "degraded": degraded,
        "warnings": warnings,
        "counts": {"files_considered": len(candidates), "files_ranked": len(rows),
                   "hotspots": len(top),
                   "detector_hits": sum(len(h) for h in hits_by_file.values())},
        "pattern_coverage": coverage,
        "coupling": coupling[:50],
        "hotspots": top,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="signals.py", description="thunderstruck deterministic signal layer")
    ap.add_argument("--repo", default=None, help="target repo (default: cwd)")
    ap.add_argument("--top", type=int, default=10, help="how many hotspots to keep")
    ap.add_argument("--since", default="12m", help="history window: 12m, 90d, 2y, ISO date")
    ap.add_argument("--path", default=None, help="restrict to a subdirectory")
    ap.add_argument("--include-tests", action="store_true",
                    help="rank test files too (excluded by default)")
    ap.add_argument("--stdout", action="store_true", help="print JSON instead of writing")
    args = ap.parse_args(argv)

    try:
        payload = build(args)
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2

    # stderr only: hotspots.json and everything rendered from it stay free of
    # machine-specific paths.
    checkout = c.source_checkout()
    if checkout:
        print(f"thunderstruck: warning: running from the source checkout "
              f"{checkout}, not an installed release. Its current branch and "
              f"uncommitted edits decide what this scan checks. Install from "
              f"the GitHub marketplace for a fixed version.", file=sys.stderr)

    if args.stdout:
        print(json.dumps(payload, indent=2))
        return 0

    repo = Path(payload["repo"]["root"])
    dest = c.out_dir(repo) / "hotspots.json"
    c.write_json(dest, payload)
    for w in payload["warnings"]:
        print(f"thunderstruck: warning: {w}", file=sys.stderr)
    print(f"{len(payload['hotspots'])} hotspots from "
          f"{payload['counts']['files_considered']} files "
          f"({payload['window']['commits']} commits since "
          f"{payload['window']['since_date']}) -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
