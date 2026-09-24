"""#28: the Markdown primitives keep untrusted text inert. Unit tests, plus a
real GFM-like renderer (markdown-it-py with linkify, stricter than GitHub:
it also links bare domains, as VS Code's preview does)."""

from __future__ import annotations

import os
from html.parser import HTMLParser

import pytest

import mdtext


def _renderer():
    if os.environ.get("THUNDERSTRUCK_REQUIRE_RENDERER"):
        from markdown_it import MarkdownIt  # CI: a missing renderer is a failure
    else:
        MarkdownIt = pytest.importorskip("markdown_it").MarkdownIt
        pytest.importorskip("linkify_it")
    return MarkdownIt("gfm-like")


class _Html(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


def render(markdown: str) -> _Html:
    parsed = _Html()
    parsed.feed(_renderer().render(markdown))
    return parsed


HOSTILE = [
    "[see fix](https://evil.example/x)",
    "![](https://tracker.example/x.png)",
    "<img src=x onerror=alert(1)> <b>bold</b> <details>d</details>",
    "<https://evil.example>",
    "plain https://evil.example/path?q=1 and www.evil.example",
    "mail me at alice@evil.example or mailto:bob@evil.example",
    "calls api.evil.example then deploy.py",
    "*em* _em_ **strong** ~~strike~~ `code` ``double``",
    "&copy; &#60;script&#62; \\ trailing backslash \\",
    "costs $5 and $10, math $x^2$ and $$y$$",
    ":smile: :+1:",
    "a | b | c",
    "line one\nline two\r\n# heading\n- list item\n| row |\n---\n> quote",
    "[x]\n(https://evil.example)",
    "!\\[not an image\\](https://evil.example)",
    "`" * 5 + "fence" + "`" * 3,
    "[^1] footnote and [ref]: https://evil.example",
]


def _flat(s: str) -> str:
    return " ".join(s.split())


@pytest.mark.parametrize("payload", HOSTILE)
def test_hostile_prose_renders_as_its_own_characters(payload):
    html = render(mdtext.text(payload))
    assert set(html.tags) <= {"p", "code"}, html.tags
    assert _flat("".join(html.text)) == _flat(payload)


@pytest.mark.parametrize("payload", HOSTILE)
def test_hostile_text_keeps_a_table_row_intact(payload):
    row = f"| {mdtext.text(payload, cell=True)} | {mdtext.code(payload, cell=True)} |"
    html = render("| a | b |\n|---|---|\n" + row)
    assert html.tags.count("tr") == 2 and html.tags.count("td") == 2, html.tags
    assert set(html.tags) <= {"table", "thead", "tbody", "tr", "th", "td", "code"}, html.tags
    assert "a" not in html.tags and "img" not in html.tags


@pytest.mark.parametrize("payload", HOSTILE)
def test_hostile_heading_stays_one_heading(payload):
    html = render(f"### FR-001 · {mdtext.text(payload, heading=True)}\n\nnext")
    assert html.tags.count("h3") == 1 and html.tags.count("p") == 1, html.tags
    assert _flat("".join(html.text)).startswith("FR-001 · " + _flat(payload))


@pytest.mark.parametrize("payload", HOSTILE)
def test_code_spans_show_anything_verbatim(payload):
    html = render(mdtext.code(payload))
    assert html.tags == ["p", "code"], html.tags
    assert "".join(html.text).strip() == " ".join(payload.replace("\r\n", "\n").split("\n")).strip() \
        or _flat("".join(html.text)) == _flat(payload)


def test_linked_is_the_only_way_to_make_a_link():
    html = render(mdtext.linked("a.ts:1", "https://github.com/acme/x/blob/abc/a.ts#L1"))
    assert html.tags == ["p", "a", "code"]
    assert mdtext.linked("a.ts:1", None) == "`a.ts:1`"


@pytest.mark.parametrize("value, expected", [
    ("plain words", "plain words"),
    ("a_b*c", "a\\_b\\*c"),
    ("x # y", "x # y"),
    (None, "—"),
    (42, "42"),
    ("two\n\nlines\tand tab", "two lines and tab"),
])
def test_text_escapes_only_what_it_must(value, expected):
    assert mdtext.text(value) == expected


def test_heading_mode_escapes_hashes():
    assert mdtext.text("fails ##", heading=True) == "fails \\#\\#"


@pytest.mark.parametrize("value, expected", [
    ("a`b", "``a`b``"),
    ("`a", "`` `a ``"),
    ("x\ny", "`x y`"),
    (None, "`—`"),
])
def test_code_fences(value, expected):
    assert mdtext.code(value) == expected


def test_code_escapes_pipes_only_in_cells():
    assert mdtext.code("a|b") == "`a|b`"
    assert mdtext.code("a|b", cell=True) == "`a\\|b`"


def test_github_only_syntax_is_neutralised():
    """GitHub renders math and emoji shortcodes; markdown-it doesn't, so these
    are asserted on the Markdown itself."""
    assert "\\$x^2\\$" in mdtext.text("math $x^2$")
    assert "\\$\\$y\\$\\$" in mdtext.text("$$y$$")
    assert mdtext.text(":smile: done") == "`:smile:` done"
