"""#28 end to end: hostile text in every field a model or the scanned
repository writes reaches report.md as inert text. The only links left are
the tool's own evidence links."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import report
from test_mdtext import RENDERERS, render
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding

LINK_BASE = "https://github.com/acme/fixture/"

HOSTILE = ("x](https://evil.example) ![](https://tracker.example/p.png) <img src=x> "
           "| broken | row | \n# fake heading\n- fake item :smile: $x$ ~~s~~ www.evil.example")

MODEL_FIELDS = ("failure_mode", "trigger_condition", "amplifier", "sustaining_effect",
                "blast_radius", "how_to_verify", "confidence_rationale", "prediction")


def _assert_inert(markdown: str) -> None:
    allowed = {"h1", "h2", "h3", "p", "strong", "em", "code", "ul", "li", "table", "thead",
               "tbody", "tr", "th", "td", "hr", "blockquote", "a", "sub", "br"}
    for renderer in RENDERERS:
        html = renderer(markdown)
        assert "img" not in html.tags
        assert set(html.tags) <= allowed, (renderer.__name__, set(html.tags) - allowed)
    hrefs = _hrefs(markdown)
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
    import cmarkgfm
    from cmarkgfm.cmark import Options
    hrefs: list[str] = []
    for html in (test_mdtext._renderer().render(markdown),
                 cmarkgfm.github_flavored_markdown_to_html(markdown, options=Options.CMARK_OPT_UNSAFE)):
        parser = Hrefs()
        parser.feed(html)
        hrefs += parser.hrefs
    return hrefs


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
    hs["suppressed"] = [{"detector": "S06`](https://evil.example)", "path": "src/**|`x`",
                         "reason": f"reason: {HOSTILE}", "hits": 1}]
    hs["hotspots"][0]["file"] = "src/`a`|b](https://evil.example).ts"
    data["clean"] = [{"hotspot_id": "H98", "file": "c|d.ts", "notes": HOSTILE}]
    data["failed"] = [{"hotspot_id": "H99", "file": "e.ts", "reason": HOSTILE,
                       "errors": [HOSTILE, "# fake heading", "--- not a rule"]}]
    # fields the validator checks, rendered safely anyway in case a file skips it
    f = data["findings"][0]
    f.update(confidence="x](https://evil.example)", key="k`<img src=//e.co/>`",
             missing_patterns=["S02", "x`<img src=//e.co/>`"])
    f["evidence"][0]["type"] = "code_ [x](https://evil.example)"
    commits = [ev for ev in f["evidence"] if ev.get("type") == "commit"]
    assert commits and all("subject" in ev for ev in commits), "collect() attaches subjects"
    for ev in commits:  # a commit subject is repository text (#19 AC-3)
        ev.update(subject=f"subject: {HOSTILE}", kind="fix](https://evil.example)")
    data["context"] = {"entity_ref": "component:default/x](https://evil.example)",
                       "context_hash": "`<img src=//e.co/>`", "fetched_at": "<b>2026</b>",
                       "edges": [{"ref": "dependsOn x|y", "direction": "outbound](https://evil.example)",
                                  "attributes": {"tier": "1 | 2"}}], "truncated": {}}
    data["context_warnings"] = ["# fake context heading", f"ctx {HOSTILE}"]
    markdown = report.render_markdown(data, scanned_copy)
    _assert_inert(markdown)
    ranked = markdown.split("## Ranked hotspots", 1)[1].split("\n## ", 1)[0]
    for renderer in RENDERERS:
        rows = renderer(ranked).tags.count("tr")
        assert rows == len(hs["hotspots"]) + 1, "a hostile file name must not split the row"
    assert render(markdown).tags.count("h1") == 1, "a warning must not become a heading"



def test_context_warnings_are_strings_and_capped_visibly():
    many = [f"w{n}" for n in range(25)]
    kept = report._context_warnings([*many, {"not": "a string"}, 7])
    assert kept[:20] == many[:20]
    assert kept[20] == "5 more context warning(s) not shown; see context.json"
    assert len(kept) == 21
    assert report._context_warnings("not a list") == []
    assert report._context_warnings(["a", None, "b"]) == ["a", "b"]


def test_evidence_without_a_note_has_no_dangling_dash(linked_copy, plugin_root):
    hid, doc = _valid_finding(linked_copy, _hotspots(linked_copy))
    for ev in doc["findings"][0]["evidence"]:
        ev.pop("note", None)
    _write_finding(linked_copy, hid, doc)
    assert _validate(linked_copy, plugin_root).returncode == 0
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(linked_copy)], check=True, capture_output=True)
    markdown = (linked_copy / ".thunderstruck" / "report.md").read_text()
    evidence = [line for line in markdown.splitlines() if line.startswith("- _")]
    assert evidence and not any(line.rstrip().endswith("—") for line in evidence), evidence


def test_hostile_linked_file_names_stay_inert(scanned_copy, plugin_root):
    """A file name next to a link is still inert, and never escapes its row."""
    import links
    data = report.collect(scanned_copy)
    hs = data["hotspots"]
    hostile = ["src/`a`|b](https:atk.test).ts", "src/x) [y](javascript:alert(1)) z.ts",
               "src/<img src=x>.ts", "src/www.atk.test :smile:.ts"]
    for h, name in zip(hs["hotspots"], hostile):
        h["file"] = name
    ctx = links.LinkContext.for_provider("github", base=LINK_BASE.rstrip("/"), sha="a" * 40)
    data["clean"] = [{"hotspot_id": "H98", "file": hostile[0], "notes": "n"}]
    data["failed"] = [{"hotspot_id": "H99", "file": hostile[1], "reason": "r"}]
    data["hotspot_links"] = report._set_file_urls(hs["hotspots"], data["clean"] + data["failed"],
                                                  ctx)
    assert all(v["url"] and v["history_url"] for v in data["hotspot_links"].values())
    markdown = report.render_markdown(data, scanned_copy)
    _assert_inert(markdown)
    ranked = markdown.split("## Ranked hotspots", 1)[1].split("\n## ", 1)[0]
    for renderer in RENDERERS:
        html = renderer(ranked)
        assert html.tags.count("tr") == len(hs["hotspots"]) + 1
        assert html.tags.count("a") == 2 * len(hs["hotspots"])
    for section in ("## Hotspots investigated with no finding", "## Incomplete"):
        body = markdown.split(section, 1)[1].split("\n## ", 1)[0]
        for renderer in RENDERERS:
            assert renderer(body).tags.count("a") == 1, (section, renderer.__name__)
