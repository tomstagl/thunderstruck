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
# --- Task 2: quotes, inputs, briefs, links and the table, proven on small texts ---

TOY = """# A guide

One paragraph of purpose.

## Inputs

You need the ticket. If an input is missing, stop and ask for it.

## Steps

Write a failing test first and watch it fail.
Write a failing test first, always.

- Make the change as small
  as it can be.
- Report real results.

## Lens

""" + "body " * 25 + "\n"

FIX06 = "fix-06-failing-test-first"
LENS1 = "review-lens-1-state-and-concurrency"


def test_a_whole_sentence_pins_its_row():
    assert g.row_problems(FIX06, TOY, "Write a failing test first and watch it fail.") == []
    assert g.row_problems(FIX06, TOY, "Write a failing test first, always.") == []


def test_a_whole_item_a_whole_cell_and_a_wrapped_item_pin_without_a_sentence_end():
    text = "- Ask first\n- Make the change as small\n  as it can be.\n\nAsk first | Never push | Do not publish\n"
    assert g.row_problems(FIX06, text, "Make the change as small as it can be.") == []
    assert g.row_problems(FIX06, text, "  Make the change\nas small as it can be. ") == []
    assert g.row_problems(FIX06, text, "Never push") == []
    assert g.row_problems(FIX06, text, "Do not publish") == []


def test_a_one_word_sentence_and_a_long_one_both_pin():
    long_sentence = " ".join(["word"] * 60) + "."
    text = f"- Never push.\n\n{long_sentence} Then more.\n"
    assert g.row_problems("fix-11b-never-push", text, "Never push.") == []
    assert g.row_problems("fix-11b-never-push", text, long_sentence) == []


@pytest.mark.parametrize("quote, fragment", [
    (None, "no quote is pinned"),
    ("   ", "no quote is pinned"),
    ("Write a failing test first", "part of a sentence"),
    ("failing test first and watch it fail.", "part of a sentence"),
    ("Write a failing test first and watch it", "part of a sentence"),
    ("Write a failing", "part of a sentence"),
    ("Delete the cache before you start", "is not in the document"),
    ("Report real results. Make the change", "is not in the document"),   # two list items
    ("A guide", "is in a heading"),
])
def test_a_quote_that_does_not_pin_is_refused_with_the_reason(quote, fragment):
    problems = g.row_problems(FIX06, TOY, quote)
    assert len(problems) == 1 and fragment in problems[0], problems
    assert FIX06 in problems[0] and "docs/fix-agent-instructions.md" in problems[0]


def test_markup_belongs_to_the_sentence_it_wraps():
    text = "**Never push.** Ask first.\n"
    assert g.row_problems("fix-11b-never-push", text, "**Never push.**") == []
    assert "part of a sentence" in g.row_problems("fix-11b-never-push", text, "Never push.")[0]


def test_a_repeated_sentence_is_extended_when_a_next_sentence_exists_and_kept_when_not():
    extend = "Never push. Never force-push.\n\n- Never push.\n"
    problems = g.row_problems("fix-11b-never-push", extend, "Never push.")
    assert len(problems) == 1 and "occurs 2 times" in problems[0] and "line 1" in problems[0]
    assert g.row_problems("fix-11b-never-push", extend, "Never push. Never force-push.") == []
    kept = "- Never push.\n\nSee below.\n\n- Never push.\n"
    assert g.row_problems("fix-11b-never-push", kept, "Never push.") == []


def test_a_quote_that_lives_only_in_a_heading_or_code_is_not_prose():
    text = "# T\n\n## Always write a failing test first\n\nSomething else here today.\n\n```sh\nrun the failing test now please\n```\n"
    assert "in a heading" in g.row_problems(FIX06, text, "Always write a failing test first")[0]
    assert "in a code" in g.row_problems(FIX06, text, "run the failing test now please")[0]


def test_taking_a_row_out_deletes_the_matched_block_by_line_not_the_first_words():
    text = ("# Guide\n\nThe lenses are: state and concurrency, callers.\n\n"
            "## State and concurrency\n\nLook at shared state.\n")
    row = "review-lens-1-state-and-concurrency"
    mutated, n = g.without_row(row, text, "State and concurrency")
    assert n == 1 and "The lenses are: state and concurrency" in mutated and "## State" not in mutated
    assert g.row_problems(row, mutated, "State and concurrency")
    twice = "- Never push.\n\nMiddle.\n\n- Never push.\n"
    mutated, n = g.without_row("fix-11b-never-push", twice, "Never push.")
    assert n == 2 and "Never push" not in mutated and "Middle." in mutated


