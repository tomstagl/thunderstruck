"""#19 AC-17: `calibrate.py --summary` prints counts that are safe to paste
into a public issue. Nothing that identifies the repository may leak."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_dormant import _commit
from build_fixture import isolated_git_env

ROOT = Path(__file__).resolve().parent.parent


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "acme-private-monolith"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True,
                   env=isolated_git_env())
    _commit(repo, {"src/acme_secret_pricing/engine.py":
                   "import requests\n\ndef price():\n    return requests.get(ACME_INTERNAL_URL)\n",
                   "src/web/app.ts": "export const x = 1;\n"},
            "feat: acme pricing engine", days_ago=3)
    return repo


def _summary(repo: Path) -> tuple[str, dict]:
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "calibrate.py"), "--repo",
                           str(repo), "--lang", "all", "--patterns", "all", "--summary"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout + proc.stderr, json.loads(proc.stdout)


def test_summary_counts_hits_per_detector(tmp_path):
    _, doc = _summary(_repo(tmp_path))
    assert doc["schema"] == "thunderstruck.calibration-summary/v1"
    assert doc["detectors"]["S01-py-requests-no-timeout"]["hits"] == 1
    assert doc["detectors"]["S01-py-requests-no-timeout"]["files"] == 1
    assert doc["files_swept"]["python"] == 1 and doc["files_swept"]["typescript"] == 1
    assert doc["catalog_hash"].startswith("sha256:")


def test_summary_leaks_nothing_that_identifies_the_repository(tmp_path):
    repo = _repo(tmp_path)
    out, _ = _summary(repo)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                         text=True, check=True).stdout.strip()
    for secret in ("acme", "secret_pricing", "engine.py", "ACME_INTERNAL_URL", str(repo),
                   repo.name, sha, sha[:7], "src/"):
        assert secret.lower() not in out.lower(), secret


def test_detailed_mode_is_unchanged(tmp_path):
    repo = _repo(tmp_path)
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "calibrate.py"), "--repo",
                           str(repo), "--lang", "python", "--patterns", "S01"],
                          capture_output=True, text=True, check=True)
    assert "S01-py-requests-no-timeout\tsrc/acme_secret_pricing/engine.py:4" in proc.stdout
