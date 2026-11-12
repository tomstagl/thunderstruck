"""#57 AC-5: no stage runs, imports or builds the scanned project."""

from __future__ import annotations

import ast
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

FORBIDDEN_NAMES = {"exec", "eval", "compile", "__import__"}
FORBIDDEN_MODULES = {"importlib", "runpy", "ctypes", "pty"}
FORBIDDEN_OS = {"system", "popen", "execv", "execve", "execvp", "execvpe", "execl", "execle",
                "execlp", "execlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe", "spawnl",
                "spawnle", "spawnlp", "spawnlpe", "posix_spawn", "posix_spawnp"}
# (file, function): the only places a process may start. The first group must
# start git; context.run_command starts the catalog command the user approved
# by hash (#1). gen_sample_report and the other NOT_A_STAGE scripts are
# development tools (spec §11.1 lists the stages): validate_plugin.py runs
# `claude plugin validate` for a maintainer, never during a scan.
GIT_ONLY = {("_common.py", "git"), ("_common.py", "git_paths"), ("_common.py", "commit_touches"),
            ("_common.py", "commit_exists"), ("_common.py", "tracked_index"),
            ("_common.py", "find_repo_root")}
OTHER_ALLOWED = {("context.py", "run_command")}
NOT_A_STAGE = {"gen_sample_report.py", "gen_catalog_docs.py", "validate_plugin.py"}


def _scripts() -> list[Path]:
    return sorted(p for p in SCRIPTS.rglob("*.py") if p.name not in NOT_A_STAGE)


def _calls(tree: ast.AST):
    """Every call with the name of its innermost enclosing def ("<module>" at top level)."""
    def visit(node: ast.AST, owner: str):
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else owner
            if isinstance(child, ast.Call):
                yield owner, child
            yield from visit(child, inner)
    yield from visit(tree, "<module>")


