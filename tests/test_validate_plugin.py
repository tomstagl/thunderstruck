"""`validate_plugin.py` allows exactly the known CLAUDE.md warning and keeps
`--strict` for everything else. The report shape is the one
`claude plugin validate --strict --json` prints."""

from __future__ import annotations

import validate_plugin as vp

KNOWN = ("CLAUDE.md at the plugin root is not loaded as project context. To ship "
         "context with your plugin, use a skill (skills/<name>/SKILL.md) instead.")


def _report(warnings=(), errors=(), file="/repo/CLAUDE.md", manifest_warnings=()):
    return {
        "success": False,
        "strict": True,
        "manifest": {"file": "/repo/.claude-plugin/marketplace.json", "type": "marketplace",
                     "errors": [], "warnings": list(manifest_warnings), "notes": []},
        "contents": [{"file": file, "type": "plugin", "errors": list(errors),
                      "warnings": list(warnings), "notes": []}],
    }


def _w(message, path="root"):
    return {"path": path, "message": message, "code": None}


def test_the_known_warning_alone_passes():
    assert vp.problems(_report([_w(KNOWN)])) == []


def test_a_clean_report_passes():
    assert vp.problems(_report()) == []


def test_any_other_warning_fails():
    found = vp.problems(_report([_w(KNOWN), _w("plugin.json: unrecognized field 'hooks'")]))
    assert len(found) == 1 and "unrecognized field" in found[0]


def test_the_known_message_on_another_file_fails():
    assert vp.problems(_report([_w(KNOWN)], file="/repo/skills/x/SKILL.md"))


def test_a_manifest_warning_fails():
    assert vp.problems(_report(manifest_warnings=[_w("missing description")]))


def test_errors_always_fail():
    assert vp.problems(_report([_w(KNOWN)], errors=[_w("duplicate hooks file")]))
