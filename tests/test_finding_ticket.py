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
