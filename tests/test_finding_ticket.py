"""#108: a finding becomes a ticket someone can act on.

Small git repositories are built in a temporary directory with a hand-made
report.json, so each condition (a stale file, a hostile snippet, a missing
link setting) is exercised on its own; one test runs the real pipeline over
the fixture."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c
import mdtext
from test_mdtext import RENDERERS, render

ROOT = Path(__file__).resolve().parent.parent


# --- Task 1: the fence and tracker references in mdtext ---------------------

HOSTILE_LINES = [
    "const a = 1;",
    "```",
    "````js",
    "    ``` still not the end of the fence",
    "# not a heading",
    "- not a list item",
    "[click](https://evil.example) ![i](https://evil.example/x.png) <img src=x onerror=1> <script>alert(1)</script>",
    "x" * 5000,
    "tab\there  and trailing spaces  ",
    "lone\rcr, bidi ‮ reversed, escape \x1b[31m",
]


def test_verbatim_fence_is_longer_than_any_backtick_run_inside():
    block, escaped = mdtext.verbatim(HOSTILE_LINES)
    rows = block.split("\n")
    assert rows[0] == "`" * 5 == rows[-1]          # the longest run is four
    assert escaped == 3                              # the lone \r, the bidi mark, the escape
    assert mdtext.verbatim(["plain"]) == ("```\nplain\n```", 0)
    assert mdtext.verbatim(["a `b` c"])[0].startswith("```\n")


@pytest.mark.parametrize("renderer", RENDERERS, ids=lambda r: r.__name__)
def test_a_verbatim_block_is_one_code_block_whatever_it_holds(renderer):
    block, _ = mdtext.verbatim(HOSTILE_LINES)
    html = renderer(f"before\n\n{block}\n\nafter")
    assert html.tags == ["p", "pre", "code", "p"], html.tags
    shown = "".join(html.text)
    assert "evil.example" in shown and "# not a heading" in shown
    body = shown.split("before", 1)[1].rsplit("after", 1)[0]
    assert "‮" not in body and "\x1b" not in body and "\r" not in body
    assert "\\u202e" in body and "\\u001b" in body and "\\u000d" in body
    assert "\t" in body and "  \n" in body            # tabs and trailing spaces are kept


def test_verbatim_keeps_every_other_character_as_written():
    lines = ["  indented", "", "naïve — ünïcode ✓", "x = '\"'; y = `z`"]
    block, escaped = mdtext.verbatim(lines)
    assert escaped == 0
    assert block.split("\n")[1:-1] == lines


@pytest.mark.parametrize("token, shown", [
    ("#12", "`#12`"), ("(#12),", "(`#12`),"), ("!7", "`!7`"), ("ABC-123", "`ABC-123`"),
    ("acme/api#12", "`acme/api#12`"), ("PR#7", "`PR#7`"), ("group/proj!3", "`group/proj!3`"),
    ("a1b2c3d", "`a1b2c3d`"), ("0a1b2c3d4e5f60718293a4b5c6d7e8f901234567",
                               "`0a1b2c3d4e5f60718293a4b5c6d7e8f901234567`"),
])
def test_a_tracker_reference_becomes_a_code_span(token, shown):
    assert mdtext.text(f"see {token} now") == f"see {shown} now"


@pytest.mark.parametrize("word", ["10:30:45", "C#", "2000000", "1234567", "decade", "defaced", "deadbeef",
                                  "plain", "a-b", "v1.2", "utf-8", "sha-256", "x86-64", "line-5"])
def test_ordinary_words_and_numbers_are_left_alone(word):
    """A key needs capitals (not utf-8), a sha needs a digit and a letter (not a word made of
    a-f), and a run of digits alone is a number."""
    assert mdtext.text(f"see {word} now") == f"see {word} now"


# --- Task 2: choosing the finding, and the status --------------------------

import finding_ticket as ft

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
SCANNED_AT = "2025-01-06T09:00:00+00:00"
KEY = "a1b2c3d4e5f6"
BASE = "https://github.example.com/acme/scanned"
RELEASES = "".join(f"line {n}\n" for n in range(1, 31))


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True,
                          text=True, env=GIT_ENV)


def make_repo(tmp_path, files=None):
    """A committed repository standing in for the scanned one."""
    repo = tmp_path / "scanned"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    for rel, content in (files or {"src/releases.ts": RELEASES,
                                   "src/api.ts": "export const api = 1;\n"}).items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    return repo


def head_of(repo):
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def make_finding(repo, **over):
    """A finding as report.json carries it, with the hashes validate.py would record."""
    f = {"id": "FR-001", "key": KEY, "hotspot_id": "H01", "hotspot_score": 0.5,
         "location": {"file": "src/releases.ts", "symbol": "fetchRelease", "lines": "3-5", "url": None},
         "missing_patterns": ["S02"],
         "failure_mode": "Retries stack and one blip becomes a storm",
         "trigger_condition": "The upstream answers 503 for more than two seconds",
         "amplifier": "Two layers retry", "sustaining_effect": "Every client waits the same time",
         "blast_radius": "Every release lookup",
         "blast_items": [{"claim": "Lookups wait on the loop", "basis": "traced", "evidence": [0]},
                         {"claim": "web-frontend depends on it", "basis": "catalog", "evidence": [2]}],
         "not_checked": [{"item": "Whether callers retry again", "how_to_check": "Read the callers"}],
         "implicit_guarantees": [{"guarantee": "One blip never reaches the caller",
                                  "removed_by": "capping the loop", "evidence": [0]}],
         "evidence": [{"type": "code", "ref": "src/releases.ts:3-5", "note": "the loop", "url": None},
                      {"type": "code", "ref": "src/api.ts:1", "note": "the client", "url": None},
                      {"type": "catalog", "ref": "dependencyOf component:default/web-frontend",
                       "note": "listed as a dependent", "url": None}],
         "preconditions": [], "confidence": "medium", "confidence_claimed": "high",
         "confidence_rationale": "Both layers are visible",
         "how_to_verify": "Stub a 503 and count the requests",
         "prediction": "The next incident is a retry storm",
         "check": {"status": "unchecked", "by": None, "reason": None},
         "gate": "none", "history": [], "catalog_evidence": [], "also_at": [], "shares_code_with": []}
    f.update(over)
    if "content_hash" not in over:
        f["content_hash"] = c.sha256_file(repo / f["location"]["file"])
    if "evidence_hashes" not in over:
        f["evidence_hashes"] = {p: c.sha256_file(repo / p) for p in sorted(
            {e["ref"].split(":")[0] for e in f["evidence"] if e["type"] == "code"})}
    return f


def _permalink(sha, ref):
    path, _, rng = ref.partition(":")
    a, _, b = rng.partition("-")
    return f"{BASE}/blob/{sha}/{path}#L{a}" + (f"-L{b}" if b else "")


def make_report(repo, findings=None, links=True, **over):
    """report.json as report.py writes it, linked when `links`; returns the dict."""
    sha = head_of(repo)
    findings = [make_finding(repo)] if findings is None else findings
    if links:
        for f in findings:
            f["location"].setdefault("url", None)
            if f["location"].get("file") and f["location"].get("url") is None:
                f["location"]["url"] = _permalink(sha, f"{f['location']['file']}:{f['location']['lines']}")
            for ev in f["evidence"]:
                if ev["type"] == "code" and ev.get("url") is None:
                    ev["url"] = _permalink(sha, ev["ref"])
    rep = {"schema": c.REPORT_SCHEMA_VERSION, "generated_at": "2099-01-01T00:00:00+00:00",
           "scanned_at": SCANNED_AT, "repo": {"root": str(repo), "head": sha, "branch": "alice/feature"},
           "warnings": [], "run_warnings": [],
           "links": ({"provider": "github", "base_url": BASE, "sha": sha, "remote": "origin"}
                     if links else None),
           "verification": {"ran": False, "model": None, "checked": 0, "reused": 0,
                            "dependencies": [], "warnings": []},
           "findings": findings, "refuted": []}
    rep.update(over)
    (repo / ".thunderstruck").mkdir(exist_ok=True)
    c.write_json(repo / ".thunderstruck" / "report.json", rep)
    return rep


def test_a_finding_is_found_by_its_key(tmp_path):
    rep = make_report(make_repo(tmp_path))
    found = ft.find_finding(rep, KEY)
    assert found["key"] == KEY and found["check"]["status"] == "unchecked"


@pytest.mark.parametrize("key", ["", "FR-001", "../../etc/passwd", "A1B2C3D4E5F6", "a1b2c3d4e5f",
                                 "a1b2c3d4e5f6a", "a1b2c3d4e5f6\n", "a1b2c3d4e5f6/../x"])
def test_a_key_has_a_shape_before_anything_else_uses_it(tmp_path, key):
    rep = make_report(make_repo(tmp_path))
    with pytest.raises(c.ThunderstruckError, match="12 lowercase hex"):
        ft.find_finding(rep, key)


def test_a_missing_or_unrecognised_check_reads_as_unchecked(tmp_path):
    repo = make_repo(tmp_path)
    for check in ({"status": "approved"}, "junk", None):
        rep = make_report(repo, [make_finding(repo, check=check)])
        assert ft.find_finding(rep, KEY)["check"]["status"] == "unchecked"
    f = make_finding(repo)
    del f["check"]
    assert ft.find_finding(make_report(repo, [f]), KEY)["check"]["status"] == "unchecked"


def test_the_stored_report_is_not_changed_by_looking(tmp_path):
    repo = make_repo(tmp_path)
    rep = make_report(repo)
    before = copy.deepcopy(rep)
    ft.find_finding(rep, KEY)["failure_mode"] = "changed"
    assert rep == before


def test_a_refuted_finding_gets_no_ticket_and_the_refusal_says_why(tmp_path):
    repo = make_repo(tmp_path)
    refuted = make_finding(repo, check={"status": "refuted", "by": "skeptic", "reason": "x"})
    rep = make_report(repo, findings=[], refuted=[refuted])
    with pytest.raises(c.ThunderstruckError, match="refuted.*no ticket is made"):
        ft.find_finding(rep, KEY)


def test_a_duplicate_names_the_finding_that_absorbed_it(tmp_path):
    repo = make_repo(tmp_path)
    survivor = make_finding(repo, key="f" * 12, also_at=[{"key": KEY, "hotspot_id": "H02",
                                                          "location": {"file": "src/api.ts"}}])
    rep = make_report(repo, [survivor])
    with pytest.raises(c.ThunderstruckError, match="duplicate.*ffffffffffff"):
        ft.find_finding(rep, KEY)


def test_an_unknown_key_lists_the_keys_to_choose_from(tmp_path):
    repo = make_repo(tmp_path)
    many = [make_finding(repo, key=f"{n:012x}", id=f"FR-{n:03d}") for n in range(1, 31)]
    rep = make_report(repo, many)
    with pytest.raises(c.ThunderstruckError) as err:
        ft.find_finding(rep, "0" * 12)
    message = str(err.value)
    assert "no finding with key 000000000000" in message
    assert message.count("src/releases.ts") == 20 and "and 10 more" in message


def test_the_listing_shows_key_id_location_and_a_clipped_failure_mode(tmp_path):
    repo = make_repo(tmp_path)
    f = make_finding(repo, failure_mode="a" * 300 + "\nsecond \x1b[31mline")
    (line,) = ft.list_findings(make_report(repo, [f]))
    assert line.startswith(f"{KEY} · FR-001 · src/releases.ts:3-5 · aaaa")
    assert "\x1b" not in line and "\n" not in line and len(line) < 220


def test_the_report_must_exist_and_be_this_schema(tmp_path):
    repo = make_repo(tmp_path)
    with pytest.raises(c.ThunderstruckError, match="no report.json"):
        ft.load_report(repo)
    make_report(repo, schema="thunderstruck.report/v1")
    with pytest.raises(c.ThunderstruckError, match="schema.*Re-run the scan"):
        ft.load_report(repo)
    make_report(repo)
    assert ft.load_report(repo)["findings"]


@pytest.mark.parametrize("given, status", [
    ("Hypothesis", "Hypothesis"), ("hypothesis", "Hypothesis"), ("fix proposed", "Fix proposed"),
    ("fix-proposed", "Fix proposed"), ("FIX_REVIEWED", "Fix reviewed"), (" Reproduced ", "Reproduced")])
def test_a_status_is_one_of_the_four(given, status):
    assert ft.parse_status(given) == status


def test_any_other_status_is_refused():
    import argparse
    with pytest.raises(argparse.ArgumentTypeError, match="Hypothesis, Reproduced, Fix proposed, Fix reviewed"):
        ft.parse_status("Fixed")


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


# --- Task 3: stop when the code is not the scan ----------------------------

import links


def _check(repo, rep=None, finding=None):
    rep = rep if rep is not None else json.loads((repo / ".thunderstruck" / "report.json").read_text())
    ft.check_snapshot(repo, rep, finding if finding is not None else ft.find_finding(rep, KEY))


def _refused(repo, *fragments, rep=None, finding=None):
    with pytest.raises(c.ThunderstruckError) as err:
        _check(repo, rep, finding)
    message = str(err.value)
    for fragment in fragments:
        assert fragment in message, (fragment, message)
    return message


def test_a_tree_that_is_the_scanned_commit_passes(tmp_path):
    repo = make_repo(tmp_path)
    make_report(repo)
    _check(repo)


def test_an_edited_cited_file_stops_and_names_the_way_forward(tmp_path):
    repo = make_repo(tmp_path)
    make_report(repo)
    (repo / "src/releases.ts").write_text("edited\n")
    message = _refused(repo, '"src/releases.ts": differs from the scanned commit',
                       "Rescan with /thunderstruck-scan", f"git switch --detach {head_of(repo)}")
    assert message.startswith("no ticket was written for finding " + KEY)


def test_a_staged_edit_stops(tmp_path):
    repo = make_repo(tmp_path)
    make_report(repo)
    (repo / "src/api.ts").write_text("export const api = 2;\n")
    git(repo, "add", "src/api.ts")
    _refused(repo, '"src/api.ts": differs from the scanned commit')


def test_a_file_the_scan_saw_in_another_state_can_only_be_fixed_by_a_rescan(tmp_path):
    repo = make_repo(tmp_path)
    finding = make_finding(repo, content_hash="sha256:" + "0" * 64)     # scanned dirty, now the commit's text
    make_report(repo, [finding])
    message = _refused(repo, '"src/releases.ts": changed since the scan recorded it',
                       "Rescan with /thunderstruck-scan", "cannot fix that")
    assert "git switch" not in message


def test_an_edit_since_the_scan_offers_the_checkout_and_says_when_it_will_not_do(tmp_path):
    repo = make_repo(tmp_path)
    make_report(repo)
    (repo / "src/releases.ts").write_text("edited\n")
    message = _refused(repo, f"git switch --detach {head_of(repo)}", "only a rescan fixes that")
    assert "cannot fix that" not in message


def test_when_any_file_needs_a_rescan_the_way_forward_is_the_rescan(tmp_path):
    repo = make_repo(tmp_path)
    finding = make_finding(repo, content_hash="sha256:" + "0" * 64)
    make_report(repo, [finding])
    (repo / "src/api.ts").write_text("edited\n")                      # a plain edit as well
    message = _refused(repo, '"src/api.ts": differs from the scanned commit',
                       '"src/releases.ts": changed since the scan recorded it', "cannot fix that")
    assert "git switch" not in message


def test_the_ticket_script_may_start_git_and_nothing_else():
    """#102's test_no_execution.py reviews where a process may start: finding_ticket.py runs git, in _git."""
    import ast
    import test_no_execution as ne
    tree = ast.parse((ROOT / "scripts" / "finding_ticket.py").read_text(encoding="utf-8"))
    starters = {fn for fn, call in ne._calls(tree) if ast.unparse(call.func).startswith("subprocess.")}
    assert starters == {"_git"}
    assert ("finding_ticket.py", "_git") in ne.GIT_ONLY


