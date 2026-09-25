"""The ticket agent's readiness check (#39).

Which ticket the nightly agent builds is a rule, not a judgment, so it is
decided by a script and every rule has a test here. The reason strings are
part of the contract: they are what the maintainer reads in the morning.
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
SKILL_DIR = ROOT / ".claude" / "skills" / "implement-ticket"
SCRIPT = SKILL_DIR / "pick_ticket.py"

NOW = "2026-09-26T01:52:00Z"
SPEC = "docs/superpowers/specs/2026-09-25-agent-design.md"
PLAN = "docs/superpowers/plans/2026-09-25-agent.md"
OTHER_SPEC = "docs/superpowers/specs/2026-09-25-other-design.md"
OTHER_PLAN = "docs/superpowers/plans/2026-09-25-other.md"
BODY = f"- **Design (spec):** `{SPEC}`\n- **Implementation plan:** `{PLAN}`\n"


def _git(repo: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "init.defaultBranch=main", *args],
                   cwd=repo, env=env, check=True, capture_output=True)


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("tickets")
    files = {
        SPEC: "# Agent: design\n\n**Requirements:** [#39](https://example.com/issues/39).\n",
        PLAN: "# Agent plan\n\nRequirements AC-1…AC-3 are in GitHub issue #39.\n",
        OTHER_SPEC: "**Requirements:** [#390](https://example.com/issues/390).\n",
        OTHER_PLAN: "Requirements are in GitHub issue #390.\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "specs and plans")
    return root


def issue(number=39, title="A ready ticket", body=BODY, author="tomstagl",
          labels=(), state="OPEN", claimed_at=None) -> dict:
    return {"number": number, "title": title, "body": body, "author": author,
            "labels": list(labels), "state": state, "claimed_at": claimed_at}


def candidates(*issues, prs=(), writers=("tomstagl",)) -> dict:
    return {"repo": "tomstagl/thunderstruck", "writers": list(writers),
            "issues": list(issues), "open_prs": list(prs)}


def run(repo: Path, tmp_path: Path, data, ref="HEAD", now=NOW):
    path = tmp_path / "candidates.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    proc = subprocess.run([sys.executable, str(SCRIPT), str(path), "--ref", ref, "--now", now],
                          cwd=repo, capture_output=True, text=True)
    out = json.loads(proc.stdout) if proc.returncode == 0 else None
    return proc.returncode, out, proc


def reason(repo, tmp_path, *issues, **kw) -> str:
    code, out, proc = run(repo, tmp_path, candidates(*issues, **kw))
    assert code == 0, proc.stderr
    assert out["picked"] is None, out
    [skipped] = out["skipped"]
    return skipped["reason"]


# -- the happy path -------------------------------------------------------------

def test_a_ready_ticket_is_picked(repo, tmp_path):
    code, out, proc = run(repo, tmp_path, candidates(issue()))
    assert code == 0, proc.stderr
    assert out["picked"] == {"number": 39, "title": "A ready ticket", "spec": SPEC, "plan": PLAN}
    assert out["skipped"] == [] and out["ignored_drafts"] == []


def test_the_lowest_number_wins_and_the_rest_are_not_skipped(repo, tmp_path):
    body = BODY + "Also relates to #39.\n"
    other = issue(number=41, body=body)
    _, out, _ = run(repo, tmp_path, candidates(other, issue()))
    assert out["picked"]["number"] == 39
    assert out["skipped"] == []


def test_output_is_byte_stable(repo, tmp_path):
    data = candidates(issue(number=12, title="DRAFT: x"), issue(number=5, author="x"), issue())
    first = run(repo, tmp_path, data)[2].stdout
    assert first == run(repo, tmp_path, data)[2].stdout
    assert [s["number"] for s in json.loads(first)["skipped"]] == [5]


# -- rule 1: open ----------------------------------------------------------------

def test_a_closed_ticket_is_not_reported_at_all(repo, tmp_path):
    _, out, _ = run(repo, tmp_path, candidates(issue(state="CLOSED")))
    assert out == {"picked": None, "skipped": [], "ignored_drafts": []}


# -- rule 2: draft anywhere in the title ------------------------------------------

@pytest.mark.parametrize("title", ["DRAFT: x", "Draft: x", "DRAFT - x", "draft - x",
                                   "Fix the thing (draft)", "A DrAfT ticket"])
def test_draft_anywhere_in_the_title_is_ignored(repo, tmp_path, title):
    _, out, _ = run(repo, tmp_path, candidates(issue(title=title)))
    assert out == {"picked": None, "skipped": [], "ignored_drafts": [39]}


# -- rule 3: write access -----------------------------------------------------------

def test_an_author_without_write_access_is_skipped(repo, tmp_path):
    assert reason(repo, tmp_path, issue(author="stranger")) == "author stranger has no write access"


def test_logins_compare_case_insensitively(repo, tmp_path):
    _, out, _ = run(repo, tmp_path, candidates(issue(author="TomStagl")))
    assert out["picked"]["number"] == 39


# -- rules 4 and 5: exactly one spec and one plan path -------------------------------

def test_no_spec_path(repo, tmp_path):
    assert reason(repo, tmp_path, issue(body=f"`{PLAN}`")) == "no spec path in ticket"


def test_a_placeholder_spec_path_is_no_spec_path(repo, tmp_path):
    body = f"`docs/superpowers/specs/YYYY-MM-DD-agent-design.md`\n`{PLAN}`"
    assert reason(repo, tmp_path, issue(body=body)) == "no spec path in ticket"


def test_more_than_one_spec_path(repo, tmp_path):
    body = BODY + f"`{OTHER_SPEC}`"
    assert reason(repo, tmp_path, issue(body=body)) == "more than one spec path in ticket"


def test_the_same_path_twice_is_one_path(repo, tmp_path):
    _, out, _ = run(repo, tmp_path, candidates(issue(body=BODY + BODY)))
    assert out["picked"]["number"] == 39


def test_no_plan_path(repo, tmp_path):
    assert reason(repo, tmp_path, issue(body=f"`{SPEC}`")) == "no plan path in ticket"


def test_more_than_one_plan_path(repo, tmp_path):
    body = BODY + f"`{OTHER_PLAN}`"
    assert reason(repo, tmp_path, issue(body=body)) == "more than one plan path in ticket"


# -- rules 6 and 7: on the ref ---------------------------------------------------------

def test_spec_not_on_ref(repo, tmp_path):
    missing = "docs/superpowers/specs/2026-09-24-lead-precision-design.md"
    body = f"`{missing}` on branch `claude/x`\n`{PLAN}`"
    assert reason(repo, tmp_path, issue(body=body)) == f"spec not on HEAD: {missing}"


def test_plan_not_on_ref(repo, tmp_path):
    missing = "docs/superpowers/plans/2026-09-24-lead-precision.md"
    body = f"`{SPEC}`\n`{missing}`"
    assert reason(repo, tmp_path, issue(body=body)) == f"plan not on HEAD: {missing}"


# -- rules 8 and 9: the spec and plan name the ticket back ---------------------------

def test_spec_must_reference_the_ticket(repo, tmp_path):
    body = f"`{OTHER_SPEC}`\n`{PLAN}`"
    assert reason(repo, tmp_path, issue(body=body)) == "spec does not reference #39"


def test_plan_must_reference_the_ticket(repo, tmp_path):
    body = f"`{SPEC}`\n`{OTHER_PLAN}`"
    assert reason(repo, tmp_path, issue(body=body)) == "plan does not reference #39"


def test_a_longer_number_is_not_a_reference(repo, tmp_path):
    # The other spec and plan say #390; ticket #39 must not match them.
    body = f"`{OTHER_SPEC}`\n`{OTHER_PLAN}`"
    assert reason(repo, tmp_path, issue(body=body)) == "spec does not reference #39"


# -- rules 10 and 11: markers -----------------------------------------------------------

def test_a_claimed_ticket_is_skipped(repo, tmp_path):
    t = issue(labels=["agent:in-progress"], claimed_at="2026-09-25T03:00:00Z")
    assert reason(repo, tmp_path, t) == "already claimed"


def test_a_claim_without_timestamp_is_still_a_claim(repo, tmp_path):
    assert reason(repo, tmp_path, issue(labels=["agent:in-progress"])) == "already claimed"


def test_a_claim_older_than_a_day_is_stale(repo, tmp_path):
    t = issue(labels=["agent:in-progress"], claimed_at="2026-09-25T00:52:00Z")
    assert reason(repo, tmp_path, t) == "stale claim since 2026-09-25T00:52:00Z"


def test_a_blocked_ticket_is_skipped(repo, tmp_path):
    t = issue(labels=["agent:blocked"])
    assert reason(repo, tmp_path, t) == "blocked, see ticket comments"


# -- rule 12: no open PR ---------------------------------------------------------------

def test_an_open_pr_that_references_the_ticket(repo, tmp_path):
    pr = {"number": 40, "title": "Build it", "body": "Closes #39.", "head": "claude/x"}
    assert reason(repo, tmp_path, issue(), prs=[pr]) == "open PR #40 references it"


def test_an_open_pr_for_a_longer_number_does_not_count(repo, tmp_path):
    pr = {"number": 40, "title": "Fix #390", "body": "", "head": "claude/x"}
    _, out, _ = run(repo, tmp_path, candidates(issue(), prs=[pr]))
    assert out["picked"]["number"] == 39


# -- the first failing rule is the reason ------------------------------------------------

def test_the_first_failing_rule_is_the_reason(repo, tmp_path):
    t = issue(author="stranger", body="", labels=["agent:blocked"])
    assert reason(repo, tmp_path, t) == "author stranger has no write access"


# -- input and exit codes ------------------------------------------------------------------

@pytest.mark.parametrize("data", [
    "not json",
    "[]",
    json.dumps({"writers": [], "open_prs": []}),
    json.dumps({"issues": [], "open_prs": []}),
    json.dumps({"issues": [], "writers": []}),
    json.dumps({"issues": [{"title": "no number"}], "writers": [], "open_prs": []}),
])
def test_malformed_input_exits_2(repo, tmp_path, data):
    code, _, proc = run(repo, tmp_path, data)
    assert code == 2
    assert proc.stdout == ""


def test_an_unknown_ref_exits_2(repo, tmp_path):
    code, _, _ = run(repo, tmp_path, candidates(issue()), ref="no-such-ref")
    assert code == 2


def test_nothing_ready_exits_0(repo, tmp_path):
    code, out, _ = run(repo, tmp_path, candidates())
    assert code == 0 and out == {"picked": None, "skipped": [], "ignored_drafts": []}


def test_the_script_is_stdlib_only():
    tree = ast.parse(SCRIPT.read_text())
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    bad = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
           if a.name.split(".")[0] not in stdlib]
    bad += [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
            and n.module and n.module.split(".")[0] not in stdlib]
    assert not bad, f"pick_ticket.py imports non-stdlib modules: {bad}"


def test_a_claim_time_without_zone_is_utc(repo, tmp_path):
    t = issue(labels=["agent:in-progress"], claimed_at="2026-09-25T00:52:00")
    assert reason(repo, tmp_path, t) == "stale claim since 2026-09-25T00:52:00"


# -- the skill that drives the agent ------------------------------------------------------

def test_the_skill_names_every_step():
    """Guards against the procedure quietly losing a step in a later edit."""
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert text.startswith("---\nname: implement-ticket\n")
    for needle in ("pick_ticket.py", "agent:in-progress", "agent:blocked", "Closes #",
                   "THUNDERSTRUCK_REQUIRE_RENDERER=1", "gen_catalog_docs.py --check",
                   "gen_sample_report.py --check", "claude plugin validate . --strict",
                   "subscribe_pr_activity", "red:", "Nothing ready", "Blocked:", "PR opened:"):
        assert needle in text, f"SKILL.md no longer mentions {needle!r}"
