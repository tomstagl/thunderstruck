# Validator gaps: design

**Requirements:** [#25](https://github.com/tomstagl/thunderstruck/issues/25). The problem, stories, scope, acceptance criteria (AC-n) and decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-24-validator-gaps.md`

## 1. Where the gaps are

| Gap | Code today |
|---|---|
| `location.lines` unchecked | `Validator.check_finding` only checks `location.file` exists |
| reversed code range | `check_evidence` tests `start < 1` and `end > total`, never `start ≤ end` |
| path escapes | `_common.ref_path` = `str(p).lstrip("./")`: `/etc/x` → `etc/x`, `../x` → `x`, `src/../../x` passes and is opened |
| symlinks | `_count_lines(repo / rel)` follows them |
| untracked / ignored files | anything on disk counts |
| dotfiles | `lstrip("./")` turns `.github/x.py` into `github/x.py` |
| two identities | `stable_key(location.file)` and `index.json` use the path as written, so `./a.ts` ≠ `a.ts` |
| stale cache | `bundle.py` treats a findings file as cached when its `bundle_hash` matches, whatever rules validated it |

## 2. Canonical paths

`_common.ref_path(p)` becomes: `str(p)`, with leading `./` segments removed, repeatedly. Nothing else is stripped, so `.github/x.py` stays `.github/x.py`, and `../x` stays `../x`, which the check below then rejects rather than rewrites.

`_common.path_problem(rel) -> str | None` returns a reason when the canonical path is:

- empty;
- absolute (`/…`, or a Windows drive such as `C:…`);
- has a `..` segment;
- contains a backslash (git paths always use `/`);
- is not in canonical form: an empty segment (`a//b`), a `.` segment, or a trailing `/`. pathlib would silently collapse these onto a real file.

Callers that already use `ref_path`, namely `report.py` and `links.py`, get the fix for free. `links._escapes` stays as defence in depth.

## 3. Tracked files only

The `Validator` loads the index once through `_common.tracked_index`: `git ls-files -s -z`, read as bytes and decoded as UTF-8 with `surrogateescape`, so a file name the locale can't decode doesn't crash validation. The result is `{path: mode}`. Unmerged entries keep their first stage. Intent-to-add entries count as tracked, since their content is on disk. It then resolves a cited path, whether a location or a code ref, with `_resolve(raw) -> (rel, total_lines, error)`. The checks run in this order, and **no file is opened until all of them pass** (AC-2):

1. `rel = ref_path(raw)`. If `path_problem(rel)`, error: "must be a path relative to the repository root, without `..`".
2. `rel` is not in the index:
   - if it is a directory, error: "is a directory";
   - if it exists on disk, error: "is not tracked by git (untracked or ignored files can't be cited)";
   - otherwise, error: "no such file in the repository", plus "did you mean …" when the index holds the same path in a different case.
3. The mode is `120000`: "is a symbolic link". The mode is `160000`: "is a submodule, not a file". Paths inside a submodule, or under a tracked symlinked directory, are never in the index, so step 2 already rejects them.
4. `(repo / rel).resolve() != repo.resolve() / rel`: "passes through a symbolic link in the working tree". This means no component of the path may be a symlink. A plain "stays inside the repo" test would let a tracked file replaced locally by a link to an ignored `.env` pass (review finding). `resolve()` only calls lstat and readlink; it opens nothing.
5. `os.lstat` fails: "is tracked but missing from the working tree (deleted locally, or outside a sparse checkout)". The path is not a regular file (`S_ISREG`): "is not a regular file". Without this check, a FIFO would block the line count forever.
6. Only now are the lines counted, from the working tree, so tracked files with uncommitted edits validate against what is on disk (AC-3).

`commit_touches` passes only paths that resolved, with `--literal-pathspecs`. Without that, `src/[id].ts` is a glob that matches `src/i.ts`, and a commit to the wrong file would count as history.

The index lookup and the line counts are cached per validator run. A repository with 100k files costs one `ls-files` call.

## 4. Line ranges

A single helper, `parse_range(value) -> (start, end) | None`, accepts:

- an int (not a bool);
- a string matching `[0-9]+` or `[0-9]+-[0-9]+`, anchored with `^…\Z`. The regex uses `[0-9]` and `\Z`, not `\d` and `$`, so Unicode digits such as `١٦` and a trailing newline don't count as line numbers. `CODE_REF` gets the same treatment.

Nothing else is accepted: no spaces, no `L` prefix, no en dash. The range must satisfy `1 ≤ start ≤ end ≤ total`.

- **`location.lines`:** optional. A missing key, or `null`, means a whole-file location and stays valid. Any other value must parse and fit. Otherwise the error is: `location.lines 'L16' must be a line ("42") or a range ("42-118") with start ≤ end inside src/a.ts, which has 120 lines`.
- **`code` refs:** a malformed range (such as `a.ts:L16` or an en dash) and an out-of-range or reversed one both get the same message. The path is resolved first (split at the last `:`), so the message can give the file's length: `evidence[i].ref 'a.ts:28-16' — that line does not exist: use a line ("42") or a range ("42-118") with start ≤ end inside a.ts, which has 120 lines`. The `location.lines` error is built by the same function.

`links.parse_lines` stays lenient (spaces, ints). It is the report's display fallback and only ever sees validated values. It keeps rendering a whole-file link for anything else. `report.py`'s reversed-range `min/max` stays as defence in depth against a tampered file. `report.py` also never counts lines for a path with a `path_problem`: with the new `ref_path`, `repo / "/etc/x"` would otherwise be `/etc/x`.

## 5. One identity per file

When a document is valid, `validate.py` already writes back `key`, `content_hash` and `catalog_evidence`. It now also canonicalises the paths the finding carries:

- `location.file` becomes `rel`;
- each `code` ref's path becomes `rel` (for example `./src/a.ts:3` becomes `src/a.ts:3`).

`key`, `content_hash`, `index.json` and the guardrail all read the canonical path, so `./a/b.ts` and `a/b.ts` are one file everywhere (AC-4). Detector refs already have to match a `hotspots.json` ref exactly, and those paths are canonical.

**Keys (AC-5).** A finding whose path has no leading `./` keeps its key, because the input to `stable_key` doesn't change. A finding written with `./` gets the key its canonical form always should have had. That is the point of AC-4, and the only key change.

## 6. Re-investigating stale findings (AC-7)

`_common.VALIDATION_RULES = 2` is a rules version. `validate.py` stamps each valid document with `"validated_with": VALIDATION_RULES`.

A findings file counts as validated under older rules when it has findings carrying `key` and lacks the current stamp. Only `validate.py` writes `key`, and `save_finding.py` now strips `key`, `content_hash`, `catalog_evidence` and `validated_with` from model output, so a model can't forge any of them.

When the `bundle_hash` matches and the file was validated under older rules, **`bundle.py` re-runs today's `Validator` on it**:

- if it still passes, the bundle stays cached, and the scan's validate step re-stamps it;
- if it fails, the bundle is not cached, and the hotspot is investigated again.

`bundle.py` prints the number re-queued on the line *before* its final counts line, which the scan skill reads. This is cheaper than re-investigating every old finding, and it matches AC-7 exactly: only findings that *fail* the new rules are redone (review finding). Clean and failed files have no findings and are reused as before.

**The report is gated on the stamp.** `report.py` shows a file's findings only when it carries the current stamp. Any other file with findings is listed under *Incomplete* as "findings not validated by this version's rules — re-run the scan". So nothing reaches the report or `index.json` without today's validator having passed it, even when `report.py` runs alone after an upgrade, or after a file was re-saved without validation.

A future rule change bumps `VALIDATION_RULES`.

## 7. Investigator and repair text (AC-6)

The investigator prompt (`agents/thunderstruck-investigator.md`) and the repair-round text (`skills/thunderstruck-scan/SKILL.md`) gain one rule each, both saying the same thing:

- paths are copied from the bundle: relative to the repository root, with no `./`, `..` or absolute path, and naming a tracked file;
- `location.lines` is `"42"` or `"42-118"` with start ≤ end, and is left out for a whole-file finding;
- a code ref is `path:42` or `path:42-118`, following the same rules.

## 8. The sample report

`gen_sample_report.py` writes `"lines": f"{line}-{line + 12}"`, which already overruns two fixture files (`api.ts` has 13 lines but the sample cites 6-18; `format.ts` has 14 lines but cites 4-16). The generator clamps the end to the file's length. The sample changes only in those two locations and is regenerated, and #26's check enforces that.

## 9. Test strategy

- **`tests/test_validate_paths.py`**: uses small `tmp_path` git repos and the `Validator` directly.
  - **Paths:** absolute, `..`, backslash, untracked, ignored, a tracked symlink, a path through a tracked symlinked directory, a submodule path, a tracked directory replaced locally by a symlink to outside the repo, and a dotfile under a dot-directory (accepted).
  - **Never opened:** a spy on `Path.open` asserts that no rejected path was opened.
  - **Line ranges:** `location.lines` accepts an int, `"16"`, `"16-28"` and a missing key or `null`. It rejects `"L16"`, `"16–28"`, `"28-16"`, `"16-999"`, `0`, `True`, `" 16"` and `[16]`.
  - **Code refs:** a reversed code ref is rejected.
  - **Canonicalisation:** `./src/a.ts` is written back as `src/a.ts`, and its key equals the key for `src/a.ts`.
  - **Keys:** an existing finding without `./` keeps its key.
- **`tests/test_pipeline.py`**: the existing `_valid_finding` flow still passes.
- **Stale cache:**
  - an old validated file that still passes is reused;
  - one that now fails is re-queued, with the message on the line before the counts;
  - clean and failed files are reused;
  - validate stamps what it passes;
  - the report lists an unstamped file with findings as Incomplete;
  - `save_finding` strips validator-owned fields.
- **Review cases:**
  - Unicode digits and trailing newlines;
  - `//`, `/.` and a trailing `/`;
  - a directory, and a case mismatch;
  - a tracked file replaced by a link to an ignored `.env`;
  - a FIFO, under a 5-second alarm;
  - a file deleted locally, and one outside a sparse checkout;
  - `commit_touches` with `[id].ts`.

  The open spy covers `Path.open`, `builtins.open`, `io.open` and `os.open`.
- **End to end, by hand:** in a scratch repository, a hotspot under `.github/scripts/` is ranked, and a finding written with `./` is canonicalised, validated, reported, indexed and shown by the guardrail.
- **Prompt text:** the investigator prompt and the scan skill name the accepted forms (substring checks, so the text can't silently drift).
- **Sample:** `gen_sample_report.py --check` (from #26) passes after regeneration.

## 10. Decisions

| Decision | Rationale |
|---|---|
| "Inside the repository" means in the git index; content is read from the working tree | The ticket's decision. It excludes dependency, generated and secret files, and keeps local scans working. |
| Reject, never rewrite, a suspicious path | Rewriting `/etc/x` to `etc/x` is what let a finding validate against an unrelated file. |
| Canonicalise only leading `./` | That's the only harmless spelling difference. Everything else is either the real path or rejected. |
| Canonical paths written back by the validator | One place fixes identity for the key, the index, the guardrail and the report. |
| A rules version stamp, and a re-check of stale files in `bundle.py` | Only findings that fail today's rules are redone (AC-7). Clean and failed files behave as today. |
| The report is gated on the stamp | Findings reach the report only through today's validator, whatever order the scripts run in. |
| Lenient `links.parse_lines` stays | It is display-only, and harmless once the validator is strict. |

## 11. Open design questions

- **Follow-up (review finding 10):** `signals.py` can still rank files that can never validate. It checks candidates with `is_file()`, which follows symlinks, and it lists files with `git ls-files` without `-z`, so non-ASCII names come back quoted. That is outside #25's criteria and is tracked in #30.

- The backslash rule could reject a legitimate Linux file name that contains `\`. That is vanishingly rare in source trees, and such a file can still be cited once the rule is relaxed. It is kept strict for now.
