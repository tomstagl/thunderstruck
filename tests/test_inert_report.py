"""#28 end to end: hostile text in every field a model or the scanned
repository writes reaches report.md as inert text. The only links left are
the tool's own evidence links."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import report
from test_mdtext import render
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding

LINK_BASE = "https://github.com/acme/fixture/"

HOSTILE = ("x](https://evil.example) ![](https://tracker.example/p.png) <img src=x> "
           "| broken | row | \n# fake heading\n- fake item :smile: $x$ ~~s~~ www.evil.example")

MODEL_FIELDS = ("failure_mode", "trigger_condition", "amplifier", "sustaining_effect",
                "blast_radius", "how_to_verify", "confidence_rationale", "prediction")


def _assert_inert(markdown: str) -> None:
    html = render(markdown)
    links = [t for t in html.tags if t == "a"]
    assert "img" not in html.tags
    allowed = {"h1", "h2", "h3", "p", "strong", "em", "code", "ul", "li", "table", "thead",
               "tbody", "tr", "th", "td", "hr", "blockquote", "a", "sub", "br"}
    assert set(html.tags) <= allowed, set(html.tags) - allowed
    hrefs = _hrefs(markdown)
    assert len(hrefs) == len(links)
    assert all(h.startswith(LINK_BASE) for h in hrefs), hrefs
    assert "evil.example" not in "".join(hrefs) and "tracker.example" not in "".join(hrefs)


def _hrefs(markdown: str) -> list[str]:
    from html.parser import HTMLParser
    import test_mdtext

    class Hrefs(HTMLParser):
        def __init__(self):
            super().__init__()
            self.hrefs: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.hrefs.append(dict(attrs).get("href", ""))
    parser = Hrefs()
    parser.feed(test_mdtext._renderer().render(markdown))
    return parser.hrefs


def test_hostile_model_text_stays_inert(linked_copy, plugin_root):
    hid, doc = _valid_finding(linked_copy, _hotspots(linked_copy))
    finding = doc["findings"][0]
    for field in MODEL_FIELDS:
        finding[field] = f"{field}: {HOSTILE}"
    finding["location"]["symbol"] = "sym`bol](https://evil.example)"
    for ev in finding["evidence"]:
        ev["note"] = f"note: {HOSTILE}"
    _write_finding(linked_copy, hid, doc)
    assert _validate(linked_copy, plugin_root).returncode == 0
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(linked_copy)], check=True, capture_output=True)
    markdown = (linked_copy / ".thunderstruck" / "report.md").read_text()
    _assert_inert(markdown)
    html = render(markdown)
    assert html.tags.count("h3") == 1, "a field must not add a heading"
    finding_table_rows = markdown.split("### FR-001", 1)[1].split("**Evidence**", 1)[0]
    assert render(finding_table_rows).tags.count("tr") == 6, "one row per field, none added"
    assert "fake heading" in "".join(html.text) and "fake item" in "".join(html.text)


def test_hostile_repository_names_stay_inert(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    data = report.collect(scanned_copy)
    hs = data["hotspots"]
    hs["repo"]["root"] = str(Path("/tmp") / "repo](https://evil.example)")
    hs["repo"]["branch"] = "feat/`x`](https://evil.example)"
    hs["window"]["since"] = "12m](https://evil.example)"
    hs["warnings"] = [f"warning: {HOSTILE}"]
    hs["hotspots"][0]["file"] = "src/`a`|b](https://evil.example).ts"
    data["clean"] = [{"hotspot_id": "H98", "file": "c|d.ts", "notes": HOSTILE}]
    data["failed"] = [{"hotspot_id": "H99", "file": "e.ts", "reason": HOSTILE,
                       "errors": [HOSTILE]}]
    markdown = report.render_markdown(data, scanned_copy)
    _assert_inert(markdown)
    ranked = markdown.split("## Ranked hotspots", 1)[1]
    rows = render(ranked).tags.count("tr")
    assert rows == len(hs["hotspots"]) + 1, "a hostile file name must not split the row"
