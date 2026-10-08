"""#37: dependency source at declared or locked versions (spec §4)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import zipfile
from pathlib import Path

import pytest

import deps


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".thunderstruck").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _index(*packages: dict) -> dict:
    return {"schema": deps.DEPS_SCHEMA, "packages": list(packages), "warnings": []}


def _pkg(**over) -> dict:
    p = {"id": "pypi:kombu", "ecosystem": "pypi", "name": "kombu", "declared": ">=5.6",
         "declared_in": ["requirements/default.txt"], "version": "5.7.0a1", "basis": "declared_range",
         "status": "available", "reason": None, "source": None, "snapshot": None}
    p.update(over)
    return p


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """deps.py opens no socket (spec §15)."""
    def refuse(*a, **k):
        raise AssertionError("deps.py must not open a socket")
    monkeypatch.setattr(socket, "socket", refuse)


def test_deps_imports_only_stdlib_and_common_at_module_level():
    """validate.py imports deps on every scan, --no-verify included: packaging
    and yaml are imported inside the discoverers that use them, never at the top."""
    import ast
    import sys as _sys
    tree = ast.parse(Path(deps.__file__).read_text())
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.add(node.module.split(".")[0])
    assert top <= set(_sys.stdlib_module_names) | {"_common", "__future__"}, top


def test_deps_runs_no_process():
    """deps.py runs no package manager or anything else: it never imports a process or network module."""
    import ast
    tree = ast.parse(Path(deps.__file__).read_text())
    names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
             for a in n.names} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not names & {"subprocess", "socket", "urllib", "urllib.request", "http", "http.client"}


# --- Task 2 -----------------------------------------------------------------
def _snapshotted(tmp_path: Path) -> tuple[Path, dict]:
    repo = _repo(tmp_path)
    src = tmp_path / "site" / "kombu"
    (src / "utils").mkdir(parents=True)
    (src / "utils" / "functional.py").write_text("".join(f"line {i}\n" for i in range(1, 401)))
    files = [("kombu/utils/functional.py", src / "utils" / "functional.py")]
    dest = deps.snapshot_dir(repo, "pypi", "kombu", "5.7.0a1")
    assert deps.copy_tree(files, dest, deps.LIMITS) is None
    index = _index(_pkg(snapshot=deps.snapshot_rel("pypi", "kombu", "5.7.0a1")))
    return repo, index


def test_a_dependency_ref_resolves(tmp_path):
    repo, index = _snapshotted(tmp_path)
    got, err = deps.resolve_dependency_ref(repo, index, "pypi:kombu@5.7.0a1:kombu/utils/functional.py:318-332")
    assert err is None
    assert got == {"id": "pypi:kombu", "version": "5.7.0a1", "path": "kombu/utils/functional.py",
                   "start": 318, "end": 332}


@pytest.mark.parametrize("ref, needle", [
    ("pypi:kombu@5.6.0:kombu/utils/functional.py:1", "read at 5.7.0a1, not 5.6.0"),
    ("pypi:redis@8.1.0:redis/client.py:1", "not an available dependency"),
    ("pypi:kombu@5.7.0a1:kombu/../../etc/passwd:1", "'..'"),
    ("pypi:kombu@5.7.0a1:/etc/passwd:1", "absolute"),
    ("pypi:kombu@5.7.0a1:kombu/utils/functional.py:399-401", "has 400 lines"),
    ("pypi:kombu@5.7.0a1:kombu/utils:1", "no such file"),
    ("pypi:kombu@5.7.0a1:kombu/utils/functional.py", "is not ecosystem:name@version:path:line"),
    ("cargo:serde@1.0.0:src/lib.rs:1", "is not ecosystem:name@version:path:line"),
])
def test_a_dependency_ref_that_does_not_resolve_says_why(tmp_path, ref, needle):
    repo, index = _snapshotted(tmp_path)
    got, err = deps.resolve_dependency_ref(repo, index, ref)
    assert got is None and needle in err


def test_no_index_means_no_dependency_ref_resolves(tmp_path):
    repo, _ = _snapshotted(tmp_path)
    got, err = deps.resolve_dependency_ref(repo, None, "pypi:kombu@5.7.0a1:kombu/utils/functional.py:1")
    assert got is None and "no dependency source was read in this scan" in err


def test_scoped_npm_and_maven_names_parse():
    m = deps.DEP_REF.match("npm:@aws-sdk/client-s3@3.500.0:dist-cjs/index.js:10")
    assert (m["eco"], m["name"], m["version"], m["path"]) == ("npm", "@aws-sdk/client-s3", "3.500.0", "dist-cjs/index.js")
    m = deps.DEP_REF.match("maven:org.apache.httpcomponents/httpclient@4.5.14:org/apache/A.java:1-2")
    assert m["name"] == "org.apache.httpcomponents/httpclient" and m["end"] == "2"


def test_copy_tree_refuses_symlinks_and_escapes(tmp_path):
    target = tmp_path / "secret"
    target.write_text("x")
    link = tmp_path / "link.py"
    link.symlink_to(target)
    assert "symlink" in deps.copy_tree([("pkg/link.py", link)], tmp_path / "d1", deps.LIMITS)
    ok = tmp_path / "ok.py"
    ok.write_text("x")
    assert "'..'" in deps.copy_tree([("../ok.py", ok)], tmp_path / "d2", deps.LIMITS)
    assert not (tmp_path / "d1").exists() and not (tmp_path / "d2").exists()


def test_copy_tree_refuses_a_package_over_its_limit(tmp_path):
    f = tmp_path / "big.py"
    f.write_text("x" * 2000)
    limits = deps.Limits(per_package_bytes=1000, per_package_files=10, total_bytes=10_000)
    assert "too large to snapshot" in deps.copy_tree([("big.py", f)], tmp_path / "d", limits)
    assert not (tmp_path / "d").exists()  # never truncated


def test_copy_jar_extracts_sources_and_refuses_traversal(tmp_path):
    jar = tmp_path / "a-1.0-sources.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("org/a/A.java", "class A {}\n")
        z.writestr("META-INF/MANIFEST.MF", "x")
    assert deps.copy_jar(jar, tmp_path / "out", (".java", ".kt"), deps.LIMITS) is None
    assert (tmp_path / "out" / "org" / "a" / "A.java").is_file()
    assert not (tmp_path / "out" / "META-INF").exists()
    bad = tmp_path / "bad.jar"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../evil.java", "x")
    assert "'..'" in deps.copy_jar(bad, tmp_path / "out2", (".java",), deps.LIMITS)


def test_snapshot_marks_unavailable_and_reuses(tmp_path):
    repo = _repo(tmp_path)
    src = tmp_path / "site"
    (src / "kombu").mkdir(parents=True)
    (src / "kombu" / "__init__.py").write_text("x = 1\n")
    index = _index(_pkg(source=str(src), files=["kombu/__init__.py"]))
    out = deps.snapshot(repo, index)
    p = out["packages"][0]
    assert p["status"] == "available" and p["snapshot"] == ".thunderstruck/deps/pypi/kombu@5.7.0a1"
    marker = json.loads((repo / p["snapshot"] / ".snapshot.json").read_text())
    assert marker == {"id": "pypi:kombu", "version": "5.7.0a1", "files": 1}
    (src / "kombu" / "__init__.py").unlink()  # the source is gone, the snapshot is reused
    assert deps.snapshot(repo, _index(_pkg(source=str(src), files=["kombu/__init__.py"])))["packages"][0]["status"] == "available"


def test_unsafe_names_never_become_directories(tmp_path):
    repo = _repo(tmp_path)
    out = deps.snapshot(repo, _index(_pkg(id="pypi:../x", name="../x", source=str(tmp_path), files=[])))
    assert out["packages"][0]["status"] == "unavailable"
    assert "unsafe" in out["packages"][0]["reason"]
    assert not (repo / ".thunderstruck" / "x").exists()
