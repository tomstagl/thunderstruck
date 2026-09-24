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


# ------------------------------------------------------------- pinned dates --

import pytest  # noqa: E402

import gen_sample_report as gen  # noqa: E402

REPORT = ("# thunderstruck — fixture\n\n"
          "**fixture** · `main` @ `446de9b`  \n"
          "Scanned 2026-09-24 · window `2020-01-01` (since 2020-01-01, 18 commits)  \n\n"
          "`component:default/fixture-app` · 4 edge(s), 1 hop · fetched 2026-09-23 (1 days ago) · x\n")


def test_pin_dates_rewrites_and_labels():
    out = gen.pin_dates(REPORT, "2025-07-29")
    assert "Scanned 2025-07-29 (dates fixed for this sample) · window" in out
    assert "fetched 2025-07-29 (0 days ago)" in out
    assert "2026-" not in out


@pytest.mark.parametrize("broken", [
    REPORT.replace("Scanned 2026-09-24", "Ran 2026-09-24"),
    REPORT.replace("fetched 2026-09-23 (1 days ago)", "fetched on 2026-09-23"),
    REPORT + "Scanned 2026-09-25 · again\n",
])
def test_pin_dates_requires_exactly_one_match(broken):
    with pytest.raises(SystemExit, match="matched"):
        gen.pin_dates(broken, "2025-07-29")


def test_real_report_never_prints_the_label(scanned_copy, plugin_root):
    """AC-5: fixed dates exist only in the generator, never in a real scan."""
    import sys
    from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(scanned_copy)], check=True, capture_output=True)
    report = (scanned_copy / ".thunderstruck" / "report.md").read_text()
    assert gen.DATE_LABEL not in report
    scanned = _hotspots(scanned_copy)["generated_at"][:10]
    assert f"Scanned {scanned} · " in report, "a real scan prints its real date, unlabelled"


# -------------------------------------------------------------- check mode --


def test_check_passes_on_an_identical_sample(tmp_path):
    dest = tmp_path / "sample-report.md"
    dest.write_text("same\n")
    assert gen.check(dest, "same\n") == (True, "sample-report.md is up to date")


def test_check_shows_the_diff_and_how_to_regenerate(tmp_path):
    dest = tmp_path / "sample-report.md"
    dest.write_text("a\nold\n")
    ok, message = gen.check(dest, "a\nnew\n")
    assert not ok
    assert "-old" in message and "+new" in message
    assert message.endswith(f"regenerate with: {gen.REGENERATE}")


def test_check_fails_on_a_missing_sample(tmp_path):
    ok, message = gen.check(tmp_path / "sample-report.md", "x\n")
    assert not ok and "does not exist" in message and gen.REGENERATE in message


def test_check_truncates_long_diffs(tmp_path):
    dest = tmp_path / "sample-report.md"
    dest.write_text("".join(f"old {n}\n" for n in range(200)))
    ok, message = gen.check(dest, "".join(f"new {n}\n" for n in range(200)))
    assert not ok and "more diff line(s)" in message
    assert len(message.splitlines()) <= gen.DIFF_LINES + 3