def test_calls_are_attributed_to_their_innermost_def_only():
    tree = ast.parse("import subprocess\ndef outer():\n    def inner():\n        subprocess.run(['git'])\n"
                     "    subprocess.run(['git'])\nsubprocess.run(['x'])\n")
    owners = sorted(fn for fn, call in _calls(tree) if ast.unparse(call.func) == "subprocess.run")
    assert owners == ["<module>", "inner", "outer"]


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_no_script_imports_or_evaluates_code(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & FORBIDDEN_MODULES, path
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in FORBIDDEN_MODULES, path
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in FORBIDDEN_NAMES, f"{path.name}: {node.func.id}()"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
            assert node.func.attr not in FORBIDDEN_OS, f"{path.name}: os.{node.func.attr}()"


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_processes_start_only_where_reviewed(path):
    tree = ast.parse(path.read_text())
    for fn, call in _calls(tree):
        f = call.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "subprocess" \
                and f.attr in {"run", "Popen", "call", "check_call", "check_output"}:
            where = (path.name, fn)
            assert where in GIT_ONLY | OTHER_ALLOWED, f"{path.name}:{call.lineno} starts a process in {fn}()"
            if where in GIT_ONLY:
                argv = call.args[0] if call.args else None
                assert isinstance(argv, ast.List) and isinstance(argv.elts[0], ast.Constant) \
                    and argv.elts[0].value == "git", f"{path.name}:{call.lineno} must start git"


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_sys_path_only_gains_the_plugins_own_directories(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in {"insert", "append"} and isinstance(node.func.value, ast.Attribute) \
                and node.func.value.attr == "path" and getattr(node.func.value.value, "id", None) == "sys":
            assert "__file__" in ast.unparse(node), f"{path.name}:{node.lineno}: {ast.unparse(node)}"


def test_the_hooks_run_only_the_plugins_scripts_without_site():
    """AC-5: python3 -S, so an active project venv's .pth files never run in a hook."""
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    commands = [h["command"] for group in hooks["hooks"].values() for m in group for h in m["hooks"]]
    assert commands and all("${CLAUDE_PLUGIN_ROOT}/scripts/" in cmd for cmd in commands)
    assert all(cmd.startswith("python3 -S ") for cmd in commands), commands


@pytest.mark.parametrize("path", ["agents/thunderstruck-investigator.md", "agents/thunderstruck-skeptic.md",
                                  "skills/thunderstruck-scan/SKILL.md"])
def test_instructions_say_it(path):
    assert c.NO_EXECUTION in (ROOT / path).read_text()


@pytest.mark.parametrize("path", ["agents/thunderstruck-investigator.md", "agents/thunderstruck-skeptic.md"])
def test_agents_cannot_run_anything(path):
    head = (ROOT / path).read_text().split("---")[1]
    tools = next(l for l in head.splitlines() if l.startswith("tools:")).split(":", 1)[1]
    assert {t.strip() for t in tools.split(",")} <= {"Read", "Grep", "Glob"}


TRAPS = {
    "setup.py": "import pathlib; pathlib.Path('{s}/setup.py').touch()\n",
    "conftest.py": "import pathlib; pathlib.Path('{s}/conftest.py').touch()\n",
    "sitecustomize.py": "import pathlib; pathlib.Path('{s}/sitecustomize.py').touch()\n",
    "trap/__init__.py": "import pathlib; pathlib.Path('{s}/trap_init').touch()\n",
    ".venv/lib/python3.12/site-packages/trap.pth": "import pathlib; pathlib.Path('{s}/pth').touch()\n",
    ".venv/lib/python3.12/site-packages/trap-1.0.dist-info/METADATA": "Name: trap\nVersion: 1.0\n",
    ".venv/lib/python3.12/site-packages/trap-1.0.dist-info/RECORD": "trap.pth,,\n",
    "Makefile": "all:\n\ttouch {s}/make\n",
    "build.gradle": "task x { doLast { new File('{s}/gradle').text = '' } }\n",
    "pom.xml": "<project><build><plugins/></build></project>\n",
    ".envrc": "touch {s}/envrc\n",
}
TOOLS = ["npm", "npx", "yarn", "pnpm", "pip", "pip3", "poetry", "mvn", "gradle", "gradlew", "make",
         "node", "java", "go", "cargo", "tox", "pytest"]


def test_no_stage_runs_anything_from_a_trapped_repository(validated_repo, validated_env, tmp_path):
    sentinels = tmp_path / "sentinels"
    sentinels.mkdir()
    for rel, body in TRAPS.items():
        p = validated_repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.replace("{s}", str(sentinels)))
    pkg = json.loads((validated_repo / "package.json").read_text())
    pkg["scripts"] = {k: f"touch {sentinels}/npm-{k}" for k in ("preinstall", "postinstall", "prepare")}
    pkg["dependencies"] = {"trap": "1.0.0"}
    (validated_repo / "package.json").write_text(json.dumps(pkg))
    (validated_repo / "requirements.txt").write_text("trap==1.0\n")
    shadow = tmp_path / "bin"
    shadow.mkdir()
    for tool in TOOLS:
        t = shadow / tool
        t.write_text(f"#!/bin/sh\ntouch {sentinels}/tool-{tool}\n")
        t.chmod(t.stat().st_mode | stat.S_IEXEC)
    env = {**validated_env, "PATH": f"{shadow}{os.pathsep}{validated_env.get('PATH', os.environ['PATH'])}",
           "VIRTUAL_ENV": str(validated_repo / ".venv")}
    steps = [["signals.py", "--top", "5"], ["bundle.py"], ["validate.py"],
             ["verify.py", "prepare", "--model", "sonnet"], ["verify.py", "apply"],
             ["report.py"], ["report_html.py"]]
    for step in steps:
        subprocess.run([sys.executable, str(SCRIPTS / step[0]), *step[1:], "--repo", str(validated_repo)],
                       capture_output=True, text=True, cwd=str(validated_repo), env=env)
    payload = {"tool_name": "Edit", "cwd": str(validated_repo), "session_id": "s",
               "tool_input": {"file_path": str(validated_repo / "src/sync/collection.ts")}}
    subprocess.run([sys.executable, str(SCRIPTS / "guardrail.py")], input=json.dumps(payload),
                   capture_output=True, text=True, cwd=str(validated_repo), env=env)
    assert sorted(p.name for p in sentinels.iterdir()) == []
