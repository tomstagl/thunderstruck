"""The second ground-truth set (#59): provenance, labels, baselines (spec 2026-10-03-second-ground-truth-design.md)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import benchmark as b

ROOT = Path(__file__).resolve().parent.parent
SETS = ROOT / "docs" / "calibration" / "correctness"
CELERY = SETS / "celery"
SECOND = SETS / "trigger-dev"  # the set chosen in Task 1 (spec §1)


def readme_row(name: str) -> str:
    text = (SECOND / "README.md").read_text()
    m = re.search(rf"^\| {re.escape(name)} \| (.+?) \|$", text, re.M)
    assert m, f"README.md has no '| {name} | … |' row"
    return m.group(1).strip()


def readme_commit() -> str:
    m = re.fullmatch(r"`([0-9a-f]{40})`", readme_row("Commit"))
    assert m, "the Commit row is not a backquoted 40-character SHA"
    return m.group(1)


# --- Task 1 -----------------------------------------------------------------
def readme_role() -> str:
    return readme_row("Role")


def test_the_set_is_public_pinned_and_licensed():
    assert re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", readme_row("Repository"))
    readme_commit()
    assert re.fullmatch(r"`\d{4}-\d{2}-\d{2}`", readme_row("Window from"))
    assert readme_role() in ("holdout", "development")
    assert readme_row("Licence")
    assert readme_row("Tests at the pinned commit")
    licences = sorted(p.name for p in (SECOND / "LICENSES").iterdir() if p.is_file())
    assert licences, "LICENSES/ is empty"
    for p in (SECOND / "LICENSES").iterdir():
        assert p.read_text().strip(), f"{p.name} is empty"


# --- Task 2 -----------------------------------------------------------------
# CI cannot know the labeller's $HOME or work directory; the check for those is
# Step 5's grep. A per-user macOS temp directory never appears in upstream source.
LOCAL_PATH = re.compile(r"/var/folders/")


def report() -> dict:
    return json.loads((SECOND / "scan" / "report.json").read_text())


def test_the_scan_is_of_the_pinned_commit_with_the_recorded_scope():
    r = report()
    assert r["repo"]["head"] == readme_commit()
    assert r["repo"]["root"] == "<repo>"
    for name in ("hotspots.json", "validation.json", "catalog-brief.md", "profile.toml"):
        assert (SECOND / "scan" / name).is_file(), name
    hs = json.loads((SECOND / "scan" / "hotspots.json").read_text())
    assert hs["config"]["profile"] is True
    assert hs["repo"]["root"] == "<repo>"
    assert hs["window"]["since"] == readme_row("Window from").strip("`")  # spec §4.2
    assert readme_row("Scan").startswith("`/thunderstruck-scan --top ")
    assert readme_row("Plugin")
    assert readme_row("Investigator model")


def test_the_scan_has_enough_valid_findings():
    r = report()
    assert r["counts"]["findings"] >= 15            # spec §4.2
    assert r["counts"]["findings"] == len(r["findings"])
    assert all(f["key"] for f in r["findings"])
    assert {f["hotspot_id"] for f in r["findings"]} <= {h["id"] for h in r["hotspots"]}


def test_no_local_path_is_checked_in():
    leaks = [str(p.relative_to(SECOND)) for p in SECOND.rglob("*")
             if p.is_file() and LOCAL_PATH.search(p.read_text(errors="ignore"))]
    assert leaks == []


# --- Task 3 -----------------------------------------------------------------
DEP_PLACEHOLDERS = ("<node_modules>/", "<gradle-cache>/")


def labels() -> dict:
    return b.load_label_sets([CELERY / "labels.json", SECOND / "labels.json"])[1]


def ac2_count(set_: dict) -> int:
    return sum(1 for lb in set_["labels"]
               if lb["basis"] == "executed"
               or (lb["basis"] == "read" and any(d in (lb.get("established_by") or "") for d in DEP_PLACEHOLDERS)))


def test_the_set_validates_beside_celery_with_the_recorded_role():
    s = labels()
    assert s["role"] == readme_role()
    assert s["commit"] == report()["repo"]["head"] == readme_commit()
    assert s["repo"] == readme_row("Repository").removeprefix("https://github.com/")


def test_every_finding_is_labelled_once_and_nothing_else():
    keys = [f["key"] for f in report()["findings"]]
    assert len(keys) == len(set(keys))
    assert sorted(lb["key"] for lb in labels()["labels"]) == sorted(keys)


def test_at_least_half_are_executed_or_read_from_dependency_source():
    s = labels()
    assert 2 * ac2_count(s) >= len(s["labels"]), (ac2_count(s), len(s["labels"]))


def test_every_label_says_how_and_executed_ones_name_checked_in_reproductions():
    for lb in labels()["labels"]:
        assert lb.get("established_by"), lb["display"]
        if lb["basis"] == "executed":
            named = re.findall(r"repro/[\w./-]+", lb["established_by"])
            assert named, lb["display"]
            for path in named:
                assert (SECOND / path).is_file(), path


def test_the_labeller_is_recorded_and_is_not_the_investigator():
    who = {lb["labelled_by"] for lb in labels()["labels"]}
    assert readme_row("Labelled by")
    assert readme_row("Investigator model") not in who


def test_review_has_a_section_per_finding():
    text = (SECOND / "review.md").read_text()
    for lb in labels()["labels"]:
        assert re.search(rf"^## {re.escape(lb['display'])} ", text, re.M), lb["display"]


# --- Task 4 -----------------------------------------------------------------
PIPELINE_SOURCE = ("scan/report.json and scan/bundles via benchmark.run_from_report and add_bundles; "
                   "verdict upheld for every reported finding (spec §7.1)")


def _second_model() -> str | None:
    m = readme_row("Investigator model")
    # The row reads "<model id> (<how many investigators>)"; the run records the id only.
    return None if m == "not recorded" else m.split(" (")[0]


def pipeline_run(set_dir: Path, model: str | None) -> dict:
    """Today's pipeline as one run (spec §7.1).

    run_from_report puts its argument path in produced_by.source; it is
    replaced below, so no local path reaches the file."""
    run = b.run_from_report(set_dir / "scan" / "report.json")
    b.add_bundles(run, set_dir / "scan" / "bundles", set_dir / "scan" / "report.json")
    for rec in run["findings"].values():
        rec["verdict"] = "upheld"
        rec["duplicate_of"] = None
    run["produced_by"] = {"stage": "pipeline", "model": model, "source": PIPELINE_SOURCE}
    run["findings"] = dict(sorted(run["findings"].items()))
    return run


def _dump(run: dict) -> str:
    return json.dumps(run, indent=2, sort_keys=True) + "\n"


def write_pipeline_runs() -> None:
    for set_dir, model in ((CELERY, None), (SECOND, _second_model())):
        (set_dir / "runs").mkdir(exist_ok=True)
        (set_dir / "runs" / "pipeline.json").write_text(_dump(pipeline_run(set_dir, model)))


def totals(run_path: Path) -> dict[str, dict[str, list[int]]]:
    sets = b.load_label_sets([CELERY / "labels.json", SECOND / "labels.json"])
    [r] = b.evaluate([b.load_run(run_path)], sets)["runs"]
    assert r["excluded"] == [], "the labeller is the scored model (spec §5.3)"
    assert r["unlabelled"] == []
    return {name: {f["name"]: [f["k"], f["n"]] for f in m["figures"]} for name, m in r["measures"].items()}


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "benchmark.py"), *args],
                          capture_output=True, text=True, cwd=ROOT)


CELERY_RUN = CELERY / "runs" / "pipeline.json"
SECOND_RUN = SECOND / "runs" / "pipeline.json"

# Filled in Step 4 from the set's own figures; totals only, whatever the role (spec §6).
SECOND_PIPELINE_TOTALS: dict[str, dict[str, list[int]]] = {
    "bundles": {
        "refuting fact elsewhere": [8, 11],
        "refuting fact not in repository": [0, 11],
        "refuting fact shown": [0, 3],
        "refuting fact unreadable": [0, 11],
        "shown, partly elsewhere": [0, 3],
    },
    "confidence": {
        "confidence: exact": [10, 15],
        "confidence: over": [1, 15],
        "confidence: under": [4, 15],
        "confidence: within one": [14, 15],
    },
    "duplicates": {
        "duplicates found": [0, 0],
        "false duplicates": [0, 15],
    },
    "verdicts": {
        "verdict: correct refuted": [0, 15],
        "verdict: one step": [1, 15],
        "verdict: same": [4, 15],
        "verdict: wrong direction": [10, 15],
    },
}


def test_pipeline_runs_rederive_from_the_scans():
    assert CELERY_RUN.read_text() == _dump(pipeline_run(CELERY, None))
    assert SECOND_RUN.read_text() == _dump(pipeline_run(SECOND, _second_model()))


def test_celery_pipeline_baseline():
    t = totals(CELERY_RUN)
    assert t["verdicts"] == {"verdict: same": [5, 21], "verdict: one step": [4, 21],
                             "verdict: wrong direction": [12, 21], "verdict: correct refuted": [0, 21]}
    assert t["duplicates"]["duplicates found"] == [0, 1]
    assert t["confidence"]["confidence: exact"] == [8, 21]
    assert t["confidence"]["confidence: within one"] == [20, 21]
    assert t["confidence"]["confidence: over"] == [6, 21]
    assert t["confidence"]["confidence: under"] == [7, 21]
    assert t["bundles"]["refuting fact shown"] == [4, 9]


def test_second_set_pipeline_baseline():
    assert SECOND_PIPELINE_TOTALS, "Task 4 Step 4 fills these in"
    assert totals(SECOND_RUN) == SECOND_PIPELINE_TOTALS


def test_both_sets_are_reported_per_set_and_pooled_with_their_n():
    p = _cli("--run", str(CELERY_RUN), "--run", str(SECOND_RUN))
    assert p.returncode == 0, p.stderr
    out = p.stdout
    s = labels()
    assert "# celery/celery@508c112 (development)" in out
    assert f"# {s['repo']}@{s['commit'][:7]} ({s['role']})" in out
    for measure in ("verdicts", "duplicates", "confidence", "bundles"):
        assert f"## pooled {measure}" in out, measure
    for ln in (ln for ln in out.splitlines() if re.search(r" \d+/\d+  \(", ln)):
        assert "@" in ln and "n=" in ln and "labels:" in ln, ln
    m = re.search(r"verdict: same\s+\d+/(\d+)  \(.*pooled", out)
    assert m and int(m.group(1)) == 21 + len(s["labels"])


def test_the_role_decides_what_prints_by_default():
    s = labels()
    head = f"# {s['repo']}@{s['commit'][:7]} ({s['role']})"
    default = _cli("--run", str(SECOND_RUN)).stdout
    assert head in default
    rows = re.search(r"^  FR-\d+ ", default, re.M)
    if s["role"] == "holdout":
        assert not rows
        shown = _cli("--run", str(SECOND_RUN), "--reveal").stdout
        rate_lines = [ln for ln in shown.splitlines() if re.search(r" \d+/\d+  \(", ln)]
        assert rate_lines and all(ln.endswith("· revealed") for ln in rate_lines)
    else:
        assert rows
