"""Observed dependencies through the pipeline: bundles (AC-1, AC-10, AC-11) and
validation (AC-2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import _common as c
import bundle

HEADING = "## Dependencies observed in this file"


def index_of(repo: Path) -> dict:
    return json.loads((repo / ".thunderstruck" / "bundles" / "index.json").read_text())


def bundle_for(repo: Path, rel: str) -> tuple[str, str]:
    for entry in index_of(repo)["bundles"]:
        if entry["file"] == rel:
            return entry["id"], Path(entry["bundle"]).read_text()
    raise AssertionError(f"no bundle for {rel}")


def section(body: str) -> str:
    start = body.index(HEADING)
    end = body.find("\n## ", start + 1)
    return body[start:] if end < 0 else body[start:end]


def ref_of(repo: Path, value: str) -> str:
    doc = c.load_observed(repo)
    return next(o["ref"] for o in doc["observations"] if o["value"] == value)


# ---------------------------------------------------------------- bundles --

def test_a_hotspot_is_briefed_with_its_own_calls(context_scanned_repo):
    hid, body = bundle_for(context_scanned_repo, "src/client/releases.ts")
    assert hid == "H01"
    service_end = body.index("## Service context")
    assert body.index(HEADING) > service_end
    after_service = body[service_end:].split("\n## ", 2)[1]
    assert after_service.startswith(HEADING[3:])
    ref = ref_of(context_scanned_repo, "RELEASES_API_URL")
    assert (f"- `{ref}` → documented: `dependsOn component:default/releases-api` "
            "(matched by name)") in section(body)
    assert "Cite one as `observed`" in section(body)


def test_mapped_unmatched_and_ignored_wording(context_scanned_repo):
    _, body = bundle_for(context_scanned_repo, "src/sync/collection.ts")
    text = section(body)
    assert (f"- `{ref_of(context_scanned_repo, 'LEDGER_ADDR')}` → not in the catalog "
            "(declared as `component:default/ledger`)") in text
    assert f"- `{ref_of(context_scanned_repo, 'FX_RATES_URL')}` → matches no documented " \
           "dependency" in text
    _, body = bundle_for(context_scanned_repo, "src/sync/scheduler.ts")
    text = section(body)
    assert (f"- `{ref_of(context_scanned_repo, 'ANALYTICS_COLLECTOR_URL')}` → ignored by the "
            "profile: third-party analytics; tracked outside the catalog") in text
    assert (f"- `{ref_of(context_scanned_repo, 'REPORTING_JOB_URL')}` → documented only as a "
            "dependent: `dependencyOf component:default/reporting-job`") in text


def test_a_file_with_no_observation_has_no_section(context_scanned_repo):
    observed_files = {o["file"] for o in c.load_observed(context_scanned_repo)["observations"]}
    quiet = [e for e in index_of(context_scanned_repo)["bundles"] if e["file"] not in observed_files]
    assert quiet
    for entry in quiet:
        assert HEADING not in Path(entry["bundle"]).read_text()


def test_the_index_records_observed_hash(context_scanned_repo):
    want = c.load_observed(context_scanned_repo)["observed_hash"]
    index = index_of(context_scanned_repo)
    assert index["observed_hash"] == want
    assert all(e["observed_hash"] == want for e in index["bundles"])


def test_sixteen_observations_render_fifteen_lines():
    obs = [{"ref": f"observed env:X{n:02d}_URL src/a.ts:{n}", "kind": "env",
            "value": f"X{n:02d}_URL", "file": "src/a.ts", "line": n} for n in range(16)]
    doc = {"observations": obs, "resolutions": [
        {"kind": "env", "value": o["value"], "resolution": "unmatched", "entity": None,
         "edge": None, "via": None, "occurrences": 1} for o in obs]}
    text = bundle.section_observed(doc, "src/a.ts")
    assert text.count("\n- `observed ") == 15
    assert "… and 1 more observed in this file" in text
    assert bundle.section_observed(doc, "src/b.ts") == ""
    assert bundle.section_observed(None, "src/a.ts") == ""


def test_an_injected_value_stays_inside_its_code_span():
    evil = "observed env:X src/a`](x)<b>.ts:1"
    doc = {"observations": [{"ref": evil, "kind": "env", "value": "X", "file": "src/a.ts",
                             "line": 1}],
           "resolutions": [{"kind": "env", "value": "X", "resolution": "unmatched",
                            "entity": None, "edge": None, "via": None, "occurrences": 1}]}
    line = [ln for ln in bundle.section_observed(doc, "src/a.ts").splitlines()
            if ln.startswith("- ")][0]
    assert line.startswith("- ``") and "<b>" in line and "](x)" in line


def test_bundles_are_deterministic_with_observations(context_scanned_copy, context_env, run_steps):
    before = {e["id"]: e["bundle_hash"] for e in index_of(context_scanned_copy)["bundles"]}
    run_steps(context_scanned_copy, context_env, ["observed.py"], ["bundle.py"])
    after = {e["id"]: e["bundle_hash"] for e in index_of(context_scanned_copy)["bundles"]}
    assert before == after


def test_no_context_means_no_section_and_unchanged_bundles(scanned_copy, run_steps):
    before = {e["id"]: e["bundle_hash"] for e in index_of(scanned_copy)["bundles"]}
    run_steps(scanned_copy, None, ["observed.py"], ["bundle.py"])
    assert json.loads((scanned_copy / ".thunderstruck" / "observed.json").read_text())["status"] \
        == "skipped"
    index = index_of(scanned_copy)
    assert {e["id"]: e["bundle_hash"] for e in index["bundles"]} == before
    assert index["observed_hash"] is None
    for entry in index["bundles"]:
        assert HEADING not in Path(entry["bundle"]).read_text()
