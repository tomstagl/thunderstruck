from __future__ import annotations

import _common
from detectors import run_detectors


def _cat(det: dict) -> dict:
    return {"patterns": [{"id": "SX", "tier": "A", "detectors": {"python": [det]}}],
            "aliases": {}}


def test_regex_require_skips_files_without_the_construct():
    det = {"id": "SX-py", "kind": "regex", "pattern": r"\.all\(\)",
           "require": r"^\s*import\s+sqlite3\b"}
    assert run_detectors(_cat(det), "a.py", "x = mask.all()\n", "python") == []
    hits = run_detectors(_cat(det), "a.py", "import sqlite3\nrows = q.all()\n", "python")
    assert [h.line for h in hits] == [2]


def test_triple_quoted_argument_is_a_string_not_a_docstring():
    src = 'def f(cur):\n    cur.execute(\n        """\n        SELECT id FROM t\n        """\n    )\n'
    assert "SELECT id FROM t" in _common.strip_comments(src, "python")


def test_function_and_module_docstrings_are_still_blanked():
    src = '"""Module talks about Retry-After."""\ndef f():\n    """Honours Retry-After."""\n    return 1\n'
    out = _common.strip_comments(src, "python")
    assert "Retry-After" not in out and "return 1" in out


def test_docstring_after_multiline_signature_is_blanked():
    src = 'def f(\n    a,\n) -> int:\n    """Honours Retry-After."""\n    return a\n'
    out = _common.strip_comments(src, "python")
    assert "Retry-After" not in out and "return a" in out


def test_attribute_docstring_is_blanked():
    src = 'TIMEOUT = 5\n"""Retry-After is read elsewhere."""\n'
    assert "Retry-After" not in _common.strip_comments(src, "python")


def test_string_after_assignment_operator_is_kept():
    src = 'Q = \\\n    """\nSELECT id FROM t\n"""\n'
    assert "SELECT id FROM t" in _common.strip_comments(src, "python")


def test_hash_inside_multiline_string_is_kept():
    src = 'Q = """\nSELECT 1 # not a comment\n"""\n'
    assert "# not a comment" in _common.strip_comments(src, "python")


# --- #58: absent_before ------------------------------------------------------
def test_absent_before_excuses_a_regex_hit_within_its_window():
    det = {"id": "SX-py", "kind": "regex", "pattern": r"except\s*:",
           "absent_before": r"guarded\(", "absent_before_window": 3}
    near = "guarded()\ntry:\n    y()\nexcept:\n    pass\n"
    far = "guarded()\nx = 1\ntry:\n    y()\nexcept:\n    pass\n"
    assert run_detectors(_cat(det), "a.py", near, "python") == []
    assert [h.line for h in run_detectors(_cat(det), "a.py", far, "python")] == [5]


def test_absent_before_includes_the_hits_own_line():
    det = {"id": "SX-py", "kind": "regex", "pattern": r"\.add\(",
           "absent_before": r"if not (\w+):\n[^\n]*\.add\(\1\)", "absent_before_window": 1}
    assert run_detectors(_cat(det), "a.py", "if not row:\n    s.add(row)\n", "python") == []
    assert len(run_detectors(_cat(det), "a.py", "if not flag:\n    s.add(row)\n", "python")) == 1


def test_absent_before_moves_a_file_absent_hit_to_the_first_unexcused_anchor():
    det = {"id": "SX-py", "kind": "file_absent", "anchor": r"\.add\(", "absent": r"UPSERT",
           "absent_before": r"if not (\w+):\n[^\n]*\.add\(\1\)", "absent_before_window": 1}
    src = "if not row:\n    s.add(row)\nx = 1\ns.add(other)\n"
    assert [h.line for h in run_detectors(_cat(det), "a.py", src, "python")] == [4]


def test_absent_before_excusing_every_anchor_leaves_no_hit():
    det = {"id": "SX-py", "kind": "file_absent", "anchor": r"\.add\(", "absent": r"UPSERT",
           "absent_before": r"if not (\w+):\n[^\n]*\.add\(\1\)", "absent_before_window": 1}
    src = "if not row:\n    s.add(row)\nif not job:\n    s.add(job)\n"
    assert run_detectors(_cat(det), "a.py", src, "python") == []


def test_a_detector_without_absent_before_is_unchanged():
    det = {"id": "SX-py", "kind": "file_absent", "anchor": r"\.add\(", "absent": r"UPSERT"}
    src = "if not row:\n    s.add(row)\ns.add(other)\n"
    assert [h.line for h in run_detectors(_cat(det), "a.py", src, "python")] == [2]


def test_absent_before_tolerates_crlf():
    det = {"id": "SX-py", "kind": "regex", "pattern": r"except\s*:",
           "absent_before": r"try\s*:[ \t]*\n[^\n]*except", "absent_before_window": 1}
    assert run_detectors(_cat(det), "a.py", "try:\r\nexcept:\r\n    pass\r\n", "python") == []
