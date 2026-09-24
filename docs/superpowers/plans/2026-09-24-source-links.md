# Source Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every resolved file:line, detector and commit ref in `report.md` becomes a web permalink pinned to the scanned commit, and `report.json` carries the same URLs.

**Architecture:** `scripts/links.py` is new and stdlib-only. It holds pure functions for parsing remotes and building URLs, plus `link_context()`, which contains every linking git call. `report.py` calls it once in `collect()` and writes URLs onto deep copies of the findings. The Markdown and JSON renderers both read those URLs. The scan, bundles, index and guardrail are unchanged.

**Tech Stack:** Python ≥ 3.11 stdlib, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-24-source-links-design.md` (§n below refers to it). Requirements AC-1…AC-10 are in GitHub issue #22.

**Branch:** `feat/source-links`. Each task ends in one commit. Tick the task in the issue's *Implementation progress* when it merges.

## Global constraints

- `links.py`: stdlib only. Git calls go only through `_common.git(..., timeout=30)`, and only inside `link_context`.
- No behaviour change in `signals.py`, `bundle.py`, `validate.py`, `guardrail.py`, the investigator prompt or `index.json`. The one exception is a pure refactor: `validate.py` calls the new `_common.ref_path` helper instead of an inline `.lstrip("./")`.
- A URL is built only from git, the profile and a resolved ref. A `url` in a finding JSON is overwritten.
- `report.py` never fails because of linking (spec §6, *Failure handling*).
- The full suite passes on **every** commit: `uv run --with pytest --with pyyaml --with lizard pytest tests/ -q`.
- Commits are imperative sentences in the repo's style and end with the session's attribution trailer.

---

### Task 1: Pure URL building (AC-1, AC-4)

**Files:** create `scripts/links.py` and `tests/test_links.py`; modify `scripts/_common.py` (`ref_path`) and `scripts/validate.py` (use `ref_path`).

- [x] **Step 1:** Write table-driven failing tests for the pure part of spec §10: `parse_remote`, `detect_provider`, `encode_path` (after `ref_path`), `LinkContext.code` for range, single line and whole file, `?plain=1`, `LinkContext.commit`, template fill in a single pass, the whole-file template cut, and `parse_lines`. Include the cases `"C:\\repos\\x"`, `"https://github.com/"`, `"https://github.com:bad/x"`, `"../x"`, a base with braces, `"../src/x.ts"` → `src/x.ts`, and `" 16 - 28 "` / `"L16"` / `"16–28"` / `"28-16"`.
- [x] **Step 2:** Run `pytest tests/test_links.py -q` and confirm the failures.
- [x] **Step 3:** Implement:
  - `Remote`, `parse_remote`, `detect_provider`, `encode_path`, `parse_lines(value, total) -> (start, end) | None`;
  - `TEMPLATES`, `PLAIN_EXTS`, `_fill` (one `re.sub` with a mapping), `template_error`;
  - `LinkContext` with `for_provider`, `for_templates`, `code(path, start=None, end=None)` and `commit(full_sha)`.

  `code` returns `None` for a path in `unlinked`. Add `_common.ref_path(p) = str(p).lstrip("./")`, and have `validate.py` use it in both of its call sites.
- [x] **Step 4:** Run `pytest tests/test_links.py tests/test_pipeline.py -q` and confirm they pass.
- [x] **Step 5:** Commit: `Parse git remotes and build permalinks for GitHub, GitLab and Bitbucket`.

### Task 2: Config and link context (AC-3, AC-5, AC-6, AC-7)

**Files:** modify `scripts/links.py` and `tests/test_links.py`.

- [x] **Step 1:** Write failing tests:
  - every `config_from_profile` failure in spec §2 gives `(None, [one warning naming the key])`;
  - `enabled = false` gives `(None, [])`;
  - `link_context` against tiny `tmp_path` git repos covers every git case in spec §10: remote selection; unrecognised host; modified, staged, committed-after-scan, untracked, ignored, symlink and `[id].ts` paths; commit expansion and a bad token; push state for the scanned SHA and for a cited commit; the `base_url`-only skip of the push check; a git failure (a non-repo directory) → one "references are not linked" warning.

  A helper `_repo(tmp_path, remote=...)` runs `git init -q`, makes one commit and sets `refs/remotes/origin/main`.
- [x] **Step 2:** Run the tests and confirm they fail.
- [x] **Step 3:** Implement `LinkConfig`, `config_from_profile(profile)` and
  `link_context(repo, profile, scanned_sha, cited_paths, cited_commits) -> LinkResult(ctx, commits, warnings)`, following spec §3 and §6.

  Catch `ThunderstruckError`, `subprocess.TimeoutExpired` and `OSError` around the git block. Run `ls-tree`/`diff` with `--literal-pathspecs` as the global option before the subcommand (`c.git(repo, "--literal-pathspecs", "ls-tree", …)`).
- [x] **Step 4:** Run `pytest tests/test_links.py -q` and confirm it passes.
- [x] **Step 5:** Commit: `Resolve the link base, stale files, commit ids and push state for report links`.

### Task 3: Linked refs in report.md (AC-1, AC-2, AC-5, AC-6)

**Files:**
- modify `scripts/report.py`; create `tests/test_report_links.py` (reuses the helpers in `tests/test_pipeline.py`);
- modify `tests/fixtures/build_fixture.py`: add `add_remote(repo, url, tracking=True)`, which runs `git remote add` and, when `tracking` is set, `git update-ref refs/remotes/<name>/main HEAD`;
- modify `tests/conftest.py`: add a `linked_copy` fixture that runs `add_remote` on `scanned_copy`.

- [x] **Step 1:** Write the failing pipeline tests from spec §10. On `linked_copy`, write `_valid_finding` with `_write_finding`, then `_validate` and render. Assert that:
  - the location line matches `\*\* · \[`…`\]\(https://github.com/acme/fixture/blob/<head>/`;
  - the `_code_` and `_detector_` lines link to the same base;
  - the `_commit_` line is ``[`<7 hex>`](…/commit/<40 hex>)``;
  - a commit ref `"<sha> subject"` renders the subject after the link;
  - `catalog` stays plain (on `context_scanned_copy` plus `add_remote`).

  Negative cases:
  - no remote → plain refs and a warning;
  - `enabled = false` → no link warning;
  - `location.lines = "L16"` → a whole-file link;
  - a token-bearing remote → neither `ghs_SECRET` nor `bob` appears in `report.md` or `report.json`;
  - a cited file edited after validation → unlinked and named.
- [x] **Step 2:** Run the tests and confirm they fail.
- [x] **Step 3:** Implement in `report.py`:
  - `collect()` deep-copies each finding;
  - `_link_refs(data, repo)` gathers the cited paths (location files plus `code`/`detector` ref paths via `validate.CODE_REF`/`DETECTOR_REF` and `c.ref_path`) and the commit tokens (`ref.split()[0]`), then calls `link_context` inside a broad `try` that turns any exception into a warning;
  - it sets `location["url"]` and each `ev["url"]` (or `None`), and stores `data["links"]` and `data["link_warnings"]`;
  - `render_markdown` renders from those `url`s. The commit text is ``[`sha7`](url)`` followed by `` `rest` `` when the ref has one;
  - `link_warnings` is added to *Run warnings*.
- [x] **Step 4:** Run the full suite and confirm it passes.
- [x] **Step 5:** Commit: `Link finding locations and evidence refs to permalinks at the scanned commit`.

### Task 4: URLs in report.json (AC-8)

**Files:** modify `scripts/report.py` and `tests/test_report_links.py`.

> Tasks 3 and 4 touch the same functions and landed as one commit.

- [x] **Step 1:** Write failing tests:
  - `report.json` has a `links` object (`provider`, `base_url`, `sha`, `remote`), `location.url` and every `evidence[].url`, with `null` for catalog;
  - `warnings` ends with the link warnings;
  - with no remote, `links` is `null` and every `url` is `null`;
  - `index.json` contains no `"url"`;
  - the findings files are byte-identical before and after `report.py`.
- [x] **Step 2:** Implement in `render_json`. **Step 3:** Run the full suite.
- [x] **Step 4:** Commit: `Carry permalinks in report.json`.

### Task 5: Sample report, docs, version (AC-9, AC-10)

**Files:**
- `scripts/gen_sample_report.py`: after the fixture is built and **before** `signals.py` runs, call `add_remote(repo, "https://github.example.com/acme/fixture.git")` and **append** `[links]\nprovider = "github"\n` to the untracked `.thunderstruck.toml` that `add_service_context` wrote. Do not overwrite `[context]`, and keep the file untracked so the pinned SHAs don't change. Add a sentence to the header comment saying the links point at a placeholder host.
- `examples/sample-report.md`: regenerate it.
- `tests/test_docs_in_sync.py`: add `test_sample_report_links_its_refs`.
- `README.md`: add a `### Source links` subsection under *Per-repository profiles* (the `[links]` table and a short degradation list), and one sentence in *Privacy* saying the report names the remote's web base.
- `examples/thunderstruck.toml.example`: add a commented `[links]` block.
- Version `0.4.0` in `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `pyproject.toml`.

- [x] **Step 1:** Write `test_sample_report_links_its_refs`. It fails against the current sample.
- [x] **Step 2:** Update the generator and run `uv run scripts/gen_sample_report.py`. Review the diff: only the ref formatting, the header comment and the scan date may change.
- [x] **Step 3:** Update the docs, the example profile and the version, and add the CHANGELOG entry.
- [x] **Step 4:** Verify:

```bash
uv run --with pytest --with pyyaml --with lizard pytest tests/ -q
uv run scripts/gen_catalog_docs.py --check
claude plugin validate . --strict
```

Then scan this repository (its remote is on github.com), open three links from its `report.md`, and check that each lands on the cited line.
- [x] **Step 5:** Commit: `Show permalinks in the sample report and document [links]; bump to 0.4.0`.

---

## AC coverage

| AC | Tasks |
|---|---|
| AC-1 | 1, 3 |
| AC-2 | 3 |
| AC-3 | 2 |
| AC-4 | 1, 3 |
| AC-5 | 2, 3 |
| AC-6 | 2, 3 |
| AC-7 | 2 |
| AC-8 | 4 |
| AC-9 | 5 (determinism test unchanged throughout) |
| AC-10 | 5 |
