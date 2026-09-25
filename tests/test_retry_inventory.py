"""#19 AC-16: retry amplification needs every retry layer in view at once:
the code, the mesh and the library defaults nobody configured."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import signals
import _common as c
from test_coverage_gaps import _git
from detectors import Hit

VS = Path(__file__).parent / "detectors" / "samples" / "S01" / "yaml" / "positive.yaml"
MESH = "deploy/releases-virtualservice.yaml"


def _scan(repo: Path, plugin_root: Path) -> dict:
    for script, extra in (("signals.py", ["--top", "8", "--since", "24m"]), ("bundle.py", [])):
        proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / script),
                               "--repo", str(repo), *extra], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())


def _with_mesh(repo: Path) -> Path:
    (repo / "deploy").mkdir()
    (repo / MESH).write_text(VS.read_text())
    _git(repo, "add", MESH)
    _git(repo, "commit", "-q", "-m", "chore: mesh routing for releases")
    return repo


def test_inventory_spans_code_and_config(scanned_copy, plugin_root):
    data = _scan(_with_mesh(scanned_copy), plugin_root)
    layers = data["retry_layers"]
    assert {"kind": "config", "file": MESH, "detector_id": "S10-yaml-mesh-retry"}.items() <= \
        next(r for r in layers if r["file"] == MESH).items()
    code = {r["file"] for r in layers if r["kind"] == "code"}
    assert {"src/client/releases.ts", "src/client/retry-wrapper.ts"} <= code
    assert layers == sorted(layers, key=lambda r: (r["kind"], r["file"], r["line"]))


def test_a_retrying_hotspot_is_briefed_with_every_layer(scanned_copy, plugin_root):
    data = _scan(_with_mesh(scanned_copy), plugin_root)
    hid = next(h["id"] for h in data["hotspots"] if h["file"] == "src/client/releases.ts")
    bundle = (scanned_copy / ".thunderstruck" / "bundles" / f"{hid}.md").read_text()
    section = bundle.split("## Retry layers in this repository", 1)[1].split("\n## ", 1)[0]
    for f in (MESH, "src/client/releases.ts", "src/client/retry-wrapper.ts"):
        assert f in section


def test_a_hotspot_without_a_retry_lead_gets_no_inventory(scanned_copy, plugin_root):
    data = _scan(_with_mesh(scanned_copy), plugin_root)
    hid = next(h["id"] for h in data["hotspots"] if h["file"] == "src/sync/collection.ts")
    bundle = (scanned_copy / ".thunderstruck" / "bundles" / f"{hid}.md").read_text()
    assert "## Retry layers in this repository" not in bundle


def test_unchanged_config_is_still_inventoried(scanned_copy, plugin_root):
    """A mesh file untouched in the window is still a retry layer."""
    _with_mesh(scanned_copy)
    data = _scan(scanned_copy, plugin_root)
    assert any(r["file"] == MESH for r in data["retry_layers"])
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / "signals.py"),
                           "--repo", str(scanned_copy), "--top", "8", "--since", "1d",
                           "--dormant", "0"], capture_output=True, text=True)
    if proc.returncode == 0:  # the window may hold no commit at all
        data = json.loads((scanned_copy / ".thunderstruck" / "hotspots.json").read_text())
        assert any(r["file"] == MESH for r in data["retry_layers"])


def test_score_false_hits_never_weigh():
    patterns = c.effective_patterns(c.load_catalog(), {})
    hit = Hit("S10", "S10-py-boto3-default-retries", "a.py", 2, "", "low", "")
    assert signals.stability_weight([hit], patterns, unscored={hit.detector_id}) == (0.0, {})
    assert signals.stability_weight([hit], patterns)[0] > 0


def test_library_default_detectors_are_unscored_inventory():
    dets = {d["id"]: d for p in c.load_catalog()["patterns"]
            for ds in (p.get("detectors") or {}).values() for d in ds}
    for did in ("S10-py-boto3-default-retries", "S10-java-feign-default-retryer",
                "S10-ts-aws-sdk-default-retries"):
        assert dets[did].get("score") is False and dets[did].get("inventory") == "retry_layer"
