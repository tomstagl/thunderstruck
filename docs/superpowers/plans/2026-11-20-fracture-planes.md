# Fracture planes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add *planes*: stack-specific rubrics selected by a script, embedded in bundles and skeptic briefs, with a CI gate that fails when a plane × pattern cell is undeclared.

**Architecture:** A plane is `planes/<id>/{plane.yaml,rubric.md}`. `scripts/fracture_planes.py` loads and checks them and selects the active ones from the tracked-file index; `signals.py` records the selection in `hotspots.json`; `bundle.py` and `verify.py` embed the matching rubric sections, so both hashes cover them. The model applies the text and never chooses it.

**Tech Stack:** Python 3.11 stdlib, pyyaml (deferred import, as `_common.load_catalog`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-20-fracture-planes-design.md`
**Ticket:** #112. Tasks name the `AC-n` they satisfy; the criteria are in the parent ticket.
**Branch:** `feat/112-fracture-planes`, built in an interactive session while #112 carries `agent:in-progress`. Not `agent/112-…`: the nightly picker resumes a draft PR on such a branch (never push to `main`).

| Subticket | Tasks |
|---|---|
| #113 — definitions and coverage | 1–3 |
| #114 — selection and investigator guidance | 4–5 |
| #115 — skeptic guidance and reuse | 6–7 |
| #116 — report, Spring seed and release documentation | 8–10 |

Tasks 0 and 11 belong to #112. These are tracking subtickets, not separate nightly jobs. Use Superpowers red–green–refactor for each slice: run the new focused tests before writing implementation and confirm the red result is for the missing behavior. After each slice, record its focused result, review, commits and next step or blocker in a progress comment on #112. Stay on the implementation branch, fetch and sync `origin/main` at each slice boundary and before Task 11, following the nightly skill's conflict rules. Do not edit the parent issue body while implementing. Subtickets are done on the branch once their changes pass focused tests and are integrated; don't wait for GitHub issue closure to run Task 11.

## Global Constraints

- Word is **plane**, never "profile" (`.thunderstruck.toml` owns that word).
- `scripts/guardrail.py` stays stdlib-only and never imports `fracture_planes.py`.
- Bundles stay byte-identical across runs; with no active plane they are byte-identical to today's. No timestamp, absolute path or other volatile value in plane text or in the section it produces.
- `validate.py` and `VALIDATION_RULES` are not changed: a finding still needs `code` evidence.
- Plane text is plugin content. Nothing in the scanned repository can add or alter a plane.
- A plane that fails to load at run time is skipped and named in `warnings`; it never fails a scan.
- Selection reads at most `MAX_READ_BYTES = 65536` bytes of a file and examines at most `MAX_RULE_FILES = 25` files per rule.
- Section limits: a pattern section ≤ 700 characters, `## General` ≤ 800; no ATX heading, setext underline or code fence (backtick or tilde) inside a body. Bundle cap for the section: 12% of the bundle budget, applied by omitting whole sections. The plane section joins `service`, `observed` and `kept` in `build_bundle`'s existing `fixed = sum(c.estimate_tokens(p) for p in (...) if p)`; `rest = max(budget - fixed, budget // 2) if fixed else budget` is unchanged (`estimate_tokens("")` is 1, so the `if p` guard stays).
- `load_planes(directory=None)` takes the planes directory itself (default: the module function `planes_dir()`, called through the module global so a monkeypatch of `fracture_planes.planes_dir` works; the parameter is deliberately not named `planes_dir`); `check_planes(..., repo_root=None)` takes the plugin root for `docs/calibration/planes/`. Run-time tests inject a directory by monkeypatching `fracture_planes.planes_dir` and call `signals.build`, `bundle.main` and `verify.prepare` in-process.
- Everything reading `hotspots.json["planes"]` uses `.get("planes") or []`.
- Languages are compared after `_common.detector_language(catalog, lang)` on both sides; a plane's `languages` may not contain an alias key.
- Every `scripts/*.py` carries a module docstring (`test_every_script_has_a_docstring`), including `fracture_planes.py` and `gen_plane_docs.py`.
- Versions agree across `plugin.json`, `marketplace.json`, `pyproject.toml` and the top `CHANGELOG.md` heading. The planned next minor is `0.21.0` from `0.20.0`; recheck current `main` in Task 10.
- Stage explicit paths in every commit, new files included, also where a step below says `git commit -am`. Never `git add tests/` or another directory.
- Test command: `uv run --with pytest --with pyyaml --with lizard --with packaging --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q`. Below, `PYTEST` means `uv run --with pytest --with pyyaml --with lizard pytest`.

## Review Focus

Input classes the spec implies and no task's happy path exercises, most likely first. Each has its test in the task named.

1. A hotspot whose language no active plane covers (a `.py` file in a repo with `java-spring` active) gets no section and the same bytes as before. Task 5.
2. A `rubric.md` with CRLF line endings or a trailing section without a final newline parses the same as LF. Task 1.
3. Two planes both active and both with a section for one pattern: both are shown, in id order, identically on every run. Task 5.
4. A tracked `pom.xml` that is binary, huge, or not UTF-8 neither crashes selection nor matches by accident. Task 4.
5. `supersedes` naming a plane that is not installed, or forming a cycle, is a load problem that skips the plane at build and at run time, never a crash. Tasks 1 and 4.
6. A `.js` hotspot with a `typescript` plane active gets guidance, and a plane keyed `javascript` is a gate failure. Tasks 5 and 2.
7. A plane edited after `signals.py` ran is skipped with a warning, not embedded under a stale `rubric_hash`. Tasks 5 and 6.

---

## File structure

| File | Responsibility |
|---|---|
| `scripts/fracture_planes.py` (create) | Load, check, select and render planes. One module, stdlib + `_common`. |
| `scripts/gen_plane_docs.py` (create) | Render the matrix to `skills/stability-catalog/references/planes.md`; `--check`. |
| `planes/java-spring/{plane.yaml,rubric.md}` (create) | The seed plane. |
| `scripts/signals.py`, `scripts/bundle.py`, `scripts/verify.py`, `scripts/report.py` (modify) | Record, embed, embed, show. |
| `examples/sample-report.{md,html}` (regenerate) | `report.json` gains `planes`, and the HTML embeds the whole report. Generated; never hand-edited. |
| `agents/thunderstruck-{investigator,skeptic}.md` (modify) | Say what plane guidance is. |
| `tests/test_planes.py`, `tests/planes/fixtures/**` (create) | Loader, gate, selection, rendering. |

---

### Task 0: Preconditions

**Files:** none.

- [ ] **Step 1:** Confirm the ticket is filed, titled without "DRAFT", and that its AC numbers match the `AC-n` named below; confirm the spec and this plan both refer to #112. If the ticket's criteria differ, change the ticket or spec first, not this plan.
- [ ] **Step 2:** Run the full test command and `uv run scripts/validate_plugin.py` on a clean `main`. Expected: all pass. Record the test count; Task 11 compares against it.

---

### Task 1: The plane manifest and its loader (AC-1)

**Files:**
- Create: `scripts/fracture_planes.py`
- Create: `tests/test_planes.py`, `tests/planes/fixtures/good/{plane.yaml,rubric.md}`, and one fixture directory per failure listed in Step 1 under `tests/planes/fixtures/bad-<rule>/`.

**Interfaces:**
- Produces, in `scripts/fracture_planes.py`:
  `PLANE_SCHEMA = "thunderstruck.plane/v1"`, `MATURITIES = ("seed", "calibrated")`, `MAX_RULE_FILES = 25`, `MAX_READ_BYTES = 65536`.
  `@dataclass(frozen=True) class DetectRule: file: str; contains: str | None`.
  `@dataclass(frozen=True) class RubricEntry: pattern_id: str; text: str` (`text` is the section body, stripped, LF-normalised).
  `@dataclass(frozen=True) class Plane: id: str; title: str; maturity: str; languages: tuple[str, ...]; detect: tuple[DetectRule, ...]; supersedes: tuple[str, ...]; cells: dict[str, dict[str, str]]; rubric: dict[str, RubricEntry]; general: str; rubric_hash: str`.
  `planes_dir() -> Path` (`plugin_root() / "planes"`).
  `load_planes(directory: Path | None = None) -> tuple[dict[str, Plane], list[str]]`: a missing directory returns `({}, [])`; never raises for one bad plane; returns the planes that loaded and one problem string per failure, formatted `planes/<id>/<file>: <problem>`.
- `rubric_hash` is `_common.sha256_text(title + "\n" + rubric.md text)` after LF normalisation: it covers exactly what is embedded, so editing a `cells` entry or `maturity` changes nothing downstream.

- [ ] **Step 1: Write the failing tests** in `tests/test_planes.py`, one per name:
  - `test_a_good_plane_loads_with_every_field` — `load_planes(plugin_root / "tests" / "planes" / "fixtures")` (the `plugin_root` fixture) gives `planes["good"]` with `maturity == "seed"`, `languages == ("java",)`, a `rubric["S01"].text` that starts with `**Counts as protection.**`, a non-empty `general`, and `rubric_hash` starting `sha256:`.
  - `test_each_malformed_plane_reports_its_file_and_problem` — parametrised over the `bad-*` fixtures; each returns a problem that starts `planes/<dir>/` and contains the quoted problem text: `bad-schema` (wrong `schema`), `bad-id` (`id` differs from the directory), `bad-maturity`, `bad-yaml` (unparseable), `bad-no-rubric` (no `rubric.md`), `bad-detect` (a rule with neither `file` nor valid shape), `bad-cell` (a `cells` entry that is neither `na` nor `planned`, or has an empty reason), `bad-heading` (a rubric with `## S01 — Timeouts`), `bad-supersedes-unknown` (a plane naming an uninstalled plane) and the pair `bad-supersedes-cycle-a` / `bad-supersedes-cycle-b` (each naming the other; the parametrised test expects a problem for each directory of the pair).
  - `test_a_hash_ignores_cells_and_maturity` — two fixture planes identical in title and rubric but with different `cells` and `maturity` share a `rubric_hash`.
  - `test_one_bad_plane_does_not_hide_the_good_ones` — `good` is still in the result when a `bad-*` sibling fails.
  - `test_crlf_rubric_parses_like_lf` — a `crlf` fixture yields the same `RubricEntry.text` and `rubric_hash` as its LF twin `lf`.
- [ ] **Step 2:** Run `PYTEST tests/test_planes.py -q`. Expected: FAIL, `ModuleNotFoundError: fracture_planes`.
- [ ] **Step 3:** Implement the dataclasses and `load_planes` in `scripts/fracture_planes.py`. Parse `rubric.md` by splitting on lines that match `^## (General|S\d+)\s*$`; `## General` fills `Plane.general`, each `## S<digits>` a `RubricEntry`. Any other line beginning `## ` is a load problem, `planes/<id>/rubric.md: unrecognised heading '<text>'`, so `## S01 — Timeouts` can never be swallowed into the section above it. Import yaml inside the function, as `_common.load_catalog` does.
- [ ] **Step 4:** Run `PYTEST tests/test_planes.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `git add <each changed file> && git commit -m "Planes: the manifest and its loader (#112)"`.

---

### Task 2: The completeness gate (AC-2)

**Files:**
- Modify: `scripts/fracture_planes.py`
- Test: `tests/test_planes.py`, more fixtures under `tests/planes/fixtures/`

**Interfaces:**
- Consumes: Task 1's `Plane`, `load_planes`; `_common.load_catalog` (the `patterns` list, `languages` dict, `tier` field).
- Produces: `cell_state(plane: Plane, pattern_id: str) -> str` returning `"rubric" | "na" | "planned" | "missing"`.
  `check_planes(planes: dict[str, Plane], catalog: dict, repo_root: Path | None = None) -> list[str]`: one problem string per rule broken, `[]` when clean. Fixture planes are checked against a small stub catalog passed in by the test, so a fixture built to break one rule does not also report `missing` for every real pattern. The rules are spec §2.2: a `missing` cell for any Tier A/B pattern; a pattern both in `rubric` and `cells`; a rubric or `cells` ID that is not a Tier A/B pattern; a section lacking `**Counts as protection.**` or `**Does not count.**`; a section over 700 characters or `general` over 800; a body matching any of `^\s{0,3}#{1,6}(\s|$)`, `^\s{0,3}(=+|-+)\s*$` or `^\s{0,3}(`{3,}|~{3,})` (multiline), one test each, including a `####` heading; `calibrated` with a `planned` cell or without `docs/calibration/planes/<id>.md` containing `Repository:`, `Commit:` and `n:`; a `supersedes` id that is unknown or part of a cycle, which is a **load** rule: `load_planes` reports it and skips the plane, so it is tested through Task 1's fixtures and `check_planes` never sees such a plane; a `languages` entry absent from `catalog["languages"]` or present as a key of `catalog["aliases"]`.

- [ ] **Step 1: Write the failing tests:**
  - `test_cell_state_covers_all_four_states` — against `good` plus a pattern it declares `na`, one `planned`, and one it does not mention.
  - `test_the_gate_names_each_missing_cell` — a plane covering only `S01` produces a problem for `S02` that contains `planes/<id>` and `S02`.
  - One test per remaining rule, using a fixture plane built to break only that rule, asserting the problem text contains the plane id and the offending pattern or id: `test_both_rubric_and_cell_is_a_problem`, `test_unknown_pattern_id_is_a_problem` (a Tier C id such as `S20` counts as unknown), `test_section_without_the_two_labels_is_a_problem`, `test_oversized_sections_are_a_problem`, `test_calibrated_needs_no_planned_cells_and_a_ledger`, `test_language_not_in_the_catalog_or_an_alias_key_is_a_problem` (Review Focus 6), `test_a_body_with_a_heading_or_a_fence_is_a_problem`.
  - `test_the_real_planes_pass_the_gate` — `planes, problems = load_planes(); assert problems == []; assert check_planes(planes, catalog) == []`, over the repository's own `planes/`. (This fails nothing until Task 9 adds a plane; it must pass vacuously when `planes/` is absent.)
- [ ] **Step 2:** Run `PYTEST tests/test_planes.py -q`. Expected: the new tests FAIL, `AttributeError: cell_state`.
- [ ] **Step 3:** Implement `cell_state` and `check_planes`. Tier A/B IDs come from `catalog["patterns"]` where `str(tier).upper()` is `A` or `B`. Keep unknown and cyclic `supersedes` checks in Task 1's loader.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -am "Planes: the completeness gate (#112)"` (add new fixtures first).

---

### Task 3: The generated matrix and the CI check (AC-7)

**Files:**
- Create: `scripts/gen_plane_docs.py` (with PEP 723 metadata, `requires-python = ">=3.11"`, `dependencies = ["pyyaml>=6.0"]`, as `gen_catalog_docs.py`), `skills/stability-catalog/references/planes.md` (generated, never hand-edited)
- Modify: `tests/test_docs_in_sync.py`, `.github/workflows/ci.yml`, `tests/test_plugin_paths.py` (add the generated `planes.md` to `GENERATED`, so it is not checked as hand-written content). `scripts/gen_catalog_docs.py` is **not** changed.

**Interfaces:**
- Consumes: `fracture_planes.load_planes`, `fracture_planes.cell_state`, `_common.load_catalog`.
- Produces: `render(planes: dict[str, Plane], catalog: dict) -> str` in `gen_plane_docs.py`. A banner as in `gen_catalog_docs.py` (`<!-- Generated from planes/ by scripts/gen_plane_docs.py. Do not edit by hand. -->`), a table with one row per plane and one column per Tier A/B pattern whose cell reads `R`, `n/a`, `planned` or `MISSING`, each with ` D` appended when the catalog has a detector for any of the plane's languages for that pattern; below it, per plane: title, maturity, languages, the `detect` rules, and each `na`/`planned` reason. With no planes, a single sentence saying none are installed. CLI: no argument writes the file, `--check` exits 1 when stale.

- [ ] **Step 1: Write the failing tests** in `tests/test_docs_in_sync.py`:
  - `test_plane_matrix_is_regenerated` — runs `gen_plane_docs.py --check`, asserts return code 0 with the same message style as `test_patterns_reference_is_regenerated`.
  - In `tests/test_planes.py`: `test_render_marks_each_cell_state_and_detector` — rendering the `good` fixture plane with a stub catalog yields the strings `R D`, `n/a`, `planned`, `MISSING` in the cells you construct; and `test_render_is_deterministic_and_has_no_path_or_date` — two renders are equal and the output contains no `/Users`, no `/tmp` and no four-digit year.
- [ ] **Step 2:** Run both. Expected: FAIL, script missing.
- [ ] **Step 3:** Implement `render` and the CLI. Mirror `gen_catalog_docs.py`'s structure and `--check`. Run `uv run scripts/gen_plane_docs.py` to produce the file.
- [ ] **Step 4:** Add a CI step after "Generated docs are in sync": `Plane matrix is in sync`, running `uv run --python ${{ matrix.python }} scripts/gen_plane_docs.py --check`.
- [ ] **Step 5:** Run both tests. Expected: PASS. Commit: `git add <each changed file> && git commit -m "Planes: a generated matrix, checked in CI (#112)"`.

---

### Task 4: Deterministic selection (AC-3)

**Files:**
- Modify: `scripts/fracture_planes.py`, `scripts/signals.py`
- Test: `tests/test_planes.py`, `tests/test_pipeline.py` (one assertion on `hotspots.json`)

**Interfaces:**
- Consumes: `Plane`, `DetectRule`, `load_planes`; in `signals.py`, the `index = c.tracked_index(repo)` already built, and `warnings`.
- Produces: `@dataclass(frozen=True) class Selected: plane_id: str; matched_by: str; rubric_hash: str`.
  `glob_to_regex(pattern: str) -> re.Pattern[str]` (separate from `_common._glob_to_re`, which has no `**/`): `*` matches within a path segment, `**/` spans zero or more directories, everything else is literal.
  `head_reader(repo: Path) -> Callable[[str], str | None]`: returns the first `MAX_READ_BYTES` bytes decoded as UTF-8 with `errors="replace"`, or `None` on `OSError` or `ValueError` (a path from `tracked_index` can carry a surrogate-escaped byte; `open` then raises `FileNotFoundError` or `UnicodeEncodeError`).
  `select(index: Iterable[str], read: Callable[[str], str | None], planes: dict[str, Plane], usable: Callable[[str], bool] = lambda p: True) -> tuple[list[Selected], list[str]]`: the selection sorted by `plane_id`, and warnings. A rule examines at most `MAX_RULE_FILES` matching paths in `(depth, path)` order; when it had more candidates a warning `plane <id>: rule <file> had N candidates, examined 25` is returned. `matched_by` is the first path that matched. A plane named in another active plane's `supersedes` is dropped. `select` applies `usable(path)` only to paths that already match a rule's `file` glob, so the per-path `lstat` is not spent on the whole index. `signals.py` passes `usable = lambda p: plane_usable(repo, p, index[p], filters)`, with `signals.plane_usable(repo: Path, rel: str, mode: str, filters) -> bool` being `c.is_utf8(rel) and not c.path_problem(rel) and c.tracked_file_problem(repo, rel, mode) is None and filters.exclusion_reason(rel) in (None, "path")`: the `--path` restriction must not hide a repository-root manifest.
  `hotspots.json` gains `"planes": [{"id", "matched_by", "rubric_hash"}]`, sorted by id; always present, `[]` when none.

- [ ] **Step 1: Write the failing tests:**
  - `test_glob_star_stays_in_a_segment_and_double_star_spans` — `**/pom.xml` matches `pom.xml` and `a/b/pom.xml`; `*.xml` does not match `a/pom.xml`; `a.b` is literal (the dot is not a wildcard).
  - `test_select_matches_on_contains_and_reports_the_first_path` — two `pom.xml` files, the second containing `spring-boot`; `matched_by` is that second path.
  - `test_select_is_independent_of_index_order` — the same index shuffled gives the same result.
  - `test_rule_examines_at_most_25_files` — 30 matching files with the marker only in the 26th: no match.
  - `test_unreadable_binary_and_huge_files` — a reader returning `None`, a path containing a lone surrogate (`"a\udcffb/pom.xml"`), one returning bytes decoded with replacement characters, and a marker placed after byte 65536 each do not match and do not raise. (Review Focus 4.)
  - `test_supersedes_drops_the_superseded_plane`.
  - `test_a_pom_under_a_test_directory_does_not_activate_a_plane` — at the `signals.build` level, on a fixture with `src/test/resources/pom.xml` containing `spring-boot`.
  - `test_a_root_manifest_activates_a_plane_when_only_a_subdirectory_is_scanned` — build the repository with `build_fixture.build(dest)`, add and commit `pom.xml` and `services/foo/App.java` through the helper's git environment, call `signals.build(argparse.Namespace(repo=..., top=10, since="24m", path="services/foo", include_tests=False, dormant=0, dormant_limit=0))` in-process (no existing test does; the Namespace fields are those `build` reads), with `--path services/foo` and a root `pom.xml` containing `spring-boot`.
  - `test_a_path_that_is_not_utf8_is_not_usable` — `signals.plane_usable` with `c.tracked_file_problem` monkeypatched to return `None` (macOS cannot hold such a file, so only this makes the test fail first everywhere): `"a\udcffb/pom.xml"` is `False`, `"a/pom.xml"` is `True`.
  - `test_usable_is_only_called_for_paths_that_match_a_rule`, `test_a_symlink_named_pom_xml_is_not_opened` and `test_a_root_manifest_sorts_before_a_deep_one`.
  - `test_a_truncated_rule_warns` — the 30-file case returns the warning text above.
  - In `tests/test_pipeline.py`: `test_hotspots_json_records_planes_even_when_none` — the fixture repo's `hotspots.json["planes"] == []`.
  - `test_a_broken_plane_is_skipped_with_a_warning_and_the_scan_continues` — monkeypatch `fracture_planes.planes_dir` to a directory holding `good` and `bad-yaml`; `signals.build` returns a payload, `warnings` has `plane skipped: planes/bad-yaml/…`, and `good` is selectable (spec §5, Review Focus 5).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the functions. In `signals.py`, after the tracked index is built: `loaded, problems = fracture_planes.load_planes()`; append each problem to `warnings` as `plane skipped: <problem>`; `selected, sel_warnings = fracture_planes.select(index, fracture_planes.head_reader(repo), loaded, usable=usable)`; extend `warnings` with `sel_warnings`; write the selection into the payload. Import `fracture_planes` the way the other scripts import `_common`.
- [ ] **Step 4:** Run `PYTEST tests/test_planes.py tests/test_pipeline.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -am "Planes: deterministic selection recorded in hotspots.json (#112)"`.

---

### Task 5: Plane guidance in the bundle (AC-4)

**Files:**
- Modify: `scripts/fracture_planes.py`, `scripts/bundle.py`
- Test: `tests/test_planes.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Plane`, `Selected` ids from `data["planes"]`; `hs["language"]`, `hs["detector_hits"][i]["pattern_id"]`; `c.estimate_tokens`.
- Produces: `guidance(planes: dict[str, Plane], active_ids: Sequence[str], language: str, pattern_ids: Iterable[str], catalog: dict, cap_tokens: int | None = None, *, include_general: bool) -> str` (`None`: no cap, as the skeptic's brief) in `fracture_planes.py`. `language` and each plane's `languages` are compared after `_common.detector_language`. Returns `""` when no active plane covers the language or no section applies. Otherwise: the heading `## Plane guidance`, a one-paragraph preface (the maintainers' text about what counts as protection on this stack; not repository content; not evidence), then per plane in id order `### <id> — <title>`, a line `rubric <rubric_hash>`, the line ``full rubric: `.thunderstruck/planes/<id>.md` ``, its general text when `include_general`, and `#### <PatternID>` plus the section body for each requested pattern the plane has, in id order. No volatile values.
  `bundle.section_planes(hs: dict, data: dict, loaded: dict[str, Plane], catalog: dict, cap_tokens: int) -> str` calls `guidance` with the hotspot's language and lead pattern ids. `guidance` omits whole sections that do not fit (reverse id order) and ends with the line `Omitted to fit the budget: java-spring S10, S28.`; if the fixed lines and General alone exceed the cap, only the title, hash and rubric path remain
  `fracture_planes.write_plane_rubrics(dest: Path, loaded: dict[str, Plane], active_ids: Sequence[str]) -> list[Path]` (in `fracture_planes.py`, used by `bundle.py` and `verify.py`) writes `<dest>/planes/<id>.md` (the full rubric, LF) for each active plane.
  `build_bundle` gains an optional last parameter `loaded_planes: dict | None = None`, after `ctx` and `obs` and passed by keyword (`bundle.main` and `tests/test_lessons.py` call it positionally up to those); with `None` or no active plane it produces exactly today's bytes. The section sits after `section_detectors`; its cap is `int(budget * 0.12)`; the plane section is built before `rest` (the cap does not depend on `rest`), and `rest` follows the guarded rule in Global Constraints. `fracture_planes.resolve_active(loaded: dict[str, Plane], recorded: Sequence[dict]) -> tuple[list[str], list[str]]` is the one place stale-plane skipping happens: it returns the active ids (recorded entries whose plane is loaded and whose live `rubric_hash` equals the recorded one) and one warning per skipped plane. `section_planes`, `bundle.py:main` and `verify.prepare` all call it, and `write_plane_rubrics` is given its result, so no file is written for a plane that was skipped. `write_plane_rubrics` first removes what is at `<dest>/planes`: `shutil.rmtree` when `c.is_real_dir`, else `unlink` for a symlink or file (spec §4), never through a link. `data.get("planes") or []`; when the key is absent, `bundle.py:main` warns on stderr "hotspots.json records no planes (written before this version); re-run signals.py", as it does for `own_packages`. `build_bundle` and `bundle.py:main` take their active ids from `resolve_active`; `main` prints its warnings to stderr.

- [ ] **Step 1: Write the failing tests:**
  - `test_guidance_is_empty_for_a_language_no_active_plane_covers` — Review Focus 1: a `python` hotspot with only a `java` plane active returns `""`.
  - `test_guidance_lists_only_requested_patterns_in_id_order_with_general_first`.
  - `test_two_active_planes_both_shown_in_id_order` — Review Focus 3, and two calls return equal strings.
  - `test_a_bundle_with_no_active_plane_is_byte_identical` — with a synthetic `hs`/`data` built in the test (no git, no dates), `build_bundle(..., loaded_planes=None)` equals the same call with a loaded dict and `data["planes"] == []`, and equals a call where a plane is active but covers another language. No literal hash of a real fixture bundle: the pytest fixture's dates move with the calendar and `lizard` is unpinned, so it would fail tomorrow. `gen_sample_report.py --check` is the cross-version guard.
  - `test_a_js_hotspot_gets_guidance_from_a_typescript_plane` (Review Focus 6).
  - `test_a_rubric_edit_changes_the_bundle_of_every_hotspot_the_plane_covers_and_no_other` — two covered hotspots, one in another language; editing a section no hotspot has a lead on still changes the two covered bundles, not the third.
  - `test_the_cap_holds_at_every_budget_and_a_plane_that_cannot_fit_is_left_out_with_a_warning` — at `--budget 1000` the guidance is at most `int(1000 * 0.12)` tokens, or empty with the warning.
  - `test_whole_sections_are_omitted_to_fit_the_cap_and_the_omission_is_named` — with a small `cap_tokens` no section is cut mid-body and the closing line names exactly the dropped ids.
  - `test_with_neither_section_the_bundle_is_the_bytes_the_old_formula_gave` — on a synthetic hotspot, recompute the body with the pre-change expression (`fixed` over `service`, `observed` and `kept`; `rest = max(budget - fixed, budget // 2) if fixed else budget`) inline and assert byte equality with `build_bundle(..., loaded_planes=None)` and with a no-plane-covering load. This is the guard against today's output; it is not new-code-against-new-code.
  - `test_the_source_budget_shrinks_by_the_plane_share_and_the_floor_holds` — with a plane section and no service, observed or lessons section, `rest == budget - tokens(planes)`; with all four, `fixed` counts each once and the floor `budget // 2` holds.
  - `test_a_hotspots_json_without_a_planes_key_does_not_crash_bundle` (and warns).
  - `test_a_stale_plane_file_is_removed_on_the_next_bundle_run`.
  - `test_a_symlink_at_the_planes_directory_is_replaced_and_never_followed` — the link's target keeps its files and gains none.
  - `test_a_plane_edited_after_signals_is_skipped_with_a_warning` (Review Focus 7), `test_resolve_active_skips_unloaded_and_changed_planes_and_names_them`, `test_a_broken_plane_does_not_stop_bundle_main` (monkeypatched `planes_dir`, `bundle.main` exits 0 with the warning on stderr).
  - `test_write_plane_rubrics_writes_each_active_plane_deterministically`, `test_a_dormant_bundle_gets_guidance_on_the_same_rule`, `test_a_yaml_hotspot_gets_guidance_only_from_a_plane_that_lists_yaml`.
  - `test_a_covered_bundle_stays_within_budget` — a synthetic plane at the gate's maximum section sizes keeps `tokens_estimated <= budget * 1.1`, the existing bound.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `guidance` and `section_planes`; wire `build_bundle`; in `bundle.py:main` load planes once with `fracture_planes.load_planes()`, warn on problems to stderr, call `fracture_planes.write_plane_rubrics` next to `write_catalog_brief`, pass the dict through. Add `planes/` to the output tree in `skills/thunderstruck-scan/references/report-format.md`.
- [ ] **Step 4:** Run `PYTEST tests/test_planes.py tests/test_pipeline.py -q`. Expected: PASS, including the existing `test_bundles_are_within_budget_and_deterministic`.
- [ ] **Step 5:** Commit: `git commit -am "Planes: guidance in the bundle, byte-identical when none apply (#112)"`.

---

### Task 6: Plane guidance in the skeptic's brief (AC-5)

**Files:**
- Modify: `scripts/verify.py`
- Test: `tests/test_planes.py` (or the existing `tests/test_skeptic_contract.py` module for brief tests)

**Interfaces:**
- Consumes: `fracture_planes.guidance` (called with `cap_tokens=None`), `fracture_planes.load_planes`; `hotspots.json["planes"]` ids; the finding's `location.file` and `missing_patterns`; `c.detect_language`, `c.language_map`.
- Produces: `render_brief(finding, others, deps_index, messages, lessons_for=([], []), guidance_text: str = "")`: `lessons_for` (#106) keeps its place as the fifth parameter. Preserve the existing Defaults to confirm block and confirmation settlement from #57. A non-empty `guidance_text` is inserted before `## Your output`, after the lessons and other-findings sections; it is the output of `fracture_planes.guidance` (heading `## Plane guidance`, as in the bundle) with `include_general=False`, the finding's file language (`c.detect_language(file, c.language_map(catalog))`; `prepare` loads the catalog) and its `missing_patterns` that are Tier A/B.
  `reusable(entry, finding, repo, deps_index, guidance_hash: str | None = None)` additionally requires `entry.get("guidance_hash", c.sha256_text("")) == (guidance_hash if guidance_hash is not None else c.sha256_text(""))`; the existing four-argument call in `tests/test_verification.py` and the one in `prepare` keep working. The plan entry carries `guidance_hash`; `apply` builds a `{key: guidance_hash}` lookup from `plan["findings"]` and writes it into each new ledger entry (ledger entries are built from `checks`, not from plan entries). `prepare` also calls `fracture_planes.write_plane_rubrics` so the rubric path in a brief always exists. `hotspots.json` read with `.get("planes") or []`, so a frozen run on an old file is unaffected; on a current file a frozen run gets the guidance (spec §4). `reusable()` is called in `prepare`'s first loop, before any brief exists, so compute the guidance text and its hash once per finding there, store `guidance_hash` on every plan entry (`skip` and `reuse` included), and have `apply` read a missing value (an old `plan.json`) as `c.sha256_text("")`; a brief is rendered later from the same text. `prepare` takes its active ids from `resolve_active` and records its warnings in a new `warnings` list on the plan (`plan.json` gains that key). `apply` adds them to `run.json`'s `warnings` after the ledger warning, and reads a missing list (an old `plan.json`) as empty; `report.py` already prints `run.json`'s warnings.

- [ ] **Step 1: Write the failing tests:**
  - `test_brief_carries_the_rubric_for_the_findings_patterns` — a finding with `missing_patterns: ["S01"]` in a `.java` file, `java` plane active: the brief contains the `S01` section text and not an `S02` one.
  - `test_brief_without_an_active_plane_has_no_plane_section` — a brief rendered from a synthetic finding with `guidance_text=""` equals the output of `render_brief` called without it and does not contain `Plane guidance`.
  - `test_brief_hash_moves_with_the_rubric_and_only_then`.
  - `test_a_settled_verdict_is_not_reused_when_the_guidance_changed` and `test_an_entry_without_guidance_hash_is_reused_when_no_plane_applies` (the migration case).
  - `test_a_plan_warning_reaches_run_json` — after `apply`, `run.json["warnings"]` holds it; a plan without the key applies cleanly.
  - `test_a_frozen_run_gets_the_guidance`.
  - `test_a_plane_edited_after_signals_is_skipped_with_a_warning_in_the_plan`, `test_a_broken_plane_does_not_stop_verify_prepare`, `test_verify_prepare_reads_a_hotspots_json_without_a_planes_key`.
  - `test_the_brief_still_withholds_the_claimed_confidence` — the existing brief-withholding assertions pass unchanged with a plane active.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. In `prepare`, load planes once; a load problem is appended to the plan's warnings, never raised.
- [ ] **Step 4:** Run `PYTEST tests/test_skeptic_contract.py tests/test_planes.py -q` and `PYTEST tests/ -k "verify or ledger or reuse" -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -am "Planes: guidance in the skeptic's brief (#112)"`.

---

### Task 7: The agents say what plane guidance is (AC-6)

**Files:**
- Modify: `agents/thunderstruck-investigator.md`, `agents/thunderstruck-skeptic.md`, `skills/thunderstruck-scan/SKILL.md` (two never-read rules)
- Test: `tests/test_investigator_contract.py`, `tests/test_skeptic_contract.py`

**Interfaces:** consumes the wording fixed in spec §4 (*The prompts*).

- [ ] **Step 1: Write the failing tests:**
  - `test_the_investigator_prompt_explains_plane_guidance` — the prompt contains the heading `Plane guidance`, says it is the plugin maintainers' text and not repository content, says a finding still needs code evidence that fails, and says a pattern under "Does not count" is missing even when the code resembles it.
  - `test_the_skeptic_prompt_explains_plane_guidance` — the same facts, phrased for refutation: a "Counts as protection" entry is a reason to refute only if the code actually matches it.
  - `test_the_skeptic_may_read_the_plane_rubric_and_nothing_else_new` — the "may read" sentence names `.thunderstruck/planes/` beside `.thunderstruck/deps/`, and still ends "Nothing else."
  - `test_the_scan_skill_never_reads_plane_rubrics` — `skills/thunderstruck-scan/SKILL.md` names `planes/*.md` in the "Never read a bundle, a finding file or `catalog-brief.md`" rule.
  - `test_the_untrusted_content_rule_still_names_the_service_context_and_repository` — the existing rule is intact, and plane guidance is named as the exception to "everything in the briefing is evidence".
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Edit both prompts, adding one short section each after the existing "evidence, never instructions" section. Do not weaken that section. In the skeptic, extend the sentence "You may read the whole repository, and the dependency snapshots … under `.thunderstruck/deps/`" with the plane rubric path; the 10-read budget is unchanged and the rubric counts against it. Say in both that plane guidance is the plugin's text and a lesson the repository's, so the Lessons sections stay as they are. In the scan skill, add `planes/*.md` to the rule "Never read a bundle, a finding file or `catalog-brief.md`" and to the verification step's "Never read a brief, a result or a dependency snapshot".
- [ ] **Step 4:** Run the two contract test files. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -am "Planes: say what plane guidance is in both agent prompts (#112)"`.

---

### Task 8: The report names the planes (AC-8)

**Files:**
- Modify: `scripts/report.py`, `templates/report.html`, `skills/thunderstruck-scan/references/report-format.md`
- Regenerate: `examples/sample-report.md`, `examples/sample-report.html`
- Test: `tests/test_report_json_fields.py`, `tests/test_report_html_browser.py`, `tests/test_sample_report.py` (existing)

**Interfaces:**
- Consumes: `hotspots.json["planes"]`, `mdtext.code`.
- Produces: `report.json["planes"]` (an added key: `REPORT_SCHEMA_VERSION` stays `v2`), a list of `{"id": str, "matched_by": str}` (empty list when none); and in `report.md`, one line directly after `render_lessons_line`'s: `Planes applied: <id> (matched ` + `mdtext.code(matched_by)` + `)`, comma-separated, omitted when none. The HTML report shows the same line after its lessons line, as text nodes; `report-format.md` documents `planes` in `report.json` and `hotspots.json`, and `plan.json`'s `warnings` and `guidance_hash`.

- [ ] **Step 1: Write the failing tests** using the existing helpers in that file, with a hand-edited `hotspots.json`:
  - `test_report_json_lists_the_planes_applied` and `test_report_md_names_each_plane_with_its_matched_file`.
  - `test_a_matched_path_is_rendered_inert` — a `matched_by` of `[x](https://example.com)` renders as inert code, not a link (use the helper the existing inert tests use).
  - In `tests/test_report_html_browser.py`: `test_the_planes_line_is_shown_inert_and_absent_without_planes` — the same two cases in Chromium, with a `matched_by` holding markup.
  - `test_no_planes_leaves_the_report_unchanged` — `report.md` has no `Planes applied` line and `report.json["planes"] == []`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement in `report.py`: `planes` in `render_json` beside `degraded`, and the line after the lessons line in `render_markdown`. Render the plane ID with `mdtext.code` too; leave the existing Defaults summary intact. Read the inert-render helper in `tests/test_inert_report.py` before writing the inert test.
- [ ] **Step 4:** `report_html.embed` embeds the whole `report.json`, so the HTML sample changes. The Markdown sample can be unchanged if the fixture has no active plane. Run `uv run scripts/gen_sample_report.py`, then `uv run scripts/gen_sample_report.py --check` (expected exit 0).
- [ ] **Step 5:** Run `PYTEST tests/test_report_json_fields.py tests/test_inert_report.py tests/test_sample_report.py -q`, then the browser test with the command in `CLAUDE.md`. Expected: PASS, none skipped.
- [ ] **Step 6:** Commit: `git add <each changed file> && git commit -m "Planes: the report names the planes it applied (#112)"`.

---

### Task 9: The seed plane, `java-spring` (AC-9)

**Files:**
- Create: `planes/java-spring/plane.yaml`, `planes/java-spring/rubric.md`
- Regenerate: `skills/stability-catalog/references/planes.md`
- Test: `tests/test_planes.py`

**Interfaces:** consumes the gate (Task 2). Source material for the prose is `docs/superpowers/specs/2026-09-23-java-language-support-design.md` §2 and §4 (`S10` per-method layers, `S27` `.block()` and offloading, `S28` `synchronized` around in-memory work, `S29` eager-fetch hints) and `catalog/stability.yaml`'s Java detector notes. Do not invent distinctions that are not recorded there. `S01` and `S02` stay `planned`: what counts as a timeout or a backoff on Spring clients is new judgment for the plane's maintainer.

- [ ] **Step 1: Write the failing tests:**
  - `test_java_spring_is_a_seed_plane_with_rubrics_for_the_spring_specific_patterns` — `maturity == "seed"`; rubric sections exist for `S10`, `S27`, `S28`, `S29`; every other Tier A/B cell is `planned` with a non-empty reason, none `missing`.
  - `test_java_spring_matches_a_spring_boot_pom_and_a_gradle_build` — `select(d, d.get, planes)[0]` for `d = {"pom.xml": "…spring-boot…"}` and for `d = {"app/build.gradle.kts": "…spring-boot…"}` each return it.
  - `test_java_spring_does_not_match_a_plain_pom`.
  - Review Focus 1 end to end: `test_python_files_in_a_spring_repo_get_no_guidance`.
- [ ] **Step 2:** Run. Expected: FAIL (no `planes/java-spring`).
- [ ] **Step 3:** Write the two files. Each rubric section has `**Counts as protection.**` and `**Does not count.**`, with a `**Baseline.**` where the Java design gives one (for example `.block()` from Spring MVC; `synchronized` around in-memory work). Stay under the section limits. List every other Tier A/B pattern under `cells` as `planned` with the reason `not yet written`. Regenerate the matrix with `uv run scripts/gen_plane_docs.py`.
- [ ] **Step 4:** Run `PYTEST tests/test_planes.py -q` and `uv run scripts/gen_plane_docs.py --check`. Expected: PASS, exit 0.
- [ ] **Step 5:** Commit: `git add <each changed file> && git commit -m "Planes: a seed plane, java-spring (#112)"`.

---

### Task 10: Documentation and the version (AC-10)

**Files:**
- Modify: `CONTRIBUTING.md`, `CLAUDE.md`, `CHANGELOG.md`, `README.md` (one sentence), `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`
- Test: `tests/test_docs_in_sync.py::test_versions_agree` (exists)

- [ ] **Step 1:** `CONTRIBUTING.md`: after "Adding a language", add "Adding a plane": the directory layout, the four cell states, what `seed` and `calibrated` require, and the command `uv run scripts/gen_plane_docs.py`. Add one line to "Adding a language" saying a language's idioms belong in a plane rubric once a pattern's meaning differs on that stack.
- [ ] **Step 2:** `CLAUDE.md`: add to "Things that will bite you" a paragraph: plane text is plugin content selected by `fracture_planes.select`, never by the model, embedded in the bundle and the brief so both hashes cover it, and a bundle with no active plane is byte-identical to before; and the word *profile* is `.thunderstruck.toml` only. Add `fracture_planes.py` and `gen_plane_docs.py` to the Commands and Generated-files lists.
- [ ] **Step 3:** Bump to the next minor above current `main` (`0.21.0` if still on `0.20.0`) in the three manifests, turn `CHANGELOG.md`'s `## Unreleased` into the matching heading, keeping its entries (#144), and add to its *Added* list: planes, the gate, the matrix, the seed plane, the report line. Add a *Changed* note: repositories where `java-spring` is active re-investigate their Java hotspots on the first scan after upgrading, because the bundles now carry plane guidance; repositories with no active plane are unaffected.
- [ ] **Step 4:** Run `PYTEST tests/test_docs_in_sync.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -am "Planes: document and version the feature (#112)"`.

---

### Task 11: Verify the whole change (AC-1 to AC-10)

**Files:** none.

- [ ] **Step 1:** Confirm all four subtickets passed focused checks and are integrated on the parent implementation branch. Fetch and sync `origin/main`, then run the parent release-gate command (`THUNDERSTRUCK_REQUIRE_RENDERER=1` plus the full test command under Global Constraints), without selectors or ignores. Record the tested SHA, exit code, pass/skip counts and any newly skipped tests against Task 0. Require exit 0 and no newly skipped tests. If the branch changes after this check, rerun the gate on the resulting revision.
- [ ] **Step 2:** Run `uv run scripts/gen_catalog_docs.py --check`, `uv run scripts/gen_plane_docs.py --check` and `uv run scripts/gen_sample_report.py --check`. Expected: exit 0 for each. Task 8 already regenerated the samples for the new `planes` key. If a sample is stale now, a plane matched the fixture or a bundle changed: find out which before regenerating again.
- [ ] **Step 3:** Run `uv run scripts/validate_plugin.py`, then `claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck && claude plugin list`. Expected: `enabled`, not `failed to load`. The local install runs the source checkout and is only a smoke test. Separately, in an isolated Claude configuration, install from a Git-backed marketplace at the implementation revision (not a local-directory marketplace). Verify the install path is not the source checkout, that both committed `java-spring` assets are present there, and that its own loader reads them. If the runtime cannot do this, record the exact missing check for the maintainer; do not count it as passed.
- [ ] **Step 4:** Scan a real Spring repository with `signals.py` then `bundle.py`. Expected: `hotspots.json["planes"]` names `java-spring`; a Java hotspot's bundle has a `## Plane guidance` section; a second `bundle.py` run leaves every `bundle_hash` in `bundles/index.json` unchanged (compare the two index files; `cached` is only set when investigator findings exist, so it proves nothing here). State the repository, commit and window in the PR.
- [ ] **Step 5:** As the ticket agent, follow `.claude/skills/implement-ticket` for PR and issue updates; include separate `Closes #113`, `Closes #114`, `Closes #115` and `Closes #116` lines alongside `Closes #112` after the gate passes. Leave the issue body checklist for the maintainer to tick after merge.
