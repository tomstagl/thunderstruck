"""#101: dependency source for packages a declared package pulls in (spec §2)."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

import deps


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".thunderstruck").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """deps.py opens no socket (#37 spec §15)."""
    def refuse(*a, **k):
        raise AssertionError("deps.py must not open a socket")
    monkeypatch.setattr(socket, "socket", refuse)


# --- Task 1 -----------------------------------------------------------------
def test_extras_are_the_union_over_every_declaration(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("kombu[sqlalchemy,redis]>=5\n")
    (repo / "pyproject.toml").write_text('[project]\nname="x"\ndependencies=[]\n'
                                         '[project.optional-dependencies]\nmongo=["kombu[mongodb]"]\n')
    assert deps.pypi_declared_extras(repo) == {"kombu": ["mongodb", "redis", "sqlalchemy"]}
    # the existing contract is unchanged
    assert deps.pypi_declared(repo)["kombu"] == (">=5", ["pyproject.toml", "requirements.txt"])


def test_a_declaration_without_extras_has_an_empty_list(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("kombu>=5\n")
    assert deps.pypi_declared_extras(repo) == {"kombu": []}
