#!/usr/bin/env python3
"""Hotspot X-ray spike over the Celery scan. Read-only against the repo."""
from __future__ import annotations

import ast
import json
import re
import subprocess
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import lizard

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "scripts"))
from _common import classify_commit  # noqa: E402  (the one definition every stage uses)

REPO = Path(os.environ["CELERY_REPO"])  # a celery checkout at 508c112, scanned
DATA = Path(__file__).resolve().parents[2]  # docs/calibration/correctness/celery
TS = DATA / "scan"
OUT = Path(__file__).resolve().parent
SINCE = "2025-10-03"
SCAN_TS = datetime(2026, 10, 3, 16, 3, 58, tzinfo=timezone.utc).timestamp()
HEAD = "508c1129269d2b1baffc516d8f5c05da06273ef0"
CTX = 3          # context lines around each X-ray function
FULL_HISTORY = "--full" in sys.argv


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True, errors="replace").stdout


# ---------------------------------------------------------------- spans ----
_span_cache: dict[tuple[str, str], list[dict]] = {}


def spans(sha: str, path: str) -> list[dict]:
    """Functions in path@sha: lizard spans + CCN, ast-qualified names."""
    key = (sha, path)
    if key in _span_cache:
        return _span_cache[key]
    code = git("show", f"{sha}:{path}")
    out: list[dict] = []
    if code:
        quals: dict[int, str] = {}
        try:
            tree = ast.parse(code)

            def walk(node, prefix):
                for ch in ast.iter_child_nodes(node):
                    if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        quals[ch.lineno] = prefix + ch.name
                        walk(ch, prefix + ch.name + ".")
                    elif isinstance(ch, ast.ClassDef):
                        walk(ch, prefix + ch.name + ".")
                    else:
                        walk(ch, prefix)
            walk(tree, "")
        except SyntaxError:
            pass
        res = lizard.analyze_file.analyze_source_code(path, code)
        for f in res.function_list:
            out.append({"name": quals.get(f.start_line, f.name), "start": f.start_line,
                        "end": f.end_line, "ccn": f.cyclomatic_complexity, "nloc": f.nloc})
    _span_cache[key] = out
    return out


def fn_at(fs: list[dict], line: int) -> dict | None:
    best = None
    for f in fs:
        if f["start"] <= line <= f["end"] and (best is None or f["end"] - f["start"] < best["end"] - best["start"]):
            best = f          # innermost
    return best


def fn_for(fs: list[dict], lo: int, hi: int) -> dict | None:
    """Innermost function at the first line of [lo,hi] that lies inside one
    (a ref may start on a decorator or class line)."""
    for ln in range(lo, hi + 1):
        f = fn_at(fs, ln)
        if f:
            return f
    return None


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.M)


def hunks(sha: str, path: str) -> list[tuple[int, int, int, int]]:
    """(old_start, old_n, new_start, new_n) for every hunk of path in sha."""
    diff = git("show", "-U0", "--format=", "--no-renames", sha, "--", path)
    return [(int(a), int(b or 1), int(c), int(d or 1)) for a, b, c, d in HUNK.findall(diff)]


def touched_functions(sha: str, path: str) -> set[str]:
    """Qualified names of functions whose lines changed in sha (new side; a
    pure deletion credits the old-side function and the new-side neighbour)."""
    names: set[str] = set()
    new = spans(sha, path)
    old = None
    for a, an, c, cn in hunks(sha, path):
        if cn > 0:
            for ln in range(c, c + cn):
                f = fn_at(new, ln)
                if f:
                    names.add(f["name"])
        else:                                   # pure deletion
            if old is None:
                old = spans(sha + "^", path)
            for ln in range(a, a + max(an, 1)):
                f = fn_at(old, ln)
                if f:
                    names.add(f["name"])
            f = fn_at(new, c) or fn_at(new, c + 1)
            if f:
                names.add(f["name"])
    return names


def commits_for(path: str, since: str | None, follow: bool) -> list[dict]:
    args = ["log", "--no-merges", "--format=%H%x00%at%x00%an%x00%s", "--name-only"]
    if since:
        args.append(f"--since={since}")
    if follow:
        args += ["--follow", "-M"]
    raw = git(*args, "--", path)
    out = []
    cur = None
    for line in raw.split("\n"):
        if "\x00" in line:
            sha, at, an, subj = line.split("\x00", 3)
            cur = {"sha": sha, "at": int(at), "author": an, "subject": subj,
                   "kind": classify_commit(subj), "path": path}
            out.append(cur)
        elif line.strip() and cur is not None:
            cur["path"] = line.strip()
    return out


