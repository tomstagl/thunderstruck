"""#19 AC-7: files nobody has touched in the window can still be the
integration point that takes production down. They are listed, never ranked,
and investigated only on request."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from build_fixture import isolated_git_env

ROOT = Path(__file__).resolve().parent.parent
LEGACY = "src/legacy_client.py"


def _commit(repo: Path, files: dict[str, str], msg: str, days_ago: int) -> None:
    for rel, body in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body)
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")
    env = isolated_git_env()
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com", GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg], check=True, env=env)


def _repo(tmp_path: Path, legacy: int = 1) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True,
                   env=isolated_git_env())
    old = {LEGACY: "import requests\n\ndef fetch(url):\n    return requests.get(url).json()\n"}
    for n in range(1, legacy):
        old[f"src/legacy_{n}.py"] = ("import requests\n\ndef get(u):\n"
                                     "    return requests.post(u, json={}).json()\n")
    _commit(repo, old, "feat: legacy client", days_ago=400)
    for n in range(5):
        _commit(repo, {"src/app.py": f"def main():\n    return {n}\n"}, f"feat: step {n}",
                days_ago=5 - n)
    return repo


def _signals(repo: Path, *extra: str) -> dict:
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "signals.py"), "--repo",
                           str(repo), "--since", "30d", *extra], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())


def test_an_untouched_integration_point_is_listed_not_ranked(tmp_path):
    data = _signals(_repo(tmp_path))
    assert LEGACY not in {h["file"] for h in data["hotspots"]}
    d = data["dormant"][0]
    assert (d["id"], d["file"]) == ("D01", LEGACY)
    assert "S01-py-requests-no-timeout" in {h["detector_id"] for h in d["detector_hits"]}
    assert d["churn"]["commits"] == 0 and d["churn"]["last_modified"]
    assert d["churn"]["recent_shas"], "the last change is named"


def test_dormant_zero_lists_nothing(tmp_path):
    assert _signals(_repo(tmp_path), "--dormant", "0")["dormant"] == []


def test_sweep_cap_is_visible(tmp_path):
    data = _signals(_repo(tmp_path, legacy=2), "--dormant-limit", "1")
    assert len(data["dormant"]) == 1
    assert any("1 unchanged file(s) were not swept" in w for w in data["warnings"]), data["warnings"]


def test_suppression_applies_to_the_dormant_sweep(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".thunderstruck.toml").write_text(
        '[[suppress]]\ndetector = "S01"\npath = "src/**"\nreason = "gateway sets timeouts"\n')
    assert _signals(repo)["dormant"] == []


def test_investigate_dormant_builds_a_deterministic_d_bundle(tmp_path):
    repo = _repo(tmp_path)
    _signals(repo)

    def build() -> bytes:
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "bundle.py"), "--repo",
                               str(repo), "--investigate-dormant", "1"],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return (repo / ".thunderstruck" / "bundles" / "D01.md").read_bytes()

    first = build()
    assert b"No commits in the window. Last change:" in first
    assert b"feat: legacy client" in first
    assert build() == first
    index = json.loads((repo / ".thunderstruck" / "bundles" / "index.json").read_text())
    assert [b["id"] for b in index["bundles"] if b["id"].startswith("D")] == ["D01"]


def test_without_the_flag_no_d_bundle_is_built(tmp_path):
    repo = _repo(tmp_path)
    _signals(repo)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "bundle.py"), "--repo", str(repo)],
                   check=True, capture_output=True)
    assert not (repo / ".thunderstruck" / "bundles" / "D01.md").exists()


def test_report_lists_dormant_integration_points(tmp_path):
    repo = _repo(tmp_path)
    _signals(repo)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "report.py"), "--repo", str(repo)],
                   check=True, capture_output=True)
    report = (repo / ".thunderstruck" / "report.md").read_text()
    section = report.split("## Dormant integration points", 1)[1]
    assert "D01" in section and LEGACY in section and "S01" in section


def test_sweep_is_fast(tmp_path):
    repo = tmp_path / "big"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True,
                   env=isolated_git_env())
    _commit(repo, {f"pkg/m{n}.py": "import requests\n\ndef f(u):\n    return requests.get(u)\n"
                   for n in range(500)}, "feat: many", days_ago=400)
    _commit(repo, {"src/app.py": "x = 1\n"}, "feat: app", days_ago=1)
    start = time.monotonic()
    data = _signals(repo)
    assert time.monotonic() - start < 10
    assert len(data["dormant"]) == 5
