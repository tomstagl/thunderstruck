"""#25: a cited path is one canonical, tracked file inside the repository, and
every line range lies inside it. The Validator is exercised directly against
small git repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import _common as c
from build_fixture import isolated_git_env
from validate import Validator


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                           *args], check=True, capture_output=True, text=True,
                          env=isolated_git_env()).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "src").mkdir()
    (root / "src" / "a.ts").write_text("".join(f"line {n}\n" for n in range(1, 21)))
    (root / ".github" / "scripts").mkdir(parents=True)
    (root / ".github" / "scripts" / "deploy.py").write_text("x = 1\n" * 10)
    (root / "lnk.ts").symlink_to("src/a.ts")
    (root / "lnkdir").symlink_to("src")
    (root / ".gitignore").write_text("gen/\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "init")
    (root / "gen").mkdir()
    (root / "gen" / "out.ts").write_text("x\n")
    (root / "src" / "new.ts").write_text("x\n")
    return root


def _validator(repo: Path) -> Validator:
    return Validator(repo, {"hotspots": []}, c.load_catalog())


def _doc(file: str, lines=None, code_ref: str | None = None) -> dict:
    loc = {"file": file, "symbol": "f"}
    if lines is not None:
        loc["lines"] = lines
    return {"hotspot_id": "H01", "findings": [{
        "location": loc, "missing_patterns": ["S02"], "failure_mode": "fails",
        "trigger_condition": "t", "amplifier": "a", "sustaining_effect": None,
        "blast_radius": "b", "confidence": "medium", "confidence_rationale": "r",
        "how_to_verify": "v",
        "evidence": [{"type": "code", "ref": code_ref or f"{file}:1", "note": "n"}]}]}


# ------------------------------------------------------------------ paths --


@pytest.mark.parametrize("path", ["src/a.ts", "./src/a.ts", "././src/a.ts",
                                  ".github/scripts/deploy.py", "./.github/scripts/deploy.py"])
def test_tracked_files_are_accepted(repo, path):
    assert _validator(repo).check_document(_doc(path)) == []


@pytest.mark.parametrize("path, fragment", [
    ("/etc/hostname", "is absolute"),
    ("C:/x.ts", ("is absolute", "is not path:line")),   # as a code ref, the colon breaks the format
    ("../outside.txt", "'..'"),
    ("src/../../outside.txt", "'..'"),
    ("src\\a.ts", "backslash"),
    ("src/new.ts", "not tracked by git"),
    ("gen/out.ts", "not tracked by git"),
    ("src/missing.ts", "no such file"),
    ("lnk.ts", "symbolic link"),
    ("lnkdir/a.ts", "not tracked by git"),  # under a symlinked dir: never in the index
    ("github/scripts/deploy.py", "no such file"),
])
def test_paths_outside_the_tracked_tree_are_rejected(repo, path, fragment):
    for doc in (_doc(path, code_ref="src/a.ts:1"), _doc("src/a.ts", code_ref=f"{path}:1")):
        errors = _validator(repo).check_document(doc)
        fragments = fragment if isinstance(fragment, tuple) else (fragment,)
        assert errors and any(f in e for e in errors for f in fragments), errors


def test_rejected_paths_are_never_opened(repo, tmp_path, monkeypatch):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n")
    opened: list[str] = []
    real_open = Path.open

    def spy(self, *args, **kwargs):
        opened.append(str(self))
        return real_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, "open", spy)
    for path in ("src/../../outside.txt", str(outside), "../outside.txt", "gen/out.ts"):
        _validator(repo).check_document(_doc(path, code_ref=f"{path}:1"))
    assert not [p for p in opened if "outside" in p or "gen" in p], opened


def test_tracked_dir_replaced_by_a_symlink_to_outside(repo, tmp_path):
    (repo / "lib").mkdir()
    (repo / "lib" / "b.ts").write_text("x\n")
    _git(repo, "add", "lib")
    _git(repo, "commit", "-qm", "lib")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "b.ts").write_text("x\n")
    (repo / "lib" / "b.ts").unlink()
    (repo / "lib").rmdir()
    (repo / "lib").symlink_to(elsewhere)
    errors = _validator(repo).check_document(_doc("lib/b.ts"))
    assert any("resolves outside the repository" in e for e in errors), errors


def test_submodule_paths_are_rejected(repo, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    _git(sub, "init", "-q", "-b", "main")
    (sub / "f.c").write_text("int x;\n")
    _git(sub, "add", ".")
    _git(sub, "commit", "-qm", "sub")
    _git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "vendor")
    assert _validator(repo).check_document(_doc("vendor/f.c"))
    errors = _validator(repo).check_document(_doc("vendor"))
    assert any("submodule" in e for e in errors), errors


def test_uncommitted_edits_validate_against_the_working_tree(repo):
    with (repo / "src" / "a.ts").open("a") as fh:
        fh.write("".join(f"more {n}\n" for n in range(10)))
    assert _validator(repo).check_document(_doc("src/a.ts", code_ref="src/a.ts:30")) == []


# ------------------------------------------------------------ line ranges --


@pytest.mark.parametrize("lines", [16, "16", "16-20", "1-20", "20", None])
def test_readable_location_ranges_are_accepted(repo, lines):
    assert _validator(repo).check_document(_doc("src/a.ts", lines)) == []


def test_a_location_without_lines_is_a_whole_file_finding(repo):
    assert _validator(repo).check_document(_doc("src/a.ts")) == []


@pytest.mark.parametrize("lines", ["L16", "16–18", "18-16", "16-21", "21", 0, "0", True,
                                   " 16", "16 - 18", [16], "16,18", ""])
def test_unreadable_location_ranges_are_rejected(repo, lines):
    errors = _validator(repo).check_document(_doc("src/a.ts", lines))
    assert len(errors) == 1 and "location.lines" in errors[0], errors
    assert '"42-118"' in errors[0] and "20 lines" in errors[0]


@pytest.mark.parametrize("ref, ok", [
    ("src/a.ts:16", True), ("src/a.ts:16-20", True), ("src/a.ts:16-16", True),
    ("src/a.ts:18-16", False), ("src/a.ts:0", False), ("src/a.ts:20-21", False)])
def test_code_ref_ranges_must_ascend_inside_the_file(repo, ref, ok):
    errors = _validator(repo).check_document(_doc("src/a.ts", code_ref=ref))
    assert (errors == []) is ok, errors
    if not ok:
        assert "start ≤ end" in errors[0] and "20 lines" in errors[0]