# ------------------------------------------------------------ scan data ----
hot = json.load(open(TS / "hotspots.json"))["hotspots"]
report = json.load(open(TS / "report.json"))
verdicts = {f["id"]: f for f in json.load(open(DATA / "verdicts.json"))["findings"]}
findings = report["findings"]

NOTE = re.compile(r"## Source — `([^`]+)`\n\n_lines (\d+)-(\d+) .*?_\n\n```\w*\n(.*?)\n```", re.S)
today_excerpt: dict[str, dict] = {}
for hs in hot:
    t = (TS / "bundles" / f"{hs['id']}.md").read_text()
    m = NOTE.search(t)
    lo, hi = int(m.group(2)), int(m.group(3))
    today_excerpt[hs["id"]] = {"lo": lo, "hi": hi, "lines": len(m.group(4).split("\n"))}


# ---------------------------------------------------------------- refs ----
REF = re.compile(r"([\w./\-]+\.(?:py|rst|toml|cfg)):(\d+)(?:-(\d+))?((?:\s*(?:and|,)\s*\d+(?:-\d+)?)*)")


def parse_refs(s: str | None) -> list[dict]:
    """'a.py:10-20; b.py:5 and 30-40; site-packages/x.py:1' -> ranges."""
    out = []
    for m in REF.finditer(s or ""):
        path, a, b, extra = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        rngs = [(a, int(b) if b else a)]
        for e in re.finditer(r"(\d+)(?:-(\d+))?", extra or ""):
            rngs.append((int(e.group(1)), int(e.group(2) or e.group(1))))
        for lo, hi in rngs:
            kind = ("dependency" if "site-packages" in path else
                    "docs" if path.endswith(".rst") else "repo")
            out.append({"file": path, "lo": lo, "hi": hi, "kind": kind})
    return out


def covered(rng: dict, excerpt: list[tuple[int, int]]) -> float:
    n = rng["hi"] - rng["lo"] + 1
    hit = sum(1 for ln in range(rng["lo"], rng["hi"] + 1) if any(a <= ln <= b for a, b in excerpt))
    return hit / n


# ------------------------------------------------------------- per file ----
def rank(fs: list[dict], churn: dict, fixes: dict, fix_weight: float) -> list[dict]:
    mx_c = max([churn.get(f["name"], 0) + fix_weight * fixes.get(f["name"], 0) for f in fs] + [1])
    mx_ccn = max([f["ccn"] for f in fs] + [1])
    rows = []
    for f in fs:
        c = churn.get(f["name"], 0) + fix_weight * fixes.get(f["name"], 0)
        rows.append({**f, "commits": churn.get(f["name"], 0), "fix_commits": fixes.get(f["name"], 0),
                     "score": round((c / mx_c) * (f["ccn"] / mx_ccn), 4)})
    # churned functions by score, then unchurned by ccn (fills leftover budget)
    rows.sort(key=lambda r: (-r["score"], -r["ccn"], r["start"]))
    return rows


def excerpt_for(ranked: list[dict], budget: int, nlines: int, skip: bool = False) -> list[tuple[int, int]]:
    """Greedy fill, whole functions with CTX lines each side; the function
    that overflows is truncated (as _clip does today) and filling stops."""
    chosen: list[tuple[int, int]] = []
    used = 0
    for r in ranked:
        lo, hi = max(1, r["start"] - CTX), min(nlines, r["end"] + CTX)
        new_lines = sum(1 for ln in range(lo, hi + 1) if not any(a <= ln <= b for a, b in chosen))
        if new_lines == 0:
            continue
        if used + new_lines > budget:
            if skip:
                continue                      # whole functions only; try smaller ones
            room = budget - used
            if room > CTX + 2:
                chosen.append((lo, lo + room - 1))
            break
        chosen.append((lo, hi))
        used += new_lines
    chosen.sort()
    merged: list[tuple[int, int]] = []
    for a, b in chosen:
        if merged and a <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


