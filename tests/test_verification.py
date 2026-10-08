"""#37: refuting findings before they reach the report."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


# --- Task 1 -----------------------------------------------------------------
def test_verdicts_are_check_statuses_but_unchecked():
    assert c.VERDICTS == ("upheld", "narrowed", "refuted", "inconclusive")
    assert set(c.VERDICTS) == set(c.CHECK_STATUSES) - {"unchecked"}


def test_refutable_fields_are_finding_fields():
    assert c.REFUTABLE_FIELDS == ("failure_mode", "trigger_condition", "amplifier",
                                  "sustaining_effect", "blast_radius", "how_to_verify",
                                  "prediction", "preconditions")


SETTING = {"setting": "S", "default": "False", "default_ref": "a.py:1", "value": "True"}


@pytest.mark.parametrize("check, gate", [
    ({"status": "narrowed", "refuted_claims": [{"field": "preconditions", "setting": SETTING}]},
     "non_default_setting"),
    ({"status": "upheld", "refuted_claims": [{"field": "preconditions", "setting": SETTING}]}, "none"),
    ({"status": "narrowed", "refuted_claims": [{"field": "preconditions"}]}, "none"),
    ({"status": "narrowed", "refuted_claims": [{"field": "amplifier", "setting": SETTING}]}, "none"),
    ({"status": "narrowed", "refuted_claims": "junk"}, "none"),
    ({"status": "narrowed"}, "none"),
])
def test_a_setting_the_skeptic_found_gates_a_narrowed_finding(check, gate):
    assert c.finding_gate({"preconditions": [], "check": check}) == gate


def test_investigator_preconditions_still_gate():
    f = {"preconditions": [{"needs": "changed"}], "check": {"status": "upheld"}}
    assert c.finding_gate(f) == "non_default_setting"
    assert c.skeptic_settings(f) == []


# --- Task 6 -----------------------------------------------------------------
import deps  # noqa: E402
import validate  # noqa: E402


def _validator(repo: Path, deps_index: dict | None = None) -> "validate.Validator":
    hotspots = c.load_json(repo / ".thunderstruck" / "hotspots.json")
    return validate.Validator(repo, hotspots, c.load_catalog(ROOT), deps_index=deps_index)


def _dep_index(repo: Path) -> dict:
    src = repo.parent / "site" / "lib"
    src.mkdir(parents=True, exist_ok=True)
    (src / "core.py").write_text("".join(f"l{i}\n" for i in range(1, 51)))
    pkg = {"id": "pypi:lib", "ecosystem": "pypi", "name": "lib", "declared": "==1.0",
           "declared_in": ["requirements.txt"], "version": "1.0", "basis": "pinned", "status": "available",
           "reason": None, "source": str(src.parent), "files": ["lib/core.py"], "snapshot": None}
    return deps.snapshot(repo, {"schema": deps.DEPS_SCHEMA, "packages": [pkg], "warnings": []})


def test_check_ref_rejects_a_dependency_ref_unless_allowed(scanned_copy):
    v = _validator(scanned_copy, _dep_index(scanned_copy))
    errors: list[str] = []
    assert v.check_ref("pypi:lib@1.0:lib/core.py:3-4", "x", errors) is None
    assert "dependency refs are accepted in a verification verdict only" in errors[0]
    errors.clear()
    assert v.check_ref("pypi:lib@1.0:lib/core.py:3-4", "x", errors, allow_dependency=True) == \
        ("pypi:lib@1.0:lib/core.py", 3, 4)
    assert errors == []


@pytest.mark.parametrize("ev, ok, needle", [
    ({"type": "dependency", "ref": "pypi:lib@1.0:lib/core.py:7", "note": "n"}, True, None),
    ({"type": "dependency", "ref": "pypi:lib@2.0:lib/core.py:7", "note": "n"}, False, "read at 1.0, not 2.0"),
    ({"type": "detector", "ref": "S01@x:1", "note": "n"}, False, "not verdict evidence"),
    ({"type": "catalog", "ref": "dependencyOf x", "note": "n"}, False, "not verdict evidence"),
])
def test_verdict_evidence(scanned_copy, ev, ok, needle):
    v = _validator(scanned_copy, _dep_index(scanned_copy))
    errors: list[str] = []
    got = v.check_verdict_evidence(ev, "check.evidence[0]", errors, finding_files=[])
    assert (got is not None) is ok
    assert (needle is None and errors == []) or any(needle in e for e in errors)


def test_a_verdict_commit_may_touch_a_file_only_the_verdict_cites(scanned_copy):
    wrapper_sha = subprocess.run(["git", "-C", str(scanned_copy), "log", "-1", "--format=%h", "--",
                                  "src/client/retry-wrapper.ts"], capture_output=True, text=True).stdout.strip()
    v = _validator(scanned_copy)
    errors: list[str] = []
    ev = {"type": "commit", "ref": wrapper_sha, "note": "n"}
    # touches retry-wrapper.ts, which the verdict cites as code: accepted
    assert v.check_verdict_evidence(ev, "e", errors, finding_files=["src/client/retry-wrapper.ts"]) == "commit"
    # an unrelated file only: rejected with validate.py's message
    errors.clear()
    assert v.check_verdict_evidence(ev, "e", errors, finding_files=["src/util/format.ts"]) is None
    assert "does not touch" in errors[0]


# --- Task 7 -----------------------------------------------------------------
import verify  # noqa: E402


def _prepare(repo: Path, env: dict, *extra: str) -> dict:
    args = list(extra) if "--model" in extra else ["--model", "sonnet", *extra]
    proc = subprocess.run([sys.executable, str(SCRIPTS / "verify.py"), "prepare", "--repo", str(repo), *args],
                          capture_output=True, text=True, cwd=str(repo), env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads((repo / ".thunderstruck" / "checks" / "plan.json").read_text())


def test_every_validated_finding_is_planned_once(validated_repo, validated_env):
    plan = _prepare(validated_repo, validated_env)
    findings = verify.load_findings(validated_repo)
    assert sorted(e["key"] for e in plan["findings"]) == sorted(f["finding"]["key"] for f in findings)
    assert {e["action"] for e in plan["findings"]} == {"check"}
    assert plan["model"] == "sonnet" and plan["generated_at"] == c.load_json(
        validated_repo / ".thunderstruck" / "hotspots.json")["generated_at"]


def test_an_invalid_hotspot_is_not_planned(validated_repo, validated_env):
    val = c.load_json(validated_repo / ".thunderstruck" / "validation.json")
    val["results"][0]["valid"] = False
    c.write_json(validated_repo / ".thunderstruck" / "validation.json", val)
    plan = _prepare(validated_repo, validated_env)
    assert val["results"][0]["hotspot_id"] not in {e["hotspot_id"] for e in plan["findings"]}


def test_the_brief_holds_the_claim_and_evidence_only(validated_repo, validated_env):
    plan = _prepare(validated_repo, validated_env)
    entry = plan["findings"][0]
    brief = (validated_repo / entry["brief"]).read_text()
    f = next(x["finding"] for x in verify.load_findings(validated_repo) if x["finding"]["key"] == entry["key"])
    assert f["failure_mode"] in brief and f["evidence"][0]["ref"] in brief
    assert f["confidence_rationale"] not in brief
    for word in ("confidence", "history", "notes"):
        assert f"`{word}`" not in brief and f"## {word.title()}" not in brief
    assert "## Other findings in this scan" in brief and str(validated_repo) not in brief


def test_the_brief_carries_full_commit_messages(validated_repo, validated_env):
    plan = _prepare(validated_repo, validated_env)
    releases = next(e for e in plan["findings"] if e["file"].endswith("releases.ts"))
    brief = (validated_repo / releases["brief"]).read_text()
    assert "## Commit messages" in brief and "fix: " in brief


def test_prepare_is_deterministic(validated_repo, validated_env):
    first = _prepare(validated_repo, validated_env)
    briefs = {e["key"]: (validated_repo / e["brief"]).read_bytes() for e in first["findings"]}
    second = _prepare(validated_repo, validated_env)
    assert first == second
    assert briefs == {e["key"]: (validated_repo / e["brief"]).read_bytes() for e in second["findings"]}


def _ledger_entry(repo: Path, item: dict, status: str = "upheld") -> dict:
    f = item["finding"]
    return {"location": f["location"]["file"], "claim_hash": verify.claim_hash(f),
            "files": verify.hash_files(repo, verify.cited_files(f)),
            "dependency_versions": {},
            "check": {"status": status, "by": "skeptic", "reason": "held", "model": "claude-haiku-4-5"},
            "scan": "2026-01-01T00:00:00+00:00", "head": "0" * 40}


def _write_ledger(repo: Path, entries: dict) -> None:
    c.write_json(repo / ".thunderstruck" / "checks" / "ledger.json",
                 {"schema": verify.LEDGER_SCHEMA, "entries": entries})


def test_an_unchanged_finding_reuses_its_verdict(validated_repo, validated_env):
    item = verify.load_findings(validated_repo)[0]
    _write_ledger(validated_repo, {item["finding"]["key"]: _ledger_entry(validated_repo, item)})
    plan = _prepare(validated_repo, validated_env)
    assert {e["key"]: e["action"] for e in plan["findings"]}[item["finding"]["key"]] == "reuse"


def test_a_changed_cited_file_is_checked_again(validated_repo, validated_env):
    """Review Focus 4: same key, same text, one cited file changed elsewhere."""
    item = verify.load_findings(validated_repo)[0]
    _write_ledger(validated_repo, {item["finding"]["key"]: _ledger_entry(validated_repo, item)})
    cited = validated_repo / item["finding"]["location"]["file"]
    cited.write_text(cited.read_text() + "\n// unrelated\n")
    assert {e["key"]: e["action"] for e in _prepare(validated_repo, validated_env)["findings"]}[
        item["finding"]["key"]] == "check"


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(claim_hash="0" * 64),
    lambda e: e["files"].update({"src/client/retry-wrapper.ts": "0" * 64}),
    lambda e: e.update(dependency_versions={"pypi:kombu": "5.7.0a1"}),
    lambda e: e["check"].update(status="unchecked"),
])
def test_reuse_needs_every_condition(validated_repo, mutate):
    item = verify.load_findings(validated_repo)[0]
    entry = _ledger_entry(validated_repo, item)
    mutate(entry)
    assert verify.reusable(entry, item["finding"], validated_repo, None) is False


def test_frozen_mode_plans_the_celery_keys(tmp_path):
    frozen = ROOT / "docs" / "calibration" / "correctness" / "celery" / "scan"
    items = verify.load_frozen(frozen)
    assert len(items) == 21 and all(i["path"] is None for i in items)
    assert len({i["finding"]["key"] for i in items}) == 21


# --- Task 9 -----------------------------------------------------------------
def _verify(repo: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "verify.py"), *args, "--repo", str(repo)],
                          capture_output=True, text=True, cwd=str(repo), env=env)


def test_check_and_save(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    a, b = plan["findings"][0]["key"], plan["findings"][1]["key"]
    assert _verify(validated_repo, validated_env, "check", a, b).stdout.splitlines() == [f"{a} missing", f"{b} missing"]
    result = tmp_path / "r.json"
    result.write_text("```json\n" + json.dumps({"key": a, "verdict": "upheld"}) + "\n```")
    assert _verify(validated_repo, validated_env, "save", "--key", a, "--from", str(result), "--fallback",
                   "--usage", '{"input_tokens": 5, "output_tokens": 2, "model": "haiku"}').returncode == 0
    assert _verify(validated_repo, validated_env, "save", "--key", b, "--failed", "--reason", "timed out").returncode == 0
    assert _verify(validated_repo, validated_env, "check", a, b).stdout.splitlines() == [f"{a} saved", f"{b} failed"]
    rec = c.load_json(validated_repo / ".thunderstruck" / "checks" / "agents" / f"{a}.json")
    assert rec["fallback"] is True and rec["relayed_usage"] == {"input_tokens": 5, "output_tokens": 2, "model": "haiku"}


def test_save_refuses_an_unplanned_key(validated_repo, validated_env, tmp_path):
    _prepare(validated_repo, validated_env)
    result = tmp_path / "r.json"
    result.write_text(json.dumps({"key": "ffffffffffff", "verdict": "upheld"}))
    proc = _verify(validated_repo, validated_env, "save", "--key", "ffffffffffff", "--from", str(result))
    assert proc.returncode == 2 and "is not a planned check" in proc.stderr
