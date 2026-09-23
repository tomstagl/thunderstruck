"""Java detectors land in batches, and one positive sample per pattern can
hide a detector that never fires: the pattern-level sample test passes as
long as *any* of a pattern's detectors hits. This pins every Java detector
individually, and pins the confidence discipline from the spec (§5): no Java
detector claims `high` until calibration has earned it."""

from __future__ import annotations

from pathlib import Path

from detectors import run_detectors

SAMPLES = Path(__file__).parent / "samples"


def _java_detectors(catalog):
    for pattern in catalog["patterns"]:
        for det in (pattern.get("detectors") or {}).get("java", []) or []:
            yield pattern, det


def test_every_java_detector_fires_on_its_positive_sample(catalog):
    silent = []
    for pattern, det in _java_detectors(catalog):
        sample = SAMPLES / pattern["id"] / "java" / "positive.java"
        if not sample.exists():
            silent.append(f"{det['id']} (no {sample})")
            continue
        solo = {**catalog, "patterns": [{**pattern, "detectors": {"java": [det]}}]}
        hits = run_detectors(solo, f"src/{sample.name}",
                             sample.read_text(encoding="utf-8"), "java")
        if not any(h.detector_id == det["id"] for h in hits):
            silent.append(det["id"])
    assert not silent, (
        "Java detectors that never fire on their pattern's positive sample: "
        + ", ".join(silent))


def test_no_java_detector_claims_high_confidence(catalog):
    high = [det["id"] for _, det in _java_detectors(catalog)
            if det.get("confidence") == "high"]
    assert not high, f"Java detectors at confidence: high before calibration earned it: {high}"