results: dict = {"method": {}, "hotspots": {}, "findings": {}, "coupling": {}, "q3": {}}
t0 = time.time()
for hs in hot:
    hid, path = hs["id"], hs["file"]
    head_fs = spans(HEAD, path)
    nlines = len(git("show", f"{HEAD}:{path}").split("\n"))
    variants: dict[str, dict] = {}
    for label, since, follow in (("window", SINCE, False), ("full", None, True)):
        if label == "full" and not FULL_HISTORY:
            continue
        cs = commits_for(path, since, follow)
        churn: dict[str, int] = defaultdict(int)
        fixes: dict[str, int] = defaultdict(int)
        per_commit: dict[str, list[str]] = {}
        for cmt in cs:
            names = touched_functions(cmt["sha"], cmt["path"])
            per_commit[cmt["sha"]] = sorted(names)
            for n in names:
                churn[n] += 1
                if cmt["kind"] == "fix":
                    fixes[n] += 1
        variants[label] = {"commits": len(cs), "churn": dict(churn), "fixes": dict(fixes),
                           "per_commit": per_commit,
                           "commit_meta": {c["sha"]: {"kind": c["kind"], "subject": c["subject"], "at": c["at"]} for c in cs}}
        print(f"{hid} {label}: {len(cs)} commits, {len(churn)} functions touched  [{time.time()-t0:.0f}s]", file=sys.stderr)
    w = variants["window"]
    rA = rank(head_fs, w["churn"], w["fixes"], 0.0)
    rB = rank(head_fs, w["churn"], w["fixes"], 2.0)        # a fix counts 3x
    budget = today_excerpt[hid]["lines"]
    exA, exB = excerpt_for(rA, budget, nlines), excerpt_for(rB, budget, nlines)
    exS = excerpt_for(rA, budget, nlines, skip=True)
    tod = today_excerpt[hid]
    entry = {"file": path, "lines": nlines, "today": {**tod, "function": hs["complexity"]["top_function"]},
             "budget_lines": budget,
             "top8_churn_x_ccn": [{k: r[k] for k in ("name", "start", "end", "ccn", "commits", "fix_commits", "score")} for r in rA[:8]],
             "top8_fix_weighted": [{k: r[k] for k in ("name", "start", "end", "ccn", "commits", "fix_commits", "score")} for r in rB[:8]],
             "xray_excerpt_A": exA, "xray_excerpt_B": exB, "xray_excerpt_A_skip": exS,
             "xray_A_lines": sum(b - a + 1 for a, b in exA), "xray_B_lines": sum(b - a + 1 for a, b in exB),
             "window": {"commits": w["commits"], "functions_touched": len(w["churn"]),
                        "per_commit": w["per_commit"], "commit_meta": w["commit_meta"]}}
    if "full" in variants:
        fv = variants["full"]
        rF = rank(head_fs, fv["churn"], fv["fixes"], 0.0)
        entry["full_history"] = {"commits": fv["commits"], "functions_touched": len(fv["churn"]),
                                 "top8_churn_x_ccn": [{k: r[k] for k in ("name", "start", "end", "ccn", "commits", "fix_commits", "score")} for r in rF[:8]],
                                 "xray_excerpt_F": excerpt_for(rF, budget, nlines)}
        entry["_full_per_commit"] = fv["per_commit"]
        entry["_full_meta"] = fv["commit_meta"]
    entry["_ranked_A"] = rA
    entry["_head_fs"] = head_fs
    results["hotspots"][hid] = entry

# ---------------------------------------------------------- per finding ----
def blame_ages(path: str, lo: int, hi: int) -> list[int]:
    raw = git("blame", "-w", "-L", f"{lo},{hi}", "--line-porcelain", HEAD, "--", path)
    return [int(m) for m in re.findall(r"^author-time (\d+)$", raw, re.M)]


def blame_shas(path: str, lo: int, hi: int) -> set[str]:
    raw = git("blame", "-w", "-L", f"{lo},{hi}", "--porcelain", HEAD, "--", path)
    return set(re.findall(r"^([0-9a-f]{40}) \d+ \d+", raw, re.M))


def commit_touches_fn(sha: str, path: str, lo: int, hi: int) -> bool:
    """Did sha change a line inside [lo,hi] of path? (any-side, by hunk overlap at HEAD lines
    is impossible; we use the function at HEAD containing lo and ask whether sha touched it)."""
    f = fn_at(spans(HEAD, path), lo)
    if not f:
        return False
    full = git("rev-parse", sha).strip()
    return f["name"] in touched_functions(full, path)


