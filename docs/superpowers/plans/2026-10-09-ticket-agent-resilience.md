# Ticket Agent Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The nightly ticket agent finds that a merged plan has gone stale before it builds, proposes the fix as a PR a human merges, and leaves stranded work in a draft PR it can resume.

**Architecture:** A new stdlib script, `plan_drift.py`, lists commits on `origin/main` since the spec and plan were last touched that change files they name. `pick_ticket.py` learns two kinds of agent PR: an amendment PR holds its ticket, and an agent draft PR is resumed instead of blocking. `SKILL.md` gains a preflight, an amendment step and a resume path. Documentation follows.

**Tech Stack:** Python 3 stdlib (bare `python3`), pytest, git. No plugin code changes.

**Spec:** `docs/superpowers/specs/2026-10-09-ticket-agent-resilience-design.md` (cited `§n` below; `#39 §n` is `2026-09-25-daily-ticket-agent-design.md`). Requirements AC-1…AC-12 are in GitHub issue #79.

**Branch:** `feat/ticket-agent-resilience`. One commit per task, `(#79)` in the subject, the task's `AC-n` in the body. The full suite passes on every commit, and its real exit code is checked:

```bash
THUNDERSTRUCK_REQUIRE_RENDERER=1 uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

## Global Constraints

- Both scripts are stdlib only and run on bare `python3`, never `uv` (#39 §2). No syntax or method newer than Python 3.8: no `str.removeprefix`, no `match`, no `X | Y` outside annotations under `from __future__ import annotations`.
- Neither script touches the network. Output is JSON on stdout; exit 0, or exit 2 when the input is unusable. Same inputs, same bytes out.
- Nothing under `skills/`, `agents/`, `hooks/`, `scripts/`, `catalog/` changes, so there is no version bump and no CHANGELOG entry. `.claude/` ships to no one.
- The agent never merges, never edits a ticket body, and edits a spec or plan only on the `agent/<n>-amend` branch (#79 AC-11).
- Existing tests are changed only where the contract they pin changes on purpose. The two that do are named in Task 2.

## Review Focus

- **Shallow clone.** The Routine starts from a fresh clone. A shallow history makes the clone boundary look like the plan's last commit and reports no drift. Expected: the script exits 2 and says so (Task 1); the skill unshallows first (Task 3).
- **Fork spoofing.** A PR from a fork can name its head `agent/39-x` or `agent/39-amend`. Expected: it is an ordinary PR and blocks the ticket; it never gives the agent a branch to resume (Task 2).
- **Missing PR fields.** The model forgets `draft` or `head_repo` when gathering. Expected: the PR blocks the ticket, never releases it (Task 2).
- **Two drafts for one ticket.** Expected: the lowest PR number is resumed, the same on every run (Task 2).
- **A second conflict.** A gap recurs after one amendment, or the first amendment was closed unmerged. Expected: `agent:blocked`, never another amendment (Task 3, step 6a).
- **Quiet night.** No drift. Expected: one `git log`, no baseline suite, no label, no comment (Task 3, step 3a).

---

### Task 0: Preconditions

- [ ] `.claude/skills/implement-ticket/pick_ticket.py`, `SKILL.md` and `tests/test_pick_ticket.py` exist on `origin/main`, and `uv run --with pytest pytest tests/test_pick_ticket.py -q` passes. If they do not, stop: #39 has not merged.
- [ ] `git fetch origin main && git merge-base --is-ancestor origin/main HEAD`. Merge `origin/main` in if it is not.
- [ ] `git rev-parse --is-shallow-repository` prints `false`. If `true`, run `git fetch --unshallow` (Task 1's replay needs history).

### Task 1: The drift check (AC-1)

**Files:** new `.claude/skills/implement-ticket/plan_drift.py`; new `tests/test_plan_drift.py`.

**Interfaces:**
- Produces: `python3 plan_drift.py --plan P --spec S --ref R` prints `{"base": sha, "named": int, "drifted": [{"sha", "subject", "paths"}], "gone": [{"path", "change", "to"?}], "truncated": bool}`. Exit 2 with a message on stderr when the ref, plan or spec is unusable or the clone is shallow. Task 3 runs it.

- [ ] **Step 1: Write the tests.** Create `tests/test_plan_drift.py`:

```python
"""The ticket agent's drift check (#79).

It narrows what the agent has to read before building: the commits that
landed on main after the spec and plan were last agreed, on files they name.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude" / "skills" / "implement-ticket" / "plan_drift.py"

SPEC = "docs/superpowers/specs/2026-10-09-x-design.md"
PLAN = "docs/superpowers/plans/2026-10-09-x.md"
PLAN_TEXT = """# X plan

