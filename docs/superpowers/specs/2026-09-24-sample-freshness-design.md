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
- **Every** `GIT_*` variable from the caller is removed before anything is set. That covers layout and identity (`GIT_DIR`, `GIT_COMMON_DIR`, `GIT_INDEX_FILE`, `GIT_DEFAULT_HASH`, …) and config injected through the environment (`GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`/`KEY_n`/`VALUE_n`), which is how some hosted environments turn signing on.
- git reads its default **ignore and attributes files** (`$XDG_CONFIG_HOME/git/ignore`, `~/.config/git/ignore`, `$XDG_CONFIG_HOME/git/attributes`, `/etc/gitattributes`) even with no config file at all. An ignored `*.ts` or a `working-tree-encoding` attribute breaks the build. The env therefore also sets `GIT_ATTR_NOSYSTEM=1`, and injects `core.excludesFile` and `core.attributesFile` as `/dev/null` through `GIT_CONFIG_COUNT`.
- `build()` runs `git init --template= --object-format=sha1 -b main`. An empty template means no sample hooks, and the explicit object format guards against git versions whose default differs.

`build()` and its helpers (`run`, `add_remote`, `add_service_context`) use this environment for every git call. Tests therefore get the same protection: a developer with commit signing no longer gets signing prompts from the fixture.

The generator passes the same environment to every pipeline subprocess (`signals.py`, `context.py`, `bundle.py`, `save_finding.py`, `validate.py`, `report.py`). It keeps the variables the pipeline needs (`PATH`, `HOME`, `THUNDERSTRUCK_TRUST_CONTEXT`, `XDG_CONFIG_HOME`). It drops `CLAUDE_PLUGIN_*`: `_common.plugin_root()` honours `CLAUDE_PLUGIN_ROOT`, and the sample must describe the checkout it sits in. For the same reason, the generator resolves its own root, and the output path, from `__file__`.

**Not covered:** Windows line endings (the ticket names Linux and macOS), and git versions older than 2.28, which lack `--object-format`. The fixture already requires `init -b`, which needs 2.28 as well.

## 4. Pinned dates

The pinned day is the committer date of the fixture's `HEAD` (`git log -1 --format=%cs`), 2025-07-29 today. That satisfies "no date earlier than the fixture's last commit" by construction, and it follows the fixture if its history changes.

`pin_dates(report, day)` makes exactly these substitutions, and each must match **exactly once**. Otherwise it raises, so a format change in `report.py` breaks generation loudly instead of quietly un-pinning:

| Pattern | Replacement |
|---|---|
| `^Scanned \d{4}-\d{2}-\d{2} · ` | `Scanned {day} (dates fixed for this sample) · ` |
| `fetched \d{4}-\d{2}-\d{2} \(\d+ days? ago\)` | `fetched {day} (0 days ago)` |

Before pinning, the generator checks that the report has a `## Service context` section. If it doesn't, it fails with "service context was not fetched" rather than letting `pin_dates` blame a format change. On a slow runner the stub catalog can time out, and the error should say so.

The label lives in the visible run line (decision in #26). The context line has no label of its own; the run line covers every date in the report.

## 5. Dependency pins

The generator's PEP 723 block pins exact versions, `pyyaml==6.0.3` and `lizard==1.24.0` (the versions that resolve today), and sets `[tool.uv] exclude-newer`. That fixes the transitive dependencies too: lizard pulls in `pygments` and `pathspec`, which don't affect the TypeScript fixture today, but nothing guarantees that stays true. A bump moves the pins and the date together. The generator runs every pipeline script with `sys.executable`, so these are the versions that produce the sample. The pytest environment (`uv run --with lizard …`) stays unpinned, which is why freshness is checked by the generator itself and not from inside pytest. A deliberate upgrade edits the pin and regenerates the sample in the same PR; CI enforces it (AC-6).

## 6. Check mode

`--check` generates into memory and compares the result with `examples/sample-report.md`.

- Equal: print `sample-report.md is up to date`, exit 0.
- Different, or missing: print a unified diff capped at 80 lines, then `regenerate with: uv run scripts/gen_sample_report.py`, and exit 1.

Comparison is `str ==` on the text. Both sides are read with universal newlines, so a CRLF checkout still compares equal. Every read in the generator names `encoding="utf-8"`, because the report contains `—` and `·`.

## 7. CI

The `tests` matrix job gains a step after "Generated docs are in sync":

```yaml
- name: Sample report is in sync
  run: uv run --python ${{ matrix.python }} scripts/gen_sample_report.py --check
```

Running it on 3.11, 3.12 and 3.13 is what shows the output is identical across supported Pythons (AC-1). The existing step "Configure git for the fixture repository" stays: tests still need it, and the generator ignores it by design.

A separate `sample-macos` job on `macos-latest` runs only the check. This is what shows the output is identical on macOS (AC-1).

## 8. Test strategy

- **`tests/test_sample_report.py`**:
  - `pin_dates` rewrites both spots and adds the label;
  - it raises when a pattern matches zero times or twice;
  - `check()` passes for an equal body, and fails with the diff and the command for a stale one or a missing file.
- **Isolation.** The fixture is built in a hostile environment:
  - a global config with `commit.gpgsign=true` and `gpg.program=false`, so any signing attempt fails the commit;
  - a `core.hooksPath` whose hooks exit 1;
  - `init.templateDir` holding a failing hook;
  - `init.defaultObjectFormat=sha256`;
  - XDG `git/ignore` (`*.ts`, `package.json`) and `git/attributes` (`working-tree-encoding=UTF-16`);
  - and the environment variables `GIT_DEFAULT_HASH=sha256`, `GIT_COMMON_DIR`, `GIT_CONFIG_PARAMETERS` and `GIT_CONFIG_COUNT`/`KEY`/`VALUE`, each injecting signing.

  The build must succeed, and its `HEAD` must equal a reference build made with every `GIT_*` removed and an empty XDG dir. The two builds are compared to each other, not to a constant, so the test does not break when the fixture's content changes.
- **Across days.** `generate()` must not contain today's date, and must contain the label. This holds because the pinned day is not today.
- **AC-5, structurally.** No script under `scripts/` other than the generator mentions `pin_dates` or the label.
- **AC-5, behaviourally.** A real `report.py` run over the fixture prints the scan's own date, unlabelled.
- **CI step (§7)** runs the real check on every supported Python.
- **Manual.** Stale the sample on purpose, confirm the check fails with a diff, then restore it. Regenerate under a hostile global config and confirm the output is unchanged.

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
