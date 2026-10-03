#!/usr/bin/env python3
"""Summaries over results.json: coverage by verdict class, coupling hits, Q3 rules."""
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

OUT = Path(__file__).resolve().parent
r = json.load(open(OUT / "results.json"))
F = r["findings"]
ORD = {"low": 0, "medium": 1, "high": 2}
CORRECT = {"correct": 1.0, "correct_but_gated": 1.0, "partially_correct": 0.5, "wrong": 0.0}
VARIANTS = ["today", "xray_A", "xray_B", "xray_A_skip"] + (["xray_full"] if any("xray_full" in f["cited_coverage"] for f in F.values()) else [])


def spearman(xs, ys):
    def ranks(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
                j += 1
            for k in range(i, j + 1):
                out[s[k]] = (i + j) / 2 + 1
            i = j + 1
        return out
    rx, ry = ranks(xs), ranks(ys)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 2) if den else 0.0


# ------------------------------------------------------ Q1.4 coverage summary
cov = {"per_finding": {}, "by_verdict": {}, "totals": {}}
by_class = defaultdict(list)
for fid, f in F.items():
    c, rc = f["cited_coverage"], f["refuting_coverage"]
    row = {"verdict": f["verdict"], "cited_in_file": c["in_hotspot_file"],
           "cited_other_files": len(c["other_repo_files"]),
           "cited": {v: c.get(v) for v in VARIANTS},
           "refuting_in_file": rc["in_hotspot_file"] if rc else None,
           "refuting_elsewhere": (rc["other_repo_files"] + rc["docs"] + rc["dependency"]) if rc else None,
           "refuting": {v: rc.get(v) for v in VARIANTS} if rc and rc["in_hotspot_file"] else None}
    cov["per_finding"][fid] = row
    by_class[f["verdict"]].append(row)
for cls, rows in by_class.items():
    d = {"n": len(rows)}
    for v in VARIANTS:
        vals = [x["cited"][v] for x in rows if x["cited"][v] is not None]
        d[f"cited_full_{v}"] = sum(1 for x in vals if x >= 0.999)
        d[f"cited_mean_{v}"] = round(mean(vals), 2) if vals else None
        rv = [x["refuting"][v] for x in rows if x["refuting"] and x["refuting"][v] is not None]
        d[f"refuting_in_file_n"] = len(rv)
        d[f"refuting_full_{v}"] = sum(1 for x in rv if x >= 0.999)
    cov["by_verdict"][cls] = d
tot = {"n": len(F)}
for v in VARIANTS:
    vals = [f["cited_coverage"][v] for f in F.values() if f["cited_coverage"][v] is not None]
    tot[f"cited_full_{v}"] = sum(1 for x in vals if x >= 0.999)
    tot[f"cited_any_{v}"] = sum(1 for x in vals if x > 0)
    tot[f"cited_mean_{v}"] = round(mean(vals), 2)
    rv = [f["refuting_coverage"][v] for f in F.values() if f["refuting_coverage"] and f["refuting_coverage"]["in_hotspot_file"]]
    tot["refuting_facts_with_part_in_hotspot_file"] = len(rv)
    tot[f"refuting_full_{v}"] = sum(1 for x in rv if x >= 0.999)
refs = [f for f in F.values() if f["refuting_coverage"]]
tot["refuting_facts_total"] = len(refs)
tot["refuting_facts_entirely_outside_hotspot_file"] = sum(1 for f in refs if f["refuting_coverage"]["in_hotspot_file"] == 0)
tot["refuting_facts_touching_dependency_or_docs"] = sum(1 for f in refs if f["refuting_coverage"]["dependency"] or f["refuting_coverage"]["docs"])
cov["totals"] = tot

# ------------------------------------------------------- Q1.5 coupling summary
coup = {"window": {"targets": 0, "top5": 0, "top10": 0, "any_shared": 0},
        "full": {"targets": 0, "top5": 0, "top10": 0, "any_shared": 0}, "detail": []}
for hid, c in r["coupling"].items():
    for lab in ("window", "full"):
        if lab not in c:
            continue
        for k, t in c[lab]["targets"].items():
            coup[lab]["targets"] += 1
            coup[lab]["top5"] += bool(t["top5"])
            coup[lab]["top10"] += bool(t["top10"])
            coup[lab]["any_shared"] += t["shared_commits"] > 0
            coup["detail"].append({"hotspot": hid, "variant": lab, "target": k, "for": t["for"], "shared": t["shared_commits"],
                                   "rank": t["rank"], "ties": t["ties_at_count"], "candidates": c[lab]["candidates"],
                                   "file_rank": t["file_level_rank"]})

