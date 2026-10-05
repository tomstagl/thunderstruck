# Call Sites on macOS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A briefing lists a file's call sites on macOS as on Linux. It says "none found" or "not searched" instead of leaving the section out, and CI checks the call-site tests on macOS.

**Architecture:** `bundle.py` gets `call_site_hits(repo, symbols)`. It runs `git grep -F -w -e <symbol>…` (fixed strings, git's own word boundary, no platform regex library) and returns `None` when the search does not finish. `section_related` renders one of three states from it. `main` prints a line for each briefing whose call sites were not searched. A new CI job runs the call-site tests on `macos-latest`.

**Tech Stack:** Python 3.11+ (stdlib), git, `uv`, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-05-call-sites-on-macos-design.md` (§n below refers to it; §0 has the cause and its evidence). Requirements AC-1…AC-6 and the product decision are in GitHub issue #66.

**Branch:** named by whoever builds it. One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

On macOS before Task 1, `tests/test_signals_citable.py::test_non_ascii_names_are_briefed_unquoted` fails on `main`. That failure is this ticket. From Task 1 on, it passes.

New tests go in one file, `tests/test_call_sites.py`, appended task by task under a `# --- Task N` comment. Run them with `uv run --with pytest --with pyyaml --with lizard pytest tests/test_call_sites.py -q`.

## Global Constraints

- Bundles stay byte-identical across runs on an unchanged repo. No stderr, exit code, duration or path outside the repo goes into a bundle body (§3).
- Matching is unchanged apart from the platform (AC-4): the first 12 symbols, the same six glob pathspecs, `-I`, `-n`, `core.quotePath=false`, the 15-line and 160-character caps, the hotspot's own lines excluded, and non-UTF-8 lines skipped.
- No regex from the scanned repo or its symbols ever reaches git: `-F` only, never `-E`, `-G` or `-P` (§2).
- `VALIDATION_RULES` does not change (§5).
- `guardrail.py`, the finding contract, `validate.py` and the report are untouched.
- Public repository: no organisation-specific names, hosts, local paths or credentials in any file.

## Review Focus

1. **A hotspot whose only hits are its own lines.** The briefing says `None found`, never an empty list. Pinned in Task 2 by `test_no_callers_is_stated`'s sibling, `test_only_its_own_lines_is_none_found`.
2. **git exits 128 (a bad pathspec or a corrupt index), times out, or is missing.** Each gives `Not searched`, and `bundle.py` does not crash. Pinned in Task 2.
3. **`stepper`, `my_step`.** Not call sites of `step`. Pinned in Task 1.

---

### Task 1: Call sites found on every platform

**Satisfies:** AC-1 (the non-ASCII test and the fixture's call sites on macOS), AC-2 (a test red on macOS, one red everywhere), AC-4 (whole words, same limits).

**Files:**
- Modify: `scripts/bundle.py` (`import subprocess`; new `CALLER_GLOBS` and `call_site_hits` above `section_related`; the search in `section_related`)
- Create: `tests/test_call_sites.py`

**Interfaces:**
- Produces, in `bundle`: `CALLER_GLOBS: tuple[str, ...]`; `call_site_hits(repo: Path, symbols: list[str]) -> str | None`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_call_sites.py`:

```python
"""#66: a briefing's call sites are found on every platform, and a search
that did not finish says so."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import bundle
from build_fixture import isolated_git_env


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


def _call_sites(repo: Path, rel: str) -> str:
    text = bundle.section_related(repo, {"file": rel}, [], 10_000)
    return text.partition("## Call sites elsewhere in the repo\n")[2].partition("\n## ")[0].strip()


# --- Task 1 -----------------------------------------------------------------
CALLER = "import { step } from './a';\nstep(1);\nconst stepper = 2;\nconst my_step = 3;\n"


def test_callers_are_found_as_whole_words(tmp_path):
    """AC-2, AC-4. Red on macOS before the fix, where no line is found."""
    repo = _repo(tmp_path, {"src/a.ts": "export function step(x: number) { return x; }\n",
                            "src/b.ts": CALLER})
    assert _call_sites(repo, "src/a.ts").split("\n") == [
        "- `src/b.ts:1:import { step } from './a';`",
        "- `src/b.ts:2:step(1);`",
    ]


def test_the_fixture_briefs_its_callers(scanned_repo):
    """AC-1: the shipped fixture, as the pipeline runs it."""
    index = json.loads((scanned_repo / ".thunderstruck" / "bundles" / "index.json").read_text())
    entry = next(b for b in index["bundles"] if b["file"] == "src/client/releases.ts")
    text = Path(entry["bundle"]).read_text(encoding="utf-8")
    assert "src/sync/scheduler.ts:26:" in text and "src/sync/scheduler.ts:30:" in text


def test_the_search_hands_git_no_pattern(tmp_path, monkeypatch):
    """AC-2 on every platform: symbols reach git as fixed strings, so no
    platform regex library ever reads them (spec §2)."""
    seen = []
    real = subprocess.run
    monkeypatch.setattr(bundle.subprocess, "run",
                        lambda args, **kw: (seen.append(list(args)), real(args, **kw))[1])
    repo = _repo(tmp_path, {"src/a.ts": "export const step = 1;\n", "src/b.ts": CALLER})
    _call_sites(repo, "src/a.ts")
    (args,) = [a for a in seen if "grep" in a]
    assert "-F" in args and "-w" in args
    assert not {"-E", "-G", "-P"} & set(args)
    assert args[args.index("-e") + 1] == "step"


def test_a_file_without_exports_has_no_call_site_section(tmp_path):
    """AC-4: nothing was searched for, so nothing is said."""
    repo = _repo(tmp_path, {"src/a.ts": "const step = 1;\n", "src/b.ts": CALLER})
    assert "## Call sites" not in bundle.section_related(repo, {"file": "src/a.ts"}, [], 10_000)
```

- [ ] **Step 2: Run them and watch them fail.**

```bash
uv run --with pytest --with pyyaml --with lizard pytest tests/test_call_sites.py -q
```

Expected: `test_the_search_hands_git_no_pattern` fails on every platform (`AttributeError`: `bundle` has no `subprocess`). On macOS, `test_callers_are_found_as_whole_words` and `test_the_fixture_briefs_its_callers` also fail with no call sites found. On Linux they pass. `test_a_file_without_exports_has_no_call_site_section` passes everywhere.

- [ ] **Step 3: Implement.** In `scripts/bundle.py`, add `import subprocess` after `import re`. Add above `def section_related(`:

```python
CALLER_GLOBS = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.py")


def call_site_hits(repo: Path, symbols: list[str]) -> str | None:
    """`git grep` lines naming any of `symbols` as a whole word, or None when
    the search did not finish.

    The symbols are fixed strings and git's own -w draws the word boundary:
    `-E` hands a pattern to the platform's regex library, and macOS's has no
    `\\b`, so every search came back empty there (#66). Names stay unquoted so
    a non-ASCII hotspot matches itself; the pathspecs stay globs on purpose.
    """
    args = ["git", "-C", str(repo), "-c", "core.quotePath=false", "grep", "-n", "-I", "-w", "-F"]
    for symbol in symbols:
        args += ["-e", symbol]
    try:
        proc = subprocess.run([*args, "--", *CALLER_GLOBS], capture_output=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode not in (0, 1):      # 1 is "no line matched"
        return None
    return proc.stdout.decode("utf-8", "surrogateescape")
```

In `section_related`, replace the search:

```python
    callers: list[str] = []
    if symbols:
        pattern = r"\b(" + "|".join(re.escape(s) for s in symbols[:12]) + r")\b"
        # unquoted names, so a non-ASCII hotspot matches itself below; the
        # pathspecs stay globs on purpose
        hits = c.git_paths(repo, "-c", "core.quotePath=false", "grep", "-n", "-I", "-E",
                           pattern, "--", "*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.py",
                           check=False, timeout=60)
        for line in hits.split("\n"):
```

with:

```python
    callers: list[str] = []
    hits: str | None = ""
    if symbols:
        hits = call_site_hits(repo, symbols[:12])
        for line in (hits or "").split("\n"):
```

Leave the rest of the loop and the rendering as they are; Task 2 changes the rendering. `re` is still used by `IMPORT_RES` and `EXPORT_RES`; keep the import.

- [ ] **Step 4: Run the tests.**

```bash
uv run --with pytest --with pyyaml --with lizard pytest tests/test_call_sites.py tests/test_signals_citable.py tests/test_pipeline.py -q
```

Expected: all pass, on macOS `test_non_ascii_names_are_briefed_unquoted` included.

- [ ] **Step 5: Full suite** (command above). Expected: `exit=0`.

- [ ] **Step 6: Commit**

```bash
git add scripts/bundle.py tests/test_call_sites.py
git commit -m "Find call sites with fixed strings, so macOS finds them (#66)"
```

### Task 2: None found and not searched, stated

**Satisfies:** AC-3.

**Files:**
- Modify: `scripts/bundle.py` (two constants after `CALLER_GLOBS`; the rendering in `section_related`; one line in `main`)
- Modify: `skills/thunderstruck-scan/SKILL.md` (Step 2)
- Modify: `tests/test_call_sites.py`

**Interfaces:**
- Produces, in `bundle`: `CALL_SITES_NONE: str`, `CALL_SITES_NOT_SEARCHED: str` (the exact sentences of spec §3).

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_call_sites.py`:

```python
# --- Task 2 -----------------------------------------------------------------
def test_no_callers_is_stated(tmp_path):
    """AC-3."""
    repo = _repo(tmp_path, {"src/a.ts": "export const lonely = 1;\n",
                            "src/b.ts": "export const other = 2;\n"})
    assert _call_sites(repo, "src/a.ts") == bundle.CALL_SITES_NONE


def test_only_its_own_lines_is_none_found(tmp_path):
    """AC-3: a hit in the hotspot itself is not a call site."""
    repo = _repo(tmp_path, {"src/a.ts": "export const lonely = 1;\nconsole.log(lonely);\n"})
    assert _call_sites(repo, "src/a.ts") == bundle.CALL_SITES_NONE


@pytest.mark.parametrize("outcome", ["exit-128", "timeout", "no-git"])
def test_a_search_that_did_not_finish_is_stated(tmp_path, monkeypatch, outcome):
    """AC-3: unknown is never shown as empty."""
    repo = _repo(tmp_path, {"src/a.ts": "export const step = 1;\n", "src/b.ts": CALLER})

    def run(args, **kw):
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(args, kw.get("timeout"))
        if outcome == "no-git":
            raise FileNotFoundError("git")
        return subprocess.CompletedProcess(args, 128, b"", b"fatal")

    monkeypatch.setattr(bundle.subprocess, "run", run)
    assert _call_sites(repo, "src/a.ts") == bundle.CALL_SITES_NOT_SEARCHED


def test_bundle_prints_which_briefings_lack_call_sites(scanned_repo, tmp_path, monkeypatch, capsys):
    """AC-3: the bundle step names them, and the scan relays it."""
    import shutil
    repo = tmp_path / "copy"
    shutil.copytree(scanned_repo, repo, symlinks=True)
    monkeypatch.setattr(bundle, "call_site_hits", lambda *a, **k: None)
    assert bundle.main(["--repo", str(repo)]) == 0
    assert "src/client/releases.ts: call sites not searched" in capsys.readouterr().out
```

- [ ] **Step 2: Run them and watch them fail.**

```bash
uv run --with pytest --with pyyaml --with lizard pytest tests/test_call_sites.py -q -k "stated or none_found or prints"
```

Expected: every one fails on every platform: `AttributeError` for the two constants, and no printed line.

- [ ] **Step 3: Implement.** In `scripts/bundle.py`, after `CALLER_GLOBS`:

```python
CALL_SITES_NONE = ("None found: no other tracked `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` "
                   "or `.py` file names these symbols as a whole word.")
CALL_SITES_NOT_SEARCHED = ("Not searched: the search for call sites did not finish, "
                           "so they are unknown, not absent.")
```

In `section_related`, replace:

```python
    if symbols:
        out += ["## Symbols this file exports", "",
                ", ".join(f"`{s}`" for s in symbols[:25]), ""]
    if callers:
        out += ["## Call sites elsewhere in the repo", ""]
        out += [f"- `{ln}`" for ln in callers]
        out.append("")
```

with:

```python
    if symbols:
        out += ["## Symbols this file exports", "",
                ", ".join(f"`{s}`" for s in symbols[:25]), ""]
        out += ["## Call sites elsewhere in the repo", ""]
        if hits is None:
            out += [CALL_SITES_NOT_SEARCHED, ""]
        elif callers:
            out += [f"- `{ln}`" for ln in callers]
            out.append("")
        else:
            out += [CALL_SITES_NONE, ""]
```

In `main`, directly after `path.write_text(body, encoding="utf-8")`:

```python
        if CALL_SITES_NOT_SEARCHED in body:
            print(f"{hs['id']} {hs['file']}: call sites not searched; its briefing says so")
```

In `skills/thunderstruck-scan/SKILL.md`, Step 2, after the sentence ending "the line before the counts says how many.", add:

```markdown
A line ending "call sites not searched; its briefing says so" names a
briefing whose call-site search did not finish: relay it as it is, since that
investigator saw no callers it could rely on.
```

- [ ] **Step 4: Run the tests.**

```bash
uv run --with pytest --with pyyaml --with lizard pytest tests/test_call_sites.py tests/test_pipeline.py -q
```

Expected: all pass, `test_bundles_are_within_budget_and_deterministic` included.

- [ ] **Step 5: Full suite and the sample** (the sample renders findings, not briefings, so it does not change):

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
uv run scripts/gen_sample_report.py --check; echo "exit=$?"
```

Expected: both `exit=0`.

- [ ] **Step 6: Commit**

```bash
git add scripts/bundle.py skills/thunderstruck-scan/SKILL.md tests/test_call_sites.py
git commit -m "Say when call sites were none or not searched (#66)"
```

### Task 3: The call-site tests on macOS in CI

**Satisfies:** AC-5, and AC-1 checked on macOS on every PR.

**Files:**
- Modify: `.github/workflows/ci.yml` (a new job after `sample-macos`)

- [ ] **Step 1: Add the job.** After the `sample-macos` job, at the same indentation:

```yaml
  call-sites-macos:
    # macOS's regex library has no \b under -E, so call sites came back empty
    # there for every file while Linux passed (#66). The full suite stays on Linux.
    name: call sites on macOS
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Call-site tests
        run: uv run --with pytest --with pyyaml --with lizard pytest tests/test_call_sites.py tests/test_signals_citable.py -v
```

- [ ] **Step 2: Check the workflow parses.**

```bash
uv run --with pyyaml python -c "import yaml; jobs = yaml.safe_load(open('.github/workflows/ci.yml'))['jobs']; assert jobs['call-sites-macos']['runs-on'] == 'macos-latest'; print(sorted(jobs))"
```

Expected: the job list, `call-sites-macos` included.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "Run the call-site tests on macOS in CI (#66)"
```

The job's first real run is on the PR. A red `call sites on macOS` there blocks the PR like any failing check.

### Task 4: Release

**Satisfies:** AC-6.

**Files:**
- Modify: `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`

- [ ] **Step 1: Version.** Bump the patch version in all four places to `<version>`: the next patch above `main`'s at the time. Read it from `pyproject.toml` on `origin/main`; for example, `0.10.0` becomes `0.10.1`.

- [ ] **Step 2: CHANGELOG.** Add above the previous top entry, with that version in the heading:

```markdown
## <version>

Call sites in briefings on macOS (#66).

### Fixed

- **Briefings list call sites on macOS.** The search passed `\b` to the platform's regex library, which macOS's does not support under `git grep -E`, so every macOS scan since 0.1.0 briefed its investigators without call sites. Symbols are now searched as fixed strings with git's own whole-word matching, identically on every platform.

### Changed

- **A briefing says when there are no call sites, or when they were not searched**, instead of leaving the section out. `bundle.py` prints one line per briefing whose search did not finish.
- **Some cached findings are investigated once more.** Briefings change for files that export symbols but have no callers (every platform), and on macOS for files that have callers; their findings were made without that context.
```

- [ ] **Step 3: Run every check.**

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
uv run scripts/gen_catalog_docs.py --check; echo "exit=$?"
uv run scripts/gen_sample_report.py --check; echo "exit=$?"
uv run scripts/validate_plugin.py; echo "exit=$?"
claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck && claude plugin list
```

Expected: every `exit=0` (`exit=2` from `validate_plugin.py` means `claude` is not on `PATH`: not run, never passed); `test_versions_agree` passes; `claude plugin list` shows thunderstruck `enabled`.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md .claude-plugin/plugin.json .claude-plugin/marketplace.json pyproject.toml
git commit -m "Call sites on macOS: release note (#66)"
```

## Acceptance criteria coverage

| AC | Tasks |
|---|---|
| AC-1 | 1 (the non-ASCII test and the fixture's call sites pass on macOS), 3 (checked on macOS in CI) |
| AC-2 | 1 (`test_callers_are_found_as_whole_words` red on macOS, `test_the_search_hands_git_no_pattern` red everywhere); the cause is in spec §0 |
| AC-3 | 2 |
| AC-4 | 1 (whole words, no-exports case; the loop's limits and filters untouched) |
| AC-5 | 3 |
| AC-6 | 4 |
