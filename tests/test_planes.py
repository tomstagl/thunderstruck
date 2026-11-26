"""Fracture planes (#112): loading, the completeness gate, the matrix, selection.

Spec: docs/superpowers/specs/2026-11-20-fracture-planes-design.md
"""

from __future__ import annotations

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
