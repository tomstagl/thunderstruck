# A re-scan keeps the scan it replaces, and a window can be repeated: design

**Requirements:** [#98](https://github.com/tomstagl/thunderstruck/issues/98). The problem, stories, scope and acceptance criteria (AC-n) are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-22-keep-previous-scan.md`.
**Evidence:** `scripts/signals.py` (`parse_since`, the `window` record `{since, since_date, commits, …}` in `hotspots.json`, `--since` default `"12m"`, the write of `hotspots.json` at the end of `main`); `scripts/bundle.py:631-650` (a finding in `findings/` is reused when its `bundle_hash` matches: the checkpoint); `scripts/report_html.py` (exits when `report.json`'s schema is not the one it renders); `_common.REPORT_SCHEMA_VERSION`; CLAUDE.md "Bundles must stay byte-identical across runs".

## 1. What is wrong

`signals.py` starts a scan by writing `hotspots.json`; `bundle.py`, the investigators, `validate.py`, `verify.py` and `report.py` then replace `bundles/`, `findings/`, `checks/`, `report.*` and `index.json`. Nothing records that an earlier, finished scan was there. A re-run with another head, another default window (`12m` moves with the date) or another plugin version replaces it with no warning, and an older `report.json` can no longer be rendered by a newer `report_html.py`.

The window is already recorded (`window.since`, `window.since_date`), but a bare re-run does not read it.

## 2. Decisions

### 2.1 What "the same scan" means

A scan's identity is `(repo.head, window.since_date, config.top, config.path, config.include_tests, REPORT_SCHEMA_VERSION)`. The earlier scan counts as *finished* when `.thunderstruck/report.json` exists and its `scanned_at` equals `hotspots.json`'s `generated_at` (`report.json`'s own `generated_at` is when the report was rendered; the rule is the one `report.py` already uses for `checks/run.json`, which carries the scan's `generated_at`).

- Finished and the identity is equal: this is a re-run of the same scan. Nothing is archived and nothing changes: the checkpoint in `bundle.py` keeps working on the live `findings/`.
- Finished and the identity differs: archive (§2.2).
- Not finished (no `report.json`, or from another scan): an interrupted scan is being resumed or restarted; nothing is archived, because there is no finished report to lose.

### 2.2 The archive is a copy, made before anything is overwritten

`signals.py`, before writing the new `hotspots.json`, copies these paths from `.thunderstruck/` into `.thunderstruck/previous/<YYYYMMDD>-<head7>/` (the date of the old `generated_at`, the old head; a `-2`, `-3` suffix if the name exists): `hotspots.json`, `report.json`, `report.md`, `report.html` (if present), `index.json`, `validation.json`, `usage.json`, `findings/`, `checks/verdicts.json`, `checks/run.json`. Not copied: `bundles/`, `checks/briefs/`, `deps/` and `context.json` (large, or regenerated from git and the catalog).

**Why a copy and not a move.** `findings/` is what `bundle.py` reuses for unchanged bundles. Moving it would turn every re-scan into a full re-investigation. The live files stay where they are; the copy is for reading the old scan.

**Bound.** At most 3 archives are kept. After copying, the oldest beyond 3 (by directory name) are deleted: only directories directly under `previous/` that match the name pattern, never anything else. A copy that fails part-way is removed whole and reported as a warning; the scan goes on (the ticket's worst outcome is the status quo, not a stopped scan).

`previous/` is under `.thunderstruck/`, which is the tool's own output directory. No script of the scan reads it, so a bundle can never depend on it and `test_bundles_are_within_budget_and_deterministic` is unaffected.

### 2.3 What the scan says

`signals.py` adds one line to `warnings` (printed on stderr and carried into `hotspots.json` and the report's Run warnings, as the other warnings are):

`the earlier scan of <date> (head <h7>, since <date>) was replaced; a copy is in .thunderstruck/previous/<name>/. Finding ids (FR-001) are numbered per scan: refer to a finding by its key.`

and, when it differs, the window sentence of §2.4. The line is built from stored values only. When no archive was made because the copy failed, it says that instead.

`hotspots.json` gains `"previous": {"archived": "<name>"|null, "generated_at": …, "head": …, "since_date": …}` so the report can state it without re-deriving it. A scan with no earlier scan has no `previous` key, which keeps the generated sample report unchanged.

### 2.4 Repeating a window

`--since` defaults to `None`; the script resolves it to `12m` when no earlier scan exists, as today. New value `--since previous`: the earlier scan's `window.since_date` (an ISO date, which `parse_since` already takes). With no earlier `hotspots.json` it is an error that says so.

A bare re-run does **not** silently reuse the earlier window: a window that never moves turns "12 months" into "however long ago the first scan was", and the output would no longer say what the default means. When a bare re-run's `since_date` differs from the earlier scan's, the warning says: `the earlier scan used since <d1>; this one uses 12m (since <d2>). Pass --since previous to repeat it.` The skill offers it to the user when it can ask and relays the line when it cannot.

### 2.5 The renderer says where the old output is

When `report_html.py` (and `report.py` for a stored report it must read) refuses a `report.json` of another schema, its message adds: `If this scan was replaced by a newer one, its copy is in .thunderstruck/previous/ (kept from version <this one>)`; for output older than the archive feature it says the earlier output was not kept. It does not render an archive of another schema: that is the version that wrote it.

## 3. Out of scope

Comparing two scans (what changed between them); migrating a stored report to a newer schema; archiving the `bundles/`.

## 4. Degradation

An unreadable `report.json` is treated as "not finished". A full disk or a permission error while copying removes the partial copy and warns. A `previous/` that is a file or a symlink is not followed: the archive is skipped with a warning (`c.tracked_file_problem`-style `lstat` check).

## 5. Test strategy

- Same identity: no `previous/`, live files untouched, the checkpoint still reuses a finding.
- Different head, different window, different `top`, different schema: one archive, with exactly the listed paths and the old bytes; the live `findings/` still present.
- Unfinished earlier scan: no archive.
- Three archives kept, the fourth call removes the oldest, and a stray directory in `previous/` is left alone.
- `--since previous`: uses the earlier `since_date`; errors with no earlier scan; a bare re-run on a later date prints the window sentence.
- The warning and `previous` reach Run warnings; the generated sample is unchanged (`gen_sample_report.py --check`).
- The renderer's refusal names `previous/`.
