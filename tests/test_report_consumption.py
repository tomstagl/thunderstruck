"""The Consumption section of report.md, and `consumption` in report.json (#5)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import report
from test_inert_report import _assert_inert

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS_LINE = "Weighted by published price per model and token type, Claude Sonnet 5.5 input = 1."


def _row(weighted: int | None, **counts) -> dict:
    return {"input": 0, "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": 0,
            "output": 0, **counts, "weighted": weighted}


def _usage(repo: Path, **over) -> dict:
    hotspots = json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())
    doc = {
        "schema": "thunderstruck.usage/v1", "source": "transcripts",
        "window": {"from": hotspots["generated_at"], "to": "2099-01-01T00:00:00+00:00"},
        "orchestrator": {"calls": 41, "by_model": {"claude-opus-5-5": _row(595_644)}},
        "investigators": {"agents": 10, "respawns": 0, "repairs": 1, "fallback_saves": 0,
                          "calls": 70,
                          "by_model": {"claude-sonnet-5-5": _row(445_000)},
                          "by_hotspot": {"H01": {"agents": 2, "calls": 9, "weighted": 52_000}}},
        "total_weighted": 1_040_644, "missing": []}
    return {**doc, **over}


def _report(repo: Path, usage: dict | None) -> tuple[str, dict]:
    path = repo / ".thunderstruck" / "usage.json"
    if usage is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(json.dumps(usage))
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "report.py"),
                           "--repo", str(repo)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = repo / ".thunderstruck"
    return (out / "report.md").read_text(), json.loads((out / "report.json").read_text())


def _section(markdown: str) -> str:
    assert "## Consumption" in markdown
    return markdown.split("## Consumption\n", 1)[1].split("\n## ", 1)[0]


def test_a_measured_scan_reports_its_consumption(scanned_copy):
    markdown, doc = _report(scanned_copy, _usage(scanned_copy))
    section = _section(markdown)
    assert "Signals to report: 1041k weighted tokens." in section
    assert "Orchestrator 596k (`claude-opus-5-5`, 41 calls)." in section
    assert ("Investigators 445k across 10 agents (`claude-sonnet-5-5`), "
            "1 repair, 0 re-spawns.") in section
    assert WEIGHTS_LINE in section
    assert "saved by the orchestrator" not in section
    assert doc["consumption"]["investigators"]["by_hotspot"]["H01"]["weighted"] == 52_000


def test_the_section_follows_run_warnings_or_the_header(scanned_copy):
    markdown, _ = _report(scanned_copy, _usage(scanned_copy))
    headings = [line for line in markdown.splitlines() if line.startswith("## ")]
    i = headings.index("## Consumption")
    assert i == (1 if headings[0] == "## Run warnings" else 0), headings


def test_fallback_saves_are_counted(scanned_copy):
    usage = _usage(scanned_copy)
    usage["investigators"]["fallback_saves"] = 2
    section = _section(_report(scanned_copy, usage)[0])
    assert "2 result(s) saved by the orchestrator because the hook did not deliver them." \
        in section


def test_a_partial_measurement_says_what_it_covers(scanned_copy):
    usage = _usage(scanned_copy, source="partial",
                   missing=["H04: no agent record, the hook did not fire"])
    section = _section(_report(scanned_copy, usage)[0])
    assert "Signals to report: 1041k" not in section, "a partial total is not the whole"
    assert "Covers: " in section
    assert "Not measured: H04: no agent record, the hook did not fire." in section


def test_an_unmeasured_scan_says_why(scanned_copy):
    usage = _usage(scanned_copy, source="unavailable", total_weighted=0,
                   missing=["orchestrator: session transcript not readable",
                            "H01: no agent record, the hook did not fire"])
    section = _section(_report(scanned_copy, usage)[0])
    assert section.strip() == ("Consumption was not measured: orchestrator: session "
                               "transcript not readable; H01: no agent record, the hook "
                               "did not fire.")


def test_a_usage_json_from_an_earlier_scan_is_ignored(scanned_copy):
    usage = _usage(scanned_copy)
    usage["window"]["from"] = "2000-01-01T00:00:00+00:00"
    markdown, doc = _report(scanned_copy, usage)
    assert "## Consumption" not in markdown
    assert "usage.json is from an earlier scan and was ignored" in doc["run_warnings"]
    assert "- `usage.json` is from an earlier scan and was ignored" in markdown
    assert doc["consumption"] is None


def test_without_usage_json_the_report_is_unchanged(scanned_copy):
    markdown, doc = _report(scanned_copy, None)
    assert "## Consumption" not in markdown
    assert doc["consumption"] is None
    data = report.collect(scanned_copy)
    del data["usage"]
    assert report.render_markdown(data, scanned_copy) == markdown


def test_model_names_are_inert(scanned_copy):
    usage = _usage(scanned_copy)
    usage["orchestrator"]["by_model"] = {"[x](http://e.example) <img src=x>": _row(1)}
    usage["missing"] = ["model [y](http://e.example) has no weights"]
    usage["source"] = "partial"
    markdown, _ = _report(scanned_copy, usage)
    _assert_inert(markdown)
