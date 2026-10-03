# A second ground-truth repository for the correctness benchmark: design

**Requirements:** [#59](https://github.com/tomstagl/thunderstruck/issues/59), part of [#54](https://github.com/tomstagl/thunderstruck/issues/54). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-10-03-second-ground-truth.md`.
**Extends:** [#55](https://github.com/tomstagl/thunderstruck/issues/55), whose spec (`docs/superpowers/specs/2026-10-03-correctness-benchmark-design.md`, "#55 §n" below) and plan are on the branch `spec/correctness-benchmark`, [PR #60](https://github.com/tomstagl/thunderstruck/pull/60). **This design depends on #60 merging and on #55 being built:** it uses #55's label format `thunderstruck.labels/v1` (#55 §2), its run format `thunderstruck.benchmark-run/v1` (#55 §3.1), its labelling procedure (#55 §10, `docs/calibration/correctness/labelling.md`) and its holdout role (#55 §5.3) exactly as written there. If #60 changes any of them before it merges, this spec is updated first.

## 1. Architecture

Nothing in `scripts/`, `agents/`, `skills/`, `catalog/`, `hooks/` or `templates/` changes. A second label set is a new directory, as #55 §1 promises (#55 AC-10), plus one run file in the Celery set and one test file:

```
docs/calibration/correctness/<set>/          NEW · one directory, data only
  README.md                                  provenance: repo, commit, licence, release, scan
                                             arguments, labeller, results for today's pipeline
  LICENSES/                                  the upstream licence texts that cover scan/ and repro/
  scan/                                      the scan as produced (#55 §10 step 1), local paths scrubbed
    report.json, hotspots.json, validation.json, catalog-brief.md, bundles/, findings/
    profile.toml                             the .thunderstruck.toml the scan ran with (§4.2)
    usage.json                               when the release writes one (#5)
  labels.json                                thunderstruck.labels/v1, role "holdout" (§6)
  review.md                                  per finding: verdict, how established, refuting fact
                                             in words, preconditions; the reader's evidence
  repro/                                     every reproduction a label names (§5.2)
  runs/pipeline.json                         thunderstruck.benchmark-run/v1: today's pipeline (§7)

docs/calibration/correctness/celery/runs/pipeline.json   NEW · the same baseline for Celery (§7)
tests/test_benchmark_second_set.py                       NEW · the set's checks and baselines (§10)
```

`<set>` is the chosen repository's name in lower case with dots replaced by hyphens (`trigger.dev` → `trigger-dev`). The scorer finds the set by globbing `docs/calibration/correctness/*/labels.json` (#55 §1); nothing registers it.

## 2. Selection criteria

A candidate must meet all of these, each checked from the repository itself, not from its website:

| # | Criterion | Why | How it is checked |
|---|---|---|---|
| C-1 | A service that calls external systems (databases, queues, caches, HTTP APIs) from its own server code | The catalog is written for that code; Celery is a library | The top 10 of `signals.py` with UI code excluded (§4.2) are server-side files that call such systems, and most carry detector leads |
| C-2 | TypeScript or Java (ticket, scope) | A second language beside Celery's Python; both have calibrated detectors (`docs/calibration/typescript.md`, `java.md`) | File counts by extension at `HEAD` |
| C-3 | A permissive licence (MIT, Apache-2.0, BSD) covering the whole tree, so excerpts may be checked in (AC-1) | `scan/bundles/` and `repro/` copy upstream code into this public repository. Copyleft (GPL, AGPL) and source-available licences are excluded: they either attach terms to this repository or forbid redistribution. A tree with proprietary "enterprise" directories is excluded too, because the scan cannot be guaranteed to stay out of them | `LICENSE*` and `NOTICE*` files at every level; `license` fields of the packages the scan would rank |
| C-4 | A test suite that runs locally, with real dependencies started locally (Docker is acceptable, cloud credentials are not) | AC-2 wants at least half the labels established by execution; a labeller can only execute in a project whose tests run | The repository's own contributor docs and CI workflows name the command; Task 1 of the plan runs it at the pinned commit |
| C-5 | Enough history: at least 300 non-bot commits in the 12-month window and 10 hotspots with real churn | A ranking on thin history is weaker (`signals.py` warns); Celery had 372 | `signals.py --top 10 --since 12m`, which counts the window's commits after skipping bots |
| C-6 | Actively maintained at the pinned commit | Findings about abandoned code are less useful and harder to verify against current dependencies | Last commit within a month of pinning |

## 3. Candidates

Researched on 2026-10-03 from blobless clones (licence, languages, activity, contributor docs, CI) and from `signals.py` run from `main` at `3e7bd55` over a shallow clone (`--since 2025-10-03 --top 10`). Every figure below was read from the repository or from that run.

### 3.1 Shortlist

| | **triggerdotdev/trigger.dev** | **conductor-oss/conductor** | **kestra-io/kestra** |
|---|---|---|---|
| What it is | Background-job and workflow platform: a webapp, a run engine and a run queue on PostgreSQL, Redis and ClickHouse | Workflow orchestration server (the Netflix Conductor fork): HTTP tasks, Redis/Postgres/MySQL persistence, Kafka, AMQP, SQS, NATS | Event-driven orchestration server: executor, JDBC queue and repository, worker, scheduler |
| HEAD read | `b21b2ec2f6928b2257676c5d4955723075bf380e` (2026-10-02) | `ab2de6da6c7b5935e6c6d09da29953b8d4cfe291` (2026-10-02) | `11a82dc60df64f0358c26640fdc449182515becc` (2026-10-03) |
| Licence (C-3) | Root `LICENSE` Apache-2.0; `packages/core`, `trigger-sdk`, `cli-v3`, `build`, `python` and `internal-packages/otlp-importer` carry MIT `LICENSE` files; two `NOTICE.md` files credit MIT-licensed upstreams (Hookdeck samples, PostHog). No proprietary directory | Root `LICENSE` Apache-2.0; `CONTRIBUTING.md`: "All files are released with the Apache 2.0 license"; `licenseheader.txt` | Root `LICENSE` Apache-2.0; Helm charts carry their own `LICENSE` |
| Language (C-2) | TypeScript: 3,778 `.ts`, 770 `.tsx`, 4 `.js` | Java: 1,509 `.java`; plus 1,297 `.ts`/`.tsx` in the `ui/`, `ui-next/` front ends | Java: 2,808 `.java`; plus 1,152 `.ts`/`.tsx` in `ui/` |
| Window commits (C-5) | 1,570 after 53 bot commits skipped | 694 | 4,054 |
| Since | 2022-11 | 2016-12 | 2019-08 |
| Test command (C-4), from the repo | `AGENTS.md`: "We use vitest exclusively. Never mock anything - use testcontainers instead"; `pnpm run test --filter webapp`, per package `pnpm run test ./src/… --run` after `pnpm run build --filter <pkg>`; CI: `pnpm run test:webapp`. Docker required (testcontainers for Redis and PostgreSQL) | `README.md`: requirements Docker, JDK 21+; `./gradlew build`; CI: `./gradlew test -x :conductor-test-harness:test`; modules are named `conductor-<dir>` (`settings.gradle`), so `./gradlew :conductor-core:test`. Persistence modules use Testcontainers | `AGENTS.md`: `./gradlew :<module>:test`, `./gradlew unitTest`, executor changes `./gradlew :jdbc-h2:test --tests "H2RunnerTest"` (H2, no external database) |
| Hotspots, UI excluded (C-1) | All 10 server-side: run engine `index.ts`, `createBackgroundWorker.server.ts`, `clickhouseEventRepository.server.ts`, `runsReplicationService.server.ts`, `PostgresRunStore.ts`, `triggerTask.server.ts`, `s2realtimeStreams.server.ts`, run-queue `index.ts`, `env.server.ts`, a replay route | All 10 Java: `WorkflowExecutorOps`, `AbstractProtoMapper`, `AgentService`, `Task`, `DeciderService`, `WorkflowSweeper`, `Join`, `LLMHelper`, `DoWhile`, `SubWorkflow` | All 10 Java: `ExecutorService`, `ExecutionEventMessageHandler`, `JsonSchemaGenerator`, `AbstractJdbcRepository`, `DefaultExecutor`, `RunVariables`, `FlowInputOutput`, `QueryFilter`, `ExecutionService`, `WorkerTaskProcessor` |
| Hotspots with detector leads | 8 of 10 (S01, S02, S05–S10, S12, S15–S17, S19) | 0 of 10 | 3 of 10 (S01, S04, S28) |
| Profile that excludes UI (§4.2) | `exclude_globs = ["*.tsx"]`, `exclude_dirs = ["packages"]` (the published SDK and CLI, which are client libraries) | `exclude_dirs = ["ui", "ui-next"]` | `exclude_dirs = ["ui"]` |
| Dependency placeholder (§5.2) | `<node_modules>` | `<gradle-cache>` | `<gradle-cache>` |

Without the profile, UI code took hotspot slots in every candidate: in trigger.dev a side menu, a filter bar and a route component; in Conductor five of ten were `ui-next/` files; in Kestra two. In trigger.dev the published SDK and CLI (`packages/`) took five slots more; they call the platform's own API, which makes them client libraries, the kind the first set already covers.

### 3.2 Considered and rejected

| Repository | Why not |
|---|---|
| Unleash/unleash | `LICENSE` at `HEAD` is GNU AGPL-3.0 (C-3) |
| novuhq/novu | `LICENSE-MIT` plus `LICENSE-ENTERPRISE`, a "Novu Proprietary Software License" for enterprise packages (C-3) |
| medusajs/medusa | `LICENSE` is MIT "except for the Enterprise Edition materials identified in ENTERPRISE-LICENSE.md" (C-3) |

### 3.3 Recommendation

**trigger.dev.** It is the only candidate where the ranked code is the kind the catalog is written for: eight of ten hotspots already carry detector leads, against none in Conductor and three in Kestra. That matters twice. The benchmark measures stages that act on findings, and findings on lead-free orchestration logic (Conductor's decider, Kestra's executor) test the investigator's reading of state machines more than the stability patterns. And #58 and later detector work need a set where leads exist to be judged. Its tests already run real PostgreSQL and Redis in testcontainers, so most findings can be reproduced by adapting an existing test. That is the cheapest path to AC-2's half executed. It differs from Celery on every axis the ticket names: a service, not a library; TypeScript, not Python; its own database, queue and analytics store, not a broker client.

Its costs: a large and fast-moving monorepo (pinning handles that); some hotspots (`env.server.ts`) are configuration, which suits #57's defaults work and is not a defect of the set; and the test setup needs Docker, pnpm 10 and a build of dependent packages before a package's tests run.

**Conductor** is the Java alternative if the maintainer wants Java over leads: real external calls in `http-task/` and its persistence modules, but they did not rank, so the scan would be about workflow state. **Kestra** has the most activity and a test path without Docker (H2), but its external calls live mostly in plugins kept in other repositories.

The maintainer picks (ticket, open product questions); the plan's first task records the pick. Everything after §3 is written for any of the three, with per-candidate values in §3.1's table.

## 4. The scan

### 4.1 Release under test

The scan uses the pipeline that #56, #37 and #57 are measured against: the newest commit of `main` that contains #55 and none of those three. While none of them has merged, that is `main`, installed from the GitHub marketplace, as a user installs it. The repository has no release tags, so if one of them has merged by then, the plugin is installed from a clean clone of the last `main` commit before the first of them, as a local marketplace. `signals.py` then warns that it runs from a source checkout; the warning is expected, and `README.md` records it. Either way `README.md` records the plugin version and its commit.

### 4.2 Arguments and scope

`/thunderstruck-scan --top 10 --since 12m`, the arguments of the Celery scan, on a clean clone at the pinned commit, with a `.thunderstruck.toml` holding §3.1's profile and nothing else. The profile is how a user restricts a scan (`_common.Filters.from_profile`); it adds to the default exclusions and never replaces them. `hotspots.json` records `config.profile: true`; the file itself is copied to `scan/profile.toml` so the scope is reproducible. Excluding UI code is the scope decision of §3.1, made before any finding exists; nothing is excluded after seeing findings.

If the scan reports fewer than 15 findings, it is re-run once at the same commit with `--top 15` and the first scan is discarded, before any finding is labelled. Below 15, a single relabel moves a rate by more than 6 points and the Wilson interval spans most of the scale. Hotspots under **Incomplete** are recorded in `README.md` and not labelled.

### 4.3 What is copied

#55 §10 step 1: `report.json`, `hotspots.json`, `validation.json`, `catalog-brief.md`, `bundles/` and `findings/` into `scan/`, plus `profile.toml` and, when the release writes it, `usage.json` (#5). Every local absolute path is replaced: the scanned checkout by `<repo>`, the plugin by `<thunderstruck>`, the labeller's sandbox by `<labeller-scratchpad>`, and the dependency store by §3.1's placeholder. Nothing else is edited. A test asserts no file of the set contains a home or temp-directory path (§10).

## 5. Labelling

### 5.1 Procedure

#55 §10 as written: for each finding establish the verdict, preferring execution, then reading, then reasoning; record the refuting fact as typed ranges, the deserved confidence, duplicates and each precondition with its literal and effective value; write the label with `labelled_by`; validate with `scripts/benchmark.py`. The labeller may execute the project in their own sandbox (#55 §10). Thunderstruck's pipeline never does.

### 5.2 What this set adds to it

These are conventions of this set, checked by its own test (§10), not rules of the scorer:

- **`established_by` on every label**, not only `executed` ones. For `executed` it names one or more files under `repro/`, each of which exists. For `read` it names what was read; a label that rests on dependency source names at least one path under the dependency placeholder (`<node_modules>/@prisma/client/…`, `<gradle-cache>/…`).
- **Reproductions are checked in** under `repro/`, named by display id (`repro/FR-003.test.ts`), with a header comment naming the command that ran it. Celery's lived in the reviewer's scratchpad and are lost; a reader of this set can rerun them. They are not run in CI: they need the scanned project and its services.
- **AC-2's count.** A label counts toward "established by execution or by reading dependency source" when its `basis` is `executed`, or its `basis` is `read` and `established_by` contains the dependency placeholder. The test asserts `2 × count ≥ n`.
- **`review.md`** holds the prose `verdicts.json` held for Celery: per finding the verdict, how it was established, the refuting fact in words and the preconditions. `labels.json` stays the scorer's input; `review.md` is what a reviewer of the labelling PR reads.

### 5.3 Who labels

A model may label (#55, product decisions), and the scorer excludes a finding when the scored run's model equals its labeller (#55 §3.4). So the labeller must be a model that no stage scored on this set runs as by default: not the scan's session or investigator model (recorded in `README.md`, and in `usage.json` when present), and not the refuter model #37's spec names. **The default is `claude-fable-5-1`**, Celery's labeller, which keeps the labeller mix of the two sets comparable; Task 1 checks it against #37's spec at that time and records the choice. Every label names it; a person who relabels a finding writes their handle.

## 6. Role: holdout

**Recommended: `"role": "holdout"`.** #54's success measure is that the Celery figures hold on the second repository "without tuning to it". That is a holdout by definition, and #55 §5.3 provides the mechanism: totals only by default, and `--reveal` marks every figure line `revealed` so a PR that looked shows it.

Consequences, all within #55's design:

- Celery stays the development set: #56, #37 and #57 tune and report per finding against it, and report this set's totals beside it.
- The set's test pins totals only, never a per-finding row, so `tests/` does not become a per-finding answer key (§10).
- The labels are public, so the holdout is a discipline, not a secret. CLAUDE.md's benchmark paragraph (#55 plan, Task 9) gains one sentence naming the set as holdout: its `labels.json` and `review.md` are not read while changing a stage, and a PR that used `--reveal` says why.
- A holdout of about 20 findings has wide intervals. It can show that a change does not generalise (a drop beyond its interval), not that it does. `README.md` states this beside the figures.

The alternative, `development`, doubles the data to tune on and leaves no unseen set. Once tickets have tuned on it, nothing would test generalisation until a third set.

## 7. Baselines and combined figures (AC-3, AC-4)

### 7.1 Today's pipeline as a run

Celery's baselines for today's pipeline come through the adapters (#55 §6.2): confidences from `--report`, bundles from `--bundles`. AC-3 also wants figures for both sets together, and #55 pools only when one command scores one run per set (#55 §5.2), while `--report` takes one scan. So each set gets **`runs/pipeline.json`**, today's pipeline as one run:

| Field | From |
|---|---|
| `commit` | `scan/report.json` `repo.head` |
| `produced_by` | `{"stage": "pipeline", "model": <the scan's investigator model, or null when not recorded>, "source": "scan/report.json and scan/bundles via benchmark.run_from_report and add_bundles; verdict upheld for every reported finding"}` |
| `findings[key].confidence` | `run_from_report` (#55 §3.2) |
| `findings[key].bundle` | `add_bundles` (#55 §3.3) |
| `findings[key].verdict` | `upheld` for every finding: today's pipeline reports every finding that passed validation, so it upholds every one |
| `findings[key].duplicate_of` | `null`: today's pipeline marks no duplicates |

The file is derived, never edited: a test rebuilds it from `scan/` with #55's own adapter functions and compares it byte for byte, as #55 does for `runs/spike-refuter.json`. Celery's model is `null` (the correctness scan did not record it). The new set's model is the one recorded in `README.md`, which lets the independence check (#55 §3.4) run.

The verdict and duplicate fields add one baseline Celery did not have: **report everything**. It is what #37's refuter must beat. Against the matrix (#55 §4.1) it scores a set's correct findings `same`, its gated findings `one step`, and every partially correct or wrong finding `wrong direction`. On Celery: 5 same, 4 one step, 12 wrong direction, 0 correct refuted; duplicates found 0 of 1. Its confidence and bundle figures are #55's (8 of 21 exact; 4 of 9 shown), because the same adapters produce them.

Precondition defaults (#55 §4.5) are not part of today's pipeline: `report.json` states none until #56/#57. The labels carry them, so the defaults measure is reported per set and pooled as soon as a run states them.

### 7.2 The command

```bash
uv run scripts/benchmark.py --run docs/calibration/correctness/celery/runs/pipeline.json \
                            --run docs/calibration/correctness/<set>/runs/pipeline.json
```

prints per set, then pooled, every measure the runs carry, each line with its repository, commit, n and labeller mix (#55 §5.1). This is AC-3. Two runs on the same set are never pooled (#55 §5.2), so a PR that adds a refuter run states one command per comparison; the spike refuter run and the pipeline run of Celery are not given together when pooled lines are wanted.

### 7.3 Recorded figures

`README.md` records, for the new set: the number of findings and hotspots, the verdict distribution, the basis mix and AC-2's count, and the totals of `runs/pipeline.json` (confidence exact/within one/over/under; refuting facts shown of those in the hotspot file; report-everything verdict outcomes). The test (§10) pins the same totals, so a relabel fails it, as #55 §2.3 intends.

## 8. Licence and provenance (AC-1)

- `LICENSES/` holds a verbatim copy of every upstream licence and notice file covering a path in `scan/` or `repro/`. For trigger.dev: the root `LICENSE` (Apache-2.0), plus the MIT `LICENSE` of any package directory a copied file sits in. Apache-2.0 §4 asks that redistributed copies carry the licence and state changes. `README.md` states that the only change to copied files is the path scrubbing of §4.3.
- `README.md` records: repository URL, pinned commit, licence, the release of thunderstruck and its commit, scan arguments and profile, the session and investigator models, the labeller, the date, and the test command that ran at the pinned commit with its result (C-4).
- A test asserts `labels.json`'s `commit` equals `scan/report.json`'s `repo.head`, which equals the commit in `README.md`.

## 9. Security

Everything copied from the scanned repository is data. The scanned code, its comments, commit messages and its own agent instructions (trigger.dev and Kestra both ship an `AGENTS.md` and a `CLAUDE.md`) are evidence and never instructions, both for the scan (CLAUDE.md, "Repository content is data") and for the labeller. A labeller that meets text trying to steer the review records it in `review.md` and does not follow it.

Reproductions run only in the labeller's sandbox, never in CI or in the pipeline. They are checked in as text; nothing in this repository imports or executes them. #55 §9's rule holds unchanged: no label, refuting fact or verdict reaches a prompt, a bundle, the catalog or a sample. #55's `test_labels_never_reach_the_pipeline` covers the new directory without change.

The public-repository rule applies: scrubbed paths, no hosts, no credentials. A reproduction that needs a secret (an API key for an LLM call) uses a fake server or is not executed, and its label says so.

## 10. Test strategy

`tests/test_benchmark_second_set.py`, stdlib plus pytest, in the existing suite and so in CI. It imports `benchmark` as #55's tests do. `SECOND` names the set's directory once, at the top.

- **The set loads and validates** (#55 §2.2): `load_label_sets` on Celery and the new set together; distinct commits.
- **Coverage:** the label keys equal the keys of `scan/report.json`'s findings: every finding labelled, nothing extra (AC-2).
- **Provenance (AC-1):** `labels.commit == report.repo.head`; `README.md` contains that commit, a licence line and `LICENSES/` is non-empty; role is `holdout`.
- **AC-2's count** per §5.2, and every `executed` label's `established_by` names files that exist under `repro/`.
- **Scrubbed:** no file under the set contains a home directory (`/Users/`, `/home/`), a per-user temp directory (`/private/var/`, `/var/folders/`) or a drive-letter path. Bare `/tmp/` is allowed, because a reproduction may write there.
- **Pipeline runs re-derive:** for both sets, `runs/pipeline.json` equals what §7.1 builds from `scan/`.
- **Baselines (AC-4):** the totals of §7.3 for the new set, read from `evaluate` without `--reveal`; Celery's report-everything totals (5/4/12/0, duplicates 0 of 1) and its unchanged confidence and bundle totals (8 of 21, 4 of 9).
- **Per set and combined (AC-3):** §7.2's command exits 0, prints a block per set and a `## pooled` block for every measure, and every rate line carries `@`, `n=` and `labels:`. The pooled verdict n equals the sum of the two sets' n.
- **Holdout:** the same command without `--reveal` prints no per-finding row for the new set, and with `--reveal` every figure line of that set ends `· revealed`.

The new set's figures are pinned as totals only (§6).

## 11. Consumption

The benchmark makes no model call (#55 §11). Two things in this ticket do, both outside the plugin. The scan costs one default scan, measured by `usage.json` when #5 has landed. The labelling is a per-finding review by a model with execution, like Celery's. Its cost was not recorded for Celery. This set records the labeller's token totals in `README.md`, from the session transcript, by the method of `docs/calibration/consumption.md`. Nothing here changes what a user's scan costs.

## 12. Degradation

| Condition | Behaviour |
|---|---|
| The chosen repository's test command fails at the pinned commit | Task 1 stops; the maintainer picks the next candidate or a newer commit. A set whose tests do not run cannot meet AC-2 |
| The scan yields fewer than 15 findings | One re-scan with `--top 15`, before labelling (§4.2) |
| A hotspot is incomplete | Listed in `README.md`, not labelled; n is the findings that exist |
| A finding cannot be executed (needs a cloud service, a secret, real LLM output) | Labelled `read` or `reasoned`, and the reason is in `review.md`; AC-2's test fails if this leaves fewer than half, and the PR says so rather than relabelling |
| The labeller is the model a scored run uses | That finding is excluded at scoring time and the output counts it (#55 §3.4); §5.3 chooses the labeller to avoid it |
| #60 changes the label or run format before merging | This spec is revised first; no set is written against an unmerged format |

## 13. Dependencies and order

- **#55 (PR #60)**: the formats, the procedure, the holdout flag, `scripts/benchmark.py` and its adapters. This ticket cannot start before #55 is built and merged.
- **#5**: when merged, the scan's `usage.json` names the investigator model and its consumption; without it the README records the session model by hand.
- **#56, #37, #57**: they should be measured against this set's pipeline baseline, so the scan uses a release without them (§4.1). Labelling can run in parallel with their development; their PRs report this set's totals once it has merged.
- **#58**: unaffected; it can use this set's detector leads as further evidence, outside the benchmark.

## 14. Decisions

- **Recommend trigger.dev.** The lead density, the testcontainers suite and the contrast to Celery outweigh Java as a preference (§3.3); the ticket says "preferably TypeScript or Java", and both qualify.
- **Exclude UI code by a profile, decided per candidate before the scan.** Without it, front-end components fill hotspot slots in all three candidates and yield findings outside the catalog's scope. A profile is the user-facing mechanism and leaves the pipeline unchanged.
- **Holdout.** #54's success measure asks for a set nothing was tuned on (§6).
- **A `runs/pipeline.json` per set rather than a repeatable `--report`.** Pooling across sets needs one run per set in one command; making `--report` repeatable is a scorer change, which the ticket rules out. The file is re-derived by test, so it cannot drift from the scan.
- **"Report everything" as the verdict baseline.** Today's pipeline has no refuter; upholding every finding is what it does, and it is the figure #37 must beat. It is computed, not labelled, so it adds nothing to trust.
- **`established_by` on every label and reproductions checked in.** AC-2 has to be checkable mechanically, and Celery's scratchpad scripts are not recoverable. The scorer is untouched: these are the set's own checks.
- **At least 15 findings, by re-scan before labelling.** A smaller n makes every figure an interval spanning most of the scale; re-scanning after labelling would select findings.
- **Same scan arguments as Celery.** A different window or depth would make the two sets differ in more than repository.

## 15. Open design questions

None.
