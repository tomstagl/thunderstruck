"""Shared pytest fixtures."""

from __future__ import annotations

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
