"""#66: portable whole-word call-site search and visible degradation."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import bundle
from build_fixture import isolated_git_env


CALLER = "import { step } from './a';\nstep(1);\nconst stepper = 2;\nconst my_step = 3;\n"
EXPORT = "export const step = 1;\n"


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                       env=isolated_git_env())
    return repo


def _call_sites(repo: Path, rel: str = "src/a.ts") -> str:
    text = bundle.section_related(repo, {"file": rel}, [], 10_000)
    return text.partition("## Call sites elsewhere in the repo\n")[2].partition("\n## ")[0].strip()


# --- Task 1 -----------------------------------------------------------------
def test_callers_are_found_as_whole_words(tmp_path):
    repo = _repo(tmp_path, {"src/a.ts": EXPORT, "src/b.ts": CALLER})
    assert _call_sites(repo).splitlines() == [
        "- `src/b.ts:1:import { step } from './a';`",
        "- `src/b.ts:2:step(1);`",
    ]


def test_the_fixture_briefs_its_callers(scanned_repo):
    index = json.loads((scanned_repo / ".thunderstruck/bundles/index.json").read_text())
    entry = next(b for b in index["bundles"] if b["file"] == "src/client/releases.ts")
    text = Path(entry["bundle"]).read_text(encoding="utf-8")
    assert "src/sync/scheduler.ts:26:" in text and "src/sync/scheduler.ts:30:" in text


def test_the_search_hands_git_no_pattern(tmp_path, monkeypatch):
    repo = _repo(tmp_path, {"src/a.ts": EXPORT, "src/b.ts": CALLER})
    seen = []
    real = subprocess.run

    def record(args, **kwargs):
        if "grep" in args:
            seen.append(args)
        return real(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", record)
    _call_sites(repo)
    (args,) = seen
    assert {"-F", "-w"} <= set(args)
    assert not {"-E", "-G", "-P"} & set(args)
    assert args[args.index("-e") + 1] == "step"


def test_a_file_without_exports_has_no_call_site_section(tmp_path):
    repo = _repo(tmp_path, {"src/a.ts": "const step = 1;\n", "src/b.ts": CALLER})
    assert "## Call sites" not in bundle.section_related(repo, {"file": "src/a.ts"}, [], 10_000)


# --- Task 2 -----------------------------------------------------------------
@pytest.mark.parametrize("hits", ["", "src/a.ts:1:export const step = 1;\n"])
def test_no_other_callers_is_stated(tmp_path, monkeypatch, hits):
    repo = _repo(tmp_path, {"src/a.ts": EXPORT})
    monkeypatch.setattr(bundle, "call_site_hits", lambda *args: hits, raising=False)
    assert _call_sites(repo).startswith("None found:")


@pytest.mark.parametrize("outcome", ["exit-128", "timeout", "no-git"])
def test_a_search_that_did_not_finish_is_stated(tmp_path, monkeypatch, outcome):
    repo = _repo(tmp_path, {"src/a.ts": EXPORT, "src/b.ts": CALLER})
    real = subprocess.run

    def run(args, **kwargs):
        if "grep" not in args:
            return real(args, **kwargs)
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        if outcome == "no-git":
            raise FileNotFoundError("git")
        return subprocess.CompletedProcess(args, 128, b"", b"fatal details")

    monkeypatch.setattr(subprocess, "run", run)
    text = _call_sites(repo)
    assert text.startswith("Not searched:")
    assert "fatal details" not in text


def test_bundle_prints_which_briefings_lack_call_sites(scanned_repo, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "copy"
    shutil.copytree(scanned_repo, repo, symlinks=True)
    monkeypatch.setattr(bundle, "call_site_hits", lambda *args: None, raising=False)
    assert bundle.main(["--repo", str(repo)]) == 0
    assert "src/client/releases.ts: call sites not searched" in capsys.readouterr().out
