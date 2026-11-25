"""Matching observations to the catalog: ignore, then map, then exact name (#6, spec §3, §4)."""

from __future__ import annotations

import pytest

import observed


@pytest.fixture(scope="module")
def rules():
    return observed.load_rules()


def edge(ref: str, direction: str = "outbound") -> dict:
    rtype, neighbour = ref.split(" ")
    return {"ref": ref, "type": rtype, "direction": direction, "neighbour": neighbour,
            "attributes": {}}


def obs(kind: str, value: str, file: str = "src/a.ts", line: int = 1) -> dict:
    return {"kind": kind, "value": value, "file": file, "line": line}


def cfg(map_=(), ignore=()) -> dict:
    loaded, warnings = observed.load_config({"observed": {"map": list(map_), "ignore": list(ignore)}})
    assert warnings == []
    return loaded


def by_value(result: dict) -> dict:
    return {(r["kind"], r["value"]): r for r in result["resolutions"]}


EDGES = [edge("dependsOn component:default/payments-api"),
         edge("dependsOn component:default/ledger"),
         edge("dependsOn resource:default/orders-db"),
         edge("dependencyOf component:default/reporting-job", "inbound")]


def test_ignore_beats_map_and_map_beats_name(rules):
    conf = cfg(map_=[{"entity": "component:default/ledger", "env": ["PAYMENTS_API_URL"]}],
               ignore=[{"env": "LEDGER_ADDR", "reason": "vendor"}])
    conf["map"].append({"entity": "component:default/ledger", "host": [], "env": ["LEDGER_ADDR"],
                        "secret": []})
    got = observed.resolve([obs("env", "PAYMENTS_API_URL"), obs("env", "LEDGER_ADDR")],
                           EDGES, conf, rules)
    res = by_value(got)
    assert res[("env", "PAYMENTS_API_URL")]["resolution"] == "documented"
    assert res[("env", "PAYMENTS_API_URL")]["entity"] == "component:default/ledger"
    assert res[("env", "PAYMENTS_API_URL")]["via"] == "map"
    assert res[("env", "LEDGER_ADDR")]["resolution"] == "ignored"
    assert got["ignored"] == [{"rule": "env LEDGER_ADDR", "reason": "vendor", "hits": 1}]


@pytest.mark.parametrize("kind,value,name", [
    ("host", "payments-api.prod.svc.cluster.local", "payments-api"),
    ("host", "payments.internal", "payments"),
    ("host", "api.vendor.internal", None),
    ("host", "www.vendor.internal", None),
    ("env", "PAYMENTS_API_URL", "payments-api"),
    ("env", "CART_ADDR", "cart"),
    ("env", "DB_CONNECT", "db"),
    ("env", "SEARCH_HOSTNAME", "search"),
    ("env", "LEDGER_ADDRESS", "ledger-address"),
    ("env", "AUTH", "auth"),
    ("secret", "secret/data/Payments-API", "payments-api"),
    ("secret", "ledger", "ledger"),
])
def test_match_name(rules, kind, value, name):
    assert observed.match_name(kind, value, rules) == name


def test_exact_name_only(rules):
    got = observed.resolve([obs("host", "payments-api.prod.svc.cluster.local"),
                            obs("host", "payments.internal"),
                            obs("host", "api.vendor.internal")],
                           EDGES + [edge("dependsOn component:default/api")], cfg(), rules)
    res = by_value(got)
    assert res[("host", "payments-api.prod.svc.cluster.local")] == {
        "kind": "host", "value": "payments-api.prod.svc.cluster.local",
        "resolution": "documented", "entity": "component:default/payments-api",
        "edge": "dependsOn component:default/payments-api", "via": "name", "occurrences": 1}
    assert res[("host", "payments.internal")]["resolution"] == "unmatched"
    assert res[("host", "api.vendor.internal")]["resolution"] == "unmatched"


def test_dependent_only_and_mapped_undocumented(rules):
    conf = cfg(map_=[{"entity": "component:default/fx", "hosts": ["fx.internal"]}])
    got = observed.resolve([obs("env", "REPORTING_JOB_URL"), obs("host", "fx.internal"),
                            obs("host", "fx.internal", line=2)], EDGES, conf, rules)
    res = by_value(got)
    assert res[("env", "REPORTING_JOB_URL")]["resolution"] == "dependent_only"
    assert res[("env", "REPORTING_JOB_URL")]["edge"] == "dependencyOf component:default/reporting-job"
    fx = res[("host", "fx.internal")]
    assert (fx["resolution"], fx["entity"], fx["edge"], fx["via"], fx["occurrences"]) == \
        ("mapped_undocumented", "component:default/fx", None, "map", 2)


def test_ambiguous_names_match_neither(rules):
    edges = [edge("dependsOn component:a/ledger"), edge("dependsOn component:b/ledger"),
             edge("dependsOn component:default/billing")]
    got = observed.resolve([obs("env", "LEDGER_ADDR")], edges, cfg(), rules)
    led = by_value(got)[("env", "LEDGER_ADDR")]
    assert led["resolution"] == "ambiguous" and led["entity"] is None
    assert led["candidates"] == ["dependsOn component:a/ledger", "dependsOn component:b/ledger"]
    assert got["not_observed"] == []
    assert got["no_mapping"] == ["dependsOn component:default/billing"]