def test_a_heading_row_pins_exactly_one_whole_heading():
    text = "# T\n\n## Lens 1: State\n\ntext\n\n## Lens 1: State\n"
    assert "2 headings" in g.row_problems(LENS1, text, "Lens 1: State")[0]
    assert "0 headings" in g.row_problems(LENS1, text, "Lens 1")[0]
    assert g.row_problems(LENS1, "## Lens 1: State\n", "Lens 1: State") == []
    assert "0 headings" in g.row_problems(LENS1, "Lens 1: State is in a paragraph.\n", "Lens 1: State")[0]


def test_inputs_come_first_and_say_what_to_do_when_one_is_missing():
    ok = g.inputs_problems("fix", TOY, "Inputs", "If an input is missing, stop and ask for it.")
    assert ok == []


@pytest.mark.parametrize("text, heading, missing, fragment", [
    ("# T\n\n## Purpose\n\nx\n\n## Inputs\n\nIf one is missing, stop and ask.\n", "Inputs",
     "If one is missing, stop and ask.", "first heading after the title is 'Purpose'"),
    ("# T\n\n## Inputs\n\nThe ticket.\n\n## Steps\n\nIf one is missing, stop and ask.\n", "Inputs",
     "If one is missing, stop and ask.", "is not inside the section"),
    ("Just text, no headings at all.\n", "Inputs", "stop and ask for it please", "first heading after the title is None"),
])
def test_a_document_that_does_not_begin_with_its_inputs_is_refused(text, heading, missing, fragment):
    problems = g.inputs_problems("fix", text, heading, missing)
    assert len(problems) == 1 and fragment in problems[0], problems


def test_prose_and_a_contents_list_may_come_before_the_inputs_heading():
    text = ("# T\n\nA version note.\n\nA second paragraph of purpose.\n\n- Inputs\n- Steps\n\n"
            "## Inputs\n\nIf one is missing, stop and ask.\n\n## Steps\n\nGo.\n")
    assert g.inputs_problems("fix", text, "Inputs", "If one is missing, stop and ask.") == []


def test_a_document_without_a_title_may_begin_with_its_inputs_section():
    text = "## Inputs\n\nIf one is missing, stop and ask.\n\n## Steps\n\nGo.\n"
    assert g.inputs_problems("review", text, "Inputs", "If one is missing, stop and ask.") == []


def test_a_subsection_stays_inside_its_section_and_a_sibling_ends_it():
    bl = g.blocks("# T\n\n## A\n\nin a\n\n### A1\n\nin a1\n\n## B\n\nin b\n")
    assert [b.text for b in g.section_of(bl, "A")] == ["in a", "A1", "in a1"]
    assert [b.text for b in g.section_of(bl, "A1")] == ["in a1"]
    assert g.section_of(bl, "Nope") == []


def test_a_lens_heading_without_a_body_is_not_a_brief():
    ok = g.section_problems(LENS1, "## Lens\n\n" + "w " * 20 + "\n", "Lens")
    assert ok == []
    short = g.section_problems(LENS1, "## Lens\n\n" + "w " * 19 + "\n\n## Next\n\n" + "w " * 50, "Lens")
    assert len(short) == 1 and "19 words" in short[0]
    nested = g.section_problems(LENS1, "## Lens\n\n" + "w " * 10 + "\n\n### Sub\n\n" + "w " * 10, "Lens")
    assert nested == []


def test_four_lens_rows_must_pin_four_different_headings():
    texts = {"review": "".join(f"## Lens {i}\n\n" + "w " * 25 + "\n\n" for i in (1, 2, 3, 4))
             + "## Report format\n\n" + "w " * 25 + "\n"}
    quotes = {r: f"Lens {i}" for i, r in enumerate(g.LENS_ROWS, 1)}
    quotes["review-report-format-heading"] = "Report format"
    assert g.lens_problems(texts, quotes) == []
    quotes[g.LENS_ROWS[1]] = "Lens 1"
    problems = g.lens_problems(texts, quotes)
    assert len(problems) == 1 and "four different headings" in problems[0]


def test_links_that_do_not_resolve_are_listed_and_the_rest_are_not(tmp_path):
    (tmp_path / "other.md").write_text("x")
    (tmp_path / "pic.png").write_bytes(b"x")
    text = ("See [other](other.md), [a part](other.md#part), [here](#top), [web](https://example.com/x), "
            "[mail](mailto:a@example.com), ![pic](pic.png) and [gone](gone.md) and [away](../away.md?x=1).\n\n"
            "```md\n[in code](nowhere.md)\n```\n")
    problems = g.link_problems(text, tmp_path)
    assert [("gone.md" in p, "away.md" in p) for p in problems] == [(True, False), (False, True)]


