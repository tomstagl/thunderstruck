"""Fracture planes (#112): loading, the completeness gate, the matrix, selection.

Spec: docs/superpowers/specs/2026-11-20-fracture-planes-design.md
"""

from __future__ import annotations

import argparse
import dataclasses
import random
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


# --------------------------------------------------------------------------
# Task 4: deterministic selection (AC-3)
# --------------------------------------------------------------------------

SPRING_POM = "<project><parent><artifactId>spring-boot-starter-parent</artifactId></parent></project>\n"
PLAIN_POM = "<project><artifactId>plain</artifactId></project>\n"


def _good(loaded):
    return {"good": loaded[0]["good"]}


def test_glob_star_stays_in_a_segment_and_double_star_spans():
    rx = fp.glob_to_regex("**/pom.xml")
    assert rx.fullmatch("pom.xml") and rx.fullmatch("a/b/pom.xml")
    assert not rx.fullmatch("a/xpom.xml") and not rx.fullmatch("pom.xml.bak")
    assert not fp.glob_to_regex("*.xml").fullmatch("a/pom.xml")
    assert fp.glob_to_regex("*.xml").fullmatch("pom.xml")
    assert not fp.glob_to_regex("a.b").fullmatch("axb")
    gradle = fp.glob_to_regex("**/build.gradle*")
    assert gradle.fullmatch("build.gradle") and gradle.fullmatch("app/build.gradle.kts")
    assert not gradle.fullmatch("build.gradle/x")


def test_select_matches_on_contains_and_reports_the_first_path(loaded):
    files = {"pom.xml": PLAIN_POM, "service/pom.xml": SPRING_POM, "z/pom.xml": SPRING_POM}
    selected, warnings = fp.select(files, files.get, _good(loaded))
    assert selected == [fp.Selected("good", "service/pom.xml", loaded[0]["good"].rubric_hash)]
    assert warnings == []


def test_select_without_a_match_selects_nothing(loaded):
    files = {"pom.xml": PLAIN_POM, "App.java": "spring-boot"}
    assert fp.select(files, files.get, _good(loaded)) == ([], [])


def test_select_is_independent_of_index_order(loaded):
    files = {f"m{i}/pom.xml": (SPRING_POM if i in (7, 12) else PLAIN_POM) for i in range(20)}
    expected = fp.select(files, files.get, _good(loaded))
    keys = list(files)
    for seed in range(5):
        random.Random(seed).shuffle(keys)
        assert fp.select(keys, files.get, _good(loaded)) == expected


def _thirty(marker_at):
    # (depth, path) order is the zero-padded name order here
    return {f"m{i:02d}/pom.xml": (SPRING_POM if i == marker_at else PLAIN_POM) for i in range(30)}


def test_rule_examines_at_most_25_files(loaded):
    files = _thirty(marker_at=25)       # the 26th in order
    selected, _ = fp.select(files, files.get, _good(loaded))
    assert selected == []
    files = _thirty(marker_at=24)       # the 25th
    assert fp.select(files, files.get, _good(loaded))[0][0].matched_by == "m24/pom.xml"


def test_a_truncated_rule_warns(loaded):
    files = _thirty(marker_at=25)
    _, warnings = fp.select(files, files.get, _good(loaded))
    assert warnings == ["plane good: rule **/pom.xml had 30 candidates, examined 25"]


def test_a_root_manifest_sorts_before_a_deep_one(loaded):
    files = _thirty(marker_at=-1)
    files["pom.xml"] = SPRING_POM
    selected, _ = fp.select(files, files.get, _good(loaded))
    assert selected[0].matched_by == "pom.xml"


def test_unreadable_binary_and_huge_files(loaded, tmp_path):
    (tmp_path / "huge").mkdir()
    (tmp_path / "huge" / "pom.xml").write_bytes(b"x" * fp.MAX_READ_BYTES + b"spring-boot")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "pom.xml").write_bytes(b"\xff\xfe\x00spring\xffboot\x00")
    read = fp.head_reader(tmp_path)
    assert read("absent/pom.xml") is None
    assert read("a\udcffb/pom.xml") is None
    assert "spring-boot" not in read("huge/pom.xml")
    assert "�" in read("bin/pom.xml")
    index = ["absent/pom.xml", "a\udcffb/pom.xml", "huge/pom.xml", "bin/pom.xml"]
    assert fp.select(index, read, _good(loaded)) == ([], [])


def test_supersedes_drops_the_superseded_plane(loaded):
    good = loaded[0]["good"]
    top = dataclasses.replace(good, id="top", supersedes=("good",))
    files = {"pom.xml": SPRING_POM}
    selected, _ = fp.select(files, files.get, {"good": good, "top": top})
    assert [s.plane_id for s in selected] == ["top"]
    # a superseding plane that is not active drops nothing
    idle = dataclasses.replace(top, detect=(fp.DetectRule("**/nothing", None),))
    selected, _ = fp.select(files, files.get, {"good": good, "top": idle})
    assert [s.plane_id for s in selected] == ["good"]


