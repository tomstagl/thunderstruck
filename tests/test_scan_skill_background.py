"""The scan skill when an Agent call returns a background launch (#97).

The skill is prose, so these tests pin it, as test_no_execution.py and
test_skeptic_contract.py pin other sentences: both modes are named, a batch is
done when every agent of it has produced a result and a completion
notification, usage is never invented, and what the skill forbids stays
forbidden. One executed test documents the existing behaviour the skill leans
on: a fallback save without usage is accepted and the report names it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_usage import _build, scan  # noqa: F401  (the fixture)

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "skills" / "thunderstruck-scan" / "SKILL.md").read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    i = SKILL.index(start)
    return SKILL[i:SKILL.index(end, i + len(start))]


STEP3 = _section("## Step 3 — investigate", "## Step 4 — validate")
STEP4 = _section("## Step 4 — validate", "## Step 4b — verify")
STEP4B = _section("## Step 4b — verify", "## Step 5 — report")


def _flat(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize("phrase", [
    "launch acknowledgement",
    "every agent of the batch",
    "completion notification",
    "without `--usage`",
    "never invent a figure",
])
def test_step_3_describes_both_modes_and_when_a_batch_is_done(phrase):
    assert phrase in _flat(STEP3)


def test_a_background_launch_ends_the_turn_without_polling():
    text = _flat(STEP3).lower()
    assert "end your turn with no further tool call" in text
    assert "never poll" in text and "do not poll" in text


def test_usage_is_taken_from_the_notification_or_the_inline_result():
    assert "from the completion notification (or the inline result)" in _flat(STEP3)


def test_a_missing_notification_is_handled_without_a_timer():
    text = _flat(STEP3).lower()
    assert "if a notification does not arrive" in text
    assert "no timer is used" in text
    assert "timer" not in text.replace("no timer is used", "")


@pytest.mark.parametrize("forbidden", ["run_in_background", "agent teams", "`SendMessage`",
                                       "`ListAgents`"])
def test_what_was_forbidden_stays_forbidden(forbidden):
    text = _flat(STEP3)
    i = text.index(forbidden)
    assert "never" in text[max(0, i - 160):i].lower()


def test_a_partial_batch_does_not_trigger_the_check():
    text = _flat(STEP3).lower()
    assert "every wake before that ends the turn again with no tool call" in text
    assert "the last agent's result and notification have both arrived" in text


def test_the_skeptic_fallback_may_omit_usage_too():
    text = _flat(STEP4B)
    assert "save without `--usage`" in text and "never invent a figure" in text


def test_the_repair_round_and_the_skeptic_batches_follow_the_same_rule():
    assert "the rule of step 3" in _flat(STEP4)
    assert "the rule of step 3" in _flat(STEP4B)
    # "foreground" alone no longer stands in for the rule
    assert "foreground, waiting for each batch" not in _flat(STEP4B)


def test_a_fallback_save_without_usage_is_partial_and_named(scan):  # noqa: F811
    repo, out = scan["repo"], scan["out"]
    (out / "agents" / "H01.json").unlink()
    result = repo / "result.json"
    result.write_text(json.dumps({"hotspot_id": "H01", "findings": []}))
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "save_finding.py"),
                           "--repo", str(repo), "--id", "H01", "--from", str(result),
                           "--fallback"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads((out / "agents" / "H01.json").read_text())["fallback"] is True
    doc = _build(scan)
    assert doc["source"] == "partial"
    assert any(m.startswith("H01") for m in doc["missing"]), doc["missing"]
