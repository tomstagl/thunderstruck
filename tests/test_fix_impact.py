"""#105: what a fix would remove, what was traced and what was inferred, what was
not checked, and numbered lines in a bundle's source."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent




# --- Task 1 -----------------------------------------------------------------
def test_vocabulary_is_the_spec_spelling():
    assert c.FIX_TOUCHES == ("lock", "retry", "cache")
    assert c.BLAST_BASES == ("traced", "catalog", "assumption")
    assert c.GUARANTEE_KEYS == ("guarantee", "removed_by", "evidence")
    assert c.BLAST_KEYS == ("claim", "basis", "evidence")
    assert c.NOT_CHECKED_KEYS == ("item", "how_to_check")
    assert c.RESOLUTION_STATES == ("resolved", "unresolved")
    assert (c.MAX_GUARANTEES, c.MAX_BLAST_ITEMS, c.MAX_NOT_CHECKED) == (5, 8, 5)


def test_the_catalog_marks_the_patterns_whose_fix_changes_a_mechanism(catalog):
    marked = {p["id"]: p["fix_touches"] for p in catalog["patterns"] if "fix_touches" in p}
    assert marked == {"S02": "retry", "S03": "retry", "S04": "retry", "S10": "retry",
                      "S09": "cache", "S28": "lock"}
    assert set(marked.values()) <= set(c.FIX_TOUCHES)


@pytest.mark.parametrize("finding, state", [
    ({}, "not_assessed"),
    ("junk", "not_assessed"),
    ({"blast_items": []}, "not_stated"),
    ({"blast_items": [], "implicit_guarantees": []}, "not_stated"),
    ({"blast_items": [], "no_guarantees_reason": "  "}, "not_stated"),
    ({"implicit_guarantees": [{}]}, "stated"),
    ({"no_guarantees_reason": "nothing else uses it"}, "none_found"),
    ({"implicit_guarantees": [{}], "no_guarantees_reason": "x"}, "stated"),
])
def test_guarantee_state(finding, state):
    assert c.guarantee_state(finding) == state


@pytest.mark.parametrize("finding, states", [
    ({}, []),
    ({"not_checked": []}, []),
    ({"not_checked": [{}, {}]}, ["open", "open"]),
    ({"not_checked": [{}, {}], "check": {"status": "upheld"}}, ["open", "open"]),
    ({"not_checked": [{}, {}, {}],
      "check": {"not_checked": [{"item": 1, "state": "resolved"}, {"item": 2, "state": "unresolved"}]}},
     ["open", "resolved", "unresolved"]),
    ({"not_checked": [{}], "check": {"not_checked": [{"item": 0, "state": "maybe"}]}}, ["open"]),
    ({"not_checked": [{}], "check": {"not_checked": [{"item": True, "state": "resolved"}, "junk"]}}, ["open"]),
    ({"not_checked": [{}], "check": {"not_checked": "junk"}}, ["open"]),
])
def test_not_checked_states_keep_every_item(finding, states):
    assert c.not_checked_states(finding) == states


# --- Task 2 -----------------------------------------------------------------
INVESTIGATOR = ROOT / "agents" / "thunderstruck-investigator.md"
SCAN = ROOT / "skills" / "thunderstruck-scan" / "SKILL.md"


def test_the_investigator_prompt_states_the_new_rules():
    flat = " ".join(INVESTIGATOR.read_text(encoding="utf-8").split())
    assert "all twelve required keys" in flat and "all ten" not in flat
    for fragment in ("`implicit_guarantees`", "`no_guarantees_reason`", "`blast_items`", "`not_checked`",
                     "A catalog edge never makes an item `traced`",
                     'completes "removed by"', "a skeptic reads this list and never reads that rationale",
                     "whatever its patterns",
                     "The validator checks that each cited line exists, not that the lines connect"):
        assert fragment in flat, fragment
    assert "say so in `confidence_rationale`" not in flat


def test_the_repair_round_asks_for_every_new_key():
    flat = " ".join(SCAN.read_text(encoding="utf-8").split())
    assert "all twelve required keys" in flat and "all ten" not in flat
    assert "`not_checked`" in flat and "`implicit_guarantees` or `no_guarantees_reason`" in flat


def test_the_catalog_brief_marks_the_patterns_the_ticket_scoped(tmp_path, catalog):
    import bundle
    path = bundle.write_catalog_brief(tmp_path, catalog, {})
    sections = path.read_text().split("\n### ")[1:]
    marked = {s.split(" — ", 1)[0]: s for s in sections if "A finding for this pattern (kind: " in s}
    assert set(marked) == {"S02", "S03", "S04", "S09", "S10", "S28"}
    assert "(kind: lock) states `implicit_guarantees`" in marked["S28"]
    assert "(kind: cache)" in marked["S09"] and "(kind: retry)" in marked["S10"]
    assert "changes a" not in path.read_text(), "the gate is the ticket's scope, not a property of the patterns"


def test_the_prompt_example_has_a_traced_item_citing_two_lines():
    from test_investigator_contract import _example
    example = _example(INVESTIGATOR.read_text(encoding="utf-8"))
    traced = [i for f in example["findings"] for i in f["blast_items"] if i["basis"] == "traced"]
    assert traced and any(len(i["evidence"]) >= 2 for i in traced), \
        "a single cited line would read as a traced path"


# --- Task 3 -----------------------------------------------------------------
from test_validate_paths import _doc, _validator, repo  # noqa: E402,F401
from validate import REQUIRED_FIELDS, Validator  # noqa: E402

_DROP = object()


def _impact(repo, **over) -> list[str]:
    """Validator errors for _doc's finding (patterns S02, one code evidence item)
    with `over` applied; _DROP removes a key."""
    doc = _doc("src/a.ts")
    finding = doc["findings"][0]
    for key, value in over.items():
        if value is _DROP:
            finding.pop(key, None)
        else:
            finding[key] = value
    return _validator(repo).check_document(doc)


def _g(**over) -> dict:
    g = {"guarantee": "Only one caller refreshes at a time", "removed_by": "releasing the lock early",
         "evidence": [0]}
    g.update(over)
    return {k: v for k, v in g.items() if v is not _DROP}


def _b(**over) -> dict:
    b = {"claim": "Every caller waits on the lock", "basis": "traced", "evidence": [0]}
    b.update(over)
    return {k: v for k, v in b.items() if v is not _DROP}


def test_a_finding_with_every_impact_field_passes(repo):
    assert _impact(repo) == []
    assert _impact(repo, no_guarantees_reason=_DROP, implicit_guarantees=[_g()]) == []
    assert _impact(repo, blast_items=[_b(), _b(basis="assumption", evidence=_DROP)],
                   not_checked=[{"item": "the retry timeout", "how_to_check": "read config.ts"}]) == []


@pytest.mark.parametrize("key, fragment", [
    ("blast_items", "findings[0].blast_items is missing"),
    ("not_checked", "findings[0].not_checked is missing (it may be [], but the key must be present)"),
])
def test_the_new_required_keys_are_named_when_missing(repo, key, fragment):
    assert any(fragment in e for e in _impact(repo, **{key: _DROP}))


@pytest.mark.parametrize("over, fragment", [
    ({"guarantee": ""}, "implicit_guarantees[0].guarantee must be a non-empty string"),
    ({"removed_by": None}, "implicit_guarantees[0].removed_by must be a non-empty string"),
    ({"evidence": _DROP}, "implicit_guarantees[0].evidence must be a non-empty list of positions"),
    ({"evidence": []}, "must be a non-empty list of positions"),
    ({"evidence": [7]}, "is 7, which is not a position in the finding's 1 evidence items"),
    ({"evidence": [True]}, "is true, which is not a position"),
    ({"evidence": ["0"]}, "is '0', which is not a position"),
    ({"code": "src/a.ts:3"}, "unknown key(s) ['code']"),
])
def test_each_guarantee_rule(repo, over, fragment):
    errors = _impact(repo, no_guarantees_reason=_DROP, implicit_guarantees=[_g(**over)])
    assert any(fragment in e for e in errors), errors


def test_a_guarantee_points_only_at_code_evidence(repo):
    doc = _doc("src/a.ts")
    f = doc["findings"][0]
    f["evidence"].append({"type": "catalog", "ref": "dependencyOf component:default/web", "note": "n"})
    f["implicit_guarantees"] = [_g(evidence=[1])]
    del f["no_guarantees_reason"]
    errors = _validator(repo).check_document(doc)
    assert any("points at evidence[1], which is 'catalog' evidence; a guarantee is shown by the "
               "code that provides it" in e for e in errors), errors


def test_more_than_five_guarantees_are_rejected(repo):
    errors = _impact(repo, no_guarantees_reason=_DROP, implicit_guarantees=[_g() for _ in range(6)])
    assert any("has 6 items; the maximum is 5" in e for e in errors)


@pytest.mark.parametrize("pattern, kind", [("S02", "retry"), ("S03", "retry"), ("S04", "retry"),
                                           ("S10", "retry"), ("S09", "cache"), ("S28", "lock")])
def test_a_lock_retry_or_cache_finding_states_guarantees_or_none_found(repo, pattern, kind):
    errors = _impact(repo, missing_patterns=[pattern], no_guarantees_reason=_DROP)
    assert any(f"missing_patterns includes {pattern} ({kind})" in e for e in errors), errors
    assert _impact(repo, missing_patterns=["S01", pattern], no_guarantees_reason=_DROP,
                   implicit_guarantees=[_g()]) == []
    assert _impact(repo, missing_patterns=[pattern], no_guarantees_reason="the lock guards a counter") == []


@pytest.mark.parametrize("patterns", [["S01"], ["S05"], ["S07"], ["S12"], ["OTHER"], ["S06", "S11"]])
def test_other_findings_need_not_state_guarantees(repo, patterns):
    assert _impact(repo, missing_patterns=patterns, no_guarantees_reason=_DROP) == []


@pytest.mark.parametrize("over, fragment", [
    ({"no_guarantees_reason": "  "}, "no_guarantees_reason must be a non-empty string when present"),
    ({"no_guarantees_reason": ["x"]}, "no_guarantees_reason must be a non-empty string when present"),
    ({"implicit_guarantees": [_g()], "no_guarantees_reason": "x"}, "state guarantees or say you found none, not both"),
    ({"implicit_guarantees": "x", "no_guarantees_reason": _DROP}, "implicit_guarantees must be a list"),
])
def test_the_none_found_reason_is_a_real_sentence_and_never_beside_guarantees(repo, over, fragment):
    assert any(fragment in e for e in _impact(repo, **over)), _impact(repo, **over)


@pytest.mark.parametrize("item, fragment", [
    (_b(claim=" "), "blast_items[0].claim must be a non-empty string"),
    (_b(basis="inferred"), "blast_items[0].basis 'inferred' is not one of ['traced', 'catalog', 'assumption']"),
    (_b(evidence=_DROP), "blast_items[0].evidence must be a non-empty list of positions"),
    (_b(evidence=[3]), "is 3, which is not a position"),
    (_b(basis="assumption"), 'is only given when basis is "traced" or "catalog"'),
    (_b(basis="catalog"), "points at evidence[0], which is 'code' evidence; a catalog item rests on a catalog edge"),
    (_b(extra="x"), "unknown key(s) ['extra']"),
])
def test_each_blast_item_rule(repo, item, fragment):
    errors = _impact(repo, blast_items=[item])
    assert any(fragment in e for e in errors), errors


def test_a_catalog_edge_never_makes_an_item_traced(repo):
    doc = _doc("src/a.ts")
    f = doc["findings"][0]
    f["evidence"].append({"type": "catalog", "ref": "dependencyOf component:default/web", "note": "n"})
    f["blast_items"] = [_b(evidence=[1])]
    errors = _validator(repo).check_document(doc)
    assert any("blast_items[0].evidence[0] points at evidence[1], which is 'catalog' evidence; a traced "
               "item cites the code you followed to reach it. An item that rests on a catalog edge has "
               'basis "catalog"' in e for e in errors), errors


def test_a_catalog_item_is_checked_only_for_pointing_at_catalog_evidence(repo):
    doc = _doc("src/a.ts")
    f = doc["findings"][0]
    f["evidence"].append({"type": "catalog", "ref": "dependencyOf component:default/web", "note": "n"})
    f["blast_items"] = [_b(basis="catalog", evidence=[1])]
    errors = _validator(repo).check_document(doc)
    assert any("no service context" in e for e in errors)           # the edge itself is resolved as before
    assert not any("blast_items" in e for e in errors)              # and the item is a valid catalog item


def test_blast_items_may_not_be_empty_or_numerous(repo):
    assert any("blast_items must be a non-empty list" in e for e in _impact(repo, blast_items=[]))
    assert any("has 9 items; the maximum is 8" in e for e in _impact(repo, blast_items=[_b()] * 9))


@pytest.mark.parametrize("over, fragment", [
    ({"not_checked": [{"item": "x"}]}, "not_checked[0].how_to_check must be a non-empty string"),
    ({"not_checked": [{"item": "", "how_to_check": "y"}]}, "not_checked[0].item must be a non-empty string"),
    ({"not_checked": [{"item": "x", "how_to_check": "y", "ref": "a:1"}]}, "unknown key(s) ['ref']"),
    ({"not_checked": ["x"]}, "not_checked[0] is not an object"),
    ({"not_checked": {"item": "x"}}, "not_checked must be a list"),
    ({"not_checked": [{"item": "x", "how_to_check": "y"}] * 6}, "has 6 items; the maximum is 5"),
])
def test_each_not_checked_rule(repo, over, fragment):
    errors = _impact(repo, **over)
    assert any(fragment in e for e in errors), errors


def test_impact_errors_are_reported_even_when_the_evidence_list_is_invalid(repo):
    """One repair round: a broken evidence list must not hide the rest."""
    errors = _impact(repo, evidence=[], blast_items=[], no_guarantees_reason=_DROP)
    assert any("evidence must be a non-empty list" in e for e in errors)
    assert any("blast_items must be a non-empty list" in e for e in errors)
    assert any("missing_patterns includes S02 (retry)" in e for e in errors)
    # the positions cannot be checked against a list that is not there
    assert not any("is not a position" in e for e in _impact(repo, evidence=[], blast_items=[_b(evidence=[9])]))


def test_findings_validated_under_rules_4_are_investigated_again(scanned_copy):
    import bundle
    from test_pipeline import _hotspots, _valid_finding
    from validate import Validator
    assert c.VALIDATION_RULES == 5
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    doc["validated_with"] = 4
    assert bundle._validated_under_older_rules(doc | {"findings": [{"key": "k"}]})
    old = json.loads(json.dumps(doc))
    for f in old["findings"]:
        for key in ("blast_items", "not_checked", "implicit_guarantees"):
            f.pop(key, None)                                  # written under the older rules
    validator = Validator(scanned_copy, _hotspots(scanned_copy), c.load_catalog())
    assert not bundle._still_valid(validator, old)
    assert bundle._still_valid(validator, doc)


def test_the_finding_schema_names_the_contract_that_wrote_it():
    import finding_shape
    assert finding_shape.FINDING_SCHEMA_VERSION == "thunderstruck.finding/v3"


def test_the_investigator_example_follows_the_impact_contract(catalog):
    from test_investigator_contract import _example
    example = _example(INVESTIGATOR.read_text(encoding="utf-8"))
    validator = Validator(ROOT, {"hotspots": []}, catalog)
    stated = 0
    for f in example["findings"]:
        types = [ev["type"] for ev in f["evidence"]]
        errors: list[str] = []
        validator.check_impact(f, "findings[0]", errors, f["evidence"], types)
        assert errors == [], errors
        stated += bool(f.get("implicit_guarantees"))
        assert {"blast_items", "not_checked"} <= set(f)
    assert stated == 1 and any("implicit_guarantees" not in f for f in example["findings"])
    assert any(i["basis"] == "traced" for f in example["findings"] for i in f["blast_items"])
    assert any(i["basis"] == "assumption" for f in example["findings"] for i in f["blast_items"])


def test_the_validator_requires_the_keys_the_prompt_names():
    flat = " ".join(INVESTIGATOR.read_text(encoding="utf-8").split())
    assert len(REQUIRED_FIELDS) == 12 and all(f"`{key}`" in flat for key in REQUIRED_FIELDS)


# --- Task 4 -----------------------------------------------------------------
import re  # noqa: E402

import benchmark as b  # noqa: E402
import bundle  # noqa: E402
import validate  # noqa: E402

NUMBERED = re.compile(r"^( *)(\d+) \| ?(.*)\Z", re.S)
MARKER = re.compile(r"^\.\.\. \[trimmed: lines (\d+)-(\d+) omitted\] \.\.\.\Z")
WHOLE = re.compile(r"^_whole file, (\d+) lines_$", re.M)
EXCERPT = re.compile(r"^_lines (\d+)-(\d+) — .* the file is (\d+) lines and did not fit the budget_$", re.M)
TRIMMED = re.compile(r"^_file trimmed to fit the budget; (\d+) lines total_$", re.M)

CONTENTS = {
    "lf": b"".join(f"x_{i:04d} = {i}\n".encode() for i in range(1, 401)),
    "no final newline": b"\n".join(f"x_{i:04d} = {i}".encode() for i in range(1, 401)),
    "crlf": b"".join(f"x_{i:04d} = {i}\r\n".encode() for i in range(1, 401)),
    "lone cr and form feed": b"".join((f"x_{i:04d} = {i}  # a\rb\x0cc\n" if i % 7 == 0 else f"x_{i:04d} = {i}\n").encode()
                                      for i in range(1, 401)),
    "blank lines": b"".join((b"\n" if i % 5 == 0 else f"x_{i:04d} = {i}\n".encode()) for i in range(1, 401)),
}


def _source(tmp_path: Path, content: bytes, budget: int, top: dict | None = None) -> tuple[str, list[str]]:
    (tmp_path / "m.py").write_bytes(content)
    hs = {"file": "m.py", "language": "python", "complexity": {"top_function": top} if top else {}}
    block = bundle.section_source(tmp_path, hs, budget)
    body = block.split("```python\n", 1)[1].rsplit("\n```", 1)[0]
    return block, body.split("\n")


def _file_lines(content: bytes) -> list[str]:
    """The lines as git counts them (split at \\n only), shown as the bundle shows them: one
    trailing \\r dropped, any other \\r as U+240D."""
    parts = content.decode().split("\n")
    if parts[-1] == "":
        parts.pop()
    return [(p[:-1] if p.endswith("\r") else p).replace("\r", "\u240d") for p in parts]


CASES = [(500, None), (10000, None), (200, {"name": "f", "lines": "100-250"}),
         (600, {"name": "f", "lines": "100-120"}), (300, {"name": "f", "lines": "380-400"}),
         (10000, {"name": "f", "lines": "100-150"})]


@pytest.mark.parametrize("name", sorted(CONTENTS))
@pytest.mark.parametrize("budget, top", CASES)
def test_every_shown_line_is_the_file_line_it_is_numbered_as(tmp_path, name, budget, top):
    """AC-8: the number in front of a line is its number in the file, whatever the file's
    line endings, and the text after it is that line."""
    content = CONTENTS[name]
    file_lines = _file_lines(content)
    block, rows = _source(tmp_path, content, budget, top)
    width = len(str(len(file_lines)))
    shown: list[int] = []
    for row in rows:
        if MARKER.match(row):
            continue
        m = NUMBERED.match(row)
        assert m, row
        n = int(m.group(2))
        assert row == f"{n:>{width}} | {file_lines[n - 1]}", (n, row)
        shown.append(n)
    assert shown == sorted(set(shown)) and shown, "numbers rise, and something is shown"
    # and what is shown is exactly what the note and the marker say
    if m := EXCERPT.search(block):
        first, last, total = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = WHOLE.search(block) or TRIMMED.search(block)
        first, last, total = 1, int(m.group(1)), int(m.group(1))
    assert total == len(file_lines), "the note counts the file as validate.py does"
    omitted = [int(x) for r in rows if (m := MARKER.match(r)) for x in m.groups()]
    covered = set(shown) | (set(range(omitted[0], omitted[1] + 1)) if omitted else set())
    assert covered == set(range(first, last + 1)), (first, last, omitted)


def test_a_clipped_block_says_which_lines_it_leaves_out(tmp_path):
    _, rows = _source(tmp_path, CONTENTS["lf"], 200, {"name": "f", "lines": "100-250"})
    at = next(i for i, r in enumerate(rows) if MARKER.match(r))
    lo, hi = (int(x) for x in MARKER.match(rows[at]).groups())
    assert int(NUMBERED.match(rows[at - 1]).group(2)) + 1 == lo
    assert int(NUMBERED.match(rows[at + 1]).group(2)) - 1 == hi
    assert sum(1 for r in rows if MARKER.match(r)) == 1


def test_an_excerpt_is_numbered_from_its_own_start_not_from_one(tmp_path):
    """The reproduction in #105: a function at line 76 gave 'lines 61-…' and the first body
    line was counted as line 1."""
    block, rows = _source(tmp_path, CONTENTS["lf"], 400, {"name": "f", "lines": "76-120"})
    assert "_lines 61-135 — the most complex function `f`" in block
    assert rows[0] == " 61 | x_0061 = 61"


def test_the_counts_in_the_notes_are_the_counts_validate_py_makes(tmp_path):
    """The excerpt note said 562 for a file of 561 lines: the empty string after the final newline."""
    for name, content in CONTENTS.items():
        (tmp_path / "m.py").write_bytes(content)
        assert len(bundle.source_lines(tmp_path / "m.py")) == validate._count_lines(tmp_path / "m.py"), name
    block, _ = _source(tmp_path, CONTENTS["lf"], 500, {"name": "f", "lines": "380-400"})
    assert "the file is 400 lines" in block and "lines 365-400 " in block
    block, _ = _source(tmp_path, CONTENTS["lf"], 500)
    assert "file trimmed to fit the budget; 400 lines total" in block
    block, _ = _source(tmp_path, CONTENTS["lf"][:2000], 10000)
    assert "whole file, " in block


def test_the_numbers_count_against_the_budget(tmp_path):
    """AC-9: a file whose text fits the budget but whose numbered text does not is no longer
    shown whole, and a clipped block stays within its budget."""
    content = "".join(f"line {i:02d}\n" for i in range(1, 101)).encode()   # 801 characters: 200 tokens
    assert len(content) // 4 == 200
    block, rows = _source(tmp_path, content, 230)           # the text alone would fit
    assert "whole file" not in block and any(MARKER.match(r) for r in rows)
    assert len("\n".join(rows)) <= 230 * 4 + 60             # the budget, and the marker line
    block, rows = _source(tmp_path, content, 350)           # numbered, it fits
    assert "whole file, 100 lines" in block and not any(MARKER.match(r) for r in rows)


def test_a_line_too_long_for_the_budget_is_named_as_left_out(tmp_path):
    content = b"a = 1\n" + b"x = '" + b"y" * 5000 + b"'\n" + b"b = 2\n"
    _, rows = _source(tmp_path, content, 100)
    assert any(MARKER.match(r) for r in rows)
    assert not any("yyyy" in r for r in rows)


def test_a_fence_in_the_source_cannot_end_the_block(tmp_path):
    lines = [f"x_{i:04d} = {i}" for i in range(1, 41)]
    lines[9] = "```"
    block, rows = _source(tmp_path, ("\n".join(lines) + "\n").encode(), 10000)
    assert "\n```\n" not in block.split("```python\n", 1)[1].rsplit("\n```", 1)[0]
    assert rows[9] == "10 | ```"
    assert b.shown_lines(block) == ("m.py", [(1, 40)])


def test_the_source_block_is_byte_identical_across_calls(tmp_path):
    first = _source(tmp_path, CONTENTS["lone cr and form feed"], 300, {"name": "f", "lines": "100-250"})
    assert first == _source(tmp_path, CONTENTS["lone cr and form feed"], 300, {"name": "f", "lines": "100-250"})


@pytest.mark.parametrize("budget, top", CASES)
def test_the_benchmark_reads_a_numbered_block_exactly(tmp_path, budget, top):
    """shown_lines used to count lines from the marker and could under-count by two; it now
    reads the numbers, so it names exactly the lines that are shown."""
    content = CONTENTS["lf"]
    block, rows = _source(tmp_path, content, budget, top)
    file, ranges = b.shown_lines(block + "## Change history — last 1 commits touching this file\n")
    claimed = {i for lo, hi in ranges for i in range(lo, hi + 1)}
    shown = {int(NUMBERED.match(r).group(2)) for r in rows if not MARKER.match(r)}
    assert file == "m.py" and claimed == shown


def test_the_benchmark_still_reads_a_bundle_written_before_numbering():
    legacy = "## Source — `a.py`\n\n_whole file, 3 lines_\n\n```python\nx = 1\ny = 2\nz = 3\n```\n"
    assert b.shown_lines(legacy) == ("a.py", [(1, 3)])
    clipped = ("## Source — `a.py`\n\n_lines 10-20 — the most complex function `f` with 15 lines of "
               "context; the file is 90 lines and did not fit the budget_\n\n```python\na\nb\n\n\n"
               "... [trimmed: 30 characters omitted] ...\n\nc\nd\n```\n")
    assert b.shown_lines(clipped) is not None


def test_a_lone_carriage_return_is_shown_visibly_and_never_starts_a_row(tmp_path):
    """A lone \\r is not a line break to git or validate.py. Raw, it could pass for the start of an
    unnumbered row; it is shown as U+240D and the numbers stay the file's."""
    content = b"a = 1\rb = 2\nc = 3\r\nd = 4\r\r\ne = 5\n"
    block, rows = _source(tmp_path, content, 10000)
    assert rows == ["1 | a = 1\u240db = 2", "2 | c = 3", "3 | d = 4\u240d", "4 | e = 5"]
    assert all(NUMBERED.match(r) for r in rows) and "\r" not in block
    assert b.shown_lines(block) == ("m.py", [(1, 4)])
    assert len(bundle.source_lines(tmp_path / "m.py")) == validate._count_lines(tmp_path / "m.py") == 4


