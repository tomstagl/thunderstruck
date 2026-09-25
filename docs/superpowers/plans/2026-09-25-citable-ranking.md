# Citable Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The files the scan ranks are exactly the files a finding can cite, and every ranked file is briefed with its own history only.

**Architecture:** `signals.py` reads history and the index with `-z`, so names arrive exactly as git stores them. The working-tree rule the validator applies moves into `_common`, and both the validator and the ranking call it. `bundle.py` looks up a hotspot's history by its literal name.

**Spec:** `docs/superpowers/specs/2026-09-25-citable-ranking-design.md` (§n below refers to it). Requirements AC-1…AC-5 are in GitHub issue #30.

**Branch:** `feat/citable-ranking`. One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

### Task 0: Record the baseline (AC-3)

**Files:** none committed. Output goes to the scratchpad and, in the end, the PR description.

- [x] On `main`, before any change, build the fixture and scan it and this repository:

```bash
B=$SCRATCH/baseline; mkdir -p $B
python3 tests/fixtures/build_fixture.py $B/fx
for R in $B/fx "$PWD"; do
  uv run --with pyyaml --with lizard scripts/signals.py --repo "$R" --top 10 --since 24m
  uv run --with pyyaml --with lizard scripts/bundle.py --repo "$R"
done
python3 - "$B/fx" "$PWD" > $B/before.txt <<'EOF'
import hashlib, json, sys
from pathlib import Path
for root in map(Path, sys.argv[1:]):
    out = root / ".thunderstruck"
    hs = json.loads((out / "hotspots.json").read_text())
    hs.pop("generated_at"); hs["counts"].pop("files_not_citable", None)
    print(root.name, hashlib.sha256(json.dumps(hs, sort_keys=True).encode()).hexdigest())
    for b in sorted((out / "bundles").glob("H*.md")):
        print(" ", b.name, hashlib.sha256(b.read_bytes()).hexdigest())
EOF
```

  Keep `$B/fx` for Task 4 so both runs see the same fixture commits.

### Task 1: Read history with exact file names (AC-2, AC-3)

**Files:** `scripts/_common.py`, `scripts/signals.py`; new `tests/test_signals_citable.py`.

- [x] Write failing unit tests for the parser (spec §8, "History parser"). Stub `c.git_paths` with `monkeypatch` and feed hand-built `-z` output:

```python
RS = signals._RECORD_SEP

def _record(sha, subject, *entries):
    return f"{RS}{sha}\x00t\x002026-09-01T00:00:00+00:00\x00{subject}\n" + "".join(entries) + "\x00"

def _change(path, adds=1, dels=0):
    return f"{adds}\t{dels}\t{path}\0"

def _rename(old, new):
    return f"0\t0\t\0{old}\0{new}\0"

def test_history_reads_names_exactly(monkeypatch):
    raw = (_record("b" * 40, "mv", _rename("src/módulo/a.ts", "src/módulo/b.ts"))
           + _record("a" * 40, "fix: one", _change("src/módulo/a.ts"),
                     _change('src/q"t.ts'), _change("src/tab\there.ts"),
                     "-\t-\tsrc/blob.ts\0")
           + _record("c" * 40, "empty"))
    monkeypatch.setattr(c, "git_paths", lambda *a, **k: raw)
    h = signals.collect_history(Path("."), "2026-01-01", c.Filters(include_tests=True))
    per = h["per_file"]
    assert per["src/módulo/b.ts"]["commits"] == 1
    assert per["src/módulo/a.ts"]["commits"] == 1 and per["src/módulo/a.ts"]["fix_commits"] == 1
    assert {'src/q"t.ts', "src/tab\there.ts", "src/blob.ts"} <= set(per)
    assert per["src/blob.ts"]["insertions"] == 0
    assert h["total_commits"] == 3
```

- [x] Add `git_paths` to `_common.py`, next to `git` (spec §2):

```python
def git_paths(repo_root: Path, *args: str, timeout: int = 180) -> str:
    """git output that carries file names, decoded exactly.

    Bytes are decoded as UTF-8 with surrogateescape, so a name that isn't
    valid UTF-8 survives as a string instead of crashing the run.
    """
    proc = subprocess.run(["git", "-C", str(repo_root), *args],
                          capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise ThunderstruckError(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout.decode("utf-8", "surrogateescape")
```

