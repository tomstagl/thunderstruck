"""#56: confidence that means the claim was checked, preconditions, and the
history signal, from the rule tables to every output."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent


# --- Task 1 -----------------------------------------------------------------
TABLE = {
    ("high", "unchecked"): "medium", ("high", "upheld"): "high", ("high", "narrowed"): "medium",
    ("high", "inconclusive"): "medium", ("high", "refuted"): "low",
    ("medium", "unchecked"): "medium", ("medium", "upheld"): "medium", ("medium", "narrowed"): "low",
    ("medium", "inconclusive"): "medium", ("medium", "refuted"): "low",
    ("low", "unchecked"): "low", ("low", "upheld"): "low", ("low", "narrowed"): "low",
    ("low", "inconclusive"): "low", ("low", "refuted"): "low",
}


@pytest.mark.parametrize("claimed, status", sorted(TABLE))
def test_effective_confidence_table(claimed, status):
    assert c.effective_confidence(claimed, status) == TABLE[(claimed, status)]


def test_only_upheld_can_be_high():
    assert {s for s in c.CHECK_STATUSES if c.effective_confidence("high", s) == "high"} == {"upheld"}


def test_an_unknown_status_counts_as_unchecked_and_an_unknown_claim_as_low():
    assert c.effective_confidence("high", "probably") == "medium"
    assert c.effective_confidence("certain", "upheld") == "low"
    assert c.effective_confidence(None, "unchecked") == "low"


@pytest.mark.parametrize("finding, expected", [
    ({}, "unchecked"),
    ({"check": None}, "unchecked"),
    ({"check": "upheld"}, "unchecked"),
    ({"check": {"status": "maybe"}}, "unchecked"),
    *[({"check": {"status": s}}, s) for s in ("unchecked", "upheld", "narrowed", "inconclusive", "refuted")],
])
def test_check_status(finding, expected):
    assert c.check_status(finding) == expected


@pytest.mark.parametrize("preconditions, gate", [
    ([], "none"),
    (None, "none"),
    ([{"needs": "default"}, {"needs": "default"}], "none"),
    ([{"needs": "default"}, {"needs": "changed"}], "non_default_setting"),
    (["not an object", {"needs": "changed"}], "non_default_setting"),
])
def test_finding_gate(preconditions, gate):
    assert c.finding_gate({"preconditions": preconditions}) == gate


def test_vocabularies_are_the_spec_spelling():
    assert c.CHECK_STATUSES == ("unchecked", "upheld", "narrowed", "inconclusive", "refuted")
    assert c.COMMIT_ROLES == ("introduced", "fixed", "mitigated", "changed")
    assert c.PRECONDITION_NEEDS == ("changed", "default")
    assert c.DOCUMENTED == ("yes", "no", "not_checked")
    assert c.GATES == ("none", "non_default_setting")
    assert set(c.CHECK_SENTENCES) == set(c.CHECK_STATUSES)
    assert set(c.GATE_MARKERS) == set(c.GATES) - {"none"}


# --- Task 2 -----------------------------------------------------------------
import bundle  # noqa: E402
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding  # noqa: E402
from test_validate_paths import _doc, _git, _validator, repo  # noqa: E402,F401

FORMAT = "src/util/format.ts"
RELEASES = "src/client/releases.ts"
_DROP = object()


def _pre(**over) -> dict:
    p = {"setting": "RETRY_ON_429", "default": "false", "default_ref": "src/a.ts:1",
         "needs": "changed", "value": "true", "documented": "no", "doc_ref": None}
    p.update(over)
    return {k: v for k, v in p.items() if v is not _DROP}


def _errors(repo, *items) -> list[str]:
    doc = _doc("src/a.ts")
    doc["findings"][0]["preconditions"] = list(items)
    return _validator(repo).check_document(doc)


def test_complete_preconditions_pass(repo):
    assert _errors(repo) == []
    assert _errors(repo, _pre()) == []
    assert _errors(repo, _pre(needs="default", value=_DROP, documented="yes",
                              doc_ref="src/a.ts:2-3")) == []


@pytest.mark.parametrize("over, fragment", [
    ({"setting": ""}, "preconditions[0].setting must be a non-empty string"),
    ({"default": None}, "preconditions[0].default must be a non-empty string"),
    ({"default_ref": "src/a.ts:99"}, "that line does not exist"),
    ({"default_ref": "src/new.ts:1"}, "not tracked by git"),
    ({"default_ref": "/etc/hostname:1"}, "is absolute"),
    ({"default_ref": "src/a.ts"}, "is not path:line"),
    ({"default_ref": _DROP}, "preconditions[0].default_ref must be one string"),
    ({"needs": "maybe"}, "needs 'maybe' is not one of"),
    ({"value": None}, "value must name the value the failure needs"),
    ({"needs": "default"}, "value must be absent or null"),
    ({"documented": True}, "documented True is not one of"),
    ({"documented": "yes"}, "preconditions[0].doc_ref must be one string"),
    ({"documented": "no", "doc_ref": "src/a.ts:2"}, 'doc_ref is only given when documented is "yes"'),
    ({"confirmation": {"state": "confirmed"}}, "unknown key(s) ['confirmation']"),
])
def test_each_precondition_rule(repo, over, fragment):
    errors = _errors(repo, _pre(**over))
    assert any(fragment in e for e in errors), errors


def test_a_setting_is_listed_once(repo):
    errors = _errors(repo, _pre(), _pre(setting=" retry_on_429 "))
    assert any("listed twice" in e for e in errors), errors


def test_preconditions_must_be_present_and_a_list(repo):
    doc = _doc("src/a.ts")
    del doc["findings"][0]["preconditions"]
    assert "findings[0].preconditions is missing (it may be [], but the key must be present)" \
        in _validator(repo).check_document(doc)
    doc["findings"][0]["preconditions"] = {"setting": "x"}
    assert any("preconditions must be a list" in e for e in _validator(repo).check_document(doc))


def test_amplifier_and_sustaining_effect_are_optional_but_never_filler(repo):
    doc = _doc("src/a.ts")
    f = doc["findings"][0]
    del f["amplifier"], f["sustaining_effect"]
    assert _validator(repo).check_document(doc) == []
    f["amplifier"] = "  "
    assert any("amplifier must be a non-empty string when present; leave it out" in e
               for e in _validator(repo).check_document(doc))


def _with_commit(repo, role=_DROP, etype="commit") -> list[str]:
    doc = _doc("src/a.ts")
    sha = _git(repo, "rev-parse", "HEAD").strip()[:7]
    item = {"type": etype, "ref": sha if etype == "commit" else "src/a.ts:1", "note": "n"}
    if role is not _DROP:
        item["role"] = role
    doc["findings"][0]["evidence"].append(item)
    return _validator(repo).check_document(doc)


def test_commit_evidence_needs_a_role(repo):
    assert any("role None is not one of" in e for e in _with_commit(repo))
    assert any("role 'blamed' is not one of" in e for e in _with_commit(repo, "blamed"))
    assert _with_commit(repo, "introduced") == []          # init wrote src/a.ts:1
    assert any("role is only given on commit evidence" in e
               for e in _with_commit(repo, "changed", etype="code"))


@pytest.mark.parametrize("check, ok", [
    ({"status": "upheld", "by": "skeptic", "reason": "held", "holds": "all"}, True),
    ({"status": "probably"}, False),
    ("upheld", False),
    ({"status": "unchecked", "reason": 3}, False),
])
def test_an_existing_check_is_validated(repo, check, ok):
    doc = _doc("src/a.ts")
    doc["findings"][0]["check"] = check
    assert (_validator(repo).check_document(doc) == []) is ok


def _sha(repo: Path, rel: str, subject: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "log", "--format=%H %s", "--", rel],
                         capture_output=True, text=True, check=True).stdout
    return next(line.split(" ", 1)[0] for line in out.splitlines()
                if line.split(" ", 1)[1] == subject)


def _fixture_doc(repo: Path, *, file: str, line: int, commits: list[tuple[str, str]],
                 patterns=("S02",), confidence="high"):
    hid, doc = _valid_finding(repo, _hotspots(repo))
    f = doc["findings"][0]
    f["location"] = {"file": file, "symbol": "f", "lines": str(line)}
    f["missing_patterns"] = list(patterns)
    f["confidence"] = confidence
    f["evidence"] = [{"type": "code", "ref": f"{file}:{line}", "note": "the text"}] + [
        {"type": "commit", "ref": sha[:7], "role": role, "note": "history"} for sha, role in commits]
    return hid, doc


def _check(repo, plugin_root, hid, doc):
    _write_finding(repo, hid, doc)
    return _validate(repo, plugin_root)


def test_high_with_only_a_feature_commit_now_passes(scanned_copy, plugin_root):
    sha = _sha(scanned_copy, RELEASES, "feat: add release client")
    hid, doc = _fixture_doc(scanned_copy, file=RELEASES, line=1, commits=[(sha, "changed")])
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 0


def test_introduced_needs_the_commit_that_wrote_the_lines(scanned_copy, plugin_root):
    wrote = _sha(scanned_copy, FORMAT, "feat: add title formatting")
    tidy = _sha(scanned_copy, FORMAT, "refactor: tidy imports")      # touched the file, not line 4
    hid, doc = _fixture_doc(scanned_copy, file=FORMAT, line=4, commits=[(wrote, "introduced")])
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 0
    hid, doc = _fixture_doc(scanned_copy, file=FORMAT, line=4, commits=[(tidy, "introduced")])
    proc = _check(scanned_copy, plugin_root, hid, doc)
    assert proc.returncode == 1
    assert "cited as having introduced the cited code, but it wrote none of the cited lines" in proc.stdout


def test_an_uncommitted_line_is_introduced_by_no_commit(scanned_copy, plugin_root):
    wrote = _sha(scanned_copy, FORMAT, "feat: add title formatting")
    path = scanned_copy / FORMAT
    lines = path.read_text().split("\n")
    lines[3] = " * edited locally"
    path.write_text("\n".join(lines))
    hid, doc = _fixture_doc(scanned_copy, file=FORMAT, line=4, commits=[(wrote, "introduced")])
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 1


def test_validation_writes_check_and_history(scanned_copy, plugin_root):
    feat = _sha(scanned_copy, RELEASES, "feat: add release client")
    fix = _sha(scanned_copy, RELEASES, "fix: timeout again on large releases")
    hid, doc = _fixture_doc(scanned_copy, file=RELEASES, line=1,
                            commits=[(fix, "fixed"), (feat, "introduced"), (fix, "fixed")])
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 0
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    f = saved["findings"][0]
    assert saved["validated_with"] == c.VALIDATION_RULES == 4
    assert f["check"] == {"status": "unchecked", "by": None, "reason": None}
    assert f["confidence"] == "high"                      # the claim is kept as written
    assert f["history"] == [
        {"sha": fix[:7], "class": "fix", "role": "fixed", "wrote_cited_line": False},
        {"sha": feat[:7], "class": "feature", "role": "introduced", "wrote_cited_line": True},
    ]


def test_validation_keeps_an_existing_check(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    doc["findings"][0]["check"] = {"status": "upheld", "by": "skeptic", "reason": "held"}
    assert _check(scanned_copy, plugin_root, hid, doc).returncode == 0
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert saved["findings"][0]["check"]["status"] == "upheld"


def test_save_finding_strips_what_a_model_must_not_set(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    f = doc["findings"][0]
    f["check"] = {"status": "upheld"}
    f["history"] = [{"sha": "x", "class": "fix"}]
    f["confidence_claimed"] = "high"
    src = scanned_copy / "out.json"
    src.write_text(json.dumps(doc))
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "save_finding.py"),
                    "--repo", str(scanned_copy), "--id", hid, "--from", str(src)],
                   check=True, capture_output=True)
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert not {"check", "history", "confidence_claimed"} & set(saved["findings"][0])
    assert _validate(scanned_copy, plugin_root).returncode == 0
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert saved["findings"][0]["check"]["status"] == "unchecked"


def test_the_capture_hook_strips_what_a_model_must_not_set(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    doc["findings"][0].update(check={"status": "upheld"}, history=[{"sha": "x"}],
                              confidence_claimed="high")
    payload = {"session_id": "s", "transcript_path": "/dev/null", "cwd": str(scanned_copy),
               "hook_event_name": "SubagentStop", "agent_id": "a1",
               "agent_type": "plugin:thunderstruck:thunderstruck-investigator",
               "stop_reason": "completed", "last_assistant_message": json.dumps(doc)}
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / "capture_finding.py")],
                          input=json.dumps(payload), capture_output=True, text=True)
    assert proc.returncode == 0
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_text())
    assert not {"check", "history", "confidence_claimed"} & set(saved["findings"][0])
    assert saved["schema"] == "thunderstruck.finding/v2"


def test_findings_validated_under_rules_3_are_investigated_again(scanned_copy, plugin_root):
    old = {"findings": [{"key": "k", "confidence": "high"}], "validated_with": 3}
    assert bundle._validated_under_older_rules(old)
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    for f in doc["findings"]:
        del f["preconditions"]                               # written by 0.9.x
    from validate import Validator
    v = Validator(scanned_copy, _hotspots(scanned_copy), c.load_catalog())
    assert not bundle._still_valid(v, doc)