def test_a_commit_made_since_the_scan_stops(tmp_path):
    repo = make_repo(tmp_path)
    rep = make_report(repo)
    (repo / "src/releases.ts").write_text(RELEASES + "more\n")
    git(repo, "commit", "-qam", "later")
    _refused(repo, '"src/releases.ts"', rep=rep)


def test_an_untracked_cited_file_stops(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "src/new.ts").write_text("export const n = 1;\n")
    finding = make_finding(repo, evidence=[{"type": "code", "ref": "src/new.ts:1", "note": "n", "url": None}],
                           blast_items=[], implicit_guarantees=[])
    make_report(repo, [finding])
    _refused(repo, '"src/new.ts": is not tracked by git')


def test_a_committed_symlink_and_a_submodule_stop(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "src/link.ts").symlink_to("api.ts")
    git(repo, "add", "src/link.ts")
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head_of(repo)},vendor/lib")
    git(repo, "commit", "-qm", "link and submodule")
    evidence = [{"type": "code", "ref": "src/link.ts:1", "note": "l", "url": None},
                {"type": "code", "ref": "vendor/lib:1", "note": "s", "url": None}]
    finding = make_finding(repo, evidence=evidence, blast_items=[], implicit_guarantees=[],
                           content_hash="sha256:x", evidence_hashes={"src/link.ts": "x", "vendor/lib": "x"})
    make_report(repo, [finding])
    _refused(repo, '"src/link.ts": is a symbolic link', '"vendor/lib": is a submodule')


def test_a_deleted_cited_file_stops(tmp_path):
    repo = make_repo(tmp_path)
    make_report(repo)
    (repo / "src/api.ts").unlink()
    _refused(repo, '"src/api.ts": is missing from the working tree')


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_a_file_git_was_told_to_ignore_cannot_hide_an_edit(tmp_path, flag):
    repo = make_repo(tmp_path)
    make_report(repo)
    git(repo, "update-index", flag, "src/releases.ts")
    (repo / "src/releases.ts").write_text("edited behind git's back\n")
    _refused(repo, '"src/releases.ts": differs from the scanned commit')


def test_a_file_scanned_dirty_and_since_reverted_is_not_what_the_finding_recorded(tmp_path):
    repo = make_repo(tmp_path)
    finding = make_finding(repo, content_hash="sha256:" + "0" * 64)      # the scan saw other bytes
    make_report(repo, [finding])
    _refused(repo, '"src/releases.ts": changed since the scan recorded it')


