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
    ("src//a.ts", "canonical form"),
    ("src/./a.ts", "canonical form"),
    ("src/a.ts/", "canonical form"),
    ("src", "is a directory"),
    ("src/A.ts", "did you mean 'src/a.ts'"),
])
def test_paths_outside_the_tracked_tree_are_rejected(repo, path, fragment):
    for doc in (_doc(path, code_ref="src/a.ts:1"), _doc("src/a.ts", code_ref=f"{path}:1")):
        errors = _validator(repo).check_document(doc)
        fragments = fragment if isinstance(fragment, tuple) else (fragment,)
        assert errors and any(f in e for e in errors for f in fragments), errors


def test_rejected_paths_are_never_opened(repo, tmp_path, monkeypatch):
    import builtins
    import io
    import os
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n")
    opened: list[str] = []

    def spying(real, first_is_self=False):
        def spy(target, *args, **kwargs):
            opened.append(str(target))
            return real(target, *args, **kwargs)
        return spy
    real_path_open = Path.open

    def path_spy(self, *args, **kwargs):
        opened.append(str(self))
        return real_path_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, "open", path_spy)
    monkeypatch.setattr(builtins, "open", spying(builtins.open))
    monkeypatch.setattr(io, "open", spying(io.open))
    monkeypatch.setattr(os, "open", spying(os.open))
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
    assert any("passes through a symbolic link" in e for e in errors), errors


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


@pytest.mark.parametrize("ref", ["src/a.ts:١٦", "src/a.ts:L16", "src/a.ts:16–18"])
def test_code_refs_accept_only_ascii_line_numbers(repo, ref):
    errors = _validator(repo).check_document(_doc("src/a.ts", code_ref=ref))
    assert errors and "does not exist" in errors[0] and "20 lines" in errors[0], errors


@pytest.mark.parametrize("lines", ["16\n", "١٦"])
def test_location_ranges_accept_only_ascii_line_numbers(repo, lines):
    assert _validator(repo).check_document(_doc("src/a.ts", lines))


def test_a_tracked_file_replaced_by_a_link_to_an_ignored_file_is_rejected(repo):
    (repo / ".env").write_text("SECRET=1\n")
    with (repo / ".gitignore").open("a") as fh:
        fh.write(".env\n")
    (repo / "src" / "a.ts").unlink()
    (repo / "src" / "a.ts").symlink_to("../.env")
    errors = _validator(repo).check_document(_doc("src/a.ts"))
    assert any("passes through a symbolic link" in e for e in errors), errors


def test_a_tracked_path_replaced_by_a_fifo_does_not_block(repo):
    import os
    import signal
    (repo / "src" / "a.ts").unlink()
    os.mkfifo(repo / "src" / "a.ts")
    signal.signal(signal.SIGALRM, lambda *_: pytest.fail("validation blocked on a FIFO"))
    signal.alarm(5)
    try:
        errors = _validator(repo).check_document(_doc("src/a.ts"))
    finally:
        signal.alarm(0)
    assert any("not a regular file" in e for e in errors), errors


def test_a_file_deleted_locally_says_so(repo):
    (repo / "src" / "a.ts").unlink()
    errors = _validator(repo).check_document(_doc("src/a.ts"))
    assert any("missing from the working tree" in e for e in errors), errors


def test_a_file_outside_a_sparse_checkout_says_so(repo):
    _git(repo, "update-index", "--skip-worktree", "src/a.ts")
    (repo / "src" / "a.ts").unlink()
    errors = _validator(repo).check_document(_doc("src/a.ts"))
    assert any("sparse checkout" in e for e in errors), errors


def test_commit_evidence_matches_bracketed_paths_literally(repo):
    (repo / "src" / "i.ts").write_text("x\n")
    (repo / "src" / "[id].ts").write_text("y\n")
    _git(repo, "add", "src/[id].ts")
    _git(repo, "commit", "-qm", "route")
    _git(repo, "add", "src/i.ts")
    _git(repo, "commit", "-qm", "only i.ts")
    only_i = _git(repo, "rev-parse", "HEAD").strip()
    doc = _doc("src/[id].ts")
    doc["findings"][0]["evidence"].append({"type": "commit", "ref": only_i, "note": "n"})
    errors = _validator(repo).check_document(doc)
    assert any("does not touch" in e for e in errors), errors


# --------------------------------------------------------------- identity --


def _validate_file(repo: Path, doc: dict, plugin_root: Path) -> dict:
    """Run validate.py for real, so the write-back is exercised end to end."""
    import json
    import sys
    out = repo / ".thunderstruck"
    (out / "findings").mkdir(parents=True, exist_ok=True)
    (out / "hotspots.json").write_text(json.dumps({"hotspots": []}))
    path = out / "findings" / "H01.json"
    path.write_text(json.dumps(doc))
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / "validate.py"),
                           "--repo", str(repo)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(path.read_text())


def test_dot_slash_paths_are_written_back_canonical(repo, plugin_root):
    from validate import stable_key
    saved = _validate_file(repo, _doc("./src/a.ts", "3-4", code_ref="././src/a.ts:3"), plugin_root)
    f = saved["findings"][0]
    assert f["location"]["file"] == "src/a.ts"
    assert f["evidence"][0]["ref"] == "src/a.ts:3"
    assert f["key"] == stable_key("src/a.ts", "fails")


