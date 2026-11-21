"""Markdown primitives that keep untrusted text inert (#28).

report.md is built from text a model or a scanned repository wrote. Every
such value goes through one of these, so it is shown exactly as written and
can never become a link, an image, HTML, or report structure. Only the tool
itself creates links (`linked`) and structure.

Stdlib only.
"""

from __future__ import annotations

import re
from typing import Any

_WHITESPACE_RUN = re.compile(r"[ \t]+")
_BACKTICKS = re.compile(r"`+")
# C0/C1 controls, DEL, and bidi marks/overrides/isolates: shown as visible \\uXXXX, so a
# field can't hide characters or reverse what the reader sees.
_INVISIBLE = re.compile("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f-\\x9f\\u061c\\u200e\\u200f\\u202a-\\u202e\\u2066-\\u2069]")
# Inside a code block a lone carriage return is a line break to a renderer, so it is shown too.
_INVISIBLE_BLOCK = re.compile(_INVISIBLE.pattern + "|\r")

# A renderer turns substrings into links whatever the escaping: autolinks run
# on text nodes after parsing (GFM: http(s)://, www., e-mail; linkify-it, as in
# VS Code's preview, also bare domains such as api.example.com or deploy.py,
# since .py is a country TLD). No renderer links across whitespace, so each
# whitespace-separated token that could hold such a link is shown whole as a
# code span, which nothing linkifies. GitHub's emoji shortcodes likewise.
_TOKEN = re.compile(r"\S+")
_LINKISH = re.compile(
    r"://|//|www\.|mailto:|xmpp:|@"            # scheme, protocol-relative, www., e-mail
    r"|\.[^\W\d_]{2}"                           # a dot then two letters: a domain-like word
    r"|:[a-z0-9_+-]*[a-z][a-z0-9_+-]*:"          # emoji shortcode (needs a letter: not 10:30:45)
    r"|:[+-]1:|:100:|:1234:"                     # ...and GitHub's letterless ones
    # A tracker links these after rendering, and a link into someone's issue notifies it (#108):
    r"|[#!][0-9]"                                # an issue or merge request, here or in another repository: #12, acme/api#12, PR#7, group/proj!3
    r"|(?-i:\b[A-Z][A-Z0-9]+-[0-9])"             # a Jira-style key: ABC-123 (capitals only: not utf-8 or sha-256)
    r"|\b(?=[0-9a-f]*[0-9])(?=[0-9]*[a-f])[0-9a-f]{7,40}\b",  # a commit sha: a digit and a letter (a run of digits alone is a number)
    re.IGNORECASE)

# Sentence punctuation peeled off a linkish token, so the span wraps only the
# word: "(x.co)," renders as (`x.co`), not `(x.co),`. None of it can start a
# link or a shortcode on its own.
_CLOSERS = {")": "(", "]": "[", "}": "{"}
_PEEL = re.compile(r"^([(\[{\"']*)(.*?)([)\]},;:.!?\"']*)$", re.DOTALL)

# ASCII punctuation CommonMark/GFM/GitHub give meaning to inline; each may be
# backslash-escaped, and then renders as itself.
_INLINE_SPECIAL = frozenset("\\`*_[]<>|~&$")
# What would open a block if the text started a line or a list item's content.
_BLOCK_START = re.compile(r"^(?:[#+=>-]|[0-9]+[.)])")


def _visible(text: str) -> str:
    return _INVISIBLE.sub(lambda m: f"\\u{ord(m.group(0)):04x}", text)


def _flatten(value: Any) -> str:
    """One line, controls made visible, runs of spaces and tabs collapsed."""
    text = "—" if value is None else str(value)
    return _WHITESPACE_RUN.sub(" ", _visible(" ".join(text.splitlines())))


def code(value: Any, cell: bool = False) -> str:
    """A code span showing `value` verbatim, whatever it contains.

    The fence is one backtick longer than the longest run inside. A space is
    padded on both sides when the text starts or ends with a backtick or a
    space, because CommonMark strips one such space. In a GFM table cell a pipe
    splits the cell even inside a code span, so it is escaped there.
    """
    if value is None:
        return "—"
    text = _visible(" ".join(str(value).splitlines()))
    if not text.strip():
        return "—"
    fence = "`" * (max((len(r) for r in _BACKTICKS.findall(text)), default=0) + 1)
    pad = " " if text[:1] in "` " or text[-1:] in "` " else ""
    if cell:
        text = text.replace("|", "\\|")
    return f"{fence}{pad}{text}{pad}{fence}"


def verbatim(lines: list[str]) -> tuple[str, int]:
    """A fenced code block showing `lines` as written, and how many characters it
    had to show as \\uXXXX (controls, bidirectional marks, a lone carriage return).

    The fence is backticks, one more than the longest run in any line and at
    least three, with no info string, so no line can end it. It is a block of its
    own: put it at the start of a line, never inside a list item.
    """
    escaped = 0

    def show(m: re.Match) -> str:
        nonlocal escaped
        escaped += 1
        return f"\\u{ord(m.group(0)):04x}"

    body = [_INVISIBLE_BLOCK.sub(show, line) for line in lines]
    longest = max((len(run) for line in body for run in _BACKTICKS.findall(line)), default=0)
    fence = "`" * max(3, longest + 1)
    return "\n".join([fence, *body, fence]), escaped


def linked(value: Any, url: str | None, cell: bool = False) -> str:
    """A tool-generated link whose text is a code span, or the span alone."""
    span = code(value, cell)
    return f"[{span}]({url})" if url else span


def _escape(chunk: str, heading: bool) -> str:
    special = _INLINE_SPECIAL | {"#"} if heading else _INLINE_SPECIAL
    return "".join("\\" + ch if ch in special else ch for ch in chunk)


def _word(token: str, cell: bool, heading: bool) -> str:
    if not _LINKISH.search(token):
        return _escape(token, heading)
    lead, core, trail = _PEEL.match(token).groups()
    if not core or not _LINKISH.search(core):
        lead, core, trail = "", token, ""
    # A closing bracket the word itself opened belongs to it: "timeout(8000)"
    # keeps its ")", while "(x.co)" gives its ")" back to the sentence.
    while trail and trail[0] in _CLOSERS and core.count(_CLOSERS[trail[0]]) > core.count(trail[0]):
        core, trail = core + trail[0], trail[1:]
    return _escape(lead, heading) + code(core, cell) + _escape(trail, heading)


def text(value: Any, cell: bool = False, heading: bool = False) -> str:
    """Prose that renders as exactly its own characters, on one line.

    Line breaks become spaces; any word that could hold a link becomes a code span,
    with its surrounding sentence punctuation left outside; the
    remaining Markdown punctuation is backslash-escaped; and a leading block
    marker (#, -, +, =, >, "1." / "1)") is escaped, so the text is safe even
    at the start of a line or a list item.
    """
    flat = _flatten(value).strip()
    if not flat:
        return "—"
    out: list[str] = []
    pos = 0
    for m in _TOKEN.finditer(flat):
        out.append(flat[pos:m.start()])
        token = m.group(0)
        out.append(_word(token, cell, heading))
        pos = m.end()
    rendered = "".join(out)
    if (m := _BLOCK_START.match(rendered)):
        end = m.end()
        rendered = rendered[:end - 1] + "\\" + rendered[end - 1:]
    return rendered
