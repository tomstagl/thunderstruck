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


# --------------------------------------------------------------- validate --

import subprocess  # noqa: E402
import sys  # noqa: E402

from test_context_pipeline import _catalog_finding, _hotspots, _validate  # noqa: E402

RELEASES = "src/client/releases.ts"
COLLECTION = "src/sync/collection.ts"


def observed_finding(repo: Path, refs: list[str], code: bool = True,
                     extra_code: list[str] = ()) -> tuple[str, dict]:
    data = _hotspots(repo)
    hs = next(h for h in data["hotspots"] if h["file"] == RELEASES)
    data = {**data, "hotspots": [hs]}
    hid, doc = _catalog_finding(data, [], code=code)
    ev = doc["findings"][0]["evidence"]
    ev += [{"type": "code", "ref": f"{p}:1", "note": "cited"} for p in extra_code]
    ev += [{"type": "observed", "ref": r, "note": "calls it"} for r in refs]
    return hid, doc


def saved(repo: Path, hid: str) -> dict:
    return json.loads((repo / ".thunderstruck" / "findings" / f"{hid}.json").read_text())


def test_an_observation_validates_and_is_stamped(context_scanned_copy, plugin_root):
    ref = ref_of(context_scanned_copy, "RELEASES_API_URL")
    hid, doc = observed_finding(context_scanned_copy, [ref])
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 0, proc.stdout
    assert saved(context_scanned_copy, hid)["findings"][0]["observed_evidence"] == [{
        "ref": ref, "kind": "env", "value": "RELEASES_API_URL", "resolution": "documented",
        "edge": "dependsOn component:default/releases-api"}]


def test_an_ignored_observation_stays_citable(context_scanned_copy, plugin_root):
    ref = ref_of(context_scanned_copy, "ANALYTICS_COLLECTOR_URL")
    hid, doc = observed_finding(context_scanned_copy, [ref],
                                extra_code=["src/sync/scheduler.ts"])
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 0, proc.stdout
    assert saved(context_scanned_copy, hid)["findings"][0]["observed_evidence"][0]["resolution"] \
        == "ignored"


def test_rule_1_no_observations_this_scan(scanned_copy, plugin_root):
    data = _hotspots(scanned_copy)
    hid, doc = _catalog_finding(data, [])
    doc["findings"][0]["evidence"].append(
        {"type": "observed", "ref": f"observed env:X_URL {data['hotspots'][0]['file']}:1",
         "note": "x"})
    proc = _validate(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "this scan observed no dependencies, so none can be cited" in proc.stdout


def test_rule_2_observations_changed_since_bundling(context_scanned_copy, plugin_root):
    ref = ref_of(context_scanned_copy, "RELEASES_API_URL")
    path = context_scanned_copy / ".thunderstruck" / "observed.json"
    doc_ = json.loads(path.read_text())
    doc_["observations"] = [o for o in doc_["observations"] if o["value"] != "FX_RATES_URL"]
    doc_["observed_hash"] = c.observed_hash(doc_)
    path.write_text(json.dumps(doc_))
    hid, doc = observed_finding(context_scanned_copy, [ref])
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "observations changed since bundling" in proc.stdout


def test_rule_3_no_such_observation(context_scanned_copy, plugin_root):
    ref = ref_of(context_scanned_copy, "RELEASES_API_URL")
    wrong = ref.rsplit(":", 1)[0] + ":1"
    hid, doc = observed_finding(context_scanned_copy, [wrong])
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert ("no such observation; copy a ref verbatim from the bundle's 'Dependencies observed "
            "in this file' section") in proc.stdout


def test_rule_4_an_observation_in_an_uncited_file(context_scanned_copy, plugin_root):
    ref = ref_of(context_scanned_copy, "FX_RATES_URL")
    hid, doc = observed_finding(context_scanned_copy, [ref])
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert f"is an observation in {COLLECTION}" in proc.stdout
    hid, doc = observed_finding(context_scanned_copy, [ref], extra_code=[COLLECTION])
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 0, proc.stdout


def test_observations_alone_are_rejected(context_scanned_copy, plugin_root):
    ref = ref_of(context_scanned_copy, "RELEASES_API_URL")
    hid, doc = observed_finding(context_scanned_copy, [ref], code=False)
    proc = _validate(context_scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "no item of type 'code'" in proc.stdout


def test_save_finding_strips_observed_evidence():
    import finding_shape
    assert "observed_evidence" in finding_shape.OWNED_FINDING_KEYS
