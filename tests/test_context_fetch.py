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
    def doc(status):
        return json.dumps({"status": status, "entity_ref": "component:default/web-frontend",
                           "context_hash": "sha256:" + "0" * 64, "edges": [], "truncated": {}})
    assert _common.load_service_context(tmp_path) is None
    (out / "context.json").write_text(doc("failed"))
    assert _common.load_service_context(tmp_path) is None
    (out / "context.json").write_text(doc("stale"))
    assert _common.load_service_context(tmp_path)["status"] == "stale"


import json
import subprocess
from datetime import datetime, timedelta, timezone

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


@pytest.fixture
def trusted(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv(context.TRUST_ENV, "1")


@pytest.fixture
def untrusted(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv(context.TRUST_ENV, raising=False)


def test_fresh_fetch_writes_context_json(context_repo, trusted):
    doc = context.run(context_repo, now=NOW)
    assert doc["status"] == "fresh"
    assert doc["schema"] == "thunderstruck.context/v1"
    assert doc["fetched_at"] == "2026-09-23T00:00:00+00:00"
    assert doc["context_hash"].startswith("sha256:")
    on_disk = json.loads((context_repo / ".thunderstruck" / "context.json").read_text())
    assert on_disk == doc
    raw = context_repo / ".thunderstruck" / "context" / "raw"
    assert (raw / "component_default_fixture-app.json").is_file()


def test_not_configured_and_disabled_are_silent(tmp_path, trusted):
    doc = context.run(tmp_path, now=NOW)
    assert doc["status"] == "not_configured" and doc["warnings"] == []
    (tmp_path / ".thunderstruck.toml").write_text("[context]\nenabled = false\n")
    doc = context.run(tmp_path, now=NOW)
    assert doc["status"] == "disabled" and doc["warnings"] == []


def test_invalid_config_warns(tmp_path, trusted):
    (tmp_path / ".thunderstruck.toml").write_text('[context]\nentity_ref = "nope"\n')
    doc = context.run(tmp_path, now=NOW)
    assert doc["status"] == "invalid_config"
    assert any("entity_ref" in w for w in doc["warnings"])


def test_untrusted_source_never_runs(context_repo, untrusted, monkeypatch, tmp_path):
    marker = tmp_path / "calls.txt"
    monkeypatch.setenv("FAKE_CATALOG_MARKER", str(marker))
    doc = context.run(context_repo, now=NOW)
    assert doc["status"] == "untrusted"
    assert "/thunderstruck-context-config" in doc["warnings"][0]
    assert not marker.exists()


def _definition_hash(repo):
    return context.current_definition(repo)[1]


def test_approval_unlocks_and_a_changed_command_relocks(context_repo, untrusted):
    context.approve_config(context_repo, _definition_hash(context_repo))
    assert context.run(context_repo, now=NOW)["status"] == "fresh"
    profile = context_repo / ".thunderstruck.toml"
    profile.write_text(profile.read_text().replace("timeout_s = 10", "timeout_s = 11"))
    assert context.run(context_repo, now=NOW)["status"] == "untrusted"


def test_cache_is_reused_without_running_anything(context_repo, trusted, monkeypatch):
    first = context.run(context_repo, now=NOW)
    monkeypatch.setenv("FAKE_CATALOG_FAIL_REFS", MAIN)
    second = context.run(context_repo, now=NOW + timedelta(days=29))
    assert second["status"] == "cached"
    assert second["context_hash"] == first["context_hash"]
    assert second["fetched_at"] == first["fetched_at"]


def test_refresh_ignores_the_cache(context_repo, trusted):
    context.run(context_repo, now=NOW)
    doc = context.run(context_repo, now=NOW + timedelta(days=1), refresh=True)
    assert doc["status"] == "fresh" and doc["fetched_at"].startswith("2026-09-24")


def test_expired_cache_is_refetched(context_repo, trusted):
    context.run(context_repo, now=NOW)
    assert context.run(context_repo, now=NOW + timedelta(days=30))["status"] == "fresh"


def test_failed_refresh_falls_back_to_the_stale_cache(context_repo, trusted, monkeypatch):
    first = context.run(context_repo, now=NOW)
    monkeypatch.setenv("FAKE_CATALOG_AUTH", "expired")
    doc = context.run(context_repo, now=NOW + timedelta(days=34))
    assert doc["status"] == "stale"
    assert doc["edges"] == first["edges"] and doc["context_hash"] == first["context_hash"]
    assert doc["warnings"][0].startswith(
        "service context is 34 days old; refresh failed: preflight failed:")
    again = context.run(context_repo, now=NOW + timedelta(days=35))
    assert sum("days old" in w for w in again["warnings"]) == 1


def test_stale_fallback_ends_at_twice_max_age(context_repo, trusted, monkeypatch):
    context.run(context_repo, now=NOW)
    monkeypatch.setenv("FAKE_CATALOG_AUTH", "expired")
    doc = context.run(context_repo, now=NOW + timedelta(days=60))
    assert doc["status"] == "failed" and doc["edges"] == []
    assert doc["warnings"][0].startswith("service context unavailable: preflight failed")


def test_stale_fallback_never_crosses_a_definition_change(context_repo, trusted, monkeypatch):
    context.run(context_repo, now=NOW)
    profile = context_repo / ".thunderstruck.toml"
    profile.write_text(profile.read_text().replace("fixture-app", "other-app"))
    monkeypatch.setenv("FAKE_CATALOG_AUTH", "expired")
    assert context.run(context_repo, now=NOW + timedelta(days=1))["status"] == "failed"


def test_invalid_toml_is_not_fatal_and_overwrites_the_cache(context_repo, trusted):
    first = context.run(context_repo, now=NOW)
    assert first["status"] == "fresh"
    profile = context_repo / ".thunderstruck.toml"
    profile.write_text(profile.read_text() + "[context\n")
    doc = context.run(context_repo, now=NOW)
    assert doc["status"] == "invalid_config"
    assert any("service context config:" in w for w in doc["warnings"])
    on_disk = json.loads((context_repo / ".thunderstruck" / "context.json").read_text())
    assert on_disk["status"] == "invalid_config" and on_disk["edges"] == []


@pytest.mark.parametrize("mutation", [
    lambda doc: doc.__setitem__("warnings", 5),
    lambda doc: doc.__setitem__("edges", ["junk"]),
])
def test_junk_cache_is_not_reused(context_repo, trusted, mutation):
    context.run(context_repo, now=NOW)
    path = context_repo / ".thunderstruck" / "context.json"
    doc = json.loads(path.read_text())
    mutation(doc)
    path.write_text(json.dumps(doc))
    assert context.run(context_repo, now=NOW)["status"] == "fresh"


def test_corrupt_context_json_is_not_fatal(context_repo, trusted):
    context.run(context_repo, now=NOW)
    path = context_repo / ".thunderstruck" / "context.json"
    path.write_bytes(b"\xff\xfe")
    assert context.run(context_repo, now=NOW)["status"] == "fresh"


@pytest.mark.parametrize("fetched_at,expected", [
    ("2026-10-30T00:00:00+00:00", "cached"),   # in the future: clock skew
    ("not a date", "fresh"),
    ("2026-09-20T00:00:00", "fresh"),          # no timezone
])
def test_odd_timestamps(context_repo, trusted, fetched_at, expected):
    context.run(context_repo, now=NOW)
    path = context_repo / ".thunderstruck" / "context.json"
    doc = json.loads(path.read_text())
    doc["fetched_at"] = fetched_at
    path.write_text(json.dumps(doc))
    assert context.run(context_repo, now=NOW)["status"] == expected


def _cli(repo, *args, env=None):
    return subprocess.run([sys.executable, str(SCRIPTS / "context.py"), "--repo", str(repo),
                           *args], capture_output=True, text=True, env=env,
                          stdin=subprocess.DEVNULL, timeout=60)


def test_cli_reports_status_and_warnings(context_repo, tmp_path):
    env = {**os.environ, "THUNDERSTRUCK_TRUST_CONTEXT": "1",
           "XDG_CONFIG_HOME": str(tmp_path / "xdg")}
    proc = _cli(context_repo, env=env)
    assert proc.returncode == 0, proc.stderr
    assert "service context: fresh — 4 edge(s) for component:default/fixture-app" in proc.stdout
    assert "warning: attribute value rejected" in proc.stdout


def test_cli_never_prompts_without_config(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    proc = _cli(tmp_path)
    assert proc.returncode == 0 and "service context: not_configured" in proc.stdout


def test_cli_detects_the_entity(context_repo):
    proc = _cli(context_repo, "--detect-entity")
    assert proc.returncode == 0 and proc.stdout.strip() == "component:default/fixture-app"


def _untrusted_env(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "THUNDERSTRUCK_TRUST_CONTEXT"}
    env["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")
    return env


def _shown_hash(stdout):
    return next(line.split()[-1] for line in stdout.splitlines()
                if line.strip().startswith("definition "))


def test_cli_show_prints_the_definition_without_side_effects(context_repo, tmp_path):
    proc = _cli(context_repo, "--show", env=_untrusted_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "argv:" in proc.stdout and "preflight:" in proc.stdout
    assert _shown_hash(proc.stdout) == _definition_hash(context_repo)
    assert not (tmp_path / "xdg").exists()
    assert not (context_repo / ".thunderstruck" / "context.json").exists()


def test_cli_approve_records_trust_for_the_shown_hash(context_repo, tmp_path):
    env = _untrusted_env(tmp_path)
    shown = _shown_hash(_cli(context_repo, "--show", env=env).stdout)
    proc = _cli(context_repo, "--approve", "--expect", shown, env=env)
    assert proc.returncode == 0, proc.stderr
    assert "argv:" in proc.stdout
    assert (tmp_path / "xdg" / "thunderstruck" / "trusted-sources.json").is_file()
    assert "fresh" in _cli(context_repo, env=env).stdout


@pytest.mark.parametrize("expect", [[], ["--expect", "sha256:" + "0" * 64]])
def test_cli_approve_refuses_without_the_shown_hash(context_repo, tmp_path, expect):
    env = _untrusted_env(tmp_path)
    proc = _cli(context_repo, "--approve", *expect, env=env)
    assert proc.returncode == 2
    assert "--show" in proc.stderr
    assert not (tmp_path / "xdg" / "thunderstruck" / "trusted-sources.json").exists()
    assert "untrusted" in _cli(context_repo, env=env).stdout


def test_editing_a_repo_local_script_relocks(context_repo, untrusted):
    wrapper = context_repo / "bin" / "catalog.py"
    wrapper.parent.mkdir()
    wrapper.write_text(f"import runpy, sys\nsys.argv[0] = {str(FAKE)!r}\n"
                       f"runpy.run_path({str(FAKE)!r}, run_name='__main__')\n")
    profile = context_repo / ".thunderstruck.toml"
    profile.write_text(profile.read_text().replace(json.dumps(str(FAKE)), '"bin/catalog.py"'))
    assert '"bin/catalog.py"' in profile.read_text()
    context.approve_config(context_repo, _definition_hash(context_repo))
    assert context.run(context_repo, now=NOW)["status"] == "fresh"
    wrapper.write_text(wrapper.read_text() + "# changed after approval\n")
    assert context.run(context_repo, now=NOW)["status"] == "untrusted"
