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
            if not isinstance(pc.get("setting"), str) or not pc["setting"].strip():
                p.append(f"{where}: {k}: precondition setting is missing")
            if pc.get("kind") not in PRECONDITION_KINDS:
                p.append(f"{where}: {k}: precondition {pc.get('setting')!r} kind is not setting or environment")
            for side in ("literal", "effective"):
                value = pc.get(side) or {}
                if value.get("type") not in VALUE_TYPES:
                    p.append(f"{where}: {k}: precondition {pc.get('setting')!r} {side} has no valid type")
                elif value["type"] != "none" and "value" not in value:
                    p.append(f"{where}: {k}: precondition {pc.get('setting')!r} {side} has no value")
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
    if not isinstance(doc, dict) or doc.get("schema") != RUN_SCHEMA:
        return [f"{where}: schema is not {RUN_SCHEMA}"]
    p = []
    if not doc.get("commit") or not isinstance(doc["commit"], str):
        p.append(f"{where}: commit is missing or not a string")
    if not isinstance(doc.get("produced_by"), dict) or not doc["produced_by"].get("stage"):
        p.append(f"{where}: produced_by.stage is missing")
    if not isinstance(doc.get("findings"), dict):
        return p + [f"{where}: findings is not an object keyed by finding key"]
    for key, rec in sorted(doc["findings"].items()):
        if not isinstance(rec, dict):
            p.append(f"{where}: {key}: the record is not an object")
            continue
        for field, kind in (("preconditions", list), ("bundle", dict)):
            if field in rec and not isinstance(rec[field], kind):
                p.append(f"{where}: {key}: {field} is not a {'list' if kind is list else 'object'}")
        if isinstance(rec.get("preconditions"), list) and not all(isinstance(x, dict) for x in rec["preconditions"]):
            p.append(f"{where}: {key}: a precondition is not an object")
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
            record = {"confidence": f.get("confidence")}
            if isinstance(f.get("preconditions"), list):
                record["preconditions"] = [{"setting": p.get("setting"), "default": p.get("default")}
                                           for p in f["preconditions"] if isinstance(p, dict)]
            findings[f["key"]] = record
    return {"schema": RUN_SCHEMA, "commit": (report.get("repo") or {}).get("head", ""),
            "produced_by": {"stage": "investigator", "model": None, "source": str(report_path)},
            "findings": findings}


_NOTE = re.compile(r"^## Source — `(?P<file>[^`]+)`\n\n_(?P<note>[^\n]*)_\n\n```[^\n]*\n(?P<body>.*?)\n```\n(?=\n+## |\n*\Z)",
                   re.S | re.M)
_MARKER = re.compile(r"\n\n\.\.\. \[[^\]]*: \d+ characters omitted\] \.\.\.\n\n")
_WHOLE = re.compile(r"^whole file, (\d+) lines$")
_RANGE = re.compile(r"^lines (\d+)-(\d+) — ")
_TRIMMED = re.compile(r"^file trimmed to fit the budget; (\d+) lines total$")


def shown_lines(bundle_text: str) -> tuple[str, list[tuple[int, int]]] | None:
    """The file and line ranges a bundle's Source block shows; None if unparsable."""
    m = _NOTE.search(bundle_text)
    if not m:
        return None
    note, body = m.group("note"), m.group("body")
    if w := _WHOLE.match(note):
        return m.group("file"), [(1, int(w.group(1)))]  # never clipped
    if r := _RANGE.match(note):
        start, end = int(r.group(1)), int(r.group(2))
    elif t := _TRIMMED.match(note):
        start, end = 1, int(t.group(1))
    else:
        return None
    if body.endswith("\n"):
        # The excerpt ran to the file's final newline; bundle.py counted the empty line after it.
        body, end = body[:-1], end - 1
    parts = _MARKER.split(body)
    if len(parts) == 1:
        return m.group("file"), [(start, end)]
    if len(parts) != 2:
        return None
    head, tail = parts
    # A line the character cut split is not shown: drop the last head line and the first tail line.
    n_head = len(head.split("\n")) - 1
    n_tail = len(tail.split("\n")) - 1
    ranges = []
    if n_head > 0:
        ranges.append((start, start + n_head - 1))
    if n_tail > 0:
        ranges.append((end - n_tail + 1, end))
    return m.group("file"), ranges


