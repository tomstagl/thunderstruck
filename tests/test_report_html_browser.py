"""#3 in a real browser: the page renders offline with no network request
and no CSP violation, model text stays text, and the reviewer controls work.

Needs Playwright with Chromium. Skips locally without it; CI sets
THUNDERSTRUCK_REQUIRE_BROWSER so these tests can never silently skip.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import report_html
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if os.environ.get("THUNDERSTRUCK_REQUIRE_BROWSER"):
            pytest.fail("playwright is not installed")
        pytest.skip("playwright is not installed")
    return sync_playwright


@pytest.fixture(scope="module")
def browser():
    sync_playwright = _playwright()
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # no browser for this Playwright version
            if os.environ.get("THUNDERSTRUCK_REQUIRE_BROWSER"):
                raise
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


class Page:
    """A page plus everything it tried to do that it should not."""

    def __init__(self, browser, path: Path):
        self.context = browser.new_context()
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.requests: list[str] = []
        self.page.on("console", lambda m: m.type in ("error", "warning")
                     and self.errors.append(m.text))
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("request", lambda r: self.requests.append(r.url))
        self.url = path.as_uri()
        self.page.goto(self.url)

    def text(self, selector: str) -> list[str]:
        return self.page.eval_on_selector_all(selector, "els => els.map(e => e.textContent)")

    def close(self):
        self.context.close()


def _report(repo: Path, plugin_root: Path, edit=None) -> dict:
    hid, doc = _valid_finding(repo, _hotspots(repo))
    if edit:
        edit(doc)
    _write_finding(repo, hid, doc)
    assert _validate(repo, plugin_root).returncode == 0
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(repo)], check=True, capture_output=True)
    return json.loads((repo / ".thunderstruck" / "report.json").read_text())


def _page(tmp_path: Path, report: dict, name: str = "report.html") -> Path:
    template = report_html.TEMPLATE.read_text(encoding="utf-8")
    dest = tmp_path / name
    dest.write_text(report_html.render(report_html.page_data(report), template), encoding="utf-8")
    return dest


@pytest.fixture
def page(browser, scanned_copy, plugin_root, tmp_path):
    pages: list[Page] = []

    def open_(report: dict | None = None, name: str = "report.html") -> Page:
        report = report or _report(scanned_copy, plugin_root)
        p = Page(browser, _page(tmp_path, report, name))
        pages.append(p)
        return p
    yield open_
    for p in pages:
        p.close()


def test_opens_offline_without_errors_or_requests(page, scanned_copy, plugin_root):
    report = _report(scanned_copy, plugin_root)
    p = page(report)
    assert p.errors == [], p.errors
    assert p.requests == [p.url], p.requests
    assert p.page.title() == "thunderstruck — " + Path(report["repo"]["root"]).name


HOSTILE = ('</script><script id="pwn">window.pwned=1</script>'
           '<img id="pwn-img" src=x onerror="window.pwned=1"><b id="pwn-b">bold</b>')


def test_model_text_is_shown_as_text(page, scanned_copy, plugin_root):
    def edit(doc):
        doc["findings"][0]["failure_mode"] = "fm " + HOSTILE
        doc["findings"][0]["how_to_verify"] = "verify " + HOSTILE
    p = page(_report(scanned_copy, plugin_root, edit))
    p.page.keyboard.press("j")
    assert p.text("h1") == ["fm " + HOSTILE]
    assert ("verify " + HOSTILE) in p.text(".verify p")
    assert p.page.evaluate("window.pwned") is None
    for sel in ("#pwn", "#pwn-img", "#pwn-b", "img"):
        assert p.page.query_selector(sel) is None, sel
    assert p.errors == [] and p.requests == [p.url]


def test_overview_has_every_report_md_section(page, scanned_copy, plugin_root):
    report = _report(scanned_copy, plugin_root)
    report["run_warnings"] = ["a warning"]
    report["suppressed"] = [{"detector": "S15-x", "path": "a.ts", "hits": 1, "reason": "r"}]
    report["clean"] = [{"hotspot_id": "H08", "file": "src/x.ts", "notes": "fine",
                        "cited_by": ["FR-001"], "url": None}]
    report["incomplete"] = [{"hotspot_id": "H09", "file": "src/y.ts", "reason": "no output",
                             "url": None}]
    report["dormant"] = [{"id": "D01", "file": "src/z.ts", "script": False,
                          "last_modified": "2020-01-01T00:00:00+00:00", "patterns": ["S01"],
                          "url": None}]
    report["service_context"] = {"status": "fresh", "entity_ref": "component:default/app",
                                 "context_hash": "sha256:abc", "fetched_at": "2026-01-01",
                                 "edges": [{"ref": "dependsOn component:default/db",
                                            "direction": "outbound", "attributes": {"tier": "1"}}],
                                 "truncated": {"inbound": 0, "outbound": 0}}
    p = page(report)
    sections = p.text("h2")
    assert sections == ["Run warnings", "Not scanned", "Service context", "Pattern coverage",
                        "Hotspots investigated with no finding", "Incomplete",
                        "Ranked hotspots", "Dormant integration points"]
    body = p.page.inner_text("#doc")
    assert "no finding of its own; cited as evidence by FR-001" in body
    assert "a warning" in body and "S15-x on a.ts: 1 hit(s) — r" in body
    assert p.text("details.warn summary") == ["1 run warning"]


@pytest.mark.parametrize("clean,incomplete,expected", [
    (2, 0, "No findings: all 2 investigated hotspots came back clean."),
    (1, 2, "No findings, but 2 of 3 hotspots could not be analysed. See Incomplete."),
    (0, 2, "No hotspot could be analysed. This report says nothing about the code."),
    (0, 0, "No hotspot was investigated. This report says nothing about the code."),
])
def test_a_report_without_findings_says_what_happened(page, scanned_copy, plugin_root,
                                                      clean, incomplete, expected):
    report = _report(scanned_copy, plugin_root)
    report["findings"] = []
    report["clean"] = [{"hotspot_id": f"H0{i}", "file": f"c{i}.ts", "notes": "",
                        "cited_by": [], "url": None} for i in range(clean)]
    report["incomplete"] = [{"hotspot_id": f"H1{i}", "file": f"i{i}.ts", "reason": "failed",
                             "url": None} for i in range(incomplete)]
    p = page(report)
    assert p.text(".status") == [expected]
    if incomplete:
        assert "came back clean" not in p.page.inner_text("body")


def _two_findings(report: dict) -> dict:
    second = copy.deepcopy(report["findings"][0])
    second.update(id="FR-002", key="k-second", confidence="medium",
                  failure_mode="the second failure")
    report["findings"].append(second)
    return report


def test_filter_and_keyboard_stepping(page, scanned_copy, plugin_root):
    report = _two_findings(_report(scanned_copy, plugin_root))
    p = page(report)
    first = report["findings"][0]
    p.page.keyboard.press("j")
    assert p.text("h1") == [first["failure_mode"]]
    p.page.keyboard.press("j")
    assert p.text("h1") == ["the second failure"]
    p.page.keyboard.press("k")
    assert p.text("h1") == [first["failure_mode"]]
    p.page.get_by_role("button", name="Medium", exact=True).click()
    ids = p.text(".item .item-top .mono")
    assert ids == ["Overview", "FR-002"], ids


def test_reviewed_marks_survive_a_reload(page, scanned_copy, plugin_root):
    p = page(_two_findings(_report(scanned_copy, plugin_root)))
    p.page.keyboard.press("j")
    p.page.keyboard.press("r")
    assert "1 of 2 reviewed" in p.page.inner_text("#head")
    p.page.reload()
    assert "1 of 2 reviewed" in p.page.inner_text("#head")
    assert len(p.page.query_selector_all(".item.reviewed")) == 1


def test_copy_button_names_the_verify_command(page, scanned_copy, plugin_root):
    report = _report(scanned_copy, plugin_root)
    p = page(report)
    p.page.keyboard.press("j")
    fid = report["findings"][0]["id"]
    assert p.text(".cmd code") == [f"/thunderstruck-verify {fid}"]
    from playwright.sync_api import expect
    p.context.grant_permissions(["clipboard-read", "clipboard-write"])
    button = p.page.locator(".cmd button")
    button.click()
    expect(button).to_have_text("Copied")  # waits for the clipboard promise
    assert p.page.evaluate("navigator.clipboard.readText()") == f"/thunderstruck-verify {fid}"


def test_an_unrendered_template_shows_no_report_data(browser, tmp_path):
    dest = tmp_path / "raw.html"
    template = report_html.TEMPLATE.read_text(encoding="utf-8")
    dest.write_text(template.replace(report_html.HASH_PLACEHOLDER,
                                     report_html.script_hash(template)), encoding="utf-8")
    p = Page(browser, dest)
    try:
        assert "No report data" in p.page.inner_text("body")
        assert p.requests == [p.url]
    finally:
        p.close()