def test_an_unrecorded_hash_is_a_stop_not_a_pass(tmp_path):
    repo = make_repo(tmp_path)
    finding = make_finding(repo)
    del finding["evidence_hashes"]["src/api.ts"]
    make_report(repo, [finding])
    _refused(repo, '"src/api.ts": has no hash recorded by the scan')


@pytest.mark.parametrize("head", ["", "unknown", "abc1234", "A" * 40, "g" * 40, None, 7])
def test_a_scan_without_a_full_commit_cannot_be_checked(tmp_path, head):
    repo = make_repo(tmp_path)
    rep = make_report(repo)
    rep["repo"]["head"] = head
    _refused(repo, "records no scanned commit", rep=rep)


def test_a_commit_this_clone_does_not_have_stops_and_names_it(tmp_path):
    repo = make_repo(tmp_path)
    rep = make_report(repo)
    rep["repo"]["head"] = "0" * 40
    _refused(repo, "0" * 40, "is not in this repository", "shallow", rep=rep)


def test_a_shallow_clone_that_has_the_scanned_commit_passes(tmp_path):
    origin = make_repo(tmp_path / "origin")
    (origin / "src/releases.ts").write_text(RELEASES + "second\n")
    git(origin, "commit", "-qam", "second")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{origin}", str(clone)],
                   check=True, capture_output=True, env=GIT_ENV)
    assert git(clone, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    make_report(clone)
    _check(clone)


def test_a_dirty_file_nothing_cites_is_not_compared(tmp_path):
    repo = make_repo(tmp_path, {"src/releases.ts": RELEASES, "src/api.ts": "x\n", "src/other.ts": "y\n"})
    make_report(repo)
    (repo / "src/other.ts").write_text("dirty\n")
    (repo / "notes.txt").write_text("untracked\n")
    _check(repo)


def test_line_ending_conversion_alone_does_not_stop(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "config", "core.autocrlf", "true")
    (repo / "src/releases.ts").write_bytes(RELEASES.replace("\n", "\r\n").encode())
    make_report(repo)               # the hashes are of these working-tree bytes, as validate.py takes them
    _check(repo)


def test_many_files_are_named_five_at_a_time(tmp_path):
    files = {f"src/f{n}.ts": f"{n}\n" for n in range(7)}
    repo = make_repo(tmp_path, files)
    evidence = [{"type": "code", "ref": f"src/f{n}.ts:1", "note": "n", "url": None} for n in range(7)]
    finding = make_finding(repo, location={"file": "src/f0.ts", "lines": "1"}, evidence=evidence,
                           blast_items=[], implicit_guarantees=[])
    make_report(repo, [finding])
    for n in range(7):
        (repo / f"src/f{n}.ts").write_text("edited\n")
    message = _refused(repo, "… and 2 more")
    assert message.count("differs from the scanned commit") == 5


def test_a_cited_path_that_leaves_the_repository_stops(tmp_path):
    repo = make_repo(tmp_path)
    evidence = [{"type": "code", "ref": "../outside.ts:1", "note": "o", "url": None}]
    finding = make_finding(repo, evidence=evidence, blast_items=[], implicit_guarantees=[],
                           content_hash="sha256:x", evidence_hashes={})
    make_report(repo, [finding])
    _refused(repo, "climbs out of the repository")


def test_a_git_failure_or_timeout_is_a_named_stop(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    make_report(repo)

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("git", 30)

    def failure(*a, **k):
        raise c.ThunderstruckError("git ls-tree failed (128): fatal: /secret/path")
    monkeypatch.setattr(links, "stale_paths", timeout)
    _refused(repo, "git did not answer")
    monkeypatch.setattr(links, "stale_paths", failure)
    assert "/secret/path" not in _refused(repo, "git failed while comparing")


# --- Task 4: snippets from the scanned commit -------------------------------

from validate import _count_lines


def _cite(repo, rel, a, b=None, note="the code", url=None):
    ref = f"{rel}:{a}" + (f"-{b}" if b else "")
    return make_finding(repo, evidence=[{"type": "code", "ref": ref, "note": note, "url": url}],
                        blast_items=[], implicit_guarantees=[])


def _steps(repo, finding):
    return ft.code_steps(repo, head_of(repo), finding)


def _independent_lines(repo, rel):
    """The file at HEAD the way `git blame` and validate.py count it, written out again."""
    data = subprocess.run(["git", "-C", str(repo), "show", f"HEAD:{rel}"], check=True,
                          capture_output=True, env=GIT_ENV).stdout
    text = data.decode("utf-8", "replace")
    parts = text.split("\n")
    if parts[-1] == "":
        parts.pop()
    return [p[:-1] if p.endswith("\r") else p for p in parts] or [""]


CONTENTS = {
    "lf": b"one\ntwo\nthree\n",
    "no final newline": b"one\ntwo\nthree",
    "crlf": b"one\r\ntwo\r\nthree\r\n",
    "tabs and trailing spaces": b"\tone  \n\t\ttwo \nthree\t\n",
    "a lone carriage return": b"one\rstill one\ntwo\nthree\n",
    "a form feed": b"one\n\x0c\ntwo\nthree\n",
    "unicode": "naïve — ünïcode ✓\n日本語\nthree\n".encode(),
    "bytes that are not utf-8": b"caf\xe9\nbad \xff\xfe\nthree\n",
    "blank lines": b"\n\none\n\n",
    "one line": b"only\n",
    "empty": b"",
}


@pytest.mark.parametrize("name", sorted(CONTENTS))
def test_a_snippet_is_the_text_of_the_file_at_the_scanned_commit(tmp_path, name):
    repo = make_repo(tmp_path, {"src/a.ts": CONTENTS[name]})
    expected = _independent_lines(repo, "src/a.ts")
    assert len(expected) == _count_lines(repo / "src/a.ts")        # validate.py counts the same lines
    steps, extra = _steps(repo, _cite(repo, "src/a.ts", 1, len(expected) if len(expected) > 1 else None))
    assert extra == 0 and len(steps) == 1
    assert steps[0].lines == expected and (steps[0].start, steps[0].end) == (1, len(expected))


def test_a_file_stored_in_git_lfs_is_a_stop_not_a_pointer_shown_as_code(tmp_path):
    pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 12345\n"
    repo = make_repo(tmp_path, {"src/big.bin": pointer, "src/api.ts": "x\n"})
    with pytest.raises(c.ThunderstruckError, match='"src/big.bin" is stored with Git LFS.*pointer, not the code'):
        _steps(repo, _cite(repo, "src/big.bin", 1))
    (step,), _ = _steps(repo, _cite(repo, "src/api.ts", 1))               # a file that is not a pointer
    assert step.lines == ["x"]


def test_the_snippet_is_the_commit_not_the_working_tree(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "src/releases.ts").write_bytes(RELEASES.replace("\n", "\r\n").encode())
    git(repo, "config", "core.autocrlf", "true")
    (step,), _ = _steps(repo, _cite(repo, "src/releases.ts", 3, 5))
    assert step.lines == ["line 3", "line 4", "line 5"]


def test_a_single_line_and_a_range_are_rebuilt_from_the_numbers(tmp_path):
    repo = make_repo(tmp_path)
    (one,), _ = _steps(repo, _cite(repo, "src/releases.ts", 7))
    (many,), _ = _steps(repo, _cite(repo, "src/releases.ts", 7, 9))
    assert (one.label, one.lines) == ("src/releases.ts:7", ["line 7"])
    assert (many.label, many.lines) == ("src/releases.ts:7-9", ["line 7", "line 8", "line 9"])


@pytest.mark.parametrize("a, b", [(25, 99), (31, None), (0, 2), (5, 3)])
def test_a_range_the_commit_does_not_have_is_a_stop(tmp_path, a, b):
    repo = make_repo(tmp_path)
    with pytest.raises(c.ThunderstruckError, match="src/releases.ts.*at the scanned commit has 30 lines"):
        _steps(repo, _cite(repo, "src/releases.ts", a, b))


def test_only_code_evidence_makes_a_step_and_in_the_findings_order(tmp_path):
    repo = make_repo(tmp_path)
    finding = make_finding(repo, evidence=[
        {"type": "commit", "ref": "abc1234", "note": "c", "url": None},
        {"type": "code", "ref": "src/api.ts:1", "note": "second file first", "url": "https://x.example/a"},
        {"type": "catalog", "ref": "dependencyOf component:default/web", "note": "k", "url": None},
        {"type": "code", "ref": "src/releases.ts:2", "note": "then this", "url": None},
        {"type": "code", "ref": "not a ref", "note": "skipped", "url": None}],
        blast_items=[], implicit_guarantees=[])
    steps, _ = _steps(repo, finding)
    assert [s.label for s in steps] == ["src/api.ts:1", "src/releases.ts:2"]
    assert [s.note for s in steps] == ["second file first", "then this"]
    assert [s.url for s in steps] == ["https://x.example/a", None]


def test_a_long_citation_is_cut_and_says_so_outside_the_fence(tmp_path):
    repo = make_repo(tmp_path, {"src/big.ts": "".join(f"row {n}\n" for n in range(1, 101))})
    (step,), _ = _steps(repo, _cite(repo, "src/big.ts", 1, 100))
    assert len(step.lines) == ft.MAX_SNIPPET_LINES == 40 and step.hidden == 60
    text = "\n".join(ft.render_step(1, step))
    assert "Lines 41-100 (60 lines) not shown: open the link or the file." in text
    fenced = text.split("```")[1]
    assert "not shown" not in fenced and fenced.strip("\n").splitlines()[-1] == "row 40"


def test_a_very_long_line_is_shortened_and_says_so(tmp_path):
    repo = make_repo(tmp_path, {"src/min.js": "short\n" + "x" * 5000 + "\n" + "y" * 241 + "\n"})
    (step,), _ = _steps(repo, _cite(repo, "src/min.js", 1, 3))
    assert [len(line) for line in step.lines] == [5, 240, 240] and step.shortened == 2
    assert "2 lines were shortened to 240 characters." in "\n".join(ft.render_step(1, step))


def test_a_citation_of_exactly_the_caps_is_not_called_cut(tmp_path):
    repo = make_repo(tmp_path, {"src/e.ts": "".join("z" * 240 + "\n" for _ in range(40))})
    (step,), _ = _steps(repo, _cite(repo, "src/e.ts", 1, 40))
    text = "\n".join(ft.render_step(1, step))
    assert step.hidden == 0 and step.shortened == 0 and "not shown" not in text and "shortened" not in text


def test_at_most_twelve_steps_and_the_rest_are_counted(tmp_path):
    repo = make_repo(tmp_path)
    finding = make_finding(repo, evidence=[{"type": "code", "ref": f"src/releases.ts:{n}", "note": str(n),
                                            "url": None} for n in range(1, 15)],
                           blast_items=[], implicit_guarantees=[])
    steps, extra = _steps(repo, finding)
    assert len(steps) == ft.MAX_STEPS == 12 and extra == 2


def test_a_step_shows_its_link_its_code_and_what_to_notice(tmp_path):
    repo = make_repo(tmp_path)
    url = f"{BASE}/blob/{head_of(repo)}/src/releases.ts#L3-L4"
    (step,), _ = _steps(repo, _cite(repo, "src/releases.ts", 3, 4, note="the retry loop", url=url))
    assert ft.render_step(2, step) == [
        "### Step 2", "", f"[`src/releases.ts:3-4`]({url})", "", "```\nline 3\nline 4\n```", "",
        "What to notice: the retry loop", ""]


def test_a_step_without_a_link_or_a_note_still_reads_whole(tmp_path):
    repo = make_repo(tmp_path)
    (step,), _ = _steps(repo, _cite(repo, "src/releases.ts", 3, note="  "))
    rows = ft.render_step(1, step)
    assert rows[2] == "`src/releases.ts:3`" and rows[-2] == "What to notice: not stated."


def test_hidden_characters_in_the_code_are_shown_and_counted(tmp_path):
    repo = make_repo(tmp_path, {"src/h.ts": "a‮b\nc\x1bd\n"})
    (step,), _ = _steps(repo, _cite(repo, "src/h.ts", 1, 2))
    text = "\n".join(ft.render_step(1, step))
    assert "a\\u202eb" in text and "c\\u001bd" in text and "‮" not in text
    assert "2 control or bidirectional characters are shown as \\uXXXX." in text


@pytest.mark.parametrize("url, ok", [
    ("https://github.example.com/acme/scanned/blob/abc/src/x.ts#L3-L4", True), ("http://h.example/x", True),
    ("javascript:alert(1)", False), ("https://x.example/a) [b](c", False), ("https://x.example/a b", False),
    ("https://x.example/<b>", False), ("https://x.example/`", False), ("https://x.example/\\x", False),
    ("//x.example/a", False), ("https://", False), ("", False), (None, False), (7, False)])
def test_only_a_plain_web_address_is_a_link(url, ok):
    assert ft.safe_url(url) is ok


def test_every_unsafe_link_field_is_dropped_at_any_depth_and_the_rest_kept():
    value = {"url": "javascript:x", "location": {"url": "https://ok.example/a"},
             "evidence": [{"url": "https://x.example/) [y](z", "ref": "keep"}],
             "preconditions": [{"default_url": "<b>", "doc_url": "https://ok.example/d"}],
             "check": {"evidence": [{"url": None}]}, "history": [{"url": "ftp://x.example"}]}
    out = ft.clean_urls(value)
    assert out is value
    assert value["url"] is None and value["location"]["url"] == "https://ok.example/a"
    assert value["evidence"][0] == {"url": None, "ref": "keep"}
    assert value["preconditions"][0] == {"default_url": None, "doc_url": "https://ok.example/d"}
    assert value["history"][0]["url"] is None


def test_a_step_never_takes_an_unsafe_address(tmp_path):
    repo = make_repo(tmp_path)
    (step,), _ = _steps(repo, _cite(repo, "src/releases.ts", 3, url="https://x.example/a) [b](c"))
    assert step.url is None


# --- Task 5: links, the guidance and the drafted sections -------------------

SECTIONS_OK = {"schema": "thunderstruck.ticket-sections/v1", "key": KEY, "scanned_at": SCANNED_AT,
               "sections": {"fix_options": ["Cap the loop at one attempt."],
                            "acceptance_criteria": ["A 503 is retried at most twice."]}}


def _drafts(tmp_path, doc=None, raw=None, scanned_at=SCANNED_AT, key=KEY):
    path = tmp_path / f"{KEY}.sections.json"
    if raw is not None:
        path.write_bytes(raw)
    elif doc is not None:
        path.write_text(json.dumps(doc))
    return ft.load_sections(path, key, scanned_at)


def test_no_drafts_file_is_silent(tmp_path):
    drafts = _drafts(tmp_path)
    assert drafts == ft.Drafts({}, {}, [], None)


def test_a_valid_drafts_file_is_used_and_fingerprinted(tmp_path):
    drafts = _drafts(tmp_path, SECTIONS_OK)
    assert drafts.sections == {"fix_options": ["Cap the loop at one attempt."],
                               "acceptance_criteria": ["A 503 is retried at most twice."]}
    assert drafts.unused == {} and drafts.notes == []
    assert drafts.digest == "sha256:" + hashlib.sha256((tmp_path / f"{KEY}.sections.json").read_bytes()).hexdigest()


@pytest.mark.parametrize("doc, reason", [
    ({**SECTIONS_OK, "key": "f" * 12}, "it was written for another finding or an earlier scan"),
    ({**SECTIONS_OK, "scanned_at": "2020-01-01T00:00:00+00:00"}, "it was written for another finding or an earlier scan"),
    ({**SECTIONS_OK, "schema": "v0"}, "its schema is not thunderstruck.ticket-sections/v1"),
    ({**SECTIONS_OK, "sections": ["x"]}, "`sections` is not an object"),
    ([1, 2], "it is not a JSON object"),
])
def test_a_file_that_does_not_belong_is_not_used_at_all(tmp_path, doc, reason):
    drafts = _drafts(tmp_path, doc)
    assert drafts.sections == {} and len(drafts.unused) == 4
    assert all(reason in r for r in drafts.unused.values())
    assert drafts.notes == [f"The drafts file was not used: {reason}."]


@pytest.mark.parametrize("raw, reason", [
    (b"{not json", "it is not valid UTF-8 JSON"), (b"\xff\xfe", "it is not valid UTF-8 JSON"),
    (b"x" * (64 * 1024 + 1), "it is larger than 64 KB")])
def test_a_file_that_is_not_json_or_too_large_is_not_used(tmp_path, raw, reason):
    drafts = _drafts(tmp_path, raw=raw)
    assert drafts.sections == {} and reason in drafts.notes[0]


def test_a_drafts_file_with_the_wrong_binding_is_not_used_when_the_scan_has_no_stamp(tmp_path):
    assert _drafts(tmp_path, SECTIONS_OK, scanned_at=None).sections == {}


def test_a_symlinked_drafts_file_is_not_read(tmp_path):
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps(SECTIONS_OK))
    link = tmp_path / f"{KEY}.sections.json"
    link.symlink_to(target)
    drafts = ft.load_sections(link, KEY, SCANNED_AT)
    assert drafts.sections == {} and "not a regular file" in drafts.notes[0]


@pytest.mark.parametrize("draft, reason", [
    ("text", "not a non-empty list"), ([], "not a non-empty list"), (None, "not a non-empty list"),
    (["x"] * 9, "more than 8 items"), (["ok", ""], "not a string of 1 to 400 characters"),
    (["ok", "  "], "not a string of 1 to 400 characters"), (["ok", 7], "not a string of 1 to 400 characters"),
    (["x" * 401], "not a string of 1 to 400 characters")])
def test_one_bad_section_is_not_used_and_the_others_stand(tmp_path, draft, reason):
    doc = {**SECTIONS_OK, "sections": {"fix_options": draft, "out_of_scope": ["Fixing callers."]}}
    drafts = _drafts(tmp_path, doc)
    assert drafts.sections == {"out_of_scope": ["Fixing callers."]}
    assert reason in drafts.unused["fix_options"]
    assert any("Fix options" in n and reason in n for n in drafts.notes)


def test_the_caps_are_inclusive(tmp_path):
    doc = {**SECTIONS_OK, "sections": {"fix_options": ["x" * 400] * 8}}
    assert list(_drafts(tmp_path, doc).sections) == ["fix_options"]


def test_an_unknown_section_is_ignored_and_named_as_text(tmp_path):
    doc = {**SECTIONS_OK, "sections": {"fix_options": ["a"], "severity": ["high"], "x](https://evil.example)": ["b"]}}
    drafts = _drafts(tmp_path, doc)
    assert list(drafts.sections) == ["fix_options"]
    assert any("`severity`" in n for n in drafts.notes)
    assert any("`x](https://evil.example)`" in n for n in drafts.notes)         # a code span, not a link


def test_the_guidance_paths_are_the_ones_the_guidance_ticket_published():
    from guidance_check import PUBLISHED
    assert ft.GUIDANCE == PUBLISHED
    for path in ft.GUIDANCE.values():
        assert (ROOT / path).is_file()


def _plugin_repository():
    return json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["repository"].rstrip("/")


def test_the_guidance_line_links_the_plugin_repository_not_a_relative_path():
    base = _plugin_repository()
    line = ft.guidance_line()
    assert line == (f"How to fix: [`fix-agent-instructions.md`]({base}/blob/main/docs/fix-agent-instructions.md)"
                    f" · how to review: [`review-briefs.md`]({base}/blob/main/docs/review-briefs.md)")
    assert "](docs/" not in line


@pytest.mark.parametrize("plugin_json", [
    None, "{not json", "[]", "{}", '{"repository": 7}', '{"repository": "git+ssh://git@x.example/a/b"}',
    '{"repository": "https://user:secret@x.example/a/b"}', '{"repository": "https://x.example/a/b?token=1"}'])
def test_without_a_usable_repository_the_guidance_line_says_so_and_never_fails(tmp_path, monkeypatch, plugin_json):
    root = tmp_path / "plugin"
    (root / ".claude-plugin").mkdir(parents=True)
    if plugin_json is not None:
        (root / ".claude-plugin" / "plugin.json").write_text(plugin_json)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
    assert ft.guidance_line() == ("fix-agent-instructions.md and review-briefs.md in the thunderstruck "
                                  "repository (no link could be built)")


def test_a_fork_that_names_its_own_repository_links_there(tmp_path, monkeypatch):
    root = tmp_path / "plugin"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"repository": "https://git.example.com/me/thunderstruck/"}')
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
    assert "(https://git.example.com/me/thunderstruck/blob/main/docs/review-briefs.md)" in ft.guidance_line()


