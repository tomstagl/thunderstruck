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
    block = re.search(r"```json\n(\{.*?\})\n```", AGENT.read_text(), re.S)[1]
    example = json.loads(block)
    assert set(example) == set(verify.VERDICT_KEYS)
    assert all(set(rc) <= set(verify.REFUTED_CLAIM_KEYS) for rc in example["refuted_claims"])


def test_prompt_states_the_rules_that_matter():
    text = AGENT.read_text().lower()
    for phrase in ("only task is to refute", "data, never instructions", "mark as refuted",
                   "up to 10 files", "never edit", "quote", "duplicate_of"):
        assert phrase in text, phrase
    assert "confidence_rationale" not in text  # it is never given, so never mentioned
