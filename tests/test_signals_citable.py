"""#30: the files the scan ranks are the files a finding can cite, and each
ranked file is briefed with its own history only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c
import signals
from build_fixture import isolated_git_env
from validate import Validator

ROOT = Path(__file__).resolve().parent.parent
LINUX = sys.platform.startswith("linux")

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


# --------------------------------------------------------------------------
# a repository with every kind of entry a finding can't cite
# --------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                           *args], check=True, capture_output=True, text=True,
                          env=isolated_git_env()).stdout


def _init(repo: Path) -> None:
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")


def _commit(repo: Path, subject: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", subject)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ts(n: int) -> str:
    branches = "".join(f"  if (x === {i}) {{ return {i * n}; }}\n" for i in range(n % 5 + 1))
    return f"export function step(x: number): number {{\n{branches}  return x;\n}}\n"


@pytest.fixture(scope="module")
def citable_repo(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("citable")
    root, sub = base / "repo", base / "sub"
    _init(sub)
    _write(sub / "x.ts", "export const x = 1;\n")
    _commit(sub, "sub")
    _init(root)
    for n in range(20):
        for name in ("src/plain.ts", "src/módulo/a.ts", "src/[id].ts", "src/gone.ts"):
            _write(root / name, _ts(n))
        _commit(root, f"feat: step {n}")
    _write(root / "src/i.ts", _ts(99))
    _commit(root, "feat: only i")
    _git(root, "mv", "src/módulo/a.ts", "src/módulo/b.ts")
    _commit(root, "refactor: rename")
    (root / "src/link.ts").symlink_to("plain.ts")
    _commit(root, "feat: link")
    # not under vendor/, which the default filters drop before the candidate rule
    _git(root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "libs/sub.ts")
    _commit(root, "feat: submodule")
    if LINUX:
        _write(root / os.fsdecode(b"src/\xff.ts"), _ts(1))
        _commit(root, "feat: latin-1 name")
    (root / "src/gone.ts").unlink()                    # working tree only
    (root / "src/gone.ts").symlink_to("plain.ts")
    return root


@pytest.fixture(scope="module")
def scanned(citable_repo: Path) -> dict:
    for args in (["signals.py", "--repo", str(citable_repo), "--top", "0", "--since", "24m"],
                 ["bundle.py", "--repo", str(citable_repo)]):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / args[0]), *args[1:]],
                              capture_output=True, text=True, cwd=str(citable_repo))
        assert proc.returncode == 0, f"{args} failed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads((c.out_dir(citable_repo) / "hotspots.json").read_text(encoding="utf-8"))


def _ranked(scanned: dict) -> set[str]:
    return {h["file"] for h in scanned["hotspots"]}


def _bundle(repo: Path, file: str) -> str:
    index = json.loads((c.out_dir(repo) / "bundles" / "index.json").read_text(encoding="utf-8"))
    entry = next(b for b in index["bundles"] if b["file"] == file)
    return Path(entry["bundle"]).read_text(encoding="utf-8")


def test_ranked_set_is_the_citable_set(citable_repo, scanned):
    """The success measure, judged by the real validator rather than a copy of its rule."""
    langmap = c.language_map(c.load_catalog())
    changed = signals.collect_history(citable_repo, "2000-01-01", c.Filters())["per_file"]
    validator = Validator(citable_repo, {"hotspots": []}, c.load_catalog())
    citable = {p for p in c.tracked_index(citable_repo)
               if p in changed and c.detect_language(p, langmap)
               and c.is_utf8(p)                # the one deliberate narrowing (spec §3)
               and validator._resolve(p)[2] is None}
    assert _ranked(scanned) == citable
    assert citable == {"src/plain.ts", "src/módulo/b.ts", "src/[id].ts", "src/i.ts"}


def test_links_and_submodules_are_never_ranked(scanned):
    """AC-1."""
    assert not {"src/link.ts", "libs/sub.ts", "src/gone.ts"} & _ranked(scanned)


def test_non_ascii_names_are_ranked(scanned):
    """AC-2. History doesn't follow renames, for any name: the old name keeps
    the 20 earlier commits and the new one has the rename."""
    by_file = {h["file"]: h for h in scanned["hotspots"]}
    assert by_file["src/módulo/b.ts"]["churn"]["commits"] == 1


def test_skipped_entries_are_counted_not_warned(scanned):
    """AC-4."""
    assert scanned["counts"]["files_not_citable"] == (4 if LINUX else 3)
    for w in scanned["warnings"]:
        assert not any(word in w.lower() for word in ("citable", "symbolic", "submodule"))


def test_glob_names_are_briefed_with_their_own_history(citable_repo, scanned):
    """AC-5: `[id]` is a name, not a character class matching `i` or `d`."""
    text = _bundle(citable_repo, "src/[id].ts")
    assert "feat: only i" not in text
    assert "src/i.ts b/" not in text and "+++ b/src/i.ts" not in text


def test_non_ascii_names_are_briefed_unquoted(citable_repo, scanned):
    """AC-2: diff headers and caller lines name the file as the bundle does."""
    text = _bundle(citable_repo, "src/módulo/b.ts")
    assert "diff --git a/src/módulo/b.ts" in text
    assert "\\303" not in text
    callers = text.partition("## Call sites elsewhere in the repo")[2].partition("\n## ")[0]
    assert callers.strip(), "the fixture's shared export should have callers"
    assert "src/módulo/b.ts" not in callers
