"""Skills and agents must reach plugin files by paths Claude Code substitutes.

Claude Code replaces ${CLAUDE_PLUGIN_ROOT} and ${CLAUDE_SKILL_DIR} when it
loads plugin content, but neither is set in the Bash tool's environment. A
bare relative path, or a shorthand such as `$T` defined in prose, only works
if the model resolves it by hand; when it does not, the natural recovery is to
go looking for a thunderstruck checkout, which is issue #20.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

GENERATED = {ROOT / "skills" / "stability-catalog" / "references" / "patterns.md"}
CONTENT = sorted(
    p for p in [*ROOT.glob("skills/**/*.md"), *ROOT.glob("agents/*.md")]
    if p not in GENERATED
)
SUBSTITUTED = ("CLAUDE_PLUGIN_ROOT", "CLAUDE_SKILL_DIR")

PLACEHOLDER_PATH = re.compile(r"\$\{(CLAUDE_PLUGIN_ROOT|CLAUDE_SKILL_DIR)\}/([\w./-]+)")
# A backticked path into the plugin's own tree with no placeholder in front.
BARE_PLUGIN_PATH = re.compile(
    r"`((?:scripts|catalog|examples|references|skills|agents|hooks)/[\w./-]*[\w-])`")
FENCE = re.compile(r"^```(?:bash|sh)\n(.*?)^```", re.MULTILINE | re.DOTALL)
SHELL_VAR = re.compile(r"\$\{?([A-Za-z_]\w*)")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def test_content_is_discovered():
    assert any("thunderstruck-scan" in str(p) for p in CONTENT)


@pytest.mark.parametrize("path", CONTENT, ids=_rel)
def test_placeholder_paths_resolve(path):
    missing = []
    for var, rel in PLACEHOLDER_PATH.findall(path.read_text()):
        base = ROOT if var == "CLAUDE_PLUGIN_ROOT" else path.parent
        if not (base / rel.rstrip(".")).exists():
            missing.append(f"${{{var}}}/{rel}")
    assert not missing, f"{_rel(path)} names files the plugin does not ship: {missing}"


@pytest.mark.parametrize("path", CONTENT, ids=_rel)
def test_no_bare_plugin_relative_paths(path):
    bare = BARE_PLUGIN_PATH.findall(path.read_text())
    assert not bare, (
        f"{_rel(path)} names plugin files without a substituted base: {bare}. "
        f"Prefix them with ${{CLAUDE_PLUGIN_ROOT}}/ or ${{CLAUDE_SKILL_DIR}}/.")


@pytest.mark.parametrize("path", CONTENT, ids=_rel)
def test_commands_use_no_unset_shell_variables(path):
    unset = []
    for block in FENCE.findall(path.read_text()):
        unset += [v for v in SHELL_VAR.findall(block) if v not in SUBSTITUTED]
    assert not unset, (
        f"{_rel(path)} runs commands with shell variables the Bash tool does not "
        f"have: {sorted(set(unset))}")


def _signals(root: Path, repo: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "signals.py"), "--repo", str(repo),
         "--top", "3", "--since", "24m", "--stdout"],
        capture_output=True, text=True, cwd=str(repo), env=env)


def test_running_from_a_checkout_is_visible(fixture_repo, tmp_path):
    checkout = tmp_path / "checkout"
    for part in ("scripts", "catalog"):
        shutil.copytree(ROOT / part, checkout / part)
    (checkout / ".git").mkdir()

    proc = _signals(checkout, fixture_repo)
    assert proc.returncode == 0, proc.stderr
    assert "running from the source checkout" in proc.stderr
    assert "source checkout" not in proc.stdout


def test_an_installed_copy_does_not_warn(fixture_repo, tmp_path):
    installed = tmp_path / "cache" / "thunderstruck" / "0.3.0"
    for part in ("scripts", "catalog"):
        shutil.copytree(ROOT / part, installed / part)

    proc = _signals(installed, fixture_repo)
    assert proc.returncode == 0, proc.stderr
    assert "source checkout" not in proc.stderr
