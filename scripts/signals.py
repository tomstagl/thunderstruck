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


def collect_history(repo: Path, since: str, filters: c.Filters,
                    extra_fix: tuple[str, ...] = ()) -> dict[str, Any]:
    """One `git log --numstat` pass feeds churn, fix-ratio and coupling.

    Read with -z, so file names arrive exactly as git stores them: never
    C-quoted, and a rename is its old and new name rather than `a => b`.
    """
    fmt = f"{_RECORD_SEP}%H%x00%an%x00%aI%x00%s"
    raw = c.git_paths(repo, "log", f"--since={since}", "--numstat", "-z", "--no-merges",
                      f"--pretty=format:{fmt}", "--", ".")

    per_file: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"commits": 0, "insertions": 0, "deletions": 0,
                 "authors": set(), "fix_commits": 0, "resilience_commits": 0,
                 "refactor_commits": 0,
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
        kind = c.classify_commit(subject, extra_fix)

        touched: list[str] = []
        tokens = iter(body.split("\0"))
        for token in tokens:
            cols = token.split("\t", 2)          # a name may itself contain a tab
            if len(cols) != 3:
                continue
            adds, dels, path = cols
            if not path:                         # rename or copy: old, then new
                next(tokens, None)
                path = next(tokens, "")
            if not path or filters.excludes_path(path):
                continue
            touched.append(path)
            entry = per_file[path]
            entry["commits"] += 1
            entry["insertions"] += int(adds) if adds.isdigit() else 0
            entry["deletions"] += int(dels) if dels.isdigit() else 0
            entry["authors"].add(author)
            entry["fix_commits"] += int(kind == "fix")
            entry["resilience_commits"] += int(kind == "resilience")
            entry["refactor_commits"] += int(kind == "refactor")
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


# Extensions of programming languages with no detectors, so a run can say by
# name what it could not read (#19 AC-1). Data formats are not listed.
UNSUPPORTED_LANGUAGES = {
    ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala", ".go": "Go", ".rb": "Ruby",
    ".cs": "C#", ".rs": "Rust", ".php": "PHP", ".swift": "Swift", ".groovy": "Groovy",
}
UNSUPPORTED_SHOWN = 8


