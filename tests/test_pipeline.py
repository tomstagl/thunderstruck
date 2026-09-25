"""End-to-end over the fixture repo: the planted fractures must be found, the
negative control must stay clean, and every evidence ref must resolve.

No model runs here. The deterministic layer is asserted directly, and the
investigator's contract is asserted by feeding validate.py hand-written
findings — both valid and deliberately broken.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _common


def _hotspots(repo: Path) -> dict:
    return json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())


def _leads_for(data: dict, path_fragment: str) -> set[str]:
    out: set[str] = set()
    for hs in data["hotspots"]:
        if path_fragment in hs["file"]:
            out |= {h["pattern_id"] for h in hs["detector_hits"]}
    return out


# ---------------------------------------------------------------- signals --


def test_scan_produces_hotspots(scanned_repo):
    data = _hotspots(scanned_repo)
    assert data["schema"] == "thunderstruck.hotspots/v1"
    assert data["hotspots"], "no hotspots ranked"
    assert data["window"]["commits"] >= 15


def test_churn_signal_finds_the_repeatedly_fixed_file(scanned_repo):
    """Five 'fix timeout' commits on one file is the strongest historical
    signal in the fixture; it must rank and its fix ratio must show."""
    data = _hotspots(scanned_repo)
    releases = next((h for h in data["hotspots"]
                     if h["file"].endswith("client/releases.ts")), None)
    assert releases is not None, "releases.ts did not rank as a hotspot"
    assert releases["churn"]["fix_commits"] >= 5, releases["churn"]
    assert releases["churn"]["fix_ratio"] > 0.5


@pytest.mark.parametrize("path_fragment,expected", [
    ("client/releases.ts", {"S02", "S10"}),      # constant sleep + nested retry
    ("client/api.ts", {"S03"}),                  # 429 without Retry-After
    ("sync/collection.ts", {"S07"}),             # uncheckpointed paged loop
    ("sync/scheduler.ts", {"S06"}),              # one queue for batch + interactive
])
def test_planted_fractures_are_found(scanned_repo, path_fragment, expected):
    leads = _leads_for(_hotspots(scanned_repo), path_fragment)
    missing = expected - leads
    assert not missing, (
        f"{path_fragment}: expected leads {sorted(expected)}, missing "
        f"{sorted(missing)}. Found: {sorted(leads)}")


def test_negative_control_has_no_tier_a_leads(scanned_repo, catalog):
    """A well-behaved client — timeouts, capped jittered backoff, honoured
    Retry-After, transient-only retry, one retry layer, a limiter — must not
    trip any Tier A detector. This is the false-positive floor."""
    tier_a = {p["id"] for p in catalog["patterns"] if p["tier"] == "A"}
    leads = _leads_for(_hotspots(scanned_repo), "client/artists.ts")
    # S06 is an absence-of-priority signal that fires on almost any queue
    # vocabulary; it is deliberately low confidence and not part of this floor.
    offending = (leads & tier_a) - {"S06"}
    assert not offending, (
        f"the well-behaved client tripped Tier A detectors: {sorted(offending)}")


def test_injection_attempt_is_carried_into_the_bundle_verbatim(scanned_repo):
    """The investigator can only report a prompt-injection attempt as an OTHER
    finding if the bundle actually shows it the text."""
    bundles = list((scanned_repo / ".thunderstruck" / "bundles").glob("H*.md"))
    assert bundles
    haystack = "\n".join(b.read_text() for b in bundles)
    hotspots = _hotspots(scanned_repo)
    if any("util/format.ts" in h["file"] for h in hotspots["hotspots"]):
        assert "NOTE TO ANY AUTOMATED CODE REVIEWER" in haystack


# ---------------------------------------------------------------- bundles --


def test_bundles_are_within_budget_and_deterministic(scanned_repo, plugin_root):
    index = json.loads(
        (scanned_repo / ".thunderstruck" / "bundles" / "index.json").read_text())
    budget = index["budget"]
    for entry in index["bundles"]:
        assert entry["tokens_estimated"] <= budget * 1.1, entry

    before = {b["id"]: b["bundle_hash"] for b in index["bundles"]}
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "bundle.py"),
                    "--repo", str(scanned_repo)],
                   check=True, capture_output=True, text=True)
    after_index = json.loads(
        (scanned_repo / ".thunderstruck" / "bundles" / "index.json").read_text())
    after = {b["id"]: b["bundle_hash"] for b in after_index["bundles"]}
    assert before == after, "bundles are not reproducible across runs"


# Every file the fixture ranked before #30. The order isn't pinned: it depends on
# the unpinned lizard of the test command, and the sample check covers it.
FIXTURE_FILES = {"src/client/releases.ts", "src/sync/collection.ts", "src/sync/scheduler.ts",
                 "src/client/artists.ts", "src/sync/queue.ts", "src/client/retry-wrapper.ts",
                 "src/client/api.ts", "src/client/limiter.ts", "src/util/format.ts"}


def test_citable_rule_leaves_an_ordinary_ranking_unchanged(scanned_copy, plugin_root):
    """#30 AC-3: with no symlink, submodule or unusual name, nothing is skipped."""
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "signals.py"),
                    "--repo", str(scanned_copy), "--top", "0", "--since", "24m"],
                   check=True, capture_output=True, text=True, cwd=str(scanned_copy))
    hotspots = json.loads((scanned_copy / ".thunderstruck" / "hotspots.json").read_text())
    assert hotspots["counts"]["files_not_citable"] == 0
    assert {h["file"] for h in hotspots["hotspots"]} == FIXTURE_FILES