def add_bundles(run: dict, bundles_dir: Path, report_path: Path) -> dict:
    """--bundles: attach what each finding's bundle shows, joined through the scan."""
    try:
        report = json.loads(report_path.read_text())
    except (OSError, ValueError) as e:
        raise InputError([f"{report_path}: {e}"]) from None
    try:
        index = json.loads((bundles_dir / "index.json").read_text())
    except (OSError, ValueError) as e:
        raise InputError([f"{bundles_dir}: {e}"]) from None
    files = {b["id"]: b["file"] for b in index.get("bundles") or []}
    for f in report.get("findings") or []:
        key, hid = f.get("key"), f.get("hotspot_id")
        if not key or not hid:
            continue
        if hid not in files:
            # A finding whose hotspot has no bundle entry is unreadable, never silently unscored.
            run["findings"].setdefault(key, {})["bundle"] = {"file": None, "shown": None}
            continue
        path = bundles_dir / f"{hid}.md"
        parsed = shown_lines(path.read_text()) if path.is_file() else None
        rec = run["findings"].setdefault(key, {})
        if parsed is None or parsed[0] != files[hid]:
            rec["bundle"] = {"file": files[hid], "shown": None}
        else:
            rec["bundle"] = {"file": files[hid], "shown": [list(r) for r in parsed[1]]}
    return run


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


SHOWN, NOT_SHOWN, ELSEWHERE, NOT_IN_REPO, UNREADABLE = (
    "shown", "not shown", "elsewhere", "not in repository", "unreadable")
BUNDLE_OUTCOMES = (SHOWN, NOT_SHOWN, ELSEWHERE, NOT_IN_REPO, UNREADABLE)


def score_bundles(records: dict, label_set: dict) -> dict:
    rows = {}
    for k, r in records.items():
        fact = label_set["_by_key"][k].get("refuting_fact")
        if not fact or "bundle" not in r:
            continue
        repo = [x for x in fact.get("ranges") or [] if x["kind"] == "repo"]
        bfile, shown = r["bundle"]["file"], r["bundle"]["shown"]
        mine = [x for x in repo if x["file"] == bfile]
        partly = bool(mine) and len(mine) < len(repo)
        if not repo:
            outcome = NOT_IN_REPO
        elif shown is None:
            outcome = UNREADABLE
        elif not mine:
            outcome = ELSEWHERE
        elif all(any(a <= x["lo"] and x["hi"] <= b for a, b in shown) for x in mine):
            outcome = SHOWN
        else:
            outcome = NOT_SHOWN
        rows[k] = {"outcome": outcome, "partly_elsewhere": outcome == SHOWN and partly}
    counts = {o: sum(1 for x in rows.values() if x["outcome"] == o) for o in BUNDLE_OUTCOMES}
    counts["partly elsewhere"] = sum(1 for x in rows.values() if x["partly_elsewhere"])
    return {"rows": rows, "counts": counts, "keys": sorted(rows)}


_NUM = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(s|ms)?$")


def normalise_value(raw) -> dict:
    """A run's stated default as a §4.5 value."""
    if raw is None:
        return {"type": "none"}
    if isinstance(raw, bool):
        return {"type": "bool", "value": raw}
    if isinstance(raw, (int, float)):
        return {"type": "number", "value": "inf" if raw == math.inf else raw}
    text = " ".join(str(raw).split())
    low = text.casefold()
    if low in ("none", "null"):
        return {"type": "none"}
    if low in ("true", "false"):
        return {"type": "bool", "value": low == "true"}
    if low in ("inf", "infinity"):
        return {"type": "number", "value": "inf"}
    if m := _NUM.match(low):
        value = float(m.group(1))
        if m.group(2) == "ms":
            return {"type": "number", "value": value / 1000, "unit": "s"}
        return {"type": "number", "value": value, **({"unit": "s"} if m.group(2) else {})}
    return {"type": "text", "value": low}


def values_match(a: dict, b: dict) -> bool:
    if a["type"] != b["type"]:
        return False
    if a["type"] == "none":
        return True
    if a["type"] == "number":
        va, vb = a["value"], b["value"]
        if (va == "inf") != (vb == "inf"):
            return False
        if va != "inf" and float(va) != float(vb):
            return False
        return not a.get("unit") or not b.get("unit") or a["unit"] == b["unit"]
    if a["type"] == "text":
        return " ".join(str(a["value"]).split()).casefold() == " ".join(str(b["value"]).split()).casefold()
    return a["value"] == b["value"]


EFFECTIVE, LITERAL_ONLY, NEITHER, NOT_STATED = "matches effective", "matches literal only", "matches neither", "not stated"
DEFAULT_OUTCOMES = (EFFECTIVE, LITERAL_ONLY, NEITHER, NOT_STATED)