def test_not_observed_versus_no_mapping(rules):
    conf = cfg(map_=[{"entity": "component:default/ledger", "hosts": ["ledger.internal"]}])
    got = observed.resolve([obs("env", "PAYMENTS_API_URL")], EDGES, conf, rules)
    assert got["not_observed"] == ["dependsOn component:default/ledger"]
    assert got["no_mapping"] == ["dependsOn resource:default/orders-db"]
    assert "dependsOn component:default/payments-api" not in got["not_observed"] + got["no_mapping"]


def test_ignore_rules_count_hits_and_wildcards(rules):
    conf = cfg(ignore=[{"host": "*.vendor.internal", "reason": "third party"},
                       {"secret": "unused/path", "reason": "kept for later"}])
    got = observed.resolve([obs("host", "a.vendor.internal"), obs("host", "a.vendor.internal", line=3),
                            obs("host", "vendor.internal")], EDGES, conf, rules)
    res = by_value(got)
    assert res[("host", "a.vendor.internal")]["resolution"] == "ignored"
    assert res[("host", "vendor.internal")]["resolution"] == "unmatched"
    assert got["ignored"] == [
        {"rule": "host *.vendor.internal", "reason": "third party", "hits": 2},
        {"rule": "secret unused/path", "reason": "kept for later", "hits": 0}]


def test_resolutions_are_sorted(rules):
    got = observed.resolve([obs("host", "b.internal"), obs("env", "Z_URL"), obs("host", "a.internal")],
                           EDGES, cfg(), rules)
    assert [(r["kind"], r["value"]) for r in got["resolutions"]] == \
        [("env", "Z_URL"), ("host", "a.internal"), ("host", "b.internal")]


@pytest.mark.parametrize("profile,fragment", [
    ({"map": [{"entity": "not a ref", "env": ["X_URL"]}]}, "[[observed.map]] entry 2"),
    ({"map": [{"entity": "component:default/a", "env": ["X_URL"]},
              {"entity": "component:default/b", "env": ["X_URL"]}]}, "[[observed.map]] entry 3"),
    ({"map": [{"entity": "component:default/a", "env": ["lower"]}]}, "[[observed.map]] entry 2"),
    ({"ignore": [{"host": "a.internal", "env": "X_URL", "reason": "r"}]}, "[[observed.ignore]] entry 2"),
    ({"ignore": [{"host": "a.internal"}]}, "[[observed.ignore]] entry 2"),
    ({"ignore": [{"host": "a.internal", "reason": "  "}]}, "[[observed.ignore]] entry 2"),
    ({"own_hosts_annotation": 5}, "own_hosts_annotation"),
])
def test_an_invalid_entry_is_dropped_with_one_warning(profile, fragment):
    good_map = {"entity": "component:default/keep", "env": ["KEEP_URL"]}
    good_ignore = {"env": "SKIP_URL", "reason": "r"}
    raw = {"map": [good_map, *profile.get("map", [])],
           "ignore": [good_ignore, *profile.get("ignore", [])]}
    if "own_hosts_annotation" in profile:
        raw["own_hosts_annotation"] = profile["own_hosts_annotation"]
    loaded, warnings = observed.load_config({"observed": raw})
    # the good entries come first, so the bad one's number is shifted by one
    assert len(warnings) == 1 and fragment in warnings[0], warnings
    assert {"entity": "component:default/keep", "host": [], "env": ["KEEP_URL"], "secret": []} \
        in loaded["map"]
    assert {"kind": "env", "value": "SKIP_URL", "reason": "r"} in loaded["ignore"]
    assert loaded["own_hosts_annotation"] == "thunderstruck.io/own-hosts"


def test_map_hash_is_stable_and_covers_map_and_ignore():
    a = cfg(map_=[{"entity": "component:default/a", "env": ["A_URL"]}])
    b = cfg(map_=[{"entity": "component:default/a", "env": ["A_URL"]}])
    c_ = cfg(map_=[{"entity": "component:default/a", "env": ["B_URL"]}])
    assert observed.map_hash(a) == observed.map_hash(b) != observed.map_hash(c_)
    assert observed.map_hash(a).startswith("sha256:")


def test_no_observed_table_is_an_empty_config():
    assert observed.load_config({}) == ({"own_hosts_annotation": "thunderstruck.io/own-hosts",
                                        "map": [], "ignore": []}, [])


def test_an_ignore_reason_is_capped():
    loaded, warnings = observed.load_config({"observed": {"ignore": [
        {"env": "A_URL", "reason": "x" * 201}, {"env": "B_URL", "reason": "y" * 200}]}})
    assert [r["value"] for r in loaded["ignore"]] == ["B_URL"]
    assert len(warnings) == 1 and "200" in warnings[0]
