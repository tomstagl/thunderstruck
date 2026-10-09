"""The scanned project's own package names (#58): an import of one never
opens a boundary rule's `require` gate, so a library calling its own code is
not a call through that library."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import _common


def _git_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, check=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    return root


def test_own_packages_come_from_tracked_files(tmp_path):
    repo = _git_repo(tmp_path / "repo", {
        "celery/__init__.py": "",
        "celery/app/__init__.py": "",
        "src/kit/__init__.py": "",
        "examples/requests/__init__.py": "",   # an example named like a library
        "docs/conf.py": "",
        "package.json": '{"name": "@acme/web"}',
        "packages/db/package.json": '{"name": "@acme/db", "private": true}',
        "broken/package.json": "{not json",
        "src/main/java/com/acme/A.java": (
            "/*\r\npackage com.wrong;\r\n */\r\n@Generated\r\npackage com.acme;\r\n\r\nclass A {}\r\n"),
        "src/main/java/com/acme/B.java": "/* licence */ package com.acme.b; // b\nclass B {}\n",
        "Default.java": "import java.util.List;\nclass Default {}\npackage com.never;\n",
        "deep/package.json": "[" * 200000,
    })
    (repo / "untracked").mkdir()
    (repo / "untracked" / "__init__.py").write_text("")
    # a tracked symlink is never followed, even to a well-formed package.json
    (tmp_path / "outside.json").write_text('{"name": "leaked"}')
    (repo / "link").mkdir()
    (repo / "link" / "package.json").symlink_to(tmp_path / "outside.json")
    subprocess.run(["git", "add", "link"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "link"], cwd=repo, check=True)
    own, warnings = _common.own_packages(repo, _common.tracked_index(repo))
    assert own == {"python": ["celery", "kit"], "typescript": ["@acme/db", "@acme/web"],
                   "java": ["com.acme", "com.acme.b"]}
    assert len(warnings) == 1 and "2 tracked file(s)" in warnings[0], warnings
    assert "broken/package.json" in warnings[0], warnings


def test_test_and_fixture_directories_are_not_own(tmp_path):
    # A fixture's copy of axios must not hide axios calls in src/, and a test
    # helper declared in Spring's package must not hide RestTemplate calls.
    repo = _git_repo(tmp_path / "repo", {
        "package.json": '{"name": "web"}',
        "test/fixtures/node_modules/axios/package.json": '{"name": "axios"}',
        "examples/basic/package.json": '{"name": "got"}',
        "src/main/java/com/acme/Client.java": "package com.acme;\nclass Client {}\n",
        "src/test/java/org/springframework/web/client/Helper.java": (
            "package org.springframework.web.client;\nclass Helper {}\n"),
    })
    own, warnings = _common.own_packages(repo, _common.tracked_index(repo))
    assert own == {"python": [], "typescript": ["web"], "java": ["com.acme"]}, own
    assert warnings == []


def test_a_repository_with_no_packages_owns_none(tmp_path):
    repo = _git_repo(tmp_path / "repo", {"app.py": "print(1)\n"})
    assert _common.own_packages(repo, _common.tracked_index(repo)) == (
        {"python": [], "typescript": [], "java": []}, [])


def test_hotspots_record_own_packages(scanned_repo):
    data = json.loads((scanned_repo / ".thunderstruck" / "hotspots.json").read_text())
    assert data["own_packages"] == {"python": [], "typescript": ["fixture"], "java": []}
