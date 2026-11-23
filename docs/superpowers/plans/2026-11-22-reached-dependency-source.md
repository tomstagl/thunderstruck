# Dependency source for reached packages: Implementation Plan

> For agentic workers: build task by task, test first. Steps use checkbox (`- [ ]`) syntax.

**Ticket:** #101. **Spec:** `docs/superpowers/specs/2026-11-22-reached-dependency-source-design.md`. Each task names the `AC-n` of the ticket it satisfies. A design change goes in the spec first.

**Goal:** a skeptic can read, and cite, the source of a package that a declared package pulls in.

**Branch:** named by whoever builds it; the agent uses `agent/101-reached-dependency-source`. Stage explicit paths only. Do not bump the version (maintainer's call, 2026-11-22); add the change under `## Unreleased` in `CHANGELOG.md`.

## Task 0: anchors (no AC)

- [x] Read the spec. Confirm in `scripts/deps.py`: `pypi_declared` returns `{name: (spec, files)}`, `discover_pypi`, `_installed`, `BASES`, `resolve_dependency_ref`. `git grep -n "basis" -- scripts skills agents tests | cut -c1-140` to find every consumer of `basis` (the brief, the report, tests): each learns `installed` in Task 4.
- [x] `git grep -n "declared_in\|\"declared\"" -- scripts tests` for every reader of those keys: a reached entry has `declared: null` and `declared_in: []`.
- [x] Run `tests/test_deps*.py` and `tests/test_verification.py`: note they pass.

## Task 1: extras are kept (AC-1)

**Files:** `scripts/deps.py`, `tests/test_deps_reached.py` (new).

- [x] Failing test: `pypi_declared` for a `requirements.txt` with `kombu[sqlalchemy,redis]>=5` and a `pyproject.toml` optional group listing `kombu[mongodb]` gives the union of extras for `kombu`. Today it returns only `(spec, files)`.
- [x] Implement without breaking the callers found in Task 0: return a third element, the sorted extras, or add `pypi_declared_extras(repo)` beside it, whichever leaves every existing test unchanged. Commit by path. `AC-1`, `Task: 1`.

## Task 2: follow the installed metadata (AC-1, AC-2, AC-3)

**Files:** `scripts/deps.py`, `tests/test_deps_reached.py`.

- [x] Failing tests from spec §5 with a synthetic `site-packages` built in `tmp_path` (a `*.dist-info/METADATA` with `Requires-Dist`, a `RECORD`, one `.py` per package): reached through a hard requirement and through a requested extra, not through an unrequested one; depth cap 2; cap of 40 with a warning; cycle; sorted order; marker not evaluable.
- [x] Implement `reached_pypi(declared, extras, sites)` returning the entries of spec §2.3 and warnings, using `packaging.requirements.Requirement` and `Marker.evaluate({"extra": e})` (both already imported lazily in `deps.py`: keep the imports inside the function, so module level stays stdlib and `_common`). `discover_pypi` appends them after the declared entries.
- [x] Commit by path. `AC-1, AC-2, AC-3`, `Task: 2`.

## Task 3: basis, lock and editable (AC-2)

**Files:** `scripts/deps.py`, tests.

- [x] Failing tests: `basis: installed` without a lock; `locked` when `uv.lock` lists it, `unavailable` with the existing mismatch wording when its version differs; an editable install is `unavailable`.
- [x] Add `installed` to `BASES` and apply the declared package's rules to a reached one (share the code; do not copy it).
- [x] Commit. `AC-2`, `Task: 3`.

## Task 4: citing and showing it (AC-3, AC-4)

**Files:** `scripts/deps.py` (`resolve_dependency_ref`), `scripts/verify.py` (brief), `scripts/report.py`, tests.

- [ ] Failing tests: a ref into a reached package resolves; into an undeclared, unreached one it is rejected with today's message; the brief lists reached packages after declared ones with `reached via <parent>` and is byte-identical across two runs; `report.py` appends "(not declared by the project; reached through <parent>)" to such a citation, through `mdtext`.
- [ ] Implement. `tests/test_inert_report.py` and the brief determinism test must still pass.
- [ ] Commit by path. `AC-3, AC-4`, `Task: 4`.

## Task 5: the skeptic's instructions and docs (AC-4, AC-5)

- [ ] `agents/thunderstruck-skeptic.md`: one sentence that a dependency listed as reached is read as the declared package's dependency, not as the project's. Check `tests/test_skeptic_contract.py` for sentence pins and update them in the same commit if the file pins the prompt text.
- [ ] `docs/calibration/verification.md`: add one sentence under "Celery benchmark" that #101 adds reached packages and that the measured "4 of 73" is the figure before it; do not change any measured figure. README and CLAUDE.md (the `deps.py` paragraph) say what is reached and the caps. `CHANGELOG.md` under `## Unreleased`.
- [ ] Full suite (CLAUDE.md command), both `--check` generators, `uv run scripts/validate_plugin.py`. All pass before any push.
- [ ] Commit. `AC-4, AC-5`, `Task: 5`.

## Task 6: the measurement (maintainer, AC-6)

- [ ] Maintainer: on the frozen Celery checkout with its environment, run `deps.py` and record in `docs/calibration/verification.md` how many reached packages were snapshotted (expecting py-amqp and SQLAlchemy among them), with the commit and version. No labels are read or changed. The agent marks the PR ready after Task 5 and says AC-6 is the maintainer's.
