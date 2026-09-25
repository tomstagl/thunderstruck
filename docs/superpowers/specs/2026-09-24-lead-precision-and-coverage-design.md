# Lead precision and visible coverage — design

**Requirements:** [#19](https://github.com/tomstagl/thunderstruck/issues/19). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-24-lead-precision-and-coverage.md`

Origin: a review of `examples/sample-report.md` from a *Release It!* / Google
SRE perspective. Every false positive named below was reproduced by running
the real `run_detectors` over idiomatic, correct code. Every proposed regex
in §6 was run against those cases *and* the full existing suite on a scratch
copy of the repository when this spec was first written. The plan's
*Verification already done* section records the re-run on the base that
includes #21–#36.

**What this ticket does not cover.** This ticket makes *leads* trustworthy
and shows what the scan did *not* look at. The other half of the problem is
a finding whose evidence all resolves but whose conclusion is wrong, for
example "no timeout" when a wrapper sets one. That half needs a second model
pass that tries to refute each finding, and it has its own ticket,
[#37](https://github.com/tomstagl/thunderstruck/issues/37). Nothing here
depends on it. §3 and §7.4 narrow the same gap from the deterministic side.

**What merged since the first draft, and what that changes here:**

| Merged | Consequence for this design |
|---|---|
| #25/#31 canonical tracked paths | §2.4 indexes canonical paths only, so there are no duplicate index entries. §2.1 uses `c.tracked_index`, not `git ls-files` text. |
| #25/#31 `VALIDATION_RULES` | §3 raises it to 3, so `high` findings validated under the old gate are investigated again rather than carried forward. |
| #26/#29 sample freshness in CI | AC-19's regenerated sample is checked in CI. |
| #30/#36 citable ranking | Every file is either a candidate or `not_citable` (symlink, submodule, non-UTF-8 name). §2.1 adds that as a bucket, so the counts add up to `tracked`. |
| #28/#34 inert report text | Commit subjects (§2.3) are repository-written text and go through `mdtext.text`. The same holds for suppression reasons (§8): the profile is repository content. |
| #22/#23, #33/#35 links | Commit refs are already linked. §2.3 adds the subject after the link. The "no finding" list is now *Hotspots investigated with no finding* (§2.4). |

## 1. Architecture

No stage changes shape. The deterministic pipeline gains inputs and outputs;
the investigator gains context; the model boundary does not move.

```
signals.py   + coverage_gaps        (what was not looked at, and why)
             + dormant[]            (Tier A leads in files outside the window)
             + retry_layers[]       (code + config + library-default retries)
             + suppressed[]         (profile suppressions that matched)
             + config languages     (yaml, properties)
             + commit classifier v2 (fix / resilience / feature / refactor)
bundle.py    + "Retry layers in this repository" section
             + D-bundles for dormant files (opt-in)
validate.py  + high needs a *fix-classified* commit
report.py    + Not scanned · lead precision · commit subjects · dormant list
             + findings indexed under every file cited as code evidence
calibrate.py + --summary (counts only, safe to paste publicly)
```

The governing rule holds: everything above is deterministic. Bundles stay
byte-identical on an unchanged repo (every new list is sorted; nothing carries
a timestamp or an absolute path).

## 2. Report honesty

### 2.1 Not scanned (`coverage_gaps`)

`signals.build` already loads `c.tracked_index(repo)` (#36). Each entry in
it lands in exactly one bucket, first match wins:

| Bucket | Rule |
|---|---|
| `excluded:<reason>` | `Filters.exclusion_reason(rel)` returns `test`, `generated`, `vendored`, `build`, `migration`, `asset`, `tooling`, `profile` or `path` |
| `unsupported:<ext>` | `detect_language` is `None` |
| `not_citable` | the #36 rule: not UTF-8, a `path_problem`, or a `tracked_file_problem` (symlink, submodule, missing from the working tree). The count equals `counts.files_not_citable` for changed files, and it also covers unchanged ones. |
| `unchanged` | supported, citable, not excluded, no commit in the window |
| `considered` | everything else |

The citability check for unchanged files costs one `lstat` each, and the
index is already in memory. Nothing is opened.

`Filters.excludes_path` becomes `exclusion_reason(rel) is not None`, so the
two can never disagree. `hotspots.json` gains:

```json
"coverage_gaps": {
  "tracked": 1840,
  "considered": 212,
  "unchanged": 901,
  "not_citable": 2,
  "excluded": {"test": 402, "generated": 31, "migration": 12},
  "unsupported": {".kt": 212, ".md": 40, "other": 28}
}
```

`unsupported` keeps the 8 largest extensions and folds the rest into
`other`. `report.py` renders a **Not scanned** section right after *Run
warnings*. When an unsupported extension is a known programming language
(`.kt .kts .scala .go .rb .cs .rs .php .swift .groovy`), it also adds a run
warning: `212 Kotlin files (.kt) were not scanned — no detectors exist for
this language.` This is the "degradation is visible" rule applied to
coverage.

### 2.2 Lead precision in the coverage table

The *Pattern coverage* table's `Files with a lead` column reads as a risk
census. It is detector output. The table becomes:

| Column | Source |
|---|---|
| `Files with an unconfirmed lead` | files with a lead of this pattern, minus the files where a validated finding cites that pattern's lead (so the column means what it says) |
| `Leads read` | detector hits inside investigated hotspots |
| `Leads confirmed` | distinct `detector` refs of this pattern cited by a finding that passed validation |
| `Findings` | as today |

A footnote under the table: *"0 leads" means no file matched the detector's
anchor. It does not mean the pattern is present.* `report.json` gains
`lead_precision: {S01: {"read": 7, "confirmed": 1}, …}`. Over many runs,
this is the per-pattern precision signal for repos we cannot see (§9).

### 2.3 Commit subjects next to commit refs

`report.py` resolves each `commit` ref with
`git log -1 --format=%s <sha>`, read through `c.git_paths` so a subject that
isn't valid UTF-8 can't crash the run. It renders the subject with its class
(§4) after the existing commit link (#23):

```
- _commit_ [`cab143e`](…/commit/cab143e…) — "fix: timeout again on large releases" (fix) — 5th timeout fix in the window
```

The subject is text the scanned repository wrote, so it goes through
`md.text` like every other repository-written value (#34). It can never
become a link, an image or report structure. The class is the tool's own
vocabulary. The investigator's note stays, but a reader can now see the
history itself instead of trusting its summary.

### 2.4 Findings that span files

`render_index` files a finding under `location.file` **and** under every
file cited as `code` evidence. Since #31, every one of those paths is
canonical, so `./a.ts` and `a.ts` can't produce two entries. Secondary
entries carry `"via": "evidence", "anchor": "<location.file>"`. The guardrail
renders them as
`- FR-001 (cited as evidence; finding is on src/client/releases.ts): …`.
The guardrail stays stdlib-only and the change is additive, so its
constraints hold.

**Staleness per file.** The guardrail compares each index entry's
`content_hash` with the file on disk. Today that hash is taken only for
`location.file`. `validate.py` therefore also writes
`evidence_hashes: {path: sha256}` for every cited code file. Like `key` and
`content_hash`, the field is owned by the validator: `save_finding.py`
strips it from model output. `render_index` takes a secondary entry's
`content_hash` from it, so an edit to the cited file marks exactly that
entry stale.

In the report, a hotspot whose file is cited as code evidence by another
hotspot's finding stays in *Hotspots investigated with no finding* (#35).
Its line says *"no finding of its own; cited as evidence by FR-001"*
instead of the investigator's note alone. The finding id is the tool's own
text.

## 3. The `high` confidence gate

Today `high` needs any commit that touched the file, so "most recent change
to this file" passes (sample report FR-002 to FR-005). The rule becomes: at
least one `commit` evidence item must (a) touch a cited file, as today,
**and** (b) corroborate. A commit corroborates when either:

- `classify_commit` (§4) labels its subject `fix`; or
- the finding's `missing_patterns` is exactly `["OTHER"]` **and** the commit
  *introduced* a line inside a cited `code` range. The check is
  `git blame --porcelain -L <start>,<end> -- <file>` on the working tree,
  one call per cited range, cached. Only the SHAs it reports count, and
  uncommitted lines (the all-zero SHA) never match.

The second rule exists because an `OTHER` finding such as a
prompt-injection comment has no fix history: the text itself is the defect,
and the commit that wrote it is the corroboration. It is mechanical, like
the first. `git blame` rather than `git log -S` because blame answers "who
wrote *these* lines" exactly and doesn't depend on the text being unique.
Sample FR-003 keeps `high` under this rule, and a test pins that.

Rejection text:

> `confidence is 'high' but no cited commit is a fix. The most recent change
> to a file is not corroboration; cite the fix commits from the bundle's
> history, or use 'medium'.`

For an `OTHER`-only finding the text adds: `…or the commit that introduced
the cited lines.` The investigator prompt gains the same rule. It costs one
`git log -1 --format=%s` per commit ref (cached like `_sha_cache`), plus one
blame per cited range for `OTHER`-only findings.

**Stale findings.** `c.VALIDATION_RULES` goes from 2 to 3. `bundle.py`
already treats a findings file stamped with an older version as uncached
(#31), so no `high` finding that passed the old gate is carried forward.

## 4. Commit classification v2

`FIX_KEYWORDS` mixes *intent* (fix, revert, crash) with *vocabulary*
(timeout, retry, 429). As a result, resilience work makes a file look
fragile: "Add retry with exponential backoff and jitter" counts as a fix,
and the investigator reads repeated fixes as "root cause never addressed".
The new `classify_commit(subject, extra_fix)`:

1. A Conventional Commits prefix `^(\w+)(\([^)]*\))?!?:` wins.
   `fix|hotfix|bugfix|revert` → `fix`; `refactor|style|chore|build|ci|deps`
   → `refactor`; `feat|feature|perf|docs|test|tests` → `feature`.
2. `^Revert "` → `fix`.
3. `FIX_INTENT` (fix, bug, hotfix, revert, regression, crash, outage,
   incident, deadlock, hang, stall, leak, oom, broken, repair, plus the
   profile's `[history] fix_keywords`) → `fix`.
4. `RESILIENCE` (retry, backoff, jitter, timeout, 429, rate limit, throttle,
   circuit breaker, idempotent, dedupe) → `resilience`.
5. `REFACTOR_KEYWORDS` → `refactor`; otherwise `feature`.

`patch` is dropped: "chore: patch version bump" is not a fix. `fix_commits`
counts `fix` only. Bundles label `resilience` commits, so the investigator
can say "three resilience changes and still failing", which is a stronger
claim than a fix count. Non-English teams add their words through
`[history] fix_keywords = ["behoben", "Fehler", "corrige"]`, matched as
case-insensitive whole words.

`classify_commit` moves from `bundle.py` to `_common.py`, together with the
keyword sets it reads. `signals.py`, `bundle.py`, `validate.py` (§3) and
`report.py` (§2.3) then share one definition, and the same subject can't be
a fix in one stage and a feature in another. The validator reads the
profile's `fix_keywords` the same way `signals.py` does, so a German `fix`
counts for the gate too.

## 5. Dormant integration points

**Problem.** Candidates are only files with a commit in the window. The
classic *Release It!* integration point, an old client wrapper with no
timeout that everything calls, has zero churn and is never considered.

**Mechanism.** After ranking, `signals.py` sweeps the `unchanged` bucket
(§2.1) in path order, capped by `--dormant-limit` (default 3000 files; past
the cap a run warning says how many were skipped). Only detectors of
patterns marked `dormant: true` in the catalog run. Those are S01, S02,
S03, S04, S05, S10, S27, S28 and S30, which describe integration points and
blocked threads. A file qualifies with at least one hit of confidence
`medium` or `high`, or two `low` hits from different patterns. Ordering is
by `(-stability_weight, last_modified ascending, path)`. `last_modified`
takes one `git log -1 --format=%aI` per qualifying file, and only for the
first `3 × --dormant` of them.

`hotspots.json` gains `dormant: [...]` (ids `D01…`, default `--dormant 5`),
with the same row shape as a hotspot and `churn` zeroed except
`last_modified` and the last SHA. The report lists them under **Dormant
integration points**, with the lead ids and the date of the last change.

**Investigation is opt-in.** `/thunderstruck-scan --investigate-dormant N`
(default 0) builds `D` bundles. Their history section reads *"No commits in
the window. Last change: <date> <sha> <subject>."* Dormant bundles count
against the same ≤4-parallel cap and add at most N to the run. The plugin
still does not exhibit S05.

## 6. Detector engine and precision changes

### 6.1 Engine

- **`require` on `regex` detectors.** This has the same meaning as on
  `file_absent`: the file must match it somewhere, or the detector is
  skipped. It is five lines in `_run_regex`, prototyped and verified.
- **Python docstrings.** `_PY_DOCSTRING_START` currently blanks *any*
  triple-quoted string that opens a line. So the SQL in
  `cur.execute(\n    """\n    SELECT …\n    """)` is invisible (verified:
  S08-select stays silent on it). The rule inverts: a triple quote that
  opens a line is a **string** only when it continues an expression, and a
  docstring otherwise. It continues an expression when, at that point,
  - the bracket depth is above 0 (an open `(`, `[` or `{` outside strings
    and comments), or
  - the previous code line ends with `=`, `,`, `\`, or a binary operator.

  Everything else stays a docstring: the first statement, a docstring after
  `def f(\n    a,\n) -> int:`, and an attribute docstring after `x = 1`.
  A first draft keyed on "the previous line is a `def`/`class` header"
  failed on multi-line signatures. The re-verification on the current base
  caught that, and it would have let prose satisfy absence detectors such
  as S03. A string is copied verbatim to its closing quote, including any
  `#` inside it (today a `#` inside a multi-line string blanks the rest of
  that line). The same applies to a triple quote that opens mid-line
  (`Q = """`).
- **Config languages** (§7) strip `#` comments. For YAML, a `#` counts at
  line start or after whitespace, outside quotes. For `.properties`, a `#`
  or `!` counts as the first non-blank character.

### 6.2 Precision changes (all verified on a scratch copy)

| Detector | False positive reproduced | Change |
|---|---|---|
| S19-py-except-pass (high) | `except ImportError: pass`, `except FileNotFoundError: pass` | Pattern matches only bare `except:`, `except Exception` and `except BaseException`. A narrow typed swallow is deliberate. |
| S19-py-bare-except | cleanup, then bare `raise` | `absent_within: '^\s*raise\s*$'`, window 8, offset 1 |
| S04-py-bare-except-retry | `for line in lines: try … except Exception: log; continue` | `continue` alone no longer counts. Requires a retry-shaped loop header (`for _ in range`, `for attempt…`, `while`) or retry vocabulary within 6 lines before/after |
| S07-py / S07-ts insert-without-upsert | insert guarded by a unique constraint and a duplicate-key handler | `absent` also accepts `IntegrityError`, `UniqueViolation`, `DuplicateKey`, `P2002`, `E11000`, `ER_DUP_ENTRY`, `23505` |
| S08-py-query-all-without-limit | `np.isclose(a, b).all()` | `require`: a DB import (sqlalchemy, django, psycopg, sqlite3, pymongo, …), a `.objects` manager, or a `*.execute(` |
| S08-{py,ts}-select-without-limit | `SELECT … WHERE id = %s`, `SELECT count(*)` | `absent_within` also accepts aggregate selects, `WHERE [x.]id =`, `FETCH FIRST` and `TOP n` |
| S05-py-http-without-limiter | `requests` used once, plus an unrelated `for` anywhere in the file | Anchor is now an HTTP call *inside* a loop body (≤8 lines, deeper indent) or inside `gather`/`.map`. A file-wide `for` no longer qualifies. |
| S11-py / S15-py | `from requests.adapters import …` / `except requests.exceptions.…` counted as a call | Anchor excludes `requests.exceptions`, `.adapters`, `.codes` and the exception class names |
| S06-py / S13-py | a function-local `with ThreadPoolExecutor() as pool` | Anchor needs a *shared* queue or pool: module-level assignment or `self.x =`. A local pool serves one caller. |
| S19-ts-empty-catch (high) | `catch (_ignored) {}` | Same convention as Java: `_…`, `ignored`, `expected` and `unused` parameter names are exempt |
| S17-ts-cache-without-ttl | function-local `const m = new Map()` used as a lookup index | Anchor is a module-level or class-field `new Map`. This also fixes a **false negative**: `new Map<K, V>()` with generics never matched `new\s+Map\s*\(` |
| S14-ts-unbounded-queue | Redux state `buffer: []`, local `const buffer = []` | Anchor is a module-level, class-field or `this.` queue/buffer/backlog |
| S08-ts-unbounded-promise-all | `Promise.all(REGIONS.map(…))` over a 3-element const | An ALL_CAPS receiver is a bounded constant. The `(?i)` is scoped so it doesn't leak into that alternative. |
| S04-ts-retry-without-discrimination | `async-retry` with `bail()` on 404 | `absent` also accepts `bail(`, `AbortError` (p-retry), `onFailedAttempt` and cockatiel `handleWhen/Type/Result` |
| S06-ts | `import throttle from 'lodash/throttle'` in a React hook | Anchor is a module-level or class-field queue/limiter/worker/pool declaration, never an import |
| S27-java-blocking-in-reactive | `…subscribeOn(boundedElastic())` 13 lines down a Reactor chain | `window` 12 → 20 |

**Reviewed and kept as leads.** These are not false positives the code can
decide:

- `findByOrderId` (S08-java) is bounded only by the domain.
- `@Retry`/`@CircuitBreaker` without `fallbackMethod` (S15-java) still throws.
- `@Scheduled(cron)` on an instance that is single "by deployment" (S16-java).
- A `static synchronized` lazy init that validates a connection (S28).
- An empty `catch (NumberFormatException e)` without the `ignored` name (S19-java).
- A module-level `_cache = {}` over a bounded domain (S17-py): its
  confidence drops to `low`, because boundedness of the key domain is
  undecidable from text.

All of these are what **suppression** (§8) is for.

## 7. Configuration scanning

### 7.1 Languages

```yaml
languages:
  yaml:       { extensions: [".yml", ".yaml"], rank_only_with_leads: true }
  properties: { extensions: [".properties"],   rank_only_with_leads: true }
```

`rank_only_with_leads`: a config file enters the hotspot ranking only if it
carries at least one detector hit. `values.yaml` churns constantly. Without
this flag it would take investigator slots on churn alone. lizard does not
parse config, so `ccn_max` is 1 and the complexity axis sits at its floor.
The stability weight carries these files.

New default excludes: dirs `.github`, `.circleci`, `.gitlab`; globs
`.gitlab-ci.yml`, `docker-compose*.y*ml`, `mkdocs.yml`,
`.pre-commit-config.yaml`, `openapi*.y*ml`, `swagger*.y*ml`,
and `<tool>.config.*` for named build and test tools (`playwright`,
`vitest`, `vite`, `jest`, `webpack`, `next`, `eslint` and similar) (tooling).
CI and tooling configuration fails builds, not production. A blanket
`*.config.ts` was the first draft. Review found it also dropped runtime
configuration such as NestJS `database.config.ts` and Angular
`app.config.ts`, which hold exactly the timeouts and pool sizes this tool
looks for, so only named tools are excluded.

### 7.2 Detectors (all `confidence: low` until calibrated)

| Id | Kind | Anchor / rule |
|---|---|---|
| `S01-yaml-virtualservice-no-timeout` | file_absent | anchor `^kind:\s*VirtualService\b`, require `^\s*http:\s*$`, absent `^\s*timeout:\s*\S` |
| `S10-yaml-mesh-retry` | regex, inventory | `^\s*retries:\s*$`, present_within `^\s*attempts:\s*[1-9]` (window 4) |
| `S10-yaml-resilience4j-retry` | regex, inventory | `^\s*max-?[Aa]ttempts:\s*[2-9]`, require `^\s*resilience4j:\s*$` |
| `S10-properties-resilience4j-retry` | regex, inventory | `^\s*resilience4j\.retry\.[\w.-]+\.max-?[Aa]ttempts\s*[=:]\s*[2-9]` |
| `S30-yaml-liveness-checks-dependencies` | regex | `^\s*livenessProbe:\s*$`, present_within (window 6) a `path:` of `/actuator/health` (the aggregate, not `/liveness`), `…/health/{db,deep,full,all,deps,dependencies,downstream,readiness}`, `/ready`, `/readyz` |

The rules were run by hand against positive and negative YAML; the plan
turns each case into a sample.

### 7.3 New pattern S30

```yaml
- id: S30
  name: Liveness checks only the process itself
  tier: A
  weight: 1.0
  metastable_role: sustaining
  dormant: true
  failure_if_absent: >-
    A liveness probe that checks a dependency restarts healthy pods when the
    dependency slows. Restarts cut capacity, the survivors take more load and
    fail their probes too: the restart loop outlives the original blip.
  references:
    - "Kubernetes docs — Configure Liveness, Readiness and Startup Probes"
    - "Nygard, Release It! (2nd ed.), ch. 4 — Chain Reactions"
```

### 7.4 Retry-layer inventory

The SRE book's retry amplification (R retries at N layers make R^N requests)
is invisible when the layers live in different files: app code, a mesh
`VirtualService`, a library default. Detectors tagged `inventory:
retry_layer` feed a repo-wide list. Detectors tagged `score: false` never
add to `stability_weight`:

- code: existing S10 module hits, plus `@Retryable`/`RetryTemplate` hits;
- config: the S10-yaml and S10-properties detectors above;
- library defaults (`score: false`):
  - `S10-py-boto3-default-retries`: `boto3.client(`/`.resource(` without
    `retries` within 6 lines. Botocore retries by default.
  - `S10-java-feign-default-retryer`: `Feign.builder()` without
    `.retryer(` within 12 lines. Plain Feign's `Retryer.Default` makes up
    to 5 attempts.
  - `S10-ts-aws-sdk-default-retries`: `new \w+Client(` in a file importing
    `@aws-sdk/`, without `maxAttempts`. The v3 default is 3 attempts.

`hotspots.json.retry_layers` is sorted by `(kind, file, line)`. Every
bundle whose file has an S02, S04 or S10 lead gets a **Retry layers in this
repository** section of at most 15 entries, with a "+N more" line. When a
mesh file changes, those bundles' hashes change and their cached findings
are recomputed. That is the correct invalidation.

## 8. Suppression

```toml
[[suppress]]
detector = "S16-java-scheduled-no-jitter"   # a detector id, or a pattern id for all its detectors
path     = "src/main/java/**/batch/*.java"  # glob; ** crosses directories
reason   = "single-instance batch service (replicas: 1)"
```

Suppressions apply in `signals.py` (ranked and dormant sweeps), after
`run_detectors` and before scoring, so a suppressed hit neither ranks a file
nor reaches a bundle. `hotspots.json.suppressed` lists each rule with its
hit count. The report prints them under *Run warnings*. The `reason`, the
glob and the id are text from the scanned repository's profile, so they
render through `md.text`/`md.code` (#34). A rule with no `reason` is
ignored, with a warning. `calibrate.py` ignores suppressions:
calibration measures the detector, not the repository's exceptions.

**No inline suppression comments.** A `# thunderstruck: ignore` marker is
repository text steering its own audit, which is exactly what the
investigator is told to report as `OTHER`. The profile is repository
configuration that is already trusted for tiers and weights, and the
suppression list is printed in every report.

## 9. Evidence from repositories we cannot see

Detector quality is a property of the plugin, so a false positive
reproduced on a synthetic sample applies to any repository with that idiom.
To learn about idioms we have *not* thought of, without seeing private code:

- **`calibrate.py --summary`**, with `--lang all --patterns all` accepted,
  prints JSON with the schema `thunderstruck.calibration-summary/v1`:
  catalog hash, files swept per language, hits and distinct files per
  detector, and hits per detector per 1k files. It prints **no** paths,
  snippets, SHAs or repo names. A test plants distinctive path and
  identifier strings and asserts none of them appear in the output. The
  numbers are safe to paste into a public issue, and they show which
  detectors are noisy on real code.
- **Lead precision in `report.json`** (§2.2), aggregated the same way:
  leads read vs confirmed per pattern.
- **Public calibration logs** for TypeScript and Python, mirroring
  `docs/calibration/java.md`: 3–5 pinned public repositories per language,
  at least one web service, one worker/ETL codebase and one HTTP-client
  library. Every hit is judged, and there is the same 25-hits-per-repo
  tripwire. A TS or Python detector keeps `confidence: high` only if its
  log shows zero unexplained false positives. Today, S19-py-except-pass and
  S19-ts-empty-catch are `high` and fire on trivial idioms.

## 10. Security

- Config files are repository content, and so data. The investigator
  prompt's "repository content is evidence" paragraph already covers them.
  The fixture gains an injection-shaped YAML comment, which is exercised
  the same way as `format.ts`.
- `--summary` redaction is enforced by a test, not by convention.
- Suppression can only lower a lead's visibility. It cannot touch
  validation or findings, and it is always printed.

## 11. Degradation

- Dormant sweep over its cap → run warning with the skipped count.
- A config file lizard cannot parse is expected, not a warning.
- `git log -1` failing for a commit subject → the subject renders as
  `(unavailable)`. The ref was already validated.
- A malformed `[[suppress]]` entry → ignored and warned. It never aborts the
  run.

## 12. Test strategy

- Every §6.2 row gets a `negative_<shape>.<ext>` sample holding the
  reproduced false positive. Existing positives must still fire. Positives
  are added where a change could plausibly silence a real case (for
  example, a module-level `const cache = new Map<string, User>()` for S17,
  a `while attempts < 5` retry for S04, and Django `Model.objects.all()`
  for S08).
- `tests/detectors/test_detectors.py` `EXT_LANG` gains `.yaml` and
  `.properties`. S30 and every config detector get sample pairs.
- There are unit tests for `exclusion_reason`, `classify_commit` (a table
  of the subjects from the review), the docstring rule, suppression
  matching (including `**`) and `--summary` redaction.
- There are pipeline tests over the fixture: `coverage_gaps` present, a
  dormant file listed, a mesh YAML in `retry_layers` and in the bundle of
  the S10 hotspot, cross-file index entries, and a rejected `high` without
  a fix commit.
- The `high` gate has both sides tested: an `OTHER`-only finding citing the
  commit that introduced its lines passes, and a commit that touched the
  file elsewhere fails. The same introducing commit on a finding that also
  names `S01` fails. An uncommitted cited line never matches.
- `coverage_gaps` buckets add up to `tracked`, and a tracked symlink lands
  in `not_citable`, not `unchanged`.
- A secondary index entry goes stale when its own file changes, not when
  the anchor file does.
- The inert-text tests (#34) gain a commit whose subject is
  `[x](https://evil) <img src=x> # heading`, and a suppression reason
  shaped the same way. Both render as literal text under both
  renderers.
- `test_bundles_are_within_budget_and_deterministic` still passes with the
  new sections.
- The guardrail keeps its latency and stdlib-only tests.

## 13. Decisions and rationale

- **List dormant files and investigate them opt-in, not by default.**
  Investigating by default would silently double subagent spend. A list
  costs nothing and makes the blind spot visible.
- **Fix-classified commit for `high`, not "N commits".** A count can still
  be satisfied by feature work. A fix subject is mechanical and checkable.
  It won't catch a mislabelled commit, but that is a much smaller hole.
- **`OTHER` findings may cite the introducing commit** (decided on #19).
  Injected text has no fix history. The commit that wrote the cited lines
  is the strongest corroboration there is, and `git blame` checks it
  mechanically. The exception is limited to findings whose only pattern is
  `OTHER`, so a stability finding can't use it to skip the fix-history
  requirement.
- **Wrong conclusions are not addressed here.** This ticket makes leads and
  their citations trustworthy. A finding whose refs all resolve but whose
  reasoning is wrong needs a model-side refutation pass. That pass is #37,
  and it is opt-in, to keep the default cost unchanged.
- **`rank_only_with_leads` for config.** Config churn measures deployment
  activity, not fragility.
- **Narrow excepts are not swallows.** `failure_if_absent` for S19 is
  "silent data drift on a write path". An `ImportError` at import time or a
  `FileNotFoundError` on delete is not a write path.
- **Suppression lives in the profile only** (§8).
- **Migrations stay excluded** from the ranking. Schema-change risk is real,
  but it needs its own pattern (locking DDL, non-backward-compatible
  change), not the current detectors. It is now visible under *Not
  scanned*.

## 14. Open design questions

- Should `rank_only_with_leads` also apply to code languages in monorepos,
  where UI components dominate churn and complexity?
- Should the dormant sweep weight files by fan-in (how many files import
  them)? That needs an import graph per language, which is not deterministic
  across build systems.
- Should Helm templates (`{{ }}`) be rendered before scanning, or scanned as
  text (v1: as text)?
