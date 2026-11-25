"""Every planted drift case in the context fixture is reported, and no negative is (#6)."""

from __future__ import annotations

import json

import _common as c


def doc_of(repo):
    doc = c.load_observed(repo)
    assert doc is not None
    return doc


def test_planted_resolutions(context_scanned_repo):
    doc = doc_of(context_scanned_repo)
    res = {(r["kind"], r["value"]): r for r in doc["resolutions"]}
    want = {
        ("env", "RELEASES_API_URL"): ("documented", "component:default/releases-api", "name"),
        ("env", "FX_RATES_URL"): ("unmatched", None, None),
        ("env", "LEDGER_ADDR"): ("mapped_undocumented", "component:default/ledger", "map"),
        ("env", "REPORTING_JOB_URL"): ("dependent_only", "component:default/reporting-job", "name"),
        ("env", "ANALYTICS_COLLECTOR_URL"): ("ignored", None, None),
        ("secret", "secret/data/search-api"): ("documented", "component:default/search-api", "name"),
    }
    assert {k: (r["resolution"], r["entity"], r["via"]) for k, r in res.items()} == want
    assert res[("env", "RELEASES_API_URL")]["edge"] == "dependsOn component:default/releases-api"


def test_planted_edge_lists(context_scanned_repo):
    doc = doc_of(context_scanned_repo)
    assert doc["not_observed"] == ["dependsOn component:default/legacy-billing"]
    assert doc["no_mapping"] == ["dependsOn component:default/payments-api",
                                 "dependsOn resource:default/orders-db"]
    assert doc["ignored"] == [{"rule": "env ANALYTICS_COLLECTOR_URL",
                               "reason": "third-party analytics; tracked outside the catalog",
                               "hits": 1}]
    assert doc["excluded"] == {"own_host": 0} and doc["own_hosts_known"] is True


def test_no_negative_is_observed(context_scanned_repo):
    blob = json.dumps(doc_of(context_scanned_repo))
    for host in ("api.example.com", "legacy.example.com", "fixture-app.internal"):
        assert host not in blob


def test_the_plain_fixture_is_untouched(scanned_repo):
    assert not (scanned_repo / ".thunderstruck" / "observed.json").exists()
    assert c.load_observed(scanned_repo) is None