def test_a_dot_slash_and_a_plain_spelling_share_one_index_entry(scanned_copy, plugin_root):
    import copy
    import json
    import sys
    from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    first = doc["findings"][0]
    file = first["location"]["file"]
    second = copy.deepcopy(first)
    second["failure_mode"] = "fails differently"
    first["location"]["file"] = "./" + file
    doc["findings"].append(second)
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                           "--repo", str(scanned_copy)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    index = json.loads((scanned_copy / ".thunderstruck" / "index.json").read_text())
    assert list(index["files"]) == [file]
    assert len(index["files"][file]["findings"]) == 2


def test_a_plain_path_keeps_its_key(repo, plugin_root):
    from validate import stable_key
    saved = _validate_file(repo, _doc("src/a.ts"), plugin_root)
    assert saved["findings"][0]["key"] == stable_key("src/a.ts", "fails")


def test_a_dotfile_under_a_dot_directory_validates_end_to_end(repo, plugin_root):
    saved = _validate_file(repo, _doc(".github/scripts/deploy.py", "2-3"), plugin_root)
    assert saved["findings"][0]["location"]["file"] == ".github/scripts/deploy.py"


# ------------------------------------------------ findings from older rules --


def _bundle(repo: Path, plugin_root: Path) -> tuple[dict, str]:
    import json
    import sys
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / "bundle.py"),
                           "--repo", str(repo)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    index = json.loads((repo / ".thunderstruck" / "bundles" / "index.json").read_text())
    return {b["id"]: b for b in index["bundles"]}, proc.stdout


def _saved(repo: Path, hid: str, doc: dict, bundle_hash: str) -> Path:
    import json
    doc = {**doc, "bundle_hash": bundle_hash}
    path = repo / ".thunderstruck" / "findings" / f"{hid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    return path


def _old_validated(doc: dict) -> dict:
    """What 0.4.0's validator left behind: keys, no rules stamp."""
    import copy
    doc = copy.deepcopy(doc)
    for f in doc["findings"]:
        f["key"] = "0123456789ab"
    return doc


def test_findings_from_older_rules_that_still_pass_are_reused(scanned_copy, plugin_root):
    from test_pipeline import _hotspots, _valid_finding
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    bundles, _ = _bundle(scanned_copy, plugin_root)
    _saved(scanned_copy, hid, _old_validated(doc), bundles[hid]["bundle_hash"])
    bundles, out = _bundle(scanned_copy, plugin_root)
    assert bundles[hid]["cached"] is True
    assert "investigated again" not in out


def test_findings_from_older_rules_that_now_fail_are_reinvestigated(scanned_copy, plugin_root):
    from test_pipeline import _hotspots, _valid_finding
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    doc["findings"][0]["location"]["lines"] = "L1"      # passed 0.4.0, fails now
    bundles, _ = _bundle(scanned_copy, plugin_root)
    _saved(scanned_copy, hid, _old_validated(doc), bundles[hid]["bundle_hash"])
    bundles, out = _bundle(scanned_copy, plugin_root)
    assert bundles[hid]["cached"] is False
    assert "1 bundle(s) had findings that fail today's validation rules" in out
    assert out.strip().splitlines()[-1].endswith("reused from cache"), "the skill reads the last line"


def test_clean_and_failed_files_are_reused_as_before(scanned_copy, plugin_root):
    from test_pipeline import _hotspots
    hs = _hotspots(scanned_copy)["hotspots"]
    bundles, _ = _bundle(scanned_copy, plugin_root)
    _saved(scanned_copy, hs[0]["id"], {"hotspot_id": hs[0]["id"], "findings": [], "notes": "clean"},
           bundles[hs[0]["id"]]["bundle_hash"])
    _saved(scanned_copy, hs[1]["id"], {"hotspot_id": hs[1]["id"], "findings": [],
                                       "analysis_failed": True}, bundles[hs[1]["id"]]["bundle_hash"])
    bundles, _ = _bundle(scanned_copy, plugin_root)
    assert bundles[hs[0]["id"]]["cached"] and bundles[hs[1]["id"]]["cached"]


def test_validated_findings_are_stamped_and_reused(scanned_copy, plugin_root):
    import json
    from test_pipeline import _hotspots, _valid_finding, _validate
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    bundles, _ = _bundle(scanned_copy, plugin_root)
    path = _saved(scanned_copy, hid, doc, bundles[hid]["bundle_hash"])
    assert _validate(scanned_copy, plugin_root).returncode == 0
    assert json.loads(path.read_text())["validated_with"] == c.VALIDATION_RULES
    bundles, _ = _bundle(scanned_copy, plugin_root)
    assert bundles[hid]["cached"] is True


def test_report_never_shows_findings_the_current_rules_did_not_pass(scanned_copy, plugin_root):
    import json
    import sys
    from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    _write_finding(scanned_copy, hid, doc)                # re-saved, not re-validated
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(scanned_copy)], check=True, capture_output=True)
    payload = json.loads((scanned_copy / ".thunderstruck" / "report.json").read_text())
    assert payload["findings"] == []
    reasons = {e["hotspot_id"]: e["reason"] for e in payload["incomplete"]}
    assert "not validated by this version's rules" in reasons[hid]


def test_save_finding_strips_validator_owned_fields(scanned_copy, plugin_root):
    import json
    import sys
    from test_pipeline import _hotspots, _valid_finding
    _bundle(scanned_copy, plugin_root)
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    doc["validated_with"] = c.VALIDATION_RULES
    doc["findings"][0].update(key="forged", content_hash="x", catalog_evidence=[])
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / "save_finding.py"),
                           "--repo", str(scanned_copy), "--id", hid],
                          input=json.dumps(doc), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert "validated_with" not in saved
    assert not {"key", "content_hash", "catalog_evidence"} & set(saved["findings"][0])
