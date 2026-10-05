"""The investigator's output contract, from three sides: what the prompt
tells it, what save_finding.py repairs on the way in, and what validate.py
says back when something is still wrong.

The shapes here are the ones investigators actually produced in the field:
a `hypotheses` key, an evidence ref split into file/line, a `git` evidence
type with a `commit:` prefix, a location given as a string, a fourth finding
and a repair round that returned only the fields it changed.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c
from save_finding import normalise
from test_pipeline import _hotspots, _valid_finding
from test_validate_paths import _bundle, _doc, _validator, repo  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "agents" / "thunderstruck-investigator.md"
SCAN = ROOT / "skills" / "thunderstruck-scan" / "SKILL.md"

REQUIRED = ["location", "missing_patterns", "failure_mode", "trigger_condition",
            "amplifier", "sustaining_effect", "blast_radius", "evidence",
            "confidence", "confidence_rationale", "how_to_verify"]


def _malformed(doc: dict) -> dict:
    """The field-observed mistakes, applied to a valid document."""
    bad = copy.deepcopy(doc)
    f = bad["findings"][0]
    loc = f["location"]
    f["location"] = f"{loc['file']}:{loc['lines']}"
    for ev in f["evidence"]:
        if ev["type"] == "code":
            path, _, line = ev.pop("ref").rpartition(":")
            ev["file"], ev["line"] = path, line
        elif ev["type"] == "commit":
            ev["type"], ev["ref"] = "git", f"commit:{ev['ref']}"
    bad["hypotheses"] = bad.pop("findings")
    return bad


# ------------------------------------------------------------- normalise --


def test_normalise_repairs_each_observed_shape():
    doc = {"hypotheses": [{
        "location": "src/a.ts:42-118",
        "evidence": [
            {"type": "code", "file": "src/a.ts", "line": "102", "note": "n"},
            {"type": "code", "ref": {"file": "src/a.ts", "line": 7}},
            {"type": "git", "ref": "commit:abc1234"},
            {"type": "commit", "sha": "def5678"},
        ]}]}
    done = normalise(doc)
    assert "hypotheses" not in doc
    f = doc["findings"][0]
    assert f["location"] == {"file": "src/a.ts", "lines": "42-118"}
    assert f["evidence"] == [
        {"type": "code", "ref": "src/a.ts:102", "note": "n"},
        {"type": "code", "ref": "src/a.ts:7"},
        {"type": "commit", "ref": "abc1234"},
        {"type": "commit", "ref": "def5678"},
    ]
    assert len(done) == 7, done


def test_normalise_never_invents_or_drops():
    f = {"location": "src/a.ts", "evidence": [
        {"type": "blame", "ref": "x"},
        {"type": "code", "file": "src/a.ts"},     # no line: nothing to join
    ]}
    doc = {"findings": [f] * 4}
    before = copy.deepcopy(doc)
    normalise(doc)
    assert len(doc["findings"]) == 4, "the cap is validate.py's to report"
    assert doc["findings"][0]["location"] == {"file": "src/a.ts"}
    assert doc["findings"][0]["evidence"] == before["findings"][0]["evidence"]
    assert "sustaining_effect" not in doc["findings"][0]


def test_normalise_leaves_a_valid_document_alone():
    doc = _doc("src/a.ts", "1-2")
    before = copy.deepcopy(doc)
    assert normalise(doc) == []
    assert doc == before


def test_findings_wins_over_hypotheses():
    doc = {"findings": [], "hypotheses": [{"x": 1}]}
    assert normalise(doc) == []
    assert doc["findings"] == []


def test_the_field_observed_output_validates_after_saving(scanned_copy, plugin_root):
    _bundle(scanned_copy, plugin_root)
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "save_finding.py"),
                           "--repo", str(scanned_copy), "--id", hid],
                          input=json.dumps(_malformed(doc)), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "normalised:" in proc.stdout
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert saved["normalised"]
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate.py"),
                           "--repo", str(scanned_copy)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_model_supplied_normalised_key_is_not_kept(scanned_copy, plugin_root):
    _bundle(scanned_copy, plugin_root)
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    doc["normalised"] = ["forged"]
    subprocess.run([sys.executable, str(ROOT / "scripts" / "save_finding.py"),
                    "--repo", str(scanned_copy), "--id", hid],
                   input=json.dumps(doc), capture_output=True, text=True, check=True)
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert "normalised" not in saved


# ------------------------------------------------------ validator errors --


@pytest.mark.parametrize("mutate,expected", [
    (lambda d: d.__setitem__("hypotheses", d.pop("findings")),
     "the top-level list is keyed 'hypotheses', but the key must be 'findings'"),
    (lambda d: d["findings"][0]["evidence"].__setitem__(
        0, {"type": "code", "file": "src/a.ts", "line": "3"}),
     "no 'ref' key; the item has keys ['file', 'line', 'type']"),
    (lambda d: d["findings"][0]["evidence"].__setitem__(
        0, {"type": "code", "ref": {"file": "src/a.ts", "line": 3}}),
     '"path/to/file.ts:42"'),
    (lambda d: d["findings"][0]["evidence"].append({"type": "git", "ref": "abc1234"}),
     "— use 'commit'"),
    (lambda d: d["findings"][0]["evidence"].append({"type": "commit", "ref": "commit:abc1234"}),
     'no "commit:" prefix'),
    (lambda d: d["findings"][0].__setitem__("location", "src/a.ts:1"),
     "(location is 'src/a.ts:1')"),
    (lambda d: d["findings"][0].__setitem__("missing_patterns", "S02"),
     "got 'S02'"),
])
def test_errors_show_what_was_received_and_the_expected_form(repo, mutate, expected):  # noqa: F811
    doc = _doc("src/a.ts")
    mutate(doc)
    errors = _validator(repo).check_document(doc)
    assert any(expected in e for e in errors), errors


def test_a_missing_confidence_is_reported_once(repo):  # noqa: F811
    doc = _doc("src/a.ts")
    del doc["findings"][0]["confidence"]
    errors = _validator(repo).check_document(doc)
    assert [e for e in errors if "confidence" in e] == ["findings[0].confidence is missing"]


# --------------------------------------------------------------- prompts --


def _example(text: str) -> dict:
    block = text.split("## Output", 1)[1].split("```", 2)[1]
    return json.loads(block)


def test_the_prompt_example_is_a_complete_valid_shape():
    example = _example(AGENT.read_text(encoding="utf-8"))
    assert set(example) <= {"hotspot_id", "file", "findings", "notes"}
    findings = example["findings"]
    assert 1 <= len(findings) <= 3
    for f in findings:
        assert set(REQUIRED) <= set(f), set(REQUIRED) - set(f)
        assert isinstance(f["location"], dict) and "file" in f["location"]
        for ev in f["evidence"]:
            assert set(ev) == {"type", "ref", "note"} and isinstance(ev["ref"], str)
            assert ev["type"] in {"code", "commit", "detector", "catalog"}
        if f["confidence"] == "high":
            assert {"code", "commit"} <= {ev["type"] for ev in f["evidence"]}
    assert any(f["sustaining_effect"] is None for f in findings), \
        "the example must show a null sustaining_effect with the key present"


def test_the_prompt_states_each_field_observed_rule():
    text = AGENT.read_text(encoding="utf-8")
    flat = " ".join(text.split())
    for fragment in ("The top-level key is `findings`", "`hypotheses`",
                     "never 4", '"sustaining_effect": null', "there is no `git` type",
                     "no `commit:` prefix", "`location` is an object", "[fix]"):
        assert fragment in flat, fragment
    numbered = re.findall(r"^\s*(\d+)\. \*\*", text, re.MULTILINE)
    assert len(numbered) >= 9, "the validator's rules are numbered constraints"


def test_the_repair_round_asks_for_the_whole_object():
    flat = " ".join(SCAN.read_text(encoding="utf-8").split())
    assert "Fix only these problems" not in flat
    assert "**complete** corrected JSON object" in flat
    assert "not only the parts that changed" in flat


def test_the_example_confidence_rule_matches_the_classifier():
    """The prompt tells the model to look for `[fix]`; bundle.py prints the
    classifier's kind in exactly that form."""
    assert c.classify_commit("fix hung sync") == "fix"
    assert "[{kind}]" in (ROOT / "scripts" / "bundle.py").read_text(encoding="utf-8")