def compute_coverage_gaps(repo: Path, index: dict[str, str], filters: c.Filters,
                          langmap: dict, considered: set[str]) -> dict[str, Any]:
    """Every tracked file in exactly one bucket, first match wins: excluded
    (by reason), unsupported (by extension), not citable, considered, or
    unchanged in the window. Opens no file. Candidates were already checked
    for citability; every other supported file gets the same check (lstat and
    a symlink-free resolve), so `not_citable` covers unchanged files too.

    The result carries `_by_extension`, the unfolded unsupported counts, for
    the caller to pop.
    """
    excluded: dict[str, int] = defaultdict(int)
    unsupported: dict[str, int] = defaultdict(int)
    not_citable = n_considered = 0
    unchanged: list[str] = []
    for rel, mode in index.items():
        reason = filters.exclusion_reason(rel)
        if reason is not None:
            excluded[reason] += 1
        elif c.detect_language(rel, langmap) is None:
            unsupported[Path(rel).suffix.lower() or "(no extension)"] += 1
        elif rel in considered:
            n_considered += 1
        elif (not c.is_utf8(rel) or c.path_problem(rel)
              or c.tracked_file_problem(repo, rel, mode)):
            not_citable += 1
        else:
            unchanged.append(rel)
    ranked = sorted(unsupported.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = dict(sorted(ranked[:UNSUPPORTED_SHOWN]))
    rest = sum(n for _, n in ranked[UNSUPPORTED_SHOWN:])
    if rest:
        shown["other"] = rest
    return {"tracked": len(index), "considered": n_considered, "unchanged": len(unchanged),
            "not_citable": not_citable, "excluded": dict(sorted(excluded.items())),
            "unsupported": shown, "_by_extension": dict(unsupported),
            "_unchanged": sorted(unchanged)}


def unsupported_language_warnings(by_extension: dict[str, int]) -> list[str]:
    return [f"{n} {UNSUPPORTED_LANGUAGES[ext]} files ({ext}) were not scanned — no "
            f"detectors exist for this language."
            for ext, n in sorted(by_extension.items()) if ext in UNSUPPORTED_LANGUAGES]


def detector_flags(catalog: dict) -> tuple[set[str], set[str]]:
    """(detectors that never add weight, detectors that mark a retry layer)."""
    unscored, inventory = set(), set()
    for pattern in catalog.get("patterns", []):
        for dets in (pattern.get("detectors") or {}).values():
            for det in dets or []:
                if det.get("score") is False:
                    unscored.add(det["id"])
                if det.get("inventory") == "retry_layer":
                    inventory.add(det["id"])
    return unscored, inventory


def build_retry_layers(hits: list, catalog: dict, langmap: dict,
                       unscored: set[str]) -> list[dict]:
    """One entry per retry layer per file, repo-wide (#19 AC-16). Retry
    amplification is R^N over layers that live in different files: code, the
    mesh, and library defaults nobody configured."""
    layers: dict[tuple[str, str], dict] = {}
    for h in hits:
        if h.detector_id in unscored:
            kind = "library-default"
        elif c.rank_only_with_leads(catalog, c.detect_language(h.file, langmap)):
            kind = "config"
        else:
            kind = "code"
        key = (kind, h.file)
        if key not in layers or h.line < layers[key]["line"]:
            layers[key] = {"kind": kind, "file": h.file, "line": h.line,
                           "detector_id": h.detector_id, "pattern_id": h.pattern_id,
                           "note": h.note}
    return sorted(layers.values(), key=lambda r: (r["kind"], r["file"], r["line"]))


def _qualifies(hits: list, unscored: set[str] | frozenset = frozenset()) -> bool:
    """A dormant file needs one medium/high lead, or low leads from two patterns.
    A library default on its own (score: false) is inventory, not a lead."""
    hits = [h for h in hits if h.detector_id not in unscored]
    if any(h.confidence in ("medium", "high") for h in hits):
        return True
    return len({h.pattern_id for h in hits}) >= 2


def dormant_sweep(repo: Path, unchanged: list[str], catalog: dict, patterns: dict,
                  langmap: dict, suppressions: list, suppressed_hits: list[int],
                  keep: int, limit: int, unscored: set[str] | frozenset = frozenset(),
                  inventory_ids: set[str] | frozenset = frozenset()
                  ) -> tuple[list[dict], int, list]:
    """Files with no commit in the window that carry integration-point leads
    (#19 AC-7). Only `dormant: true` patterns run. They are listed, never
    ranked. Returns the rows, how many files the cap skipped, and the retry
    layers found on the way: an untouched mesh file is still a layer."""
    wanted = sorted(pid for pid, p in catalog["_by_id"].items() if p.get("dormant"))
    swept, skipped = unchanged[:max(0, limit)], max(0, len(unchanged) - max(0, limit))
    qualified: list[tuple[float, str, list, dict]] = []
    inventory: list = []
    for rel in swept:
        text = c.read_text(repo / rel)
        if text is None:
            continue
        raw_hits = run_detectors(catalog, rel, text, c.detect_language(rel, langmap),
                                 pattern_ids=wanted)
        inventory += [h for h in raw_hits if h.detector_id in inventory_ids]
        if keep <= 0:
            continue
        hits = apply_suppressions(raw_hits, suppressions, suppressed_hits)
        if hits and _qualifies(hits, unscored):
            weight, per_pattern = stability_weight(hits, patterns, unscored)
            if weight <= 0:
                continue  # every lead is of a pattern the profile tiered out
            qualified.append((weight, rel, hits, per_pattern))
    # application code first: scripts are usually run by hand, not in production
    qualified.sort(key=lambda q: (c.is_script_path(q[1]), -q[0], q[1]))
    last: dict[str, tuple[str, str]] = {}
    for _, rel, _, _ in qualified[:3 * keep]:
        out = c.git(repo, "--literal-pathspecs", "log", "-1", "--format=%H%x00%aI%x00%at",
                    "--", rel, check=False).strip()
        sha, when, epoch = (out.split("\x00") + ["", "", ""])[:3]
        last[rel] = (sha, when, int(epoch) if epoch.isdigit() else 0)
    # chronological: the epoch, not the ISO string, whose offsets vary per commit
    top = sorted(qualified[:3 * keep],
                 key=lambda q: (c.is_script_path(q[1]), -q[0], last[q[1]][2], q[1]))[:keep]
    rows = []
    for n, (weight, rel, hits, per_pattern) in enumerate(top, 1):
        sha, when, _ = last[rel]
        rows.append({
            "id": f"D{n:02d}", "file": rel, "language": c.detect_language(rel, langmap),
            "dormant": True, "script": c.is_script_path(rel), "content_hash": c.sha256_file(repo / rel),
            "churn": {"commits": 0, "insertions": 0, "deletions": 0, "authors": 0,
                      "fix_commits": 0, "resilience_commits": 0, "refactor_commits": 0,
                      "fix_ratio": 0.0, "last_modified": when or None,
                      "recent_shas": [sha] if sha else []},
            "complexity": None,
            "detector_hits": [h.to_dict() for h in hits],
            "stability": {"weight": round(weight, 3), "per_pattern": per_pattern,
                          "patterns": sorted({h.pattern_id for h in hits})},
            "scores": {"churn_norm": 0.0, "complexity_norm": 0.0, "raw": 0.0, "score": 0.0},
            "coupled_files": [],
        })
    return rows, skipped, inventory


def apply_suppressions(hits: list, rules: list[c.Suppression],
                       counts: list[int]) -> list:
    """Drop hits a profile rule suppresses, counting each rule's matches."""
    if not rules:
        return hits
    kept = []
    for h in hits:
        for n, rule in enumerate(rules):
            if rule.matches(h.detector_id, h.pattern_id, h.file):
                counts[n] += 1
                break
        else:
            kept.append(h)
    return kept


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


def stability_weight(hits: list, patterns: dict[str, dict],
                     unscored: set[str] | frozenset = frozenset()) -> tuple[float, dict[str, float]]:
    """Weight each *pattern* once per file, at its strongest hit.

    Five S01 hits in one file is one missing timeout habit, not five. Counting
    them separately would rank a long file above a fragile one. A `score:
    false` detector (a library default, recorded for the retry inventory)
    never adds weight.
    """
    best: dict[str, float] = {}
    for hit in hits:
        if hit.detector_id in unscored:
            continue
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
    history = collect_history(repo, since_arg, filters, c.profile_fix_keywords(profile))
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

    # A candidate is a file a finding can cite: the validator's own rule. A
    # changed entry that fails it (a symlink, a submodule, a name that isn't
    # UTF-8) is counted, never warned about; one no longer tracked is history.
    index = c.tracked_index(repo)
    candidates: list[str] = []
    not_citable = 0
    for p in per_file:
        if c.detect_language(p, langmap) is None:
            continue
        mode = index.get(p)
        if mode is None:
            continue
        if not c.is_utf8(p) or c.path_problem(p) or c.tracked_file_problem(repo, p, mode):
            not_citable += 1
            continue
        candidates.append(p)
    if not candidates:
        raise c.ThunderstruckError(
            "no files in a supported language changed in this window. "
            f"Supported: {', '.join(sorted(catalog['languages']))}.")

    coverage_gaps = compute_coverage_gaps(repo, index, filters, langmap, set(candidates))
    warnings.extend(unsupported_language_warnings(coverage_gaps.pop("_by_extension")))
    unchanged_files = coverage_gaps.pop("_unchanged")

    # lizard has no parser for configuration; config sits at the complexity floor
    complexity, complexity_warning = analyse_complexity(
        repo, [p for p in candidates
               if not c.rank_only_with_leads(catalog, c.detect_language(p, langmap))])
    degraded = {"complexity": complexity_warning is not None}
    if complexity_warning:
        warnings.append(complexity_warning)

    # detector pass. Profile suppressions apply here, before scoring, so a
    # suppressed hit neither ranks a file nor reaches a bundle.
    suppressions, suppress_warnings = c.load_suppressions(profile)
    warnings.extend(suppress_warnings)
    suppressed_hits = [0] * len(suppressions)
    unscored, inventory_ids = detector_flags(catalog)
    hits_by_file: dict[str, list] = {}
    # The retry inventory reads raw hits: a suppressed lead is still a layer.
    inventory_hits: list = []
    for rel in candidates:
        text = c.read_text(repo / rel)
        if text is None:
            continue
        lang = c.detect_language(rel, langmap)
        raw_hits = run_detectors(catalog, rel, text, lang)
        inventory_hits += [h for h in raw_hits if h.detector_id in inventory_ids]
        hits_by_file[rel] = apply_suppressions(raw_hits, suppressions, suppressed_hits)

    # A config file ranks only with a lead, and is dropped before normalising
    # so its deploy churn doesn't compress every other file's score.
    considered = candidates
    candidates = [p for p in candidates
                  if hits_by_file.get(p)
                  or not c.rank_only_with_leads(catalog, c.detect_language(p, langmap))]

    churn_raw = [float(per_file[p]["commits"]) for p in candidates]
    comp_raw = [float(complexity.get(p, {}).get("ccn_max", 1) or 1) for p in candidates]
    churn_norm = c.normalize(churn_raw)
    comp_norm = ([1.0] * len(candidates) if degraded["complexity"]
                 else c.normalize(comp_raw))

    rows = []
    for i, rel in enumerate(candidates):
        hits = hits_by_file.get(rel, [])
        weight, per_pattern = stability_weight(hits, patterns, unscored)
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
                "resilience_commits": churn["resilience_commits"],
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

    dormant, skipped, swept_inventory = dormant_sweep(
        repo, unchanged_files, catalog, patterns, langmap, suppressions, suppressed_hits,
        args.dormant, args.dormant_limit, unscored, inventory_ids)
    retry_layers = build_retry_layers(inventory_hits + swept_inventory, catalog, langmap,
                                      unscored)
    if skipped:
        warnings.append(
            f"{skipped} unchanged file(s) were not swept for dormant integration "
            f"points (--dormant-limit {args.dormant_limit}); raise the limit to "
            f"sweep them.")

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
        "counts": {"files_considered": len(considered), "files_ranked": len(rows),
                   "files_not_citable": not_citable,
                   "hotspots": len(top),
                   "detector_hits": sum(len(h) for h in hits_by_file.values())},
        "pattern_coverage": coverage,
        "coverage_gaps": coverage_gaps,
        "dormant": dormant,
        "retry_layers": retry_layers,
        "suppressed": [{"detector": r.detector, "path": r.path, "reason": r.reason,
                        "hits": n} for r, n in zip(suppressions, suppressed_hits)],
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
    ap.add_argument("--dormant", type=int, default=5,
                    help="how many dormant integration points to list (0: none)")
    ap.add_argument("--dormant-limit", type=int, default=3000,
                    help="most unchanged files to sweep for them")
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
