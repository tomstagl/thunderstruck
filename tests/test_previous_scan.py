"""#98: a re-scan keeps the scan it replaces, and a window can be repeated."""

from __future__ import annotations

import json
from pathlib import Path

import _common as c


def _hotspots(head="a" * 40, since_date="2025-11-22", top=10, path=None, include_tests=False,
              generated_at="2026-11-22T10:00:00+00:00") -> dict:
    return {"generated_at": generated_at, "repo": {"head": head},
            "window": {"since_date": since_date},
            "config": {"top": top, "path": path, "include_tests": include_tests}}


# --------------------------------------------------------------------------
# Task 1: the scan identity and the finished test (AC-1, AC-2)
# --------------------------------------------------------------------------


def test_scan_identity_is_the_tuple_of_the_spec():
    ident = c.scan_identity(_hotspots(path="src", include_tests=True))
    assert ident == ("a" * 40, "2025-11-22", 10, "src", True, c.REPORT_SCHEMA_VERSION)


def test_scan_identity_differs_on_each_part():
    base = c.scan_identity(_hotspots())
    for change in ({"head": "b" * 40}, {"since_date": "2025-12-01"}, {"top": 5},
                   {"path": "src"}, {"include_tests": True}):
        assert c.scan_identity(_hotspots(**change)) != base, change


def test_scan_identity_is_none_for_a_document_missing_a_part():
    for broken in ({}, {"repo": {}, "window": {}, "config": {}},
                   {k: v for k, v in _hotspots().items() if k != "window"},
                   {k: v for k, v in _hotspots().items() if k != "config"}, None, [], "x"):
        assert c.scan_identity(broken) is None
    no_head = _hotspots()
    del no_head["repo"]["head"]
    assert c.scan_identity(no_head) is None


def _out(tmp_path: Path, hotspots=None, report=None) -> Path:
    out = tmp_path / ".thunderstruck"
    out.mkdir(parents=True)
    if hotspots is not None:
        (out / "hotspots.json").write_text(json.dumps(hotspots))
    if report is not None:
        (out / "report.json").write_text(json.dumps(report))
    return out


def test_scan_finished_only_when_the_report_belongs_to_the_scan(tmp_path):
    hs = _hotspots()
    assert c.scan_finished(_out(tmp_path / "a", hs, {"scanned_at": hs["generated_at"]})) is True
    assert c.scan_finished(_out(tmp_path / "b", hs, {"scanned_at": "2020-01-01T00:00:00+00:00"})) is False
    # report.json's own generated_at is the render time and says nothing about the scan
    assert c.scan_finished(_out(tmp_path / "c", hs, {"generated_at": hs["generated_at"]})) is False


def test_scan_finished_is_false_when_a_file_is_missing_or_unreadable(tmp_path):
    hs = _hotspots()
    assert c.scan_finished(_out(tmp_path / "a", hs)) is False
    assert c.scan_finished(_out(tmp_path / "b", report={"scanned_at": "x"})) is False
    out = _out(tmp_path / "c", hs)
    (out / "report.json").write_text("{not json")
    assert c.scan_finished(out) is False
    out = _out(tmp_path / "d", hs)
    (out / "report.json").write_text("[]")
    assert c.scan_finished(out) is False
    assert c.scan_finished(tmp_path / "nowhere") is False


# --------------------------------------------------------------------------
# Task 2: the archive (AC-1, AC-2, AC-5)
# --------------------------------------------------------------------------

import shutil  # noqa: E402

import pytest  # noqa: E402

import previous  # noqa: E402

COPIED = ["hotspots.json", "report.json", "report.md", "report.html", "index.json",
          "validation.json", "usage.json", "findings/FR-a.json", "checks/verdicts.json",
          "checks/run.json"]
NOT_COPIED = ["bundles/x.md", "checks/briefs/k.md", "deps/pkg/a.py", "context.json",
              "hook-trace.jsonl", "tickets/k.md"]


def _scan(repo: Path, hotspots: dict | None = None, files=COPIED + NOT_COPIED) -> Path:
    """A finished `.thunderstruck/` whose files each hold their own name."""
    hs = hotspots or _hotspots()
    out = repo / ".thunderstruck"
    for rel in files:
        f = out / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"old {rel}\n")
    (out / "hotspots.json").write_text(json.dumps(hs))
    (out / "report.json").write_text(json.dumps({"scanned_at": hs["generated_at"]}))
    return out


def _new(**change) -> tuple:
    return c.scan_identity(_hotspots(**change))


def test_a_changed_scan_is_copied_with_exactly_the_listed_paths(tmp_path):
    out = _scan(tmp_path)
    result = previous.archive(tmp_path, _new(head="b" * 40))
    assert result["archived"] == "20261122-aaaaaaa"
    assert result["warning"] == previous.warning_for(result["previous"])
    assert result["previous"] == {"archived": "20261122-aaaaaaa",
                                  "generated_at": "2026-11-22T10:00:00+00:00",
                                  "head": "a" * 40, "since_date": "2025-11-22"}
    dest = out / "previous" / "20261122-aaaaaaa"
    got = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
    assert got == sorted(COPIED)
    assert (dest / "findings/FR-a.json").read_text() == "old findings/FR-a.json\n"
    assert (dest / "report.md").read_text() == "old report.md\n"
    # a copy, not a move: the live files stay where the checkpoint reads them
    assert (out / "findings/FR-a.json").is_file() and (out / "bundles/x.md").is_file()


