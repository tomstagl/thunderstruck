"""#28: the Markdown primitives keep untrusted text inert. Unit tests, plus a
real GFM-like renderer (markdown-it-py with linkify, stricter than GitHub:
it also links bare domains, as VS Code's preview does)."""

from __future__ import annotations

import os
from html.parser import HTMLParser

import pytest

import mdtext


RENDERER_MODULES = ("markdown_it", "linkify_it", "cmarkgfm")


def _require_renderers() -> None:
    """Skip locally when the renderers are missing; fail in CI, which sets
    THUNDERSTRUCK_REQUIRE_RENDERER so these tests can never silently skip."""
    import importlib
    missing = []
    for name in RENDERER_MODULES:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing and os.environ.get("THUNDERSTRUCK_REQUIRE_RENDERER"):
        pytest.fail(f"renderer packages missing: {missing}")
    if missing:
        pytest.skip(f"renderer packages missing: {missing}")


def _renderer():
    _require_renderers()
    from markdown_it import MarkdownIt
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


def _parse(html: str) -> _Html:
    parsed = _Html()
    parsed.feed(html)
    return parsed


def render(markdown: str) -> _Html:
    """markdown-it with linkify: stricter than GitHub (links bare domains, as
    VS Code's preview does)."""
    return _parse(_renderer().render(markdown))


def render_gh(markdown: str) -> _Html:
    """cmark-gfm, GitHub's own engine, with its autolink and table extensions."""
    _require_renderers()
    import cmarkgfm
    from cmarkgfm.cmark import Options
    return _parse(cmarkgfm.github_flavored_markdown_to_html(markdown, options=Options.CMARK_OPT_UNSAFE))


RENDERERS = [render, render_gh]


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
    """What a reader sees: controls made visible, whitespace collapsed and trimmed."""
    return " ".join(mdtext._visible(" ".join(s.splitlines())).split())


@pytest.mark.parametrize("renderer", RENDERERS)
@pytest.mark.parametrize("payload", HOSTILE)
def test_hostile_prose_renders_as_its_own_characters(payload, renderer):
    html = renderer(mdtext.text(payload))
    assert set(html.tags) <= {"p", "code"}, html.tags
    assert _flat("".join(html.text)) == _flat(payload)


@pytest.mark.parametrize("renderer", RENDERERS)
@pytest.mark.parametrize("payload", HOSTILE + ["# not a heading", "--- not a rule", "+ nor a list",
                                               "1. nor this", "2) nor this", "> nor a quote",
                                               "    not code", "= setext"])
def test_hostile_text_is_safe_as_list_item_content(payload, renderer):
    html = renderer(f"- {mdtext.text(payload)}\n- next")
    assert html.tags.count("li") == 2 and set(html.tags) <= {"ul", "li", "code", "p"}, html.tags


@pytest.mark.parametrize("renderer", RENDERERS)
@pytest.mark.parametrize("payload", HOSTILE)
def test_hostile_text_keeps_a_table_row_intact(payload, renderer):
    row = f"| {mdtext.text(payload, cell=True)} | {mdtext.code(payload, cell=True)} |"
    html = renderer("| a | b |\n|---|---|\n" + row)
    assert html.tags.count("tr") == 2 and html.tags.count("td") == 2, html.tags
    assert set(html.tags) <= {"table", "thead", "tbody", "tr", "th", "td", "code"}, html.tags
    assert "a" not in html.tags and "img" not in html.tags


@pytest.mark.parametrize("renderer", RENDERERS)
@pytest.mark.parametrize("payload", HOSTILE)
def test_hostile_heading_stays_one_heading(payload, renderer):
    html = renderer(f"### FR-001 · {mdtext.text(payload, heading=True)}\n\nnext")
    assert html.tags.count("h3") == 1 and html.tags.count("p") == 1, html.tags
    assert _flat("".join(html.text)).startswith("FR-001 · " + _flat(payload))


@pytest.mark.parametrize("renderer", RENDERERS)
@pytest.mark.parametrize("payload", HOSTILE + [" a ", "`", " ` "])
def test_code_spans_show_anything_verbatim(payload, renderer):
    html = renderer(mdtext.code(payload))
    assert html.tags == ["p", "code"], html.tags
    assert "".join(html.text).rstrip("\n") == mdtext._visible(" ".join(payload.splitlines()))


def test_linked_is_the_only_way_to_make_a_link():
    html = render(mdtext.linked("a.ts:1", "https://github.com/acme/x/blob/abc/a.ts#L1"))
    assert html.tags == ["p", "a", "code"]
    assert mdtext.linked("a.ts:1", None) == "`a.ts:1`"