for f in findings:
    fid, hid = f["id"], f["hotspot_id"]
    hs_entry = results["hotspots"][hid]
    hfile = hs_entry["file"]
    v = verdicts[fid]
    cited = []
    for e in f["evidence"]:
        if e["type"] == "code":
            cited += parse_refs(e["ref"])
    refuting = parse_refs((v.get("refuting_fact") or {}).get("where"))
    tod = [(hs_entry["today"]["lo"], hs_entry["today"]["hi"])]
    exA, exB = hs_entry["xray_excerpt_A"], hs_entry["xray_excerpt_B"]
    exS = hs_entry["xray_excerpt_A_skip"]
    exF = hs_entry.get("full_history", {}).get("xray_excerpt_F")

    def cov(rngs):
        mine = [r for r in rngs if r["file"] == hfile]
        other = [r for r in rngs if r["file"] != hfile]
        def frac(ex):
            return None if not mine else round(sum(covered(r, ex) for r in mine) / len(mine), 2)
        d = {"in_hotspot_file": len(mine), "other_repo_files": sorted({r["file"] for r in other if r["kind"] == "repo"}),
             "docs": sorted({r["file"] for r in other if r["kind"] == "docs"}),
             "dependency": sorted({r["file"] for r in other if r["kind"] == "dependency"}),
             "today": frac(tod), "xray_A": frac(exA), "xray_B": frac(exB), "xray_A_skip": frac(exS)}
        if exF:
            d["xray_full"] = frac(exF)
        d["functions"] = sorted({(fn_for(hs_entry["_head_fs"], r["lo"], r["hi"]) or {"name": "<module>"})["name"] for r in mine})
        return d

    cited_cov, ref_cov = cov(cited), cov(refuting)
    # ages of cited lines (all repo files)
    ages = []
    for r in cited:
        if r["kind"] == "repo" and (REPO / r["file"]).exists():
            ages += blame_ages(r["file"], r["lo"], r["hi"])
    age_days = [(SCAN_TS - a) / 86400 for a in ages]
    # commits
    commit_ev = [e for e in f["evidence"] if e["type"] not in ("code", "detector")]
    shas = [e["ref"].split()[0] for e in commit_ev]
    cited_blame = set()
    for r in cited:
        if r["kind"] == "repo" and (REPO / r["file"]).exists():
            cited_blame |= blame_shas(r["file"], r["lo"], r["hi"])
    wrote = {s: any(b.startswith(s) for b in cited_blame) for s in shas}
    # fix commits touching cited functions in window (hotspot file only)
    w = hs_entry["window"]
    fn_names = cited_cov["functions"]
    fix_touch = sum(1 for sha, names in w["per_commit"].items()
                    if w["commit_meta"][sha]["kind"] == "fix" and set(names) & set(fn_names))
    any_touch = sum(1 for sha, names in w["per_commit"].items() if set(names) & set(fn_names))
    rv_commits = {c["sha"]: c for c in v.get("commits") or []}
    results["findings"][fid] = {
        "hotspot": hid, "verdict": v["verdict"], "claimed": v["confidence_assessment"]["claimed"],
        "deserved": v["confidence_assessment"]["deserved"],
        "cited": cited, "cited_coverage": cited_cov,
        "refuting": refuting, "refuting_in_bundle_per_reviewer": (v.get("refuting_fact") or {}).get("in_bundle"),
        "refuting_coverage": ref_cov if refuting else None,
        "age_days": {"n": len(age_days), "median": round(median(age_days)) if age_days else None,
                     "min": round(min(age_days)) if age_days else None, "max": round(max(age_days)) if age_days else None,
                     "share_older_than_2y": round(sum(1 for a in age_days if a > 730) / len(age_days), 2) if age_days else None},
        "commits": [{"sha": s, "kind": e.get("kind"), "wrote_cited_lines_blame": wrote[s],
                     "reviewer_role": rv_commits.get(s, {}).get("role_actual"),
                     "reviewer_wrote": rv_commits.get(s, {}).get("wrote_cited_lines")} for s, e in zip(shas, commit_ev)],
        "has_commit": bool(shas), "has_fix_commit": any(e.get("kind") == "fix" for e in commit_ev),
        "fix_commit_wrote_cited_lines": any(e.get("kind") == "fix" and wrote[s] for s, e in zip(shas, commit_ev)),
        "any_commit_wrote_cited_lines": any(wrote.values()),
        "fix_commits_touching_cited_fns_window": fix_touch,
        "commits_touching_cited_fns_window": any_touch,
        "n_preconditions_reviewer": len(v.get("preconditions") or []),
        "n_preconditions_literal_ne_effective_reviewer": sum(
            1 for p in v.get("preconditions") or [] if str(p.get("literal_default")) != str(p.get("effective_default"))),
    }

