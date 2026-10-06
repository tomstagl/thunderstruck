#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Score a run against labelled ground truth (spec 2026-10-03-correctness-benchmark-design.md).

Deterministic, standard library only: no network, no model, no git.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETS = ROOT / "docs" / "calibration" / "correctness"

LABELS_SCHEMA = "thunderstruck.labels/v1"
RUN_SCHEMA = "thunderstruck.benchmark-run/v1"
RESULT_SCHEMA = "thunderstruck.benchmark/v1"

VERDICTS = ("correct", "correct_but_gated", "partially_correct", "wrong")
RUN_VERDICTS = ("upheld", "upheld_but_gated", "narrowed", "refuted")
BASES = ("executed", "read", "reasoned")
CONFIDENCE = ("low", "medium", "high")
ROLES = ("development", "holdout")
RANGE_KINDS = ("repo", "dependency", "docs", "history")
PRECONDITION_KINDS = ("setting", "environment")
VALUE_TYPES = ("none", "bool", "number", "text")

_SHA = re.compile(r"^[0-9a-f]{40}$")

class InputError(Exception):
    """Input that cannot be scored. ``problems`` names every reason."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# --------------------------------------------------------------- label sets
def validate_label_set(doc: dict, where: str) -> list[str]:
    p: list[str] = []
    if doc.get("schema") != LABELS_SCHEMA:
        return [f"{where}: schema is not {LABELS_SCHEMA}"]
    if not _SHA.match(str(doc.get("commit", ""))):
        p.append(f"{where}: commit is not a 40-character hex SHA")
    if doc.get("role") not in ROLES:
        p.append(f"{where}: role must be one of {', '.join(ROLES)}")
    if not doc.get("repo"):
        p.append(f"{where}: repo is empty")
    labels = doc.get("labels")
    if not isinstance(labels, list):
        return p + [f"{where}: labels is not a list"]
    keys = [lb.get("key") for lb in labels]
    for key in sorted({k for k in keys if keys.count(k) > 1}, key=str):
        p.append(f"{where}: key {key} occurs more than once")
    for lb in labels:
        k = lb.get("key") or "<no key>"
        for field in ("key", "verdict", "basis", "labelled_by"):
            if not lb.get(field):
                p.append(f"{where}: {k}: {field} is missing")
        if lb.get("verdict") and lb["verdict"] not in VERDICTS:
            p.append(f"{where}: {k}: verdict {lb['verdict']!r} is not one of {', '.join(VERDICTS)}")
        if lb.get("basis") and lb["basis"] not in BASES:
            p.append(f"{where}: {k}: basis {lb['basis']!r} is not one of {', '.join(BASES)}")
        if lb.get("basis") == "executed" and not lb.get("established_by"):
            p.append(f"{where}: {k}: basis is executed but established_by is empty")
        dc = lb.get("deserved_confidence")
        if dc is not None and dc not in CONFIDENCE:
            p.append(f"{where}: {k}: deserved_confidence {dc!r} is not one of {', '.join(CONFIDENCE)}")
        dup = lb.get("duplicate_of")
        if dup is not None and (dup == lb.get("key") or dup not in keys):
            p.append(f"{where}: {k}: duplicate_of {dup!r} is not another key in the set")
        for r in ((lb.get("refuting_fact") or {}).get("ranges") or []):
            if r.get("kind") not in RANGE_KINDS:
                p.append(f"{where}: {k}: range kind {r.get('kind')!r} is not one of {', '.join(RANGE_KINDS)}")
            elif r["kind"] == "repo":
                lo, hi = r.get("lo"), r.get("hi")
                if not (isinstance(lo, int) and isinstance(hi, int) and 0 < lo <= hi and r.get("file")):
                    p.append(f"{where}: {k}: repo range {r.get('file')}:{lo}-{hi} is not a valid line range")
        for pc in lb.get("preconditions") or []:
            if pc.get("kind") not in PRECONDITION_KINDS:
                p.append(f"{where}: {k}: precondition {pc.get('setting')!r} kind is not setting or environment")
            for side in ("literal", "effective"):
                if (pc.get(side) or {}).get("type") not in VALUE_TYPES:
                    p.append(f"{where}: {k}: precondition {pc.get('setting')!r} {side} has no valid type")
    return p


def load_label_sets(paths: list[Path]) -> list[dict]:
    """Load and validate every set; raise InputError naming every problem."""
    sets, problems = [], []
    for path in paths:
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError) as e:
            problems.append(f"{path}: {e}")
            continue
        found = validate_label_set(doc, str(path))
        if found:
            problems += found
            continue
        doc["_path"] = str(path)
        doc["_by_key"] = {lb["key"]: lb for lb in doc["labels"]}
        sets.append(doc)
    seen: dict[str, str] = {}
    for s in sets:
        if s["commit"] in seen:
            problems.append(f"{s['_path']}: commit {s['commit']} is also the commit of {seen[s['commit']]}")
        seen[s["commit"]] = s["_path"]
    if problems:
        raise InputError(problems)
    return sets


def default_label_paths() -> list[Path]:
    return sorted(DEFAULT_SETS.glob("*/labels.json"))


def select_set(sets: list[dict], commit: str) -> dict:
    for s in sets:
        if commit and s["commit"].startswith(commit) and len(commit) >= 7:
            return s
    loaded = ", ".join(f"{s['repo']}@{s['commit'][:7]}" for s in sets) or "none"
    raise InputError([f"run commit {commit or '<none>'} matches no loaded label set (loaded: {loaded})"])


# ------------------------------------------------------------------ figures
def wilson(k: int, n: int, z: float = 1.959964) -> tuple[int, int]:
    """Wilson 95% score interval, in whole percent."""
    if n == 0:
        return (0, 100)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round((c - h) / d * 100), round((c + h) / d * 100))


def basis_of(label_set: dict, keys: list[str]) -> dict:
    """What a figure over ``keys`` rests on."""
    mix: dict[str, dict[str, int]] = {}
    for k in sorted(keys):
        lb = label_set["_by_key"][k]
        by = mix.setdefault(lb["labelled_by"], {})
        by[lb["basis"]] = by.get(lb["basis"], 0) + 1
    return {"repo": label_set["repo"], "commit": label_set["commit"], "n": len(keys),
            "labelled": len(label_set["labels"]), "labellers": mix}


def figure(name: str, k: int, n: int, basis: dict) -> dict:
    lo, hi = wilson(k, n)
    return {"name": name, "k": k, "n": n, "interval": [lo, hi], "basis": basis}


def format_basis(basis: dict) -> str:
    parts = []
    for who, bases in sorted(basis["labellers"].items()):
        detail = ", ".join(f"{c} {b}" for b, c in sorted(bases.items(), key=lambda x: BASES.index(x[0])))
        parts.append(f"{sum(bases.values())} {who} ({detail})")
    n = (f"n={basis['n']} findings" if basis["n"] == basis["labelled"]
         else f"n={basis['n']} of {basis['labelled']} labelled findings")
    return f"{basis['repo']}@{basis['commit'][:7]} · {n} · labels: {'; '.join(parts) or 'none'}"


def format_figure(fig: dict, revealed: bool = False) -> str:
    lo, hi = fig["interval"]
    tail = " · revealed" if revealed else ""
    return f"{fig['name']:<28} {fig['k']}/{fig['n']}  ({lo}–{hi}%)  {format_basis(fig['basis'])}{tail}"


# --------------------------------------------------------------------- runs
def validate_run(doc: dict, where: str) -> list[str]:
    if doc.get("schema") != RUN_SCHEMA:
        return [f"{where}: schema is not {RUN_SCHEMA}"]
    p = []
    if not doc.get("commit"):
        p.append(f"{where}: commit is missing")
    if not isinstance(doc.get("produced_by"), dict) or not doc["produced_by"].get("stage"):
        p.append(f"{where}: produced_by.stage is missing")
    if not isinstance(doc.get("findings"), dict):
        return p + [f"{where}: findings is not an object keyed by finding key"]
    for key, rec in sorted(doc["findings"].items()):
        v = rec.get("verdict")
        if v is not None and v not in RUN_VERDICTS:
            p.append(f"{where}: {key}: verdict {v!r} is not one of {', '.join(RUN_VERDICTS)}")
        c = rec.get("confidence")
        if c is not None and c not in CONFIDENCE:
            p.append(f"{where}: {key}: confidence {c!r} is not one of {', '.join(CONFIDENCE)}")
    return p


def load_run(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise InputError([f"{path}: {e}"]) from None
    problems = validate_run(doc, str(path))
    if problems:
        raise InputError(problems)
    return doc


def run_from_report(report_path: Path) -> dict:
    """--report: a scan's confidences as a run."""
    try:
        report = json.loads(report_path.read_text())
    except (OSError, ValueError) as e:
        raise InputError([f"{report_path}: {e}"]) from None
    findings = {}
    for f in report.get("findings") or []:
        if f.get("key"):
            findings[f["key"]] = {"confidence": f.get("confidence")}
    return {"schema": RUN_SCHEMA, "commit": (report.get("repo") or {}).get("head", ""),
            "produced_by": {"stage": "investigator", "model": None, "source": str(report_path)},
            "findings": findings}


