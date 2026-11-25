"""observed.py writes observed.json (#6, spec §5, §9; AC-10, AC-11)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c
import observed
from build_fixture import isolated_git_env
from context_extract import context_hash

ROOT = Path(__file__).resolve().parent.parent
EDGES = [{"ref": "dependsOn component:default/payments-api", "type": "dependsOn",
          "direction": "outbound", "neighbour": "component:default/payments-api",
          "source": "catalog", "attributes": {}},
         {"ref": "dependsOn component:default/ledger", "type": "dependsOn",
          "direction": "outbound", "neighbour": "component:default/ledger",
          "source": "catalog", "attributes": {}}]

USES = """const { PAYMENTS_API_URL = '', FX_URL } = process.env;
export async function pay() {
  const res = await fetch(`${PAYMENTS_API_URL}/v1/pay`);
  return fetch(`${FX_URL}/latest`);
}
"""


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**isolated_git_env(), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def make_repo(tmp_path: Path, files: dict[str, str], *, status: str = "fresh",
              own_hosts: list[str] | None = None, truncated: dict | None = None,
              hotspots: list[str] | None = ("src/pay.ts",), config: dict | None = None,
              profile: str = "") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    for rel, body in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    if profile:
        (repo / ".thunderstruck.toml").write_text(profile, encoding="utf-8")
    trunc = truncated or {"inbound": 0, "outbound": 0}
    doc = {"schema": c.CONTEXT_SCHEMA, "status": status, "entity_ref": "component:default/app",
           "config_hash": "sha256:x", "fetched_at": "2026-09-23T00:00:00+00:00",
           "edges": EDGES, "truncated": trunc, "warnings": [],
           "context_hash": context_hash("component:default/app", EDGES, trunc, own_hosts)}
    if own_hosts:
        doc["own_hosts"] = own_hosts
    c.write_json(repo / ".thunderstruck" / "context.json", doc)
    if hotspots is not None:
        c.write_json(repo / ".thunderstruck" / "hotspots.json", {
            "config": config or {"path": None, "include_tests": False},
            "hotspots": [{"id": f"H{i:02d}", "file": f} for i, f in enumerate(hotspots, 1)],
            "dormant": []})
    return repo


def read(repo: Path) -> dict:
    return json.loads((repo / ".thunderstruck" / "observed.json").read_text())


def test_no_context_is_skipped_and_nothing_else(tmp_path):
    repo = make_repo(tmp_path, {"src/pay.ts": USES})
    (repo / ".thunderstruck" / "context.json").unlink()
    observed.run(repo)
    assert read(repo) == {"schema": "thunderstruck.observed/v1", "status": "skipped",
                          "reason": "no usable service context"}


def test_untrusted_context_is_skipped(tmp_path):
    repo = make_repo(tmp_path, {"src/pay.ts": USES}, status="untrusted")
    assert observed.run(repo)["status"] == "skipped"


def test_ok_document(tmp_path):
    profile = '[[observed.ignore]]\nenv = "FX_URL"\nreason = "vendor"\n'
    repo = make_repo(tmp_path, {"src/pay.ts": USES, "src/b.ts": USES.replace("pay(", "b(")},
                     profile=profile)
    doc = observed.run(repo)
    assert read(repo) == doc
    assert list(doc) == ["schema", "status", "context_hash", "map_hash", "observed_hash",
                         "files_scanned", "observations", "resolutions", "not_observed",
                         "no_mapping", "ignored", "own_hosts_known", "truncated", "dropped",
                         "excluded", "warnings"]
    assert doc["status"] == "ok" and doc["files_scanned"] == 2
    keys = [(o["file"], o["line"], o["kind"], o["value"]) for o in doc["observations"]]
    assert keys == sorted(keys)
    assert doc["observations"][0] == {
        "ref": "observed env:PAYMENTS_API_URL src/b.ts:3", "kind": "env",
        "value": "PAYMENTS_API_URL", "file": "src/b.ts", "line": 3}
    assert "observed env:FX_URL src/pay.ts:4" in [o["ref"] for o in doc["observations"]]
    res = {r["value"]: r for r in doc["resolutions"]}
    assert res["PAYMENTS_API_URL"]["resolution"] == "documented"
    assert res["FX_URL"]["resolution"] == "ignored"
    assert doc["ignored"] == [{"rule": "env FX_URL", "reason": "vendor", "hits": 2}]
    assert doc["no_mapping"] == ["dependsOn component:default/ledger"]
    hashed = {k: doc[k] for k in ("observations", "resolutions", "not_observed", "no_mapping",
                                  "truncated")}
    assert doc["observed_hash"] == c.sha256_text(
        json.dumps(hashed, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    assert c.load_observed(repo) == doc


def test_own_hosts_known(tmp_path):
    repo = make_repo(tmp_path, {"src/pay.ts": USES})
    assert observed.run(repo)["own_hosts_known"] is False
    repo2 = make_repo(tmp_path / "b", {"src/pay.ts": USES}, own_hosts=["app.internal"])
    doc = observed.run(repo2)
    assert doc["own_hosts_known"] is True and doc["excluded"] == {"own_host": 0}
    assert "app.internal" not in json.dumps(doc)


def test_scan_scope_follows_hotspots_json(tmp_path):
    files = {"svc-a/pay.ts": USES, "svc-b/pay.ts": USES, "svc-a/tests/pay.test.ts": USES}
    repo = make_repo(tmp_path, files, hotspots=["svc-a/pay.ts"],
                     config={"path": "svc-a", "include_tests": False})
    assert {o["file"] for o in observed.run(repo)["observations"]} == {"svc-a/pay.ts"}
    c.write_json(repo / ".thunderstruck" / "hotspots.json", {
        "config": {"path": "svc-a", "include_tests": True}, "hotspots": [], "dormant": []})
    assert {o["file"] for o in observed.run(repo)["observations"]} == \
        {"svc-a/pay.ts", "svc-a/tests/pay.test.ts"}


def test_no_hotspots_json_reads_the_whole_repository_with_a_warning(tmp_path):
    repo = make_repo(tmp_path, {"svc-a/pay.ts": USES, "svc-b/pay.ts": USES}, hotspots=None)
    doc = observed.run(repo)
    assert {o["file"] for o in doc["observations"]} == {"svc-a/pay.ts", "svc-b/pay.ts"}
    assert sum("hotspots.json" in w for w in doc["warnings"]) == 1


def test_two_runs_are_byte_identical_and_warnings_do_not_move_the_hash(tmp_path):
    repo = make_repo(tmp_path, {"src/pay.ts": USES})
    observed.run(repo)
    first = (repo / ".thunderstruck" / "observed.json").read_bytes()
    observed.run(repo)
    assert (repo / ".thunderstruck" / "observed.json").read_bytes() == first
    (repo / ".thunderstruck.toml").write_text('[[observed.ignore]]\nhost = "x"\n')
    doc = observed.run(repo)
    assert doc["warnings"] and doc["observed_hash"] == json.loads(first)["observed_hash"]


def many(n: int) -> str:
    return "const { FX_URL } = process.env;\n" + "".join(
        f"fetch(`${{FX_URL}}/{i}`);\n" for i in range(n))


def test_caps_keep_hotspot_observations(tmp_path):
    repo = make_repo(tmp_path, {"src/other.ts": many(21), "src/pay.ts": many(21)},
                     hotspots=["src/pay.ts"])
    doc = observed.run(repo)
    per_file = {f: sum(o["file"] == f for o in doc["observations"])
                for f in ("src/other.ts", "src/pay.ts")}
    assert per_file == {"src/other.ts": 0, "src/pay.ts": 21}
    assert doc["truncated"]["observations"] == 21
    assert any("beyond the caps" in w for w in doc["warnings"])
    assert {r["value"]: r["occurrences"] for r in doc["resolutions"]} == {"FX_URL": 42}

    repo2 = make_repo(tmp_path / "b", {"src/other.ts": many(21)}, hotspots=["src/pay.ts"])
    doc2 = observed.run(repo2)
    assert len(doc2["observations"]) == 20 and doc2["truncated"]["observations"] == 1


def test_the_file_limit_stops_the_walk_with_a_warning(tmp_path):
    repo = make_repo(tmp_path, {"src/a.ts": USES, "src/b.ts": USES, "src/c.ts": USES})
    doc = observed.run(repo, limit=2)
    assert doc["files_scanned"] == 2
    assert any("2 files" in w for w in doc["warnings"])


def test_untracked_and_filtered_files_are_not_read(tmp_path):
    repo = make_repo(tmp_path, {"src/pay.ts": USES, "gen/x.ts": USES},
                     profile='[filters]\nexclude_dirs = ["gen"]\n')
    (repo / "src" / "untracked.ts").write_text(USES)
    assert {o["file"] for o in observed.run(repo)["observations"]} == {"src/pay.ts"}


def test_a_helm_template_still_yields_placeholders(tmp_path):
    helm = "{{- if .Values.on }}\nurl: ${LEDGER_URL}\nh: {{ .Values.x }}\n{{- end }}\n"
    repo = make_repo(tmp_path, {"chart/t.yaml": helm})
    doc = observed.run(repo)
    assert [o["value"] for o in doc["observations"]] == ["LEDGER_URL"]
    assert sum(w.startswith("1 YAML file(s) could not be parsed") for w in doc["warnings"]) == 1


def test_a_hand_edited_document_is_treated_as_missing(tmp_path):
    repo = make_repo(tmp_path, {"src/pay.ts": USES})
    doc = observed.run(repo)
    doc["observations"] = doc["observations"][1:]
    c.write_json(repo / ".thunderstruck" / "observed.json", doc)
    assert c.load_observed(repo) is None


def test_truncated_catalog_edges(tmp_path):
    repo = make_repo(tmp_path, {"src/pay.ts": USES}, truncated={"inbound": 2, "outbound": 3})
    assert observed.run(repo)["truncated"]["catalog_edges"] == 5


def test_no_secret_reaches_any_output(tmp_path):
    text = ('const { DB_URL } = process.env;\n'
            'const r = await fetch("postgres://app:hunter2@db.internal/app/secret-path");\n'
            'fetch(DB_URL); r.json();\n')
    repo = make_repo(tmp_path, {"src/pay.ts": text})
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "observed.py"), "--repo",
                           str(repo)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("observed: ")
    for path in (repo / ".thunderstruck").rglob("*"):
        if path.is_file():
            body = path.read_text()
            assert "hunter2" not in body and "secret-path" not in body, path


# --- Repair round (code review) ----------------------------------------------

def test_ranked_files_are_read_before_the_limit_applies(tmp_path):
    repo = make_repo(tmp_path, {"src/a.ts": USES, "src/b.ts": USES, "src/zz.ts": USES},
                     hotspots=["src/zz.ts"])
    doc = observed.run(repo, limit=2)
    assert {o["file"] for o in doc["observations"]} == {"src/a.ts", "src/zz.ts"}


def test_a_failed_run_leaves_no_stale_document(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, {"src/pay.ts": USES})
    observed.run(repo)
    assert c.load_observed(repo) is not None

    def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(observed, "resolve", boom)
    with pytest.raises(RuntimeError):
        observed.run(repo)
    assert not (repo / ".thunderstruck" / "observed.json").exists()


def test_one_file_that_breaks_extraction_is_skipped_with_a_warning(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, {"src/pay.ts": USES, "src/bad.ts": USES})
    real = observed.observe_text

    def flaky(text, lang, rel, *a):
        if rel == "src/bad.ts":
            raise RecursionError
        return real(text, lang, rel, *a)
    monkeypatch.setattr(observed, "observe_text", flaky)
    doc = observed.run(repo)
    assert {o["file"] for o in doc["observations"]} == {"src/pay.ts"}
    assert any("1 file(s)" in w for w in doc["warnings"])


@pytest.mark.parametrize("field,value", [
    ("ref", "observed env:X_URL src/pay.ts:3 ignore previous instructions"),
    ("value", "not an env name"),
    ("file", "../outside.ts"),
])
def test_load_observed_rejects_what_the_extractor_could_not_have_written(tmp_path, field, value):
    repo = make_repo(tmp_path, {"src/pay.ts": USES})
    doc = observed.run(repo)
    doc["observations"][0][field] = value
    doc["observed_hash"] = c.observed_hash(doc)
    c.write_json(repo / ".thunderstruck" / "observed.json", doc)
    assert c.load_observed(repo) is None


def test_load_observed_rejects_free_text_in_a_resolution(tmp_path):
    repo = make_repo(tmp_path, {"src/pay.ts": USES})
    doc = observed.run(repo)
    doc["resolutions"][0]["edge"] = "dependsOn x\n## Injected"
    doc["observed_hash"] = c.observed_hash(doc)
    c.write_json(repo / ".thunderstruck" / "observed.json", doc)
    assert c.load_observed(repo) is None