def test_the_investigator_prompt_tells_the_model_to_cite_the_numbers():
    flat = " ".join(INVESTIGATOR.read_text(encoding="utf-8").split())
    assert "Cite those numbers in `location` and in `code` refs; never count lines yourself" in flat
    assert "trimmed one names the lines it leaves out" in flat


def test_every_bundle_of_the_fixture_numbers_its_source(scanned_repo):
    """AC-8, AC-9: every bundle's hash changed once, because every bundle's source is numbered."""
    bundles = sorted((scanned_repo / ".thunderstruck" / "bundles").glob("H*.md"))
    assert bundles
    for path in bundles:
        file, ranges = b.shown_lines(path.read_text())
        assert ranges and ranges[0][0] >= 1, path.name
        assert re.search(r"```\w*\n *\d+ \| ", path.read_text()), path.name


# --- Task 5 -----------------------------------------------------------------
import verify  # noqa: E402
from test_verification import _apply, _entry, _finding, _line, _prepare, _save, _v  # noqa: E402


def test_the_verdict_contract_gains_exactly_the_three_keys():
    assert verify.VERDICT_KEYS == ("key", "verdict", "reason", "holds", "refuted_claims", "evidence",
                                   "dependencies_read", "duplicate_of",
                                   "guarantees", "no_guarantees_reason", "not_checked", "confirmations")
    assert verify.VERDICT_KEYS[-1] == "confirmations", "#57's pin on the last key stands"
    assert verify.VERDICT_GUARANTEE_KEYS == ("of", "guarantee", "removed_by", "evidence")
    assert verify.VERDICT_NOT_CHECKED_KEYS == ("item", "state", "note", "evidence")