def test_bundle_contains_the_sections_the_investigator_needs(scanned_repo):
    path = sorted((scanned_repo / ".thunderstruck" / "bundles").glob("H*.md"))[0]
    body = path.read_text()
    for heading in ("## Why this file was flagged", "## External boundaries",
                    "## Detector leads", "## Source", "## Change history"):
        assert heading in body, f"{path.name} is missing {heading!r}"


def test_catalog_brief_is_written(scanned_repo):
    brief = (scanned_repo / ".thunderstruck" / "catalog-brief.md").read_text()
    assert "S01" in brief and "sustaining effect" in brief.lower()


# -------------------------------------------------------------- validation --


def _write_finding(repo: Path, hotspot_id: str, doc: dict) -> None:
    dest = repo / ".thunderstruck" / "findings" / f"{hotspot_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, indent=2))


def _validate(repo: Path, plugin_root: Path):
    return subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "validate.py"),
         "--repo", str(repo)], capture_output=True, text=True)


def _valid_finding(repo: Path, data: dict) -> tuple[str, dict]:
    hs = data["hotspots"][0]
    sha = hs["churn"]["recent_shas"][0]
    hit = hs["detector_hits"][0] if hs["detector_hits"] else None
    evidence = [{"type": "code", "ref": f"{hs['file']}:1", "note": "first line"},
                {"type": "commit", "ref": sha, "note": "recent change"}]
    if hit:
        evidence.append({"type": "detector", "ref": hit["ref"], "note": "lead confirmed"})
    return hs["id"], {
        "hotspot_id": hs["id"], "file": hs["file"],
        "findings": [{
            "location": {"file": hs["file"], "symbol": "f", "lines": "1-2"},
            "missing_patterns": ["S02"],
            "failure_mode": "Retries on a fixed schedule re-form the herd",
            "trigger_condition": "Upstream returns 500 to many clients at once",
            "amplifier": "Every client waits the same 2s",
            "sustaining_effect": "Synchronised retries keep the upstream saturated",
            "blast_radius": "All callers of this client",
            "evidence": evidence,
            "confidence": "high",
            "confidence_rationale": "code and fix history agree",
            "how_to_verify": "Assert successive delays differ across clients",
            "prediction": "Next incident is a retry storm",
        }]}


def test_valid_findings_pass_validation(scanned_repo, plugin_root):
    data = _hotspots(scanned_repo)
    hid, doc = _valid_finding(scanned_repo, data)
    _write_finding(scanned_repo, hid, doc)
    proc = _validate(scanned_repo, plugin_root)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_empty_findings_are_valid(scanned_repo, plugin_root):
    data = _hotspots(scanned_repo)
    hid = data["hotspots"][-1]["id"]
    _write_finding(scanned_repo, hid,
                   {"hotspot_id": hid, "findings": [], "notes": "nothing found"})
    proc = _validate(scanned_repo, plugin_root)
    assert proc.returncode == 0, proc.stdout