# -------------------------------------------------------------- Q1.6 age
age = {"by_verdict": {}, "rho_age_vs_correct": None}
for cls, rows in by_class.items():
    meds = [F[fid]["age_days"]["median"] for fid in F if F[fid]["verdict"] == cls and F[fid]["age_days"]["median"] is not None]
    age["by_verdict"][cls] = {"n": len(meds), "median_of_median_age_days": sorted(meds)[len(meds) // 2] if meds else None,
                              "min": min(meds) if meds else None, "max": max(meds) if meds else None}
ids = [fid for fid in F if F[fid]["age_days"]["median"] is not None]
age["rho_age_vs_correct"] = spearman([F[i]["age_days"]["median"] for i in ids], [CORRECT[F[i]["verdict"]] for i in ids])
age["rho_age_vs_deserved"] = spearman([F[i]["age_days"]["median"] for i in ids], [ORD[F[i]["deserved"]] for i in ids])
age["old_code_findings"] = {fid: {"median_age_days": F[fid]["age_days"]["median"], "verdict": F[fid]["verdict"]}
                            for fid in F if (F[fid]["age_days"]["median"] or 0) > 1500}

# ----------------------------------------------------------------- Q3 rules
def rule_current(f):          # validator gate as a predictor: high iff a cited [fix] commit touches the file
    return "high" if f["has_fix_commit"] else "medium"
def rule_blame(f):            # high iff a cited [fix] commit wrote a cited line; medium iff any commit wrote one; else low
    return "high" if f["fix_commit_wrote_cited_lines"] else "medium" if f["any_commit_wrote_cited_lines"] else "low"
def rule_fixcount(f):         # fix commits in window touching the cited functions
    n = f["fix_commits_touching_cited_fns_window"]
    return "high" if n >= 2 else "medium" if n == 1 else "low"
def rule_age(f):              # settled code: older cited lines -> higher
    a = f["age_days"]["median"] or 0
    return "high" if a > 730 else "medium" if a > 180 else "low"
def rule_age_inv(f):          # fresh code: younger -> higher
    a = f["age_days"]["median"] or 0
    return "high" if a <= 180 else "medium" if a <= 730 else "low"
def rule_precond(f):          # REVIEWER-DERIVED feature, not available at scan time
    n = f["n_preconditions_reviewer"]
    return "high" if n == 0 else "medium" if n <= 2 else "low"
def rule_const(f):
    return "medium"

RULES = {"claimed_by_investigator": lambda f: f["claimed"], "current_gate(high iff cited fix commit)": rule_current,
         "blame(fix commit wrote cited lines)": rule_blame, "fix_count_on_cited_functions": rule_fixcount,
         "age_old_is_high": rule_age, "age_young_is_high": rule_age_inv,
         "preconditions_reviewer_derived": rule_precond, "always_medium": rule_const}
q3 = {"table": {}, "rules": {}}
for fid, f in F.items():
    q3["table"][fid] = {"verdict": f["verdict"], "claimed": f["claimed"], "deserved": f["deserved"],
                        "has_commit": f["has_commit"], "has_fix_commit": f["has_fix_commit"],
                        "fix_commit_wrote_cited_lines": f["fix_commit_wrote_cited_lines"],
                        "any_commit_wrote_cited_lines": f["any_commit_wrote_cited_lines"],
                        "fix_commits_on_cited_fns_window": f["fix_commits_touching_cited_fns_window"],
                        "commits_on_cited_fns_window": f["commits_touching_cited_fns_window"],
                        "median_age_days": f["age_days"]["median"],
                        "n_preconditions(reviewer)": f["n_preconditions_reviewer"],
                        "n_precond_literal_ne_effective(reviewer)": f["n_preconditions_literal_ne_effective_reviewer"]}
des = [ORD[f["deserved"]] for f in F.values()]
cor = [CORRECT[f["verdict"]] for f in F.values()]
for name, fn in RULES.items():
    pred = [ORD[fn(f)] for f in F.values()]
    q3["rules"][name] = {"exact_agreement": sum(p == d for p, d in zip(pred, des)),
                         "within_one": sum(abs(p - d) <= 1 for p, d in zip(pred, des)),
                         "over_rated": sum(p > d for p, d in zip(pred, des)),
                         "under_rated": sum(p < d for p, d in zip(pred, des)),
                         "rho_vs_deserved": spearman(pred, des), "rho_vs_correctness": spearman(pred, cor),
                         "n": len(pred)}
feat = {"has_fix_commit": [int(f["has_fix_commit"]) for f in F.values()],
        "fix_commit_wrote_cited_lines": [int(f["fix_commit_wrote_cited_lines"]) for f in F.values()],
        "fix_commits_on_cited_fns": [f["fix_commits_touching_cited_fns_window"] for f in F.values()],
        "commits_on_cited_fns": [f["commits_touching_cited_fns_window"] for f in F.values()],
        "median_age": [f["age_days"]["median"] or 0 for f in F.values()],
        "n_preconditions(reviewer)": [f["n_preconditions_reviewer"] for f in F.values()],
        "n_cited_other_files": [len(f["cited_coverage"]["other_repo_files"]) for f in F.values()],
        "cited_today_coverage": [f["cited_coverage"]["today"] or 0 for f in F.values()]}
q3["feature_rho"] = {k: {"vs_deserved": spearman(v, des), "vs_correctness": spearman(v, cor)} for k, v in feat.items()}
# the three high claims
q3["high_claims"] = {fid: {"deserved": f["deserved"], "fix_commit_wrote_cited_lines": f["fix_commit_wrote_cited_lines"],
                           "reviewer_roles": [c["reviewer_role"] for c in f["commits"]]} for fid, f in F.items() if f["claimed"] == "high"}

r["summary"] = {"coverage": cov, "coupling": coup, "age": age, "q3": q3}
json.dump(r, open(OUT / "results.json", "w"), indent=1)
print(json.dumps(r["summary"], indent=1))
