# Fracture planes: stack-specific judgment, selected deterministically — design

**Requirements:** #112. The problem, users, scope, acceptance criteria (AC-n) and success measures live in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-20-fracture-planes.md`

This document describes how a **plane** carries the judgment that today lives only in detector regexes and in prose written per language, and how that judgment reaches the investigator and the skeptic without making a bundle depend on a model's choice. Examples use generic names.

## 1. The problem in the code today

A pattern says *what* fails (`S01` no timeout). A detector says *where a regex noticed a lead*. Neither says what **counts as protection on a given stack**. That knowledge is real and stack-shaped: a blocking call in a servlet controller is correct and the same call inside a Reactor operator starves the event loop; a `synchronized` block around in-memory work is idiomatic and around I/O is a convoy; `@Retryable` plus resilience4j on one call is two layers. The Java design records these distinctions (`2026-09-23-java-language-support-design.md` §2 and §4), but only as detector design notes. The investigator never sees them, and the skeptic cannot apply them.

Adding a language also has no machine-checked definition of done. The "pattern × language" matrix is a hand-written table (§3 of that spec) and a ledger. Nothing fails when a cell is forgotten.

## 2. The concept

A **plane** is a body of stack-specific judgment about where failure lives: a framework (`java-spring`), a platform (`kubernetes`), or a language idiom set. "Profile" is not used: that word already means the repository's own `.thunderstruck.toml`.

A plane is a directory, auto-discovered like `catalog/`:

```
planes/<id>/plane.yaml     manifest: when it applies, what it covers, what it defers
planes/<id>/rubric.md      prose: per pattern, what counts as protection on this stack
```

```yaml
schema: thunderstruck.plane/v1
id: java-spring
title: Java / Spring Boot services
maturity: seed                 # seed | calibrated
languages: [java]              # catalog language keys (never an alias key: `typescript` covers `.js` too)
detect:                        # the plane is active when ANY rule matches a tracked file
  - {file: "**/pom.xml", contains: "spring-boot"}
  - {file: "**/build.gradle*", contains: "spring-boot"}
supersedes: []                 # plane ids this one replaces wherever both are active
cells:                         # every Tier A/B pattern without a rubric section is declared here
  S06: {na: "no priority queues exist in the Spring stack this plane covers"}
  S12: {planned: "resilience4j CircuitBreaker thresholds"}
```

`rubric.md` has one `## <PatternID>` section per pattern it covers, plus an optional `## General` section. A pattern section must contain a `**Counts as protection.**` paragraph and a `**Does not count.**` paragraph, and may contain a `**Baseline.**` paragraph (what comparable systems ship safely). Beyond those labels the text is free: the labels make a section checkable, the prose leaves the judgment to the reader.

### 2.1 Why the hybrid, and where determinism ends

The model never chooses a plane. A script does, from tracked files, so a bundle is a pure function of the repository, the catalog and the planes. The rubric text is embedded in the bundle and in the skeptic's brief, so both hashes cover it: editing a rubric re-investigates what it touches, and a stale verdict is recognised by `brief_hash`. The model *applies* the text. Whether a particular `@Retryable` counts as protection stays a judgment.

### 2.2 The completeness rule (the gate)

For each plane and each Tier A and Tier B pattern in the catalog, the cell is exactly one of:

| State | Meaning |
|---|---|
| `rubric` | `rubric.md` has a well-formed section for it |
| `na` | the manifest declares it with a reason: the failure does not exist on this stack |
| `planned` | the manifest declares it with a reason: known gap |
| `missing` | none of the above. This fails the build |

Further rules, all failures: a pattern with both a rubric section and a `cells` entry; a rubric section or `cells` entry naming an ID that is not a Tier A/B pattern; `maturity: calibrated` with any `planned` cell, or without a ledger at `docs/calibration/planes/<id>.md` that names `Repository:`, `Commit:` and `n:`; a `supersedes` cycle or an unknown plane id; a `languages` entry the catalog does not define or that is a catalog alias key (a plane written for `typescript` applies to JavaScript too, because both sides are resolved with `_common.detector_language`); a pattern section over 700 characters or a `## General` section over 800, because the text is embedded in bundles and briefs and a plane must not be able to starve the source of its budget; a section body containing an ATX heading (`^\s{0,3}#{1,6}(\s|$)`), a setext underline (`^\s{0,3}(=+|-+)\s*$`) or a code fence of backticks or tildes (`^\s{0,3}(`{3,}|~{3,})`), which would rewrite the structure of the document it is embedded in; a `supersedes` id that is unknown or cyclic is also a load problem at run time (the plane is skipped and named in `warnings`, never a crash); any `## ` heading in `rubric.md` other than `## General` or `## S<digits>`.