def test_links_built_have_no_reason_and_links_not_built_give_the_one_the_report_recorded():
    assert ft.links_reason({"links": {"provider": "github"}}) is None
    recorded = "references are not linked: host git.example.com is not recognised; set provider"
    assert ft.links_reason({"links": None, "warnings": ["other"], "run_warnings": ["x", recorded]}) == recorded
    assert ft.links_reason({"links": None, "warnings": [recorded], "run_warnings": []}) == recorded
    assert "enabled = false" in ft.links_reason({"links": None, "warnings": [], "run_warnings": []})


@pytest.mark.parametrize("ev, linked, fragment", [
    ({"type": "code", "ref": "src/a.ts:1", "url": "https://h.example/a#L1"}, True, None),
    ({"type": "catalog", "ref": "dependencyOf component:default/web", "url": None}, True,
     "not linked: catalog data has no source location"),
    ({"type": "dependency", "ref": "pypi:requests@2.0:requests/api.py:5", "url": None}, True,
     "not linked: a dependency's source is not in this repository"),
    ({"type": "commit", "ref": "abc1234", "url": None}, True, "not linked: commit not found in this repository"),
    ({"type": "code", "ref": "src/a.ts:1", "url": None}, True, "not linked: no link could be built"),
    ({"type": "code", "ref": "src/a.ts:1", "url": None}, False, "not linked: links could not be built (see Header)"),
    ({"type": "catalog", "ref": "dependencyOf x", "url": None}, False, "not linked: catalog data has no source location")])
