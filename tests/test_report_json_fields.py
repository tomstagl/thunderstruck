"""#3 Task 1: report.json carries every section report.md shows, computed
once in Python, so the HTML page never derives a number itself (spec §2)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import mdtext as md
import report
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding

COLUMNS = ("id", "name", "tier", "unconfirmed_files", "leads_read", "leads_confirmed", "findings")


def _report(repo: Path, plugin_root: Path) -> tuple[str, dict]:
    hid, doc = _valid_finding(repo, _hotspots(repo))
    _write_finding(repo, hid, doc)
    assert _validate(repo, plugin_root).returncode == 0
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(repo)], check=True, capture_output=True)
    out = repo / ".thunderstruck"
    return (out / "report.md").read_text(), json.loads((out / "report.json").read_text())


def _md_coverage_rows(markdown: str) -> list[list[str]]:
    table = markdown.split("## Pattern coverage", 1)[1].split("\n\n<sub>", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("| ")]
    return [[cell.strip() for cell in row.strip("|").split(" | ")] for row in rows[1:]]


def _as_md_cells(row: dict) -> list[str]:
    def num(v):
        return "—" if v is None else str(v)
    return [md.code(row["id"], cell=True), md.text(row["name"], cell=True),
            "—" if row["tier"] is None else md.text(row["tier"], cell=True),
            num(row["unconfirmed_files"]), num(row["leads_read"]),
            num(row["leads_confirmed"]), str(row["findings"])]


def _md_run_warnings(markdown: str) -> list[str]:
    if "## Run warnings" not in markdown:
        return []
    block = markdown.split("## Run warnings\n\n", 1)[1].split("\n\n", 1)[0]
    return [line[2:] for line in block.splitlines()
            if line.startswith("- ") and not line.startswith("- **Suppressed leads**")]


def test_report_json_has_the_new_fields(scanned_copy, plugin_root):
    markdown, payload = _report(scanned_copy, plugin_root)
    hs = _hotspots(scanned_copy)
    assert payload["scanned_at"] == hs["generated_at"]
    assert payload["suppressed"] == []
    assert payload["files_affected"] == 1
    assert isinstance(payload["run_warnings"], list)
    assert payload["coverage_rows"], "no pattern coverage rows"
    for row in payload["coverage_rows"]:
        assert tuple(row) == COLUMNS


def test_coverage_rows_are_the_markdown_table(scanned_copy, plugin_root):
    markdown, payload = _report(scanned_copy, plugin_root)
    assert [_as_md_cells(r) for r in payload["coverage_rows"]] == _md_coverage_rows(markdown)


def test_warnings_keep_their_meaning(scanned_copy, plugin_root):
    """`warnings` is an existing field: hotspot plus link warnings, unchanged."""
    _, payload = _report(scanned_copy, plugin_root)
    data = report.collect(scanned_copy)
    assert payload["warnings"] == (list(data["hotspots"].get("warnings") or [])
                                   + list(data["link_warnings"]))


def test_helpers_match_the_markdown_with_every_section(scanned_copy, plugin_root):
    """Context warnings, suppressed leads and an OTHER row all present: the
    helpers and report.md agree line for line."""
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    doc["findings"][0]["missing_patterns"] = ["S02", "OTHER"]
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    data = report.collect(scanned_copy)
    data["hotspots"]["warnings"] = ["lizard missing: ranked on churn alone"]
    data["context_warnings"] = ["catalog said <b>hi</b>"]
    data["link_warnings"] = ["links: not linked"]
    data["hotspots"]["suppressed"] = [{"detector": "S15-ts-no-fallback", "path": "src/a.ts",
                                       "reason": "edge fallback", "hits": 2}]
    markdown = report.render_markdown(data, scanned_copy)
    payload = report.render_json(data)

    assert payload["run_warnings"] == ["lizard missing: ranked on churn alone",
                                       "catalog said <b>hi</b>", "links: not linked"]
    assert [md.text(w) for w in payload["run_warnings"]] == _md_run_warnings(markdown)
    assert payload["warnings"] == ["lizard missing: ranked on churn alone", "links: not linked"]
    assert payload["suppressed"] == [{"detector": "S15-ts-no-fallback", "path": "src/a.ts",
                                      "hits": 2, "reason": "edge fallback"}]
    other = payload["coverage_rows"][-1]
    assert other == {"id": "OTHER", "name": "Not in the catalog", "tier": None,
                     "unconfirmed_files": None, "leads_read": None, "leads_confirmed": None,
                     "findings": 1}
    assert [_as_md_cells(r) for r in payload["coverage_rows"]] == _md_coverage_rows(markdown)
    assert re.search(rf"across {payload['files_affected']} file\(s\)", markdown)


def test_clean_entries_carry_cited_by(scanned_copy, plugin_root):
    """A clean hotspot another finding cites: report.json names the citing
    ids, as report.md's "cited as evidence by" note does (spec §2)."""
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    data = report.collect(scanned_copy)
    finding = data["findings"][0]
    other = next(h["file"] for h in data["hotspots"]["hotspots"]
                 if h["file"] != finding["location"]["file"])
    finding["evidence"].append({"type": "code", "ref": f"{other}:1"})
    data["clean"] = [{"hotspot_id": "H98", "file": other, "notes": "fine"},
                     {"hotspot_id": "H99", "file": "nobody/cites.py", "notes": ""}]
    markdown = report.render_markdown(data, scanned_copy)
    payload = report.render_json(data)

    by_file = {e["file"]: e["cited_by"] for e in payload["clean"]}
    assert by_file == {other: [finding["id"]], "nobody/cites.py": []}
    assert f"no finding of its own; cited as evidence by {finding['id']}" in markdown
    assert "cited_by" not in data["clean"][0], "collect()'s data must not be mutated"


GAPS = {"tracked": 40, "considered": 12, "unchanged": 9, "not_citable": 1,
        "excluded": {"test": 6, "weird-reason": 2},
        "unsupported": {".rb": 3, "other": 4, ".go": 3}}


def test_not_scanned_plain_and_markdown_agree():
    plain = report.not_scanned(GAPS)
    assert plain["intro"].startswith("Of 40 tracked files, 12 changed")
    assert plain["items"] == [
        "9 in a supported language had no commit in the window, so they could not rank on churn",
        "1 are not citable (symbolic links, submodules, or names that are not UTF-8)",
        "6 excluded: test code",
        "2 excluded: weird-reason",
        "no detectors for their language or format: 4 other, 3 .go, 3 .rb",
    ]
    marked = report.not_scanned(GAPS, code=md.code, text=md.text)
    section = report.render_not_scanned(GAPS)
    assert section == ["## Not scanned", "", marked["intro"], "",
                       *[f"- {i}" for i in marked["items"]], ""]
    assert report.not_scanned(None) is None


def test_report_json_carries_not_scanned(scanned_copy, plugin_root):
    _, payload = _report(scanned_copy, plugin_root)
    gaps = _hotspots(scanned_copy).get("coverage_gaps")
    assert payload["not_scanned"] == report.not_scanned(gaps)
    assert payload["not_scanned"] is not None
    assert "`" not in json.dumps(payload["not_scanned"])