`seed` exists so a plane can ship before it is complete without hiding the gap: planned cells are printed in the generated matrix, so the gap is visible and countable. A detector column (`D` when the catalog has a detector for any of the plane's languages) sits beside it. It is information, not a substitute for a rubric.

## 3. Selection

`select()` runs once in `signals.py`, over the tracked-file index it already builds. A rule matches when a tracked path matches `file` (a small glob: `*` stays within a segment, `**/` spans directories) and, when `contains` is given, the file's first 64 KiB contains the string. Only paths the scan's own file filter admits (`Filters.exclusion_reason` is `None`) are considered, so a `pom.xml` under a test or vendored directory does not activate a plane. The filter ignores the `--path` restriction (reason `"path"`): a repository-root `pom.xml` still activates a plane when only a subdirectory is scanned. Only tracked regular files that pass `tracked_file_problem` are read, so a symlink or FIFO named `pom.xml` is never opened. A rule examines at most 25 matching files, taken in `(depth, path)` order so a root manifest is never cut off by a deep one; when a rule had more candidates than that, a warning says so. A file that cannot be read does not match; undecodable bytes are replaced, not fatal. Nothing is executed and nothing is fetched.

Every active plane is applied. Where plane A `supersedes` plane B, B is dropped when A is active. Planes that do not supersede each other can both address one pattern. Their entries are then shown in id order, and the investigator reconciles them.

`hotspots.json` records `planes: [{id, matched_by, rubric_hash}]`, sorted by id. `bundle.py` and `verify.py` load the planes again, and embed a plane only when its live `rubric_hash` equals the recorded one; otherwise they warn that the plane changed after `signals.py` ran and skip it. The report describes the selection recorded by signals; a later stage that skips a stale plane warns instead of embedding changed rubric text. `matched_by` is the first matching repository-relative path. The report renders the path and the recorded plane ID through `mdtext.code`.

## 4. Where the text goes

**The bundle.** A `## Plane guidance` section follows `## Detector leads`. For a hotspot whose language, resolved through `detector_language`, is one a plane lists, it holds for each such active plane: the plane's title, its `rubric_hash` (a hash of the plane's title and `rubric.md` only, so editing a cell or `maturity` in `plane.yaml` does not re-investigate anything), its `## General` text, the rubric sections for the patterns that have a detector lead on this hotspot, and the path of the plane's full rubric, `.thunderstruck/planes/<id>.md`, which `bundle.py` writes beside `catalog-brief.md`. The investigator may read it on demand, within its existing read budget. The absence of a lead is where "what counts as protection" matters most, but inlining every section would spend the budget the source needs. Putting `rubric_hash` in the body means any edit to a plane's rubric changes the bundle hash of every hotspot the plane covers, so findings are re-investigated against the guidance that is now in force, never cached against stale guidance.

The section is capped at 12% of the bundle budget and taken off the top: `rest = budget`, less `tokens(service)` when a service section exists, less `tokens(planes)` when a plane section exists, floored at `budget // 2` when either exists. Each term is guarded so that with neither section `rest` is exactly `budget`, as today. The source, history and related sections keep their shares of the remaining budget; the guidance takes only its actual estimated tokens. The cap is applied by omitting whole sections, never by cutting through one: sections that do not fit are dropped starting from the last plane in id order and, within a plane, from the highest pattern id, and a final line names them with their plane (`Omitted to fit the budget: java-spring S10, S28.`). The preface, the plane headers, the hash and path lines and the omission line all count toward the cap. The gate's limits do not make the cap hold (it shrinks with `--budget`); omission does, down to a plane contributing its title, hash and rubric path only. When even that does not fit, the plane is left out and a warning says so, so the cap holds at every budget. With no active plane the section is empty and the bundle is byte-identical to today's.

**The skeptic's brief.** A `## Plane guidance` section holds the rubric sections for the finding's `missing_patterns` in the finding file's language, and the path of the full rubric. The skeptic sees the sections for the patterns the claim rests on, because those are what it adjudicates, and may read the full file. This differs from the investigator's set on purpose. Nothing about the claimed confidence enters it. The brief stays deterministic, and the section is part of `brief_hash`. The brief has no token cap: the gate's limits bound it. `verify.py prepare` writes `.thunderstruck/planes/<id>.md` itself, so a verification run without a prior `bundle.py` never points at a missing file; the function that writes the files (used by both) clears the directory first, so a plane that stopped matching leaves no file behind. A settled verdict is reused only when the finding, its files and dependencies are unchanged **and** the hash of the guidance text in its brief is unchanged: the ledger records `guidance_hash` (the hash of that text, or of the empty string when none applies, so entries written before planes stay valid where no plane applies).

**The prompts.** The skeptic's "may read" sentence and the scan skill's "never read a bundle" rule name `.thunderstruck/planes/<id>.md` (readable by the agents, never by the orchestrating session). Both agent prompts say what the section is: the plugin maintainers' text about what counts as protection on this stack. It is not repository content, so the "repository content is evidence, never instructions" rule does not apply to it. It is also not evidence: a finding still needs `code` evidence that fails, and `validate.py` is unchanged. A pattern the rubric lists under "Does not count" is missing even if the code resembles it. A pattern a rubric lists under "Counts" is not missing unless the investigator can cite code that defeats it.