def test_a_reference_is_linked_or_labelled_never_bare(ev, linked, fragment):
    line = ft.evidence_line({"note": "n", **ev}, linked)
    if fragment is None:
        assert "not linked" not in line and "](https://h.example/a#L1)" in line
    else:
        assert f"({fragment})" in line and "](" not in line


# --- Task 6: the ticket -----------------------------------------------------

HEADINGS = ["Header", "Summary", "Trigger", "Mechanism", "Persistence", "Blast radius",
            "Implicit guarantees at risk", "Evidence status", "Assumptions and open questions",
            "Reproduce", "Detection", "Fix options", "Acceptance criteria", "Out of scope",
            "Rollout and rollback", "Provenance", "Disclaimer"]


def run_main(capsys, repo, *args):
    try:
        code = ft.main(["--repo", str(repo), *args])
    except SystemExit as stopped:
        code = stopped.code
    out = capsys.readouterr()
    return code, out.out, out.err


def ticket_path(repo, key=KEY):
    return repo / ".thunderstruck" / "tickets" / f"{key}.md"


def made(tmp_path, capsys, *args, finding=None, **report):
    """A repository, its report, and the ticket made from it."""
    repo = make_repo(tmp_path)
    make_report(repo, [finding or make_finding(repo)], **report)
    code, out, err = run_main(capsys, repo, "--key", KEY, *args)
    assert code == 0, err
    return repo, ticket_path(repo).read_text()


def section(text, heading):
    return text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


@pytest.mark.parametrize("failure, title", [
    ("Retries stack", "Retries stack"),
    ("  two\nlines  and   gaps ", "two lines and gaps"),
    ("word " * 40, ("word " * 19).rstrip() + " word…"),
    ("x" * 150, "x" * 100 + "…"),
    ("", "(no failure mode)"), (None, "(no failure mode)")])
def test_the_title_is_the_failure_mode_on_one_short_line(failure, title):
    assert ft.title({"failure_mode": failure}) == title
    assert len(ft.title({"failure_mode": failure})) <= 101


def test_every_section_is_there_in_the_tickets_order(tmp_path, capsys):
    _, text = made(tmp_path, capsys)
    assert text.startswith("# Retries stack and one blip becomes a storm\n")
    assert [l[3:] for l in text.splitlines() if l.startswith("## ")] == HEADINGS
    assert ft.SECTIONS_HEADINGS == tuple(HEADINGS)
    assert text.endswith("\n") and not text.endswith("\n\n") and "\r" not in text


def test_each_section_comes_from_its_field(tmp_path, capsys):
    repo, text = made(tmp_path, capsys)
    header = section(text, "Header")
    assert "- **Location** — [`src/releases.ts:3-5`](" in header and "`fetchRelease`" in header
    assert "- **Confidence** — medium (claimed high)" in header
    assert "- **Check status** — unchecked" in header and "- **Status** — Hypothesis" in header
    assert f"- **Key** — `{KEY}`" in header and "- **Scan date** — 2025-01-06" in header
    assert "- **Links** — built from the repository's link settings" in header
    assert "**Failure mode** — Retries stack and one blip becomes a storm" in section(text, "Summary")
    assert "**Prediction** — The next incident is a retry storm" in section(text, "Summary")
    assert "**Trigger** — The upstream answers 503 for more than two seconds" in section(text, "Trigger")
    assert "**Preconditions** — none: the failure happens on default settings." in section(text, "Trigger")
    mechanism = section(text, "Mechanism")
    assert "**Amplifier** — Two layers retry" in mechanism
    assert mechanism.count("### Step ") == 2 and "What to notice: the loop" in mechanism
    assert "**Sustaining effect** — Every client waits the same time" in section(text, "Persistence")
    blast = section(text, "Blast radius")
    assert "**Summary** — Every release lookup" in blast and "**Traced impact**" in blast
    assert "**Inferred impact**" in blast and "Lookups wait on the loop" in blast
    assert "One blip never reaches the caller" in section(text, "Implicit guarantees at risk")
    assert "**Check** — unchecked." in section(text, "Evidence status")
    assert "Whether callers retry again — how to check: Read the callers" in section(text, "Assumptions and open questions")
    assert "**Why this confidence** — Both layers are visible" in section(text, "Assumptions and open questions")
    assert "**Verify** — Stub a 503 and count the requests" in section(text, "Reproduce")
    assert "No reproduction is recorded for this finding." in section(text, "Reproduce")


def test_a_section_with_no_data_says_not_assessed_and_why(tmp_path, capsys):
    repo = make_repo(tmp_path)
    f = make_finding(repo)
    for field in ("amplifier", "sustaining_effect", "prediction"):
        del f[field]
    make_report(repo, [f])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text()
    assert "**Amplifier** — not stated." in section(text, "Mechanism")
    assert ("Not assessed: the finding states no sustaining effect; it is given only when the code "
            "shows one.") in section(text, "Persistence")
    assert "Prediction" not in section(text, "Summary")
    assert ("Not assessed: a finding records no detection signal (the log line, metric or alert "
            "that would show the failure).") in section(text, "Detection")
    for heading in ("Fix options", "Acceptance criteria", "Out of scope", "Rollout and rollback"):
        assert ("Not assessed: no proposal was drafted for this section; a finding records none and "
                "the plugin proposes none.") in section(text, heading)