# --------------------------------------------------------------- coupling ----
TARGET_K = (5, 10)
for hid, hs_entry in results["hotspots"].items():
    hfile = hs_entry["file"]
    top = [r["name"] for r in hs_entry["_ranked_A"][:3]]
    # targets: other-file locations cited or refuting, from this hotspot's findings
    targets: dict[tuple[str, str], str] = {}
    for fid, fr in results["findings"].items():
        if fr["hotspot"] != hid:
            continue
        for r, role in [(r, "cited") for r in fr["cited"]] + [(r, "refuting") for r in fr["refuting"]]:
            if r["kind"] == "repo" and r["file"] != hfile and r["file"].endswith(".py") and (REPO / r["file"]).exists():
                fn = fn_for(spans(HEAD, r["file"]), r["lo"], r["hi"])
                targets[(r["file"], fn["name"] if fn else "<module>")] = f"{fid}:{role}"
    hs_raw = next(h for h in hot if h["id"] == hid)
    out = {"top_functions": top, "targets": {f"{k[0]}::{k[1]}": v for k, v in targets.items()},
           "file_level_coupled_files_in_hotspots_json": hs_raw.get("coupled_files")}
    for label in ("window", "full"):
        if label == "full" and "full_history" not in hs_entry:
            continue
        per_commit = hs_entry["window"]["per_commit"] if label == "window" else hs_entry["_full_per_commit"]
        shared = [sha for sha, names in per_commit.items() if set(names) & set(top)]
        counts: dict[tuple[str, str], int] = defaultdict(int)
        file_counts: dict[str, int] = defaultdict(int)
        for sha in shared:
            files = [p for p in git("show", "--format=", "--name-only", sha).split("\n")
                     if p.endswith(".py") and p.startswith("celery/") and p != hfile and not p.startswith("t/")]
            for p in files:
                file_counts[p] += 1
                for n in touched_functions(sha, p):
                    counts[(p, n)] += 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        franked = sorted(file_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        hits = {}
        for tkey, who in targets.items():
            pos = next((i for i, (k, _) in enumerate(ranked) if k == tkey), None)
            cnt = counts.get(tkey, 0)
            tied = sum(1 for _, c in ranked if c == cnt) if cnt else None
            fpos = next((i for i, (k, _) in enumerate(franked) if k == tkey[0]), None)
            hits[f"{tkey[0]}::{tkey[1]}"] = {"for": who, "shared_commits": cnt, "rank": None if pos is None else pos + 1,
                                            "ties_at_count": tied, "top5": pos is not None and pos < 5,
                                            "top10": pos is not None and pos < 10,
                                            "file_level_rank": None if fpos is None else fpos + 1,
                                            "file_shared_commits": file_counts.get(tkey[0], 0)}
        out[label] = {"shared_commits_of_top_functions": len(shared), "candidates": len(ranked),
                      "top10": [{"fn": f"{k[0]}::{k[1]}", "n": c} for k, c in ranked[:10]],
                      "targets": hits}
        print(f"{hid} coupling {label}: {len(shared)} commits, {len(ranked)} candidate functions [{time.time()-t0:.0f}s]", file=sys.stderr)
    results["coupling"][hid] = out

for e in results["hotspots"].values():
    for k in [k for k in e if k.startswith("_")]:
        del e[k]

results["method"] = {
    "window_commits": f"git log --no-merges --since={SINCE} -- <file> (matches hotspots.json counts exactly)",
    "full_history": "git log --no-merges --follow -M (only with --full)",
    "function_credit": "new-side hunk lines (git show -U0) mapped to lizard function spans in that revision; pure deletions credit the old-side function; identity = ast-qualified name (Class.method / outer.inner), lizard name as fallback",
    "fix_classification": "scripts/_common.classify_commit imported directly",
    "rank_A": "(commits_in_window / max) x (ccn_at_HEAD / max_ccn); ties by ccn; zero-churn functions follow by ccn",
    "rank_B": "((commits + 2*fix_commits) / max) x (ccn / max_ccn) -- a fix counts three times",
    "excerpt": f"same line budget as today's Source block; whole functions +/-{CTX} lines, greedy in rank order; the overflowing function is truncated and filling stops (mirrors _clip)",
    "coupling": "commits touching the hotspot's top-3 rank-A functions; every other celery/*.py (tests under t/ excluded) function touched in those commits counted; rank by shared commits",
    "age": "git blame -w at HEAD, author-time, days before the scan timestamp",
}
json.dump(results, open(OUT / "results.json", "w"), indent=1, default=list)
print(f"done in {time.time()-t0:.0f}s", file=sys.stderr)