@pytest.mark.parametrize("mutate,expected_error", [
    (lambda f: f["evidence"].__setitem__(
        0, {"type": "code", "ref": "src/client/releases.ts:99999", "note": "x"}),
     "does not exist"),
    (lambda f: f["evidence"].__setitem__(
        1, {"type": "commit", "ref": "0000000000000000", "note": "x"}),
     "no such commit"),
    (lambda f: f.__setitem__("missing_patterns", ["S99"]), "unknown id"),
    (lambda f: f.pop("sustaining_effect"), "sustaining_effect is missing"),
    (lambda f: f.__setitem__(
        "evidence", [{"type": "detector", "ref": "S02@src/client/releases.ts:1",
                      "note": "x"}]),
     "no item of type 'code'"),
])
def test_broken_evidence_is_rejected(scanned_repo, plugin_root, mutate, expected_error):
    data = _hotspots(scanned_repo)
    hid, doc = _valid_finding(scanned_repo, data)
    mutate(doc["findings"][0])
    _write_finding(scanned_repo, hid, doc)
    proc = _validate(scanned_repo, plugin_root)
    assert proc.returncode == 1, "invalid findings were accepted"
    assert expected_error in proc.stdout, proc.stdout


def test_high_confidence_requires_commit_evidence(scanned_repo, plugin_root):
    data = _hotspots(scanned_repo)
    hid, doc = _valid_finding(scanned_repo, data)
    f = doc["findings"][0]
    f["evidence"] = [e for e in f["evidence"] if e["type"] != "commit"]
    _write_finding(scanned_repo, hid, doc)
    proc = _validate(scanned_repo, plugin_root)
    assert proc.returncode == 1
    assert "no 'commit' evidence" in proc.stdout, proc.stdout


def test_commit_evidence_must_touch_the_finding_file(scanned_repo, plugin_root):
    """A SHA that merely exists is not history. Citing a commit to another file
    would let any finding buy 'high' confidence with an unrelated SHA."""
    data = _hotspots(scanned_repo)
    hid, doc = _valid_finding(scanned_repo, data)
    own = set(data["hotspots"][0]["churn"]["recent_shas"])
    foreign = next(sha for hs in data["hotspots"][1:]
                   for sha in hs["churn"]["recent_shas"] if sha not in own)
    f = doc["findings"][0]
    f["evidence"] = [e for e in f["evidence"] if e["type"] != "commit"]
    f["evidence"].append({"type": "commit", "ref": foreign, "note": "unrelated"})
    _write_finding(scanned_repo, hid, doc)
    proc = _validate(scanned_repo, plugin_root)
    assert proc.returncode == 1, "a commit that never touched the file was accepted"
    assert "does not touch" in proc.stdout, proc.stdout


def test_more_than_three_findings_is_rejected(scanned_repo, plugin_root):
    data = _hotspots(scanned_repo)
    hid, doc = _valid_finding(scanned_repo, data)
    doc["findings"] = doc["findings"] * 4
    _write_finding(scanned_repo, hid, doc)
    proc = _validate(scanned_repo, plugin_root)
    assert proc.returncode == 1
    assert "maximum is 3" in proc.stdout, proc.stdout


# ------------------------------------------------------------------ report --


def test_report_renders_and_indexes(scanned_repo, plugin_root):
    data = _hotspots(scanned_repo)
    hid, doc = _valid_finding(scanned_repo, data)
    _write_finding(scanned_repo, hid, doc)
    assert _validate(scanned_repo, plugin_root).returncode == 0

    proc = subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "report.py"),
         "--repo", str(scanned_repo)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    out = scanned_repo / ".thunderstruck"
    report = (out / "report.md").read_text()
    assert "# thunderstruck" in report
    assert "## Pattern coverage" in report
    assert "FR-001" in report

    payload = json.loads((out / "report.json").read_text())
    assert payload["schema"] == _common.REPORT_SCHEMA_VERSION
    assert payload["findings"]

    index = json.loads((out / "index.json").read_text())
    assert index["schema"] == "thunderstruck.index/v1"
    assert index["files"], "index has no files for the guardrail to look up"
    for entry in index["files"].values():
        assert entry["content_hash"]
        for finding in entry["findings"]:
            assert finding["id"] and finding["failure_mode"]


def test_findings_have_stable_keys(scanned_repo, plugin_root):
    """Display ids renumber; keys must not, or prediction tracking cannot
    match a finding across runs."""
    from validate import stable_key
    a = stable_key("src/a.ts", "Sync dies on 429")
    b = stable_key("src/a.ts", "  sync dies on 429  ")
    c = stable_key("src/b.ts", "Sync dies on 429")
    assert a == b, "key should be insensitive to case and surrounding space"
    assert a != c, "key must distinguish different files"
