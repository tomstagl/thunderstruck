"""The lead table states what a lead and no lead mean (#58 AC-5)."""

from __future__ import annotations

import report

TEMPLATE = report.c.plugin_root() / "templates" / "report.html"


def test_the_wording_says_what_a_lead_and_no_lead_mean():
    assert report.LEADS_HEADING == "Detector leads by pattern"
    assert "never proof that the pattern is missing" in report.LEADS_INTRO
    assert "a lead describes the default the code ships with" in report.LEADS_INTRO
    assert "does not mean the pattern is present" in report.LEADS_FOOTNOTE
    for text in (report.LEADS_HEADING, report.LEADS_INTRO, report.LEADS_FOOTNOTE):
        assert "coverage" not in text.lower() and "covered" not in text.lower()


def test_the_html_template_carries_the_same_words():
    template = TEMPLATE.read_text(encoding="utf-8")
    for text in (report.LEADS_HEADING, report.LEADS_INTRO, report.LEADS_FOOTNOTE):
        assert text in template, text
    assert "Pattern coverage" not in template
    assert "Run, coverage," not in template