def test_a_table_without_rows_names_every_required_behaviour_missing():
    problems = g.quote_problems({"fix": "", "review": ""}, [])
    assert len(problems) == len(g.REQUIRED)
    assert all("no quote is pinned" in p for p in problems)


def test_the_rows_themselves_are_checked():
    _, problems = g.pinned([{"id": "nope", "quote": "x"}, {"id": FIX06, "quote": "a"}, {"id": FIX06, "quote": "b"}])
    assert any("unknown row 'nope'" in p for p in problems) and any("pinned twice" in p for p in problems)


def test_every_required_row_belongs_to_a_published_document():
    assert {d for d, _k, _w in g.REQUIRED.values()} == set(g.PUBLISHED)
    assert {k for _d, k, _w in g.REQUIRED.values()} == {"prose", "heading"}
    fix = [r for r in g.REQUIRED if r.startswith("fix-0") or r.startswith("fix-1")]
    assert sorted({r[4:6] for r in fix}) == [f"{n:02d}" for n in range(1, 12)], "eleven fix behaviours"
    assert len(g.LENS_ROWS) == 4


def test_the_table_shows_the_text_the_line_and_what_is_missing():
    rows = [{"id": FIX06, "quote": "Write a failing test first and watch it fail."},
            {"id": "fix-07-smallest-change", "quote": "no such | text with `ticks` in it"},
            {"id": "fix-inputs-heading", "quote": "Inputs"}]
    out = g.table({"fix": TOY, "review": ""}, rows)
    lines = {ln.split("|")[1].strip("` "): ln for ln in out.splitlines()[2:]}
    assert lines[FIX06].endswith("| 11 |")
    assert "` You need the ticket. `" in lines["fix-inputs-heading"] and lines["fix-inputs-heading"].endswith("| 5 |")
    assert "NOT FOUND" in lines["fix-07-smallest-change"]
    assert r"`` no such \| text with `ticks` in it ``" in lines["fix-07-smallest-change"]
    assert "MISSING" in lines["fix-01-stop-and-ask"]
    assert len(lines) == len(g.REQUIRED)
# --- Task 3: the two documents are in place, plain, neutral and linked ---------

DOCS = {doc: ROOT / path for doc, path in g.PUBLISHED.items()}

NOT_THE_AGENTS = (
    "\nThe document is the maintainer's and is never edited by a ticket. A hit is a gap in the document, "
    "or a rule too strict for a legitimate sentence; either is for the maintainer. "
    "The ticket agent stops as agent:blocked and quotes the lines above.")


def _text(doc: str) -> str:
    return DOCS[doc].read_text(encoding="utf-8")


def test_the_documents_are_at_their_published_paths():
    missing = [p for p in g.PUBLISHED.values() if not (ROOT / p).is_file()]
    assert not missing, (
        f"missing: {missing}. These two paths are linked from the README and from tickets; "
        f"moving one breaks them (spec §2).")


@pytest.mark.parametrize("doc", sorted(DOCS))
def test_a_document_is_plain_utf8_text_without_front_matter(doc):
    raw = DOCS[doc].read_bytes()
    assert raw.strip(), f"{g.PUBLISHED[doc]} is empty"
    text = raw.decode("utf-8")
    assert not g.has_front_matter(text), (
        f"{g.PUBLISHED[doc]} starts with a front-matter block, which makes it a skill or agent file")


@pytest.mark.parametrize("doc", sorted(DOCS))
def test_a_document_is_harness_neutral(doc):
    hits = g.lint(_text(doc), RULES)
    lines = [f"{g.PUBLISHED[doc]}:{h.line}: [{h.rule} {h.name}] {h.excerpt}" for h in hits]
    assert not hits, "\n".join(lines) + NOT_THE_AGENTS


@pytest.mark.parametrize("doc", sorted(DOCS))
def test_the_links_in_a_document_resolve(doc):
    problems = g.link_problems(_text(doc), DOCS[doc].parent)
    assert not problems, f"{g.PUBLISHED[doc]}: " + "; ".join(problems) + NOT_THE_AGENTS


@pytest.mark.parametrize("doc", sorted(DOCS))
@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.id)
def test_a_violation_added_to_a_real_document_is_caught(doc, rule):
    """The check has teeth on the real text, whatever its Markdown looks like."""
    mutated = _text(doc) + "\n\n" + rule.positive[0] + "\n"
    assert rule.id in {h.rule for h in g.lint(mutated, RULES)}


@pytest.mark.parametrize("doc", sorted(DOCS))
def test_front_matter_added_to_a_real_document_is_caught(doc):
    assert g.has_front_matter("---\nname: x\n---\n" + _text(doc))
