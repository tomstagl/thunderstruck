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


# --- Task 2 -----------------------------------------------------------------
def _venv(repo: Path) -> Path:
    site = repo / ".venv" / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True)
    return site


def _install(site: Path, name: str, version: str, requires: list[str] = (), *,
             files: dict[str, str] | None = None, editable: bool = False, record: bool = True) -> None:
    dist = site / f"{name.replace('-', '_')}-{version}.dist-info"
    dist.mkdir(parents=True)
    head = [f"Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    head += [f"Requires-Dist: {r}" for r in requires]
    (dist / "METADATA").write_text("\n".join(head) + "\n\nA description.\nRequires-Dist: not-a-header\n")
    files = {f"{name.lower().replace('-', '_')}/__init__.py": "x\n"} if files is None else files
    lines = []
    for rel, body in files.items():
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_text(body)
        lines.append(f"{rel},,")
    lines.append(f"{dist.name}/METADATA,,")
    if record:
        (dist / "RECORD").write_text("\n".join(lines) + "\n")
    if editable:
        (dist / "direct_url.json").write_text('{"url": "file:///x", "dir_info": {"editable": true}}')


def _kombu_env(repo: Path) -> Path:
    site = _venv(repo)
    _install(site, "kombu", "5.4.0", ["amqp<6,>=5.1.1", 'SQLAlchemy>=1.4; extra == "sqlalchemy"'])
    _install(site, "amqp", "5.3.1", ["vine<6,>=5.0.0"])
    _install(site, "vine", "5.1.0")
    _install(site, "SQLAlchemy", "2.0.36", ["greenlet!=0.4.17"])
    _install(site, "greenlet", "3.1.1")
    return site


def _reached(repo: Path) -> dict[str, dict]:
    pkgs, _ = deps.discover_pypi(repo, {})
    return {p["name"]: p for p in pkgs if p.get("reached_via")}


def test_a_declared_package_reaches_its_hard_requirements_and_not_an_unrequested_extra(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("kombu>=5\n")
    _kombu_env(repo)
    reached = _reached(repo)
    assert sorted(reached) == ["amqp", "vine"]
    amqp = reached["amqp"]
    assert {k: amqp[k] for k in ("id", "ecosystem", "declared", "declared_in", "reached_via", "version",
                                 "basis", "status", "reason")} == {
        "id": "pypi:amqp", "ecosystem": "pypi", "declared": None, "declared_in": [],
        "reached_via": ["kombu"], "version": "5.3.1", "basis": "installed", "status": "available",
        "reason": None}
    assert amqp["files"] == ["amqp/__init__.py"]
    assert reached["vine"]["reached_via"] == ["amqp"]


def test_a_requested_extra_is_followed(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("kombu[sqlalchemy]>=5\n")
    _kombu_env(repo)
    reached = _reached(repo)
    assert sorted(reached) == ["amqp", "greenlet", "sqlalchemy", "vine"]
    assert reached["sqlalchemy"]["reached_via"] == ["kombu"]


def test_reached_packages_are_snapshotted(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("kombu>=5\n")
    _kombu_env(repo)
    index = deps.snapshot(repo, deps.discover(repo, {}, tmp_path / "home"))
    amqp = next(p for p in index["packages"] if p["id"] == "pypi:amqp")
    assert amqp["snapshot"] == ".thunderstruck/deps/pypi/amqp@5.3.1"
    assert (repo / amqp["snapshot"] / "amqp" / "__init__.py").is_file()


def test_depth_is_capped_at_two_hops(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("a\n")
    site = _venv(repo)
    _install(site, "a", "1.0", ["b"])
    _install(site, "b", "1.0", ["c"])
    _install(site, "c", "1.0", ["d"])
    _install(site, "d", "1.0")
    assert sorted(_reached(repo)) == ["b", "c"]


def test_a_cycle_and_a_declared_package_are_never_added_twice(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("a\nc\n")
    site = _venv(repo)
    _install(site, "a", "1.0", ["b"])
    _install(site, "b", "1.0", ["a", "c"])
    _install(site, "c", "1.0", ["b"])
    pkgs, _ = deps.discover_pypi(repo, {})
    assert [p["id"] for p in pkgs].count("pypi:b") == 1
    b = next(p for p in pkgs if p["id"] == "pypi:b")
    assert b["reached_via"] == ["a", "c"]
    assert next(p for p in pkgs if p["id"] == "pypi:a")["declared"] == ""


def test_reached_via_lists_at_most_three_parents(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("p1\np2\np3\np4\n")
    site = _venv(repo)
    for n in ("p1", "p2", "p3", "p4"):
        _install(site, n, "1.0", ["shared"])
    _install(site, "shared", "1.0")
    assert _reached(repo)["shared"]["reached_via"] == ["p1", "p2", "p3"]


def test_at_most_forty_reached_packages_and_the_rest_are_named(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("hub\n")
    site = _venv(repo)
    names = [f"dep{i:02d}" for i in range(45)]
    _install(site, "hub", "1.0", names)
    for n in names:
        _install(site, n, "1.0")
    pkgs, warnings = deps.discover_pypi(repo, {})
    reached = [p["name"] for p in pkgs if p.get("reached_via")]
    assert reached == names[:40]  # breadth first, names in sorted order
    assert len(warnings) == 1
    assert "40" in warnings[0] and all(n in warnings[0] for n in names[40:])


def test_the_order_is_sorted_and_two_runs_agree(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("zed\nalpha\n")
    site = _venv(repo)
    _install(site, "zed", "1.0", ["yak", "bee"])
    _install(site, "alpha", "1.0", ["moth"])
    for n in ("yak", "bee", "moth"):
        _install(site, n, "1.0")
    first = deps.discover_pypi(repo, {})
    assert [p["name"] for p in first[0]] == ["alpha", "zed", "moth", "bee", "yak"]
    assert deps.discover_pypi(repo, {}) == first


def test_a_marker_that_cannot_be_evaluated_excludes_the_requirement_and_says_why(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("a\n")
    site = _venv(repo)
    _install(site, "a", "1.0", ['odd; python_full_version ~= "x"', 'skipped; python_version < "2"'])
    _install(site, "odd", "1.0")
    _install(site, "skipped", "1.0")
    reached = _reached(repo)
    assert "skipped" not in reached  # a marker that evaluates false is simply not followed
    odd = reached["odd"]
    assert odd["status"] == "unavailable" and odd["snapshot"] is None
    assert "marker" in odd["reason"] and "could not be evaluated" in odd["reason"]


def test_an_unreadable_metadata_stops_that_branch_and_warns(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("a\n")
    site = _venv(repo)
    _install(site, "a", "1.0", ["b"])
    _install(site, "b", "1.0", ["c"])
    _install(site, "c", "1.0")
    real = deps._requires_dist

    def unreadable_b(dist):
        if dist.name.startswith("b-"):
            raise OSError("unreadable")
        return real(dist)
    monkeypatch.setattr(deps, "_requires_dist", unreadable_b)
    pkgs, warnings = deps.discover_pypi(repo, {})
    assert [p["name"] for p in pkgs if p.get("reached_via")] == ["b"]
    assert any("pypi:b" in w and "METADATA" in w for w in warnings)


def test_a_reached_package_with_no_record_or_no_python_files_is_unavailable(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("a\n")
    site = _venv(repo)
    _install(site, "a", "1.0", ["norec", "nopy"])
    _install(site, "norec", "1.0", record=False)
    _install(site, "nopy", "1.0", files={"nopy/data.bin": "x"})
    reached = _reached(repo)
    assert reached["norec"]["status"] == "unavailable" and "RECORD" in reached["norec"]["reason"]
    assert reached["nopy"]["status"] == "unavailable" and ".py" in reached["nopy"]["reason"]


def test_a_requirement_that_is_not_installed_is_unavailable(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("a\n")
    _install(_venv(repo), "a", "1.0", ["gone"])
    gone = _reached(repo)["gone"]
    assert gone["status"] == "unavailable"
    assert gone["reason"] == "no installed copy in .venv, venv or $VIRTUAL_ENV"


def test_no_environment_reaches_nothing(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("kombu>=5\n")
    assert _reached(repo) == {}


# --- Task 3 -----------------------------------------------------------------
def test_installed_is_a_basis():
    assert deps.BASES == ("locked", "pinned", "declared_range", "installed")


def test_a_lock_listing_a_reached_package_makes_it_locked(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("kombu>=5\n")
    (repo / "uv.lock").write_text('version = 1\n[[package]]\nname = "amqp"\nversion = "5.3.1"\n'
                                  '[[package]]\nname = "vine"\nversion = "5.0.0"\n')
    _kombu_env(repo)
    reached = _reached(repo)
    assert (reached["amqp"]["basis"], reached["amqp"]["status"]) == ("locked", "available")
    vine = reached["vine"]
    assert (vine["basis"], vine["status"]) == ("locked", "unavailable")
    assert vine["reason"] == "installed 5.1.0, the lock says 5.0.0"
    assert vine["version"] == "5.1.0" and vine["snapshot"] is None


def test_without_a_lock_the_basis_is_installed(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("kombu>=5\n")
    _kombu_env(repo)
    assert {p["basis"] for p in _reached(repo).values()} == {"installed"}


def test_an_editable_reached_package_is_unavailable(tmp_path):
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("a\n")
    site = _venv(repo)
    _install(site, "a", "1.0", ["b"])
    _install(site, "b", "1.0", editable=True)
    b = _reached(repo)["b"]
    assert b["status"] == "unavailable"
    assert b["reason"] == "editable install, not a released version"


def test_an_installed_but_unavailable_package_is_still_followed(tmp_path):
    """As for a declared package: what it requires is read from its installed metadata."""
    repo = _repo(tmp_path)
    (repo / "requirements.txt").write_text("a\n")
    site = _venv(repo)
    _install(site, "a", "1.0", ["b"])
    _install(site, "b", "1.0", ["c"], editable=True)
    _install(site, "c", "1.0")
    assert _reached(repo)["c"]["status"] == "available"
