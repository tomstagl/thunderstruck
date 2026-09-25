# Changelog

All notable changes to thunderstruck are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## 0.8.0

Trustworthy leads and visible coverage (#19).

### Added

- **Not scanned.** `report.md` says what the scan did not look at: files with no commit in the window, files no finding could cite, excluded paths by reason (tests, generated code, vendored code, migrations, tooling and CI config, the profile, `--path`), and extensions with no detectors. A programming language with no detectors, such as Kotlin or Go, gets a run warning with its file count. `hotspots.json` and `report.json` carry `coverage_gaps`.
- **Lead precision.** The pattern coverage table shows files with an unconfirmed lead, leads read, and leads confirmed, with a note that 0 leads does not mean the pattern is present. `report.json` carries `lead_precision`.
- **Dormant integration points.** Files untouched in the window that carry timeout, retry, pushback or blocking-call leads are listed (`--dormant N`, default 5; the sweep is capped by `--dormant-limit`, with a warning when the cap is hit). `/thunderstruck-scan --investigate-dormant N` investigates the first N inside the usual parallel cap.
- **Configuration scanning.** `.yaml`/`.yml` and `.properties` are scanned and rank only when they carry a lead. New detectors: Istio VirtualService without a route timeout (S01), mesh and resilience4j retry layers (S10), and a new Tier A pattern **S30**, liveness probes that check dependencies instead of only the process.
- **Retry-layer inventory.** `hotspots.json` `retry_layers` lists every retry layer in the repository: code, mesh and resilience4j config, and library defaults nobody configured (boto3, Feign, AWS SDK v3). Every hotspot that retries is briefed with all of them.
- **Suppression.** `[[suppress]]` rules in `.thunderstruck.toml` silence a detector or pattern on a path glob, with a required reason. Every rule is printed in every report with its hit count. There are no inline suppression comments.
- **`calibrate.py --summary`** prints hit counts per detector and nothing that identifies the repository, so noise on private code can be reported publicly.
- **Commit subjects in the report.** Every cited commit shows its subject and class next to the link.
- **Findings that span files.** `index.json` files a finding under every file it cites as code evidence, so the guardrail warns on those files too ("cited as evidence"). A hotspot cited by another finding is no longer presented as clean.
- Calibration logs for configuration, TypeScript and Python under `docs/calibration/`.

### Changed

- **`high` confidence needs a corroborating commit**: a cited fix to the cited code, or, for an `OTHER`-only finding, the commit that wrote the cited lines. The most recent change to a file is no longer enough. Findings validated under the old rule are re-checked (`VALIDATION_RULES` 3).
- **Commit classification.** A Conventional Commits prefix wins, and resilience work (retry, backoff, timeout, rate limit) is its own class instead of a fix, so hardening a file no longer makes it look fragile. `[history] fix_keywords` adds fix words for non-English commit subjects.
- **Detector precision.** 18 reproduced false-positive shapes on correct Python, TypeScript and Java code no longer fire, each with a negative sample. S17-ts now sees `new Map<K, V>()`. S17-py drops to `low`. S27's offload window grows from 12 to 20 lines.
- **Default excludes** cover Django `tests.py`, `*_tests.py`, Cypress, benchmarks, named build and test tool configs, `*.d.ts`, `*.pyi`, generated directories, OpenAPI specs and CI configuration.

### Fixed

- A profile's `exclude_dirs`, `exclude_globs` and `exclude_authors` were ignored: `Filters.from_profile` extended the lists after they had been compiled.
- A `.thunderstruck.toml` that is not valid UTF-8 is reported as unreadable instead of crashing the report.
- A triple-quoted Python string passed as an argument, such as SQL given to `execute()`, is no longer blanked as a docstring, so detectors see it.

## 0.7.0

### Fixed

- **The scan ranks only files a finding can cite** (#30). Ranking and validation now share one rule for "a file".
  - Tracked symbolic links and submodules no longer rank as hotspots, so they no longer spend a `--top` slot and always land under *Incomplete*.
  - Files whose names contain non-ASCII characters, such as `src/módulo/a.ts`, are ranked. Git's quoting used to hide them from the scan.
  - A file whose name contains glob characters, such as `pages/[id].tsx`, is briefed with its own history only. Commits that touched only `pages/i.tsx` no longer appear in its briefing.
  - A non-ASCII hotspot's briefing names it unquoted in diff headers, and no longer lists the hotspot as its own caller.
  - A file or author name that isn't valid UTF-8 no longer crashes ranking. Such a file is skipped and counted.

### Added

- `hotspots.json` `counts.files_not_citable`: how many changed, tracked entries in a supported language were skipped because no finding could cite them. Nothing is added to the report's warnings.

## 0.6.0

### Added

- **Links for every listed file** (#24). Every file in the ranked hotspots table, *Hotspots investigated with no finding* and *Incomplete* links to the whole file at the scanned commit, including in a report with no findings.
- Each ranked hotspot also links to the file's change history up to the scanned commit, on GitHub, GitLab and Bitbucket. That history is the churn that earned the hotspot's rank. Custom URL templates get no history link.
- `report.json` carries `url` on hotspot, clean and incomplete entries, and `history_url` on hotspots. Each is `null` when unlinked. `index.json` is unchanged.

### Changed

- The warning about files that differ from the scanned commit names the first five, then "… and N more".
- **Possibly breaking for custom templates:** `code_template` and `commit_template` may no longer contain whitespace, control characters, or ``| ( ) < > [ ] ` \ "``. Those would break a link or a table row. A template containing one disables linking, with a warning naming the character.
- A code template with `{start}` or `{end}` before `#` has no whole-file form, so listed files stay plain, and a warning now says so.
- Git receives the paths to check in chunks, so a large `--top` can't overflow a command line and leave the whole report unlinked.

## 0.5.1

### Security

- Text a model or a scanned repository wrote can no longer render as a link, an image, HTML or report structure in `report.md` (#28). That covers finding fields, evidence notes, clean notes, validator errors, warnings, file names, symbols, and the repository and branch names.
  - Any word in that text that could hold a link (URLs, e-mail addresses, `@`, domain-like words such as `api.example.com` or `deploy.py`) or an emoji shortcode is shown as code, not clickable. A quoted endpoint stays visible and copyable.
  - Control and bidirectional-override characters are shown as `\uXXXX`, so a field can't hide text or reverse what the reader sees.
  - The only links left in the report are the tool's own evidence links.
- The test suite renders the report with GitHub's engine (`cmarkgfm`) and with a VS Code-like renderer (`markdown-it-py` with `linkify-it-py`), including a seeded fuzz test. CI requires those tests; locally they skip when the packages are missing.

## 0.5.0

### Changed

- **Stricter finding validation** (#25).
  - A cited path must name a file git tracks, relative to the repository root, and stay inside it. Absolute paths, `..`, untracked, ignored, symlinked and submodule paths are rejected, never rewritten or opened.
  - Every line range must lie inside its file with start ≤ end, including a finding's `location.lines`.
  - Paths to dotfiles are no longer misread (`.github/x.py` was read as `github/x.py`).
  - `./src/a.ts` and `src/a.ts` now share one stable key, one `index.json` entry and one guardrail lookup.
- **Findings validated by 0.4.0 or earlier are re-checked once** on the next scan. Those that still pass are reused; those that fail today's rules are investigated again, and `bundle.py` says how many. The report shows only findings validated under the current rules; anything else is listed as Incomplete with the reason.
- The sample report's two overrunning line ranges (`api.ts`, `format.ts`) are clamped to their files and regain their line anchors.

## 0.4.0

### Added

- Source links in the report. Each finding's location and every `code`,
  `detector` and `commit` ref in `report.md` links to the cited lines, or the
  commit, at the scanned SHA on GitHub, GitLab or Bitbucket; other hosts are
  configured with a `[links]` table. `report.json` carries the same URLs and
  a `links` object (#22).
- A cited file that differs from the scanned commit is left unlinked and
  named, so no link opens other lines than the ones cited. Credentials in a
  remote URL never reach the report, and every reason links could not be
  built is printed under *Run warnings* (#22).

## 0.3.1

### Fixed

- Skills no longer depend on the model resolving plugin paths by hand. The
  `$T` shorthand is gone: every command names its script by the full
  `${CLAUDE_PLUGIN_ROOT}` path, and references, the example config and the
  catalog are named by substituted paths too. A regression test fails on any
  unset shell variable in a skill command, and on any plugin path that is
  not anchored or does not exist (#20).
- `signals.py` warns on stderr when the plugin runs from a git checkout. A
  local-directory marketplace or `--plugin-dir` runs that working tree in
  place, so its branch and uncommitted edits decide what a scan checks (#20).
- The README says that a local-directory install is a development mode that
  runs the checkout live (#20).

## 0.3.0

### Added

- Java as a scanned language, with detectors for every existing pattern
  (`S01`–`S19`) and three new patterns: `S27` (no blocking calls on
  event-loop threads), `S28` (locks and waits with a bound) and `S29`
  (bounded query fan-out — no N+1 lazy loading). Framework coverage spans
  Spring (MVC, WebFlux, WebClient, RestTemplate), Hibernate/JPA, Kafka,
  resilience4j, gRPC, Akka, JMS and RabbitMQ. Every Java detector is
  `low` or `medium` confidence. None claims `high` in this pass, because a
  regex over Java has no AST to lean on. Four detectors are `medium` (the
  `java.net.http` client and request timeouts, and the two empty-catch
  detectors). Each has at least one real-world true positive and no unfixed
  false positive in the final calibration sweep. The rest are `low`.
- `scripts/calibrate.py`, which sweeps a real repository with a chosen set
  of patterns so a detector's precision can be judged against code nobody
  wrote for the test, not just its synthetic samples. The full calibration
  log, with every hit's file:line and verdict, is at
  [`docs/calibration/java.md`](docs/calibration/java.md).

## 0.2.0

### Added

- Service context (#1): a scan can know which services depend on this one,
  and which it depends on, from your service catalog. `context.py` runs a
  command you configure under `[context]` in `.thunderstruck.toml` and
  approve per machine (`--show` prints the definition hash, which covers
  any repo-local script it runs; `--approve --expect <hash>` trusts exactly
  that), reads Backstage `relations[]`, and every bundle lists
  the 1-hop neighbours. Findings may cite an edge as `catalog` evidence,
  which `validate.py` resolves against the snapshot the bundle was built
  from. The report and the edit guardrail name cited neighbours. The new
  skill `/thunderstruck-context-config` sets it up. Without a `[context]`
  table, nothing changes.

### Fixed

- False positives on correct code, each now pinned by a negative sample:
  - `S01` looked only *after* the call, so a timeout or `AbortSignal` set on
    the line before, or passed through `**kwargs`, still fired at high
    confidence. Detectors now look back a few lines and treat an opaque
    options variable or a kwargs splat as unknowable rather than missing.
  - `S03` fired at high confidence on any file that mentioned 429, including
    one that only maps the status to an error and never retries. It now
    requires retry/wait vocabulary in the file.
  - `S05` fired on every file with a single HTTP call and, being Tier A,
    boosted the ranking of every client file. It now requires a loop or
    fan-out in the file and no longer anchors on client construction such
    as `axios.create(`. `S11` and `S15` share the call-site anchor.
  - `S04` counted `axios-retry`, tenacity and urllib3 `Retry` configuration
    as undiscriminating retries.
  - `S07` treated `Object.create(`, `axios.create(`, `set.add(` and
    `list.insert(` as database inserts.
  - `S08` flagged `Promise.all([a(), b()])` and `asyncio.gather(a(), b())`,
    whose concurrency is fixed by construction.
  - `S16` flagged every `setInterval`, including UI clocks that touch no
    shared dependency; it now needs an I/O-shaped call in the callback.
- `validate.py` accepted any commit SHA that exists as `commit` evidence, so
  a finding could buy `high` confidence with a commit to an unrelated file.
  A commit ref must now have changed the finding's file or a file cited as
  `code` evidence.

### Added

- `file_absent` detectors accept an optional `require` regex that must also
  match somewhere in the file, so a whole-file absence can be scoped to files
  that actually do the thing the pattern guards.

## 0.1.0

First release.

### Added

- `/thunderstruck-scan` — the full pipeline: churn × complexity × missing
  stability patterns, context bundles, investigator subagents, deterministic
  evidence validation, and a ranked report. Supports `--top`, `--since`,
  `--path`, `--dry-run` and `--include-tests`.
- `/thunderstruck-verify FR-001` — turns a finding into a failing test or a
  reproduction, matching the repository's existing test conventions.
- `stability-catalog` — a model-invoked skill that loads the pattern catalog
  when Claude writes or reviews code that crosses a process boundary.
- Stability pattern catalog: 19 patterns across Tier A and Tier B with 57
  detectors for TypeScript/JavaScript and Python, plus 7 Tier C patterns
  catalogued for vocabulary but not scanned.
- `thunderstruck-investigator` subagent: read-only (Read/Grep/Glob), bounded
  to 10 extra file reads, with an explicit rule that repository content is
  evidence and never instruction.
- Deterministic evidence validation. Every `code`, `commit` and `detector`
  ref is resolved mechanically before it reaches the report; invalid findings
  get exactly one repair round, then are recorded as incomplete.
- PreToolUse guardrail hook: warn-only, fail-open, once per file per session,
  medium/high confidence only, with a staleness notice when the file has
  changed since the scan.
- Checkpointing by bundle content hash, so an interrupted scan resumes and an
  unchanged hotspot is never re-investigated.
- Repo profiles (`.thunderstruck.toml`) for re-tiering patterns and declaring
  boundary facts.
- Fixture-based test suite with planted fractures and a negative control, plus
  positive and negative detector samples per pattern per language.

### Notes

- The guardrail runs on `PreToolUse` rather than `PostToolUse`, so the warning
  arrives before the edit. The hooks reference documents
  `hookSpecificOutput.additionalContext` for that event.
- The matcher is `Edit|Write|NotebookEdit`. `MultiEdit` no longer exists in
  Claude Code.