- [x] In `signals.collect_history`, run `c.git_paths(repo, "log", f"--since={since}", "--numstat", "-z", "--no-merges", f"--pretty=format:{fmt}", "--", ".")`, and replace the body loop with the token walk:

```python
        touched: list[str] = []
        tokens = iter(body.split("\0"))
        for token in tokens:
            cols = token.split("\t", 2)          # a name may itself contain a tab
            if len(cols) != 3:
                continue
            adds, dels, path = cols
            if not path:                         # rename or copy: old, then new
                next(tokens, None)
                path = next(tokens, "")
            if not path or filters.excludes_path(path):
                continue
            touched.append(path)
            # … the per-file accounting below is unchanged
```

  The header split (`record.strip("\n")`, `partition("\n")`, `split("\x00")`) stays as it is. Delete `_unrename`.

- [x] Run the parser tests, then the full suite. `test_bundles_are_within_budget_and_deterministic` and `test_sample_report.py` must pass without regenerating anything.
- [x] Commit: `Read churn history with -z so file names arrive exactly as git stores them`.

### Task 2: Rank only citable files and count the rest (AC-1, AC-2, AC-4)

**Files:** `scripts/_common.py`, `scripts/validate.py`, `scripts/signals.py`, `tests/test_signals_citable.py`.

- [x] Write the repository fixture and failing tests (spec §8). A module-scoped fixture builds the repository with `isolated_git_env()` from `build_fixture`, and at least 20 commits so no churn warning muddies the `warnings` assertion:

```python
@pytest.fixture(scope="module")
def citable_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("citable") / "repo"
    sub = tmp_path_factory.mktemp("citable") / "sub"
    _init(sub); _write(sub / "x.ts", "export const x = 1;\n"); _commit(sub, "sub")
    _init(root)
    for n in range(20):
        _write(root / "src/plain.ts", _ts(n)); _write(root / "src/módulo/a.ts", _ts(n))
        _write(root / "src/[id].ts", _ts(n)); _write(root / "src/gone.ts", _ts(n))
        _commit(root, f"feat: step {n}")
    _write(root / "src/i.ts", _ts(99)); _commit(root, "feat: only i")
    _git(root, "mv", "src/módulo/a.ts", "src/módulo/b.ts"); _commit(root, "refactor: rename")
    (root / "src/link.ts").symlink_to("plain.ts"); _commit(root, "feat: link")
    _git(root, "-c", "protocol.file.allow=always", "submodule", "add", str(sub), "libs/sub.ts")  # not vendor/: filtered
    _commit(root, "feat: vendor")
    if sys.platform.startswith("linux"):
        _write(root / os.fsdecode(b"src/\xff.ts"), _ts(1)); _commit(root, "feat: latin-1 name")
    (root / "src/gone.ts").unlink(); (root / "src/gone.ts").symlink_to("plain.ts")  # working tree only
    return root
```

  `_ts(n)` returns a small TypeScript function whose body varies with `n`. Run `signals.py --top 0 --since 24m` and `bundle.py` once in a second module fixture, and assert:

  - **success measure:** `{h["file"] for h in hotspots}` equals `{p for p, _ in c.tracked_index(repo).items() if p in changed and c.detect_language(p, langmap) and c.is_utf8(p) and Validator(...)._resolve(p)[2] is None}`, where `changed` is the `per_file` of `collect_history` on the same window;
  - **AC-1:** none of `src/link.ts`, `libs/sub.ts`, `src/gone.ts` is ranked;
  - **AC-2:** `src/módulo/b.ts` is ranked, and its `churn.commits` is 1: the rename commit. The 20 earlier commits stay with `src/módulo/a.ts`, since history doesn't follow renames;
  - **AC-4:** `counts.files_not_citable` is 4 on Linux and 3 elsewhere, and no entry of `warnings` mentions "citable", "symbolic" or "submodule".

- [x] Move the working-tree checks out of `Validator._resolve` into `_common.tracked_file_problem(repo_root, rel, mode)` (spec §3), with the messages copied verbatim and `_resolves_to_itself` moved alongside it. `_common` gains `import errno` and `import stat`. `_resolve` becomes:

```python
        elif (error := c.tracked_file_problem(self.repo, rel, mode)) is None:
            if (total := self._lines_in(rel)) is None:
                error = "could not be read"
```

  Run `tests/test_validate_paths.py` **unmodified**: it proves the move changed no behaviour.