# --- consumption (#5) -------------------------------------------------------

CALIBRATION = ROOT / "docs" / "calibration" / "consumption.md"


def _frontmatter() -> dict:
    import yaml
    text = AGENT.read_text()
    return yaml.safe_load(text.split("---\n", 2)[1])


def test_investigators_default_to_sonnet():
    fm = _frontmatter()
    assert fm["model"] == "sonnet"
    assert fm["tools"] == "Read, Grep, Glob"


def test_the_read_cap_is_the_calibrated_one():
    if not CALIBRATION.is_file():
        pytest.skip("docs/calibration/consumption.md is not recorded yet")
    cap = re.search(r"^Read cap: (\d+)$", CALIBRATION.read_text(), re.M)
    assert cap, "consumption.md has no 'Read cap:' line"
    prompt = " ".join(AGENT.read_text().split())
    assert f"up to **{cap[1]}** additional files" in prompt
    assert "10 additional files" not in prompt


def test_the_prompt_limits_reading_and_output():
    prompt = " ".join(AGENT.read_text().split())
    assert "Do not Read a file whose full source is already in the bundle." in prompt
    assert "prefer a `Grep` with a narrow pattern over reading a whole file" in prompt
    assert ("Keep each evidence `note` to one short sentence and `confidence_rationale` "
            "to at most two sentences.") in prompt