def split_run(run: dict, label_set: dict) -> tuple[dict, list[str], list[str]]:
    """(scored records by key, unlabelled keys, keys excluded by independence)."""
    model = (run.get("produced_by") or {}).get("model")
    scored, unlabelled, excluded = {}, [], []
    for key, rec in sorted(run["findings"].items()):
        lb = label_set["_by_key"].get(key)
        if lb is None:
            unlabelled.append(key)
        elif model and lb["labelled_by"] == model:
            excluded.append(key)
        else:
            scored[key] = rec
    return scored, unlabelled, excluded


# ------------------------------------------------------------------ scoring
def score_confidence(records: dict, label_set: dict) -> dict:
    rows = {}
    for k, r in records.items():
        deserved = label_set["_by_key"][k].get("deserved_confidence")
        if not r.get("confidence") or not deserved:
            continue
        step = CONFIDENCE.index(r["confidence"]) - CONFIDENCE.index(deserved)
        rows[k] = {"run": r["confidence"], "deserved": deserved, "step": step}
    counts = {"exact": sum(1 for x in rows.values() if x["step"] == 0),
              "within one": sum(1 for x in rows.values() if abs(x["step"]) <= 1),
              "over": sum(1 for x in rows.values() if x["step"] > 0),
              "under": sum(1 for x in rows.values() if x["step"] < 0)}
    high_above = sorted(k for k, x in rows.items() if x["run"] == "high" and x["step"] > 0)
    return {"rows": rows, "counts": counts, "high_above_deserved": high_above, "keys": sorted(rows)}


