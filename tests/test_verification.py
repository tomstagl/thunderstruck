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


# --- Task 10 ----------------------------------------------------------------
def _entry(plan: dict, fragment: str) -> dict:
    return next(e for e in plan["findings"] if fragment in e["file"])


def _finding(repo: Path, key: str) -> dict:
    return next(i["finding"] for i in verify.load_findings(repo) if i["finding"]["key"] == key)


def _line(repo: Path, rel: str, needle: str) -> int:
    return next(n for n, l in enumerate((repo / rel).read_text().splitlines(), 1) if needle in l)


def _save(repo: Path, env: dict, tmp_path: Path, verdict: dict) -> None:
    p = tmp_path / f"{verdict['key']}.json"
    p.write_text(json.dumps(verdict))
    assert _verify(repo, env, "save", "--key", verdict["key"], "--from", str(p)).returncode == 0


def _apply(repo: Path, env: dict) -> dict:
    proc = _verify(repo, env, "apply")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return c.load_json(repo / ".thunderstruck" / "checks" / "verdicts.json")["checks"]


def _v(key: str, verdict: str, **over) -> dict:
    v = {"key": key, "verdict": verdict, "reason": "r", "holds": None, "refuted_claims": [],
         "evidence": [], "dependencies_read": [], "duplicate_of": None}
    v.update(over)
    return v


def test_upheld_is_written_into_the_findings_file(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", reason="All three layers are real."))
    checks = _apply(validated_repo, validated_env)
    assert checks[e["key"]]["status"] == "upheld" and checks[e["key"]]["by"] == "skeptic"
    assert checks[e["key"]]["model"] == c.MODEL_ALIASES[plan["model"]]
    assert _finding(validated_repo, e["key"])["check"]["status"] == "upheld"


def test_no_result_failed_and_unparsed_are_unchecked_with_reasons(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    keys = [e["key"] for e in plan["findings"]]
    _verify(validated_repo, validated_env, "save", "--key", keys[1], "--failed", "--reason", "timed out")
    bad = tmp_path / "bad.json"
    bad.write_text("I could not decide.")
    _verify(validated_repo, validated_env, "save", "--key", keys[2], "--from", str(bad))
    _save(validated_repo, validated_env, tmp_path, _v(keys[3], "probably"))
    checks = _apply(validated_repo, validated_env)
    assert checks[keys[0]] == {"status": "unchecked", "by": "skeptic", "reason":
                               "No verdict reached disk: the skeptic failed, stopped or its result was not saved."}
    assert checks[keys[1]]["reason"] == "The skeptic returned nothing usable: timed out"
    assert checks[keys[2]]["reason"].startswith("The skeptic's output did not follow the verdict contract")
    assert "verdict 'probably'" in checks[keys[3]]["reason"]


def test_refuted_with_unresolved_evidence_is_inconclusive(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "api.ts")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "refuted", refuted_claims=[
        {"field": "failure_mode", "claim": "a 429 is retried", "fact": "f", "evidence": [0]}],
        evidence=[{"type": "code", "ref": "src/client/api.ts:9999", "note": "n"}]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "inconclusive"
    assert check["reason"].startswith("The verdict was refuted, but none of its evidence resolved:")


def test_narrowed_with_a_quoted_claim_and_resolving_evidence(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "api.ts")
    wait = _line(validated_repo, "src/client/api.ts", "setTimeout(resolve, 5000)")
    _save(validated_repo, validated_env, tmp_path, _v(
        e["key"], "narrowed", holds="A 429 is retried after a fixed 5 s, ignoring Retry-After.",
        refuted_claims=[
            {"field": "amplifier", "claim": "immediately schedules another", "fact": "It waits 5 s first.",
             "evidence": [0]},
            {"field": "amplifier", "claim": "a paraphrase that is not in the text", "fact": "x", "evidence": [0]}],
        evidence=[{"type": "code", "ref": f"src/client/api.ts:{wait}", "note": "the fixed wait"}]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "narrowed"
    assert [rc["claim"] for rc in check["refuted_claims"]] == ["immediately schedules another"]
    assert "Ignored: refuted_claims[1]" in check["reason"]


def test_narrowed_without_holds_is_inconclusive(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "api.ts")
    wait = _line(validated_repo, "src/client/api.ts", "setTimeout(resolve, 5000)")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "narrowed", refuted_claims=[
        {"field": "amplifier", "claim": "immediately schedules another", "fact": "f", "evidence": [0]}],
        evidence=[{"type": "code", "ref": f"src/client/api.ts:{wait}", "note": "n"}]))
    assert _apply(validated_repo, validated_env)[e["key"]]["reason"] == \
        "Narrowed, but the skeptic did not say what holds."


def test_an_other_finding_is_not_refuted_on_its_own_text(validated_repo, validated_env, tmp_path):
    """AC-11: the only evidence is the steering comment the finding cites."""
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "format.ts")
    f = _finding(validated_repo, e["key"])
    code_ref = next(ev["ref"] for ev in f["evidence"] if ev["type"] == "code")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "refuted", refuted_claims=[
        {"field": "failure_mode", "claim": "instructs automated reviewers", "fact": "The file says it was reviewed.",
         "evidence": [0]}], evidence=[{"type": "code", "ref": code_ref, "note": "already audited"}]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "inconclusive"
    assert check["reason"] == "The verdict rests only on the text this finding reports as steering the audit."


def test_a_stale_result_is_not_applied(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = plan["findings"][0]
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld"))
    path = validated_repo / ".thunderstruck" / "checks" / "results" / f"{e['key']}.json"
    doc = json.loads(path.read_text())
    doc["brief_hash"] = "0" * 64
    path.write_text(json.dumps(doc))
    assert _apply(validated_repo, validated_env)[e["key"]]["reason"] == \
        "The only verdict on disk was for an earlier version of this finding."


def test_apply_writes_the_ledger_and_run_and_reuse_follows(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "releases.ts")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "refuted", refuted_claims=[
        {"field": "failure_mode", "claim": "60 requests per caller", "fact": "f", "evidence": [0]}],
        evidence=[{"type": "code", "ref": "src/client/retry-wrapper.ts:1", "note": "n"}]))
    _apply(validated_repo, validated_env)
    ledger = c.load_json(validated_repo / ".thunderstruck" / "checks" / "ledger.json")["entries"]
    assert set(ledger) == {e["key"]}  # unchecked findings are never remembered
    assert "src/client/retry-wrapper.ts" in ledger[e["key"]]["files"]
    run = c.load_json(validated_repo / ".thunderstruck" / "checks" / "run.json")
    assert run["generated_at"] == plan["generated_at"] and run["counts"]["refuted"] == 1
    again = _prepare(validated_repo, validated_env)
    assert _entry(again, "releases.ts")["action"] == "reuse"
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "refuted"
    assert check["reused_from"] == {"scan": plan["generated_at"], "head": plan["head"]}


