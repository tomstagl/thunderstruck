"""#108: a finding becomes a ticket someone can act on.

Small git repositories are built in a temporary directory with a hand-made
report.json, so each condition (a stale file, a hostile snippet, a missing
link setting) is exercised on its own; one test runs the real pipeline over
the fixture."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c
import mdtext
from test_mdtext import RENDERERS, render

ROOT = Path(__file__).resolve().parent.parent


# --- Task 1: the fence and tracker references in mdtext ---------------------

HOSTILE_LINES = [
    "const a = 1;",
    "```",
    "````js",
    "    ``` still not the end of the fence",
    "# not a heading",
    "- not a list item",
    "[click](https://evil.example) ![i](https://evil.example/x.png) <img src=x onerror=1> <script>alert(1)</script>",
    "x" * 5000,
    "tab\there  and trailing spaces  ",
    "lone\rcr, bidi ‮ reversed, escape \x1b[31m",
]


def test_verbatim_fence_is_longer_than_any_backtick_run_inside():
    block, escaped = mdtext.verbatim(HOSTILE_LINES)
    rows = block.split("\n")
    assert rows[0] == "`" * 5 == rows[-1]          # the longest run is four
    assert escaped == 3                              # the lone \r, the bidi mark, the escape
    assert mdtext.verbatim(["plain"]) == ("```\nplain\n```", 0)
    assert mdtext.verbatim(["a `b` c"])[0].startswith("```\n")


@pytest.mark.parametrize("renderer", RENDERERS, ids=lambda r: r.__name__)
def test_a_verbatim_block_is_one_code_block_whatever_it_holds(renderer):
    block, _ = mdtext.verbatim(HOSTILE_LINES)
    html = renderer(f"before\n\n{block}\n\nafter")
    assert html.tags == ["p", "pre", "code", "p"], html.tags
    shown = "".join(html.text)
    assert "evil.example" in shown and "# not a heading" in shown
    body = shown.split("before", 1)[1].rsplit("after", 1)[0]
    assert "‮" not in body and "\x1b" not in body and "\r" not in body
    assert "\\u202e" in body and "\\u001b" in body and "\\u000d" in body
    assert "\t" in body and "  \n" in body            # tabs and trailing spaces are kept


def test_verbatim_keeps_every_other_character_as_written():
    lines = ["  indented", "", "naïve — ünïcode ✓", "x = '\"'; y = `z`"]
    block, escaped = mdtext.verbatim(lines)
    assert escaped == 0
    assert block.split("\n")[1:-1] == lines


@pytest.mark.parametrize("token, shown", [
    ("#12", "`#12`"), ("(#12),", "(`#12`),"), ("!7", "`!7`"), ("ABC-123", "`ABC-123`"),
    ("acme/api#12", "`acme/api#12`"), ("PR#7", "`PR#7`"), ("group/proj!3", "`group/proj!3`"),
    ("a1b2c3d", "`a1b2c3d`"), ("0a1b2c3d4e5f60718293a4b5c6d7e8f901234567",
                               "`0a1b2c3d4e5f60718293a4b5c6d7e8f901234567`"),
])
def test_a_tracker_reference_becomes_a_code_span(token, shown):
    assert mdtext.text(f"see {token} now") == f"see {shown} now"


@pytest.mark.parametrize("word", ["10:30:45", "C#", "2000000", "1234567", "decade", "defaced", "deadbeef",
                                  "plain", "a-b", "v1.2", "utf-8", "sha-256", "x86-64", "line-5"])
def test_ordinary_words_and_numbers_are_left_alone(word):
    """A key needs capitals (not utf-8), a sha needs a digit and a letter (not a word made of
    a-f), and a run of digits alone is a number."""
    assert mdtext.text(f"see {word} now") == f"see {word} now"
