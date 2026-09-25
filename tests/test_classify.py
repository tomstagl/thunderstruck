"""#19 AC-6: commit classification v2. Resilience work is not a fix."""

from __future__ import annotations

import pytest
from _common import classify_commit

@pytest.mark.parametrize("subject,expected", [
    ("Add retry with exponential backoff and jitter", "resilience"),
    ("feat: honour Retry-After on 429", "feature"),
    ("Introduce rate limiting for partner API", "resilience"),
    ("chore: patch version bump", "refactor"),
    ("fix typo in README", "fix"),
    ("Add timeout to payment client", "resilience"),
    ("Handle 429 from upstream", "resilience"),
    ("fix: handle hang in release fetch", "fix"),
    ('Revert "add cache"', "fix"),
    ("Release 1.2.3", "feature"),
    ("Fehler behoben", "feature"),
    ("refactor: tidy imports", "refactor"),
])
def test_classify(subject, expected):
    assert classify_commit(subject) == expected

def test_profile_keywords():
    assert classify_commit("Fehler behoben", extra_fix=("behoben",)) == "fix"


def test_profile_keywords_are_whole_words_and_case_insensitive():
    assert classify_commit("FEHLER BEHOBEN", extra_fix=("behoben",)) == "fix"
    assert classify_commit("unbehoben lassen", extra_fix=("behoben",)) == "feature"
    assert classify_commit("corrige le bug", extra_fix=("corrige",)) == "fix"


def test_a_conventional_prefix_wins_over_vocabulary():
    assert classify_commit("feat(api): retry with backoff") == "feature"
    assert classify_commit("fix(sync)!: retry storm on 429") == "fix"
    assert classify_commit("ci: fix flaky job") == "refactor"
    assert classify_commit("perf: stop leaking sockets") == "feature"


def test_fix_intent_beats_resilience_vocabulary():
    assert classify_commit("Fix timeout on large releases") == "fix"
    assert classify_commit("Timeout crash in the importer") == "fix"