@pytest.mark.parametrize("change", [{"head": "b" * 40}, {"since_date": "2025-12-01"},
                                    {"top": 5}, {"path": "src"}, {"include_tests": True}])
def test_each_part_of_the_identity_triggers_an_archive(tmp_path, change):
    _scan(tmp_path)
    assert previous.archive(tmp_path, _new(**change))["archived"]


def test_a_different_report_schema_triggers_an_archive(tmp_path):
    _scan(tmp_path)
    newer = _new()[:5] + ("thunderstruck.report/v99",)
    assert previous.archive(tmp_path, newer)["archived"]


def test_the_same_scan_archives_nothing(tmp_path):
    out = _scan(tmp_path)
    result = previous.archive(tmp_path, _new())
    assert result == {"archived": None, "warning": None, "previous": None}
    assert not (out / "previous").exists()


def test_an_unfinished_scan_archives_nothing(tmp_path):
    out = _scan(tmp_path)
    (out / "report.json").unlink()
    assert previous.archive(tmp_path, _new(head="b" * 40))["archived"] is None
    (out / "report.json").write_text(json.dumps({"scanned_at": "2020-01-01T00:00:00+00:00"}))
    assert previous.archive(tmp_path, _new(head="b" * 40))["archived"] is None
    assert not (out / "previous").exists()


def test_no_earlier_scan_archives_nothing(tmp_path):
    assert previous.archive(tmp_path, _new()) == {"archived": None, "warning": None, "previous": None}


def test_a_name_clash_gets_a_suffix(tmp_path):
    out = _scan(tmp_path)
    (out / "previous" / "20261122-aaaaaaa").mkdir(parents=True)
    assert previous.archive(tmp_path, _new(head="b" * 40))["archived"] == "20261122-aaaaaaa-2"
    _scan(tmp_path)
    assert previous.archive(tmp_path, _new(head="b" * 40))["archived"] == "20261122-aaaaaaa-3"


def test_the_warning_says_what_was_replaced_and_where(tmp_path):
    _scan(tmp_path)
    warning = previous.warning_for({"archived": "20261122-aaaaaaa", "generated_at": "2026-11-22T10:00:00+00:00",
                                    "head": "a" * 40, "since_date": "2025-11-22"})
    assert warning == ("the earlier scan of 2026-11-22 (head aaaaaaa, since 2025-11-22) was replaced; "
                       "a copy is in .thunderstruck/previous/20261122-aaaaaaa/. Finding ids (FR-001) "
                       "are numbered per scan: refer to a finding by its key.")


def test_three_copies_are_kept_and_only_matching_directories_are_removed(tmp_path):
    out = _scan(tmp_path)
    prev = out / "previous"
    for name in ("20260101-1111111", "20260102-2222222", "20260103-3333333"):
        (prev / name).mkdir(parents=True)
    (prev / "notes").mkdir()
    (prev / "20260101-zzzzzzz").mkdir()
    (prev / "README.txt").write_text("mine\n")
    result = previous.archive(tmp_path, _new(head="b" * 40))
    assert result["archived"] == "20261122-aaaaaaa"
    kept = sorted(p.name for p in prev.iterdir())
    assert kept == sorted(["20260102-2222222", "20260103-3333333", "20261122-aaaaaaa",
                           "20260101-zzzzzzz", "README.txt", "notes"])
    assert not (prev / "20260101-1111111").exists()


def test_pruning_never_touches_anything_outside_previous(tmp_path):
    out = _scan(tmp_path)
    for name in ("20260101-1111111", "20260102-2222222", "20260103-3333333"):
        (out / "previous" / name).mkdir(parents=True)
    outside = tmp_path / "20250101-0000000"
    outside.mkdir()
    previous.archive(tmp_path, _new(head="b" * 40))
    assert outside.is_dir() and (out / "findings").is_dir() and (tmp_path / ".thunderstruck/hotspots.json").is_file()


def test_a_symlinked_previous_is_skipped_with_a_warning(tmp_path):
    out = _scan(tmp_path)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (out / "previous").symlink_to(target)
    result = previous.archive(tmp_path, _new(head="b" * 40))
    assert result["archived"] is None and result["warning"] and "previous" in result["warning"]
    assert list(target.iterdir()) == []
    assert result["previous"]["archived"] is None


def test_a_previous_that_is_a_file_is_skipped_with_a_warning(tmp_path):
    out = _scan(tmp_path)
    (out / "previous").write_text("not a directory\n")
    result = previous.archive(tmp_path, _new(head="b" * 40))
    assert result["archived"] is None and result["warning"]
    assert (out / "previous").read_text() == "not a directory\n"


def test_a_failing_copy_leaves_no_partial_directory(tmp_path, monkeypatch):
    out = _scan(tmp_path)
    real, calls = shutil.copy2, []

    def flaky(src, dst, *a, **kw):
        calls.append(src)
        if len(calls) == 3:
            raise OSError("disk full")
        return real(src, dst, *a, **kw)

    monkeypatch.setattr(shutil, "copy2", flaky)
    result = previous.archive(tmp_path, _new(head="b" * 40))
    assert result["archived"] is None
    assert "could not be kept" in result["warning"] and "disk full" in result["warning"]
    assert "Finding ids (FR-001) are numbered per scan" in result["warning"]
    assert result["previous"]["archived"] is None
    assert list((out / "previous").iterdir()) == []
    assert (out / "findings/FR-a.json").is_file()