def test_planes_are_selected_in_id_order(loaded):
    good = loaded[0]["good"]
    planes = {"zeta": dataclasses.replace(good, id="zeta"), "alpha": dataclasses.replace(good, id="alpha")}
    files = {"pom.xml": SPRING_POM}
    assert [s.plane_id for s in fp.select(files, files.get, planes)[0]] == ["alpha", "zeta"]


def test_a_rule_without_contains_matches_on_the_path_alone(loaded):
    plane = dataclasses.replace(loaded[0]["good"], detect=(fp.DetectRule("**/Chart.yaml", None),))
    files = {"deploy/Chart.yaml": ""}
    selected, _ = fp.select(files, lambda p: None, {"good": plane})
    assert selected[0].matched_by == "deploy/Chart.yaml"


def test_usable_is_only_called_for_paths_that_match_a_rule(loaded):
    files = {"pom.xml": PLAIN_POM, "src/App.java": "", "README.md": "", "lib/pom.xml": SPRING_POM}
    asked = []
    fp.select(files, files.get, _good(loaded), usable=lambda p: asked.append(p) or True)
    assert sorted(asked) == ["lib/pom.xml", "pom.xml"]


def test_an_unusable_path_is_never_read(loaded):
    files = {"pom.xml": SPRING_POM, "lib/pom.xml": SPRING_POM}
    opened = []
    selected, _ = fp.select(files, lambda p: opened.append(p) or files[p], _good(loaded),
                            usable=lambda p: p != "pom.xml")
    assert opened == ["lib/pom.xml"]
    assert selected[0].matched_by == "lib/pom.xml"


def test_a_symlink_named_pom_xml_is_not_opened(loaded, tmp_path):
    import _common as c
    import signals

    (tmp_path / "real.xml").write_text(SPRING_POM)
    (tmp_path / "pom.xml").symlink_to("real.xml")
    index = {"pom.xml": "120000", "real.xml": "100644"}
    filters = c.Filters.from_profile({})
    opened = []
    read = fp.head_reader(tmp_path)
    selected, _ = fp.select(index, lambda p: opened.append(p) or read(p), _good(loaded),
                            usable=lambda p: signals.plane_usable(tmp_path, p, index[p], filters))
    assert selected == [] and opened == []


def test_a_path_that_is_not_utf8_is_not_usable(monkeypatch, tmp_path):
    import _common as c
    import signals

    monkeypatch.setattr(c, "tracked_file_problem", lambda repo, rel, mode: None)
    filters = c.Filters.from_profile({})
    assert signals.plane_usable(tmp_path, "a\udcffb/pom.xml", "100644", filters) is False
    assert signals.plane_usable(tmp_path, "a/pom.xml", "100644", filters) is True


# signals.build in-process, on copies of the session fixture repository

def _repo_with(src, dest, files):
    from build_fixture import run

    shutil.copytree(src, dest, symlinks=True)
    for rel, body in files.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).write_text(body)
    run(dest, "add", *files)
    run(dest, "commit", "-q", "-m", "feat: add build manifests")
    return dest


def _build(repo, path=None):
    import signals

    return signals.build(argparse.Namespace(
        repo=str(repo), top=10, since="24m", path=path, include_tests=False,
        dormant=0, dormant_limit=0))


@pytest.fixture
def plane_dir(tmp_path, monkeypatch):
    directory = tmp_path / "planes"
    directory.mkdir()
    shutil.copytree(FIXTURES / "good", directory / "good")
    monkeypatch.setattr(fp, "planes_dir", lambda: directory)
    return directory


def test_a_pom_under_a_test_directory_does_not_activate_a_plane(fixture_repo, tmp_path, plane_dir):
    repo = _repo_with(fixture_repo, tmp_path / "repo", {"src/test/resources/pom.xml": SPRING_POM})
    assert _build(repo)["planes"] == []


def test_a_root_manifest_activates_a_plane_when_only_a_subdirectory_is_scanned(
        fixture_repo, tmp_path, plane_dir):
    repo = _repo_with(fixture_repo, tmp_path / "repo", {
        "pom.xml": SPRING_POM,
        "services/foo/App.java": "class App {\n  void run() {}\n}\n",
    })
    payload = _build(repo, path="services/foo")
    good = fp.load_planes(plane_dir)[0]["good"]
    assert payload["planes"] == [{"id": "good", "matched_by": "pom.xml", "rubric_hash": good.rubric_hash}]


def test_a_broken_plane_is_skipped_with_a_warning_and_the_scan_continues(
        fixture_repo, tmp_path, plane_dir):
    shutil.copytree(FIXTURES / "bad-yaml", plane_dir / "bad-yaml")
    repo = _repo_with(fixture_repo, tmp_path / "repo", {"pom.xml": SPRING_POM})
    payload = _build(repo)
    assert "plane skipped: planes/bad-yaml/plane.yaml: not valid YAML" in payload["warnings"]
    assert [p["id"] for p in payload["planes"]] == ["good"]
