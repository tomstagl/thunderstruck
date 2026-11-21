"""Fracture-plane contracts: loading, coverage, and deterministic selection."""

from __future__ import annotations

from importlib import import_module

import pytest
import yaml

from test_pipeline import _hotspots

RUBRIC = (
    "## General\n\nCheck the protection at the call site.\n\n"
    "## S01\n\n**Counts as protection.** An explicit deadline.\n\n"
    "**Does not count.** An unbounded wait.\n"
)


@pytest.fixture
def api():
    # Keep the integration test runnable before the loader exists.
    return import_module("fracture_planes")


def _write_plane(root, plane_id, *, rubric=RUBRIC, **overrides):
    directory = root / plane_id
    directory.mkdir()
    manifest = {
        "schema": "thunderstruck.plane/v1",
        "id": plane_id,
        "title": "Example stack",
        "maturity": "seed",
        "languages": ["java"],
        "detect": [{"file": "**/pom.xml", "contains": "spring-boot"}],
        "supersedes": [],
        "cells": {},
    }
    manifest.update(overrides)
    (directory / "plane.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    if rubric is not None:
        (directory / "rubric.md").write_bytes(rubric.encode("utf-8"))


def test_loads_manifest_and_normalizes_rubric_line_endings(api, tmp_path):
    _write_plane(tmp_path, "lf")
    _write_plane(tmp_path, "crlf", rubric=RUBRIC.replace("\n", "\r\n"))
    _write_plane(tmp_path, "no-final-newline", rubric=RUBRIC.rstrip("\n"))
    planes, problems = api.load_planes(tmp_path)
    assert problems == []
    plane = planes["lf"]
    assert plane.maturity == "seed"
    assert plane.languages == ("java",)
    assert plane.detect == (api.DetectRule("**/pom.xml", "spring-boot"),)
    assert plane.general == "Check the protection at the call site."
    section = plane.rubric["S01"].text
    assert section.startswith("**Counts as protection.**")
    assert planes["crlf"].rubric["S01"].text == section
    assert planes["no-final-newline"].rubric["S01"].text == section
    assert planes["crlf"].rubric_hash == plane.rubric_hash
    assert plane.rubric_hash.startswith("sha256:")


@pytest.mark.parametrize(("overrides", "filename", "problem"), [
    ({"schema": "wrong/v1"}, "plane.yaml", "schema"),
    ({"id": "not-the-directory"}, "plane.yaml", "id"),
    ({"maturity": "unknown"}, "plane.yaml", "maturity"),
    ({"detect": [{"contains": "spring-boot"}]}, "plane.yaml", "detect"),
    ({"rubric": None}, "rubric.md", None),
    ({"rubric": RUBRIC.replace("## S01", "## S01 — Timeouts")}, "rubric.md", "heading"),
    ({"supersedes": ["not-installed"]}, "plane.yaml", "not-installed"),
])
def test_malformed_plane_is_reported_without_hiding_valid_planes(
    api, tmp_path, overrides, filename, problem,
):
    _write_plane(tmp_path, "good")
    _write_plane(tmp_path, "bad", **overrides)
    planes, problems = api.load_planes(tmp_path)
    assert set(planes) == {"good"}
    assert any(message.startswith(f"planes/bad/{filename}:")
               and (problem is None or problem in message.split(":", 1)[1])
               for message in problems)


def test_loader_rejects_every_plane_in_a_supersedes_cycle(api, tmp_path):
    _write_plane(tmp_path, "good")
    _write_plane(tmp_path, "cycle-a", supersedes=["cycle-b"])
    _write_plane(tmp_path, "cycle-b", supersedes=["cycle-a"])
    planes, problems = api.load_planes(tmp_path)
    assert set(planes) == {"good"}
    for plane_id in ("cycle-a", "cycle-b"):
        assert any(message.startswith(f"planes/{plane_id}/plane.yaml:")
                   for message in problems)


def test_gate_names_a_missing_tier_a_or_b_cell(api, tmp_path):
    _write_plane(tmp_path, "good")
    planes, problems = api.load_planes(tmp_path)
    assert problems == []
    plane = planes["good"]
    assert api.cell_state(plane, "S01") == "rubric"
    assert api.cell_state(plane, "S02") == "missing"
    catalog = {
        "languages": {"java": {}}, "aliases": {},
        "patterns": [{"id": "S01", "tier": "A"}, {"id": "S02", "tier": "B"}],
    }
    problems = api.check_planes(planes, catalog)
    assert len(problems) == 1
    assert "planes/good" in problems[0] and "S02" in problems[0]


def test_selection_is_independent_of_index_order_and_ignores_unmatched_paths(api, tmp_path):
    _write_plane(tmp_path, "good")
    planes, problems = api.load_planes(tmp_path)
    assert problems == []
    paths = {"deep/app/pom.xml": "spring-boot", "pom.xml": "spring-boot", "README.md": ""}
    checked = []

    def usable(path):
        checked.append(path)
        return True

    selected, warnings = api.select(paths, paths.get, planes, usable=usable)
    assert warnings == []
    assert [(item.plane_id, item.matched_by) for item in selected] == [("good", "pom.xml")]
    assert "README.md" not in checked
    assert api.select(reversed(paths), paths.get, planes) == (selected, warnings)


def test_selection_warns_and_does_not_read_beyond_the_rule_limit(api, tmp_path):
    _write_plane(tmp_path, "good")
    planes, problems = api.load_planes(tmp_path)
    assert problems == []
    paths = [f"app-{i:02d}/pom.xml" for i in range(30)]
    reads = []

    def read(path):
        reads.append(path)
        return "spring-boot" if path == paths[25] else "plain Maven"

    selected, warnings = api.select(reversed(paths), read, planes)
    assert selected == []
    assert reads == paths[:25]
    assert warnings == ["plane good: rule **/pom.xml had 30 candidates, examined 25"]


def test_hotspots_records_an_empty_plane_selection(scanned_repo):
    assert _hotspots(scanned_repo)["planes"] == []
