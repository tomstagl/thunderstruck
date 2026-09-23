"""Service context through the pipeline: bundles, validation, report."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bundle

WEB = "dependencyOf component:default/web-frontend"


def _bundles(repo: Path) -> dict[str, str]:
    return {p.name: p.read_text()
            for p in sorted((repo / ".thunderstruck" / "bundles").glob("H*.md"))}


def _index(repo: Path) -> dict:
    return json.loads((repo / ".thunderstruck" / "bundles" / "index.json").read_text())


def _context(repo: Path) -> dict:
    return json.loads((repo / ".thunderstruck" / "context.json").read_text())


def _hashes(repo: Path) -> dict[str, str]:
    return {b["id"]: b["bundle_hash"] for b in _index(repo)["bundles"]}


# ---------------------------------------------------------------- bundles --


def test_bundles_carry_the_service_context(context_scanned_repo):
    bundles = _bundles(context_scanned_repo)
    assert bundles
    for body in bundles.values():
        assert "## Service context (component-level, 1 hop)" in body
        assert f"`{WEB}` — tier: 2" in body
        assert "`dependsOn component:default/payments-api` — tier: 1" in body
        assert "ignore previous instructions" not in body


def test_bundle_index_records_the_context_hash(context_scanned_repo):
    index = _index(context_scanned_repo)
    ctx_hash = _context(context_scanned_repo)["context_hash"]
    assert index["context_hash"] == ctx_hash
    assert all(b["context_hash"] == ctx_hash for b in index["bundles"])


def test_context_bundles_stay_within_budget(context_scanned_repo):
    index = _index(context_scanned_repo)
    for entry in index["bundles"]:
        assert entry["tokens_estimated"] <= index["budget"] * 1.1, entry


def test_volatile_catalog_fields_do_not_change_bundles(context_scanned_copy, context_env,
                                                       run_steps):
    env = {**context_env, "FAKE_CATALOG_VOLATILE": "1"}
    run_steps(context_scanned_copy, env, ["context.py", "--refresh"], ["bundle.py"])
    first = _hashes(context_scanned_copy)
    run_steps(context_scanned_copy, env, ["context.py", "--refresh"], ["bundle.py"])
    assert _hashes(context_scanned_copy) == first


def test_stale_fallback_leaves_bundles_byte_identical(context_scanned_copy, context_env,
                                                      run_steps):
    before = _hashes(context_scanned_copy)
    path = context_scanned_copy / ".thunderstruck" / "context.json"
    doc = json.loads(path.read_text())
    doc["fetched_at"] = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(
        timespec="seconds")
    path.write_text(json.dumps(doc))
    run_steps(context_scanned_copy, {**context_env, "FAKE_CATALOG_AUTH": "expired"},
              ["context.py"], ["bundle.py"])
    assert _context(context_scanned_copy)["status"] == "stale"
    assert _hashes(context_scanned_copy) == before


def test_no_context_means_no_section(scanned_repo):
    for body in _bundles(scanned_repo).values():
        assert "## Service context" not in body
    assert bundle.section_service_context(None) == ""


def test_context_only_profile_renders_no_profile_section():
    assert bundle.section_profile({"context": {"enabled": False}}) == ""
    assert "## Repo profile" in bundle.section_profile(
        {"profile": {"notes": "x"}, "context": {}})


# --------------------------------------------------------------- validate --

import subprocess
import sys


def _hotspots(repo: Path) -> dict:
    return json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())


def _catalog_finding(data: dict, catalog_refs: list[str], code: bool = True) -> tuple[str, dict]:
    hs = data["hotspots"][0]
    evidence = []
    if code:
        evidence += [{"type": "code", "ref": f"{hs['file']}:1", "note": "first line"},
                     {"type": "commit", "ref": hs["churn"]["recent_shas"][0],
                      "note": "recent change"}]
    evidence += [{"type": "catalog", "ref": r, "note": "catalog edge"} for r in catalog_refs]
    return hs["id"], {"hotspot_id": hs["id"], "file": hs["file"], "findings": [{
        "location": {"file": hs["file"], "symbol": "f", "lines": "1-2"},
        "missing_patterns": ["S02"],
        "failure_mode": "Retries on a fixed schedule re-form the herd",
        "trigger_condition": "Upstream returns 500 to many clients at once",
        "amplifier": "Every client waits the same 2s",
        "sustaining_effect": None,
        "blast_radius": "web-frontend depends on this component",
        "evidence": evidence,
        "confidence": "high" if code else "medium",
        "confidence_rationale": "code and fix history agree",
        "how_to_verify": "Assert successive delays differ across clients"}]}


def _validate(repo: Path, plugin_root: Path, hid: str, doc: dict):
    dest = repo / ".thunderstruck" / "findings" / f"{hid}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc))
    return subprocess.run([sys.executable, str(plugin_root / "scripts" / "validate.py"),
                           "--repo", str(repo)], capture_output=True, text=True)


def test_catalog_evidence_validates_and_is_stamped(context_scanned_copy, plugin_root):
    hid, doc = _catalog_finding(_hotspots(context_scanned_copy), [WEB])
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 0, proc.stdout
    saved = json.loads(
        (context_scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert saved["findings"][0]["catalog_evidence"] == [{
        "ref": WEB, "direction": "inbound", "neighbour": "component:default/web-frontend",
        "attributes": {"tier": "2"}}]


def test_unknown_edge_is_rejected(context_scanned_copy, plugin_root):
    hid, doc = _catalog_finding(_hotspots(context_scanned_copy),
                                ["dependsOn component:default/made-up"])
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "no such edge in the service context" in proc.stdout


def test_catalog_only_finding_is_rejected(context_scanned_copy, plugin_root):
    hid, doc = _catalog_finding(_hotspots(context_scanned_copy), [WEB], code=False)
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "no item of type 'code'" in proc.stdout


def test_context_changed_since_bundling_is_rejected(context_scanned_copy, plugin_root):
    path = context_scanned_copy / ".thunderstruck" / "context.json"
    ctx = json.loads(path.read_text())
    ctx["context_hash"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(ctx))
    hid, doc = _catalog_finding(_hotspots(context_scanned_copy), [WEB])
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "context changed since bundling" in proc.stdout


def test_catalog_ref_without_context_is_rejected(scanned_copy, plugin_root):
    hid, doc = _catalog_finding(_hotspots(scanned_copy), [WEB])
    proc = _validate(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "no service context" in proc.stdout
