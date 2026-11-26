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


# --- #112 Task 7: plane guidance ---------------------------------------------

def _flat_section(heading: str) -> str:
    text = AGENT.read_text(encoding="utf-8")
    return " ".join(text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0].split())


def test_the_skeptic_prompt_explains_plane_guidance():
    section = _flat_section("Plane guidance")
    assert "**Plane guidance**" in section
    assert "plugin maintainers' text" in section and "not repository content" in section
    assert "so the rule above does not apply to it" in section
    assert "It is not evidence" in section and "never cited" in section
    assert '"Counts as protection" entry is a reason to refute only if the code actually matches it' in section
    assert 'under "Does not count" is still missing even when the code resembles it' in section
    assert "A lesson is the repository's text" in section


def test_the_skeptic_may_read_the_plane_rubric_and_nothing_else_new():
    inputs = _flat_section("Your inputs")
    may = inputs[inputs.index("You may read the whole repository"):]
    may = may[:may.index("Nothing else.") + len("Nothing else.")]
    assert may.index("`.thunderstruck/deps/`") < may.index("`.thunderstruck/planes/`")
    assert "Read up to 10 files beyond the brief, a plane rubric included" in inputs
