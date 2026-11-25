"""#106: lessons a repository keeps reach every later briefing: the file and its
validation, matching, the bundle and the skeptic's brief, the report, and the
shipped example."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c
import lessons

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
NAME = c.LESSONS_FILENAME
MISSING = object()   # an override that leaves the key out
RLO = chr(0x202E)    # right-to-left override
ZWSP = chr(0x200B)   # zero-width space


def lesson(lid: str = "L-001", applies_to=("S10",), **over) -> dict:
    """A valid lesson, with whatever the test overrides (`id` too)."""
    base = {"id": over.pop("id", lid),
            "applies_to": list(applies_to) if isinstance(applies_to, tuple) else applies_to,
            "statement": f"statement of {lid}", "how_to_check": f"how to check {lid}",
            "source": "a review of FR-001", "confirmed_by": "a maintainer", **over}
    return {k: v for k, v in base.items() if v is not MISSING}


def toml_of(*entries: dict) -> str:
    out: list[str] = []
    for entry in entries:
        out.append("[[lesson]]")
        out += [f"{key} = {json.dumps(value)}" for key, value in entry.items()]
        out.append("")
    return "\n".join(out)


def write_lessons(repo: Path, *entries: dict) -> None:
    (repo / NAME).write_text(toml_of(*entries), encoding="utf-8")


def load(repo: Path) -> tuple[dict | None, list[str]]:
    return lessons.load(repo, c.load_catalog(ROOT))


# --- Task 1 -----------------------------------------------------------------
def test_no_lessons_file_means_no_record_and_no_warning(tmp_path):
    assert load(tmp_path) == (None, [])


def test_a_lessons_file_loads_in_file_order_with_each_field_flattened(tmp_path):
    (tmp_path / NAME).write_text(
        '[[lesson]]\nid = "L-001"\napplies_to = ["S28", "S09"]\n'
        'statement = """\nA lock\nalso   makes callers\ttake turns.\n"""\n'
        'how_to_check = "list what it guarantees"\nsource = "FR-001 review"\n'
        'confirmed_by = "a maintainer"\n\n'
        '[[lesson]]\nid = "L-002"\napplies_to = ["all"]\nstatement = "s"\n'
        'how_to_check = "h"\nsource = "x"\nconfirmed_by = "y"\n', encoding="utf-8")
    block, warnings = load(tmp_path)
    assert warnings == []
    assert block["file"] == NAME and block["status"] == "loaded" and block["skipped"] == 0
    assert [l["id"] for l in block["accepted"]] == ["L-001", "L-002"]
    assert block["accepted"][0] == {
        "id": "L-001", "applies_to": ["S28", "S09"],
        "statement": "A lock also makes callers take turns.",
        "how_to_check": "list what it guarantees", "source": "FR-001 review",
        "confirmed_by": "a maintainer"}
    assert block["accepted"][1]["applies_to"] == ["all"]


@pytest.mark.parametrize("over, reason", [
    ({"statement": MISSING}, "statement is missing or not a string"),
    ({"how_to_check": ""}, "how_to_check is empty"),
    ({"source": "  \n "}, "source is empty"),
    ({"confirmed_by": 7}, "confirmed_by is missing or not a string"),
    ({"applies_to": []}, "applies_to must be a non-empty list"),
    ({"applies_to": "S10"}, "applies_to must be a non-empty list"),
    ({"applies_to": ["S99"]}, "unknown pattern id 'S99'"),
    ({"applies_to": ["s10"]}, "(did you mean S10?)"),
    ({"applies_to": ["S22"]}, "S22 is Tier C"),
    ({"applies_to": ["OTHER"]}, "OTHER is never carried by a hotspot"),
    ({"applies_to": ["all", "S10"]}, '"all" must be the only item'),
    ({"applies_to": [["S10"]]}, "is not a string"),
    ({"applies_to": [f"S{n:02d}" for n in range(1, 14)]}, "the limit is 12"),
    ({"extra": "x"}, "unknown key(s) 'extra'"),
    ({"statement": "x" * 601}, "statement is 601 characters; the limit is 600"),
    ({"how_to_check": "x" * 401}, "the limit is 400"),
    ({"source": "x" * 201}, "the limit is 200"),
    ({"confirmed_by": "x" * 121}, "the limit is 120"),
    ({"statement": "ok " + RLO + " reversed"}, "control or invisible character (U+202E)"),
    ({"statement": "zero" + ZWSP + "width"}, "(U+200B)"),
    ({"statement": "nul" + chr(0) + "byte"}, "(U+0000)"),
])
def test_a_malformed_lesson_is_skipped_and_named_by_id(tmp_path, over, reason):
    write_lessons(tmp_path, lesson("L-001"), lesson("L-002", **over), lesson("L-003"))
    block, warnings = load(tmp_path)
    assert [l["id"] for l in block["accepted"]] == ["L-001", "L-003"]
    assert block["skipped"] == 1
    assert len(warnings) == 1 and warnings[0].startswith(f"{NAME}: lesson L-002 (entry 2) skipped: ")
    assert reason in warnings[0], warnings[0]


@pytest.mark.parametrize("bad_id", ["", " L-1", "-L", "L 1", "L/1", "x" * 41, 5, MISSING])
def test_a_lesson_with_a_bad_id_is_named_by_its_position(tmp_path, bad_id):
    write_lessons(tmp_path, lesson("L-001"), lesson("L-002", id=bad_id))
    block, warnings = load(tmp_path)
    assert [l["id"] for l in block["accepted"]] == ["L-001"]
    assert len(warnings) == 1 and "lesson entry 2 skipped: id " in warnings[0]


def test_a_duplicate_id_keeps_the_first_and_names_the_second(tmp_path):
    write_lessons(tmp_path, lesson("L-001", statement="first"), lesson("L-002"),
                  lesson("L-001", statement="second"))
    block, warnings = load(tmp_path)
    assert [l["statement"] for l in block["accepted"] if l["id"] == "L-001"] == ["first"]
    assert warnings == [f"{NAME}: lesson L-001 (entry 3) skipped: duplicate id (first used at entry 1)."]


def test_every_problem_of_one_lesson_is_in_its_one_warning(tmp_path):
    write_lessons(tmp_path, lesson("L-009", statement="", applies_to=["S99"], extra=1))
    _, warnings = load(tmp_path)
    assert len(warnings) == 1
    for reason in ("unknown key(s)", "unknown pattern id 'S99'", "statement is empty"):
        assert reason in warnings[0]


def test_the_text_limits_are_inclusive(tmp_path):
    write_lessons(tmp_path, lesson(statement="s" * 600, how_to_check="h" * 400, source="o" * 200,
                                   confirmed_by="c" * 120, id="x" * 40))
    block, warnings = load(tmp_path)
    assert warnings == [] and len(block["accepted"]) == 1


def test_only_the_first_forty_lessons_are_read(tmp_path):
    write_lessons(tmp_path, *[lesson(f"L-{n:03d}") for n in range(1, 46)])
    block, warnings = load(tmp_path)
    assert len(block["accepted"]) == 40 and block["skipped"] == 5
    assert warnings == [f"{NAME} has 45 lessons; only the first 40 are read and 5 were skipped."]


def test_a_file_with_no_lesson_table_says_so(tmp_path):
    (tmp_path / NAME).write_text("# nothing here yet\n[lessons]\nx = 1\n", encoding="utf-8")
    block, warnings = load(tmp_path)
    assert block["status"] == "loaded" and block["accepted"] == []
    assert any("unknown top-level key(s) 'lessons'" in w for w in warnings)
    assert any("has no [[lesson]] entry" in w for w in warnings)


def test_lesson_must_be_an_array_of_tables(tmp_path):
    (tmp_path / NAME).write_text('lesson = "text"\n', encoding="utf-8")
    block, warnings = load(tmp_path)
    assert block["status"] == "not_loaded" and block["accepted"] == []
    assert warnings == [f"{NAME}: `lesson` must be an array of tables ([[lesson]]); no lessons were applied."]


def test_an_entry_that_is_not_a_table_is_skipped(tmp_path):
    (tmp_path / NAME).write_text("lesson = [1, 2]\n", encoding="utf-8")
    block, warnings = load(tmp_path)
    assert block["accepted"] == [] and block["skipped"] == 2
    assert warnings[0] == f"{NAME}: lesson entry 1 skipped: is not a table."


BROKEN_FILES = {   # kind -> (the file's bytes, what the warning says)
    "syntax": (b"lesson = [", "is not valid TOML"),
    "not utf-8": (b"\xff\xfe[[lesson]]", "is not valid UTF-8"),
    "too large": (b"# " + b"x" * (lessons.MAX_FILE_BYTES + 1), "is larger than 64 KiB"),
}


@pytest.mark.parametrize("kind", sorted(BROKEN_FILES))
def test_a_broken_file_is_reported_and_loads_nothing(tmp_path, kind):
    body, reason = BROKEN_FILES[kind]
    (tmp_path / NAME).write_bytes(body)
    block, warnings = load(tmp_path)
    assert block["status"] == "not_loaded" and block["accepted"] == []
    assert len(warnings) == 1 and warnings[0].startswith(f"{NAME} {reason}")
    assert warnings[0].endswith("no lessons were applied.")


def test_a_file_exactly_at_the_size_limit_is_read(tmp_path):
    (tmp_path / NAME).write_text("#" * (lessons.MAX_FILE_BYTES - 1) + "\n", encoding="utf-8")
    block, warnings = load(tmp_path)
    assert block["status"] == "loaded" and "is larger than" not in " ".join(warnings)


def test_a_symlink_a_directory_and_a_fifo_are_never_opened(tmp_path):
    outside = tmp_path / "outside.toml"
    outside.write_text(toml_of(lesson("L-001")), encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / NAME).symlink_to(outside)
    block, warnings = load(repo)
    assert block["accepted"] == [] and "symbolic link" in warnings[0]
    (repo / NAME).unlink()
    (repo / NAME).mkdir()
    assert "is not a regular file" in load(repo)[1][0]
    (repo / NAME).rmdir()
    os.mkfifo(repo / NAME)
    assert "is not a regular file" in load(repo)[1][0]


def test_a_received_value_is_quoted_safely_in_a_warning(tmp_path):
    hostile = "x](https://evil.example)\n# fake heading " + RLO
    write_lessons(tmp_path, lesson("L-001", id=hostile))
    _, warnings = load(tmp_path)
    assert len(warnings) == 1 and "\n" not in warnings[0] and RLO not in warnings[0]
    assert warnings[0].startswith(f"{NAME}: lesson entry 1 skipped: id ")


def test_a_syntax_error_message_is_flattened_and_capped(tmp_path):
    (tmp_path / NAME).write_text('[[lesson]]\nid = "a"\nid = "b"\n', encoding="utf-8")
    _, warnings = load(tmp_path)
    assert len(warnings) == 1 and "\n" not in warnings[0] and len(warnings[0]) < 260


def test_a_byte_order_mark_is_not_content(tmp_path):
    (tmp_path / NAME).write_bytes(b"\xef\xbb\xbf" + toml_of(lesson("L-001")).encode("utf-8"))
    block, warnings = load(tmp_path)
    assert warnings == [] and [l["id"] for l in block["accepted"]] == ["L-001"]


def test_a_fifo_swapped_in_after_the_check_cannot_hang_the_scan(tmp_path):
    """The check on the path passes (patched here, as if the name were a file a moment ago), then
    the name is a FIFO with no writer: opening it blocking would wait for ever. A timeout fails the
    test instead of hanging the run."""
    os.mkfifo(tmp_path / NAME)
    code = ("import sys, pathlib; sys.path.insert(0, %r); import _common as c, lessons; "
            "c.tracked_file_problem = lambda *a, **k: None; "
            "print(lessons._read(pathlib.Path(%r)))" % (str(SCRIPTS), str(tmp_path)))
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "(None, 'is not a regular file in the working tree')"
