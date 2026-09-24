# A real freshness check for the sample report: design

**Requirements:** [#26](https://github.com/tomstagl/thunderstruck/issues/26). The problem, stories, scope, acceptance criteria (AC-n) and decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-24-sample-freshness.md`

## 1. What makes the sample drift today

| Source | Where | Effect |
|---|---|---|
| Scan date | `report.py` prints `Scanned {hotspots.generated_at[:10]}` | changes daily |
| Context fetch date and age | `report.py` `render_service_context`: `fetched {fetched_at[:10]} ({age} days ago)` | changes daily |
| Fixture SHAs | `build_fixture.build` runs every git command with the user's environment and global/system config | commit signing, `core.hooksPath`, `init.templateDir`, `GIT_DEFAULT_HASH` / `init.defaultObjectFormat` each change or break the history |
| Reading git | the pipeline's own `git log`/`diff` calls inherit the same config | settings such as `log.showSignature` can change what `signals.py` parses |
| Dependencies | the generator's PEP 723 block says `lizard>=1.17`, `pyyaml>=6.0` | a lizard release can change CCN and scores |

Nothing else in the sample reads the clock. `signals.py` only uses `now` to resolve a *relative* `--since`, and the sample passes an absolute date.

## 2. Architecture

```
gen_sample_report.py
  isolated_git_env()        one env for every subprocess: no global/system config, sha1, no templates
  build(..., env)           the fixture, built with that env
  run the real pipeline     signals → context → bundle → canned findings → validate → report (same env)
  pin_dates(report, day)    rewrites the three clock-dependent spots, labels the run line
  --check                   compares with the committed file, prints a diff and the regen command
```

**Production scripts are not touched.** Pinning happens only in the generator, by rewriting the rendered report. So a real scan cannot print a fixed date or the label (AC-5): the code that writes them is not reachable from a scan. We rejected the alternative, a clock-override variable honoured by `signals.py`, `context.py` and `report.py`: a leaked environment variable would make a real report lie about when it ran.

## 3. Git isolation

`build_fixture.isolated_git_env(base=os.environ)` returns a copy of the environment with these changes:

- `GIT_CONFIG_GLOBAL=os.devnull` and `GIT_CONFIG_NOSYSTEM=1`. No user or system config: no signing, no global hooks, no templates, no default object format.
- Every `GIT_*` variable that changes repository layout or object identity is removed: `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_DEFAULT_HASH`, `GIT_TEMPLATE_DIR`, `GIT_CEILING_DIRECTORIES`, and `GIT_CONFIG*`, apart from the two set above.
- `build()` runs `git init --template= --object-format=sha1 -b main`. An empty template means no sample hooks, and the explicit object format guards against git versions whose default differs.

`build()` and its helpers (`run`, `add_remote`, `add_service_context`) use this environment for every git call. Tests therefore get the same protection: a developer with commit signing no longer gets signing prompts from the fixture.

The generator passes the same environment to every pipeline subprocess (`signals.py`, `context.py`, `bundle.py`, `save_finding.py`, `validate.py`, `report.py`). It keeps the variables the pipeline needs (`PATH`, `HOME`, `THUNDERSTRUCK_TRUST_CONTEXT`, `XDG_CONFIG_HOME`).

**Not covered:** Windows line endings (the ticket names Linux and macOS), and git versions older than 2.28, which lack `--object-format`. The fixture already requires `init -b`, which needs 2.28 as well.

## 4. Pinned dates

The pinned day is the committer date of the fixture's `HEAD` (`git log -1 --format=%cs`), 2025-07-29 today. That satisfies "no date earlier than the fixture's last commit" by construction, and it follows the fixture if its history changes.

`pin_dates(report, day)` makes exactly these substitutions, and each must match **exactly once**. Otherwise it raises, so a format change in `report.py` breaks generation loudly instead of quietly un-pinning:

| Pattern | Replacement |
|---|---|
| `^Scanned \d{4}-\d{2}-\d{2} · ` | `Scanned {day} (dates fixed for this sample) · ` |
| `fetched \d{4}-\d{2}-\d{2} \(\d+ days? ago\)` | `fetched {day} (0 days ago)` |

The label lives in the visible run line (decision in #26). The context line has no label of its own; the run line covers every date in the report.

## 5. Dependency pins

The generator's PEP 723 block pins exact versions: `pyyaml==6.0.3` and `lizard==1.24.0`, the versions that resolve today. The generator runs every pipeline script with `sys.executable`, so these are the versions that produce the sample. The pytest environment (`uv run --with lizard …`) stays unpinned, which is why freshness is checked by the generator itself and not from inside pytest. A deliberate upgrade edits the pin and regenerates the sample in the same PR; CI enforces it (AC-6).

## 6. Check mode

`--check` generates into memory and compares the result with `examples/sample-report.md`.

- Equal: print `sample-report.md is up to date`, exit 0.
- Different, or missing: print a unified diff capped at 80 lines, then `regenerate with: uv run scripts/gen_sample_report.py`, and exit 1.

Comparison is `str ==` on the text. Both sides are LF, because the file is written with `write_text` on Linux or macOS.

## 7. CI

The `tests` matrix job gains a step after "Generated docs are in sync":

```yaml
- name: Sample report is in sync
  run: uv run --python ${{ matrix.python }} scripts/gen_sample_report.py --check
```

Running it on 3.11, 3.12 and 3.13 is what shows the output is identical across supported Pythons (AC-1). The existing step "Configure git for the fixture repository" stays: tests still need it, and the generator ignores it by design.

## 8. Test strategy

- **`tests/test_sample_report.py`**:
  - `pin_dates` rewrites both spots and adds the label;
  - it raises when a pattern matches zero times or twice;
  - `check()` passes for an equal body, and fails with the diff and the command for a stale one or a missing file.
- **Isolation.** The fixture is built with a hostile global config: `commit.gpgsign=true` with `gpg.program=false` (so any signing attempt fails the commit), a `core.hooksPath` whose `commit-msg` hook exits 1, `init.templateDir` holding a failing hook, `init.defaultObjectFormat=sha256`, and `GIT_DEFAULT_HASH=sha256`. The build must succeed, and the resulting `HEAD` must equal a build under an empty config. The two are compared to each other, not to a constant, so this test does not break whenever the fixture's content changes.
- **AC-5.** A real `report.py` run over the fixture contains neither "dates fixed for this sample" nor the pinned day.
- **CI step (§7)** runs the real check on every supported Python.
- **Manual.** Stale the sample on purpose and confirm the check fails with a diff. Regenerate twice on different days; the second run is identical.

## 9. Docs

- CLAUDE.md: its commands comment becomes true, and `gen_sample_report.py` gets its `--check` annotation.
- CONTRIBUTING.md: "Both are checked in CI" becomes true. Add the `--check` commands, and a line saying that a dependency bump regenerates the sample.
- The sample's header comment says dates are fixed, and says how to regenerate and check.

## 10. Decisions

| Decision | Rationale |
|---|---|
| Pin by rewriting the rendered report in the generator | No production code path can print a fixed date (AC-5). A clock override in the scripts could leak into real scans. |
| Exactly-once substitution | A report format change fails generation, instead of silently letting the clock back in. |
| Pinned day = fixture HEAD committer date | It satisfies "no date before the last commit" without a second constant to keep in sync. |
| Isolate git inside `build()`, not only in the generator | Tests benefit too, and there is one place to maintain. |
| Pin exact versions in the generator only | The generator is what produces the sample. Pinning the test environment would be a separate decision. |
| Freshness checked by a CI step, not a pytest test | The pytest environment is unpinned, so a test there would be flaky on dependency releases. |
