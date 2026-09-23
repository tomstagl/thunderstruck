"""Shared pytest fixtures."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))


@pytest.fixture(scope="session")
def plugin_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def catalog(plugin_root: Path) -> dict:
    import _common
    return _common.load_catalog(plugin_root)


@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory) -> Path:
    """A synthetic repository with the planted fractures from the spec."""
    from build_fixture import build
    return build(tmp_path_factory.mktemp("repo") / "fixture")


@pytest.fixture(scope="session")
def scanned_repo(fixture_repo: Path, plugin_root: Path) -> Path:
    """The fixture repo with the deterministic pipeline already run over it."""
    for args in (
        [sys.executable, str(plugin_root / "scripts" / "signals.py"),
         "--repo", str(fixture_repo), "--top", "8", "--since", "24m"],
        [sys.executable, str(plugin_root / "scripts" / "bundle.py"),
         "--repo", str(fixture_repo)],
    ):
        proc = subprocess.run(args, capture_output=True, text=True, cwd=str(fixture_repo))
        assert proc.returncode == 0, f"{args[1:]} failed:\n{proc.stdout}\n{proc.stderr}"
    return fixture_repo


FAKE_CATALOG = ROOT / "tests" / "fixtures" / "fake_catalog.py"


@pytest.fixture(scope="session")
def context_repo_template(tmp_path_factory) -> Path:
    """The fixture repo with catalog-info.yaml and a [context] table pointing
    at the stub catalog CLI. Copy it before changing anything."""
    from build_fixture import add_service_context, build
    repo = build(tmp_path_factory.mktemp("ctx") / "fixture")
    add_service_context(repo, python=sys.executable, stub=FAKE_CATALOG)
    return repo


@pytest.fixture
def context_repo(context_repo_template: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "fixture"
    shutil.copytree(context_repo_template, dest, symlinks=True)
    return dest


@pytest.fixture(scope="session")
def context_env(tmp_path_factory) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_CATALOG_")}
    return {**env, "THUNDERSTRUCK_TRUST_CONTEXT": "1",
            "XDG_CONFIG_HOME": str(tmp_path_factory.mktemp("xdg"))}


@pytest.fixture(scope="session")
def run_steps():
    def _run(repo: Path, env: dict | None, *steps: list[str]) -> None:
        for step in steps:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / step[0]), "--repo", str(repo),
                 *step[1:]], capture_output=True, text=True, cwd=str(repo), env=env)
            assert proc.returncode == 0, f"{step} failed:\n{proc.stdout}\n{proc.stderr}"
    return _run


@pytest.fixture(scope="session")
def context_scanned_repo(context_repo_template, context_env, run_steps,
                         tmp_path_factory) -> Path:
    repo = tmp_path_factory.mktemp("ctxscan") / "fixture"
    shutil.copytree(context_repo_template, repo, symlinks=True)
    run_steps(repo, context_env, ["signals.py", "--top", "8", "--since", "24m"],
              ["context.py"], ["bundle.py"])
    return repo


@pytest.fixture
def context_scanned_copy(context_scanned_repo: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "scanned"
    shutil.copytree(context_scanned_repo, dest, symlinks=True)
    return dest


@pytest.fixture
def scanned_copy(scanned_repo: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "scanned-plain"
    shutil.copytree(scanned_repo, dest, symlinks=True)
    return dest
