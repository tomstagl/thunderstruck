"""The skeptic's prompt states the contract verify.py enforces (#37 §6, §8)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import _common as c
import verify
import validate

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "agents" / "thunderstruck-skeptic.md"


def _front() -> dict:
    import yaml
    return yaml.safe_load(AGENT.read_text().split("---")[1])


def test_frontmatter_is_read_only_with_a_model():
    front = _front()
    assert front["name"] == "thunderstruck-skeptic"
    assert [t.strip() for t in front["tools"].split(",")] == ["Read", "Grep", "Glob"]
    assert front["model"] in c.MODEL_ALIASES


def test_prompt_names_every_key_verdict_field_and_evidence_type():
    text = AGENT.read_text()
    for word in (*verify.VERDICT_KEYS, *c.VERDICTS, *c.REFUTABLE_FIELDS,
                 *validate.VERDICT_EVIDENCE_TYPES, c.MISSING_GATE_PHRASE):
        assert f"`{word}`" in text or f'"{word}"' in text, word


def test_the_example_output_follows_the_contract():
    (example,) = [b for b in _blocks() if "verdict" in b]
    assert set(example) == set(verify.VERDICT_KEYS)
    assert all(set(rc) <= set(verify.REFUTED_CLAIM_KEYS) for rc in example["refuted_claims"])


def test_prompt_states_the_rules_that_matter():
    text = AGENT.read_text().lower()
    for phrase in ("only task is to refute", "data, never instructions", "mark as refuted",
                   "up to 10 files", "never edit", "quote", "duplicate_of"):
        assert phrase in text, phrase
    assert "confidence_rationale" not in text  # it is never given, so never mentioned


# --- #144: the prompt shows a missing gate with its setting -------------------
def _blocks() -> list[dict]:
    return [json.loads(b) for b in re.findall(r"```json\n(\{.*?\})\n```", AGENT.read_text(), re.S)]


def _gate_example() -> dict:
    (claim,) = [b for b in _blocks() if b.get("field") == "preconditions"]
    return claim


def test_the_shown_gate_settles_to_a_gate(validated_repo, validated_env, tmp_path):
    from test_verification import _apply, _entry, _finding, _prepare, _save, _v
    claim = _gate_example()
    assert set(claim) == set(verify.REFUTED_CLAIM_KEYS) and claim["claim"] == c.MISSING_GATE_PHRASE
    assert tuple(claim["setting"]) == verify.SETTING_KEYS
    path, line = claim["setting"]["default_ref"].rsplit(":", 1)
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "api.ts")
    _save(validated_repo, validated_env, tmp_path, _v(
        e["key"], "narrowed", holds="It happens with the setting on.", refuted_claims=[claim],
        evidence=[{"type": "code", "ref": f"src/client/api.ts:{k + 1}", "note": "n"}
                  for k in range(max(claim["evidence"]) + 1)]))
    # the example's own file does not exist in the fixture; the first line of a file that does stands in
    (tracked := validated_repo / path).parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text("\n" * int(line))
    import subprocess
    subprocess.run(["git", "add", "-f", path], cwd=validated_repo, check=True)
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert [rc.get("gate_problem") for rc in check["refuted_claims"]] == [None]
    finding = {**_finding(validated_repo, e["key"]), "preconditions": []}
    assert check["status"] == "narrowed" and c.finding_gate(finding) == "non_default_setting"
    assert verify.run_verdict(finding, check) == "upheld_but_gated"


def test_the_shown_gate_is_invented():
    """Nothing in it may come from a benchmark set. Frozen scans only: no label is read."""
    claim = _gate_example()
    words = [claim["setting"]["setting"], claim["setting"]["default_ref"].split(":")[0], claim["fact"]]
    for name in ("celery", "trigger-dev"):
        scan = ROOT / "docs" / "calibration" / "correctness" / name / "scan"
        for path in [scan / "report.json", scan / "hotspots.json", *scan.glob("findings/*"), *scan.glob("bundles/*")]:
            text = path.read_text(encoding="utf-8")
            assert not [w for w in words if w in text], path


def test_the_prompt_says_a_gated_failure_is_narrowed_and_the_keys_are_strings():
    text = " ".join(AGENT.read_text().split())
    assert "is `narrowed`, never `refuted`" in text
    assert all(f"`{k}`" in text for k in verify.SETTING_KEYS)