def score_defaults(records: dict, label_set: dict) -> dict:
    rows = []
    for k, r in sorted(records.items()):
        if "preconditions" not in r:
            continue
        stated = {str(p.get("setting", "")).strip().casefold(): p["default"]
                  for p in r["preconditions"] if "default" in p}
        for pc in label_set["_by_key"][k].get("preconditions") or []:
            if pc["kind"] != "setting":
                continue
            name = pc["setting"].strip().casefold()
            discriminating = not values_match(pc["literal"], pc["effective"])
            if name not in stated:
                outcome = NOT_STATED
            else:
                v = normalise_value(stated[name])
                outcome = (EFFECTIVE if values_match(v, pc["effective"])
                           else LITERAL_ONLY if values_match(v, pc["literal"]) else NEITHER)
            rows.append({"key": k, "setting": pc["setting"], "discriminating": discriminating, "outcome": outcome})
    head = [x for x in rows if x["discriminating"]]
    counts = {o: sum(1 for x in head if x["outcome"] == o) for o in DEFAULT_OUTCOMES}
    rest = {o: sum(1 for x in rows if not x["discriminating"] and x["outcome"] == o) for o in DEFAULT_OUTCOMES}
    return {"rows": rows, "counts": counts, "non_discriminating": rest,
            "keys": sorted({x["key"] for x in rows})}


# ------------------------------------------------------------------ results
def _figures(measure: str, m: dict, basis: dict) -> list[dict]:
    c = m.get("counts", {})
    if measure == "verdicts":
        n = len(m["keys"])
        return [figure(f"verdict: {o}", c[o], n, basis) for o in VERDICT_OUTCOMES]
    if measure == "duplicates":
        pairs = len(m["found"]) + len(m["missed"])
        return [figure("duplicates found", len(m["found"]), pairs, basis),
                figure("false duplicates", len(m["false"]), len(m["keys"]), basis)]
    if measure == "confidence":
        n = len(m["keys"])
        return [figure(f"confidence: {o}", c[o], n, basis) for o in ("exact", "within one", "over", "under")]
    if measure == "bundles":
        located = c[SHOWN] + c[NOT_SHOWN]
        n = len(m["keys"])
        return [figure("refuting fact shown", c[SHOWN], located, basis),
                figure("shown, partly elsewhere", c["partly elsewhere"], located, basis)] + [
                figure(f"refuting fact {o}", c[o], n, basis) for o in (ELSEWHERE, NOT_IN_REPO, UNREADABLE)]
    if measure == "defaults":
        n = sum(c.values())
        return [figure(f"default {o}", c[o], n, basis) for o in DEFAULT_OUTCOMES]
    raise ValueError(measure)


PER_FINDING = ("rows", "found", "missed", "false", "high_above_deserved")
SCORERS = {"verdicts": score_verdicts, "duplicates": score_duplicates, "confidence": score_confidence,
           "bundles": score_bundles, "defaults": score_defaults}


def evaluate(runs: list[dict], sets: list[dict], reveal: bool = False) -> dict:
    out = []
    for run in runs:
        ls = select_set(sets, run.get("commit", ""))
        records, unlabelled, excluded = split_run(run, ls)
        hide = ls["role"] == "holdout" and not reveal
        measures = {}
        for name, scorer in SCORERS.items():
            m = scorer(records, ls)
            if not m["keys"]:
                continue
            basis = basis_of(ls, m["keys"])
            m["figures"] = _figures(name, m, basis)
            if hide:
                for detail in PER_FINDING + ("keys",):
                    m.pop(detail, None)
            measures[name] = m
        out.append({"repo": ls["repo"], "commit": ls["commit"], "role": ls["role"],
                    "revealed": ls["role"] == "holdout" and reveal,
                    "produced_by": run.get("produced_by"),
                    "independence_checked": bool((run.get("produced_by") or {}).get("model")),
                    "display": {} if hide else {lb["key"]: lb.get("display", "") for lb in ls["labels"]},
                    "unlabelled": unlabelled, "excluded": excluded, "measures": measures})
    return {"schema": RESULT_SCHEMA, "runs": out, "pooled": pooled(out)}


def pooled(results: list[dict]) -> dict:
    """Pooled figures per measure, only across runs on distinct sets."""
    commits = [r["commit"] for r in results]
    if len(set(commits)) < 2 or len(set(commits)) != len(commits):
        return {}
    out: dict[str, list[dict]] = {}
    for r in results:
        for name, m in r["measures"].items():
            for fig in m["figures"]:
                slot = {f["name"]: f for f in out.setdefault(name, [])}
                if fig["name"] in slot:
                    f = slot[fig["name"]]
                    k, n = f["k"] + fig["k"], f["n"] + fig["n"]
                    f.update({"k": k, "n": n, "interval": list(wilson(k, n))})
                    f["basis"] = _merge_basis(f["basis"], fig["basis"])
                else:
                    out[name].append(json.loads(json.dumps(fig)))
    return out