# --- Task 11 ----------------------------------------------------------------
import report  # noqa: E402


def _report(repo: Path, env: dict) -> tuple[dict, dict, str]:
    proc = subprocess.run([sys.executable, str(SCRIPTS / "report.py"), "--repo", str(repo)],
                          capture_output=True, text=True, cwd=str(repo), env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = repo / ".thunderstruck"
    return (json.loads((out / "report.json").read_text()), json.loads((out / "index.json").read_text()),
            (out / "report.md").read_text())


def _verified(repo: Path, env: dict, tmp_path: Path, verdicts: dict[str, dict]) -> dict:
    """prepare, save one verdict per file fragment, apply. Returns the plan."""
    plan = _prepare(repo, env)
    for fragment, v in verdicts.items():
        e = _entry(plan, fragment)
        _save(repo, env, tmp_path, {**_v(e["key"], v.pop("verdict")), **v, "key": e["key"]})
    _apply(repo, env)
    return plan


def _refute_releases(repo: Path) -> dict:
    return {"verdict": "refuted", "refuted_claims": [
        {"field": "failure_mode", "claim": "60 requests per caller", "fact": "f", "evidence": [0]}],
        "evidence": [{"type": "code", "ref": "src/client/retry-wrapper.ts:1", "note": "n"}]}


def test_without_a_run_every_finding_is_unchecked(validated_repo, validated_env, tmp_path):
    """AC-1 and Review Focus 1: an earlier verified scan's checks never leak."""
    _verified(validated_repo, validated_env, tmp_path, {"releases.ts": _refute_releases(validated_repo)})
    (validated_repo / ".thunderstruck" / "checks" / "run.json").unlink()
    rj, ij, md = _report(validated_repo, validated_env)
    assert rj["verification"]["ran"] is False
    assert {f["check"]["status"] for f in rj["findings"]} == {"unchecked"}
    assert rj["refuted"] == [] and any(p.endswith("releases.ts") for p in ij["files"])


def test_a_refuted_finding_leaves_findings_and_the_index(validated_repo, validated_env, tmp_path):
    _verified(validated_repo, validated_env, tmp_path, {"releases.ts": _refute_releases(validated_repo)})
    rj, ij, _ = _report(validated_repo, validated_env)
    assert rj["verification"]["ran"] is True
    assert [f["location"]["file"] for f in rj["refuted"]] == ["src/client/releases.ts"]
    assert "id" not in rj["refuted"][0]
    assert all(not f["location"]["file"].endswith("releases.ts") for f in rj["findings"])
    assert not any(it["key"] == rj["refuted"][0]["key"] for e in ij["files"].values() for it in e["findings"])
    assert rj["counts"]["refuted"] == 1 and rj["counts"]["check_status"]["refuted"] == 1
    assert [f["id"] for f in rj["findings"]] == [f"FR-{n:03d}" for n in range(1, len(rj["findings"]) + 1)]


def test_check_evidence_is_linked_and_dependency_refs_are_not(linked_copy):
    f = {"location": {"file": "src/client/api.ts"}, "evidence": [], "check": {"status": "narrowed", "evidence": [
        {"type": "code", "ref": "src/client/api.ts:1", "note": "n"},
        {"type": "dependency", "ref": "pypi:x@1:x/y.py:1", "note": "n"}], "refuted_claims": []}}
    head = c.load_json(linked_copy / ".thunderstruck" / "hotspots.json")["repo"]["head"]
    report.link_refs(linked_copy, head, [f], [], [])
    assert f["check"]["evidence"][0]["url"].startswith("https://github.com/acme/fixture/")
    assert f["check"]["evidence"][1]["url"] is None


def _dup(key: str, file: str, dup: str | None, conf: str = "medium", status: str = "upheld") -> dict:
    return {"key": key, "location": {"file": file, "lines": "1"}, "hotspot_id": "H01",
            "confidence": conf, "gate": "none", "hotspot_score": 0.1,
            "check": {"status": status, "duplicate_of": dup}}


def test_duplicate_groups():
    """Review Focus 5: a cycle is one group; the survivor is first by report order."""
    a, b = _dup("a", "x.ts", "b", "low"), _dup("b", "y.ts", "a", "high")
    chain = [_dup("c", "c.ts", "d"), _dup("d", "d.ts", "e"), _dup("e", "e.ts", None, "high")]
    groups = report.duplicate_groups([a, b, *chain, _dup("f", "f.ts", "zzz")])
    assert {k: [x["key"] for x in v] for k, v in groups.items()} == {"b": ["a"], "e": ["c", "d"]}


def test_a_duplicate_is_reported_once_and_indexed_under_both_files(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    sched, coll = _entry(plan, "scheduler.ts"), _entry(plan, "collection.ts")
    _save(validated_repo, validated_env, tmp_path, _v(sched["key"], "upheld", duplicate_of=coll["key"]))
    _save(validated_repo, validated_env, tmp_path, _v(coll["key"], "upheld"))
    _apply(validated_repo, validated_env)
    rj, ij, _ = _report(validated_repo, validated_env)
    keys = [f["key"] for f in rj["findings"]]
    assert sched["key"] not in keys or coll["key"] not in keys
    survivor = next(f for f in rj["findings"] if f["key"] in (sched["key"], coll["key"]))
    assert len(survivor["also_at"]) == 1 and rj["counts"]["duplicates_merged"] == 1
    other_file = survivor["also_at"][0]["location"]["file"]
    assert any(it.get("via") == "duplicate" and it["key"] == survivor["key"]
               for it in ij["files"][other_file]["findings"])


def test_a_duplicate_of_a_refuted_finding_is_not_merged(validated_repo, validated_env, tmp_path):
    """Review Focus 5."""
    plan = _prepare(validated_repo, validated_env)
    rel, api = _entry(plan, "releases.ts"), _entry(plan, "api.ts")
    _save(validated_repo, validated_env, tmp_path, {**_v(rel["key"], "refuted"), **_refute_releases(validated_repo)})
    _save(validated_repo, validated_env, tmp_path, _v(api["key"], "upheld", duplicate_of=rel["key"]))
    _apply(validated_repo, validated_env)
    rj, _, _ = _report(validated_repo, validated_env)
    assert api["key"] in [f["key"] for f in rj["findings"]] and rj["counts"]["duplicates_merged"] == 0


def test_unavailable_dependency_source_is_a_run_warning(validated_repo, validated_env, tmp_path):
    (validated_repo / "requirements.txt").write_text("kombu>=5.6\n")
    _verified(validated_repo, validated_env, tmp_path, {})
    rj, _, _ = _report(validated_repo, validated_env)
    dep = rj["verification"]["dependencies"][0]
    assert dep["id"] == "pypi:kombu" and dep["status"] == "unavailable" and "source" not in dep
    assert any("Dependency source not available for pypi:kombu" in w for w in rj["run_warnings"])