def test_the_prompt_example_shows_both_item_shapes():
    import re as _re
    text = (ROOT / "agents" / "thunderstruck-skeptic.md").read_text()
    example = json.loads(_re.search(r"```json\n(\{.*?\})\n```", text, _re.S)[1])
    assert example["guarantees"] and example["not_checked"]
    assert all(set(g) <= set(verify.VERDICT_GUARANTEE_KEYS) for g in example["guarantees"])
    assert any(g["of"] is None for g in example["guarantees"]) and any(g["of"] == 0 for g in example["guarantees"])
    assert all(set(n) <= set(verify.VERDICT_NOT_CHECKED_KEYS) for n in example["not_checked"])
    assert {n["state"] for n in example["not_checked"]} == set(c.RESOLUTION_STATES)


def test_the_brief_carries_the_impact_claims_and_still_withholds_the_rationale(validated_repo, validated_env):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    brief = (validated_repo / e["brief"]).read_text()
    f = _finding(validated_repo, e["key"])
    for field in ("blast_items", "implicit_guarantees", "not_checked"):
        assert f"### {field}" in brief, field
    assert f["implicit_guarantees"][0]["guarantee"] in brief
    assert f["not_checked"][1]["how_to_check"] in brief and '"index": 1' in brief
    assert f["confidence_rationale"] not in brief and "confidence_rationale" not in brief
    api = (validated_repo / _entry(plan, "api.ts")["brief"]).read_text()
    assert "### no_guarantees_reason" in api and "### implicit_guarantees" not in api


