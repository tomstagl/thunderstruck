"""The ticket agent's drift check (#79).

It narrows what the agent has to read before building: the commits that
landed on main after the spec and plan were last agreed, on files they name.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude" / "skills" / "implement-ticket" / "plan_drift.py"

SPEC = "docs/superpowers/specs/2026-10-09-x-design.md"
PLAN = "docs/superpowers/plans/2026-10-09-x.md"
PLAN_TEXT = """# X plan

Edit `scripts/a.py:10-20`, then run `pytest tests/test_a.py::test_x -v`.
Task 3 creates `scripts/new.py`. Task 4 removes `scripts/gone.py` and moves
`scripts/old.py`. Not paths: `agent:blocked`, `uv run scripts/a.py --top 3`,
`https://example.com/a.py`, `docs/superpowers/plans/`.
"""
SPEC_TEXT = "# X design\n\nSee [#79](https://example.com/issues/79) and `catalog/x.yaml`.\n"


def _git(repo: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "init.defaultBranch=main", *args],
                   cwd=repo, env=env, check=True, capture_output=True)


def commit(repo: Path, message: str, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        path = repo / rel
        if text is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


@pytest.fixture
def repo(tmp_path) -> Path:
    _git(tmp_path, "init", "-q")
    commit(tmp_path, "contract agreed", {
        SPEC: SPEC_TEXT, PLAN: PLAN_TEXT,
        "scripts/a.py": "a\n", "scripts/gone.py": "g\n", "scripts/old.py": "o\n" * 20,
        "scripts/unnamed.py": "u\n", "tests/test_a.py": "t\n", "catalog/x.yaml": "c: 1\n",
    })
    return tmp_path


def run(repo: Path, ref="HEAD", plan=PLAN, spec=SPEC):
    proc = subprocess.run([sys.executable, str(SCRIPT), "--plan", plan, "--spec", spec,
                           "--ref", ref], cwd=repo, capture_output=True, text=True)
    return proc.returncode, (json.loads(proc.stdout) if proc.returncode == 0 else None), proc


def test_nothing_changed_since_the_contract(repo):
    code, out, _ = run(repo)
    assert code == 0
    assert out["drifted"] == [] and out["gone"] == [] and out["truncated"] is False


def test_a_commit_on_a_named_file_is_listed(repo):
    commit(repo, "Change the test", {"tests/test_a.py": "changed\n"})
    _, out, _ = run(repo)
    assert [(d["subject"], d["paths"]) for d in out["drifted"]] == \
        [("Change the test", ["tests/test_a.py"])]


def test_a_commit_on_an_unnamed_file_is_not(repo):
    commit(repo, "Elsewhere", {"scripts/unnamed.py": "changed\n"})
    assert run(repo)[1]["drifted"] == []


def test_line_and_test_id_suffixes_name_the_file(repo):
    commit(repo, "Edit a", {"scripts/a.py": "changed\n"})
    commit(repo, "Edit the test", {"tests/test_a.py": "changed\n"})
    paths = [p for d in run(repo)[1]["drifted"] for p in d["paths"]]
    assert paths == ["tests/test_a.py", "scripts/a.py"]  # newest first


def test_only_files_in_the_tree_are_named(repo):
    # a.py, test_a.py, gone.py, old.py, x.yaml exist; new.py does not; the rest are not files
    assert run(repo)[1]["named"] == 5


def test_a_file_the_plan_creates_that_main_then_gains_is_drift(repo):
    commit(repo, "Someone added new.py", {"scripts/new.py": "n\n"})
    _, out, _ = run(repo)
    assert [d["paths"] for d in out["drifted"]] == [["scripts/new.py"]]


def test_deleted_and_renamed_files_are_gone(repo):
    commit(repo, "Remove gone", {"scripts/gone.py": None})
    (repo / "scripts/old.py").rename(repo / "scripts/older.py")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "Rename old")
    gone = run(repo)[1]["gone"]
    assert gone == [{"path": "scripts/gone.py", "change": "deleted"},
                    {"path": "scripts/old.py", "change": "renamed", "to": "scripts/older.py"}]


def test_the_base_moves_when_the_plan_or_spec_is_touched(repo):
    commit(repo, "Drift", {"scripts/a.py": "changed\n"})
    commit(repo, "Amend the plan", {PLAN: PLAN_TEXT + "\nAmended.\n"})
    _, out, _ = run(repo)
    assert out["drifted"] == []
    assert out["base"] == subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                         capture_output=True, text=True).stdout.strip()


def test_the_list_is_capped_and_says_so(repo):
    for i in range(31):
        commit(repo, f"Edit {i}", {"scripts/a.py": f"{i}\n"})
    out = run(repo)[1]
    assert len(out["drifted"]) == 30 and out["truncated"] is True
    assert out["drifted"][0]["subject"] == "Edit 30"


def test_output_is_byte_stable(repo):
    commit(repo, "Edit a", {"scripts/a.py": "changed\n"})
    assert run(repo)[2].stdout == run(repo)[2].stdout


@pytest.mark.parametrize("kwargs", [{"ref": "no-such-ref"}, {"plan": "docs/superpowers/plans/missing.md"},
                                    {"spec": "docs/superpowers/specs/missing-design.md"}])
def test_an_unusable_input_exits_2(repo, kwargs):
    code, _, proc = run(repo, **kwargs)
    assert code == 2 and proc.stdout == ""


def test_a_shallow_clone_exits_2(repo, tmp_path):
    commit(repo, "More history", {"scripts/a.py": "changed\n"})
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow)],
                   check=True, capture_output=True)
    code, _, proc = run(shallow)
    assert code == 2 and "shallow" in proc.stderr and proc.stdout == ""


def test_the_script_is_stdlib_only():
    tree = ast.parse(SCRIPT.read_text())
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    bad = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
           if a.name.split(".")[0] not in stdlib]
    bad += [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
            and n.module and n.module.split(".")[0] not in stdlib]
    assert not bad, f"plan_drift.py imports non-stdlib modules: {bad}"
