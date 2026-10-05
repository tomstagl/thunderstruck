# A correctness benchmark scored against executed ground truth: design

**Requirements:** [#55](https://github.com/tomstagl/thunderstruck/issues/55), part of [#54](https://github.com/tomstagl/thunderstruck/issues/54). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-10-03-correctness-benchmark.md`.
**Evidence:** `docs/calibration/correctness.md` and `docs/calibration/correctness/celery/` (#53).

## 1. Architecture

```
docs/calibration/correctness/<set>/
  verdicts.json, scan/, spikes/   evidence as reviewed; never edited (exists for celery)
  labels.json                     NEW · thunderstruck.labels/v1 · the ground truth the scorer reads
  runs/<name>.json                NEW · thunderstruck.benchmark-run/v1 · checked-in things to score

scripts/benchmark.py              NEW · deterministic · stdlib only · no network, no model, no git
  --run FILE                      score a run file (repeatable)
  --report FILE                   adapter: a scan's report.json → confidences (§3.2)
  --bundles DIR                   adapter: a scan's bundles/ → what each Source block shows (§3.3)
  --labels DIR                    label sets to load (repeatable; default: every
                                  docs/calibration/correctness/*/labels.json)
  --json                          machine output instead of the table
  --reveal                        per-finding rows for a holdout set (§5.3)
```

The benchmark is a reader of data: label sets on one side, a run on the other, a table out. It never runs a scan, a model, the scanned project or git; producing what it scores is done on demand elsewhere (the ticket's scope). It lives in `scripts/` beside `calibrate.py` and the generators, and imports nothing outside the standard library so that CI and a maintainer run it with bare `uv run scripts/benchmark.py`.

**Nothing in the scorer knows about any one repository.** Hotspot ids, file paths, setting names, dependency locations and verdict prose live only in a set's `labels.json`. Celery is the first set; the second (#59) is a new directory and nothing else (AC-10).

## 2. Label set

### 2.1 `labels.json`

```json
{
  "schema": "thunderstruck.labels/v1",
  "repo": "celery/celery",
  "commit": "508c1129269d2b1baffc516d8f5c05da06273ef0",
  "role": "development",
  "scan": "scan/report.json",
  "labels": [
    {
      "key": "f62fb0c3468b",
      "display": "FR-001",
      "source": "verdicts.json#FR-001",
      "verdict": "partially_correct",
      "basis": "executed",
      "labelled_by": "claude-fable-5-1",
      "established_by": "review/recipe_fr001.py; redis/fr001_a.py; redis/fr001_b_dbg.py",
      "deserved_confidence": "medium",
      "duplicate_of": null,
      "refuting_fact": {
        "ranges": [
          {"file": "celery/app/base.py", "lo": 1640, "hi": 1657, "kind": "repo"},
          {"file": "celery/backends/base.py", "lo": 236, "hi": 236, "kind": "repo"},
          {"file": "celery/backends/asynchronous.py", "lo": 358, "hi": 363, "kind": "repo"}
        ]
      },
      "preconditions": [
        {"setting": "redis_socket_connect_timeout", "kind": "setting",
         "literal": {"type": "none"},
         "effective": {"type": "number", "value": 120, "unit": "s"}}
      ]
    }
  ]
}
```

| Field | Values | Notes |
|---|---|---|
| `role` | `development` · `holdout` | §5.3 |
| `scan` | path inside the set | The findings the labels belong to; kept as evidence, not read by the scorer |
| `key` | the finding's `key` | The only join key (AC-7). `display` is printed for a reader and never matched |
| `verdict` | `correct` · `correct_but_gated` · `partially_correct` · `wrong` | `correct_but_gated` counts as correct (ticket, product decisions) |
| `basis` | `executed` · `read` · `reasoned` | AC-9 |
| `labelled_by` | a model id (`claude-fable-5-1`) or a person's handle | Required, never empty |
| `established_by` | free text naming the reproduction | Required when `basis` is `executed` |
| `deserved_confidence` | `low` · `medium` · `high` | |
| `duplicate_of` | a key in the same set, or null | |
| `refuting_fact` | null, or `{ranges: [...]}` | Null for findings with nothing to refute. A range's `kind` is `repo`, `dependency`, `docs` or `history` (a commit message); only `repo` ranges carry line numbers the scorer uses |
| `preconditions[].kind` | `setting` · `environment` | `environment` is a fact about the deployment (a database user's privileges, a user-authored route), not a default; it is excluded from defaults scoring (§4.5) |
| `preconditions[].literal`, `.effective` | a value (§4.5) | `literal` is what the code or docs state; `effective` is what holds at runtime |

### 2.2 Validation

Before scoring, every loaded set is validated as a whole. A set is rejected, naming every offending label, when:

- the schema is unknown, or `commit` is not a 40-character hex SHA;
- a key occurs twice;
- a label lacks `verdict`, `basis` or `labelled_by`, or carries a value outside §2.1's vocabularies;
- `basis` is `executed` and `established_by` is empty;
- `duplicate_of` names a key not in the set, or the label itself;
- a `repo` range has `lo > hi` or a non-positive line.

A rejected set exits 2 and nothing is scored; the benchmark never scores the valid part of an invalid set. Two loaded sets with the same `commit` are rejected too, since a run is matched to its set by commit (§3.1).

### 2.3 Stability

Each finding's result is a function of its own label and its own run record only (§4). Adding a label therefore changes totals and n but never another finding's row (AC-9). Changing an existing label is a relabel: it appears as a diff to `labels.json` and fails the baseline test (§8), so it is never silent.

## 3. What is scored

### 3.1 Run file

```json
{
  "schema": "thunderstruck.benchmark-run/v1",
  "commit": "508c1129269d2b1baffc516d8f5c05da06273ef0",
  "produced_by": {"stage": "refuter", "model": "claude-fable-5-1", "source": "spikes/refute/*.json"},
  "findings": {
    "f62fb0c3468b": {"verdict": "narrowed", "duplicate_of": null},
    "…": {"confidence": "medium", "preconditions": [{"setting": "task_acks_on_timeout", "default": "True"}]}
  }
}
```

- `commit` selects the label set. A run whose commit matches no loaded set exits 2 and says which commits are loaded.
- `produced_by.stage` is free text (`investigator`, `refuter`, `confidence`, …); `model` is a model id or null for a deterministic stage.
- Every field of a finding record is optional. Each measure (§4) scores the findings that carry its field and ignores the rest, so #37 can submit verdicts alone and #56 confidences alone.
- `verdict` is `upheld` · `upheld_but_gated` · `narrowed` · `refuted`, the vocabulary the spike's refuters used. #37 either writes it or ships a converter; the scorer does not learn a second vocabulary.
- `duplicate_of` is a key. A run that names findings by display id is converted before it is scored; the scorer never maps ids.
- `bundle` is `{"file": path, "shown": [[start, end], …] | null}`: the hotspot file of the finding's bundle and the line ranges its Source block shows (§3.3), or `null` when the block is unreadable. The `--bundles` adapter writes it; a run file may carry it too, so a checked-in run can be scored for §4.4 without its scan directory.
- A precondition may also carry `confirmation`, the state #57 derives (`confirmed` or `unconfirmed`). It is reserved for #57, whose spec owns its design; this scorer ignores it until #57 extends §4.5.

### 3.2 `--report` adapter

Reads a scan's `report.json`: `repo.head` is the commit, each finding's `key` and `confidence` become a run record, and `produced_by` is `{"stage": "investigator", "model": null}` — `report.json` does not record which model investigated, so the independence check (§3.4) cannot apply and the output says so. When #56 adds preconditions to findings, this adapter reads them too; that is #56's change to make.

### 3.3 `--bundles` adapter

Reads `bundles/index.json` for each hotspot's file and each `bundles/<id>.md` for its Source block, and computes the lines it shows. It parses the three notes `bundle.py` writes (`scripts/bundle.py`, `section_source`):

| Note | Lines shown |
|---|---|
| `whole file, N lines` | 1–N |
| `lines A-B — the most complex function …` | A to B, unless clipped |
| `file trimmed to fit the budget; N lines total` | head from 1 and tail ending at N |

When `_clip` cut the excerpt, the fenced body holds a `... [trimmed: N characters omitted] ...` marker. The shown lines are then the head (from the start line, as many lines as precede the marker) and the tail (ending at the end line, as many lines as follow it). The cut is by characters, so the last head line and the first tail line are never counted as shown, even when the cut fell exactly at a line end: the parser can under-count by at most two lines and never claims a line that was not rendered whole. `bundle.py` counts the empty line after a file's final newline in `A-B` and trimmed notes; the parser drops it. A bundle whose Source block matches none of these forms is **unreadable** (§7). The bundle adapter is always given the scan's `report.json` (§4.4), and the commit is that report's `repo.head`.

A test renders `section_source` for each of the three forms, with and without clipping, and asserts the parser's lines against the rendered ones (§8), so a change to the bundle format fails here rather than silently zeroing AC-4.

"Shows" means the Source block only. The Celery reviewer's `in_bundle` differs on three facts: it reads `true` for FR-005, whose lines were visible only in a trimmed diff, and `false` for FR-003 and FR-015, whose in-file ranges the Source block holds but which also needed other files. Diff fragments are cut mid-hunk (`correctness.md`), so they are not counted as showing a fact; a fact that also has ranges in other files is reported as `shown` with `partly elsewhere` (§4.4).

### 3.4 Independence

When a run's `produced_by.model` equals a label's `labelled_by`, that finding is excluded from the run's score and the output counts the exclusions (`excluded: 21 — labeller is the scored model`). This is the mechanical form of the ticket's rule that a model never scores its own labels' stage. A null model never matches.

## 4. Scoring

### 4.1 Verdicts (AC-2)

| run ↓ / label → | correct | correct_but_gated | partially_correct | wrong |
|---|---|---|---|---|
| `upheld` | same | one step | **wrong direction** | **wrong direction** |
| `upheld_but_gated` | one step | same | **wrong direction** | **wrong direction** |
| `narrowed` | one step | one step | same | one step |
| `refuted` | **correct refuted** | **correct refuted** | one step | same |

*Wrong direction* lets an error through; *correct refuted* throws out a true finding, gated included. Narrowing a correct finding is one step, not a refutation: the finding survives with a smaller claim. On the spike's refuters this matrix gives 15 same, 4 one step, 2 wrong direction (FR-003, FR-009), 0 correct refuted, the figures in `correctness.md`.

### 4.2 Duplicates (AC-2)

Over the findings the run gave a `duplicate_of` field (null included): each labelled pair is *found* when the run names the same key, *missed* otherwise; a run pair with no label is a *false duplicate*. Celery has one labelled pair, FR-006 → FR-001.

### 4.3 Confidence (AC-3)

`low < medium < high`. Per finding: exact, over-rated or under-rated, with the step count; totals: exact, within one, over, under; and a list of every finding the run rates `high` whose deserved confidence is lower.

### 4.4 Bundles (AC-4)

Per labelled refuting fact, using its `repo` ranges and the bundle of the finding's hotspot:

| Result | When |
|---|---|
| `shown` | it has a range in the bundle's file, and every such range lies inside the shown lines |
| `not shown` | it has a range in the bundle's file, and some such range does not |
| `elsewhere` | its `repo` ranges are all in other files; no excerpt of this bundle could show it |
| `not in repository` | it has no `repo` range (dependency source, docs or history only) |
| `unreadable` | the bundle's Source block could not be parsed |

The headline is `shown / (shown + not shown)`; the other three are counted beside it, and a `shown` fact that also has `repo` ranges in other files is flagged `partly elsewhere`, since the bundle showed only part of what refutes the finding. On Celery: 4 shown (FR-003 and FR-015 partly elsewhere), 5 not shown, 3 elsewhere.

A finding is joined to its bundle within the scan that produced both: label `key` → that scan's finding `hotspot_id` → the `index.json` entry with that id → its `file`. Hotspot ids are read from the scan, never written in the scorer or the labels, so the bundle adapter is given the scan's `report.json` too (`--bundles DIR --report FILE`).

### 4.5 Defaults (AC-5)

A value is one of:

| `type` | Example | Normalised from a run's `default` |
|---|---|---|
| `none` | | `None`, `none`, `null`, JSON null |
| `bool` | `{"type": "bool", "value": true}` | `True`/`true`/`False`/`false`, JSON booleans |
| `number` | `{"type": "number", "value": 120, "unit": "s"}`; unbounded is `"value": "inf"` (JSON has no infinity) | a number, optionally followed by `s` or `ms` (converted to `s`); `inf`, `infinity` |
| `text` | `{"type": "text", "value": "max_retries=20, interval 1 s"}` | anything else, compared case-folded with whitespace collapsed |

Two numbers match when their values are equal and their units are equal or either is absent, so a run's bare `120.0` matches a label's `120 s`. Other types match on type and value. Settings match on case-folded name. Per `kind: setting` precondition the run is: *matches effective*, *matches literal only*, *matches neither*, or *not stated*. Where literal equals effective, a match counts as effective. The headline is reported over the **discriminating** preconditions, those whose literal and effective differ, because only they can show the difference AC-5 asks about; the rest are counted beside it. On Celery the discriminating ones are `redis_socket_connect_timeout` (FR-001), `task_acks_on_timeout` (FR-002), `result_backend_always_retry` (FR-014, FR-015) and `result_backend_max_retries` (FR-015).

#57 extends this measure with two figures, `confirmed_not_effective` and `upheld_on_wrong_default`, both read from the run's `preconditions[].confirmation` and verdicts. Their names are reserved here; their definitions are in #57's spec (§13.2).

## 5. Output

### 5.1 Figures (AC-6)

Every rate is produced by one function that takes the counts and the set's basis and returns the line:

```
same verdict class   15/21  (50–86%)  celery/celery@508c112 · n=21 · labels: 21 claude-fable-5-1 (20 executed, 1 read)
```

The interval is Wilson's 95% score interval, deterministic and stdlib-only; it is there because n=21 is small enough that a reader needs to see it (15/21 is 50–86%, 8/21 is 21–59%). No code path formats a rate without passing the basis, and a test asserts every rate line of the output carries `@`, `n=` and `labels:`.

### 5.2 Per set, never only pooled

Results are printed per set. When the runs scored cover more than one set, one run per set, the scorer adds a pooled line per measure, always below the per-set lines and marked `pooled`; two runs on the same set are reported side by side and never pooled. Pooling hides a regression on the smaller set, so the comparison a PR states is "no worse on any set", not "better in total". Unlabelled findings (AC-7) are listed by key under their run, counted, and appear in no rate.

### 5.3 Holdout

For a set with `role: holdout` the default output is totals only. `--reveal` prints its per-finding rows and adds `revealed` to every figure line, so a PR that tuned against a holdout set shows it. Celery is `development`; #59 decides its set's role.

### 5.4 `--json`

The same results as one object: per set, per measure, the counts, the interval, the basis, the per-finding rows (omitted for holdout sets without `--reveal`), the unlabelled keys and the exclusions. Key order and float rounding are fixed, so the output is byte-identical across runs on the same input.

## 6. The Celery set and the baseline

### 6.1 Building `labels.json`

Converted once from `verdicts.json`, and checked in. The conversion is mechanical for `key`, `verdict`, `basis` (`read_code` → `read`), `deserved_confidence`, `duplicate_of` (FR-006's id mapped to FR-001's key through `scan/report.json`) and `labelled_by` (`claude-fable-5-1`, from `notes`); `established_by` comes from each finding's `how_to_verify.what_you_ran_or_why_not` and, where that names no script, from the reproduction its `summary` cites. Refuting-fact ranges are parsed from `refuting_fact.where` with `kind` from the path (`site-packages/…` → `dependency`, `.rst` → `docs`, `git show …` → `history`). Canonical `literal`/`effective` values and the `setting`/`environment` split are normalised by hand from the prose, because the prose is the only source; each is reviewed against `verdicts.json` in the PR. `effective` records the value that holds at runtime, not a measured consequence of it: "about 0.65 s measured" for `task_publish_retry_policy` and "jitter has no effect unless retry_backoff is set" leave `effective` equal to `literal`. That leaves exactly the five discriminating preconditions named in §4.5.

A test asserts `labels.json` agrees with `verdicts.json` on every field derived mechanically, and that every precondition in `verdicts.json` appears in `labels.json` under the same setting name, or under the plain setting name where the evidence qualified it: `result_backend_always_retry (database backend)` is labelled `result_backend_always_retry`, and the combined `retry_backoff / retry_jitter` becomes one precondition per setting. The test holds that mapping as a table. `verdicts.json` itself is not edited.

### 6.2 Baseline runs (AC-8)

| Baseline | Input | Expected |
|---|---|---|
| Today's confidences | `--report scan/report.json` | 8/21 exact, 20 within one, 6 over, 7 under; `high` above deserved: FR-001, FR-003 |
| Today's bundles | `--bundles scan/bundles --report scan/report.json` | 4 shown of 9 with a range in the hotspot file |
| The spike's read-only refuters | `runs/spike-refuter.json` | 15 same, 4 one step, 2 wrong direction, 0 correct refuted; duplicate FR-006 → FR-001 found |

Today's confidences and bundles are read straight from the frozen scan through the adapters; nothing is copied. `runs/spike-refuter.json` is converted once from `spikes/refute/*.json` (display ids mapped to keys through `scan/report.json`) and checked in with `produced_by.source` naming both files; a test re-derives it from the spike files and compares. The refuters' model is not recorded in the spike files, so `produced_by.model` is null and the independence check does not apply to this baseline; the run file says so in `source`.

The "4 of 9" figure in `correctness.md` came from the X-ray spike's own parser, which used the note's line range. §3.3 computes the shown lines from the fenced body; on the ten Celery bundles the two agree (no excerpt was clipped), and the baseline test pins 4.

## 7. Degradation

| Condition | Behaviour |
|---|---|
| A label set fails validation (§2.2) | Exit 2, every bad label named, nothing scored |
| A run's commit matches no loaded set | Exit 2, the loaded commits listed |
| A run key has no label | Listed as unlabelled, counted, in no rate |
| A labelled finding is absent from the run | Not scored for that measure; the n of each figure is what was scored, and the line says `n=17 of 21 labelled` |
| A bundle's Source block is unparsable | That bundle's facts are `unreadable`, counted, never `not shown` |
| A finding is excluded by independence (§3.4) | Counted with the reason |
| `report.json` lacks a model | The output says independence was not checked |

Exit 0 means the input was scored, whatever the figures. The benchmark sets no threshold (ticket, scope).

## 8. Test strategy

`tests/test_benchmark.py`, stdlib plus pytest, in the existing suite and therefore in CI (AC-1):

- **Baseline (AC-8):** the three rows of §6.2 against the checked-in Celery set, exact counts and the per-finding lists.
- **Matrix (AC-2):** every one of the 16 cells, plus the spike totals.
- **Basis on every figure (AC-6):** every rate line of the table and every rate object of `--json` carries repo, commit, n and labeller mix.
- **Unlabelled (AC-7):** a run with an unknown key, and a run whose display ids are swapped relative to its keys, which must score by key.
- **Validation (AC-9):** one test per rejection rule in §2.2; a set of only valid labels plus one bad label scores nothing.
- **Stability (AC-9):** score, add labels to a copy of the set, score again; every original finding's row is byte-identical.
- **Second set (AC-10):** a synthetic three-finding set under `tests/fixtures/benchmark/`, with its own repo, commit, a holdout role and every verdict class, scored with the same command beside Celery; pooled lines appear; holdout rows appear only with `--reveal`.
- **Bundle parser:** §3.3's render-and-parse test for all three Source forms, clipped and not: every line the parser reports is rendered whole in the fence, and at most two whole lines are not reported.
- **Labels agree with evidence:** §6.1's comparison with `verdicts.json`, and §6.2's re-derivation of `runs/spike-refuter.json`.
- **Determinism:** two `--json` runs are byte-identical.
- **No network, no model:** the module imports nothing outside the standard library (AST check, as for `guardrail.py`).

## 9. Security

Label sets and runs are data. The scorer prints keys, display ids, setting names and counts; it does not print verdict prose, refuting-fact text or anything a scanned repository wrote, so its output carries no repository-authored text into a PR. It reads only paths under the given directories and never follows a path from inside a label (`scan`, `source` and `established_by` are provenance for a reader, not inputs). Label sets are public: §10's procedure scrubs local paths, as #53 did.

**Labels are measurement, never input.** No label, refuting fact or verdict is ever placed in an investigator or refuter prompt, a bundle, the catalog or a sample. A test asserts that nothing under `agents/`, `skills/`, `catalog/` or `scripts/` other than `benchmark.py` and its test reads `docs/calibration/correctness/`.

## 10. Labelling procedure

`docs/calibration/correctness/labelling.md` (new) documents how a set is added or extended:

1. Scan the repository at a pinned commit with the release under test; copy `report.json`, `hotspots.json`, `bundles/` and `findings/` into `<set>/scan/`, replacing local absolute paths with placeholders.
2. For each finding, establish the verdict, preferring execution of a reproduction, then reading, then reasoning, and record which. Record the refuting fact as ranges, the deserved confidence and why, duplicates, and each precondition with its literal and effective value.
3. Write the label with `labelled_by`. A model may label (ticket, product decisions); it must not label findings for a set that will score a run of the same model (§3.4 enforces this at scoring time).
4. Run `scripts/benchmark.py --labels <set>`; validation must pass. Add the set's figures for today's pipeline to the PR.

The rule that the scanned project is never executed (#57) binds the plugin and its pipeline. A labeller works outside both and may execute the project in their own sandbox, as the Celery review did; the procedure says so, so the two are not confused.

## 11. Consumption

The benchmark makes no model call and costs nothing per run. Producing what it scores does: a scan is measured by #5's `usage.json`; the spike's two read-only refuters used about 220–260k tokens each for 10–11 findings (`correctness.md`). Tickets that add model calls (#37) state their cost from `usage.json` alongside their benchmark figures; this ticket adds none.

## 12. What the benchmark cannot show

These go into CLAUDE.md and the labelling procedure (AC-11):

- **Recall.** Missed defects carry no key, so a fresh finding cannot be matched to one mechanically; Celery's five are kept as evidence and not scored.
- **An investigator change, without new labels.** `key` hashes file and failure mode, so a re-scan's reworded findings are unlabelled until someone labels them.
- **Anything beyond the sets.** One repository, one reviewer, a Python library; #59 adds the second. A figure is evidence about the sets it names.
- **Effects inside the interval.** At n=21 one relabel moves a rate by about 5 points; a change smaller than the Wilson interval is not shown to be a change.
- **The figures are not targets.** Tuning a stage against the 21 Celery findings until the score is good fits Celery; each ticket states its target against these measures, and the holdout role exists for a set no change was tuned on.

## 13. Decisions

- **A normalised `labels.json` beside the untouched evidence, not scoring `verdicts.json` directly.** The defaults are prose there, the labeller is not recorded per finding, and every later set would have to copy one review's ad-hoc schema.
- **One scorer script, not a pytest-only benchmark.** The maintainer's story is one command with per-finding output; the suite calls the same code.
- **The verdict matrix is directional, not an ordinal distance.** An ordinal distance would put FR-003 (`upheld_but_gated` against `partially_correct`) one step off; letting an error through is the failure that matters, and the matrix reproduces the spike's published split.
- **Source block only for "shows".** Diff fragments are cut mid-hunk and counted by the reviewer inconsistently; the Source block is the excerpt the bundle's budget governs.
- **Discriminating preconditions as the defaults headline.** A precondition whose literal and effective agree cannot tell the two apart.
- **Wilson interval on every rate.** It is the honest reading of a small n and needs no dependency.
- **Holdout as a label-set role.** A convention in the docs is easy to forget; a flag that marks every figure line is not.
- **Match on commit, report repo.** `report.json` records the head commit but not a repository name; the commit is the identity a label is true at.

## 14. Open design questions

None.
