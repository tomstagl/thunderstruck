# Hotspot X-ray spike — Celery scan (10 hotspots, 21 findings, reviewer ground truth)

Files: `xray.py` (pipeline, `--full` adds full history), `analyze.py` (summaries), `results.json` (per hotspot, per finding, `summary`).
Repo untouched; everything read via `git show/log/blame`.

## Method
- Commits: `git log --no-merges --since=2025-10-03 -- <file>` (counts match hotspots.json exactly); full history adds `--follow -M`.
- Function credit: new-side hunk lines of `git show -U0` mapped onto lizard spans **in that revision**; pure deletions credit the old-side function. Identity = `ast`-qualified name (`Class.method`, `outer.inner`), lizard name as fallback. Fix class = `scripts/_common.classify_commit` imported directly.
- Rank A = (commits/max) × (CCN@HEAD/max). Rank B = ((commits + 2·fix)/max) × CCN norm. Rank C (control) = churn only. Full = rank A over all history.
- Excerpt simulation: same line budget as today's Source block (70–240 lines), whole functions ±3 lines, greedy in rank order; the overflowing function is truncated and filling stops (mirrors `_clip`). "A-skip" skips functions that do not fit and continues.
- Coverage = share of a finding's cited line ranges **in the hotspot file** that fall inside the excerpt; same for the reviewer's `refuting_fact.where` ranges. Other files, `site-packages` and docs are unreachable by any excerpt and counted separately.
- Coupling: commits touching the hotspot's top-3 rank-A functions; every other `celery/*.py` function touched in those commits (tests excluded), ranked by shared commits. Targets = cited/refuting locations in other files, mapped to their HEAD function.
- Age: `git blame -w` author-time at HEAD, days before the scan.

## Q1 — does an X-ray excerpt put cited and refuting code in front of the investigator?

Cited ranges fully covered / mean coverage, 21 findings; refuting facts fully covered, of the 9 (of 12) that have a part in the hotspot file:

| excerpt | cited fully covered | mean cited coverage | refuting covered (of 9) |
|---|---|---|---|
| today (most complex function + 15 pad) | 6 | 0.46 | 4 |
| X-ray A churn×CCN | 5 | 0.42 | 4 |
| X-ray B fix-weighted | 4 | 0.43 | 3 |
| X-ray A, skip-and-continue | 5 | 0.44 | 3 |
| X-ray C churn-only (control) | 4 | 0.37 | 4 |
| X-ray full-history A | 3 | 0.26 | 3 |

By verdict class (cited fully covered, today → A): correct 2→1 (n=5), correct_but_gated 1→1 (n=4), partially_correct 3→3 (n=10), wrong 0→0 (n=2). Refuting covered today→A: partially 3→3, wrong 1→1.

What happened per hotspot (rank-A excerpt vs today):
- H02 redis.py: churn×CCN still spends 170 of 194 lines on `RedisBackend.__init__` (3 commits, CCN 38, score 0.60) and leaves 24 truncated lines for `_reconnect_pubsub` (5 commits, CCN 7, score 0.18). The ResultConsumer block 149–311 that all four H02 findings and both refuting facts live in only wins under churn-only ranking (C: FR-005 refuting 0→1.0, cited 0→0.65), and C costs FR-001's and FR-008's cited code elsewhere. **The task's premise — that X-ray would surface 149–311 — holds only with CCN removed.**
- H03, H06, H10: top-1 function is the same as today's; X-ray changes only the 15-line pads. FR-016 (correct) was cited *because* of today's pad before `apply` (`Task.retry` 872–875); X-ray A/B/C/full all lose it (1.0 → 0.0).
- H04 (79-line budget), H07 (70), H08 (87): budgets are too small for any ranking to hold a path; FR-007's four ranges are covered by nothing in any variant.
- Full history ranks `exception_to_python`, `as_task_v2`, `Consumer.__init__`, `Task.apply_async` first: historically churned, unrelated to every finding. Worst variant.
- 3 refuting facts are entirely outside the hotspot file; 3 more touch `site-packages` or docs; the FR-003 and FR-015 refuting ranges in the hotspot file *were* in today's excerpt (the fact needed other files too). So of the reviewer's "9 of 12 outside the bundle", at most 5 are addressable by any in-file excerpt, and X-ray addresses none of them that today does not.

**Verdict Q1 (excerpt): not supported.** No ranking beats today's single-function excerpt on cited or refuting coverage; the fix-weighted and full-history variants are worse. Caveat: cited coverage is biased toward today (the investigator cited what it was shown); refuting coverage is the unbiased measure and is flat at 4/9.

## Q1.5 — function-level temporal coupling
28 targets (cited or refuting functions in other files, across the 10 hotspots).

