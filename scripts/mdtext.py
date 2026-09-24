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

_LINE_BREAKS = re.compile(r"[\r\n\t\v\f  ]+")
_BACKTICKS = re.compile(r"`+")

# Substrings a renderer turns into links, or GitHub rewrites, whatever the
# escaping: autolinks run on text nodes after parsing. These are shown as
# code spans instead, which no renderer linkifies. Domain-like tokens are
# included because linkify-it (VS Code's preview) links bare `api.example.com`
# and even `deploy.py` (.py is a country TLD).
_LINKISH = re.compile(
    r"(?:(?:https?|ftp)://|www\.|mailto:|xmpp:)\S+"                 # scheme and www. links
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"                                 # e-mail addresses
    r"|(?<![\w@])[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b(?:[/:?#]\S*)?"  # domain-like tokens
    r"|:[a-z0-9_+-]+:",                                              # emoji shortcodes
    re.IGNORECASE)

# ASCII punctuation CommonMark/GFM/GitHub give meaning to inline; each may be
# backslash-escaped, and then renders as itself.
_INLINE_SPECIAL = frozenset("\\`*_[]<>|~&$")


def _flatten(value: Any) -> str:
    return _LINE_BREAKS.sub(" ", "—" if value is None else str(value))


def code(value: Any, cell: bool = False) -> str:
    """A code span showing `value` verbatim, whatever it contains.

    The fence is one backtick longer than the longest run inside, padded when
    the text starts or ends with a backtick. In a GFM table cell a pipe splits
    the cell even inside a code span, so it is escaped there.
    """
    text = _flatten(value)
    fence = "`" * (max((len(r) for r in _BACKTICKS.findall(text)), default=0) + 1)
    pad = " " if text[:1] == "`" or text[-1:] == "`" else ""
    if cell:
        text = text.replace("|", "\\|")
    return f"{fence}{pad}{text}{pad}{fence}"


def linked(value: Any, url: str | None, cell: bool = False) -> str:
    """A tool-generated link whose text is a code span, or the span alone."""
    span = code(value, cell)
    return f"[{span}]({url})" if url else span


def _escape(chunk: str, heading: bool) -> str:
    special = _INLINE_SPECIAL | {"#"} if heading else _INLINE_SPECIAL
    return "".join("\\" + ch if ch in special else ch for ch in chunk)


def text(value: Any, cell: bool = False, heading: bool = False) -> str:
    """Prose that renders as exactly its own characters, on one line.

    Line breaks become spaces; link-like substrings become code spans; the
    remaining Markdown punctuation is backslash-escaped.
    """
    flat = _flatten(value)
    out: list[str] = []
    pos = 0
    for m in _LINKISH.finditer(flat):
        out.append(_escape(flat[pos:m.start()], heading))
        out.append(code(m.group(0), cell))
        pos = m.end()
    out.append(_escape(flat[pos:], heading))
    return "".join(out)
