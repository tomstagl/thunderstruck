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