| variant | targets with ≥1 shared commit | in top-5 | in top-10 | candidate functions per hotspot |
|---|---|---|---|---|
| window | 3 | 2 | 2 | 0–29 |
| full history | 5 | 0 | 0 | 540–2841 |

Window hits: FR-015 `Backend._ensure_retryable` rank 3 and FR-016 `Request.on_failure` rank 3 — each with **1** shared commit, tied with 13 and 4 others. Full history: best is FR-003 `Request.on_failure` at rank 29 of 2841 (5 shared commits, 16 tied); FR-001's refuting `Backend.__init__` rank 199. The refuting functions for FR-001/006 (`Celery._backend`, `asynchronous.py`), FR-008, FR-009, FR-013, FR-020 never co-change with the top functions in either window. File-level coupling in hotspots.json (`coupled_files`) is empty for all 10.
**Verdict: not supported.** Two 1-commit ties in the window are indistinguishable from noise; full history buries every target under hundreds of equally-ranked functions.

## Q1.6 — code age
Median age of cited lines (days): correct 20–3946 (median 1735), gated 186–4573 (2419), partially 15–5034 (1711), wrong 229 and 2505. Spearman ρ(age, correctness) = −0.01; ρ(age, deserved) = −0.27.
The four oldest findings (>3900 d: FR-021, FR-010, FR-018, FR-019) are the documented/opt-in behaviours (fixed `default_retry_delay`, event dispatcher gated on `task_send_sent_event`, exchange-only routing). FR-016's cited lines are young (98 d median) despite being "documented". **Weakly supported** as a flag for "long-standing deliberate behaviour", with n=4; **not supported** as a correctness signal.

## Q3 — can history predict deserved confidence?
Deserved: 7 high, 8 medium, 6 low. Features per finding are in `results.json → summary.q3.table`.

| rule (3-level prediction) | exact | within 1 | over-rated | under-rated | ρ vs deserved | ρ vs correctness |
|---|---|---|---|---|---|---|
| investigator's claimed | 8 | 20 | 6 | 7 | 0.21 | −0.09 |
| current gate: high iff a cited [fix] commit, else medium | 11 | 15 | 9 | 1 | −0.06 | −0.18 |
| blame: high iff a [fix] commit wrote a cited line | 11 | 15 | 7 | 3 | 0.08 | −0.09 |
| fix commits on cited functions in window (≥2/1/0) | 5 | 16 | 8 | 8 | 0.00 | −0.12 |
| age: old = high | 5 | 15 | 10 | 6 | −0.13 | 0.05 |
| age: young = high | 7 | 17 | 5 | 9 | 0.13 | −0.05 |
| preconditions count (reviewer-derived, not scan-time) | 9 | 17 | 4 | 8 | 0.09 | 0.02 |
| always "medium" (baseline) | 8 | 21 | 7 | 6 | 0 | 0 |

The 13 findings with a cited [fix] commit split 5 deserved-high / 2 medium / 6 low-or-lower; 12 of the 13 fix commits also wrote the cited lines per blame (my blame agrees with the reviewer's `wrote_cited_lines` on 20 of 21 commits; disagreement: FR-006 cd3b42e). The three claimed-high findings all pass the blame rule too; the reviewer rates them high/medium/low. Feature correlations with correctness are all |ρ| ≤ 0.21 (strongest: *number of commits* on the cited functions, ρ = 0.21, which is a fragility signal). No rule beats the constant baseline by more than 3 agreements out of 21, which is inside what re-labelling one or two findings would change.
**Verdict: not supported.** History (fix commits, blame authorship, fix density, age) carries no detectable information about whether a finding is correct; the current gate's only effect is to lift findings whose code was recently *touched by a fix*, which is where the deserved-low findings sit as often as the deserved-high ones. The data cannot rule out a weak effect (n=21, 7/8/6 split), but it cannot show one either.

## Approximations and limits
- Function identity across history is by qualified name; renamed functions split their churn. Full history uses `--follow`, so `worker/job.py` → `request.py` is included.
- Lines in class bodies outside any function (e.g. `Task.default_retry_delay`, `RETRYABLE_DB_ERRORS`) are `<module>` and can only be covered by a pad, never by a function ranking.
- "Coverage" measures the Source block only; the reviewer's `in_bundle` also counts diffs and the history table, which is why FR-003/FR-015 differ.
- Fill policy was fixed at whole-function greedy with truncation; distributing the budget across functions (e.g. a per-function cap) was not tried and could change H02's result.
- Rank B's fix weight (×3) is a guess; rank C shows the ordering is dominated by whether CCN is in the product at all.
- Q3 preconditions are reviewer-derived and listed only to show that even a non-mechanical feature barely beats the baseline.
