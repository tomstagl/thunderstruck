"""The retry-layer section must show the cross-file layers first: they are
the ones an investigator reading one file cannot see (#19 AC-16)."""

from __future__ import annotations

import _common as c
import bundle


def test_config_and_library_layers_survive_a_long_code_list():
    layers = ([{"kind": "code", "file": f"src/m{n:02d}.py", "line": 1, "detector_id": "S02-py-backoff",
                "pattern_id": "S02", "note": ""} for n in range(20)]
              + [{"kind": "config", "file": "deploy/vs.yaml", "line": 9,
                  "detector_id": "S10-yaml-mesh-retry", "pattern_id": "S10", "note": ""},
                 {"kind": "library-default", "file": "src/s3.py", "line": 2,
                  "detector_id": "S10-py-boto3-default-retries", "pattern_id": "S10", "note": ""}])
    hs = {"file": "src/m19.py", "detector_hits": [{"pattern_id": "S02"}]}
    section = bundle.section_retry_layers(hs, {"retry_layers": layers}, c.load_catalog())
    assert "deploy/vs.yaml" in section and "src/s3.py" in section
    assert "src/m19.py" in section, "the hotspot's own layer is always shown"
    assert "more in hotspots.json" in section


def test_retry_patterns_come_from_the_catalog():
    assert bundle.retry_lead_patterns(c.load_catalog()) == {"S02", "S04", "S10"}