SAME, ONE_STEP, WRONG_DIRECTION, CORRECT_REFUTED = "same", "one step", "wrong direction", "correct refuted"
VERDICT_OUTCOMES = (SAME, ONE_STEP, WRONG_DIRECTION, CORRECT_REFUTED)
VERDICT_MATRIX = {
    #                   correct          correct_but_gated  partially_correct  wrong
    "upheld":           (SAME,            ONE_STEP,          WRONG_DIRECTION,   WRONG_DIRECTION),
    "upheld_but_gated": (ONE_STEP,        SAME,              WRONG_DIRECTION,   WRONG_DIRECTION),
    "narrowed":         (ONE_STEP,        ONE_STEP,          SAME,              ONE_STEP),
    "refuted":          (CORRECT_REFUTED, CORRECT_REFUTED,   ONE_STEP,          SAME),
}


def verdict_outcome(run_verdict: str, label_verdict: str) -> str:
    return VERDICT_MATRIX[run_verdict][VERDICTS.index(label_verdict)]


def score_verdicts(records: dict, label_set: dict) -> dict:
    rows = {k: {"run": r["verdict"], "label": label_set["_by_key"][k]["verdict"],
                "outcome": verdict_outcome(r["verdict"], label_set["_by_key"][k]["verdict"])}
            for k, r in records.items() if r.get("verdict")}
    counts = {o: sum(1 for x in rows.values() if x["outcome"] == o) for o in VERDICT_OUTCOMES}
    return {"rows": rows, "counts": counts, "keys": sorted(rows)}


def score_duplicates(records: dict, label_set: dict) -> dict:
    stated = {k: r.get("duplicate_of") for k, r in records.items() if "duplicate_of" in r}
    labelled = {k: lb["duplicate_of"] for k, lb in label_set["_by_key"].items()
                if lb.get("duplicate_of") and k in stated}
    found = sorted(k for k, d in labelled.items() if stated.get(k) == d)
    missed = sorted(k for k, d in labelled.items() if stated.get(k) != d)
    false = sorted(k for k, d in stated.items() if d and labelled.get(k) != d)
    return {"found": found, "missed": missed, "false": false, "keys": sorted(stated)}
