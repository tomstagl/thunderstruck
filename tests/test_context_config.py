"""The [context] contract and the trust gate. A committed command is code
execution, so nothing runs until it is approved on this machine."""

from __future__ import annotations

import json
import tomllib

import pytest

import context


def source(**overrides):
    base = {"name": "catalog", "kind": "command",
            "argv": ["catalogctl", "get", "entity", "{entity_ref}", "-o", "json"],
            "extractor": "backstage-relations",
            "edge_types": {"dependsOn": "outbound", "dependencyOf": "inbound"}}
    base.update(overrides)
    return base


def profile(**overrides):
    ctx = {"entity_ref": "component:default/checkout", "sources": [source()]}
    ctx.update(overrides)
    return {"context": ctx}


def test_absent_table_is_not_configured():
    assert context.load_config({}) == (None, [])


def test_valid_config_is_normalised():
    cfg, errors = context.load_config(profile())
    assert errors == []
    assert cfg["enabled"] is True and cfg["max_age_days"] == 30
    src = cfg["sources"][0]
    assert src["preflight"] == [] and src["timeout_s"] == 20
    assert src["neighbour_attributes"] == {}


def test_declined_config_needs_nothing_else():
    cfg, errors = context.load_config({"context": {"enabled": False}})
    assert errors == [] and cfg["enabled"] is False


@pytest.mark.parametrize("overrides,expected", [
    ({"entity_ref": "checkout"}, "entity_ref"),
    ({"max_age_days": 0}, "max_age_days"),
    ({"sources": []}, "at least one"),
    ({"sources": [source(), source(name="second")]}, "one source"),
    ({"sources": [source(kind="mcp")]}, "kind"),
    ({"sources": [source(argv="catalogctl get")]}, "argv"),
    ({"sources": [source(preflight=[])]}, "preflight"),
    ({"sources": [source(timeout_s=600)]}, "timeout_s"),
    ({"sources": [source(extractor="jq")]}, "extractor"),
    ({"sources": [source(edge_types={"dependsOn": "sideways"})]}, "edge_types"),
    ({"sources": [source(neighbour_attributes={"Tier Label": "x"})]}, "neighbour_attributes"),
    ({"sources": [source(neighbour_attributes={"tier\n": "x"})]}, "neighbour_attributes"),
    ({"enabled": "yes"}, "enabled"),
])
def test_invalid_config_names_the_problem(overrides, expected):
    _, errors = context.load_config(profile(**overrides))
    assert any(expected in e for e in errors), errors


def test_non_table_context_is_invalid():
    cfg, errors = context.load_config({"context": "on"})
    assert cfg is None and errors


def test_config_hash_ignores_cache_lifetime():
    a, _ = context.load_config(profile())
    b, _ = context.load_config(profile(max_age_days=7))
    assert context.config_hash(a) == context.config_hash(b)


def test_config_hash_changes_with_the_command():
    a, _ = context.load_config(profile())
    b, _ = context.load_config(profile(sources=[source(argv=["othercli", "{entity_ref}"])]))
    assert context.config_hash(a) != context.config_hash(b)


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv(context.TRUST_ENV, raising=False)
    return tmp_path / "xdg"


def test_nothing_is_trusted_by_default(xdg, tmp_path):
    assert not context.is_trusted(tmp_path, "sha256:abc")


def test_approval_is_per_repo_and_per_definition(xdg, tmp_path):
    repo_a, repo_b = tmp_path / "a", tmp_path / "b"
    path = context.approve(repo_a, "sha256:abc")
    assert path == xdg / "thunderstruck" / "trusted-sources.json"
    assert context.is_trusted(repo_a, "sha256:abc")
    assert not context.is_trusted(repo_a, "sha256:def")
    assert not context.is_trusted(repo_b, "sha256:abc")


def test_approving_twice_keeps_one_entry_per_key(xdg, tmp_path):
    context.approve(tmp_path / "a", "sha256:1")
    context.approve(tmp_path / "b", "sha256:2")
    context.approve(tmp_path / "a", "sha256:1")
    store = json.loads((xdg / "thunderstruck" / "trusted-sources.json").read_text())
    assert len(store["trusted"]) == 2


def test_ci_override_trusts_everything(xdg, tmp_path, monkeypatch):
    monkeypatch.setenv(context.TRUST_ENV, "1")
    assert context.is_trusted(tmp_path, "sha256:anything")


def test_example_profile_context_is_valid(plugin_root):
    with (plugin_root / "examples" / "thunderstruck.toml.example").open("rb") as fh:
        cfg, errors = context.load_config(tomllib.load(fh))
    assert errors == [] and cfg is not None and cfg["enabled"] is True