def test_a_finding_without_the_impact_fields_reads_not_assessed(tmp_path, capsys):
    repo = make_repo(tmp_path)
    f = make_finding(repo)
    for field in ("blast_items", "not_checked", "implicit_guarantees"):
        del f[field]
    make_report(repo, [f])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text()
    sentence = c.IMPACT_SENTENCES["not_assessed"]
    assert sentence in section(text, "Blast radius")
    assert sentence in section(text, "Implicit guarantees at risk")
    assert sentence in section(text, "Assumptions and open questions")


def test_a_code_free_finding_has_no_steps_and_says_so(tmp_path, capsys):
    repo = make_repo(tmp_path)
    f = make_finding(repo, evidence=[{"type": "catalog", "ref": "dependencyOf x", "note": "k", "url": None}],
                     blast_items=[], implicit_guarantees=[])
    make_report(repo, [f])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    assert "Not assessed: the finding cites no code." in section(ticket_path(repo).read_text(), "Mechanism")


def test_steps_beyond_the_cap_are_counted_in_the_mechanism(tmp_path, capsys):
    repo = make_repo(tmp_path)
    evidence = [{"type": "code", "ref": f"src/releases.ts:{n}", "note": str(n), "url": None} for n in range(1, 15)]
    make_report(repo, [make_finding(repo, evidence=evidence, blast_items=[], implicit_guarantees=[])])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    mechanism = section(ticket_path(repo).read_text(), "Mechanism")
    assert mechanism.count("### Step ") == 12
    assert "2 further code references are listed under Evidence status." in mechanism


