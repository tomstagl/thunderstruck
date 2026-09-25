# Citable ranking: design

**Requirements:** [#30](https://github.com/tomstagl/thunderstruck/issues/30). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-25-citable-ranking.md`

## 1. Where the gaps are

| Gap | Code today |
|---|---|
| symlinks rank | `signals.build` keeps `p in tracked and (repo / p).is_file()`. `is_file()` follows the link |
| non-ASCII names never rank | `git ls-files` and `git log --numstat` run without `-z`, so git C-quotes the name: `"src/m\303\263dulo/a.ts"`. That string is in neither the other list nor on disk |
| a rename inside a non-ASCII directory | the quoted form is `"old" => "new"`, which `_unrename` does not recognise, so the churn lands on a mangled key |
| undecodable output crashes | `_common.git` decodes with `text=True`, strictly. A file or author name that isn't valid in the locale's encoding raises `UnicodeDecodeError` |
| submodules | excluded today only because `is_file()` is false on a directory; nothing states the rule |
| two rules for "a file" | the validator's `_resolve` (#25) and the ranking filter are separate code, so they can drift |
| glob names get other files' history | `bundle.section_history` runs `git log -- src/[id].ts` and `git show <sha> -- src/[id].ts`. Without `--literal-pathspecs`, `[id]` is a character class, so commits that only touched `src/i.ts` are listed and their diffs shown |
| non-ASCII names in a briefing | `git show` headers and `git grep` output are C-quoted, so `section_related` fails its `path == rel` test and lists the hotspot as its own caller |

The last row only matters once non-ASCII files rank, which is why it is part of AC-2.

## 2. Reading file names exactly

**`_common.git_paths(repo_root, *args, timeout=180) -> str`.** Same contract as `_common.git` (raises `ThunderstruckError` on a non-zero exit), except that it reads bytes and decodes them as UTF-8 with `surrogateescape`. It is for output that carries file names. `tracked_index` already decodes this way and keeps its own call; it is not touched.

**History.** `collect_history` runs `git log --numstat -z` through `git_paths`. The pretty format and `_RECORD_SEP` are unchanged. With `-z`, each commit record is:

```
<RS><sha>\0<author>\0<date>\0<subject>\n
<adds>\t<dels>\t<path>\0                ← an ordinary change
<adds>\t<dels>\t\0<old path>\0<new path>\0   ← a rename or copy
\0                                        ← end of the commit
```

The header is still everything before the first `\n` (a `%s` subject is one line). The body is split on `\0` and walked as a token stream. Each token is split on its first two tabs only, since a name may itself contain a tab. A token whose path field is empty is followed by the old and the new name, and the new name is used, exactly as `_unrename` does today. Empty tokens are skipped. Names are never quoted and never contain the ` => ` notation, so `_unrename` is deleted.

For a name that git would not have quoted, the parsed history is identical to today's. That was checked against this repository's own history, the test fixture, and a scratch repository with both rename notations (`a/{b/x.ts => c.ts}` and `y.ts => z/y.ts`). This is the basis of AC-3 for history.

A name that is not valid UTF-8 now decodes to a string with lone surrogates instead of crashing the run. §3 decides what happens to it.

## 3. The candidate rule

**One implementation.** The working-tree half of the validator's `_resolve` (spec for #25, §3, steps 3 to 5) moves into `_common`:

```python
def tracked_file_problem(repo_root: Path, rel: str, mode: str) -> str | None:
    """Why the index entry `rel` (with its git mode) isn't a regular file in
    the working tree, or None. Opens nothing: lstat and readlink only."""
```

It returns exactly the strings `_resolve` returns today, in the same order:

1. mode `120000`: "is a symbolic link; cite the file it points to";
2. mode `160000`: "is a submodule, not a file";
3. `(repo / rel).resolve() != repo.resolve() / rel` (or it raises): "passes through a symbolic link in the working tree";
4. `lstat` fails with `ELOOP`: the same message; fails otherwise: "is tracked but missing from the working tree …";
5. not `S_ISREG`: "is not a regular file in the working tree".

`Validator._resolve` calls it in place of its own branches and keeps everything else (the `path_problem` check, the not-in-index messages and spelling hint, the line count, the cache). The validator's rules and messages do not change, which keeps the refactor inside the ticket's "no validator changes": `tests/test_validate_paths.py` passes unmodified.

**The rule in `signals.build`.** The `ls-files` set and the `is_file()` test are replaced:

```python
index = c.tracked_index(repo)
candidates, not_citable = [], 0
for p in per_file:                              # same order as today
    if c.detect_language(p, langmap) is None:
        continue
    mode = index.get(p)
    if mode is None:                            # deleted or renamed away since
        continue
    if (not c.is_utf8(p) or c.path_problem(p)
            or c.tracked_file_problem(repo, p, mode)):
        not_citable += 1
        continue
    candidates.append(p)
```

- **Order.** Candidates keep `per_file`'s insertion order, as today. Scores don't depend on order, and ties already sort by file name, but keeping the order removes any doubt for AC-3.
- **Not in the index.** A path that changed in the window but is no longer tracked is history, not a skipped file. It isn't counted. This is what happens to it today.
- **`path_problem`.** Index paths can't be absolute or contain `..`, but on Linux they can contain a backslash, which the validator rejects. Applying the same check keeps the ranked set equal to the citable set.
- **Not valid UTF-8.** `_common.is_utf8(p)` is `p.encode("utf-8")` succeeding. The validator itself would accept a surrogate-escaped path. But `bundle.py` writes the bundle with `encoding="utf-8"` and would crash on it, and no model can reproduce such a name in its findings. Such names are skipped and counted, never ranked. This is the one place the ranked set is narrower than what the validator accepts. The success-measure test states it explicitly.
- **Cost.** One `ls-files -s -z` call, which the run did before in another form, plus one `resolve` and one `lstat` per changed file in a supported language. Nothing is opened.

## 4. Counting what was skipped (AC-4)

`hotspots.json` gains `counts.files_not_citable`: the number of changed, tracked entries in a supported language that §3 skipped. It is always present, and `0` in the common case.

- Nothing is added to `warnings`, so `report.md` is unchanged (the ticket's decision).
- `report.json` and `index.json` are unchanged. The count describes the ranking run, and `hotspots.json` is where `files_considered` and `files_ranked` already live.
- The final summary line `signals.py` prints is unchanged. The scan skill reads it.
- `HOTSPOTS_SCHEMA` is not bumped. The field is additive, and nothing in the pipeline reads `counts` as a closed set.

## 5. Exact names in the briefing (AC-5, AC-2)

In `bundle.py`:

- `section_history`'s `git log -- <rel>` and `git show <sha> -- <rel>` run with `--literal-pathspecs`, as `commit_touches` and `links.py` already do. `src/[id].ts` then matches only itself.
- `git show` and `git grep` also run with `-c core.quotePath=false`, so a diff header and a caller line name a non-ASCII file the way the bundle does, and `section_related`'s `path == rel` test excludes the hotspot from its own callers.
- With `core.quotePath=false`, `git grep` prints a name that isn't valid UTF-8 as raw bytes, which `_common.git`'s strict decode can't read. The grep is read through `git_paths` (which gains `check=False`, since grep exits 1 on no match), and a hit line that doesn't encode as UTF-8 is dropped: it names a file no finding can cite, and the bundle writer couldn't encode it. `_common.is_utf8` is the one test, shared with §3's candidate rule.

Neither option changes git's output for a name without glob characters or bytes above `0x7F`. `core.quotePath=false` still quotes names containing `"`, `\` or control characters. For those, a caller line may show the quoted form and the self-match may be missed. That is cosmetic, deterministic, and such names are rare in source trees.

`git grep`'s own pathspecs (`*.ts`, `*.py`, …) are globs by design and stay that way.

## 6. Degradation

- A `git ls-files` failure raises `ThunderstruckError`, as a `git log` failure does today. Preflight fails fast; there is no partial ranking over an unknown index.
- A name that can't be decoded no longer crashes the run. It is counted under `files_not_citable`.
- `lizard`-less runs are unaffected: the candidate rule runs before complexity.

## 7. What stays byte-identical (AC-3)

For a repository with no symlink, submodule, non-ASCII, non-UTF-8 or glob-character name among its changed files:

- `per_file` and `commit_files` are identical (§2);
- the candidate list is identical, in the same order (§3);
- `hotspots.json` differs only by the new `counts.files_not_citable: 0` (and `generated_at`, as on every run);
- bundle bodies are identical, since `bundle.py` does not read `counts` and the new git options don't change the output for such names (§5). Bundle hashes, and so checkpointing, are unaffected;
- `examples/sample-report.md` is unchanged, so `gen_sample_report.py --check` passes without regeneration.

## 8. Test strategy

- **`tests/test_signals_citable.py`** (new), on a `tmp_path` repository built in the test with several commits touching:
  - `src/módulo/a.ts`, then renamed to `src/módulo/b.ts`;
  - `src/plain.ts`;
  - `src/link.ts`, a tracked symlink to `src/plain.ts`;
  - `libs/sub.ts`, a submodule (added from a local repository with `-c protocol.file.allow=always`). Not under `vendor/`, which the default filters exclude before the candidate rule runs;
  - `src/[id].ts` and `src/i.ts`, with one commit touching only `src/i.ts`;
  - `src/gone.ts`, tracked, then replaced in the working tree by a symlink;
  - on Linux only, a name that isn't valid UTF-8 (`os.fsdecode(b"src/\xff.ts")`).

  Its tests:
  - **Success measure.** The ranked set (`--top 0`, so every row) equals the set of index entries that changed in the window, are in a supported language, are valid UTF-8, and for which `Validator._resolve` returns no error. The comparison uses the real validator, not a copy of its rule.
  - **AC-1.** `src/link.ts`, `libs/sub.ts` and `src/gone.ts` are not ranked.
  - **AC-2.** `src/módulo/b.ts` is ranked, and the rename commit counts towards its churn. Earlier commits stay with `src/módulo/a.ts`, as they do for an ASCII name today: history does not follow renames.
  - **AC-4.** `counts.files_not_citable` equals the number of skipped entries (4 on Linux, 3 elsewhere), and `warnings` has no entry about them.
  - **AC-5.** The bundle for `src/[id].ts` lists only the commits that touched it. The `src/i.ts`-only commit is absent from the history and from the diffs.
  - **AC-2 in the briefing.** The bundle for `src/módulo/b.ts` shows the unquoted name in its diff headers, and doesn't list itself as a caller.
- **History parser, unit.** Feed `collect_history` (through a stubbed `git_paths`) records with an ordinary change, a rename, a binary change (`-\t-`, on a name the default filters don't exclude), a name containing `"` and a tab, and a commit with no files. It asserts the per-file counts and the rename attribution.
- **Validator refactor.** `tests/test_validate_paths.py` passes with no change to the test file.
- **AC-3.**
  - `test_bundles_are_within_budget_and_deterministic` still passes;
  - `gen_sample_report.py --check` passes without regenerating the sample;
  - a new test on the fixture asserts `counts.files_not_citable == 0`, and that the set of ranked files equals the nine files pinned in the test (taken from the current `main`). The order isn't pinned there, because it depends on the unpinned `lizard` of the test command; the sample check covers order with pinned dependencies;
  - by hand, on the fixture and on this repository: `hotspots.json` without `generated_at` and `counts.files_not_citable`, and `sha256sum` of every bundle, before and after the change, are identical. The output goes in the PR description.

## 9. Decisions

| Decision | Rationale |
|---|---|
| `-z` everywhere a file name is parsed, rather than `-c core.quotePath=false` | `quotePath=false` still quotes names with `"`, `\` or control characters. `-z` is exact for every name, and independent of the user's git config. |
| One `tracked_file_problem` shared by validator and ranking | The ticket's goal is one rule. Shared code can't drift; a test comparing two copies only catches the drift that its cases happen to cover. |
| The validator's messages move verbatim | Keeps the refactor inside "no validator changes", provable by the existing tests passing unmodified. |
| Skip names that aren't valid UTF-8, and count them | The bundle writer can't encode them, and a model can't cite them. Counting keeps the skip visible. |
| Only paths still in the index are counted as skipped | A deleted file is history, not a file the scan failed to rank. Counting it would make the number noisy on every repository. |
| The count lives only in `hotspots.json` | The ticket's decision: no warning, so no report change. `hotspots.json` already holds the run's counts. |
| `--literal-pathspecs` and `core.quotePath=false` on the per-file git calls in `bundle.py` | Byte-identical for ordinary names, so AC-3 holds and checkpointing is unaffected. |
| Drop `git grep` hit lines that aren't valid UTF-8 | Unquoted output carries raw bytes. Such a line names a file nobody can cite and can't be written to the bundle; decoding it with replacement characters would put a name in the briefing that matches no file. |

## 10. Open design questions

- **`calibrate.py`** lists files with `git ls-files` without `-z`, so it also misses non-ASCII names. It is a developer tool, not part of the ranking, so it is left out of this ticket. It could reuse `tracked_index` and the §3 rule in a follow-up.
- **Unicode normalisation.** On macOS with `core.precomposeUnicode`, git reports NFC names while an editor may pass the guardrail an NFD path. A finding on `src/módulo/b.ts` could then fail to match the guardrail's lookup. That is guardrail behaviour, outside this ticket, and worth checking once non-ASCII files produce findings.
- **Other per-file git calls.** A search found no other place that passes a hotspot's path to git as a pathspec without `--literal-pathspecs`. Any call added later needs it too. A test could enforce that, but it would have to parse the argument lists, so it is not planned.
