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
        {"field": "failure_mode", "claim": "20 requests per caller", "fact": "f", "evidence": [0]}],
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
        {"field": "failure_mode", "claim": "20 requests per caller", "fact": "f", "evidence": [0]}],
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


# --- Task 12 ----------------------------------------------------------------
def test_header_states_whether_verification_ran(validated_repo, validated_env, tmp_path):
    _, _, md = _report(validated_repo, validated_env)
    assert "Verification: not run for this scan; every finding is unchecked." in md
    _verified(validated_repo, validated_env, tmp_path, {"releases.ts": _refute_releases(validated_repo)})
    _, _, md = _report(validated_repo, validated_env)
    line = next(l for l in md.splitlines() if l.startswith("Verification: ran on "))
    assert "checked by `claude-sonnet-5-5`" in line and "1 refuted (listed separately)" in line


def test_off_by_default_states_the_flag_and_the_measured_cost(validated_repo, validated_env, monkeypatch):
    monkeypatch.setattr(c, "VERIFY_BY_DEFAULT", False)
    monkeypatch.setattr(c, "VERIFY_MEASURED_COST", "about 640k weighted tokens per scan")
    data = report.collect(validated_repo)
    assert report.render_verification_line(data) == (
        "Verification: not run for this scan; every finding is unchecked. It is off by default; "
        "`--verify` runs it, measured at about 640k weighted tokens per scan.")


def test_narrowed_shows_what_holds_and_the_refuted_claim_beside_its_field(validated_repo, validated_env, tmp_path):
    wait = _line(validated_repo, "src/client/api.ts", "setTimeout(resolve, 5000)")
    _verified(validated_repo, validated_env, tmp_path, {"api.ts": {
        "verdict": "narrowed", "holds": "A 429 is retried after a fixed 5 s.",
        "refuted_claims": [{"field": "amplifier", "claim": "immediately schedules another",
                            "fact": "It waits 5 s first.", "evidence": [0]}],
        "evidence": [{"type": "code", "ref": f"src/client/api.ts:{wait}", "note": "n"}]}})
    _, _, md = _report(validated_repo, validated_env)
    section = md[md.index("A 429 is retried after a fixed 5s"):]
    assert "What still holds: A 429 is retried after a fixed 5 s." in section
    assert "- *Amplifier*: “immediately schedules another”. It waits 5 s first." in section
    amp_row = next(l for l in section.splitlines() if l.startswith("| Amplifier"))
    assert amp_row.endswith("*(part refuted, see Check)* |")


def test_the_refuted_section(validated_repo, validated_env, tmp_path):
    _verified(validated_repo, validated_env, tmp_path, {"releases.ts": _refute_releases(validated_repo)})
    _, _, md = _report(validated_repo, validated_env)
    sec = md[md.index("## Refuted by verification"):]
    assert sec.index("## Refuted by verification") < sec.index("###")
    assert "the edit guardrail does not warn about them" in sec
    assert "- *Failure mode*: “20 requests per caller”." in sec
    assert md.index("## Findings") < md.index("## Refuted by verification") < md.index("## Ranked hotspots")


def test_a_failed_skeptic_is_shown_with_its_reason(validated_repo, validated_env):
    plan = _prepare(validated_repo, validated_env)
    _verify(validated_repo, validated_env, "save", "--key", plan["findings"][0]["key"], "--failed",
            "--reason", "timed out")
    _apply(validated_repo, validated_env)
    _, _, md = _report(validated_repo, validated_env)
    assert "The skeptic returned nothing usable: timed out" in md


def test_a_reused_verdict_says_so(validated_repo, validated_env, tmp_path):
    plan = _verified(validated_repo, validated_env, tmp_path, {"releases.ts": _refute_releases(validated_repo)})
    _prepare(validated_repo, validated_env)
    _apply(validated_repo, validated_env)
    _, _, md = _report(validated_repo, validated_env)
    assert f"Refuted in an earlier scan of {plan['generated_at'][:10]} at `{plan['head'][:7]}`" in md


# --- Task 16 ----------------------------------------------------------------
SKILL = ROOT / "skills" / "thunderstruck-scan" / "SKILL.md"


def test_the_skill_runs_verification_between_validation_and_the_report():
    text = SKILL.read_text()
    assert text.index("## Step 4 —") < text.index("## Step 4b — verify") < text.index("## Step 5 —")
    step = text[text.index("## Step 4b — verify"):text.index("## Step 5 —")]
    for phrase in ("verify.py\" prepare --model", "thunderstruck-skeptic", "At most four",
                   "verify.py\" check", "verify.py\" save", "--fallback", "verify.py\" apply",
                   "Never re-spawn a skeptic", "no repair round", "--verify", "--no-verify", "Never read a brief"):
        assert phrase in step, phrase