- [x] In `signals.build`, replace the `ls-files` set and the candidate comprehension with the loop in spec §3, and add `"files_not_citable": not_citable` to `counts`. `is_utf8` lives in `_common`, since `bundle.py` needs it too (Task 3):

```python
def is_utf8(text: str) -> bool:
    """False for a name git stored in bytes that aren't UTF-8 (surrogate-escaped)."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True
```

- [x] Add the AC-3 fixture test to `tests/test_pipeline.py`: on `scanned_repo`, `counts.files_not_citable == 0` and the set of ranked files equals the nine files the fixture ranks today (spec §8):

```python
FIXTURE_FILES = {"src/client/releases.ts", "src/sync/collection.ts", "src/sync/scheduler.ts",
                 "src/client/artists.ts", "src/sync/queue.ts", "src/client/retry-wrapper.ts",
                 "src/client/api.ts", "src/client/limiter.ts", "src/util/format.ts"}
```

  `scanned_repo` runs with `--top 8`, so this test runs `signals.py --top 0` on a copy (`scanned_copy`) to see all nine.

- [x] Run the full suite, then commit: `Rank only files a finding can cite, and count the tracked entries skipped`.

### Task 3: Look up bundle history by exact file name (AC-5, AC-2, AC-3)

**Files:** `scripts/bundle.py`, `tests/test_signals_citable.py`.

- [x] Write failing tests on `citable_repo` (spec §8):
  - the bundle for `src/[id].ts` doesn't contain the subject `feat: only i`, and no diff header in it names `src/i.ts`;
  - the bundle for `src/módulo/b.ts` contains `diff --git a/src/módulo/b.ts` and no `\303`, and its callers section doesn't list `src/módulo/b.ts`.
- [x] In `section_history`, prefix both calls with the literal-pathspec option, and the `show` call also with unquoted names (spec §5):

```python
    log = c.git(repo, "--literal-pathspecs", "log", f"--since={since}", "-n", str(k), "--no-merges",
                "--pretty=format:%H%x00%aI%x00%an%x00%s", "--", rel, check=False)
    …
        diff = c.git(repo, "-c", "core.quotePath=false", "--literal-pathspecs", "show",
                     "--no-color", "--unified=3", "--format=", sha, "--", rel,
                     check=False, timeout=60)
```

  In `section_related`, the `git grep` call gains `"-c", "core.quotePath=false"` before `"grep"`, runs through `c.git_paths(..., check=False)` (which gains a `check` flag), and drops hit lines for which `c.is_utf8` is false (spec §5). Its `*.ts`… pathspecs stay globs.
- [x] Run the full suite. The determinism test and the sample check must pass unchanged. Commit: `Look up a hotspot's history by its exact file name`.

### Task 4: Prove rankings and bundles unchanged; changelog and version (AC-3)

**Files:** `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`.

- [x] Re-run Task 0's scan on the same `$B/fx` and on this repository, write `$B/after.txt` with the same script, and `diff $B/before.txt $B/after.txt`. It must be empty. Paste both into the PR description.
- [x] Run `uv run scripts/gen_sample_report.py --check` and `uv run scripts/gen_catalog_docs.py --check`. Both must pass with nothing regenerated.
- [x] Add a CHANGELOG entry under the next minor version (0.7.0 at the time of writing; use whatever follows the top heading when this lands):
  - **Fixed:** tracked symlinks and submodules no longer rank as hotspots; files with non-ASCII names are ranked; a file name containing glob characters such as `[id].ts` is briefed with its own history only; a non-UTF-8 file or author name no longer crashes ranking.
  - **Added:** `hotspots.json` `counts.files_not_citable`.
- [x] Bump the version in all four places (`test_versions_agree`).
- [x] Run the full suite, `claude plugin validate . --strict`, and install the plugin from this checkout (`claude plugin list` says "enabled"). Commit: `Record the citable-ranking fixes; bump to 0.7.0`.
- [ ] Tick the ticket's task checklist as each task merges.

## AC coverage

| AC | Tasks |
|---|---|
| AC-1 | 2 |
| AC-2 | 1 (names read exactly), 2 (ranked), 3 (briefed correctly) |
| AC-3 | 0 and 4 (by-hand comparison), 1–3 (determinism and sample checks on every commit), 2 (fixture set test) |
| AC-4 | 2 |
| AC-5 | 3 |
