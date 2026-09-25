"""#30: the files the scan ranks are the files a finding can cite, and each
ranked file is briefed with its own history only."""

from __future__ import annotations

from pathlib import Path

import _common as c
import signals

RS = signals._RECORD_SEP


# --------------------------------------------------------------------------
# history parser
# --------------------------------------------------------------------------


def _record(sha: str, subject: str, *entries: str) -> str:
    return f"{RS}{sha}\0t\x002026-09-01T00:00:00+00:00\0{subject}\n" + "".join(entries) + "\0"


def _change(path: str, adds: int = 1, dels: int = 0) -> str:
    return f"{adds}\t{dels}\t{path}\0"


def _rename(old: str, new: str) -> str:
    return f"0\t0\t\0{old}\0{new}\0"


def test_history_reads_names_exactly(monkeypatch):
    raw = (_record("b" * 40, "mv", _rename("src/módulo/a.ts", "src/módulo/b.ts"))
           + _record("a" * 40, "fix: one", _change("src/módulo/a.ts"),
                     _change('src/q"t.ts'), _change("src/tab\there.ts"),
                     "-\t-\tsrc/blob.ts\0")
           + _record("c" * 40, "empty"))
    monkeypatch.setattr(c, "git_paths", lambda *a, **k: raw)
    h = signals.collect_history(Path("."), "2026-01-01", c.Filters(include_tests=True))
    per = h["per_file"]
    assert per["src/módulo/b.ts"]["commits"] == 1
    assert per["src/módulo/b.ts"]["shas"] == ["b" * 40]
    assert per["src/módulo/a.ts"]["commits"] == 1 and per["src/módulo/a.ts"]["fix_commits"] == 1
    assert set(per) == {"src/módulo/a.ts", "src/módulo/b.ts", 'src/q"t.ts',
                        "src/tab\there.ts", "src/blob.ts"}
    assert per["src/blob.ts"]["insertions"] == 0
    assert h["total_commits"] == 3
    assert h["commit_files"] == [["src/módulo/a.ts", 'src/q"t.ts', "src/tab\there.ts",
                                  "src/blob.ts"]]
