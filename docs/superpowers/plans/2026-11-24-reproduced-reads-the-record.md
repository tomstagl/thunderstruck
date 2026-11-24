# Reproduced Reads the Record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `finding_ticket.py --status Reproduced` is accepted when the finding has a current recorded failing test, refused with its own reason for every other state of the record, and a recorded reproduction is shown in the ticket whatever status is asked.

**Architecture:** `recorded_reproduction` reads the `reproduction` object `report.py` attaches to a finding (#103) and accepts only `fails_as_predicted` with state `current`. `reproduction_refusal` names the reason for every other state. `main` adds one `is_file()` check, only for `Reproduced`, to tell "recorded, report not rebuilt" from "nothing recorded". `render` calls `report.render_reproduction` for the header and the Reproduce section.

**Tech Stack:** Python 3.11+ (stdlib), `uv`, pytest.

**Ticket:** #143, part of #104. **Spec:** `docs/superpowers/specs/2026-11-24-reproduced-reads-the-record-design.md` (§n below refers to it). The acceptance criteria AC-1…AC-7 are in the ticket; each task names the ones it satisfies. A design change goes in the spec first.

**Branch:** named by whoever builds it; the agent uses `agent/143-reproduced-reads-the-record`. One commit per task, staging explicit paths only (never `git add -A`, never a bare `tests/`). Do not bump the version (maintainer's call, 2026-11-22, as for #103): the change is listed under `## Unreleased` in `CHANGELOG.md`.

The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
THUNDERSTRUCK_REQUIRE_RENDERER=1 uv run --with pytest --with pyyaml --with lizard --with packaging --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

A task's tests are in one file, `tests/test_finding_ticket.py`; run it with:

```bash
THUNDERSTRUCK_REQUIRE_RENDERER=1 uv run --with pytest --with pyyaml --with lizard --with packaging --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/test_finding_ticket.py -q
```

Where a step gives an old text and a new text, the old text occurs exactly once in the file; apply it with an editor and check that it did, never blindly. Tests appended to a file are separated from its last line by two blank lines.

## Global Constraints

- **The report's word is the source.** A state is read from `finding["reproduction"]`; nothing here opens a record file to learn one (§3.1). `record_on_disk` is one `is_file()`, only when `--status Reproduced` was asked, only on a key that passed `KEY_SHAPE` (§3.3).
- **Fail closed.** Only `status == "fails_as_predicted"` with `state == "current"` is a recorded reproduction. Every other value, known or not, is refused (§3.2).
- **A refusal writes nothing** and leaves an earlier ticket alone. Every message begins `status Reproduced refused for finding <key>: ` and ends `No ticket was written.` (§3.2).
- **`report.render_reproduction` is called, not copied** (§3.4). No recorded value reaches the ticket except through it or through the scrubbed finding (§4).
- **`Hypothesis` stays the default, and `Fix proposed` and `Fix reviewed` stay the requester's word** (§3.5, ticket).
- **No schema moves:** not the report's, the finding's, the record's or the ticket's, and `VALIDATION_RULES` stays (§5).
- **Existing tests this plan edits are exactly four:** `test_nothing_records_a_reproduction_yet` (replaced by two), `test_reproduced_is_refused_and_writes_nothing` (its reason), and one assertion each in `test_the_skill_states_the_contract_the_script_validates` and `test_the_readme_and_claude_md_describe_the_command_and_say_what_a_ticket_is`. Each is replaced by an assertion at least as strict. Never skip, disable or weaken a test.
- **`examples/` is not regenerated.** Its fixture has no record. `gen_sample_report.py --check` must exit 0 on every task from Task 1 on.
- The two guidance documents under `docs/` are never edited.
- A missing prerequisite stops the run: replace `agent:in-progress` with `agent:blocked`, comment naming the task and what is missing, open no PR. Never skip a task and continue.
- Public repository: no organisation-specific names, hosts or credentials in any file.

## Review Focus

For a reviewer: whether any path accepts `Reproduced` on something other than a current failing record; whether any value from the report or the record reaches a message or the ticket without `_one_line`, `mdtext` or the scrubber; whether `record_on_disk` can read a file or follow a key out of `reproductions/`; and whether a replaced test lost a check.

## Task 0: Prerequisites and baseline

**Satisfies:** none directly; every later task assumes it.

- [ ] **Step 1: Check #103 and #108 are on `main`, and that the text this plan edits is as it was written against.** A missing prerequisite sets `B`; a moved anchor sets `A`. Either stops the run.

```bash
git fetch -q origin
B=0; A=0
chk() { git show "origin/main:$1" 2>/dev/null | grep -q -F -- "$2" && echo "ok      $3" || { echo "MISSING $3"; B=1; }; }
chk scripts/reproduction.py 'def records_dir' "#103: reproduction.records_dir"
chk scripts/reproduction.py 'def summaries' "#103: reproduction.summaries"
chk scripts/reproduction.py 'def sentence_parts' "#103: reproduction.sentence_parts"
chk scripts/report.py 'def render_reproduction' "#103: report.render_reproduction"
chk scripts/report.py 'f["reproduction"] = {**summary' "#103: report attaches the reproduction object"
chk skills/thunderstruck-verify/SKILL.md 'reproduction.py" record' "#103: the verify skill records"
chk tests/test_report_reproduction.py 'def reported' "#103: the reported fixture"
chk tests/test_report_reproduction.py 'def _report_md' "#103: the _report_md helper"
chk scripts/finding_ticket.py 'def recorded_reproduction' "#108: finding_ticket.recorded_reproduction"
for name in record_on_disk reproduction_refusal; do
  if git show origin/main:scripts/finding_ticket.py | grep -q -- "def $name"; then echo "EXISTS  $name"; B=1; else echo "ok      $name is free"; fi
done
python3 - <<'EOF' || A=1
import subprocess, sys
ANCHORS = [
    ("scripts/finding_ticket.py", "from validate import CODE_REF  # noqa: E402"),
    ("scripts/finding_ticket.py", "def recorded_reproduction(finding: dict) -> dict | None:"),
    ("scripts/finding_ticket.py", "def require_status(status: str, finding: dict) -> None:"),
    ("scripts/finding_ticket.py", "        require_status(args.status, finding)"),
    ("scripts/finding_ticket.py", "    reason = links_reason(rep)"),
    ("scripts/finding_ticket.py", '         f"- **Status** — {status}",'),
    ("scripts/finding_ticket.py", '          "No reproduction is recorded for this finding.", ""]'),
    ("tests/test_finding_ticket.py", "def test_nothing_records_a_reproduction_yet(tmp_path):"),
    ("tests/test_finding_ticket.py", '    assert code == 2 and "Reproduced refused" in err and "#103" in err and out == ""'),
    ("tests/test_finding_ticket.py", '    assert "`Reproduced` is refused" in text'),
    ("tests/test_finding_ticket.py", '    assert "`Reproduced` is refused until a reproduction is recorded" in readme'),
    ("README.md", "`Reproduced` is refused\n  until a reproduction is recorded (#103)."),
    ("CLAUDE.md", "- **Only `Reproduced` is gated.** `recorded_reproduction` returns `None` until #103"),
    ("skills/thunderstruck-ticket/SKILL.md", "`Reproduced` is refused\nuntil a reproduction is recorded: relay the refusal, never work around it."),
    ("CHANGELOG.md", "namespaced or not.\n\n### Fixed\n\n- The skeptic's model is `claude-haiku-5-5`"),
]
bad = 0
for path, text in ANCHORS:
    n = subprocess.run(["git", "show", f"origin/main:{path}"], capture_output=True, text=True).stdout.count(text)
    print(("ok      " if n == 1 else f"MOVED   ({n}x) ") + f"{path}: {text.splitlines()[0][:70]}")
    bad |= n != 1
sys.exit(bad)
EOF
echo "B=$B A=$A"
```

Expected: every line `ok`, then `B=0 A=0`. A prerequisite missing (`B=1`) is a stop. A moved anchor (`A=1`) means `main` changed these files since this plan was written: run `.claude/skills/implement-ticket/plan_drift.py`, read the commits it lists, and amend the plan if one conforming text is clear, otherwise stop as the skill says.

- [ ] **Step 2: Baseline.** On a branch from `origin/main`, run `tests/test_finding_ticket.py` (command above) and `uv run scripts/gen_sample_report.py --check`. Note that both pass. Run `git log --oneline -1 -- scripts/finding_ticket.py` and keep the SHA for the PR.

## Task 1: The rule

**Satisfies:** AC-1, AC-2, AC-5. **Files:** `scripts/finding_ticket.py`, `tests/test_finding_ticket.py`.

- [ ] **Step 1: Failing tests.** In `tests/test_finding_ticket.py`:

(a) Replace `test_nothing_records_a_reproduction_yet`. Old:

```python
def test_nothing_records_a_reproduction_yet(tmp_path):
    """#103 will record one. Until then this is None and Reproduced is refused; the
    follow-up that reads #103's record changes this test with ft.recorded_reproduction."""
    repo = make_repo(tmp_path)
    f = ft.find_finding(make_report(repo), KEY)
    assert ft.recorded_reproduction(f) is None
    with pytest.raises(c.ThunderstruckError) as err:
        ft.require_status("Reproduced", f)
    message = str(err.value)
    assert KEY in message and "no failing reproduction is recorded" in message
    assert "#103" in message and "No ticket was written" in message
    for ok in ("Hypothesis", "Fix proposed", "Fix reviewed"):
        ft.require_status(ok, f)
```

New: the helper `reproduction_summary`, the parametrized rule test (§3.2, §5), and the no-key test, which keeps every assertion the old test made and changes its reason:

```python
def reproduction_summary(**over):
    """The `reproduction` object report.py attaches to a finding (#103)."""
    rep = {"status": "fails_as_predicted", "state": "current", "test_path": "tests/test_releases.py",
           "command": "pytest tests/test_releases.py -q", "recorded_head": "a" * 40,
           "stale_because": []}
    rep.update(over)
    return rep


@pytest.mark.parametrize("rep, counts", [
    (reproduction_summary(), True),
    (reproduction_summary(state="stale", stale_because=["the test file changed"]), False),
    (reproduction_summary(status="passes"), False),
    (reproduction_summary(status="blocked"), False),
    (reproduction_summary(status=None, state="unreadable"), False),
    (reproduction_summary(state="current-ish"), False),
    ("fails_as_predicted", False), (None, False), ([], False)])
def test_only_a_current_failing_test_is_a_recorded_reproduction(tmp_path, rep, counts):
    repo = make_repo(tmp_path)
    f = ft.find_finding(make_report(repo, [make_finding(repo, reproduction=rep)]), KEY)
    assert (ft.recorded_reproduction(f) is not None) is counts


def test_a_finding_with_no_reproduction_key_has_none_recorded(tmp_path):
    """A report built before #103 has no `reproduction` key on any finding (AC-5)."""
    repo = make_repo(tmp_path)
    f = ft.find_finding(make_report(repo), KEY)
    assert "reproduction" not in f and ft.recorded_reproduction(f) is None
    with pytest.raises(c.ThunderstruckError) as err:
        ft.require_status("Reproduced", f)
    message = str(err.value)
    assert KEY in message and "no reproduction is recorded for it" in message
    assert "No ticket was written" in message
    for ok in ("Hypothesis", "Fix proposed", "Fix reviewed"):
        ft.require_status(ok, f)
```

(b) In `test_reproduced_is_refused_and_writes_nothing`, the assertion that named #103 names the new reason:

```python
    assert code == 2 and "Reproduced refused" in err and "#103" in err and out == ""
```

becomes

```python
    assert code == 2 and "Reproduced refused" in err and "no reproduction is recorded for it" in err and out == ""
```

(c) Append at the end of the file:

```python
# --- #143: Reproduced reads the record --------------------------------------

REFUSALS = [
    ("none recorded", None, False, "no reproduction is recorded for it"),
    ("not in the report yet", None, True, "does not show it yet"),
    ("passed", reproduction_summary(status="passes"), False, "the recorded reproduction passed"),
    ("blocked", reproduction_summary(status="blocked"), False, "the recorded reproduction was blocked"),
    ("stale", reproduction_summary(state="stale",
                                   stale_because=["the test file changed", "the finding changed"]),
     False, "stale: the test file changed and the finding changed"),
    ("unreadable", reproduction_summary(status=None, state="unreadable"), False, "is unreadable"),
    ("unrecognised", reproduction_summary(status="maybe"), False, "unrecognised result ('maybe')"),
]


def test_reproduced_is_accepted_on_a_current_failing_reproduction(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo, [make_finding(repo, reproduction=reproduction_summary())])
    code, _, err = run_main(capsys, repo, "--key", KEY, "--status", "Reproduced")
    assert code == 0, err
    assert "- **Status** — Reproduced" in section(ticket_path(repo).read_text(), "Header")


@pytest.mark.parametrize("name, rep, on_disk, reason", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_reproduced_is_refused_with_the_reason_for_each_state_of_the_record(
        tmp_path, capsys, name, rep, on_disk, reason):
    repo = make_repo(tmp_path)
    make_report(repo, [make_finding(repo, **({} if rep is None else {"reproduction": rep}))])
    if on_disk:
        record = repo / ".thunderstruck" / "reproductions" / f"{KEY}.json"
        record.parent.mkdir(parents=True)
        record.write_text("{}")
    code, out, err = run_main(capsys, repo, "--key", KEY, "--status", "Reproduced")
    assert code == 2 and out == "" and f"status Reproduced refused for finding {KEY}" in err
    assert reason in err and "No ticket was written." in err
    assert not (repo / ".thunderstruck" / "tickets").exists()


def test_a_record_file_with_an_unsafe_name_is_never_looked_up(tmp_path):
    """Only a 12-hex key names a file: the on-disk check cannot be pointed elsewhere."""
    repo = make_repo(tmp_path)
    (repo / ".thunderstruck" / "reproductions").mkdir(parents=True)
    (repo / ".thunderstruck" / "reproductions" / "..%2fx.json").write_text("{}")
    assert ft.record_on_disk(repo, "../x") is False and ft.record_on_disk(repo, "") is False
    assert ft.record_on_disk(repo, KEY) is False
```

- [ ] **Step 2: Run the file and see 12 fail.** They are `test_only_a_current_failing_test_is_a_recorded_reproduction` (the current case), `test_a_finding_with_no_reproduction_key_has_none_recorded`, `test_reproduced_is_accepted_on_a_current_failing_reproduction`, all seven of `test_reproduced_is_refused_with_the_reason_for_each_state_of_the_record`, `test_a_record_file_with_an_unsafe_name_is_never_looked_up` (no `record_on_disk` yet) and `test_reproduced_is_refused_and_writes_nothing`. Each fails for the reason it names; a failure of setup (an import, a missing helper) is a stop.

- [ ] **Step 3: The code.** In `scripts/finding_ticket.py`, three edits.

The import:

Old text (occurs exactly once):

```python
import report  # noqa: E402
from validate import CODE_REF  # noqa: E402
```

New text:

```python
import report  # noqa: E402
import reproduction  # noqa: E402
from validate import CODE_REF  # noqa: E402
```

The rule, replacing `recorded_reproduction` and `require_status`:

Old text (occurs exactly once):

```python
def recorded_reproduction(finding: dict) -> dict | None:
    """The finding's recorded failing reproduction, or None.

    Nothing records one yet: `/thunderstruck-verify` leaves no data. #103 will, and
    the follow-up that lets `Reproduced` read that record changes this function.
    """
    return None


def require_status(status: str, finding: dict) -> None:
    """`Reproduced` is the one claim the plugin can check: it needs a recorded reproduction."""
    if status == "Reproduced" and recorded_reproduction(finding) is None:
        raise stop(f"status Reproduced refused for finding {finding.get('key')}: no failing "
                   "reproduction is recorded for it. A reproduction is a failing test that a "
                   "verification run left behind and recorded; thunderstruck does not record one "
                   "yet (issue #103 in the thunderstruck repository). Ask for Hypothesis, or "
                   "record a reproduction first. No ticket was written.")
```

New text:

```python
def recorded_reproduction(finding: dict) -> dict | None:
    """The finding's recorded failing reproduction, or None.

    That is the `reproduction` object `report.py` attaches from `.thunderstruck/reproductions/`
    (#103), and only a failing test whose record is still current: the test file and the
    finding are as they were when it was recorded. The state is the report's, read as it is,
    like the check status; it is not derived again here.
    """
    rep = finding.get("reproduction")
    if (isinstance(rep, dict) and rep.get("status") == "fails_as_predicted"
            and rep.get("state") == "current"):
        return rep
    return None


def record_on_disk(repo: Path, key: str) -> bool:
    """A record file exists for this key, whether or not the report shows it yet."""
    return KEY_SHAPE.match(key) is not None and (reproduction.records_dir(repo) / f"{key}.json").is_file()


REBUILD = "Rebuild the report (`report.py`) and ask again."


def reproduction_refusal(finding: dict, on_disk: bool = False) -> str | None:
    """Why `Reproduced` cannot be said for this finding, or None when it can."""
    if recorded_reproduction(finding) is not None:
        return None
    rep = finding.get("reproduction")
    if not isinstance(rep, dict):
        if on_disk:
            return f"a reproduction is recorded for it, but report.json does not show it yet. {REBUILD}"
        return ("no reproduction is recorded for it. Run `/thunderstruck-verify`, record the outcome "
                "of the test run, then rebuild the report and ask again. Or ask for Hypothesis.")
    status, state = rep.get("status"), rep.get("state")
    if state == "unreadable":
        return ("the reproduction recorded for it is unreadable. Record it again with "
                f"`/thunderstruck-verify`. {REBUILD}")
    if status == "passes":
        return ("the recorded reproduction passed: the hypothesis did not hold as tested, and a "
                "test that passes does not reproduce a failure.")
    if status == "blocked":
        return ("the recorded reproduction was blocked: no test could be made to run. Ask for "
                "Hypothesis, or get a test to fail and record it.")
    if status == "fails_as_predicted" and state == "stale":
        because = rep.get("stale_because")
        what = " and ".join(_one_line(b, 60) for b in because[:3]) if isinstance(because, list) and because \
            else "it no longer matches"
        return (f"the recorded failing test is stale: {what}. Run it again with "
                f"`/thunderstruck-verify`, record the outcome. {REBUILD}")
    return (f"the recorded reproduction has an unrecognised result ({_one_line(status, 30)!r}). "
            f"Record it again with `/thunderstruck-verify`. {REBUILD}")


def require_status(status: str, finding: dict, on_disk: bool = False) -> None:
    """`Reproduced` is the one claim the plugin can check: it needs a current failing reproduction."""
    if status != "Reproduced":
        return
    why = reproduction_refusal(finding, on_disk)
    if why:
        raise stop(f"status Reproduced refused for finding {finding.get('key')}: {why} "
                   "No ticket was written.")
```

The call in `main`:

Old text (occurs exactly once):

```python
        require_status(args.status, finding)
```

New text:

```python
        require_status(args.status, finding,
                       record_on_disk(repo, finding["key"]) if args.status == "Reproduced" else False)
```

- [ ] **Step 4: Run the file: 240 passed** (the count drifts with `main`; the rule is zero failures). Run `uv run scripts/gen_sample_report.py --check` and see exit 0.

- [ ] **Step 5: Commit.**

```bash
git add scripts/finding_ticket.py tests/test_finding_ticket.py
git commit -m "Ticket: Reproduced reads the recorded reproduction (#143)" \
  -m "AC-1, AC-2, AC-5" -m "Task: 1" -m "red: 12 failed in tests/test_finding_ticket.py, among them test_reproduced_is_accepted_on_a_current_failing_reproduction: status Reproduced refused for finding a1b2c3d4e5f6: no failing reproduction is recorded for it"
```

## Task 2: The ticket shows the record

**Satisfies:** AC-1, AC-3, AC-4, AC-6. **Files:** `scripts/finding_ticket.py`, `tests/test_finding_ticket.py`.

- [ ] **Step 1: Failing tests.** Append at the end of `tests/test_finding_ticket.py`. The last three use #103's `reported` fixture, so the object under test is the one `report.py` really attaches:

```python
def test_a_recorded_reproduction_is_shown_in_the_header_and_the_reproduce_section(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo, [make_finding(repo, reproduction=reproduction_summary())])
    code, _, err = run_main(capsys, repo, "--key", KEY, "--status", "Reproduced")
    assert code == 0, err
    text = ticket_path(repo).read_text()
    header = _plain(section(text, "Header"))
    assert "- **Reproduction** — Reproduced by a failing test" in header and "tests/test_releases.py" in header
    reproduce = section(text, "Reproduce")
    assert "**Verify** — Stub a 503 and count the requests" in reproduce
    assert ("Recorded with the command `pytest tests/test_releases.py -q` at commit `"
            + "a" * 12 + "`") in reproduce
    assert "No reproduction is recorded" not in text


@pytest.mark.parametrize("args, rep, lead", [
    ((), reproduction_summary(), "Reproduced by a failing test"),
    (("--status", "Fix proposed"), reproduction_summary(), "Reproduced by a failing test"),
    ((), reproduction_summary(state="stale", stale_because=["the test file changed"]),
     "Stale: a failing test was recorded"),
    ((), reproduction_summary(status="passes"), "A recorded reproduction passed"),
    ((), reproduction_summary(status="blocked"), "A reproduction was attempted and blocked"),
    ((), reproduction_summary(status=None, state="unreadable"), "A recorded reproduction is unreadable")])
def test_a_recorded_reproduction_is_shown_whatever_status_is_asked(tmp_path, capsys, args, rep, lead):
    repo = make_repo(tmp_path)
    make_report(repo, [make_finding(repo, reproduction=rep)])
    code, _, err = run_main(capsys, repo, "--key", KEY, *args)
    assert code == 0, err
    text = ticket_path(repo).read_text()
    assert lead in _plain(section(text, "Header")) and lead in _plain(section(text, "Reproduce"))
    assert "No reproduction is recorded" not in text
    if not args:
        assert "- **Status** — Hypothesis" in section(text, "Header")


def test_the_recorded_command_is_inert_and_free_of_machine_values(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ft, "machine_values", lambda: MACHINE)
    repo = make_repo(tmp_path)
    command = "cd /home/alice/work && pytest -q `id` [x](http://evil.example) <b>hi</b> #12 > devbox-17.log"
    make_report(repo, [make_finding(repo, reproduction=reproduction_summary(command=command))])
    code, _, err = run_main(capsys, repo, "--key", KEY)
    assert code == 0, err
    reproduce = section(ticket_path(repo).read_text(), "Reproduce")
    for value in ("/home/alice", "alice", "devbox-17"):
        assert value not in reproduce, value
    safe = "cd <home>/work && pytest -q `id` [x](http://evil.example) <b>hi</b> #12 > <host>.log"
    assert mdtext.code(safe) in reproduce                   # the project's own inert primitive


def test_the_ticket_with_a_recorded_reproduction_is_byte_identical_twice(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo, [make_finding(repo, reproduction=reproduction_summary())])
    assert run_main(capsys, repo, "--key", KEY, "--status", "Reproduced")[0] == 0
    first = ticket_path(repo).read_bytes()
    assert run_main(capsys, repo, "--key", KEY, "--status", "Reproduced")[0] == 0
    assert ticket_path(repo).read_bytes() == first


# The real chain, with nothing hand-built: reproduction.py records, report.py attaches the
# record to the finding, finding_ticket.py reads it. `reported` is #103's fixture: a scanned
# copy of the fixture repository with one validated finding, reported once.
import reproduction  # noqa: E402
from test_report_reproduction import _report_md, reported  # noqa: E402,F401


def test_a_reproduction_recorded_and_reported_for_real_makes_a_reproduced_ticket(reported, capsys):
    repo, key = reported
    reproduction.record(repo, key, "fails_as_predicted", "tests/test_repro.py",
                        "pytest tests/test_repro.py -q")
    _report_md(repo)                       # the report is rebuilt after recording, as the verify skill says
    code, _, err = run_main(capsys, repo, "--key", key, "--status", "Reproduced")
    assert code == 0, err
    text = ticket_path(repo, key).read_text()
    assert "- **Status** — Reproduced" in section(text, "Header")
    assert "Reproduced by a failing test" in _plain(section(text, "Reproduce"))
    assert "Recorded with the command `pytest tests/test_repro.py -q`" in section(text, "Reproduce")


def test_a_test_edited_after_it_was_recorded_is_stale_and_refused(reported, capsys):
    repo, key = reported
    reproduction.record(repo, key, "fails_as_predicted", "tests/test_repro.py",
                        "pytest tests/test_repro.py -q")
    (repo / "tests" / "test_repro.py").write_text("def test_repro():\n    assert True\n")
    _report_md(repo)
    code, out, err = run_main(capsys, repo, "--key", key, "--status", "Reproduced")
    assert code == 2 and out == "" and "stale: the test file changed" in err
    assert not (repo / ".thunderstruck" / "tickets").exists()


def test_a_record_the_report_was_not_rebuilt_for_says_to_rebuild_it(reported, capsys):
    repo, key = reported
    reproduction.record(repo, key, "fails_as_predicted", "tests/test_repro.py",
                        "pytest tests/test_repro.py -q")
    code, _, err = run_main(capsys, repo, "--key", key, "--status", "Reproduced")
    assert code == 2 and "does not show it yet" in err and "Rebuild the report" in err
```

- [ ] **Step 2: Run the file and see 9 fail:** `test_a_recorded_reproduction_is_shown_in_the_header_and_the_reproduce_section`, all six of `test_a_recorded_reproduction_is_shown_whatever_status_is_asked`, `test_the_recorded_command_is_inert_and_free_of_machine_values` and `test_a_reproduction_recorded_and_reported_for_real_makes_a_reproduced_ticket`. The byte-identical test and the stale and not-rebuilt tests already pass, because Task 1 built what they pin; they stay, because they are what keeps it built.

- [ ] **Step 3: The code.** In `render`, three edits.

Old text (occurs exactly once):

```python
    reason = links_reason(rep)
    L = [f"# {md.text(title(f), heading=True)}", "", "## Header", "",
```

New text:

```python
    reason = links_reason(rep)
    repro = report.render_reproduction(f)
    L = [f"# {md.text(title(f), heading=True)}", "", "## Header", "",
```

Old text (occurs exactly once):

```python
         f"- **Status** — {status}",
         f"- **Key** — {md.code(f.get('key'))}",
```

New text:

```python
         f"- **Status** — {status}",
         *([f"- {repro[0]}"] if repro else []),
         f"- **Key** — {md.code(f.get('key'))}",
```

Old text (occurs exactly once):

```python
    L += ["## Reproduce", "", f"**Verify** — {md.text(f.get('how_to_verify'))}", "",
          "No reproduction is recorded for this finding.", ""]
```

New text:

```python
    L += ["## Reproduce", "", f"**Verify** — {md.text(f.get('how_to_verify'))}", "",
          *(repro or ["No reproduction is recorded for this finding.", ""])]
```

- [ ] **Step 4: Run the file: 252 passed.** Run `uv run scripts/gen_sample_report.py --check` and see exit 0: the sample shows the no-record sentence, which did not change.

- [ ] **Step 5: Commit.**

```bash
git add scripts/finding_ticket.py tests/test_finding_ticket.py
git commit -m "Ticket: show a recorded reproduction in the header and Reproduce (#143)" \
  -m "AC-1, AC-3, AC-4, AC-6" -m "Task: 2" -m "red: 9 failed in tests/test_finding_ticket.py, among them test_a_recorded_reproduction_is_shown_in_the_header_and_the_reproduce_section: assert '- **Reproduction** — Reproduced by a failing test' in header"
```

## Task 3: The words

**Satisfies:** AC-7. **Files:** `README.md`, `CLAUDE.md`, `skills/thunderstruck-ticket/SKILL.md`, `tests/test_finding_ticket.py`.

- [ ] **Step 1: Failing tests.** Two existing assertions say `Reproduced` is refused; they now say when it is accepted.

In `test_the_skill_states_the_contract_the_script_validates`:

```python
    assert "`Reproduced` is refused" in text
```

becomes

```python
    assert "`Reproduced` is accepted only when a failing test is recorded" in text
```

In `test_the_readme_and_claude_md_describe_the_command_and_say_what_a_ticket_is`:

```python
    assert "`Reproduced` is refused until a reproduction is recorded" in readme
```

becomes

```python
    assert "`Reproduced` is accepted only when `/thunderstruck-verify` has recorded" in readme
```

Append at the end of the file:

```python
def test_the_docs_say_when_reproduced_is_accepted():
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    assert ("`Reproduced` is accepted only when `/thunderstruck-verify` has recorded a failing test "
            "for the finding and the record is current") in readme
    claude = " ".join((ROOT / "CLAUDE.md").read_text(encoding="utf-8").split())
    assert "`recorded_reproduction` reads the `reproduction` object `report.py` attaches" in claude
    assert "returns `None` until #103" not in claude
    skill = _flat()
    assert "`Reproduced` is accepted only when a failing test is recorded for the finding" in skill
    assert "only once the report is rebuilt" in skill
```

- [ ] **Step 2: Run the file and see 3 fail:** the two tests above and `test_the_docs_say_when_reproduced_is_accepted`.

- [ ] **Step 3: The text.** Three files, each old text once.

README, the Status bullet in `## From a finding to a reviewed fix`:

Old text (occurs exactly once):

```markdown
- **Status** is Hypothesis unless you pass `--status`. `Reproduced` is refused
  until a reproduction is recorded (#103).
```

New text:

```markdown
- **Status** is Hypothesis unless you pass `--status`. `Reproduced` is accepted only
  when `/thunderstruck-verify` has recorded a failing test for the finding and the
  record is current (#103). Anything else is refused with its reason: no record, a
  record the report does not show yet, a test that passed, a blocked run, a stale or
  an unreadable record. A recorded reproduction is shown whatever status you ask for.
```

`CLAUDE.md`, the gate bullet in `## The finding ticket`:

Old text (occurs exactly once):

```markdown
- **Only `Reproduced` is gated.** `recorded_reproduction` returns `None` until #103
  records one, and the request is refused.
```

New text:

```markdown
- **Only `Reproduced` is gated.** `recorded_reproduction` reads the `reproduction`
  object `report.py` attaches (#103) and accepts only a failing test whose state is
  `current`. Every other state is refused with its own reason, and a record file the
  report does not show yet says to rebuild the report. The state is the report's, read
  as it is, like the check status; the ticket does not derive it again.
```

`skills/thunderstruck-ticket/SKILL.md`:

Old text (occurs exactly once):

```markdown
finding is at that stage; the default is Hypothesis. `Reproduced` is refused
until a reproduction is recorded: relay the refusal, never work around it.
```

New text:

```markdown
finding is at that stage; the default is Hypothesis. `Reproduced` is accepted only
when a failing test is recorded for the finding and the record is current: relay a
refusal and its reason, never work around it. A reproduction recorded after the last
report shows in the ticket only once the report is rebuilt.
```

- [ ] **Step 4: Run the file: 253 passed.**

- [ ] **Step 5: Commit.**

```bash
git add README.md CLAUDE.md skills/thunderstruck-ticket/SKILL.md tests/test_finding_ticket.py
git commit -m "Docs: say when a ticket can be Reproduced (#143)" \
  -m "AC-7" -m "Task: 3" -m "red: 3 failed in tests/test_finding_ticket.py, among them test_the_docs_say_when_reproduced_is_accepted: the README does not say when Reproduced is accepted"
```

## Task 4: The changelog, and everything at once

**Satisfies:** AC-7. **Files:** `CHANGELOG.md`.

- [ ] **Step 1: The changelog.** One bullet at the end of the changed list under `## Unreleased`. No version moves: the top `## x.y.z` heading, `plugin.json`, `marketplace.json` and `pyproject.toml` stay as they are, which `test_versions_agree` checks.

Old text (occurs exactly once):

```markdown
namespaced or not.

### Fixed

- The skeptic's model is `claude-haiku-5-5`
```

New text:

```markdown
namespaced or not.
- **A ticket can say `Reproduced`** (#143). `finding_ticket.py --status Reproduced` is accepted when the finding has a current recorded failing test (#103), and refused with its own reason when no reproduction is recorded, when a record exists that the report does not show yet, when the test passed, when the run was blocked, when the record is stale and when it is unreadable. The header and the Reproduce section show a recorded reproduction whatever status is asked.

### Fixed

- The skeptic's model is `claude-haiku-5-5`
```

- [ ] **Step 2: The full suite, its real exit code, and every check that is not a test.**

```bash
THUNDERSTRUCK_REQUIRE_RENDERER=1 uv run --with pytest --with pyyaml --with lizard --with packaging --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
uv run scripts/gen_catalog_docs.py --check; echo "catalog=$?"
uv run scripts/gen_sample_report.py --check; echo "sample=$?"
uv run scripts/validate_plugin.py; echo "validate=$?"
claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck && claude plugin list
```

Expected: `exit=0`, `catalog=0`, `sample=0`, `validate=0` (the known CLAUDE.md warning is allowed; `validate=2` means `claude` is not on `PATH`: not run, never passed), and `thunderstruck` listed as `enabled`, not `failed to load`. If `claude` is unavailable the install check is reported as not run.

- [ ] **Step 3: Commit.**

```bash
git add CHANGELOG.md
git commit -m "Changelog: a ticket can say Reproduced (#143)" -m "AC-7" -m "Task: 4"
```

- [ ] **Step 4: The PR.** Title `A ticket can say Reproduced when a failing test is recorded`. The body begins `Refs #143`, lists the tasks, states the figures of Step 2 (the suite's pass and skip counts, and each check's exit code) and says which existing tests were edited and why (Global Constraints). Do not write a word that closes an issue next to an issue number.

## AC coverage

| AC | Tasks | Proof |
|---|---|---|
| AC-1 | 1, 2 | `test_reproduced_is_accepted_on_a_current_failing_reproduction`, the rule test, `test_a_reproduction_recorded_and_reported_for_real_makes_a_reproduced_ticket` |
| AC-2 | 1 | `test_reproduced_is_refused_with_the_reason_for_each_state_of_the_record` (seven states), and the stale and not-rebuilt tests on the real chain |
| AC-3 | 2 | the header and Reproduce tests, for a current record and for each other state, for two statuses |
| AC-4 | 2 | `test_the_recorded_command_is_inert_and_free_of_machine_values` |
| AC-5 | 1 | `test_a_finding_with_no_reproduction_key_has_none_recorded`, and the rule test's non-object cases |
| AC-6 | 2 | `test_the_ticket_with_a_recorded_reproduction_is_byte_identical_twice` |
| AC-7 | 3, 4 | `test_the_docs_say_when_reproduced_is_accepted` and the two edited assertions; the full suite, both `--check` generators, `validate_plugin.py`, the install check, the changelog bullet |