def test_a_finding_from_before_the_impact_fields_gets_a_brief_without_them():
    old = {"key": "k" * 12, "location": {"file": "a.py"}, "missing_patterns": ["S02"], "failure_mode": "f",
           "trigger_condition": "t", "blast_radius": "b", "how_to_verify": "v", "evidence": [], "preconditions": []}
    brief = verify.render_brief(old, [], None, [])
    for field in ("blast_items", "implicit_guarantees", "not_checked", "no_guarantees_reason"):
        assert f"### {field}" not in brief


RESOLVED = {0: {"type": "code", "ref": "a.py:1"}, 1: {"type": "commit", "ref": "abc1234"},
            2: {"type": "dependency", "ref": "pypi:x@1:y.py:1"}}
MINE = {"implicit_guarantees": [{"guarantee": "g0", "removed_by": "r0", "evidence": [0]},
                                {"guarantee": "g1", "removed_by": "r1", "evidence": [0]}],
        "not_checked": [{"item": "i0", "how_to_check": "h0"}, {"item": "i1", "how_to_check": "h1"}]}


@pytest.mark.parametrize("result, state, items, ignored", [
    ({"guarantees": [{"of": 1, "evidence": [0]}]}, "named",
     [{"of": 1, "guarantee": "g1", "removed_by": "r1", "evidence": [0]}], []),
    ({"guarantees": [{"of": 0, "guarantee": "reworded", "removed_by": "x", "evidence": [0, 2]}]}, "named",
     [{"of": 0, "guarantee": "g0", "removed_by": "r0", "evidence": [0, 2]}], []),
    ({"guarantees": [{"of": None, "guarantee": "new", "removed_by": "r", "evidence": [2]}]}, "named",
     [{"of": None, "guarantee": "new", "removed_by": "r", "evidence": [2]}], []),
    ({"guarantees": [{"of": 0, "evidence": [1]}]}, "not_addressed", [], ["has no code evidence that resolved"]),
    ({"guarantees": [{"of": 0, "evidence": [9]}]}, "not_addressed", [], ["has no code evidence that resolved"]),
    ({"guarantees": [{"of": 5, "evidence": [0]}]}, "not_addressed", [], ["is not a position in the finding's"]),
    ({"guarantees": [{"of": True, "evidence": [0]}]}, "not_addressed", [], ["is not a position in the finding's"]),
    ({"guarantees": [{"of": None, "evidence": [0]}]}, "not_addressed", [], ["without its guarantee and removed_by"]),
    ({"guarantees": [{"of": 0, "evidence": [0]}, {"of": 0, "evidence": [0]}]}, "named",
     [{"of": 0, "guarantee": "g0", "removed_by": "r0", "evidence": [0]}], ["repeats guarantee 0"]),
    ({"guarantees": [{"of": 0, "evidence": [0], "extra": 1}]}, "not_addressed", [], ["is not an object with the keys"]),
    ({"guarantees": "none"}, "not_addressed", [], ["guarantees is not a list"]),
    ({"guarantees": [], "no_guarantees_reason": "The lock guards a counter only."}, "none_found", [], []),
    ({"no_guarantees_reason": "  "}, "not_addressed", [], []),
    ({}, "not_addressed", [], []),
    ({"guarantees": [{"of": 0, "evidence": [0]}], "no_guarantees_reason": "none"}, "named",
     [{"of": 0, "guarantee": "g0", "removed_by": "r0", "evidence": [0]}], ["no_guarantees_reason is given beside"]),
])
def test_settle_guarantees(result, state, items, ignored):
    notes: list[str] = []
    out = verify.settle_guarantees(MINE, result, RESOLVED, notes)
    assert out["state"] == state and out["items"] == items
    assert all(any(want in n for n in notes) for want in ignored), notes
    assert (out["reason"] is None) == (state == "named")


