"""#107: the fix instructions and the review briefs are the maintainer's.

These tests read both documents and never change them: harness neutrality,
the behaviours each must state, their links, their published paths, and that
a scan does not read them. The checks live in tests/guidance_check.py; the
rules and the pinned quotes are data in tests/guidance/."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import guidance_check as g

ROOT = Path(__file__).resolve().parent.parent
RULES = g.load_rules()
BY_ID = {r.id: r for r in RULES}


# --- Task 1: the neutrality rules, proven on samples -------------------------

def test_every_rule_has_a_positive_and_a_negative_sample():
    thin = [r.id for r in RULES if not r.positive or not r.negative]
    assert not thin, f"rules without both samples: {thin}"


@pytest.mark.parametrize(
    "rule, sample",
    [pytest.param(r, s, id=f"{r.id}-positive-{i}") for r in RULES for i, s in enumerate(r.positive)])
def test_a_positive_sample_trips_its_own_rule(rule, sample):
    assert [h.rule for h in g.lint(sample, [rule])] == [rule.id], sample


NEGATIVES = (
    [pytest.param(s, id=f"{r.id}-negative-{i}") for r in RULES for i, s in enumerate(r.negative)]
    + [pytest.param(s, id=f"legitimate-{i}") for i, s in enumerate(g.load_legitimate())])


@pytest.mark.parametrize("sample", NEGATIVES)
def test_a_negative_sample_trips_no_rule(sample):
    assert g.lint(sample, RULES) == [], sample


def test_plugin_names_are_read_from_the_tree():
    components = g.plugin_components(ROOT)
    assert "thunderstruck-scan" in components and "thunderstruck-skeptic" in components
    for name in components:
        assert g.lint(f"/{name}", [BY_ID["N20"]]), name
    scripts = sorted(p.name for p in (ROOT / "scripts").glob("*.py"))
    assert scripts
    bare_ok = g.load_bare_ok()
    for name in scripts:
        assert g.lint(f"`scripts/{name}`", [BY_ID["N21"]]), name
        assert bool(g.lint(f"`{name}`", [BY_ID["N21"]])) == (name not in bare_ok), name
    assert bare_ok & set(scripts), "bare_ok lists no script of the tree"


def test_a_scan_output_name_is_not_a_plugin_path_but_the_scan_directory_is():
    assert not g.lint("Write your report to `report.md` and `index.json`.", [BY_ID["N21"]])
    assert [h.rule for h in g.lint("Look in `.thunderstruck/report.json`.", RULES)] == ["N02"]


def test_a_phrase_wrapped_across_lines_is_still_found():
    hits = g.lint("Open the file with the Read\ntool and look.\n", [BY_ID["N06"]])
    assert [(h.line, h.rule) for h in hits] == [(1, "N06")]


def test_a_hit_names_its_line_and_rule():
    text = "# Title\n\nA clean paragraph.\n\nUse `${CLAUDE_PLUGIN_ROOT}/scripts/report.py`.\n"
    hits = g.lint(text, RULES)
    assert {(h.line, h.rule) for h in hits} >= {(5, "N01"), (5, "N21")}
    assert all(h.excerpt for h in hits)


def test_code_fences_are_linted_line_by_line():
    text = "Run it:\n\n```sh\nuv run scripts/validate.py\n```\n"
    assert [(h.line, h.rule) for h in g.lint(text, RULES)] == [(4, "N21")]


def test_blocks_split_headings_paragraphs_items_rows_and_code():
    text = ("# T\n\nA first\nparagraph.\n\n- item one\n  continues\n- item two\n\n"
            "| a | b |\n|---|---|\n\n```sh\nrun x\n```\n")
    got = [(b.kind, b.line, b.text) for b in g.blocks(text)]
    assert got == [("heading", 1, "T"), ("paragraph", 3, "A first paragraph."),
                   ("item", 6, "item one continues"), ("item", 8, "item two"),
                   ("row", 10, "a | b"), ("row", 11, "---|---"), ("code", 14, "run x")]


def test_a_block_knows_its_last_line():
    text = "# T\n\nA first\nparagraph.\n\n- item one\n  continues\n- item two\n\n```sh\nrun x\n```\n"
    assert [(b.kind, b.line, b.end) for b in g.blocks(text)] == [
        ("heading", 1, 1), ("paragraph", 3, 4), ("item", 6, 7), ("item", 8, 8), ("code", 11, 11)]


def test_a_heading_carries_its_level_without_the_marks():
    got = [(b.level, b.text) for b in g.blocks("# One\n## Two ##\n###   Three  \n")]
    assert got == [(1, "One"), (2, "Two"), (3, "Three")]


def test_front_matter_makes_a_file_not_a_plain_document():
    assert g.has_front_matter("---\nname: x\ndescription: y\n---\n# Body\n")
    assert not g.has_front_matter("# Body\n\n---\n\nA rule above is not front matter.\n")
    assert not g.has_front_matter("---\nno closing line\n")
