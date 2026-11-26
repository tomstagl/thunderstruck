"""Fracture planes (#112): loading, the completeness gate, the matrix, selection.

Spec: docs/superpowers/specs/2026-11-20-fracture-planes-design.md
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import shutil
from pathlib import Path

import pytest

import _common as c
import bundle
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


# --------------------------------------------------------------------------
# Task 5: plane guidance in the bundle (AC-4)
# --------------------------------------------------------------------------


def _plane(loaded, pid="ts", languages=("typescript",), sections=None, general=None, rubric_hash=None):
    good = loaded[0]["good"]
    rubric = good.rubric if sections is None else {
        k: fp.RubricEntry(k, v) for k, v in sections.items()}
    return dataclasses.replace(
        good, id=pid, languages=languages, rubric=rubric,
        general=good.general if general is None else general,
        rubric_hash=rubric_hash or f"sha256:{pid}-{len(rubric)}")


def _record(*planes):
    return [{"id": p.id, "matched_by": "package.json", "rubric_hash": p.rubric_hash} for p in planes]


def _section(body: str) -> str:
    if "## Plane guidance" not in body:
        return ""
    rest = body.split("## Plane guidance", 1)[1]
    return "## Plane guidance" + rest.split("\n## ", 1)[0]


def _body(pid, n=1):
    return SECTION + f" Rule {pid} for case {n}."


def test_guidance_is_empty_for_a_language_no_active_plane_covers(loaded, catalog):
    good = loaded[0]["good"]
    assert fp.guidance({"good": good}, ["good"], "python", ["S01"], catalog, include_general=True) == ""
    assert fp.guidance({"good": good}, [], "java", ["S01"], catalog, include_general=True) == ""


def test_guidance_lists_only_requested_patterns_in_id_order_with_general_first(loaded, catalog):
    plane = _plane(loaded, sections={"S01": _body("S01"), "S02": _body("S02"), "S10": _body("S10")})
    text = fp.guidance({"ts": plane}, ["ts"], "typescript", ["S10", "S01", "S05"], catalog,
                       include_general=True)
    assert text.startswith("## Plane guidance\n")
    assert "### ts — Example stack" in text
    assert f"rubric {plane.rubric_hash}" in text
    assert "full rubric: `.thunderstruck/planes/ts.md`" in text
    assert "#### S02" not in text and "#### S05" not in text
    assert text.index(plane.general) < text.index("#### S01") < text.index("#### S10")
    assert _body("S10") in text
    assert "Omitted" not in text


def test_without_general_a_plane_with_no_requested_section_adds_nothing(loaded, catalog):
    plane = _plane(loaded)
    assert fp.guidance({"ts": plane}, ["ts"], "typescript", ["S05"], catalog, include_general=False) == ""
    text = fp.guidance({"ts": plane}, ["ts"], "typescript", ["S01"], catalog, include_general=False)
    assert "#### S01" in text and plane.general not in text


def test_with_general_a_covering_plane_always_shows_its_hash_and_path(loaded, catalog):
    plane = _plane(loaded, general="")
    text = fp.guidance({"ts": plane}, ["ts"], "typescript", [], catalog, include_general=True)
    assert f"rubric {plane.rubric_hash}" in text and "full rubric:" in text and "####" not in text


def test_two_active_planes_both_shown_in_id_order(loaded, catalog):
    planes = {"b": _plane(loaded, "b"), "a": _plane(loaded, "a")}
    first = fp.guidance(planes, ["b", "a"], "typescript", ["S01"], catalog, include_general=True)
    assert first.index("### a — ") < first.index("### b — ")
    assert first.count("#### S01") == 2
    assert first == fp.guidance(dict(reversed(planes.items())), ["a", "b"], "typescript", ["S01"],
                                catalog, include_general=True)


def test_a_js_hotspot_gets_guidance_from_a_typescript_plane(loaded, catalog):
    plane = _plane(loaded)
    assert "#### S01" in fp.guidance({"ts": plane}, ["ts"], "javascript", ["S01"], catalog,
                                     include_general=True)


def test_a_yaml_hotspot_gets_guidance_only_from_a_plane_that_lists_yaml(loaded, catalog):
    yaml_plane = _plane(loaded, "k8s", languages=("yaml",))
    java_plane = _plane(loaded, "jv", languages=("java",))
    planes = {"k8s": yaml_plane, "jv": java_plane}
    text = fp.guidance(planes, ["jv", "k8s"], "yaml", ["S01"], catalog, include_general=True)
    assert "### k8s — " in text and "### jv — " not in text


def test_whole_sections_are_omitted_to_fit_the_cap_and_the_omission_is_named(loaded, catalog):
    sections = {pid: _body(pid) + " " + "w" * 300 for pid in ("S01", "S02", "S03")}
    plane = _plane(loaded, sections=sections)
    full = fp.guidance({"ts": plane}, ["ts"], "typescript", list(sections), catalog, include_general=True)
    cap = c.estimate_tokens(full) - 10
    text, warnings = fp.render_guidance({"ts": plane}, ["ts"], "typescript", list(sections), catalog,
                                        cap_tokens=cap, include_general=True)
    assert c.estimate_tokens(text) <= cap and warnings == []
    assert sections["S01"] in text and sections["S02"] in text
    assert "S03" not in text.replace("Omitted to fit the budget: ts S03.", "")
    assert text.rstrip().endswith("Omitted to fit the budget: ts S03.")
    small = c.estimate_tokens(fp.guidance({"ts": plane}, ["ts"], "typescript", ["S01"], catalog,
                                          include_general=True)) + 15
    text, _ = fp.render_guidance({"ts": plane}, ["ts"], "typescript", list(sections), catalog,
                                 cap_tokens=small, include_general=True)
    assert text.rstrip().endswith("Omitted to fit the budget: ts S02, S03.")
    for pid in ("S02", "S03"):
        assert sections[pid] not in text


def test_the_last_plane_gives_way_first(loaded, catalog):
    sections = {"S01": _body("S01") + " " + "w" * 300}
    planes = {"a": _plane(loaded, "a", sections=sections), "b": _plane(loaded, "b", sections=sections)}
    full = fp.guidance(planes, ["a", "b"], "typescript", ["S01"], catalog, include_general=True)
    text, _ = fp.render_guidance(planes, ["a", "b"], "typescript", ["S01"], catalog,
                                 cap_tokens=c.estimate_tokens(full) - 10, include_general=True)
    assert text.rstrip().endswith("Omitted to fit the budget: b S01.")


def test_the_cap_holds_at_every_budget_and_a_plane_that_cannot_fit_is_left_out_with_a_warning(
        loaded, catalog):
    sections = {pid: _body(pid) + " " + "w" * 500 for pid in ("S01", "S02", "S10")}
    plane = _plane(loaded, sections=sections, general="g" * 700)
    for budget in (100, 300, 1000, 2000, 8000, 30000):
        cap = int(budget * 0.12)
        text, warnings = fp.render_guidance({"ts": plane}, ["ts"], "typescript", list(sections),
                                            catalog, cap_tokens=cap, include_general=True)
        if text:
            assert c.estimate_tokens(text) <= cap, budget
            assert f"rubric {plane.rubric_hash}" in text
        else:
            assert warnings == [f"plane ts: guidance does not fit a {cap}-token cap and is left out"]
    text, _ = fp.render_guidance({"ts": plane}, ["ts"], "typescript", list(sections), catalog,
                                 cap_tokens=int(1000 * 0.12), include_general=True)
    assert text and "General" in text and "####" not in text, "title, hash and path only"


def test_resolve_active_skips_unloaded_and_changed_planes_and_names_them(loaded):
    a, b = _plane(loaded, "a"), _plane(loaded, "b")
    recorded = _record(a, b) + [{"id": "gone", "matched_by": "pom.xml", "rubric_hash": "sha256:x"}]
    recorded[1] = dict(recorded[1], rubric_hash="sha256:old")
    ids, warnings = fp.resolve_active({"a": a, "b": b}, recorded)
    assert ids == ["a"]
    assert warnings == [
        f"plane b changed after signals.py ran (recorded sha256:old, now {b.rubric_hash}); "
        f"its guidance is left out. Re-run signals.py.",
        "plane gone is recorded in hotspots.json but does not load; its guidance is left out.",
    ]
    assert fp.resolve_active({"a": a}, [None, {"id": 3}, "x"]) == ([], [])


def _hs(data, hid):
    return next(h for h in data["hotspots"] + (data.get("dormant") or []) if h["id"] == hid)


def _build_bundle(repo, data, hs, catalog, loaded_planes=None, budget=bundle.DEFAULT_BUDGET_TOKENS,
                  planes_warnings=None):
    return bundle.build_bundle(repo, hs, data, catalog, {}, budget, 15, data["hotspots"], None, None,
                               loaded_planes=loaded_planes, warnings=planes_warnings)


def test_a_bundle_with_no_active_plane_is_byte_identical(scanned_repo, loaded, catalog):
    data = json.loads((scanned_repo / ".thunderstruck" / "hotspots.json").read_text())
    hs = _hs(data, "H01")
    before = _build_bundle(scanned_repo, data, hs, catalog)
    ts, py = _plane(loaded), _plane(loaded, "py", languages=("python",))
    assert _build_bundle(scanned_repo, {**data, "planes": []}, hs, catalog, {"ts": ts}) == before
    assert _build_bundle(scanned_repo, {**data, "planes": _record(py)}, hs, catalog, {"py": py}) == before
    covered = _build_bundle(scanned_repo, {**data, "planes": _record(ts)}, hs, catalog, {"ts": ts})
    assert covered != before
    assert _section(covered).startswith("## Plane guidance")
    assert covered.index("## Detector leads") < covered.index("## Plane guidance")


def test_with_neither_section_the_bundle_is_the_bytes_the_old_formula_gave(scanned_repo, loaded, catalog):
    data = json.loads((scanned_repo / ".thunderstruck" / "hotspots.json").read_text())
    budget = bundle.DEFAULT_BUDGET_TOKENS
    for hid in ("H01", "H04"):
        hs = _hs(data, hid)
        # build_bundle as it was before #112, with no context, observed or lessons section
        text = c.read_text(scanned_repo / hs["file"]) or ""
        own = data.get("own_packages")
        own = own if isinstance(own, dict) else None
        service, observed = bundle.section_service_context(None), bundle.section_observed(None, hs["file"])
        kept = bundle.lessons.investigator_section(*bundle.lessons.for_hotspot(data, hs["id"]))
        fixed = sum(c.estimate_tokens(p) for p in (service, observed, kept) if p)
        rest = max(budget - fixed, budget // 2) if fixed else budget
        parts = [bundle.section_header(hs, data), bundle.section_profile({}), service, observed, kept,
                 bundle.section_boundaries(text, hs["file"], hs["language"], catalog, own),
                 bundle.section_detectors(hs, catalog), bundle.section_retry_layers(hs, data, catalog),
                 bundle.section_source(scanned_repo, hs, int(rest * bundle.SHARE["source"])),
                 bundle.section_history(scanned_repo, hs, data["window"]["since_date"],
                                        int(rest * bundle.SHARE["history"]), 15,
                                        c.profile_fix_keywords({})),
                 bundle.section_related(scanned_repo, hs, data["hotspots"], int(rest * bundle.SHARE["context"]))]
        old = "\n".join(p for p in parts if p).rstrip() + "\n"
        py = _plane(loaded, "py", languages=("python",))
        assert _build_bundle(scanned_repo, data, hs, catalog) == old
        assert _build_bundle(scanned_repo, {**data, "planes": _record(py)}, hs, catalog, {"py": py}) == old


def test_the_source_budget_shrinks_by_the_plane_share_and_the_floor_holds(
        scanned_repo, loaded, catalog, monkeypatch):
    data = json.loads((scanned_repo / ".thunderstruck" / "hotspots.json").read_text())
    hs = _hs(data, "H01")
    ts = _plane(loaded)
    data = {**data, "planes": _record(ts)}
    budgets = []
    monkeypatch.setattr(bundle, "section_source", lambda repo, hs, budget: budgets.append(budget) or "")
    budget = 2000
    planes_text = bundle.section_planes(hs, data, {"ts": ts}, catalog, int(budget * 0.12))
    assert planes_text
    _build_bundle(scanned_repo, data, hs, catalog, {"ts": ts}, budget=budget)
    assert budgets[-1] == int((budget - c.estimate_tokens(planes_text)) * bundle.SHARE["source"])
    lesson = "L" * 400
    monkeypatch.setattr(bundle.lessons, "investigator_section", lambda *a: lesson)
    _build_bundle(scanned_repo, data, hs, catalog, {"ts": ts}, budget=budget)
    fixed = c.estimate_tokens(lesson) + c.estimate_tokens(planes_text)
    assert budgets[-1] == int((budget - fixed) * bundle.SHARE["source"])
    monkeypatch.setattr(bundle.lessons, "investigator_section", lambda *a: "L" * 8000)
    _build_bundle(scanned_repo, data, hs, catalog, {"ts": ts}, budget=budget)
    assert budgets[-1] == int((budget // 2) * bundle.SHARE["source"])


def test_a_rubric_edit_changes_the_bundle_of_every_hotspot_the_plane_covers_and_no_other(
        scanned_repo, loaded, catalog):
    data = json.loads((scanned_repo / ".thunderstruck" / "hotspots.json").read_text())
    hotspots = [_hs(data, "H01"), _hs(data, "H05"), dict(_hs(data, "H02"), language="python")]
    ts = _plane(loaded, rubric_hash="sha256:before")
    # a section for S27, which no fixture hotspot has a lead on
    edited = dataclasses.replace(ts, rubric=dict(ts.rubric, S27=fp.RubricEntry("S27", _body("S27"))),
                                 rubric_hash="sha256:after")
    one = [_build_bundle(scanned_repo, {**data, "planes": _record(ts)}, hs, catalog, {"ts": ts})
           for hs in hotspots]
    two = [_build_bundle(scanned_repo, {**data, "planes": _record(edited)}, hs, catalog, {"ts": edited})
           for hs in hotspots]
    assert one[0] != two[0] and one[1] != two[1]
    assert one[2] == two[2]
    assert _body("S27") not in two[0]


def test_a_plane_edited_after_signals_is_skipped_with_a_warning(scanned_repo, loaded, catalog):
    data = json.loads((scanned_repo / ".thunderstruck" / "hotspots.json").read_text())
    hs = _hs(data, "H01")
    ts = _plane(loaded)
    stale = {**data, "planes": [dict(_record(ts)[0], rubric_hash="sha256:old")]}
    warnings = []
    body = _build_bundle(scanned_repo, stale, hs, catalog, {"ts": ts}, planes_warnings=warnings)
    assert body == _build_bundle(scanned_repo, data, hs, catalog)
    assert warnings and "plane ts changed after signals.py ran" in warnings[0]


def test_a_dormant_bundle_gets_guidance_on_the_same_rule(scanned_repo, loaded, catalog):
    data = json.loads((scanned_repo / ".thunderstruck" / "hotspots.json").read_text())
    assert data["dormant"], "the fixture has a dormant integration point"
    ts = _plane(loaded)
    body = _build_bundle(scanned_repo, {**data, "planes": _record(ts)}, data["dormant"][0], catalog, {"ts": ts})
    assert "## Plane guidance" in body and "#### S01" in body


def test_a_covered_bundle_stays_within_budget(scanned_repo, loaded, catalog):
    data = json.loads((scanned_repo / ".thunderstruck" / "hotspots.json").read_text())
    biggest = SECTION + " " + "w" * (700 - len(SECTION) - 1)
    ids = ["S01", "S02", "S05", "S10", "S11", "S15", "S19"]
    ts = _plane(loaded, sections={pid: biggest for pid in ids}, general="g" * 800)
    for budget in (1000, bundle.DEFAULT_BUDGET_TOKENS):
        for hs in data["hotspots"]:
            body = _build_bundle(scanned_repo, {**data, "planes": _record(ts)}, hs, catalog, {"ts": ts},
                                 budget=budget)
            assert c.estimate_tokens(_section(body)) <= int(budget * 0.12) + 1
            if budget == bundle.DEFAULT_BUDGET_TOKENS:
                # the bound test_bundles_are_within_budget_and_deterministic holds at the
                # default budget; at 1000 the untrimmed sections alone exceed it
                assert c.estimate_tokens(body) <= budget * 1.1, (budget, hs["id"])


# bundle.main and the rubric files

def _write_planes_dir(tmp_path, monkeypatch, *planes, extra=()):
    directory = tmp_path / "plugin-planes"
    directory.mkdir()
    for pid, languages in planes:
        shutil.copytree(FIXTURES / "good", directory / pid)
        manifest = directory / pid / "plane.yaml"
        manifest.write_text(manifest.read_text().replace("id: good", f"id: {pid}")
                            .replace("languages: [java]", f"languages: [{languages}]"))
    for name in extra:
        shutil.copytree(FIXTURES / name, directory / name)
    monkeypatch.setattr(fp, "planes_dir", lambda: directory)
    return fp.load_planes(directory)[0]


def _set_recorded(repo, recorded):
    path = repo / ".thunderstruck" / "hotspots.json"
    data = json.loads(path.read_text())
    if recorded is None:
        data.pop("planes", None)
    else:
        data["planes"] = recorded
    path.write_text(json.dumps(data))


def test_write_plane_rubrics_writes_each_active_plane_deterministically(loaded, tmp_path):
    planes = {"a": _plane(loaded, "a"), "b": _plane(loaded, "b")}
    written = fp.write_plane_rubrics(tmp_path, planes, ["a"])
    assert written == [tmp_path / "planes" / "a.md"]
    first = written[0].read_bytes()
    assert b"\r" not in first and b"## S01" in first and b"## General" in first
    assert not (tmp_path / "planes" / "b.md").exists()
    fp.write_plane_rubrics(tmp_path, planes, ["a"])
    assert written[0].read_bytes() == first
    assert fp.write_plane_rubrics(tmp_path, planes, []) == []
    assert not (tmp_path / "planes").exists()


def test_a_symlink_at_the_planes_directory_is_replaced_and_never_followed(loaded, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("mine")
    out = tmp_path / "out"
    out.mkdir()
    (out / "planes").symlink_to(target, target_is_directory=True)
    fp.write_plane_rubrics(out, {"a": _plane(loaded, "a")}, ["a"])
    assert sorted(p.name for p in target.iterdir()) == ["keep.txt"]
    assert (out / "planes").is_dir() and not (out / "planes").is_symlink()
    assert (out / "planes" / "a.md").is_file()
    (out / "planes").rename(out / "moved")
    (out / "planes").write_text("a file")
    fp.write_plane_rubrics(out, {"a": _plane(loaded, "a")}, ["a"])
    assert (out / "planes" / "a.md").is_file()


def test_bundle_main_embeds_active_guidance_and_writes_the_rubric(scanned_copy, tmp_path, monkeypatch, capsys):
    planes = _write_planes_dir(tmp_path, monkeypatch, ("ts", "typescript"))
    _set_recorded(scanned_copy, _record(planes["ts"]))
    (scanned_copy / ".thunderstruck" / "planes").mkdir(exist_ok=True)
    (scanned_copy / ".thunderstruck" / "planes" / "old.md").write_text("stale")
    assert bundle.main(["--repo", str(scanned_copy)]) == 0
    out = scanned_copy / ".thunderstruck"
    assert sorted(p.name for p in (out / "planes").iterdir()) == ["ts.md"]
    assert "## Plane guidance" in (out / "bundles" / "H01.md").read_text()
    first = json.loads((out / "bundles" / "index.json").read_text())
    assert bundle.main(["--repo", str(scanned_copy)]) == 0
    second = json.loads((out / "bundles" / "index.json").read_text())
    assert [b["bundle_hash"] for b in first["bundles"]] == [b["bundle_hash"] for b in second["bundles"]]


def test_a_stale_plane_file_is_removed_on_the_next_bundle_run(scanned_copy, tmp_path, monkeypatch):
    _write_planes_dir(tmp_path, monkeypatch, ("ts", "typescript"))
    _set_recorded(scanned_copy, [])
    (scanned_copy / ".thunderstruck" / "planes").mkdir(exist_ok=True)
    (scanned_copy / ".thunderstruck" / "planes" / "ts.md").write_text("from an earlier scan")
    assert bundle.main(["--repo", str(scanned_copy)]) == 0
    assert not (scanned_copy / ".thunderstruck" / "planes").exists()


def test_a_hotspots_json_without_a_planes_key_does_not_crash_bundle(scanned_copy, tmp_path, monkeypatch, capsys):
    _write_planes_dir(tmp_path, monkeypatch, ("ts", "typescript"))
    _set_recorded(scanned_copy, None)
    assert bundle.main(["--repo", str(scanned_copy)]) == 0
    assert "hotspots.json records no planes (written before this version); re-run signals.py" \
        in capsys.readouterr().err
    assert "## Plane guidance" not in (scanned_copy / ".thunderstruck" / "bundles" / "H01.md").read_text()


def test_a_broken_plane_does_not_stop_bundle_main(scanned_copy, tmp_path, monkeypatch, capsys):
    _write_planes_dir(tmp_path, monkeypatch, extra=("bad-yaml",))
    assert bundle.main(["--repo", str(scanned_copy)]) == 0
    assert "plane skipped: planes/bad-yaml/plane.yaml: not valid YAML" in capsys.readouterr().err


def test_bundle_main_warns_about_a_stale_plane(scanned_copy, tmp_path, monkeypatch, capsys):
    planes = _write_planes_dir(tmp_path, monkeypatch, ("ts", "typescript"))
    _set_recorded(scanned_copy, [dict(_record(planes["ts"])[0], rubric_hash="sha256:old")])
    assert bundle.main(["--repo", str(scanned_copy)]) == 0
    assert "plane ts changed after signals.py ran" in capsys.readouterr().err
    assert not (scanned_copy / ".thunderstruck" / "planes").exists()
    assert "## Plane guidance" not in (scanned_copy / ".thunderstruck" / "bundles" / "H01.md").read_text()
