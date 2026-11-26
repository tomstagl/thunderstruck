"""Fracture planes (#112): loading, the completeness gate, the matrix, selection.

Spec: docs/superpowers/specs/2026-11-20-fracture-planes-design.md
"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest

import fracture_planes as fp

FIXTURES = Path(__file__).resolve().parent / "planes" / "fixtures"


@pytest.fixture(scope="module")
def loaded():
    return fp.load_planes(FIXTURES)


# --------------------------------------------------------------------------
# Task 1: the manifest and its loader (AC-1)
# --------------------------------------------------------------------------


def test_a_good_plane_loads_with_every_field(plugin_root, loaded):
    planes, _ = fp.load_planes(plugin_root / "tests" / "planes" / "fixtures")
    good = planes["good"]
    assert good.id == "good"
    assert good.title == "Example stack"
    assert good.maturity == "seed"
    assert good.languages == ("java",)
    assert good.detect == (fp.DetectRule(file="**/pom.xml", contains="spring-boot"),)
    assert good.supersedes == ()
    assert good.cells == {
        "S02": {"na": "no such failure on this example stack"},
        "S03": {"planned": "not yet written"},
    }
    assert good.rubric["S01"].pattern_id == "S01"
    assert good.rubric["S01"].text.startswith("**Counts as protection.**")
    assert good.general.startswith("Check the protection at the call site")
    assert good.rubric_hash.startswith("sha256:")


MALFORMED = {
    "bad-schema": ("plane.yaml", "schema must be 'thunderstruck.plane/v1'"),
    "bad-id": ("plane.yaml", "id 'some-other-id' does not match the directory"),
    "bad-maturity": ("plane.yaml", "maturity must be one of seed, calibrated"),
    "bad-yaml": ("plane.yaml", "not valid YAML"),
    "bad-no-rubric": ("rubric.md", "missing"),
    "bad-detect": ("plane.yaml", "detect[0] needs a non-empty 'file'"),
    "bad-cell": ("plane.yaml", "cells.S02 needs a non-empty reason"),
    "bad-heading": ("rubric.md", "unrecognised heading '## S01 — Timeouts'"),
    "bad-supersedes-unknown": ("plane.yaml", "supersedes unknown plane 'not-installed'"),
    "bad-supersedes-cycle-a": ("plane.yaml", "supersedes cycle"),
    "bad-supersedes-cycle-b": ("plane.yaml", "supersedes cycle"),
}


@pytest.mark.parametrize("directory", sorted(MALFORMED))
def test_each_malformed_plane_reports_its_file_and_problem(loaded, directory):
    planes, problems = loaded
    file, text = MALFORMED[directory]
    assert directory not in planes
    mine = [p for p in problems if p.startswith(f"planes/{directory}/")]
    assert mine, problems
    assert any(p.startswith(f"planes/{directory}/{file}: ") and text in p for p in mine), mine


def test_a_hash_ignores_cells_and_maturity(loaded):
    planes, _ = loaded
    assert planes["hash-a"].maturity != planes["hash-b"].maturity
    assert planes["hash-a"].cells != planes["hash-b"].cells
    assert planes["hash-a"].rubric_hash == planes["hash-b"].rubric_hash


def test_the_hash_covers_the_title_and_the_rubric(tmp_path):
    for name in ("base", "title", "rubric"):
        shutil.copytree(FIXTURES / "good", tmp_path / name)
        manifest = tmp_path / name / "plane.yaml"
        manifest.write_text(manifest.read_text().replace("id: good", f"id: {name}"))
    title = tmp_path / "title" / "plane.yaml"
    title.write_text(title.read_text().replace("title: Example stack", "title: Other stack"))
    rubric = tmp_path / "rubric" / "rubric.md"
    rubric.write_text(rubric.read_text().replace("explicit deadline", "explicit timeout"))
    planes, problems = fp.load_planes(tmp_path)
    assert problems == []
    hashes = {name: planes[name].rubric_hash for name in planes}
    assert len(set(hashes.values())) == 3


def test_one_bad_plane_does_not_hide_the_good_ones(loaded):
    planes, problems = loaded
    assert problems
    assert {"good", "lf", "hash-a", "hash-b"} <= set(planes)


def test_crlf_rubric_parses_like_lf(tmp_path):
    # core.autocrlf=input would turn a committed CRLF fixture into LF, so the
    # CRLF twin of `lf` is made here, with no final newline as well.
    shutil.copytree(FIXTURES / "lf", tmp_path / "lf")
    shutil.copytree(FIXTURES / "lf", tmp_path / "crlf")
    manifest = tmp_path / "crlf" / "plane.yaml"
    manifest.write_text(manifest.read_text().replace("id: lf", "id: crlf"))
    rubric = tmp_path / "crlf" / "rubric.md"
    rubric.write_bytes(rubric.read_bytes().rstrip(b"\n").replace(b"\n", b"\r\n"))
    planes, problems = fp.load_planes(tmp_path)
    assert problems == []
    assert planes["crlf"].rubric == planes["lf"].rubric
    assert planes["crlf"].general == planes["lf"].general
    assert planes["crlf"].rubric_hash == planes["lf"].rubric_hash


def test_a_missing_directory_loads_nothing(tmp_path):
    assert fp.load_planes(tmp_path / "absent") == ({}, [])


def test_text_before_the_first_section_is_a_problem(tmp_path):
    shutil.copytree(FIXTURES / "good", tmp_path / "good")
    rubric = tmp_path / "good" / "rubric.md"
    rubric.write_text("# Example stack\n\n" + rubric.read_text())
    planes, problems = fp.load_planes(tmp_path)
    assert planes == {}
    assert problems == ["planes/good/rubric.md: text before the first section"]


def test_a_repeated_section_is_a_problem(tmp_path):
    shutil.copytree(FIXTURES / "good", tmp_path / "good")
    rubric = tmp_path / "good" / "rubric.md"
    rubric.write_text(rubric.read_text() + "\n## S01\n\nAgain.\n")
    planes, problems = fp.load_planes(tmp_path)
    assert planes == {}
    assert problems == ["planes/good/rubric.md: section 'S01' appears twice"]


def test_a_plane_superseding_a_skipped_plane_is_skipped_too(tmp_path):
    shutil.copytree(FIXTURES / "good", tmp_path / "top")
    manifest = tmp_path / "top" / "plane.yaml"
    manifest.write_text(manifest.read_text().replace("id: good", "id: top")
                        .replace("supersedes: []", "supersedes: [bad-yaml]"))
    shutil.copytree(FIXTURES / "bad-yaml", tmp_path / "bad-yaml")
    planes, problems = fp.load_planes(tmp_path)
    assert planes == {}
    assert "planes/top/plane.yaml: supersedes unknown plane 'bad-yaml'" in problems


# --------------------------------------------------------------------------
# Task 2: the completeness gate (AC-2)
# --------------------------------------------------------------------------


def _stub_catalog():
    """Four Tier A/B patterns, one Tier C, and the typescript/javascript alias."""
    return {
        "patterns": [
            {"id": "S01", "tier": "A", "detectors": {"java": [{"kind": "regex"}]}},
            {"id": "S02", "tier": "A", "detectors": {"python": [{"kind": "regex"}]}},
            {"id": "S03", "tier": "B", "detectors": {}},
            {"id": "S04", "tier": "B", "detectors": {"java": [{"kind": "regex"}]}},
        ],
        "tier_c": [{"id": "S20"}],
        "languages": {"java": {}, "python": {}, "typescript": {}, "javascript": {}},
        "aliases": {"javascript": "typescript"},
    }


def _complete(loaded, **changes):
    """`good` with S04 declared, so it passes the stub gate, then changed."""
    good = loaded[0]["good"]
    cells = dict(good.cells, S04={"planned": "not yet written"})
    return dataclasses.replace(good, **{"cells": cells, **changes})


def _gate(plane, root=None):
    return fp.check_planes({plane.id: plane}, _stub_catalog(), repo_root=root)


def _with_section(plane, pid, text):
    return dataclasses.replace(plane, rubric=dict(plane.rubric, **{pid: fp.RubricEntry(pid, text)}))


SECTION = "**Counts as protection.** A deadline.\n\n**Does not count.** No deadline."


def test_cell_state_covers_all_four_states(loaded):
    good = loaded[0]["good"]
    assert fp.cell_state(good, "S01") == "rubric"
    assert fp.cell_state(good, "S02") == "na"
    assert fp.cell_state(good, "S03") == "planned"
    assert fp.cell_state(good, "S04") == "missing"


def test_a_complete_plane_passes_the_gate(loaded):
    assert _gate(_complete(loaded)) == []


def test_the_gate_names_each_missing_cell(loaded):
    plane = dataclasses.replace(loaded[0]["good"], id="only-s01", cells={})
    problems = _gate(plane)
    for pid in ("S02", "S03", "S04"):
        assert any("planes/only-s01" in p and pid in p and "no rubric section" in p for p in problems), problems
    assert not any("S01" in p for p in problems)


def test_both_rubric_and_cell_is_a_problem(loaded):
    plane = _complete(loaded, id="both")
    plane = dataclasses.replace(plane, cells=dict(plane.cells, S01={"na": "x"}))
    assert _gate(plane) == ["planes/both/plane.yaml: S01 has both a rubric section and a cells entry"]


def test_unknown_pattern_id_is_a_problem(loaded):
    in_rubric = _with_section(_complete(loaded, id="unknown"), "S20", SECTION)
    assert _gate(in_rubric) == ["planes/unknown/rubric.md: S20 is not a Tier A/B pattern"]
    in_cells = _complete(loaded, id="unknown")
    in_cells = dataclasses.replace(in_cells, cells=dict(in_cells.cells, S99={"na": "x"}))
    assert _gate(in_cells) == ["planes/unknown/plane.yaml: S99 is not a Tier A/B pattern"]


@pytest.mark.parametrize("label", ["**Counts as protection.**", "**Does not count.**"])
def test_section_without_the_two_labels_is_a_problem(loaded, label):
    text = SECTION.replace(label, "")
    plane = _with_section(_complete(loaded, id="labels"), "S01", text)
    assert _gate(plane) == [f"planes/labels/rubric.md: S01 lacks a {label} paragraph"]


def test_a_label_counts_only_at_the_start_of_a_paragraph(loaded):
    text = "Mentions **Counts as protection.** inline.\n\n**Does not count.** No deadline."
    plane = _with_section(_complete(loaded, id="labels"), "S01", text)
    assert _gate(plane) == ["planes/labels/rubric.md: S01 lacks a **Counts as protection.** paragraph"]


def test_oversized_sections_are_a_problem(loaded):
    at_limit = SECTION + " " + "x" * (700 - len(SECTION) - 1)
    assert len(at_limit) == 700
    assert _gate(_with_section(_complete(loaded, id="big"), "S01", at_limit)) == []
    over = _with_section(_complete(loaded, id="big"), "S01", at_limit + "x")
    assert _gate(over) == ["planes/big/rubric.md: S01 is 701 characters, over the 700 limit"]
    general = _complete(loaded, id="big", general="y" * 800)
    assert _gate(general) == []
    general = _complete(loaded, id="big", general="y" * 801)
    assert _gate(general) == ["planes/big/rubric.md: General is 801 characters, over the 800 limit"]


LEDGER = "# Ledger\n\n- **Repository:** example/app\n- **Commit:** `abc123`\n- **n:** 12\n"


def test_calibrated_needs_no_planned_cells_and_a_ledger(loaded, tmp_path):
    calibrated = _complete(loaded, id="cal", maturity="calibrated")
    assert _gate(calibrated, tmp_path) == [
        "planes/cal/plane.yaml: calibrated, but S03 is planned",
        "planes/cal/plane.yaml: calibrated, but S04 is planned",
        "planes/cal: calibrated, but docs/calibration/planes/cal.md is missing or does not name Repository:, Commit: and n:",
    ]
    ledger = tmp_path / "docs" / "calibration" / "planes" / "cal.md"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(LEDGER.replace("- **n:** 12\n", ""))
    no_planned = dataclasses.replace(calibrated, cells={"S02": {"na": "x"}, "S03": {"na": "x"}, "S04": {"na": "x"}})
    assert _gate(no_planned, tmp_path) == [
        "planes/cal: calibrated, but docs/calibration/planes/cal.md is missing or does not name Repository:, Commit: and n:",
    ]
    ledger.write_text(LEDGER)
    assert _gate(no_planned, tmp_path) == []


def test_language_not_in_the_catalog_or_an_alias_key_is_a_problem(loaded):
    unknown = _complete(loaded, id="lang", languages=("go",))
    assert _gate(unknown) == ["planes/lang/plane.yaml: language 'go' is not in the catalog"]
    alias = _complete(loaded, id="lang", languages=("javascript",))
    assert _gate(alias) == [
        "planes/lang/plane.yaml: language 'javascript' is an alias of 'typescript'; name 'typescript'"
    ]
    assert _gate(_complete(loaded, id="lang", languages=("typescript",))) == []


@pytest.mark.parametrize("line, what", [
    ("# Title", "a heading"),
    ("#### Sub", "a heading"),
    ("   ## Indented", "a heading"),
    ("#", "a heading"),
    ("===", "a setext underline"),
    ("  ---", "a setext underline"),
    ("```", "a code fence"),
    ("~~~python", "a code fence"),
])
def test_a_body_with_a_heading_or_a_fence_is_a_problem(loaded, line, what):
    plane = _with_section(_complete(loaded, id="struct"), "S01", SECTION + "\n" + line + "\nmore")
    assert _gate(plane) == [f"planes/struct/rubric.md: S01 contains {what}"]
    general = _complete(loaded, id="struct", general="Intro.\n" + line)
    assert _gate(general) == [f"planes/struct/rubric.md: General contains {what}"]


@pytest.mark.parametrize("line", ["#hashtag", "- a list item", "    #### indented code", "``inline``"])
def test_ordinary_markdown_in_a_body_is_not_structure(loaded, line):
    plane = _with_section(_complete(loaded, id="ok"), "S01", SECTION + "\n" + line)
    assert _gate(plane) == []


def test_the_real_planes_pass_the_gate(catalog):
    planes, problems = fp.load_planes()
    assert problems == []
    assert fp.check_planes(planes, catalog) == []


# --------------------------------------------------------------------------
# Task 3: the generated matrix (AC-7)
# --------------------------------------------------------------------------


def _matrix_row(text, plane_id):
    return next(line for line in text.splitlines() if line.startswith(f"| `{plane_id}` |"))


def test_render_marks_each_cell_state_and_detector(loaded):
    import gen_plane_docs

    text = gen_plane_docs.render({"good": loaded[0]["good"]}, _stub_catalog())
    cells = [cell.strip() for cell in _matrix_row(text, "good").strip("|").split("|")][1:]
    # S01 rubric + java detector, S02 n/a (detector only for python),
    # S03 planned (no detector), S04 undeclared + java detector.
    assert cells == ["R D", "n/a", "planned", "MISSING D"]
    assert "no such failure on this example stack" in text
    assert "not yet written" in text
    assert "`**/pom.xml` containing `spring-boot`" in text


def test_render_with_no_planes_says_so():
    import gen_plane_docs

    text = gen_plane_docs.render({}, _stub_catalog())
    assert text.startswith(gen_plane_docs.BANNER)
    assert "No planes are installed." in text
    assert "| Plane |" not in text


def test_render_is_deterministic_and_has_no_path_or_date(loaded):
    import re

    import gen_plane_docs

    planes = {k: loaded[0][k] for k in ("good", "hash-b")}
    first = gen_plane_docs.render(planes, _stub_catalog())
    assert first == gen_plane_docs.render(dict(reversed(planes.items())), _stub_catalog())
    assert "/Users" not in first and "/tmp" not in first
    assert not re.search(r"\b(19|20)\d\d\b", first)
