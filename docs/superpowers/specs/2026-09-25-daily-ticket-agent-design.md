# Daily ticket agent: design

**Requirements:** [#39](https://github.com/tomstagl/thunderstruck/issues/39). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-25-daily-ticket-agent.md`

## 1. Shape

```
Routine (cron, fresh session per fire)          ← schedule + notification only
  └─ skill  .claude/skills/implement-ticket/    ← the whole procedure, versioned in the repo
       1. gather     model → GitHub MCP          issues, collaborators, open PRs → candidates.json
       2. pick       pick_ticket.py              deterministic: one ticket or none, with reasons
       3. claim      model → GitHub MCP          label agent:in-progress, comment
       4. build      model                       plan tasks in order, test first, one commit each
       5. verify     shell                       full suite, --check generators, plugin validate
       6. PR         model → GitHub MCP          ready PR, Closes #n, AC table
       7. follow     PR activity subscription    CI and review, under the harness's PR rules
  └─ final message                               ← what the Routine's push/email carries
```

The same rule the plugin lives by applies here: **models for judgment, scripts
for anything that must be reproducible.** Deciding *which* ticket is ready is a
rule, so a script does it (AC-4). Implementing the plan is judgment, so the model
does it. The model's part in steps 1, 3 and 6 is I/O only. It fetches and posts, and it
makes no decisions there.

### Why a Routine and not GitHub Actions

A cloud Routine already has the GitHub MCP tools with this repository's access,
push and email notification, and PR-activity subscriptions that wake the
session when CI fails or a review comes in. That covers step 7 with nothing extra to build.
An Actions workflow would need an API key as a repository secret. It would also need
its own notification path and a second mechanism for following the PR.

### Why the procedure is a repo skill and not the Routine prompt

A Routine's prompt is stored outside the repository and changes without review.
A skill under `.claude/skills/` is versioned, reviewed in PRs, and read from
`main` by every fresh session. The Routine prompt stays one line, "Run the
`implement-ticket` skill", and never needs editing.

`.claude/` is project configuration for Claude Code sessions in this checkout.
It is not part of the plugin. The plugin's skills live under `skills/` and are
auto-discovered from there (CLAUDE.md, *Plugin manifest*), so nothing under `.claude/` ships
to plugin users.

## 2. The readiness check: `pick_ticket.py`

Lives beside the skill: `.claude/skills/implement-ticket/pick_ticket.py`.
Stdlib only, run with bare `python3`, and it never calls the network. The model
gathers the GitHub data (the session has no `gh` CLI, only MCP tools) and hands
it over as a file. The script's only side effect is reading `git` in the checkout.

### Input: `candidates.json`

```json
{
  "repo": "tomstagl/thunderstruck",
  "writers": ["tomstagl"],
  "issues": [
    {"number": 39, "title": "…", "body": "…", "author": "tomstagl",
     "labels": ["…"], "state": "open", "claimed_at": null}
  ],
  "open_prs": [
    {"number": 40, "title": "…", "body": "…", "head": "claude/…"}
  ]
}
```

`writers` is the set of collaborator logins with `push`, `maintain` or `admin`
permission. The model gets it from `list_repository_collaborators`.
`claimed_at` is the timestamp of the agent's own claim comment on a ticket
carrying `agent:in-progress`, and `null` otherwise (§3). The skill tells the model
to copy fields verbatim, never to summarise them. The script ignores unknown keys.

### Invocation and output

```
python3 pick_ticket.py candidates.json --ref origin/main --now 2026-09-26T01:52:00Z
```

`--now` is passed in, never read from the clock, so the same inputs always give
the same output (AC-4).

It writes JSON to stdout and always exits 0 unless its input is malformed (exit 2):

```json
{"picked": {"number": 39, "title": "…", "spec": "docs/…-design.md", "plan": "docs/….md"},
 "skipped": [{"number": 19, "reason": "plan not on origin/main: docs/superpowers/plans/…"}],
 "ignored_drafts": [2, 3, 5]}
```

`picked` is `null` when nothing is ready. Drafts go into `ignored_drafts` only,
with no reason, because a draft is not *meant* to be ready (AC-3 covers non-drafts).

### Rules, applied in this order; the first failure is the reason

| # | Rule | Reason string |
|---|---|---|
| 1 | `state == "open"` | not reported (closed issues are filtered out before this point) |
| 2 | title does not contain `draft` anywhere, case-insensitively. This covers `DRAFT:`, `Draft:`, `DRAFT -`, and also `… (draft)` | → `ignored_drafts` |
| 3 | `author in writers` | `author <login> has no write access` |
| 4 | body names exactly one spec path matching `docs/superpowers/specs/\d{4}-\d{2}-\d{2}-[a-z0-9-]+-design\.md` | `no spec path in ticket` / `more than one spec path in ticket` |
| 5 | same for the plan: `docs/superpowers/plans/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md` | `no plan path …` / `more than one plan path …` |
| 6 | spec exists on `--ref` (`git cat-file -e <ref>:<path>`) | `spec not on <ref>: <path>` |
| 7 | plan exists on `--ref` | `plan not on <ref>: <path>` |
| 8 | spec content at `<ref>` contains `#<n>` as a whole token (`#39`, not `#390`) | `spec does not reference #<n>` |
| 9 | plan content at `<ref>` likewise | `plan does not reference #<n>` |
| 10 | no label `agent:in-progress` | `already claimed` |
| 11 | no label `agent:blocked` | `blocked, see ticket comments` |
| 12 | no open PR whose title or body contains `#<n>` as a whole token | `open PR #<m> references it` |

Among the tickets that pass every rule, the lowest `number` wins (AC-2). Rule 4's
pattern ignores placeholders such as `YYYY-MM-DD-…` (see #37), so a ticket whose
spec is "to be written" fails with `no spec path in ticket`, which is the true
reason.

Rules 8 and 9 are what make "merged into `main`" mean *this ticket's* spec. A
ticket can't point at an unrelated spec that happens to exist, whether by
mistake or on purpose, because the merged spec has to name it back. Every spec and
plan on `main` today already does this (`**Requirements:** [#30]…`,
`… in GitHub issue #30`).

Rule 3 and rules 6 to 9 together are the trust boundary for a public repository.
Anyone can open a non-draft issue, but only a writer can open a ticket the agent
will act on. Only a merge to `main` can supply the spec and plan that direct the
work.

## 3. Markers on the ticket

| Label | Set when | Removed when |
|---|---|---|
| `agent:in-progress` | step 3, before any code (AC-5) | PR opened, or blocked, or the run fails |
| `agent:blocked` | step 4 or 5 stops (AC-10) | only by a human, which is how a ticket is released |

When the agent labels a ticket and the label doesn't exist yet, GitHub creates
it, so nothing needs setting up first. Each marker change comes with one ticket comment
saying what happened, with the session link. The comment follows the repo's
attribution-footer rule.

**A run that dies without cleaning up.** If the session fails between claiming
and finishing, `agent:in-progress` stays set and rule 10 skips the ticket from
then on. That is deliberate, because failing closed is safer than two agents on one
ticket. The next run reports it every night (`#n: already claimed`), and a
claim older than 24 h is also listed in that run's notification as "stale
claim, check session <link>". The age comes from the claim comment's timestamp,
which the model passes in as `claimed_at` on the issue. Rule 10 turns into `stale claim
since <ts>` when `claimed_at` is more than 24 h before `--now`. The
ticket stays skipped. A human decides.

## 4. Building (step 4)

- **Branch.** The session's designated branch (`claude/…`), or
  `agent/<n>-<topic>` when the session designates none. The plan's
  `**Branch:**` line names the branch the maintainer would use by hand, but a
  cloud session pushes to the branch it was given. The PR body names the plan's
  branch so the mapping is visible.
- **Order.** The plan's `### Task n` headings in order. Checkboxes already
  ticked on `main` are done and skipped. A task whose plan steps are all ticked
  is skipped too.
- **Test first (AC-6).** For a task that changes behaviour, write the plan's
  test, run exactly that test, and see it fail for the expected reason before
  touching the implementation. The failing output goes in the commit message
  body, one line, e.g. `red: test_x failed: KeyError 'y'`. That leaves a trace
  a reviewer can check. A documentation-only or test-only task says so in its
  commit message instead.
- **One commit per task**, with the plan's commit message if it gives one, and
  the task's `AC-n` in the message.
- **The plan's checkboxes** are ticked in the same commit as the task, as plans
  in this repo already do.

### What counts as blocked (AC-10)

The agent stops, and makes no workaround, when:

- a task needs a file, function, contract or behaviour that neither the plan
  nor the spec defines, and the code on `main` doesn't settle it;
- the plan and spec contradict each other, or the plan contradicts the code on
  `main` in a way the plan's own words don't resolve;
- a test the plan specifies can't be made to fail first, because the behaviour
  already exists, or can't be made to pass without changing another test's
  assertion;
- the checks in §5 are red and the cause is not in code this branch changed,
  after one attempt to fix it;
- the plan asks for something CLAUDE.md forbids.

In any of these cases it does three things. It pushes the branch as it stands. It comments on the ticket naming the
task number, the exact gap, and what decision would unblock it. Then it swaps the labels and
ends with the blocked summary. It never edits the spec or plan to make the gap
go away. That is a design change, and design changes start in the spec
(CLAUDE.md, *Tickets, specs and plans*).

## 5. Verification (step 5, AC-7)

Run in this order, each with its real exit code, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 \
  --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
uv run scripts/gen_catalog_docs.py --check
uv run scripts/gen_sample_report.py --check
claude plugin validate . --strict
```

The suite runs with `THUNDERSTRUCK_REQUIRE_RENDERER=1`, as in CI, so the
renderer tests can't skip. If `claude` isn't on the session's PATH, the plugin
check is reported as *not run* in the PR, never as passed. CI's `plugin` job
covers it on the PR anyway.

After the checks pass, the agent runs the `code-review` skill at `high` on the branch
diff and fixes what it confirms. It then re-runs the checks, once. This is one
extra round, not a loop, matching the plugin's own "exactly one repair round"
rule.

## 6. The PR (step 6, AC-8)

Ready for review, base `main`. The title is the ticket title. The body is:

```
Closes #<n>. Spec: <path>. Plan: <path> (plan branch: <name>).

| AC | Satisfied by |
|----|--------------|
| AC-1 | <commit sha> · tests/…::test_… |
…

## Verified locally
<each command from §5 with its exit code>

## Not verifiable in CI
<ACs the plan marks as needing a model or a human, with what was done>
```

Then comes the attribution trailer the session's instructions require. No PR template
exists in the repo today. If one is added, the skill says to mirror it.

## 7. Following the PR (step 7, AC-9)

The session subscribes to the PR's activity and follows the harness's rules for
a PR it created: fix CI failures, handle review comments, keep going until it is green
and mergeable, never merge. Nothing about this is specific to this skill, and
the skill does not restate those rules. It only says to subscribe.

## 8. Notification (AC-12)

The Routine is created with `notifications: {push: true, email: true}`. What
the notification says is the session's final message. The skill therefore ends every
run with exactly one of four summaries:

- `PR opened: #<m> for #<n> — <title>. Checks: <all green | list>.`
- `Blocked: #<n> at Task <k> — <one-line gap>. Details on the ticket.`
- `Nothing ready. Skipped: #19 plan not on origin/main, …` plus any stale
  claims (§3).
- `Run failed: <what failed>.` This covers malformed picker input, or an unexpected
  error after the claim, which is then handled like *Blocked* so no claim is
  left behind (AC-5).

## 9. Schedule

`CRON_TZ=Europe/Vienna 52 1 * * 1-5`, which is Mon to Fri at 01:52. The ticket's
"around 02:00" is moved a few minutes off the hour, because many schedules fire
on the hour and runs at that moment can be delayed. The schedule is fresh-session-per-fire, so each night starts clean from `main`.
Notification: push and email.

The Routine is created only after this PR merges. Before that, a fresh session
would check out `main` without the skill and fail on its first step.

## 10. Security

- **Untrusted input.** Ticket bodies and comments, PR bodies and review comments are
  data (AC-11). Only rule 3 plus rules 6 to 9 decide what gets built, and only the merged
  spec and plan say how. The skill states this in its first section, in the
  same words the plugin's investigator prompt uses for scanned code.
- **No new credentials.** The Routine uses the session's existing GitHub
  access. No secrets are written to the repo, the ticket or the PR.
- **Bounded.** One ticket per run. No parallel runs, because a claimed ticket is
  skipped. One repair round in §5. The tool already demands this of the code it
  scans (CLAUDE.md: *The plugin must not exhibit the patterns it hunts*).

## 11. Test strategy

`tests/test_pick_ticket.py` loads the script by path (it isn't a package) and
drives it with `candidates.json` fixtures against a throwaway git repository
built in `tmp_path`. There is one test per rule row in §2, plus these:

- lowest number wins among several ready tickets;
- a `#390` in the spec does not satisfy `#39`;
- a placeholder spec path (`YYYY-MM-DD-…`) reports `no spec path in ticket`;
- every draft spelling, including `draft` in the middle of a title, lands in `ignored_drafts`;
- a claim older than 24 h reports `stale claim since …`;
- malformed input exits 2, and every other outcome exits 0.

The skill itself is model procedure and can't be unit-tested. Its first real
run is the acceptance test for AC-5 to AC-12, and that run is recorded on #39.

## 12. Decisions

- **Labels over assignees for the claim.** The Routine acts as the maintainer's
  GitHub identity, so self-assignment would look the same as the maintainer
  taking the ticket by hand.
- **Lowest number first**, not "most recently readied". It is simple, stable,
  and it matches the order tickets were agreed in.
- **Model gathers, script decides.** The session has no `gh` and no GitHub
  token outside MCP. A script that called the API would need one.

## 13. Open design questions

- Can a fresh Routine session push to a branch named by the plan, rather than
  its designated `claude/…` branch? If so, §4 should prefer the plan's branch.
- Should a stale claim (§3) be released automatically after some number of days, or
  stay a human decision? The ticket's open question about blocked reminders is
  the product side of the same question.
