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
