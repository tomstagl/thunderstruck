"""The service's own hosts come from one annotation on its own catalog entry (#6, spec §2.6)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import _common as c
import context
from context_extract import context_hash, extract_own_hosts

NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


@pytest.fixture
def trusted(monkeypatch, tmp_path):
    for var in ("FAKE_CATALOG_OWN_HOSTS", "FAKE_CATALOG_OWN_HOSTS_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv(context.TRUST_ENV, "1")


def entity(value):
    return {"metadata": {"annotations": {"thunderstruck.io/own-hosts": value}}}


def test_extract_own_hosts_sorts_dedupes_and_counts_rejects():
    hosts, bad = extract_own_hosts(entity("Shop.Internal., *.api.shop.internal, shop.internal"),
                                   "thunderstruck.io/own-hosts")
    assert hosts == ["*.api.shop.internal", "shop.internal"] and bad == 0
    assert extract_own_hosts(entity("shop.internal, not a host!, *.*.x"),
                             "thunderstruck.io/own-hosts") == (["shop.internal"], 2)
    assert extract_own_hosts({}, "thunderstruck.io/own-hosts") == ([], 0)
    assert extract_own_hosts(entity(42), "thunderstruck.io/own-hosts") == ([], 1)


def test_annotation_writes_own_hosts(context_repo, trusted, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_OWN_HOSTS", "shop.internal, *.api.shop.internal")
    doc = context.run(context_repo, now=NOW)
    assert doc["status"] == "fresh"
    assert doc["own_hosts"] == ["*.api.shop.internal", "shop.internal"]
    assert doc["context_hash"] == context_hash(doc["entity_ref"], doc["edges"], doc["truncated"],
                                               doc["own_hosts"])
    assert doc["context_hash"] != context_hash(doc["entity_ref"], doc["edges"], doc["truncated"])
    assert c.load_service_context(context_repo)["own_hosts"] == doc["own_hosts"]


def test_a_bad_entry_is_dropped_without_echoing_it(context_repo, trusted, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_OWN_HOSTS", "shop.internal, Evil Value!")
    doc = context.run(context_repo, now=NOW)
    assert doc["own_hosts"] == ["shop.internal"]
    warned = [w for w in doc["warnings"] if "thunderstruck.io/own-hosts" in w]
    assert len(warned) == 1
    assert "evil value" not in json.dumps(doc).lower()


def test_no_annotation_means_no_field_and_the_same_hash(context_repo, trusted, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_OWN_HOSTS", "")
    doc = context.run(context_repo, now=NOW)
    assert "own_hosts" not in doc
    assert doc["context_hash"] == context_hash(doc["entity_ref"], doc["edges"], doc["truncated"])


def test_the_profile_names_the_annotation_without_changing_config_hash(context_repo, trusted,
                                                                      monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_OWN_HOSTS", "shop.internal")
    monkeypatch.setenv("FAKE_CATALOG_OWN_HOSTS_KEY", "example.com/hosts")
    before, _ = context.current_definition(context_repo)
    chash_before = context.config_hash(before, context_repo)
    doc = context.run(context_repo, now=NOW)
    assert "own_hosts" not in doc
    profile = context_repo / ".thunderstruck.toml"
    profile.write_text(profile.read_text() + '\n[observed]\nown_hosts_annotation = "example.com/hosts"\n')
    after, _ = context.current_definition(context_repo)
    assert context.config_hash(after, context_repo) == chash_before
    doc = context.run(context_repo, now=NOW, refresh=True)
    assert doc["own_hosts"] == ["shop.internal"]


def test_a_cached_document_keeps_its_own_hosts(context_repo, trusted, monkeypatch):
    monkeypatch.setenv("FAKE_CATALOG_OWN_HOSTS", "shop.internal")
    first = context.run(context_repo, now=NOW)
    second = context.run(context_repo, now=NOW)
    assert second["status"] == "cached"
    assert second["own_hosts"] == ["shop.internal"]
    assert second["context_hash"] == first["context_hash"]
    tampered = {**first, "own_hosts": ["other.internal"]}
    assert not context._reusable(tampered, first["config_hash"])


def test_load_service_context_checks_own_hosts(tmp_path):
    base = {"schema": c.CONTEXT_SCHEMA, "status": "fresh",
            "entity_ref": "component:default/a", "context_hash": "sha256:" + "0" * 64,
            "edges": [], "truncated": {"inbound": 0, "outbound": 0}}
    path = tmp_path / ".thunderstruck" / c.CONTEXT_FILENAME
    for own, ok in ((["shop.internal", "*.api.shop.internal"], True), ("shop.internal", False),
                    ([1], False), (["not a host"], False)):
        c.write_json(path, {**base, "own_hosts": own})
        assert (c.load_service_context(tmp_path) is not None) is ok, own
