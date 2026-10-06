# Labelling findings for the correctness benchmark

The benchmark (`scripts/benchmark.py`, #55) scores runs against labelled
ground truth. This page says how a label is made, how a repository is added,
and what the figures cannot show. The design is in
`docs/superpowers/specs/2026-10-03-correctness-benchmark-design.md`.

## A label set

One directory per repository and commit under `docs/calibration/correctness/`:

| Path | What it is |
|---|---|
| `labels.json` | The ground truth, `thunderstruck.labels/v1` (spec §2.1) |
| `scan/` | The scan whose findings are labelled: `report.json`, `hotspots.json`, `bundles/`, `findings/` |
| `runs/` | Optional: checked-in runs to score, `thunderstruck.benchmark-run/v1` (spec §3.1) |

Anything else in the directory is evidence for a reader (reproduction notes,
spikes). The scorer reads only `labels.json` and the files it is given.

## Making labels

1. **Scan at a pinned commit.** Run `/thunderstruck-scan` with the release
   under test on a clean checkout of the commit. Copy `report.json`,
   `hotspots.json`, `bundles/` and `findings/` into `<set>/scan/`, replacing
   local absolute paths with placeholders (`<repo>`, `<site-packages>`).
2. **Establish each verdict**, preferring, in order:
   - `executed`: a reproduction you ran. Name it in `established_by`;
   - `read`: the code, docs, full commit messages and dependency source settle it;
   - `reasoned`: neither was possible; say why in your notes.
3. **Record the verdict class.** `correct`, `correct_but_gated` (true, but
   only behind a non-default setting; it counts as correct), `partially_correct`
   or `wrong`.
4. **Record what the scorer needs:** the deserved confidence; `duplicate_of`
   (a key) for a finding that is another finding's defect seen from elsewhere;
   the refuting fact as line ranges, each typed `repo`, `dependency`, `docs`
   or `history`; and each precondition the finding depends on, with its
   literal default (what the code or docs state) and its effective default
   (what holds at runtime). A precondition about the deployment rather than a
   setting is `kind: environment`. A measured consequence is not a default:
   record the setting's value, not how long it took.
5. **Name who labelled it** in `labelled_by`: a model id or a person's handle.
   A model may label. It must not label findings for a set that will score a
   run of the same model; the scorer excludes such findings and says so.
6. **Validate:** `uv run scripts/benchmark.py --labels <set> --report <set>/scan/report.json`.
   A set with any invalid label is rejected whole and nothing is scored.

Thunderstruck never executes the project it scans. That rule binds the plugin
and its pipeline. A labeller works outside both and may execute the project in
their own sandbox, as the Celery review did.

## Adding a repository

Add a directory in the form above. The scorer needs no change; a set's figures
are printed separately, with a pooled line only below them. A set no change was
tuned on can be marked `"role": "holdout"`: its per-finding rows then appear
only with `--reveal`, and every figure line says `revealed`.

## Changing a label

Adding labels never changes another finding's result. Changing an existing
label is a relabel: the diff shows it, and the baseline tests in
`tests/test_benchmark.py` fail until they are updated in the same PR, with the
reason.

## What the figures cannot show

- **Recall.** A defect the scan missed has no key, so nothing matches it
  mechanically. Missed defects stay in the evidence and are not scored.
- **An investigator change, without new labels.** A re-scan's reworded
  findings get new keys and are unlabelled until someone labels them.
- **Anything beyond the labelled repositories.** A figure is evidence about
  the sets it names: repository, commit, n and who labelled them.
- **An effect inside the interval.** At n=21, one relabel moves a rate by
  about 5 points; a change smaller than the printed Wilson interval is not
  shown to be a change.

The figures are measures, not targets. Tuning a stage against one set's
findings until its score looks good fits that set.
