"""Fetching one source: which edges survive, what neighbours add, and how the
budget and a failing neighbour degrade the result without failing it."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

import context

FAKE = Path(__file__).resolve().parent / "fixtures" / "fake_catalog.py"
MAIN = "component:default/fixture-app"
ARGV = [sys.executable, str(FAKE), "{entity_ref}"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in [v for v in os.environ if v.startswith("FAKE_CATALOG_")]:
        monkeypatch.delenv(var)


def src(**overrides):
    base = {"name": "catalog", "kind": "command", "argv": ARGV, "preflight": [],
            "timeout_s": 10, "extractor": "backstage-relations",
            "edge_types": {"dependsOn": "outbound", "dependencyOf": "inbound"},
            "neighbour_attributes": {"tier": "example.com/tier"}}
    base.update(overrides)
    return base


def test_fetch_extracts_edges_and_attributes(tmp_path):
    result = context.fetch_source(MAIN, src(), tmp_path, 60)
    assert result.error is None
    by_ref = {e["ref"]: e for e in result.edges}
    assert sorted(by_ref) == ["dependencyOf component:default/mobile-bff",
                              "dependencyOf component:default/web-frontend",
                              "dependsOn component:default/payments-api",
                              "dependsOn component:default/releases-api"]
    assert by_ref["dependencyOf component:default/web-frontend"]["attributes"] == {"tier": "2"}
    assert by_ref["dependencyOf component:default/mobile-bff"]["attributes"] == {}
    assert any("attribute value rejected" in w and "mobile-bff tier" in w
               for w in result.warnings)
    assert not any("ignore previous" in w for w in result.warnings)
    assert set(result.raws) == {MAIN, *(e["neighbour"] for e in result.edges)}


def test_no_attribute_mapping_means_one_call(tmp_path, monkeypatch):
    marker = tmp_path / "calls.txt"
    monkeypatch.setenv("FAKE_CATALOG_MARKER", str(marker))
    context.fetch_source(MAIN, src(neighbour_attributes={}), tmp_path, 60)
    assert len(marker.read_text().splitlines()) == 1


def test_preflight_failure_stops_before_the_fetch(tmp_path, monkeypatch):
    marker = tmp_path / "calls.txt"
    monkeypatch.setenv("FAKE_CATALOG_MARKER", str(marker))
    monkeypatch.setenv("FAKE_CATALOG_AUTH", "expired")
    result = context.fetch_source(
        MAIN, src(preflight=[sys.executable, str(FAKE), "--preflight"]), tmp_path, 60)
    assert result.error.startswith("preflight failed:")
    assert marker.read_text().splitlines() == ["--preflight"]


def test_main_entity_failure_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_FAIL_REFS", MAIN)
    assert "exited 3" in context.fetch_source(MAIN, src(), tmp_path, 60).error


def test_failed_neighbour_keeps_its_edge(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_FAIL_REFS", "component:default/payments-api")
    result = context.fetch_source(MAIN, src(), tmp_path, 60)
    assert result.error is None
    edge = next(e for e in result.edges if e["neighbour"] == "component:default/payments-api")
    assert edge["attributes"] == {}
    assert any("attributes unavailable for component:default/payments-api" in w
               for w in result.warnings)


def test_neighbours_are_capped_per_direction(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_EXTRA_DEPENDENTS", "30")
    result = context.fetch_source(MAIN, src(neighbour_attributes={}), tmp_path, 60)
    inbound = [e for e in result.edges if e["direction"] == "inbound"]
    assert len(inbound) == 25
    assert result.truncated == {"inbound": 7, "outbound": 0}
    assert any("7 inbound and 0 outbound are not listed" in w for w in result.warnings)


def test_total_budget_bounds_the_run(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_EXTRA_DEPENDENTS", "30")
    monkeypatch.setenv("FAKE_CATALOG_SLEEP", "0.4")
    start = time.monotonic()
    result = context.fetch_source(MAIN, src(), tmp_path, 1.5)
    assert time.monotonic() - start < 4
    assert result.error is None
    assert len(result.edges) == 27
    assert any("not fetched within the 1.5s context budget" in w for w in result.warnings)


def test_load_service_context_only_returns_usable_docs(tmp_path):
    import _common
    out = tmp_path / ".thunderstruck"
    out.mkdir()
    assert _common.load_service_context(tmp_path) is None
    (out / "context.json").write_text('{"status": "failed", "edges": []}')
    assert _common.load_service_context(tmp_path) is None
    (out / "context.json").write_text('{"status": "stale", "edges": []}')
    assert _common.load_service_context(tmp_path)["status"] == "stale"
