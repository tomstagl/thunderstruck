"""The sample report must be byte-reproducible on any machine (#26)."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from build_fixture import build

BASE = datetime(2025, 1, 6, 9, 0, 0, tzinfo=timezone.utc)


def _head(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_fixture_ignores_user_git_config(tmp_path, monkeypatch):
    """Signing, hooks, templates, injected config and a sha256 default each
    changed or broke the fixture before; none of them may reach it now."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    for name in ("commit-msg", "pre-commit"):
        hook = hooks / name
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
    template = tmp_path / "template"
    (template / "hooks").mkdir(parents=True)
    (template / "hooks" / "commit-msg").write_text("#!/bin/sh\nexit 1\n")
    (template / "hooks" / "commit-msg").chmod(0o755)
    hostile = tmp_path / "gitconfig"
    hostile.write_text(
        "[commit]\n\tgpgsign = true\n"
        "[gpg]\n\tprogram = false\n"
        f"[core]\n\thooksPath = {hooks}\n"
        f"[init]\n\ttemplateDir = {template}\n\tdefaultObjectFormat = sha256\n")

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile))
    monkeypatch.setenv("GIT_DEFAULT_HASH", "sha256")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    hostile_head = _head(build(tmp_path / "hostile", base_date=BASE))

    for var in ("GIT_DEFAULT_HASH", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
        monkeypatch.delenv(var)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    clean_head = _head(build(tmp_path / "clean", base_date=BASE))

    assert len(hostile_head) == 40, "the fixture must stay sha1"
    assert hostile_head == clean_head