@pytest.mark.parametrize("result, expected, ignored", [
    ({"not_checked": [{"item": 0, "state": "resolved", "note": "read it", "evidence": [0, 1]}]},
     [("resolved", [0, 1]), ("unresolved", [])], []),
    ({"not_checked": [{"item": 1, "state": "unresolved", "note": "read limit", "evidence": [0]}]},
     [("unresolved", []), ("unresolved", [0])], []),
    ({"not_checked": [{"item": 0, "state": "resolved", "note": "read it"}]},
     [("unresolved", []), ("unresolved", [])], ["says resolved but has no evidence that resolved"]),
    ({"not_checked": [{"item": 0, "state": "resolved", "note": "read it", "evidence": [9]}]},
     [("unresolved", []), ("unresolved", [])], ["says resolved but has no evidence that resolved"]),
    ({"not_checked": [{"item": 0, "state": "done", "note": "x"}]},
     [("unresolved", []), ("unresolved", [])], ["needs a state of"]),
    ({"not_checked": [{"item": 0, "state": "unresolved", "note": ""}]},
     [("unresolved", []), ("unresolved", [])], ["needs a state of"]),
    ({"not_checked": [{"item": 2, "state": "unresolved", "note": "x"}]},
     [("unresolved", []), ("unresolved", [])], ["is not a position in the finding's not_checked"]),
    ({"not_checked": [{"item": False, "state": "unresolved", "note": "x"}]},
     [("unresolved", []), ("unresolved", [])], ["is not a position in the finding's not_checked"]),
    ({"not_checked": [{"item": 0, "state": "resolved", "note": "a", "evidence": [0]},
                      {"item": 0, "state": "unresolved", "note": "b"}]},
     [("resolved", [0]), ("unresolved", [])], ["repeats item 0"]),
    ({"not_checked": [{"item": 0, "state": "unresolved", "note": "x", "why": "y"}]},
     [("unresolved", []), ("unresolved", [])], ["is not an object with the keys"]),
    ({"not_checked": "all of them"}, [("unresolved", []), ("unresolved", [])], ["not_checked is not a list"]),
    ({}, [("unresolved", []), ("unresolved", [])], []),
])
def test_settle_not_checked_keeps_every_item(result, expected, ignored):
    notes: list[str] = []
    out = verify.settle_not_checked(MINE, result, RESOLVED, notes)
    assert [(e["state"], e["evidence"]) for e in out] == expected
    assert [e["item"] for e in out] == [0, 1], "one entry per listed item, in order: none disappears"
    assert all(any(want in n for n in notes) for want in ignored), notes
    assert all(e["note"] for e in out)
    unanswered = [e for e in out if e["note"] == c.NOT_ADDRESSED]
    assert all(e["state"] == "unresolved" for e in unanswered)


