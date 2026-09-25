"""#19 AC-14: YAML and .properties are scanned, with their own comment rules,
and a config file ranks only when it carries a lead."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import _common as c
from test_dormant import _commit
from build_fixture import isolated_git_env

ROOT = Path(__file__).resolve().parent.parent


def test_config_extensions_are_languages():
    langmap = c.language_map(c.load_catalog())
    assert c.detect_language("k8s/deploy.yaml", langmap) == "yaml"
    assert c.detect_language("k8s/deploy.yml", langmap) == "yaml"
    assert c.detect_language("src/main/resources/application.properties", langmap) == "properties"


def test_yaml_comments_are_blanked_but_quoted_hashes_kept():
    out = c.strip_comments('a: "x # y"  # comment\n# whole line\nb: c#d\n', "yaml")
    lines = out.split("\n")
    assert lines[0].rstrip() == 'a: "x # y"'
    assert lines[1].strip() == ""
    assert lines[2] == "b: c#d", "a # inside a plain scalar is not a comment"
    assert len(out) == len('a: "x # y"  # comment\n# whole line\nb: c#d\n')


def test_properties_comments_are_blanked():
    src = "! bang comment\n# hash comment\n  # indented\nurl=http://x#frag\n"
    lines = c.strip_comments(src, "properties").split("\n")
    assert [ln.strip() for ln in lines[:3]] == ["", "", ""]
    assert lines[3] == "url=http://x#frag"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True,
                   env=isolated_git_env())
    for n in range(10):
        _commit(repo, {"deploy/values.yaml": f"replicas: {n}\nimage: app:{n}\n",
                       "src/app.py": f"def f(x):\n    if x:\n        return {n}\n    return 0\n"},
                f"chore: release {n}", days_ago=10 - n)
    return repo


def test_config_without_a_lead_never_ranks(tmp_path):
    repo = _repo(tmp_path)
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "signals.py"), "--repo",
                           str(repo), "--since", "30d"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    data = json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())
    ranked = {h["file"] for h in data["hotspots"]}
    assert "src/app.py" in ranked
    assert "deploy/values.yaml" not in ranked
    assert not any("values.yaml" in w or "lizard" in w for w in data["warnings"]), data["warnings"]
    assert data["coverage_gaps"]["considered"] == 2, "config is considered, only not ranked"