def _merge_basis(a: dict, b: dict) -> dict:
    mix = json.loads(json.dumps(a["labellers"]))
    for who, bases in b["labellers"].items():
        for bs, c in bases.items():
            mix.setdefault(who, {})[bs] = mix.get(who, {}).get(bs, 0) + c
    return {"repo": f"{a['repo']} + {b['repo']}", "commit": "pooled", "n": a["n"] + b["n"],
            "labelled": a["labelled"] + b["labelled"], "labellers": mix}


def render(result: dict) -> str:
    lines = []
    for r in result["runs"]:
        pb = r["produced_by"] or {}
        lines.append(f"# {r['repo']}@{r['commit'][:7]} ({r['role']}) — {pb.get('stage')}"
                     f"{' · ' + pb['model'] if pb.get('model') else ''}")
        if not r["independence_checked"]:
            lines.append("independence not checked: the run does not record a model")
        if r["excluded"]:
            lines.append(f"excluded: {len(r['excluded'])} — labeller is the scored model")
        if r["unlabelled"]:
            lines.append(f"unlabelled: {len(r['unlabelled'])} — " + ", ".join(r["unlabelled"]))
        for name, m in r["measures"].items():
            lines.append(f"## {name}")
            for fig in m["figures"]:
                lines.append(format_figure(fig, revealed=r["revealed"]))
            if m.get("high_above_deserved"):
                lines.append("high above deserved: " + ", ".join(_disp(r, k) for k in _order(r, m["high_above_deserved"])))
            if any(detail in m for detail in PER_FINDING):
                lines += _rows(name, m, r)
        lines.append("")
    for name, figs in result["pooled"].items():
        lines.append(f"## pooled {name}")
        lines += [format_figure(f, revealed=any(r["revealed"] for r in result["runs"])) for f in figs]
    return "\n".join(lines).rstrip() + "\n"


def _disp(run_result: dict, key: str) -> str:
    d = run_result["display"].get(key)
    return f"{d} ({key})" if d else key


def _order(run_result: dict, keys) -> list[str]:
    """Keys in display order, so a reader finds FR-001 first; ties and missing ids by key."""
    return sorted(keys, key=lambda k: (run_result["display"].get(k) or "~", k))


def _rows(name: str, m: dict, r: dict) -> list[str]:
    if name == "verdicts":
        return [f"  {_disp(r, k)}: {x['run']} vs {x['label']} → {x['outcome']}" for k, x in ((k, m["rows"][k]) for k in _order(r, m["rows"]))]
    if name == "confidence":
        return [f"  {_disp(r, k)}: {x['run']} vs {x['deserved']} ({x['step']:+d})"
                for k, x in ((k, m["rows"][k]) for k in _order(r, m["rows"]))]
    if name == "bundles":
        return [f"  {_disp(r, k)}: {x['outcome']}{' (partly elsewhere)' if x['partly_elsewhere'] else ''}"
                for k, x in ((k, m["rows"][k]) for k in _order(r, m["rows"]))]
    if name == "defaults":
        return [f"  {_disp(r, x['key'])} {x['setting']}: {x['outcome']}{'' if x['discriminating'] else ' (non-discriminating)'}"
                for x in sorted(m["rows"], key=lambda x: (r["display"].get(x["key"]) or "~", x["key"]))]
    if name == "duplicates":
        return ([f"  found: {_disp(r, k)}" for k in m["found"]] + [f"  missed: {_disp(r, k)}" for k in m["missed"]]
                + [f"  false: {_disp(r, k)}" for k in m["false"]])
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", action="append", type=Path, default=[], help="a run file (repeatable)")
    ap.add_argument("--report", type=Path, help="a scan's report.json: its confidences")
    ap.add_argument("--bundles", type=Path, help="that scan's bundles/ (needs --report)")
    ap.add_argument("--labels", action="append", type=Path, default=[], help="a label set directory (repeatable)")
    ap.add_argument("--json", action="store_true", help="machine output")
    ap.add_argument("--reveal", action="store_true", help="per-finding rows for holdout sets")
    a = ap.parse_args(argv)
    try:
        if a.bundles and not a.report:
            raise InputError(["--bundles needs --report (the scan that produced the bundles)"])
        if not a.run and not a.report:
            raise InputError(["nothing to score: give --run or --report"])
        paths = [d / "labels.json" for d in a.labels] or default_label_paths()
        sets = load_label_sets(paths)
        runs = [load_run(p) for p in a.run]
        if a.report:
            run = run_from_report(a.report)
            if a.bundles:
                add_bundles(run, a.bundles, a.report)
            runs.append(run)
        result = evaluate(runs, sets, reveal=a.reveal)
    except InputError as e:
        for p in e.problems:
            print(f"benchmark: {p}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n" if a.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
