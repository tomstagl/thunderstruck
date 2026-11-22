"""#98: a re-scan keeps the scan it replaces, and a window can be repeated."""

from __future__ import annotations

import json
from pathlib import Path

import _common as c


def _hotspots(head="a" * 40, since_date="2025-11-22", top=10, path=None, include_tests=False,
              generated_at="2026-11-22T10:00:00+00:00") -> dict:
    return {"generated_at": generated_at, "repo": {"head": head},
            "window": {"since_date": since_date},
            "config": {"top": top, "path": path, "include_tests": include_tests}}


# --------------------------------------------------------------------------
# Task 1: the scan identity and the finished test (AC-1, AC-2)
# --------------------------------------------------------------------------


def test_scan_identity_is_the_tuple_of_the_spec():
    ident = c.scan_identity(_hotspots(path="src", include_tests=True))
    assert ident == ("a" * 40, "2025-11-22", 10, "src", True, c.REPORT_SCHEMA_VERSION)


def test_scan_identity_differs_on_each_part():
    base = c.scan_identity(_hotspots())
    for change in ({"head": "b" * 40}, {"since_date": "2025-12-01"}, {"top": 5},
                   {"path": "src"}, {"include_tests": True}):
        assert c.scan_identity(_hotspots(**change)) != base, change


def test_scan_identity_is_none_for_a_document_missing_a_part():
    for broken in ({}, {"repo": {}, "window": {}, "config": {}},
                   {k: v for k, v in _hotspots().items() if k != "window"},
                   {k: v for k, v in _hotspots().items() if k != "config"}, None, [], "x"):
        assert c.scan_identity(broken) is None
    no_head = _hotspots()
    del no_head["repo"]["head"]
    assert c.scan_identity(no_head) is None


def _out(tmp_path: Path, hotspots=None, report=None) -> Path:
    out = tmp_path / ".thunderstruck"
    out.mkdir(parents=True)
    if hotspots is not None:
        (out / "hotspots.json").write_text(json.dumps(hotspots))
    if report is not None:
        (out / "report.json").write_text(json.dumps(report))
    return out


def test_scan_finished_only_when_the_report_belongs_to_the_scan(tmp_path):
    hs = _hotspots()
    assert c.scan_finished(_out(tmp_path / "a", hs, {"scanned_at": hs["generated_at"]})) is True
    assert c.scan_finished(_out(tmp_path / "b", hs, {"scanned_at": "2020-01-01T00:00:00+00:00"})) is False
    # report.json's own generated_at is the render time and says nothing about the scan
    assert c.scan_finished(_out(tmp_path / "c", hs, {"generated_at": hs["generated_at"]})) is False


def test_scan_finished_is_false_when_a_file_is_missing_or_unreadable(tmp_path):
    hs = _hotspots()
    assert c.scan_finished(_out(tmp_path / "a", hs)) is False
    assert c.scan_finished(_out(tmp_path / "b", report={"scanned_at": "x"})) is False
    out = _out(tmp_path / "c", hs)
    (out / "report.json").write_text("{not json")
    assert c.scan_finished(out) is False
    out = _out(tmp_path / "d", hs)
    (out / "report.json").write_text("[]")
    assert c.scan_finished(out) is False
    assert c.scan_finished(tmp_path / "nowhere") is False