Edit `scripts/a.py:10-20`, then run `pytest tests/test_a.py::test_x -v`.
Task 3 creates `scripts/new.py`. Task 4 removes `scripts/gone.py` and moves
`scripts/old.py`. Not paths: `agent:blocked`, `uv run scripts/a.py --top 3`,
`https://example.com/a.py`, `docs/superpowers/plans/`.
"""
SPEC_TEXT = "# X design\n\nSee [#79](https://example.com/issues/79) and `catalog/x.yaml`.\n"


def _git(repo: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "init.defaultBranch=main", *args],
                   cwd=repo, env=env, check=True, capture_output=True)


def commit(repo: Path, message: str, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        path = repo / rel
        if text is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


@pytest.fixture
def repo(tmp_path) -> Path:
    _git(tmp_path, "init", "-q")
    commit(tmp_path, "contract agreed", {
        SPEC: SPEC_TEXT, PLAN: PLAN_TEXT,
        "scripts/a.py": "a\n", "scripts/gone.py": "g\n", "scripts/old.py": "o\n" * 20,
        "scripts/unnamed.py": "u\n", "tests/test_a.py": "t\n", "catalog/x.yaml": "c: 1\n",
    })
    return tmp_path


def run(repo: Path, ref="HEAD", plan=PLAN, spec=SPEC):
    proc = subprocess.run([sys.executable, str(SCRIPT), "--plan", plan, "--spec", spec,
                           "--ref", ref], cwd=repo, capture_output=True, text=True)
    return proc.returncode, (json.loads(proc.stdout) if proc.returncode == 0 else None), proc


def test_nothing_changed_since_the_contract(repo):
    code, out, _ = run(repo)
    assert code == 0
    assert out["drifted"] == [] and out["gone"] == [] and out["truncated"] is False


def test_a_commit_on_a_named_file_is_listed(repo):
    commit(repo, "Change the test", {"tests/test_a.py": "changed\n"})
    _, out, _ = run(repo)
    assert [(d["subject"], d["paths"]) for d in out["drifted"]] == \
        [("Change the test", ["tests/test_a.py"])]


def test_a_commit_on_an_unnamed_file_is_not(repo):
    commit(repo, "Elsewhere", {"scripts/unnamed.py": "changed\n"})
    assert run(repo)[1]["drifted"] == []


def test_line_and_test_id_suffixes_name_the_file(repo):
    commit(repo, "Edit a", {"scripts/a.py": "changed\n"})
    commit(repo, "Edit the test", {"tests/test_a.py": "changed\n"})
    paths = [p for d in run(repo)[1]["drifted"] for p in d["paths"]]
    assert paths == ["tests/test_a.py", "scripts/a.py"]  # newest first


def test_only_files_in_the_tree_are_named(repo):
    # a.py, test_a.py, gone.py, old.py, x.yaml exist; new.py does not; the rest are not files
    assert run(repo)[1]["named"] == 5


def test_a_file_the_plan_creates_that_main_then_gains_is_drift(repo):
    commit(repo, "Someone added new.py", {"scripts/new.py": "n\n"})
    _, out, _ = run(repo)
    assert [d["paths"] for d in out["drifted"]] == [["scripts/new.py"]]


def test_deleted_and_renamed_files_are_gone(repo):
    commit(repo, "Remove gone", {"scripts/gone.py": None})
    (repo / "scripts/old.py").rename(repo / "scripts/older.py")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "Rename old")
    gone = run(repo)[1]["gone"]
    assert gone == [{"path": "scripts/gone.py", "change": "deleted"},
                    {"path": "scripts/old.py", "change": "renamed", "to": "scripts/older.py"}]


def test_the_base_moves_when_the_plan_or_spec_is_touched(repo):
    commit(repo, "Drift", {"scripts/a.py": "changed\n"})
    commit(repo, "Amend the plan", {PLAN: PLAN_TEXT + "\nAmended.\n"})
    _, out, _ = run(repo)
    assert out["drifted"] == []
    assert out["base"] == subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                         capture_output=True, text=True).stdout.strip()


def test_the_list_is_capped_and_says_so(repo):
    for i in range(31):
        commit(repo, f"Edit {i}", {"scripts/a.py": f"{i}\n"})
    out = run(repo)[1]
    assert len(out["drifted"]) == 30 and out["truncated"] is True
    assert out["drifted"][0]["subject"] == "Edit 30"


def test_output_is_byte_stable(repo):
    commit(repo, "Edit a", {"scripts/a.py": "changed\n"})
    assert run(repo)[2].stdout == run(repo)[2].stdout


@pytest.mark.parametrize("kwargs", [{"ref": "no-such-ref"}, {"plan": "docs/superpowers/plans/missing.md"},
                                    {"spec": "docs/superpowers/specs/missing-design.md"}])
def test_an_unusable_input_exits_2(repo, kwargs):
    code, _, proc = run(repo, **kwargs)
    assert code == 2 and proc.stdout == ""


def test_a_shallow_clone_exits_2(repo, tmp_path):
    commit(repo, "More history", {"scripts/a.py": "changed\n"})
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow)],
                   check=True, capture_output=True)
    code, _, proc = run(shallow)
    assert code == 2 and "shallow" in proc.stderr and proc.stdout == ""


def test_the_script_is_stdlib_only():
    tree = ast.parse(SCRIPT.read_text())
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    bad = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
           if a.name.split(".")[0] not in stdlib]
    bad += [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
            and n.module and n.module.split(".")[0] not in stdlib]
    assert not bad, f"plan_drift.py imports non-stdlib modules: {bad}"
```

- [ ] **Step 2: Run them and see them fail.**
  `uv run --with pytest pytest tests/test_plan_drift.py -q` — expected: failures because `plan_drift.py` does not exist (the subprocess exits non-zero).
- [ ] **Step 3: Write the script.** Create `.claude/skills/implement-ticket/plan_drift.py`:

```python
#!/usr/bin/env python3
"""What changed on main since a ticket's spec and plan were last agreed (#79).