def test_the_status_flag_is_the_status_and_hypothesis_is_the_default(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    assert "- **Status** — Hypothesis" in ticket_path(repo).read_text()
    assert run_main(capsys, repo, "--key", KEY, "--status", "fix-proposed")[0] == 0
    assert "- **Status** — Fix proposed" in ticket_path(repo).read_text()


def test_reproduced_is_refused_and_writes_nothing(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    code, out, err = run_main(capsys, repo, "--key", KEY, "--status", "Reproduced")
    assert code == 2 and "Reproduced refused" in err and "#103" in err and out == ""
    assert not (repo / ".thunderstruck" / "tickets").exists()


def test_a_stop_writes_nothing_and_leaves_an_earlier_ticket_alone(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    before = ticket_path(repo).read_bytes()
    (repo / "src/releases.ts").write_text("edited\n")
    code, out, err = run_main(capsys, repo, "--key", KEY)
    assert code == 2 and "src/releases.ts" in err and "differs from the scanned commit" in err
    assert "git switch --detach" in err and out == ""
    assert ticket_path(repo).read_bytes() == before
    fresh = tmp_path / "fresh"
    fresh_repo = make_repo(fresh)
    make_report(fresh_repo)
    (fresh_repo / "src/api.ts").write_text("edited\n")
    assert run_main(capsys, fresh_repo, "--key", KEY)[0] == 2
    assert not (fresh_repo / ".thunderstruck" / "tickets").exists()


def test_a_wrong_key_and_a_missing_report_are_named_stops(tmp_path, capsys):
    repo = make_repo(tmp_path)
    code, _, err = run_main(capsys, repo, "--key", KEY)
    assert code == 2 and "no report.json" in err
    make_report(repo)
    code, _, err = run_main(capsys, repo, "--key", "0" * 12)
    assert code == 2 and "no finding with key" in err and KEY in err
    code, _, err = run_main(capsys, repo, "--key", "../../x")
    assert code == 2 and "12 lowercase hex" in err
    assert not (repo / ".thunderstruck" / "tickets").exists()


def test_the_list_prints_every_finding_and_writes_nothing(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    code, out, _ = run_main(capsys, repo, "--list")
    assert code == 0 and out.startswith(f"{KEY} · FR-001 · src/releases.ts:3-5 · Retries stack")
    assert not (repo / ".thunderstruck" / "tickets").exists()


def test_exactly_one_of_key_and_list(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    for args in ([], ["--key", KEY, "--list"]):
        with pytest.raises(SystemExit) as stopped:
            ft.main(["--repo", str(repo), *args])
        assert stopped.value.code == 2
    capsys.readouterr()


def test_generating_twice_is_byte_identical_from_anywhere(tmp_path, capsys, monkeypatch):
    repo = make_repo(tmp_path)
    make_report(repo)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    first = ticket_path(repo).read_bytes()
    monkeypatch.chdir(tmp_path)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    assert ticket_path(repo).read_bytes() == first
    other = tmp_path / "copy"
    import shutil
    shutil.copytree(repo, other, symlinks=True)
    rep = json.loads((other / ".thunderstruck" / "report.json").read_text())
    rep["generated_at"] = "2000-01-01T00:00:00+00:00"          # a rebuild of the same scan
    rep["repo"]["root"] = str(other)
    (other / ".thunderstruck" / "report.json").write_text(json.dumps(rep))
    assert run_main(capsys, other, "--key", KEY)[0] == 0
    assert ticket_path(other).read_bytes() == first


def test_drafted_sections_appear_labelled_and_in_provenance(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    path = repo / ".thunderstruck" / "tickets" / f"{KEY}.sections.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(SECTIONS_OK))
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text()
    label = "**Proposal, not verified** — drafted by a model from this finding. Nothing checked it."
    fix = section(text, "Fix options")
    assert label in fix and "- Cap the loop at one attempt." in fix
    assert "- A 503 is retried at most twice." in section(text, "Acceptance criteria")
    assert "Not assessed: no proposal was drafted" in section(text, "Out of scope")
    provenance = section(text, "Provenance")
    assert "Proposals: Fix options, Acceptance criteria drafted by a model" in provenance
    assert hashlib.sha256(path.read_bytes()).hexdigest() in provenance


def test_a_bad_drafts_file_never_fails_the_ticket(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    path = repo / ".thunderstruck" / "tickets" / f"{KEY}.sections.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({**SECTIONS_OK, "scanned_at": "2020-01-01T00:00:00+00:00"}))
    code, _, err = run_main(capsys, repo, "--key", KEY)
    assert code == 0 and err == ""
    text = ticket_path(repo).read_text()
    assert ("Not assessed: the draft for this section was not used: it was written for another "
            "finding or an earlier scan.") in section(text, "Fix options")
    assert "The drafts file was not used: it was written for another finding or an earlier scan." in section(text, "Provenance")
    assert "Proposal, not verified" not in text and "Proposals: none drafted." in text


def test_the_guidance_is_linked_under_fix_options_and_acceptance_criteria_only(tmp_path, capsys):
    _, text = made(tmp_path, capsys)
    line = ft.guidance_line()
    assert line in section(text, "Fix options") and line in section(text, "Acceptance criteria")
    assert text.count(line) == 2                        # nowhere else


def test_links_come_from_the_report_and_are_stated_once_in_the_header(tmp_path, capsys):
    repo, text = made(tmp_path, capsys)
    sha = head_of(repo)
    assert f"({BASE}/blob/{sha}/src/releases.ts#L3-L5)" in text
    assert f"({BASE}/blob/{sha}/src/api.ts#L1)" in text
    assert "(not linked: catalog data has no source location)" in text
    assert "Links** — not built" not in text


def test_without_links_the_ticket_says_why_with_the_reason_the_report_recorded(tmp_path, capsys):
    reason = "references are not linked: host git.example.com is not recognised; set provider"
    repo = make_repo(tmp_path)
    f = make_finding(repo)
    make_report(repo, [f], links=False, run_warnings=[reason], warnings=[reason])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text()
    assert "- **Links** — Not built. The report records: references are not linked: host `git.example.com`" in section(text, "Header")
    assert "](https://github.example.com" not in text.split("## Disclaimer")[0].replace(ft.guidance_line(), "")
    assert "(not linked: links could not be built (see Header))" in text
    assert "[`src/releases.ts:3-5`]" not in text and "`src/releases.ts:3-5`" in text


def test_a_disabled_link_setting_has_a_reason_too(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo, [make_finding(repo)], links=False)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    assert "disabled in the repository's link settings (enabled = false)" in ticket_path(repo).read_text()


def test_nothing_machine_specific_reaches_the_ticket(tmp_path, capsys):
    repo = make_repo(tmp_path)
    f = make_finding(repo, failure_mode=f"Fails in {repo}/src/releases.ts and {repo}",
                     confidence_rationale=f"Read {repo}/src/api.ts")
    make_report(repo, [f])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text()
    assert "<repo>/src/releases.ts" in text and "<repo>/src/api.ts" in text
    for value in (str(repo), str(tmp_path), "alice/feature", "2099-01-01"):
        assert value not in text, value


def test_the_provenance_and_the_disclaimer(tmp_path, capsys):
    repo, text = made(tmp_path, capsys)
    provenance = section(text, "Provenance")
    assert f"- Generated by thunderstruck from a scan of commit `{head_of(repo)}` at `{SCANNED_AT}`." in provenance
    assert f"- Finding `{KEY}` · hotspot H01 · report schema `thunderstruck.report/v2`." in provenance
    assert "- Verification did not run for this scan." in provenance
    assert "- Proposals: none drafted." in provenance
    disclaimer = section(text, "Disclaimer")
    assert "hypothesis" in disclaimer and "not a confirmed defect" in disclaimer and "not verified" in disclaimer


def test_a_symlinked_output_folder_is_refused(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".thunderstruck" / "tickets").symlink_to(outside)
    code, _, err = run_main(capsys, repo, "--key", KEY)
    assert code == 2 and "symbolic link" in err and list(outside.iterdir()) == []


def test_the_script_runs_as_a_program(tmp_path):
    repo = make_repo(tmp_path)
    make_report(repo)
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "finding_ticket.py"), "--repo", str(repo),
                           "--key", KEY], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == (f"ticket for {KEY}: .thunderstruck/tickets/{KEY}.md "
                                   "(5 sections not assessed, 0 drafted)")


def _wide_finding(repo, n=12):
    return make_finding(repo, location={"file": "src/f0.ts", "lines": "1-40", "url": None},
                        evidence=[{"type": "code", "ref": f"src/f{k}.ts:1-40", "note": f"step {k}", "url": None}
                                  for k in range(n)], blast_items=[], implicit_guarantees=[])


def _wide_repo(tmp_path, n=12):
    rows = "".join("w" * 239 + "\n" for _ in range(40))                   # a step of 9,600 characters
    return make_repo(tmp_path, {f"src/f{k}.ts": rows for k in range(n)})


def test_a_ticket_too_long_for_a_tracker_drops_steps_from_the_end_and_says_so(tmp_path, capsys):
    repo = _wide_repo(tmp_path)
    make_report(repo, [_wide_finding(repo)])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text(encoding="utf-8")
    steps = text.count("### Step ")
    assert len(text.encode("utf-8")) <= ft.MAX_TICKET_BYTES == 60_000 and 1 <= steps < 12
    assert text.index("What to notice: step 0") < text.index("### Step 2")           # the first steps are the ones kept
    assert f"What to notice: step {steps}" not in text
    dropped = 12 - steps
    assert (f"{dropped} further steps are left out so that the ticket fits a tracker (at most 60,000 "
            "bytes); the code references are listed under Evidence status.") in section(text, "Mechanism")
    assert text.count("- _code_ ") == 12                                             # every reference is still listed


def test_the_tracker_limit_and_its_margin_are_named_constants():
    assert ft.TRACKER_BODY_LIMIT == 65_536 and ft.MAX_TICKET_BYTES == ft.TRACKER_BODY_LIMIT - ft.TICKET_MARGIN
    assert ft.MAX_TICKET_BYTES < ft.TRACKER_BODY_LIMIT


def test_a_ticket_that_exactly_fits_keeps_every_step_and_one_over_drops_one(tmp_path, capsys, monkeypatch):
    repo = make_repo(tmp_path)
    make_report(repo)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    full = len(ticket_path(repo).read_bytes())
    monkeypatch.setattr(ft, "MAX_TICKET_BYTES", full)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    assert ticket_path(repo).read_text().count("### Step ") == 2
    monkeypatch.setattr(ft, "MAX_TICKET_BYTES", full - 1)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text()
    assert text.count("### Step ") == 1 and "1 further step is left out so that the ticket fits" in text


def test_a_ticket_too_long_even_without_steps_is_a_named_stop_not_a_cut(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo, [make_finding(repo, failure_mode="word " * 14_000)])
    code, out, err = run_main(capsys, repo, "--key", KEY)
    assert code == 2 and "even without a code step" in err and "60,000 bytes" in err and out == ""
    assert not (repo / ".thunderstruck" / "tickets").exists()


def test_the_cap_counts_bytes_so_multibyte_text_drops_steps_a_character_count_would_keep(tmp_path, capsys, monkeypatch):
    rows = "".join("\u20ac" * 45 + "\U0001d11e" * 45 + "\n" for _ in range(40))    # 3- and 4-byte characters
    repo = make_repo(tmp_path, {f"src/f{k}.ts": rows for k in range(12)})
    make_report(repo, [_wide_finding(repo)])
    with monkeypatch.context() as patch:                              # the whole ticket, with no cap
        patch.setattr(ft, "MAX_TICKET_BYTES", 10 ** 9)
        assert run_main(capsys, repo, "--key", KEY)[0] == 0
    full = ticket_path(repo).read_text(encoding="utf-8")
    assert len(full) < ft.MAX_TICKET_BYTES < len(full.encode("utf-8"))        # under by characters, over by bytes
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text(encoding="utf-8")
    steps = text.count("### Step ")
    assert 1 <= steps < 12 and len(text.encode("utf-8")) <= ft.MAX_TICKET_BYTES
    assert f"{12 - steps} further steps are left out" in section(text, "Mechanism")


def test_a_link_planted_at_the_old_temporary_name_is_not_written_through(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    tickets = repo / ".thunderstruck" / "tickets"
    tickets.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    (tickets / f"{KEY}.md.tmp").symlink_to(victim)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    assert victim.read_text() == "keep me" and ticket_path(repo).is_file()


def test_a_link_planted_at_the_temporary_name_is_refused(tmp_path, capsys, monkeypatch):
    repo = make_repo(tmp_path)
    make_report(repo)
    tickets = repo / ".thunderstruck" / "tickets"
    tickets.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    monkeypatch.setattr(ft.secrets, "token_hex", lambda n: "0" * 16)
    (tickets / f".{KEY}.{'0' * 16}.tmp").symlink_to(victim)
    code, _, err = run_main(capsys, repo, "--key", KEY)
    assert code == 2 and "could not create a temporary file" in err
    assert victim.read_text() == "keep me" and not ticket_path(repo).exists()


def test_a_ticket_file_that_is_a_link_is_replaced_and_never_followed(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo)
    tickets = repo / ".thunderstruck" / "tickets"
    tickets.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    ticket_path(repo).symlink_to(victim)
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    assert victim.read_text() == "keep me" and not ticket_path(repo).is_symlink()
    assert ticket_path(repo).read_text().startswith("# ")
    assert [p.name for p in tickets.iterdir()] == [f"{KEY}.md"]                       # no temporary file is left


MACHINE = ("/home/alice", "alice", "devbox-17.example.com")


def _plain(text):
    """The ticket's words with the escapes and code-span marks of mdtext taken out."""
    return __import__("re").sub(r"[`\\]", "", text)


def test_the_machine_that_ran_the_scan_is_scrubbed_from_every_text(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ft, "machine_values", lambda: MACHINE)
    repo = make_repo(tmp_path)
    f = make_finding(repo, failure_mode="Reads /home/alice/.npmrc as alice on devbox-17.example.com",
                     confidence_rationale="alice@devbox-17 saw it; the short name devbox-17 is the same host",
                     how_to_verify="Run it from /home/alice/work/other")
    make_report(repo, [f])
    path = ft.sections_path(repo, KEY)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({**SECTIONS_OK, "sections": {"fix_options": ["Edit /home/alice/.npmrc"]}}))
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = _plain(ticket_path(repo).read_text())
    assert "<home>/.npmrc as <user> on <host>" in text
    assert "<user>@<host> saw it; the short name <host> is the same host" in text
    assert "Run it from <home>/work/other" in text and "- Edit <home>/.npmrc" in text
    for value in ("/home/alice", "alice", "devbox-17"):
        assert value not in text, value


def test_a_path_that_is_the_repositorys_own_content_stays_verbatim(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ft, "machine_values", lambda: MACHINE)
    repo = make_repo(tmp_path, {"src/alice/util.ts": "const cache = '/home/alice/build'; // alice\n",
                                "src/api.ts": "x\n"})
    f = make_finding(repo, location={"file": "src/alice/util.ts", "lines": "1", "url": None},
                     evidence=[{"type": "code", "ref": "src/alice/util.ts:1", "note": "alice's cache", "url": None}],
                     blast_items=[], implicit_guarantees=[])
    make_report(repo, [f])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text()
    assert "const cache = '/home/alice/build'; // alice" in text                       # the snippet
    assert "[`src/alice/util.ts:1`](" in section(text, "Header")                      # the file's own path
    assert "What to notice: <user>'s cache" in _plain(text)                           # the model's note


def test_a_generic_account_name_is_not_a_machine_value(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ft, "machine_values", lambda: ("/root", "root", "ci"))
    repo = make_repo(tmp_path)
    make_report(repo, [make_finding(repo, failure_mode="The root cause is in /root/.cache, run as root")])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    assert "The root cause is in <home>/.cache, run as root" in _plain(ticket_path(repo).read_text())


def test_the_real_machine_values_are_read_from_the_machine():
    home, user, host = ft.machine_values()
    assert home == str(Path.home())
    assert user is None or isinstance(user, str)
    import socket
    assert host == socket.gethostname()


def test_reproduced_is_refused_before_the_code_is_checked(tmp_path, capsys, monkeypatch):
    """The refusal comes once the report is read and the key found, and before anything looks at
    the cited files: only `git rev-parse` has run (to find the repository)."""
    repo = make_repo(tmp_path)
    make_report(repo)
    (repo / "src/releases.ts").write_text("edited\n")              # a stop, if the code were checked

    def checked(*args, **kwargs):
        raise AssertionError("the code was checked before the status was refused")
    monkeypatch.setattr(ft, "check_snapshot", checked)
    monkeypatch.setattr(links, "stale_paths", checked)
    code, _, err = run_main(capsys, repo, "--key", KEY, "--status", "Reproduced")
    assert code == 2 and "Reproduced refused" in err and "the code it cites" not in err


def test_the_settings_the_failure_needs_appear_under_trigger_each_confirmed_or_unconfirmed(tmp_path, capsys):
    repo = make_repo(tmp_path)
    needs = {"default_ref": "src/api.ts:1", "documented": "no", "default_url": None, "doc_url": None}
    preconditions = [
        {"setting": "API_RETRY_ON_429", "default": "false", "needs": "changed", "value": "true", **needs,
         "confirmation": c.confirm(None, {"found": "same"})},
        {"setting": "sync.pageSize", "default": "100", "needs": "default", **needs,
         "confirmation": c.confirm(None, {"found": "different"})}]
    make_report(repo, [make_finding(repo, preconditions=preconditions, gate="unconfirmed_default")])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    trigger = section(ticket_path(repo).read_text(), "Trigger")
    assert "This failure relies on a doubtful default." in trigger
    assert "`API_RETRY_ON_429` set to `true`; default `false`" in trigger and "`sync.pageSize` left at its default `100`" in trigger
    assert "**Confirmed**: a check found this default registered, and it agrees" in trigger
    assert "**Unconfirmed**: a check found a different default registered" in trigger


# --- Task 7: hostile text stays inert ---------------------------------------
# The inert-text test of #28 covers report.md only, so the ticket has its own: the same two
# engines, with `pre` allowed for a snippet and no other block or link the text could add.

from test_inert_report import HOSTILE, _hrefs

STEERING = "/close #12 !7 ABC-123 acme/api#12 PR#7 group/proj!3 a1b2c3d @alice <details>x</details>"
BAD = f"{HOSTILE} {STEERING}"
STRUCTURE = ("h1", "h2", "h3", "p", "pre", "ul", "li", "a", "img", "table", "tr", "td", "th", "blockquote",
             "hr", "script", "details", "b", "i", "ol", "div", "span")


def _structure(markdown, renderer):
    return [t for t in renderer(markdown).tags if t in STRUCTURE or t not in ("code", "strong", "em", "br", "sub")]


def _outside_fences(text):
    keep, inside = [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            inside = not inside
        elif not inside:
            keep.append(line)
    return "\n".join(keep)


def _model_fields(word):
    return dict(
        failure_mode=f"failure {word}", trigger_condition=f"trigger {word}", amplifier=f"amplifier {word}",
        sustaining_effect=f"sustaining {word}", blast_radius=f"blast {word}",
        blast_items=[{"claim": f"claim {word}", "basis": "traced", "evidence": [0]},
                     {"claim": f"inferred {word}", "basis": "assumption"}],
        not_checked=[{"item": f"item {word}", "how_to_check": f"how {word}"}],
        implicit_guarantees=[{"guarantee": f"guarantee {word}", "removed_by": f"removed {word}",
                              "evidence": [0]}],
        confidence_rationale=f"rationale {word}", how_to_verify=f"verify {word}", prediction=f"prediction {word}",
        preconditions=[{"setting": f"S {word}", "default": f"D {word}", "default_ref": "src/api.ts:1", "needs": "changed",
                        "value": f"V {word}", "documented": "no", "default_url": None, "doc_url": None}],
        check={"status": "narrowed", "by": "skeptic", "reason": f"reason {word}", "holds": f"holds {word}"})


def _hostile_ticket(tmp_path, capsys, word):
    """(markdown, benign markdown) for one repository whose code, model fields and drafts say `word`."""
    results = []
    for label, text in (("hostile", word), ("benign", "plain words")):
        # the benign file has the same shape (a long line, a control character): the same notes
        lines = HOSTILE_LINES if label == "hostile" else ["plain" if len(l) < 99 else "p" * 5000 for l in HOSTILE_LINES[:-1]] + ["a \x1b b"]
        repo = make_repo(tmp_path / label, {"src/releases.ts": "\n".join(lines) + "\n",
                                           "src/api.ts": "export const api = 1;\n"})
        finding = make_finding(repo, location={"file": "src/releases.ts", "symbol": f"sym {text}", "lines": "1-10", "url": None},
                               evidence=[{"type": "code", "ref": f"src/releases.ts:1-{len(HOSTILE_LINES)}",
                                          "note": f"note {text}", "url": None},
                                         {"type": "code", "ref": "src/api.ts:1", "note": f"note {text}", "url": None}],
                               **_model_fields(text))
        make_report(repo, [finding])
        drafts = {"schema": "thunderstruck.ticket-sections/v1", "key": KEY, "scanned_at": SCANNED_AT,
                  "sections": {sid: [f"draft {text}", f"another {text}"] for sid, _ in ft.JUDGEMENT}}
        path = ft.sections_path(repo, KEY)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(drafts))
        assert run_main(capsys, repo, "--key", KEY)[0] == 0
        results.append(ticket_path(repo).read_text())
    return results


def _assert_inert(tmp_path, capsys, word=BAD):
    text, benign = _hostile_ticket(tmp_path, capsys, word)
    for renderer in RENDERERS:
        assert _structure(text, renderer) == _structure(benign, renderer), renderer.__name__
        html = renderer(text)
        assert "img" not in html.tags and "script" not in html.tags and "details" not in html.tags
        assert html.tags.count("h1") == 1 and html.tags.count("h2") == len(HEADINGS)
        assert html.tags.count("pre") == 2
    allowed = (BASE + "/", ft.plugin_repository() + "/")
    hrefs = _hrefs(text)
    assert hrefs and all(h.startswith(allowed) for h in hrefs), hrefs
    prose = _outside_fences(text)
    for token in ("#12", "!7", "ABC-123", "acme/api#12", "PR#7", "group/proj!3", "a1b2c3d", "@alice", "evil.example"):
        for m in __import__("re").finditer(__import__("re").escape(token), prose):
            before = prose[:m.start()]
            assert before.count("`") % 2 == 1 or before.endswith("("), (token, prose[max(0, m.start() - 40):m.end() + 20])
    assert not [l for l in prose.split("\n") if l[:1] in ("/", "@", "!", ">", "|")], "a line starts like a command or a quote"
    return text


def test_hostile_text_in_every_field_the_code_and_the_drafts_stays_inert(tmp_path, capsys):
    text = _assert_inert(tmp_path, capsys)
    assert "fake heading" in text and "fake item" in text


def test_every_defence_is_needed_the_hostile_test_fails_without_it(tmp_path, capsys, monkeypatch):
    import re
    defences = {
        "the fence is longer than any run inside": ("verbatim", lambda lines: ("```\n" + "\n".join(lines) + "\n```", 0)),
        "model text goes through mdtext.text": ("text", lambda value, cell=False, heading=False: str(value)),
    }
    for name, (attr, naive) in defences.items():
        with monkeypatch.context() as patch:
            patch.setattr(mdtext, attr, naive)
            with pytest.raises(AssertionError):
                _assert_inert(tmp_path / re.sub(r"\W", "", name), capsys)
    with monkeypatch.context() as patch:           # tracker references: the pattern before #108
        patch.setattr(mdtext, "_LINKISH", re.compile(r"://|//|www\.|mailto:|xmpp:|@|\.[^\W\d_]{2}", re.I))
        with pytest.raises(AssertionError):
            _assert_inert(tmp_path / "refs", capsys)


def test_a_hand_edited_report_cannot_plant_a_link_or_break_one(tmp_path, capsys):
    repo = make_repo(tmp_path)
    f = make_finding(repo)
    f["location"]["url"] = "javascript:alert(1)"
    f["evidence"][0]["url"] = "https://x.example/a) [click](https://evil.example"
    f["evidence"][1]["url"] = "https://x.example/ok"
    make_report(repo, [f])
    assert run_main(capsys, repo, "--key", KEY)[0] == 0
    text = ticket_path(repo).read_text()
    assert "javascript:" not in text and "evil.example" not in text
    assert "[`src/api.ts:1`](https://x.example/ok)" in text
    assert all(h.startswith(("https://x.example/ok", ft.plugin_repository())) for h in _hrefs(text))


def test_a_hostile_key_never_becomes_a_path(tmp_path, capsys):
    repo = make_repo(tmp_path)
    make_report(repo, [make_finding(repo, key="../../escape")])
    code, _, err = run_main(capsys, repo, "--key", "../../escape")
    assert code == 2 and "12 lowercase hex" in err
    assert not (repo / ".thunderstruck" / "tickets").exists() and not (tmp_path / "escape.md").exists()


def test_the_ticket_names_no_machine_value_on_the_real_fixture_either(tmp_path, capsys):
    import getpass
    import re
    _, text = made(tmp_path, capsys)
    for value in (str(tmp_path), str(Path.home()), getpass.getuser() + "/"):
        assert value not in text, value
    assert not re.search(r"(?<![\w.:/-])/(?:tmp|home|Users|root|var)/", text)