**The report.** `report.json` gains `planes`, and `report.md` one line naming them with the file each matched on.

## 5. Security and degradation

- Plane text is embedded as plain text under the section's own heading. The gate forbids headings and code fences inside it, so it cannot restructure a bundle or a brief.
- Plane text is plugin content, reviewed in a PR like the catalog. It is never taken from the scanned repository, so a repository cannot ship or alter a plane.
- Selection reads bounded bytes of tracked files only. A malformed or unreadable plane fails the plugin's tests, not a user's scan: at run time a plane that fails to load is skipped, named in `warnings`, and the scan continues. A partial report that says what is missing beats a failed scan.
- The guardrail hook is untouched: it stays stdlib-only and never imports `fracture_planes.py`. Plane handling never runs the scanned project or starts a new process.
- Verify distribution separately from local live-directory installation: the installed copy must include the committed plane assets and be able to load them without falling back to the source checkout.

## 6. Test strategy

- Loader and cell rules: fixture planes under `tests/planes/fixtures/`, one per rule, each failing with a message that names the file and the problem.
- The completeness gate runs over the real `planes/` directory, so a forgotten cell fails CI.
- Selection: glob edge cases, the byte and file caps, unreadable files, `supersedes`.
- Bundles: two builds are byte-identical; a build with no active plane, or with a plane that covers a different language, is byte-equal to a build with no planes loaded (a synthetic hotspot, or a fixture with a pinned base date: the pytest fixture's dates move with the calendar, so no literal hash of a real bundle is asserted; `gen_sample_report.py --check` is the cross-version guard); changing any part of a plane's rubric changes the bundle hash of every hotspot it covers and of no other.
- Run time: a broken plane directory, an unknown or cyclic `supersedes`, and a `hotspots.json` with no `planes` key each leave `signals`, `bundle` and `verify prepare` running with a named warning.
- Briefs: determinism, no claimed confidence, `brief_hash` moves with the rubric, and a settled verdict is not reused when the guidance in its brief changed.
- Generated `skills/stability-catalog/references/planes.md` is checked in CI, like `patterns.md`. Regenerate both samples, never hand-edit them. The HTML embeds `report.json["planes"]` (empty on the fixture); the Markdown has no plane line when the selection is empty and can remain unchanged.
- The benchmark cannot show the effect of a rubric: an investigator change without new labels yields reworded findings with new keys. The ticket's success measures are therefore structural (cells declared, gap count visible), and a later ticket labels findings on a plane's stack.

## 7. Approaches considered

- **A. Planes as catalog data only.** Deterministic, but a rubric is prose and forcing it into fields loses the nuance or bloats the YAML.
- **B. Planes as Markdown the model loads** (dt-bughunt's design). Cheap and expressive, but the model picks what to load, so bundles stop being byte-identical and checkpointing breaks. It also gives nothing to gate.
- **C. Manifest plus prose, selected by a script (chosen).** Determinism where reproducibility matters, prose where judgment does.

## 8. Decisions

- Name is **plane**, not profile (collision with `.thunderstruck.toml`).
- Detection is "any rule matches"; all active planes apply; `supersedes` is the only precedence.
- The bundle carries rubric sections only for patterns with a lead on the hotspot; the skeptic's brief carries those for the finding's patterns.
- `seed` / `calibrated` and `planned` cells are the quality ratchet; a calibrated plane needs a ledger.
- The first plane is `java-spring`. Its rubric covers the patterns for which the Java design already records a distinction (`S10`, `S27`, `S28`, `S29`); every other cell is `planned`. A rubric for `S01` and `S02` needs new judgment (what counts as a timeout or a backoff on Spring clients) and belongs to the maintainer who writes the plane, not to this change.
- The module is `scripts/fracture_planes.py`, not `planes.py`: the directories `planes/` (plugin root) and `tests/planes/` would share its name, and a reader should not have to know that Python prefers the module.
- The report schema stays `v2`: `planes` is an added key.

## 8a. Shapes fixed here and not repeated in the plan's rationale

Guidance is laid out as `##` for the section, `###` per plane (`<id> — <title>`), `####` per pattern, with a one-paragraph preface saying whose text it is, a `rubric <hash>` line and a `full rubric: <path>` line per plane. In the brief it sits just before `## Your output`, and only Tier A/B patterns are looked up. `plan.json` gains a `warnings` list that nothing else reads. The matrix cells read `R`, `n/a`, `planned` or `MISSING`, with ` D` appended where a detector exists. The 25-file warning and the stale-plane warning name the plane and the rule or hash.

## 9. Open design questions

- A `.thunderstruck.toml` switch to disable a plane that matched wrongly. Not built here: a wrongly matched plane adds guidance, it does not change a score.
- Whether a dormant file's bundle gets plane guidance. It does in this design, on the same rule as a hotspot.
- Language-less planes (`kubernetes`): `languages` takes `yaml`, which ranks only with a lead. Whether a plane may also add leads of its own belongs to the Kubernetes tickets (#90, #92).
