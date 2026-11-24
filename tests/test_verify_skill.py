"""#103 AC-4: the verify skill records the outcome by script and says it is display only."""

from __future__ import annotations

import re
from pathlib import Path

import reproduction

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "thunderstruck-verify" / "SKILL.md"


def test_the_skill_records_the_outcome_with_the_script():
    text = SKILL.read_text()
    call = re.search(r'uv run "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/reproduction\.py" record (.+)', text)
    assert call, "the skill does not call reproduction.py record"
    for flag in ("--key", "--status", "--test", "--command"):
        assert flag in call[1], flag
    for status in reproduction.STATUSES:
        assert f"`{status}`" in text, status
    # after the user's test run: the record step follows "run it and report honestly"
    assert text.index("run it and report honestly") < text.index("reproduction.py\" record")


def test_the_scope_says_the_record_is_read_for_display_only():
    scope = SKILL.read_text().split("## Scope", 1)[1]
    assert "nothing it produces feeds one" not in scope
    assert "nothing it produces changes what a scan finds, ranks or checks" in scope
    assert "for display only" in scope
    assert "diagnosis and remedy are kept apart" in scope


def test_the_skill_rebuilds_the_report_after_recording():
    text = SKILL.read_text()
    record = text.index('reproduction.py" record')
    assert record < text.index('scripts/report.py"', record) < text.index('scripts/report_html.py"', record)
