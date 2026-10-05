# Call sites on every platform: design

**Requirements:** [#66](https://github.com/tomstagl/thunderstruck/issues/66). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-10-05-call-sites-on-macos.md`.

## 0. What the evidence says

The ticket opened suspecting how macOS and git spell accented file names (composed vs decomposed Unicode). That is not the cause. Every finding below was reproduced on macOS 26 with Homebrew git 2.48.1 and Apple git 2.50.1 (Apple Git-155), on the repository the failing test builds (`citable_repo` in `tests/test_signals_citable.py`, kept with `--basetemp`). In it, four tracked files export `step`, one of them `src/módulo/b.ts`.

**The search finds nothing, for any file.** This is the exact command `section_related` runs (`scripts/bundle.py`):

```
$ git -c core.quotePath=false grep -n -I -E '\b(step)\b' -- '*.ts'; echo "rc=$?"
rc=1
$ git grep -n -E 'step' -- '*.ts'
src/[id].ts:1:export function step(x: number): number {
src/i.ts:1:export function step(x: number): number {
"src/m\303\263dulo/b.ts":1:export function step(x: number): number {
src/plain.ts:1:export function step(x: number): number {
```

Dropping `\b` finds all four files, the non-ASCII one included. The name was never the problem. All four briefings in that run lack the call-site section, not only `b.ts`'s. The non-ASCII test fails only because it is the one test that asserts call sites exist.

**`\b` and `\w` are what fail, and only under `-E`.** Counts are matches in `src/plain.ts`, whose first line is `export function step(…`:

| pattern | `-E` (ERE) | basic (BRE) | `-P` (PCRE) |
|---|---|---|---|
| `\bstep\b` | 0 | 1 | 1 |
| `[[:<:]]step[[:>:]]` | 1 | — | 1 |
| `\w+\(` | 0 | — | — |
| `step\(` | 1 | — | — |
| `-w -E '(step)'` | 1 | — | — |
| `-w -F -e step` | 1 | — | — |

`git grep -E` compiles the pattern with the platform's `regcomp`. macOS's libc supports GNU-style escapes such as `\b` only with its `REG_ENHANCED` flag, and git's macOS build sets that flag for basic expressions only (`USE_ENHANCED_BASIC_REGULAR_EXPRESSIONS`). So under `-E`, `\b` matches nothing. glibc supports `\b` in extended expressions, which is why CI on Linux passes. The behaviour is identical in Apple's git and Homebrew's.

**Ruled out:** the locale (`LC_ALL=C.UTF-8` gives the same empty result, as the ticket found), the global git config (none sets `grep.*`; `GIT_CONFIG_GLOBAL=/dev/null` changes nothing), and Unicode normalisation (the grep without `\b` names `src/módulo/b.ts` correctly).

**Confirmed by the fix.** Searching with fixed strings and git's own `-w` (§2), and nothing else changed, the test passes on macOS. So does the full suite: 1509 passed, 11 skipped. `gen_sample_report.py --check` reports both samples up to date. On the shipped fixture (`tests/fixtures/build_fixture.py`, `--top 10`), 9 briefings list exported symbols. On macOS today none of them lists call sites. With the change, 4 do: `src/client/releases.ts`, `src/sync/queue.ts`, `src/client/retry-wrapper.ts` and `src/client/limiter.ts`.

**Why CI never saw it.** The `sample-macos` job runs only `gen_sample_report.py --check`. The sample report renders findings, not briefings, so a briefing's content cannot change it. The bug has existed since the caller search was written (v0.1.0, `a484e47`).

**A second, latent gap.** `c.git_paths(..., check=False)` returns stdout and discards the exit code. A search that fails (git exit 128) looks exactly like one that found nothing, and a search that times out raises `TimeoutExpired`, which nothing catches, ending `bundle.py`.

## 1. Architecture

One function changes, and one step's output gains a line:

```
bundle.py  section_related   symbols ─► call_site_hits ─► hits | None
                                         (git grep -F -w)   │
                             renders one of three states ◄──┘   (§3)
           main              prints one line per briefing whose
                             call sites were not searched       (§4)
ci.yml     call-sites-macos  runs the call-site tests on macOS  (§6)
```

Nothing else reads call sites: no finding field, validator rule or report section depends on them. They exist only in a briefing's body.

## 2. The search

```python
def call_site_hits(repo: Path, symbols: list[str]) -> str | None
```

runs

```
git -C <repo> -c core.quotePath=false grep -n -I -w -F -e <s1> -e <s2> … -- *.ts *.tsx *.js *.jsx *.mjs *.py
```

with a 60-second timeout, and returns stdout decoded as `git_paths` decodes it (UTF-8, `surrogateescape`). It returns `None` when the search did not finish: an exit code other than 0 (lines found) or 1 (none), `TimeoutExpired`, or `OSError` (git missing).

- **`-F`: no regex library reads the symbols.** The defect is in what the platform's regex engine accepts. With fixed strings, git matches through its own `kwset`, the same on every platform. The symbols are identifiers (`str.isidentifier()`), so nothing in them needs a regex. `re.escape` goes away.
- **`-w`: git draws the word boundary.** git implements `-w` itself. A match counts only if the characters on both sides are not word characters (ASCII letters, digits, `_`). If one side is a word character, git retries further along the line. This reproduces today's `\b(…)\b` on Linux for ASCII identifiers. `step` does not match `stepper` or `my_step`. It still matches `step(` and `{ step }`.
- **One `-e` per symbol**, for the first 12 symbols as today. The order of the `-e` options does not affect git's output, which is sorted by path and line.
- **Unchanged:** `core.quotePath=false`, so a non-ASCII hotspot's own lines carry its unquoted name and are excluded. The glob pathspecs, `-I`, `-n`, and the 15-line and 160-character caps also stay. So does skipping a line that is not UTF-8.

**One accepted difference.** git's word characters are ASCII. A symbol next to a non-ASCII letter counts as a whole word: `café` matches inside `écafé`. With glibc in a UTF-8 locale, `\b` treats `é` as a word character and would not match there. That needs a non-ASCII identifier with a non-ASCII neighbour, and it can only add a line, never hide one. It is accepted rather than handled.

## 3. Three states in the briefing

When the file exports at least one symbol, the briefing always has a `## Call sites elsewhere in the repo` section, directly after `## Symbols this file exports`. Its body is exactly one of:

| state | when | body |
|---|---|---|
| found | at least one line survives the filters | `- \`<path>:<line>:<text>\`` per line, as today |
| none | the search finished and no line survives (including when every hit is the hotspot itself) | `None found: no other tracked \`.ts\`, \`.tsx\`, \`.js\`, \`.jsx\`, \`.mjs\` or \`.py\` file names these symbols as a whole word.` |
| not searched | `call_site_hits` returned `None` | `Not searched: the search for call sites did not finish, so they are unknown, not absent.` |

The two sentences are the module constants `CALL_SITES_NONE` and `CALL_SITES_NOT_SEARCHED`, and tests compare against those constants. A file that exports no symbol has neither section, as today. Nothing was searched for.

**Determinism.** Neither sentence carries git's stderr, an exit code or a duration. stderr is localised (a German git prints `Schwerwiegend: …`), and a bundle must be byte-identical across runs on an unchanged repo. A bundle written after a failed search hashes differently from one written after a successful search, so its finding is not reused once the search succeeds. That is intended.

**Budget.** The section belongs to `section_related`, which is clipped to its share as today. The new sentences are one line each.

## 4. Visible degradation

`bundle.py` prints one line per briefing in the "not searched" state, before its summary:

```
H03 src/sync/queue.ts: call sites not searched; its briefing says so
```

It decides this by finding `CALL_SITES_NOT_SEARCHED` in the body it just wrote. If the related section was clipped away, no line is printed, and the briefing no longer claims anything about call sites. The scan skill already relays what `bundle.py` prints. Step 2 of `skills/thunderstruck-scan/SKILL.md` gains one sentence naming this line, so it is relayed rather than summarised away. The report itself is out of scope (ticket, Scope Out).

## 5. Cached findings

Bundle bytes change for two kinds of hotspot, so their findings are investigated again on the next scan, once:

- **every platform:** files that export symbols but have no call sites (the new `None found` line);
- **macOS:** files that have call sites.

This is the product decision recorded in the ticket. `VALIDATION_RULES` does not change. No rule changes; the bundle hash already does the requeueing. The CHANGELOG states the one-time re-investigation.

## 6. CI on macOS

A new job, `call-sites-macos` ("call sites on macOS"), on `macos-latest`, runs:

```
uv run --with pytest --with pyyaml --with lizard pytest tests/test_call_sites.py tests/test_signals_citable.py -v
```

These two files are the call-site tests: the new file's, and `test_signals_citable.py`, which holds the non-ASCII briefing test. The job sits next to `sample-macos` and leaves it unchanged. The full suite stays Linux-only (ticket, Scope Out). `main` has no required checks today, so the job needs no settings change to run on every PR.

## 7. Test strategy

New tests go in `tests/test_call_sites.py`. They build a small git repository per test with `isolated_git_env()`, and read `section_related`'s output directly.

| test | AC | red on main |
|---|---|---|
| callers found as whole words: `b.ts` naming `step`, `stepper`, `my_step` gives exactly lines 1 and 2 | AC-2, AC-4 | macOS only (no lines found) |
| the fixture's `src/client/releases.ts` briefing cites `src/sync/scheduler.ts:26` and `:30` | AC-1 | macOS only |
| the search passes the symbols as `-F -w -e <symbol>` and never `-E` or `-P` | AC-2 | every platform |
| no callers gives exactly `CALL_SITES_NONE` | AC-3 | every platform |
| exit 128, `TimeoutExpired` and `FileNotFoundError` each give exactly `CALL_SITES_NOT_SEARCHED` | AC-3 | every platform |
| a file with no exports has no call-site section | AC-4 | passes on main (guards the unchanged case) |
| `bundle.main` prints `<file>: call sites not searched` when the search does not finish | AC-3 | every platform |

The "every platform" rows are the red step on Linux, where the platform-dependent rows pass before the fix. The test that passes the symbols as `-F -w` pins the mechanism, not just the outcome. It is the only test that fails on Linux if a later change reintroduces a platform regex. All of these were written and run against `main` and against the change while this spec was drafted (§0).

`test_bundles_are_within_budget_and_deterministic` (unchanged) keeps guarding determinism with the new sentences.

## 8. Decisions

- **`-F -w` over the alternatives.** `-P` works where git is built with PCRE, which is not guaranteed. A basic expression with `\b` works on macOS only because of a build flag, and on glibc by extension. `[[:<:]]` is BSD-only. Searching files in Python would re-implement `git grep` and its pathspec and binary handling. `-F -w` is plain git on every build.
- **No Unicode normalisation.** §0 shows names are not involved, so no NFC/NFD handling is added.
- **The search failure stays out of `report.md`.** The briefing is where a missing list misleads, and that is where the statement goes. A report warning would need a new channel from `bundle.py` to `report.py` for a rare event.
- **`call_site_hits` lives in `bundle.py`, not `_common`.** It has one caller, and it needs the exit code that `git_paths` discards. `git_paths` stays as it is for its other callers.

## 9. Open design questions

None.