@pytest.mark.parametrize("value, expected", [
    ("plain words", "plain words"),
    ("a_b*c", "a\\_b\\*c"),
    ("x # y", "x # y"),
    (None, "—"),
    ("", "—"),
    ("   ", "—"),
    (42, "42"),
    ("two\n\nlines\tand tab", "two lines and tab"),
    ("- item", "\\- item"),
    ("12. step", "12\\. step"),
    ("# title", "\\# title"),
    ("rtl\u202eevil", "rtl\\\\u202eevil"),   # shown as the text \u202e
    ("nul\x00", "nul\\\\u0000"),
])
def test_text_escapes_only_what_it_must(value, expected):
    assert mdtext.text(value) == expected


def test_heading_mode_escapes_hashes():
    assert mdtext.text("fails ##", heading=True) == "fails \\#\\#"


@pytest.mark.parametrize("value, expected", [
    ("a`b", "``a`b``"),
    ("`a", "`` `a ``"),
    ("x\ny", "`x y`"),
    (None, "—"),
    ("", "—"),
    (" a ", "`  a  `"),
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



@pytest.mark.parametrize("payload", ["HTTP://E.CO/x.png", "Http://evil.com", "WWW.E.CO",
                                     "_@.h", "a@.b", "a@b.co:smile:", "':smile:www.e.co``",
                                     "x:https://evil.com/p.png", "see //localhost:8080/x",
                                     "//127.0.0.1/a", "(//169.254.169.254/latest)", "}//10.0.0.1:80"])
@pytest.mark.parametrize("renderer", RENDERERS)
def test_review_payloads_stay_inert(payload, renderer):
    """Found in the design review: case, fence merging, GFM's broad e-mails,
    and an emoji pattern swallowing a URL scheme."""
    html = renderer(mdtext.text(payload))
    assert "a" not in html.tags and "img" not in html.tags, (mdtext.text(payload), html.tags)
    assert _flat("".join(html.text)) == _flat(payload)


def test_times_are_not_emoji():
    assert mdtext.text("at 10:30:45") == "at 10:30:45"


@pytest.mark.parametrize("code", [":+1:", ":-1:", ":100:", ":1234:"])
def test_letterless_github_emoji_are_code(code):
    assert mdtext.text(f"ok {code}") == f"ok `{code}`"


@pytest.mark.parametrize("char", ["\u061c", "\x9b", "\u202e", "\u2066"])
def test_bidi_marks_and_c1_controls_are_visible(char):
    assert mdtext.text(f"a{char}b") == f"a\\\\u{ord(char):04x}b"


@pytest.mark.parametrize("renderer", RENDERERS)
def test_fuzzed_text_stays_inert(renderer):
    """A seeded property test: random mixes of Markdown-significant fragments."""
    import random
    rng = random.Random(28)
    parts = ["[", "]", "(", ")", "!", "<", ">", "`", "``", "*", "_", "~", "|", "&", "#", "$",
             ":", "@", ".", "/", "\\", "-", "+", "=", "1.", " ", "\n", "\t", "a", "b", "co",
             "http://", "HTTPS://", "www.", "mailto:", "x.io", "smile", "e.co", "&copy;", "<img>",
             "//", "localhost", "127.0.0.1", ":1234:", "</sub>", "<!--", "]:", "**", "__"]
    for _ in range(400):
        payload = "".join(rng.choice(parts) for _ in range(rng.randint(1, 14)))
        # every position report.py puts untrusted text in
        positions = {
            "paragraph": (mdtext.text(payload), set()),
            "list item": (f"- {mdtext.text(payload)}", set()),
            "nested item": (f"- a\n  - {mdtext.text(payload)}", set()),
            "cell": ("| a |\n|---|\n| " + mdtext.text(payload, cell=True) + " |", set()),
            "heading": (f"### FR-001 · {mdtext.text(payload, heading=True)}", {"h3"}),
            "bold": (f"**{mdtext.text(payload)}** · x", {"strong"}),
            "emphasis": (f"- _{mdtext.text(payload)}_ x", {"em"}),
            "sub": (f"<sub>key {mdtext.code(payload)}</sub>", {"sub"}),
        }
        for position, (markdown, own) in positions.items():
            html = renderer(markdown)
            bad = ({"a", "img", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "pre", "blockquote",
                    "ol", "strong", "em", "del", "script", "b"} - own) & set(html.tags)
            assert not bad, (position, payload, markdown, html.tags)
            for tag in own:
                assert html.tags.count(tag) == 1, (position, payload, markdown, html.tags)
            if position in ("paragraph", "list item"):
                assert _flat("".join(html.text)) in (_flat(payload), "—"), (payload, markdown)
