"""Every Tier A pattern must fire on its positive sample and stay silent on
its negative one, in every language it claims to support.

Samples live in tests/detectors/samples/<PATTERN>/<language>/{positive,negative}.<ext>.
Adding a pattern means adding a catalog entry and a pair of samples; this test
finds them automatically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import _common
from detectors import run_detectors

SAMPLES = Path(__file__).parent / "samples"
EXT_LANG = {".ts": "typescript", ".py": "python", ".java": "java"}


def _cases() -> list[tuple[str, str, str, Path]]:
    out = []
    for pattern_dir in sorted(SAMPLES.iterdir()):
        if not pattern_dir.is_dir():
            continue
        for lang_dir in sorted(pattern_dir.iterdir()):
            if not lang_dir.is_dir():
                continue
            for sample in sorted(lang_dir.iterdir()):
                if sample.suffix in EXT_LANG:
                    out.append((pattern_dir.name, lang_dir.name,
                                sample.stem, sample))
    return out


CASES = _cases()


def test_samples_exist():
    assert CASES, "no detector samples found"


@pytest.mark.parametrize(
    "pattern_id,lang,polarity,path",
    CASES,
    ids=[f"{p}-{l}-{pol}" for p, l, pol, _ in CASES],
)
def test_sample(catalog, pattern_id, lang, polarity, path):
    text = path.read_text(encoding="utf-8")
    rel = f"src/{path.name}"
    hits = run_detectors(catalog, rel, text, lang, pattern_ids=[pattern_id])
    fired = {h.pattern_id for h in hits}

    # positive_<shape> guards a real case against over-correction; any other
    # stem (negative, negative_<shape>) must stay silent.
    if polarity.startswith("positive"):
        assert pattern_id in fired, (
            f"{pattern_id} did not fire on its positive sample {path}.\n"
            f"Sample:\n{text}")
    else:
        assert pattern_id not in fired, (
            f"{pattern_id} fired on its negative sample {path} — this is a "
            f"false positive.\nHits: {[(h.detector_id, h.line, h.note) for h in hits]}\n"
            f"Sample:\n{text}")


def test_every_tier_a_pattern_has_both_samples(catalog):
    """Tier A is what the tool leads with. A pattern with no negative sample
    has no evidence it does not fire on correct code."""
    missing = []
    for pattern in catalog["patterns"]:
        if str(pattern["tier"]).upper() != "A":
            continue
        for lang in pattern.get("detectors", {}):
            for polarity in ("positive", "negative"):
                found = any(c[0] == pattern["id"] and c[1] == lang and c[2] == polarity
                            for c in CASES)
                if not found:
                    missing.append(f"{pattern['id']}/{lang}/{polarity}")
    assert not missing, (
        "Tier A patterns without samples: " + ", ".join(missing))


def test_every_catalog_regex_compiles(catalog):
    import re
    bad = []
    for pattern in catalog["patterns"]:
        for lang, dets in (pattern.get("detectors") or {}).items():
            for det in dets or []:
                for key in ("pattern", "absent_within", "present_within", "anchor", "absent"):
                    if key in det:
                        try:
                            re.compile(det[key])
                        except re.error as exc:
                            bad.append(f"{det['id']}.{key}: {exc}")
    assert not bad, "\n".join(bad)


def test_detector_ids_are_unique(catalog):
    seen, dupes = set(), []
    for pattern in catalog["patterns"]:
        for dets in (pattern.get("detectors") or {}).values():
            for det in dets or []:
                if det["id"] in seen:
                    dupes.append(det["id"])
                seen.add(det["id"])
    assert not dupes, f"duplicate detector ids: {dupes}"


def test_module_handlers_exist(catalog):
    from detectors import modules
    missing = []
    for pattern in catalog["patterns"]:
        for dets in (pattern.get("detectors") or {}).values():
            for det in dets or []:
                if det.get("kind") == "module" and not hasattr(modules, det["handler"]):
                    missing.append(f"{det['id']} -> {det['handler']}")
    assert not missing, f"module detectors with no handler: {missing}"
