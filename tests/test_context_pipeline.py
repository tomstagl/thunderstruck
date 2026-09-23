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