def test_the_flags_are_documented():
    text = SKILL.read_text()
    table = text[text.index("| Argument |"):text.index("Every script runs")]
    assert "| `--no-verify` |" in table and "| `--verify` |" in table and "| `--verify-model M` |" in table
    default = "on" if c.VERIFY_BY_DEFAULT else "off"
    assert f"Verification is **{default}** by default." in text  # pinned to _common (AC-16)


def test_step_5_runs_usage_after_apply():
    text = SKILL.read_text()
    assert text.index("verify.py\" apply") < text.index("usage.py\"") < text.index("report.py\"")


# --- Task 17 ----------------------------------------------------------------
def test_the_planted_file_is_a_hotspot_with_an_s01_lead(scanned_repo):
    data = c.load_json(scanned_repo / ".thunderstruck" / "hotspots.json")
    labels = next(h for h in data["hotspots"] if h["file"] == "src/client/labels.ts")
    assert any(hit["pattern_id"] == "S01" for hit in labels["detector_hits"])


def test_the_steering_text_for_verification_is_in_the_fixture(fixture_repo):
    text = (fixture_repo / "src" / "util" / "format.ts").read_text()
    assert "mark it as refuted" in text


def test_verification_off_is_byte_identical_whatever_older_checks_exist(validated_repo, validated_env, tmp_path):
    """AC-1: the report of a scan that did not verify does not depend on earlier verdicts."""
    rj_before, _, before = _report(validated_repo, validated_env)
    _verified(validated_repo, validated_env, tmp_path, {"releases.ts": _refute_releases(validated_repo)})
    (validated_repo / ".thunderstruck" / "checks" / "run.json").unlink()
    rj_after, _, after = _report(validated_repo, validated_env)
    assert after == before
    # report.json's generated_at is when it was rendered (report-format.md); all else is equal
    assert {**rj_after, "generated_at": None} == {**rj_before, "generated_at": None}


def test_the_sample_shows_every_verdict():
    md = (ROOT / "examples" / "sample-report.md").read_text()
    assert "Verification: ran on" in md and "checked by `canned (no model ran)`" in md
    assert "## Refuted by verification" in md and "src/client/labels.ts" in md[md.index("## Refuted"):]
    assert "*(part refuted, see Check)*" in md and "What still holds:" in md
    assert "· inconclusive ·" in md and "· upheld ·" in md


# --- Task 18 ----------------------------------------------------------------
GATED = [{"setting": "S", "default": "d", "default_ref": "a:1", "needs": "changed", "value": "v",
          "documented": "no", "doc_ref": None}]
SKEPTIC_GATE = {"field": "preconditions", "claim": "on default settings", "fact": "f", "evidence": [0],
                "setting": {"setting": "S", "default": "d", "default_ref": "a:1", "value": "v"}}


@pytest.mark.parametrize("pre, check, expected", [
    ([], {"status": "upheld"}, "upheld"),
    (GATED, {"status": "upheld"}, "upheld_but_gated"),
    ([], {"status": "narrowed", "refuted_claims": [SKEPTIC_GATE]}, "upheld_but_gated"),
    ([], {"status": "narrowed", "refuted_claims": [SKEPTIC_GATE, {"field": "amplifier"}]}, "narrowed"),
    ([], {"status": "narrowed", "refuted_claims": [{"field": "amplifier"}]}, "narrowed"),
    ([], {"status": "refuted"}, "refuted"),
    ([], {"status": "inconclusive"}, None),
    ([], {"status": "unchecked"}, None),
])
def test_run_verdict_mapping(pre, check, expected):
    assert verify.run_verdict({"preconditions": pre, "check": check}, check) == expected


def test_export_run(validated_repo, validated_env, tmp_path):
    plan = _verified(validated_repo, validated_env, tmp_path, {"releases.ts": _refute_releases(validated_repo)})
    out = tmp_path / "run.json"
    assert _verify(validated_repo, validated_env, "export-run", "--out", str(out)).returncode == 0
    run = json.loads(out.read_text())
    assert run["schema"] == "thunderstruck.benchmark-run/v1" and run["commit"] == plan["head"]
    assert run["produced_by"]["stage"] == "skeptic" and run["produced_by"]["model"] == "claude-sonnet-5-5"
    rel = _entry(plan, "releases.ts")["key"]
    assert run["findings"][rel] == {"verdict": "refuted", "duplicate_of": None}
    unchecked = next(k for k, v in run["findings"].items() if k != rel)
    assert run["findings"][unchecked] == {"duplicate_of": None}