The spec and plan are written against the code as it was. This lists the
commits that landed afterwards on files they name, so the agent reads those
diffs before building instead of meeting the conflict at Task 7. It narrows;
it never decides whether a commit contradicts the plan.

    python3 plan_drift.py --plan docs/…/plan.md --spec docs/…/spec-design.md --ref origin/main

Exit 0 with JSON on stdout. Exit 2 when the ref, the plan or the spec is
unusable. Stdlib only; it never touches the network.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

CAP = 30
EXTENSIONS = (".py", ".md", ".yaml", ".yml", ".json", ".html", ".toml", ".txt", ".sh", ".cfg")
# Any word of the text may be a path: in a sentence, a code span, a command or
# a fenced block. Words that are not files in the tree are dropped later.
WORD_RE = re.compile(r"[^\s`'\"(),;<>\[\]{}|*?]+")
# `tests/x.py::test_y` and `scripts/x.py:123-145` name the file.
SUFFIX_RE = re.compile(r"(::.*|:\d+(?:-\d+)?)$")


class BadInput(Exception):
    pass


def git(*args: str) -> str:
    proc = subprocess.run(["git", "--literal-pathspecs", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise BadInput(proc.stderr.strip() or f"git {args[0]} failed")
    return proc.stdout


def tree(ref: str) -> set[str]:
    return set(git("ls-tree", "-r", "--name-only", "-z", ref).split("\0")) - {""}


def named_tokens(text: str) -> set[str]:
    found = set()
    for word in WORD_RE.findall(text):
        word = SUFFIX_RE.sub("", word.rstrip(".:"))
        word = word[2:] if word.startswith("./") else word
        if word and "://" not in word and ("/" in word or word.endswith(EXTENSIONS)):
            found.add(word)
    return found


def base_commit(ref: str, plan: str, spec: str) -> str:
    sha = git("log", "-1", "--format=%H", ref, "--", plan, spec).strip()
    if not sha:
        raise BadInput(f"neither {plan} nor {spec} is on {ref}")
    return sha


def renames(base: str, ref: str) -> dict[str, str]:
    parts = git("diff", "--name-status", "-M", "-z", base, ref).split("\0")
    moved, i = {}, 0
    while i < len(parts) and parts[i]:
        code = parts[i]
        if code[0] in "RC":
            if code[0] == "R":
                moved[parts[i + 1]] = parts[i + 2]
            i += 3
        else:
            i += 2
    return moved


def drift(plan: str, spec: str, ref: str) -> dict:
    # A shallow clone makes the last commit on the plan the clone's boundary,
    # which reports no drift at all. Refusing is honest; guessing is not.
    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        raise BadInput("shallow clone: history is incomplete (git fetch --unshallow)")
    for path in (plan, spec):
        git("cat-file", "-e", f"{ref}:{path}")  # BadInput when absent
    base = base_commit(ref, plan, spec)
    before, after = tree(base), tree(ref)
    text = git("show", f"{ref}:{plan}") + "\n" + git("show", f"{ref}:{spec}")
    named = named_tokens(text) & (before | after)

    drifted = []
    if named:
        log = git("log", "--no-merges", "--no-renames", "--name-only",
                  "--format=%x01%H%x00%s", f"{base}..{ref}", "--", *sorted(named))
        for block in log.split("\x01")[1:]:
            head, _, files = block.partition("\n")
            sha, _, subject = head.partition("\x00")
            touched = sorted(set(files.split("\n")) & named)
            if touched:
                drifted.append({"sha": sha, "subject": subject, "paths": touched})

    moved = renames(base, ref)
    gone = []
    for path in sorted((named & before) - after):
        entry = {"path": path, "change": "renamed" if path in moved else "deleted"}
        if path in moved:
            entry["to"] = moved[path]
        gone.append(entry)

    return {"base": base, "named": len(named), "drifted": drifted[:CAP], "gone": gone,
            "truncated": len(drifted) > CAP}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--ref", default="origin/main")
    args = ap.parse_args(argv)
    try:
        result = drift(args.plan, args.spec, args.ref)
    except BadInput as exc:
        print(f"plan_drift: {exc}", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and see them pass.**
  `uv run --with pytest pytest tests/test_plan_drift.py -q` — expected: 15 passed.
- [ ] **Step 5: Run it under the bare interpreter,** which is what the Routine uses:
  `python3 .claude/skills/implement-ticket/plan_drift.py --plan docs/superpowers/plans/2026-10-09-ticket-agent-resilience.md --spec docs/superpowers/specs/2026-10-09-ticket-agent-resilience-design.md --ref HEAD | head -5` — expected: JSON with `"drifted": []`, no traceback.
- [ ] **Step 6:** Full suite (exit code checked), then commit:

```bash
git add .claude/skills/implement-ticket/plan_drift.py tests/test_plan_drift.py
git commit -m "Ticket agent: list what changed on main since the plan was agreed (#79)" \
  -m "AC-1. Task: 1" -m "red: test_plan_drift.py failed: plan_drift.py did not exist"
```

### Task 2: The picker handles amendment and draft PRs (AC-7, AC-8)

**Files:** modify `.claude/skills/implement-ticket/pick_ticket.py`; modify `tests/test_pick_ticket.py`.

**Interfaces:**
- Consumes: each `open_prs` entry may now carry `draft` (bool) and `head_repo` (`owner/name`); `repo` is already top-level.
- Produces: `picked` gains `resume`: `{"branch": str, "pr": int}` or `null`. A new skip reason `waits for amendment PR #<m>`. Task 3's skill reads both.

- [ ] **Step 1: Change the two tests that pin the exact `picked` shape,** `test_a_ready_ticket_is_picked` and `test_the_next_ticket_is_picked_while_one_waits`. Each expected dict gains `"resume": None`:

```python
    assert out["picked"] == {"number": 39, "title": "A ready ticket", "spec": SPEC, "plan": PLAN,
                              "resume": None}
```
```python
    assert out["picked"] == {"number": 41, "title": "A ready ticket",
                             "spec": NEXT_SPEC, "plan": NEXT_PLAN, "resume": None}
```

- [ ] **Step 2: Append the new tests** to `tests/test_pick_ticket.py`:

```python
# -- amendment and draft PRs (#79) --------------------------------------------------------

REPO = "tomstagl/thunderstruck"


def pr(number, head, draft=False, head_repo=REPO, title="x", body="Refs #39."):
    return {"number": number, "title": title, "body": body, "head": head,
            "draft": draft, "head_repo": head_repo}


def test_an_open_amendment_pr_holds_the_ticket(repo, tmp_path):
    amend = pr(80, "agent/39-amend", title="Amend spec and plan for #39: x")
    assert reason(repo, tmp_path, issue(), prs=[amend]) == "waits for amendment PR #80"


def test_a_merged_amendment_releases_the_ticket(repo, tmp_path):
    _, out, _ = run(repo, tmp_path, candidates(issue(), prs=[]))
    assert out["picked"]["number"] == 39


def test_an_amendment_from_a_fork_is_an_ordinary_pr(repo, tmp_path):
    amend = pr(80, "agent/39-amend", head_repo="stranger/thunderstruck")
    assert reason(repo, tmp_path, issue(), prs=[amend]) == "open PR #80 references it"


def test_an_agent_draft_does_not_block_and_is_resumed(repo, tmp_path):
    draft = pr(81, "agent/39-library-leads", draft=True)
    _, out, _ = run(repo, tmp_path, candidates(issue(), prs=[draft]))
    assert out["picked"]["resume"] == {"branch": "agent/39-library-leads", "pr": 81}


def test_the_lowest_draft_is_resumed(repo, tmp_path):
    drafts = [pr(83, "agent/39-b", draft=True), pr(81, "agent/39-a", draft=True)]
    _, out, _ = run(repo, tmp_path, candidates(issue(), prs=drafts))
    assert out["picked"]["resume"]["pr"] == 81


def test_a_draft_from_a_fork_still_blocks(repo, tmp_path):
    draft = pr(81, "agent/39-x", draft=True, head_repo="stranger/thunderstruck")
    assert reason(repo, tmp_path, issue(), prs=[draft]) == "open PR #81 references it"


def test_a_draft_without_head_repo_still_blocks(repo, tmp_path):
    draft = {"number": 81, "title": "x", "body": "Refs #39.", "head": "agent/39-x", "draft": True}
    assert reason(repo, tmp_path, issue(), prs=[draft]) == "open PR #81 references it"


def test_a_ready_agent_pr_still_blocks(repo, tmp_path):
    ready = pr(81, "agent/39-x", draft=False)
    assert reason(repo, tmp_path, issue(), prs=[ready]) == "open PR #81 references it"


def test_a_draft_for_a_longer_number_is_not_this_tickets(repo, tmp_path):
    other = pr(81, "agent/390-x", draft=True, body="Closes #39.")
    assert reason(repo, tmp_path, issue(), prs=[other]) == "open PR #81 references it"


def test_another_pr_still_blocks_beside_a_draft(repo, tmp_path):
    prs = [pr(81, "agent/39-x", draft=True), pr(82, "claude/y", body="Closes #39.")]
    assert reason(repo, tmp_path, issue(), prs=prs) == "open PR #82 references it"
```

- [ ] **Step 3: Run and see the new ones fail.**
  `uv run --with pytest pytest tests/test_pick_ticket.py -q` — expected: the two changed tests and the amendment/draft tests fail (`KeyError: 'resume'` or a wrong reason); nothing else.
- [ ] **Step 4: Change `pick_ticket.py`.** After `STALE_AFTER = timedelta(hours=24)` add:

```python


def amend_head(n: int) -> str:
    """The branch of the agent's amendment PR for ticket n (#79 spec §3)."""
    return f"agent/{n}-amend"
```

  Before `def skip_reason(` add:

```python
def _own(pr: dict, repo: str) -> bool:
    """A PR from a branch of this repository. A fork's PR can name any branch it likes."""
    return bool(repo) and pr.get("head_repo") == repo


def _is_agent_draft(pr: dict, n: int, repo: str) -> bool:
    head = str(pr.get("head") or "")
    return (pr.get("draft") is True and _own(pr, repo)
            and head.startswith(f"agent/{n}-") and head != amend_head(n))


```

  Replace the signature and docstring of `skip_reason`:

```python
def skip_reason(issue: dict, writers: set[str], prs: list[dict], ref: Ref,
                now: datetime, open_issues: set[int], repo: str = "") -> tuple[str | None, dict]:
    """The first rule the ticket fails (spec §2, rules 3–13, #79 spec §5), or None."""
```

  Replace rule 12's loop:

```python
    for pr in prs:
        if mentions(pr.get("title") or "", n) or mentions(pr.get("body") or "", n):
            return f"open PR #{pr['number']} references it", {}
```
  with:

```python
    prs = sorted(prs, key=lambda pr: pr["number"])
    for pr in prs:  # rule 12a: the amendment PR is the gate
        if pr.get("head") == amend_head(n) and _own(pr, repo):
            return f"waits for amendment PR #{pr['number']}", {}
    resume = None
    for pr in prs:  # rule 12: an agent draft is work to resume, not a reason to wait
        if _is_agent_draft(pr, n, repo):
            resume = resume or {"branch": pr["head"], "pr": pr["number"]}
        elif mentions(pr.get("title") or "", n) or mentions(pr.get("body") or "", n):
            return f"open PR #{pr['number']} references it", {}
```

  Change the final return of `skip_reason` to `return None, {"spec": spec, "plan": plan, "resume": resume}`, and in `pick()` pass the repo:

```python
        why, paths = skip_reason(issue, writers, data["open_prs"], ref, now, open_issues,
                                  str(data.get("repo") or ""))
```

- [ ] **Step 5: Run and see everything pass.**
  `uv run --with pytest pytest tests/test_pick_ticket.py -q` — expected: 59 passed.
- [ ] **Step 6:** Full suite (exit code checked), then commit:

```bash
git add .claude/skills/implement-ticket/pick_ticket.py tests/test_pick_ticket.py
git commit -m "Ticket agent: an amendment PR holds its ticket, an agent draft is resumed (#79)" \
  -m "AC-7, AC-8. Task: 2" -m "red: test_an_agent_draft_does_not_block_and_is_resumed failed: KeyError 'resume'"
```

### Task 3: The skill: check, amend, draft, resume (AC-2 … AC-6, AC-9, AC-10, AC-11)

**Files:** modify `.claude/skills/implement-ticket/SKILL.md`; modify `tests/test_pick_ticket.py` (`test_the_skill_names_every_step`).

The skill is model procedure. The test only guards that the procedure keeps its steps. Step numbers 3a and 6a are deliberate: other text cites steps 7 and 10 by number, and the design cross-references them.

- [ ] **Step 1: Extend the guard test.** In `test_the_skill_names_every_step`, add these needles to the tuple:
  `"plan_drift.py", "--unshallow", "agent/<n>-amend", "Amendment proposed:", "Task: <k>", "Refs #", "draft: false"`.
- [ ] **Step 2: Run it and see it fail.**
  `uv run --with pytest pytest "tests/test_pick_ticket.py::test_the_skill_names_every_step" -q` — expected: `SKILL.md no longer mentions 'plan_drift.py'`.
- [ ] **Step 3: Edit `SKILL.md`.** Apply each replacement exactly; every `old` block appears once.

  **3a. Step 1, the prohibition.** Replace
```
- change a spec, a plan or a ticket body. The one exception is ticking a
  plan checkbox, `- [ ]` → `- [x]`, for a task you finished;
```
  with
```
- change a ticket body, or a spec or plan anywhere but the amendment branch of
  step 6a, which a human merges. The one other exception is ticking a plan
  checkbox, `- [ ]` → `- [x]`, for a task you finished;
```

  **3b. Step 2, the PR fields.** Replace
```
- `list_pull_requests`, state `open`, all pages: `number`, `title`, `body`,
  `head` (= `head.ref`).

Write them to `$S/candidates.json` in the shape given in spec §2.
```
  with
```
- `list_pull_requests`, state `open`, all pages: `number`, `title`, `body`,
  `head` (= `head.ref`), `draft` and `head_repo` (= `head.repo.full_name`).

Write them to `$S/candidates.json` in the shape given in spec §2, plus `draft`
and `head_repo` on each PR (#79 spec §5).
```

  **3c. Step 3, the pick.** Replace
```
- Otherwise continue with the picked ticket `#n` and its `spec` and `plan` paths.
```
  with
```
- Otherwise continue with the picked ticket `#n`, its `spec` and `plan` paths,
  and `resume`: `null`, or the branch and PR number of the agent's own draft
  from an earlier run (#79 spec §4).
```
  and, after the paragraph ending "…and don't pick a\ndifferent ticket.", add:
```
A `waits for amendment PR #m` reason is not a block either. The agent proposed
that amendment on an earlier night, and the ticket is picked once it merges.
```

  **3d. New step 3a, before `## 4. Claim`.** Insert:
````
## 3a. Preflight

Read-only: nothing is claimed, labelled or commented yet (#79 spec §2).

```bash
[ "$(git rev-parse --is-shallow-repository)" = true ] && git fetch --unshallow
python3 $T/plan_drift.py --plan <plan> --spec <spec> --ref origin/main
```

- Exit 2: end with `Run failed: plan_drift.py: <its stderr>`.
- `drifted` and `gone` both empty: nothing moved under the plan. Continue to
  step 4. Do not run the suite.
- Otherwise run the full suite on a clean `origin/main` first:

  ```bash
  git worktree add --detach $S/main origin/main
  (cd $S/main && <the pytest command from step 7>; echo "exit=$?")
  git worktree remove --force $S/main
  ```

  A red suite ends the run with `Run failed: main is red at <sha>`. Claim
  nothing, label nothing, propose nothing: that is not a plan problem. Keep
  the suite's counts and any budget the plan quotes, to compare with the
  plan's expected figures.
- Then read each listed commit (`git show <sha> -- <paths>`) and each `gone`
  entry against the plan's tasks and the spec. Decide whether the plan can
  still be built as written. It can: continue to step 4. It cannot: classify
  the gap and go to step 6a or to the not-amendable path of step 6, without
  having claimed anything. No branch exists yet, so there is no draft PR.

The list only narrows what you read. A commit on a named file that does not
contradict the plan is not a finding.
````

  **3e. Step 4, the branch.** Replace
```
`git merge-base --is-ancestor origin/main HEAD`. If it doesn't, merge `origin/main`
in before starting.
```
  with
```
`git merge-base --is-ancestor origin/main HEAD`. If it doesn't, merge `origin/main`
in before starting.

When `resume` is set, the branch is `resume.branch`: fetch it, check it out and
merge `origin/main` in. If that conflicts in the plan file on `- [ ]` / `- [x]`
lines only, take `origin/main`'s plan and re-tick every task that has a commit
on the branch with a `Task: <k>` trailer. Any other conflict is not yours to
resolve: stop as *Blocked* (step 6, not amendable).
```

  **3f. Step 5, the commit.** Replace
```
  put `(#n)` in the subject. The body names the task's `AC-n`. Add one line
  recording the failing test, e.g.
```
  with
```
  put `(#n)` in the subject. The body names the task's `AC-n`, then a trailer
  line `Task: <k>` (resume reads it), then one line recording the failing test,
  e.g.
```

  **3g. Step 6.** Replace from `When you stop:` through `4. Open no PR. End with the *Blocked* summary.` with
````
When you stop, classify the gap first:

- **Amendable:** the plan or spec's wording or steps conflict with `origin/main`
  or with each other, and one conforming text is clear. Do the steps below that
  apply, then step 6a.
- **Not amendable:** more than one reasonable design, or the fix would change
  an `AC-n`, the ticket's scope or a `CLAUDE.md` rule, or the checks are red
  for a cause outside this branch. Do all the steps below.

1. If a branch exists: commit whatever is sound and push it as it stands, then
   open a **draft** PR for it unless one exists. Title
   `<ticket title> (blocked at Task <k>)`. The body starts `Refs #<n>`, never
   `Closes`, then lists the tasks done, the task stopped at, the checks last
   run, and a link to the ticket comment or the amendment PR.
2. Comment on the ticket. Give the task number, the exact gap (quote the plan or spec
   line), and the decision that would unblock it. End with the attribution
   footer.
3. Not amendable only: replace `agent:in-progress` with `agent:blocked`. The
   maintainer removes `agent:blocked` to release the ticket. For an amendable
   gap that you claimed, remove `agent:in-progress`; the amendment PR is the gate.
4. End with the *Blocked* summary, or the *Amendment proposed* summary for an
   amendable gap.

## 6a. Amend

Only for an amendable gap (#79 spec §3):

1. `list_pull_requests`, state `closed`, head `agent/<n>-amend`. Any result,
   merged or not, means one amendment has already been proposed for this
   ticket: treat the gap as not amendable, say so in the comment, and stop.
2. Branch `agent/<n>-amend` from `origin/main`. Change only the ticket's spec
   and plan, as little as the gap allows, never an acceptance criterion. Check
   `git diff --name-only origin/main` lists nothing else; if it does, discard
   the branch and treat the gap as not amendable.
3. Commit as `Amend spec and plan for #<n>: <gap>`, push, and open a ready PR
   with base `main`. The body gives, in order: the quoted plan or spec line,
   the commit on `main` (sha and PR) it conflicts with, the proposed wording,
   any alternative considered, and "Merging this releases #<n>; the agent
   resumes the next night." End it with the PR attribution lines.
4. Comment the link on the ticket. Apply no label. Never merge it.
````

  **3h. Step 8, resuming.** Before `Look for a PR template first`, insert
```
If this run resumed a draft (`resume` is set), do not open a second PR. Update
that PR instead: the ticket's title, the body below with `Closes #<n>`, and
`draft: false`. If `update_pull_request` cannot mark it ready, close the draft
with a comment linking the new PR and open a ready PR from the same branch.

```

  **3i. Step 10, the summaries.** After the `Blocked:` line add
```
- `Amendment proposed: #<m> for #<n> — <one-line gap>. Merge to release.`
```
  and, in the list under `Then, one short line each where applicable:`, add
  `- the draft PR, when step 6 opened one: \`Draft PR: #<m>\`;`.

- [ ] **Step 4: Run the guard test and the full suite.**
  `uv run --with pytest pytest tests/test_pick_ticket.py -q` — expected: 59 passed (the guard test now includes the new needles). Then the full suite, exit code checked.
- [ ] **Step 5:** Read `SKILL.md` top to bottom once. Every step cited by number (`step 6a`, `step 7`, `step 10`) must exist, and nothing may still say a stopped run "opens no PR". Then commit:

```bash
git add .claude/skills/implement-ticket/SKILL.md tests/test_pick_ticket.py
git commit -m "Ticket agent: check the plan against main, amend it by PR, resume stranded work (#79)" \
  -m "AC-2, AC-3, AC-4, AC-5, AC-6, AC-9, AC-10, AC-11. Task: 3" \
  -m "red: test_the_skill_names_every_step failed: SKILL.md no longer mentions 'plan_drift.py'"
```

### Task 4: Documentation (AC-12)

**Files:** modify `CLAUDE.md`; modify `docs/superpowers/specs/2026-09-25-daily-ticket-agent-design.md`. Documentation-only: say so in the commit body.

- [ ] **Step 1: `CLAUDE.md`, section *The ticket agent*.** In the first paragraph replace "and no open PR for it." with "and no open PR for it other than the agent's own, below." Replace the `agent:blocked` bullet and the closing paragraph (from `- \`agent:blocked\`` to `…nothing in it ships to plugin users.`) with:

```
- `agent:blocked`: the agent stopped on a gap only a human can close (a design
  choice, an acceptance criterion, a CLAUDE.md rule), and its comment on the
  ticket names the task and the gap. Fix the spec or plan, then **remove the
  label** to release the ticket for the next run.
- An **amendment PR** (`agent/<n>-amend`, "Amend spec and plan for #n"): the plan
  or spec no longer fits `main` and one conforming text is clear. It changes
  only that ticket's spec and plan. **Merge it** and the ticket is picked the next
  night; there is no label to clear. It holds the ticket while open. At most one
  per ticket: after that the agent labels `agent:blocked` instead.
- A **draft PR** (`agent/<n>-…`, "Refs #n", "blocked at Task k"): finished tasks
  from a run that stopped part-way. Leave it: the next run resumes on that
  branch and marks the same PR ready.

Before it claims a ticket the agent runs `plan_drift.py`, which lists commits
on `main` since the spec and plan were last touched that change files they
name (`2026-10-09-ticket-agent-resilience-design.md` §2). It narrows what the
agent reads; it does not decide.

The agent never merges and never edits a ticket body. It edits a spec or plan
only on an amendment branch, for a human to merge.
`.claude/` is session configuration for this checkout, not plugin content;
nothing in it ships to plugin users.
```

- [ ] **Step 2: the #39 spec.** Under its `**Plan:**` line add:
  `**Superseded in part by** [\`2026-10-09-ticket-agent-resilience-design.md\`](2026-10-09-ticket-agent-resilience-design.md) (#79): §2 rule 12, §3 markers, §4 *What counts as blocked* and §8 summaries.`
- [ ] **Step 3:** Full suite (exit code checked), `uv run scripts/validate_plugin.py` (exit 0, or 2 if `claude` is not on `PATH`: record *not run*), then commit:

```bash
git add CLAUDE.md docs/superpowers/specs/2026-09-25-daily-ticket-agent-design.md
git commit -m "Document amendment and draft PRs in the ticket agent section (#79)" \
  -m "AC-12. Task: 4. Documentation only, so no failing test first."
```

### Task 5: Replay on #58 (success measure)

Not a commit. Run the check that would have saved the night, and record the result on #79 and in the PR body.

- [ ] **Step 1:** `git fetch --unshallow` if `git rev-parse --is-shallow-repository` is `true`, then:

```bash
python3 .claude/skills/implement-ticket/plan_drift.py \
  --plan docs/superpowers/plans/2026-10-03-library-leads.md \
  --spec docs/superpowers/specs/2026-10-03-library-leads-design.md \
  --ref 31bcaea | python3 -c "
import json, sys
d = json.load(sys.stdin)
hit = [x for x in d['drifted'] if x['sha'].startswith('31bcaea')]
assert hit and 'templates/report.html' in hit[0]['paths'], d
print('replay ok:', hit[0]['subject'], len(hit[0]['paths']), 'named files touched')"
```

  Expected: `replay ok: Confidence that means the claim was checked, not that the area is fragile (#78) …`. If it fails, the path extraction in `plan_drift.py` is wrong, not the replay: fix the script and its tests, do not weaken the assertion.
- [ ] **Step 2:** Open the PR (SKILL.md step 8 form), map every `AC-n` to its commit and test, list the commands run with exit codes, and put the replay line under *Verified locally*. Under *Not verifiable in CI*: the skill's new steps are model procedure; their first real run is the acceptance test, as in #39.
