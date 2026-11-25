"""The Catalog drift report section (#6, spec §8; AC-3 to AC-6, AC-10, AC-12)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import _common as c
import report
from test_context_pipeline import _report

HEADING = "## Catalog drift"


def drift_md(md: str) -> str:
    start = md.index(HEADING)
    end = md.find("\n## ", start + 1)
    return md[start:] if end < 0 else md[start:end]


@pytest.fixture(scope="module")
def reported(context_scanned_repo, plugin_root, tmp_path_factory):
    import shutil
    repo = tmp_path_factory.mktemp("drift") / "repo"
    shutil.copytree(context_scanned_repo, repo, symlinks=True)
    md, payload, index = _report(repo, plugin_root)
    return repo, md, payload, index


def test_the_section_follows_service_context(reported):
    _, md, _, _ = reported
    assert md.index("## Service context") < md.index(HEADING)
    between = md[md.index("## Service context"):md.index(HEADING)]
    assert between.count("\n## ") == 0
    text = drift_md(md)
    assert ("Compares the dependencies this scan observed in the code and configuration with "
            "the service catalog. These are leads to check, not findings.") in text
    for gap in ("configuration tables", "more than one variable or across files",
                "vendor SDK clients"):
        assert gap in text


def test_observed_not_in_the_catalog(reported):
    repo, md, payload, _ = reported
    text = drift_md(md)
    block = text.split("**Observed, not in the catalog** (2)", 1)[1].split("\n\n**", 1)[0]
    assert "| env | `FX_RATES_URL` |" in block
    assert "| env | `LEDGER_ADDR` (declared as `component:default/ledger`) |" in block
    fx = next(o for o in c.load_observed(repo)["observations"] if o["value"] == "FX_RATES_URL")
    assert f"{fx['file']}:{fx['line']}" in block
    rows = {r["value"]: r for r in payload["catalog_drift"]["observed_not_documented"]}
    assert rows["FX_RATES_URL"]["occurrences"] == 1
    assert rows["FX_RATES_URL"]["where"][0]["file"] == "src/sync/collection.ts"


def test_dependent_only_not_observed_and_no_mapping(reported):
    _, md, payload, _ = reported
    text = drift_md(md)
    assert "**Documented only as a dependent** (1)" in text and "`REPORTING_JOB_URL`" in text
    assert ("- `dependsOn component:default/legacy-billing`: none of its mapped values appear "
            "in the scanned files. It may be called through a shared client library, "
            "generated code or configuration outside this repository.") in text
    assert ("- `dependsOn resource:default/orders-db`: no observation could be linked to it, "
            "so this scan can't tell whether the code uses it. An `[[observed.map]]` entry "
            "naming its hosts, env vars or secrets would let it tell.") in text
    drift = payload["catalog_drift"]
    assert drift["not_observed"] == ["dependsOn component:default/legacy-billing"]
    assert "dependsOn resource:default/orders-db" in drift["no_mapping"]


def test_ignored_rules_are_printed_with_hits(reported):
    _, md, _, _ = reported
    assert ("- env `ANALYTICS_COLLECTOR_URL` — third-party analytics; tracked outside the "
            "catalog (1 hits)") in drift_md(md)


def test_own_hosts_never_appear(reported):
    _, md, payload, _ = reported
    assert "fixture-app.internal" not in md
    assert "fixture-app.internal" not in json.dumps(payload)
    assert "own hosts are unknown" not in drift_md(md)
    assert payload["catalog_drift"]["own_hosts_known"] is True


def test_index_json_does_not_change(reported):
    _, _, _, index = reported
    assert "catalog_drift" not in index and "observed" not in json.dumps(index)


def doc(**over) -> dict:
    base = {"observations": [], "resolutions": [], "not_observed": [], "no_mapping": [],
            "ignored": [], "own_hosts_known": True,
            "truncated": {"observations": 0, "catalog_edges": 0}, "warnings": []}
    return {**base, **over}


def obs(value: str, line: int, file: str = "src/a.ts") -> dict:
    return {"ref": f"observed env:{value} {file}:{line}", "kind": "env", "value": value,
            "file": file, "line": line}


def test_ambiguous_values_have_their_own_list():
    d = doc(observations=[obs("LEDGER_ADDR", 3)], resolutions=[
        {"kind": "env", "value": "LEDGER_ADDR", "resolution": "ambiguous", "entity": None,
         "edge": None, "via": None, "occurrences": 1,
         "candidates": ["dependsOn component:a/ledger", "dependsOn component:b/ledger"]}],
        no_mapping=["dependsOn component:default/billing"])
    text = "\n".join(report.render_catalog_drift(report.catalog_drift(d)))
    assert "**Ambiguous** (1)" in text
    assert "`dependsOn component:a/ledger`, `dependsOn component:b/ledger`" in text
    no_mapping = text.split("**No mapping declared** (1)", 1)[1]
    assert "billing" in no_mapping and "ledger" not in no_mapping.split("\n\n**", 1)[0]
    assert "**Documented, not observed**" not in text


def test_unknown_own_hosts_partial_scan_and_truncation_notes():
    d = doc(own_hosts_known=False, truncated={"observations": 0, "catalog_edges": 3},
            warnings=["observed dependencies: stopped after 2 files (--limit); 1 more were not "
                      "read, so the drift section is partial"])
    text = "\n".join(report.render_catalog_drift(report.catalog_drift(d)))
    assert "own hosts are unknown" in text
    assert "25 per direction" in text
    assert "partial" in text


def test_more_than_three_locations_show_plus_n():
    many = [obs("FX_URL", n) for n in range(1, 6)]
    d = doc(observations=many, resolutions=[
        {"kind": "env", "value": "FX_URL", "resolution": "unmatched", "entity": None,
         "edge": None, "via": None, "occurrences": 7}])
    text = "\n".join(report.render_catalog_drift(report.catalog_drift(d)))
    row = next(line for line in text.splitlines() if "`FX_URL`" in line)
    assert row.count("src/a.ts:") == 3 and "+4" in row and row.endswith("| 7 |")


def test_no_context_means_no_section(scanned_copy, plugin_root):
    md, payload, _ = _report(scanned_copy, plugin_root)
    assert HEADING not in md
    assert payload["catalog_drift"] is None
    assert report.render_catalog_drift(None) == []
    assert report.catalog_drift(None) is None