def _verdict_for_releases(repo: Path, key: str, verdict: str = "upheld", **over) -> dict:
    loop = _line(repo, "src/client/releases.ts", "setTimeout(resolve, SLEEP_MS)")
    sched = _line(repo, "src/sync/scheduler.ts", "return submit(() => fetchRelease(id));")
    return _v(key, verdict, evidence=[
        {"type": "code", "ref": f"src/client/releases.ts:{loop}", "note": "the loop"},
        {"type": "code", "ref": f"src/sync/scheduler.ts:{sched}", "note": "one call"}], **over)


def test_a_verdict_names_guarantees_and_resolves_items_inside_check(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    _save(validated_repo, validated_env, tmp_path, _verdict_for_releases(
        validated_repo, e["key"],
        guarantees=[{"of": 0, "evidence": [0]},
                    {"of": None, "guarantee": "Callers share one queue slot",
                     "removed_by": "running lookups outside the queue", "evidence": [1]}],
        not_checked=[{"item": 0, "state": "resolved", "note": "Both call it once.", "evidence": [1]}]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    mine = _finding(validated_repo, e["key"])["implicit_guarantees"][0]
    assert check["status"] == "upheld"
    assert check["guarantees"]["state"] == "named" and check["guarantees"]["reason"] is None
    assert check["guarantees"]["items"] == [
        {"of": 0, "guarantee": mine["guarantee"], "removed_by": mine["removed_by"], "evidence": [0]},
        {"of": None, "guarantee": "Callers share one queue slot",
         "removed_by": "running lookups outside the queue", "evidence": [1]}]
    assert [(n["item"], n["state"]) for n in check["not_checked"]] == [(0, "resolved"), (1, "unresolved")]
    assert check["not_checked"][1]["note"] == c.NOT_ADDRESSED
    assert len(check["evidence"]) == 2
    assert _finding(validated_repo, e["key"])["check"]["guarantees"]["state"] == "named"


def test_a_verdict_that_says_nothing_new_keeps_its_status_and_every_item(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "inconclusive", reason="could not settle it"))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "inconclusive" and check["reason"] == "could not settle it"
    assert check["guarantees"]["state"] == "not_addressed"
    assert [n["state"] for n in check["not_checked"]] == ["unresolved", "unresolved"]
    f = _finding(validated_repo, e["key"])
    assert len(check["not_checked"]) == len(f["not_checked"]) == 2


def test_resolving_every_item_never_changes_status_or_confidence(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    _save(validated_repo, validated_env, tmp_path, _verdict_for_releases(
        validated_repo, e["key"], "inconclusive", reason="r",
        guarantees=[{"of": 0, "evidence": [0]}],
        not_checked=[{"item": 0, "state": "resolved", "note": "n", "evidence": [1]},
                     {"item": 1, "state": "resolved", "note": "n", "evidence": [0]}]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "inconclusive"
    assert all(n["state"] == "resolved" for n in check["not_checked"])
    claimed = _finding(validated_repo, e["key"])["confidence"]
    assert c.effective_confidence(claimed, check["status"]) == "medium"   # claimed high, never raised


def test_malformed_new_keys_never_cost_the_verdict(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    _save(validated_repo, validated_env, tmp_path,
          _v(e["key"], "upheld", guarantees="none", not_checked={"0": "done"}))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "upheld"
    assert "Ignored: guarantees is not a list; not_checked is not a list" in check["reason"]
    assert [n["state"] for n in check["not_checked"]] == ["unresolved", "unresolved"]


def test_an_unknown_verdict_key_is_still_a_contract_error(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", guarantee_notes="free text"))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "unchecked"
    assert "unknown key(s) ['guarantee_notes']" in check["reason"] and "guarantees" not in check


def test_the_resolutions_survive_the_ledger_and_reuse(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    _save(validated_repo, validated_env, tmp_path, _verdict_for_releases(
        validated_repo, e["key"], guarantees=[{"of": 0, "evidence": [0]}],
        not_checked=[{"item": 0, "state": "resolved", "note": "n", "evidence": [1]}]))
    first = _apply(validated_repo, validated_env)[e["key"]]
    again = _prepare(validated_repo, validated_env)
    assert _entry(again, "releases.ts")["action"] == "reuse"
    second = _apply(validated_repo, validated_env)[e["key"]]
    assert second["guarantees"] == first["guarantees"] and second["not_checked"] == first["not_checked"]
    assert second["reused_from"]["scan"] == plan["generated_at"]


def test_a_skeptic_may_quote_a_blast_item_as_the_blast_radius(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    quote = _finding(validated_repo, e["key"])["blast_items"][0]["claim"][10:60]
    _save(validated_repo, validated_env, tmp_path, _verdict_for_releases(
        validated_repo, e["key"], "narrowed", holds="The loop does absorb one failure.",
        refuted_claims=[{"field": "blast_radius", "claim": quote, "fact": "x", "evidence": [0]}]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "narrowed" and check["refuted_claims"][0]["claim"] == quote



def test_a_quote_may_not_span_two_blast_items():
    """`_quotes` matches the summary or one item's claim, never words joined across them."""
    f = {"blast_radius": "All callers", "blast_items": [{"claim": "wait forever", "basis": "assumption"},
                                                         {"claim": "and then fail", "basis": "assumption"}]}
    assert verify._quotes(f, "blast_radius", "All callers")
    assert verify._quotes(f, "blast_radius", "wait forever")
    assert verify._quotes(f, "blast_radius", "  AND then   FAIL ")
    assert not verify._quotes(f, "blast_radius", "callers wait")
    assert not verify._quotes(f, "blast_radius", "forever and then")
    assert not verify._quotes({"blast_radius": "x"}, "blast_radius", "")


def test_the_brief_keeps_the_impact_claims_inside_the_claim_and_before_the_defaults(validated_repo, validated_env):
    """#57 adds a `## Defaults to confirm` section after the preconditions; the impact blocks are claims."""
    plan = _prepare(validated_repo, validated_env)
    brief = (validated_repo / _entry(plan, "releases.ts")["brief"]).read_text()
    claim, evidence = brief.index("## The claim"), brief.index("## Evidence as cited")
    for heading in ("### blast_items", "### implicit_guarantees", "### not_checked"):
        assert claim < brief.index(heading) < evidence, heading
    assert brief.index("### not_checked") < brief.index("## Defaults to confirm") < evidence


def test_a_finding_downgraded_for_an_unconfirmed_default_keeps_its_guarantees_and_items(
        validated_repo, validated_env, tmp_path):
    """#57's rule may turn `upheld` into `inconclusive` after settling; the check still carries what this
    ticket's functions wrote, and nothing here caused or prevented the downgrade."""
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "collection.ts")
    queue = _line(validated_repo, "src/sync/collection.ts", "let page = 1")
    _save(validated_repo, validated_env, tmp_path, _v(
        e["key"], "upheld", evidence=[{"type": "code", "ref": f"src/sync/collection.ts:{queue}", "note": "n"}],
        guarantees=[{"of": None, "guarantee": "Pages are fetched in order", "removed_by": "fetching pages in parallel",
                     "evidence": [0]}]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "inconclusive" and "rests on a default no one confirmed" in check["reason"]
    assert check["guarantees"]["state"] == "named" and check["not_checked"] == []
    assert "confirmations" in check


def test_the_claim_hash_covers_the_impact_fields_and_still_ignores_confirmations():
    f = {"failure_mode": "f", "preconditions": [{"setting": "S", "confirmation": {"state": "confirmed"}}],
         "not_checked": [{"item": "a", "how_to_check": "b"}], "blast_items": [{"claim": "c", "basis": "assumption"}]}
    base = verify.claim_hash(f)
    assert verify.claim_hash({**f, "preconditions": [{"setting": "S", "confirmation": {"state": "unconfirmed"}}]}) == base
    assert verify.claim_hash({**f, "not_checked": [{"item": "a", "how_to_check": "other"}]}) != base
    assert verify.claim_hash({**f, "blast_items": [{"claim": "c2", "basis": "assumption"}]}) != base
    assert verify.claim_hash({**f, "implicit_guarantees": []}) != base


def test_the_skeptic_shares_its_read_budget_and_unresolved_items_do_not_force_inconclusive():
    flat = " ".join((ROOT / "agents" / "thunderstruck-skeptic.md").read_text().split())
    assert "up to 10 files beyond the brief" in flat
    assert "Unresolved not-checked items alone never make a verdict `inconclusive`" in flat
    assert "a material default you could not resolve still keeps the claim from being upheld (rule 8)" in flat
    assert "An unresolved item stays open on the finding" in flat
    assert "You never reword the investigator's" in flat
