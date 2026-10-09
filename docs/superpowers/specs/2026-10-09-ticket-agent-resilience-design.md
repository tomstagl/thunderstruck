# Ticket agent resilience: design

**Requirements:** [#79](https://github.com/tomstagl/thunderstruck/issues/79). Acceptance criteria are cited as `AC-n` and live there.
**Builds on:** [`2026-09-25-daily-ticket-agent-design.md`](2026-09-25-daily-ticket-agent-design.md) (#39). Its sections are cited as `#39 §n`; bare `§n` is this document.

## 1. Problem and shape

The first real run (#58) built Tasks 1 to 6, then stopped at Task 7. The plan
required report wording that a test merged to `main` afterwards (#78) forbids.
The agent was right to stop (#39 §4, *What counts as blocked*). Three gaps cost a
night and left nothing to review:

1. **Late detection.** The conflict was checkable before Task 1: #78 changed
   files the plan names, after the plan was last touched.
2. **Stranded work.** Tasks 1 to 6 sit on a pushed branch with no PR.
3. **No cheap release.** The fix was one wording change, but the release path
   is: a human edits spec and plan, then removes `agent:blocked`, then waits
   for the next night.

The agent keeps one invariant: it never changes the contract it builds against
on its own authority. What changes is that it may *propose* a change as a
separate PR a human merges.

```
pick ─► preflight ─► claim ─► build ──► verify ─► PR
          │ drift       │       │ conflict
          ▼             │       ▼
   amendment PR ◄───────┴── amendment PR + draft PR (partial work)
   (human merges)                │
          └──── next night: picker takes the ticket, build resumes ◄──┘
```

## 2. Preflight: `plan_drift.py`

New, beside the skill: `.claude/skills/implement-ticket/plan_drift.py`. Stdlib
only, bare `python3`, no network, same contract as `pick_ticket.py`: JSON on
stdout, exit 0 unless the input is unusable (exit 2). Same inputs, same output.

```
python3 plan_drift.py --plan <path> --spec <path> --ref origin/main
```

1. **Base.** `base` is the last commit on `--ref` that touched the plan or the
   spec, whichever is later. That is the point where a human last agreed the
   contract matched `main`. After an amendment merges, the base moves up to it,
   so the same drift is never reported twice.
2. **Named paths.** Every repo path the plan or spec names: backticked tokens
   containing `/` or ending in a known extension, with a `::test_id` suffix
   stripped. A path counts if it exists at `base` or at `--ref`. Paths a task
   creates exist at neither and are ignored.
3. **Drift.** Commits in `base..--ref` that touch a named path:

```json
{"base": "5122511…",
 "named": 41,
 "drifted": [{"sha": "…", "subject": "…", "paths": ["tests/test_report.py"]}],
 "gone": [{"path": "scripts/old.py", "change": "deleted"}],
 "truncated": false}
```

`gone` lists named paths present at `base` and absent at `--ref`, with the
change (`deleted`, or `renamed` plus the new path from `git diff -M`).
`drifted` is capped at 30 entries, newest first, with `truncated: true` beyond.

The script only narrows. It cannot know that a commit contradicts a plan; the
agent reads the diffs of the listed commits against the plan's tasks and
decides (§3). An empty `drifted` and `gone` ends preflight at once.

**Baseline.** Preflight then runs the full suite on a clean `origin/main`
(the command in `SKILL.md` step 7). Red means `Run failed: main is red at
<sha>`: no claim, no label, no amendment. It is not a plan problem. The
baseline also gives the agent main's current numbers (counts, budgets) to
compare against the plan's expected figures. The #58 token figure was off for
exactly this reason.

## 3. The amendment PR

When the agent concludes the plan or spec cannot be built as written, because
of drift found in preflight or a conflict met mid-build, it classifies the gap:

| Gap | Outcome |
|---|---|
| Plan or spec wording/steps conflict with `main`, or each other, and one conforming text is clear | **Amendment PR** |
| More than one reasonable design, or the fix would change an `AC-n`, the ticket scope or a CLAUDE.md rule | `agent:blocked`, as today |
| `main` is red outside the branch's changes | `Run failed`, as today |

An amendment PR:

- is from `agent/<n>-amend`, based on `origin/main`, **ready for review**;
- changes only the ticket's spec and plan. The agent checks
  `git diff --name-only origin/main` is a subset of those two paths before
  pushing, and stops as `agent:blocked` if not;
- is as small as the gap allows and never touches an acceptance criterion;
- is titled `Amend spec and plan for #<n>: <gap>` and its body gives, in
  order: the quoted plan or spec line, the `main` commit (sha and PR) that
  conflicts with it, the proposed wording, and any alternative considered;
- says "Merging this releases #<n>; the agent resumes the next night."

The ticket gets one comment linking it. No label is applied: the open PR is the
gate (§5). The agent never merges it.

**Bounded.** At most one amendment per ticket is automatic. If a closed,
unmerged PR from `agent/<n>-amend` exists, or the gap recurs after an
amendment merged, the agent labels `agent:blocked` instead and says why. The
agent therefore cannot loop on its own proposals. The plugin may not exhibit
the patterns it hunts (CLAUDE.md).

`SKILL.md` §1 changes from "never change a spec, a plan or a ticket body" to:
never on the build branch, never a ticket body, and a spec or plan only through
the amendment PR above.

## 4. Partial work stays visible

A mid-build stop commits whatever is sound, pushes, and opens a **draft** PR:

- title `<ticket title> (blocked at Task <k>)`; body begins `Refs #<n>`, never
  `Closes`, and links the amendment PR or the ticket comment;
- lists the tasks done, the task stopped at, and the checks last run.

Preflight stops open no branch and no draft: nothing was built.

**Resume.** The picker (§5) hands the run the draft PR's branch. The agent
checks it out and merges `origin/main` in (it now holds the amendment). A
conflict in the plan file resolves to `origin/main`'s text, and the agent
re-ticks each task that has a commit on the branch. For that, every task commit
carries a `Task: <k>` trailer. Then it continues with the first undone task,
finishes, verifies, rewrites the PR body into the #39 §6 form with `Closes`, and
marks the PR ready. No second PR.

## 5. Picker changes: `pick_ticket.py`

`candidates.json` gains `draft` (bool) and `head_repo` (full name) on each open
PR; `head` is already there.

- **Rule 12 narrowed.** A PR referencing `#<n>` blocks the ticket unless it is
  an *agent draft*: `draft` is true, `head` matches `agent/<n>-…` (not
  `agent/<n>-amend`), and `head_repo` equals the candidates' `repo`. The
  repo check keeps a fork from making a ticket resume from a branch it
  controls.
- **Rule 12a, new, before 12.** An open PR whose `head` is exactly
  `agent/<n>-amend` and `head_repo` equals `repo` skips the ticket:
  `waits for amendment PR #<m>`. Once it merges, nothing holds the ticket.
  If it is closed unmerged, §3's bound applies.
- **Output.** `picked` gains `resume: {"branch": …, "pr": <m>}` when an agent
  draft exists, else `null`.

Both rules can only hold a ticket back or hand it a same-repo branch. Neither
widens the trust boundary (#39 §2).

## 6. Skill and summary changes

`SKILL.md`: a new step *Preflight* between *Pick* and *Claim*; *Blocked* (step
6) gains the amendment branch and the draft PR; *Build* gains the `Task: <k>`
trailer and resume; step 1's prohibition is reworded (§3 above). The final
summary gains a fifth line:

`Amendment proposed: #<m> for #<n> — <one-line gap>. Merge to release.`

and `Blocked` adds "Draft PR: #<m>" when one exists. #39 §8's list is
extended the same way.

## 7. Requirement changes needed in the ticket first

CLAUDE.md puts requirements in the ticket before the spec. These existing #39
criteria no longer hold as written, and the new ticket must supersede them by
number: **AC-1** (no open PR references it), **AC-10** (opens no PR; never
edits the spec or plan, in *Out* as well), **AC-12** (the set of outcomes),
**AC-13** (release instructions). Nothing here restates them.

## 8. Test strategy

- `tests/test_plan_drift.py`, same style as `test_pick_ticket.py`: a throwaway
  repo in `tmp_path`. Cases: no drift; a commit touching a named test file;
  a commit touching an unnamed file; a deleted path and a renamed one; a path
  the plan creates; a `::test_id` suffix; base moving after a commit to the
  plan; `truncated` at 31 commits; identical output on a second run.
- `tests/test_pick_ticket.py` additions: agent draft does not block and yields
  `resume`; the same PR from a fork does block; `agent/<n>-amend` open gives
  `waits for amendment PR #m`; merged (absent) releases; a non-draft PR still
  blocks.
- **Replay acceptance (manual, recorded on the ticket).** Run `plan_drift.py`
  over the #58 plan with `--ref` at #78's merge commit. It must list #78. If it
  does not, the path extraction in §2 is wrong, not the replay.
- The skill is model procedure and cannot be unit-tested. The first run that
  hits a conflict is its acceptance test, as in #39 §11.

## 9. Decisions

- **Propose, never edit in place.** Option "continue within a deviation rule"
  was rejected: it lets the agent decide design on its own authority, which is
  the line #39 draws. An amendment keeps that line and turns the release into
  one merge.
- **Draft PR, not a branch alone.** A pushed branch is invisible; a draft is in
  the PR list, runs CI and shows what is stranded.
- **Script narrows, model judges.** Whether a commit contradicts a plan is a
  reading task. Which commits could is a `git log` query and is reproducible.
- **No label for the amendment wait.** The open PR is already visible and
  already the thing a human acts on; a label would be a second marker to keep
  in step.

## 10. Decisions on what was open

- **Marking a draft ready.** Resume calls `update_pull_request` with
  `draft: false`. If the tool offers no such field, the agent closes the draft
  with a comment and opens a ready PR from the same branch, linking the draft.
  Either way the branch and its commits are the same.
- **Plan conflicts on resume.** The `Task: <k>` trailer re-ticks tasks. A merge
  conflict anywhere in the plan file other than `- [ ]` / `- [x]` lines is not
  resolved by the agent: it uses `agent:blocked` (#79 AC-9).
- **Baseline cost.** The baseline suite runs only when the drift list is
  non-empty (§2), so a quiet night costs one `git log`.
