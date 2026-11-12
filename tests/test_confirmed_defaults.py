"""#57: defaults a finding relies on are confirmed or flagged, never assumed."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _common as c

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


# --- Task 1 -----------------------------------------------------------------
def _item(found="same", **over) -> dict:
    it = {"setting": "s", "precondition": 0, "found": found, "default": "1", "default_ref": "a.py:1",
          "default_ref_error": None, "default_call_site": False}
    it.update(over)
    return it


@pytest.mark.parametrize("call_site, item, basis", [
    (None, None, "not_checked"),
    (False, None, "not_checked"),
    (True, None, "call_site_fallback"),
    (True, _item("same"), "registered"),
    (False, _item("same"), "registered"),
    (False, _item("different"), "contradicted"),
    (False, _item("not_found", default=None, default_ref=None), "not_found"),
    (False, _item("same", default_ref_error="no such file"), "unresolved"),
    (False, _item("same", default_names_setting=False), "unresolved"),
    (False, _item("different", default_names_setting=False), "unresolved"),
    (False, _item("same", default_names_setting=True), "registered"),
    (False, _item("same", default_call_site=True), "call_site_fallback"),
    (True, _item("same", default_call_site=True), "call_site_fallback"),
    (False, _item("different", default_call_site=True), "call_site_fallback"),
    (False, _item("maybe"), "not_checked"),
])
def test_confirm_table(call_site, item, basis):
    got = c.confirm(call_site, item)
    assert got["basis"] == basis
    assert got["state"] == ("confirmed" if basis == "registered" else "unconfirmed")
    assert got["reason"] == c.CONFIRMATION_REASONS[basis]


def test_vocabularies_are_the_spec_spelling():
    assert c.CONFIRMATION_STATES == ("confirmed", "unconfirmed")
    assert c.CONFIRMATION_BASES == ("registered", "contradicted", "call_site_fallback",
                                    "not_found", "unresolved", "not_checked")
    assert c.CONFIRMATION_FOUND == ("same", "different", "not_found")
    assert set(c.CONFIRMATION_REASONS) == set(c.CONFIRMATION_BASES)
    assert c.GATES == ("none", "unconfirmed_default", "non_default_setting")
    assert c.GATE_MARKERS["unconfirmed_default"] == "relies on a doubtful default"
    assert c.DOUBTFUL_BASES == ("call_site_fallback", "contradicted", "not_found", "unresolved")
    assert c.DEFAULT_UNCONFIRMED_MARKER == "default unconfirmed"


def _pre(needs="default", call_site=False, setting="s") -> dict:
    return {"setting": setting, "default": "1", "default_ref": "a.py:1", "needs": needs,
            "value": None if needs == "default" else "2", "documented": "no", "doc_ref": None,
            "confirmation": {"call_site": call_site}}


def test_with_confirmations_derives_listed_and_unlisted_items_without_mutating():
    f = {"preconditions": [_pre(call_site=True), _pre(setting="t")],
         "check": {"status": "upheld", "confirmations": [
             _item("same", setting="t", precondition=1),
             _item("different", setting="u", precondition=None, claim="u is 1", stated_call_site=True)]}}
    before = json.dumps(f, sort_keys=True)
    got = c.with_confirmations(f, f["check"]["confirmations"])
    assert json.dumps(f, sort_keys=True) == before
    p0, p1 = got["preconditions"]
    assert (p0["confirmation"]["basis"], p0["confirmation"]["by"], p0["confirmation"]["call_site"]) == \
        ("call_site_fallback", "validator", True)
    assert (p1["confirmation"]["state"], p1["confirmation"]["by"]) == ("confirmed", "skeptic")
    unlisted = got["check"]["confirmations"][1]
    assert unlisted["confirmation"]["basis"] == "contradicted"


def test_with_confirmations_without_a_check_is_mechanical_only():
    got = c.with_confirmations({"preconditions": [_pre(call_site=True), _pre(call_site=None)]}, None)
    assert [p["confirmation"]["basis"] for p in got["preconditions"]] == ["call_site_fallback", "not_checked"]


def test_unconfirmed_defaults_counts_needs_default_and_unlisted_only():
    f = c.with_confirmations({"preconditions": [_pre("changed", call_site=True), _pre("default")],
                              "check": {"confirmations": [_item("same", setting="u", precondition=None)]}},
                             [_item("same", setting="u", precondition=None)])
    names = [x["setting"] for x in c.unconfirmed_defaults(f)]
    assert names == ["s"]  # the needs: changed one does not count; the unlisted one is confirmed


@pytest.mark.parametrize("finding, gate", [
    ({"preconditions": []}, "none"),
    ({"preconditions": [{**_pre(), "confirmation": {"state": "confirmed"}}]}, "none"),
    ({"preconditions": [_pre()]}, "none"),                                  # not_checked: not doubtful
    ({"preconditions": [{"setting": "s", "default": "1", "needs": "default"}]}, "none"),
    *[({"preconditions": [{**_pre(), "confirmation": {"state": "unconfirmed", "basis": b}}]}, "unconfirmed_default")
      for b in ("call_site_fallback", "contradicted", "not_found", "unresolved")],
    ({"preconditions": [{**_pre(), "confirmation": {"state": "unconfirmed", "basis": "not_checked"}}]}, "none"),
    ({"preconditions": [_pre(), _pre("changed", setting="t")]}, "non_default_setting"),
    ({"preconditions": [], "check": {"confirmations": [
        {"setting": "u", "precondition": None, "confirmation": {"state": "unconfirmed", "basis": "contradicted"}}]}},
     "unconfirmed_default"),
    ({"preconditions": [], "check": {"confirmations": [
        {"setting": "u", "precondition": None, "confirmation": {"state": "unconfirmed", "basis": "not_checked"}}]}},
     "none"),
])
def test_finding_gate_has_three_gates_in_precedence(finding, gate):
    assert c.finding_gate(finding) == gate


# --- Task 2 -----------------------------------------------------------------
CATALOG = c.load_catalog()

# (language, text, setting, expected). Positives first per language, then the
# negative controls of spec §4.2.
READS = [
    ("python", "        self.always_retry = conf.get('result_backend_always_retry', True)\n",
     "result_backend_always_retry", True),
    ("python", "        self.max_retries = conf.get('result_backend_max_retries', 3)\n",
     "result_backend_max_retries", True),
    ("python", "x = conf.get(\n    'result_backend_always_retry',\n    True)\n", "result_backend_always_retry", True),
    ("python", "max_retries = kwargs.pop('max_retries', 3)\n", "max_retries", True),
    ("python", "t = getattr(settings, 'HTTP_TIMEOUT', 30)\n", "HTTP_TIMEOUT", True),
    ("python", "t = os.getenv('HTTP_TIMEOUT', '30')\n", "HTTP_TIMEOUT", True),
    ("python", "t = os.environ.get(\"HTTP_TIMEOUT\", \"30\")\n", "http_timeout", True),
    ("python", "    backend_always_retry=Option(False, type='bool'),\n", "backend_always_retry", False),
    ("python", "DEFAULTS = {'max_retries': 3}\n", "max_retries", False),
    ("python", "x = conf.result_backend_always_retry\n", "result_backend_always_retry", False),
    ("python", "x = conf.get('result_backend_always_retry')\n", "result_backend_always_retry", False),
    ("python", "x = conf.get('other_setting', True)\n", "result_backend_always_retry", False),
    ("python", "# x = conf.get('result_backend_always_retry', True)\n", "result_backend_always_retry", False),
    ("python", "parser.add_argument('--timeout', default=30)\n", "timeout", False),
    ("typescript", "const PAGE_SIZE = get<number>(\"sync.pageSize\", 100);\n", "sync.pageSize", True),
    ("typescript", "const n = config.get('sync.pageSize', 100);\n", "sync.pageSize", True),
    ("typescript", "const t = process.env.TIMEOUT_MS ?? 30000;\n", "TIMEOUT_MS", True),
    ("typescript", "const t = process.env[\"TIMEOUT_MS\"] || \"30000\";\n", "TIMEOUT_MS", True),
    ("typescript", "const REGISTERED = { \"sync.pageSize\": 500 };\n", "sync.pageSize", False),
    ("typescript", "const on = process.env.API_RETRY_ON_429 === \"true\";\n", "API_RETRY_ON_429", False),
    ("typescript", "// const n = config.get('sync.pageSize', 100);\n", "sync.pageSize", False),
    ("java", "String t = props.getProperty(\"http.timeout\", \"30\");\n", "http.timeout", True),
    ("java", "@Value(\"${http.timeout:30}\") private int timeout;\n", "http.timeout", True),
    ("java", "int n = map.getOrDefault(\"pool.size\", 10);\n", "pool.size", True),
    ("java", "private Duration timeout = Duration.ofSeconds(30);\n", "timeout", False),
    ("java", "String t = System.getenv(\"HTTP_TIMEOUT\");\n", "HTTP_TIMEOUT", False),
    ("yaml", "timeout: ${http.timeout:30}\n", "http.timeout", True),
    ("yaml", "http:\n  timeout: 30\n", "http.timeout", False),
    ("properties", "client.timeout=${http.timeout:30}\n", "http.timeout", True),
    ("properties", "http.timeout=30\n", "http.timeout", False),
]


@pytest.mark.parametrize("lang, text, setting, expected", READS)
def test_fallback_reads(lang, text, setting, expected):
    assert c.reads_with_fallback(text, setting, lang, CATALOG) is expected


def test_javascript_uses_the_typescript_patterns():
    assert c.reads_with_fallback("const t = process.env.T ?? 5;\n", "T", "javascript", CATALOG) is True


def test_every_language_with_setting_reads_has_both_polarities():
    langs = set(CATALOG["setting_reads"])
    for lang in langs:
        polarities = {exp for lg, _, _, exp in READS if lg == lang}
        assert polarities == {True, False}, f"{lang} needs a positive and a negative case"


@pytest.mark.parametrize("setting", ["max_retries (database backend)", "a.b*c", "x)(", "", "   "])
def test_a_name_that_is_prose_or_regex_never_matches_and_never_raises(setting):
    assert c.reads_with_fallback("x = conf.get('a.b*c', 1)\n", setting, "python", CATALOG) in (False,)


@pytest.mark.parametrize("text, setting, lang, expected", [
    ("x = conf.get('result_backend_always_retry', True)\n", "result_backend_always_retry", "python", True),
    ("    backend_always_retry=Option(False, type='bool'),\n", "result_backend_always_retry", "python", True),
    ("        socket_connect_timeout=None,\n", "redis_socket_connect_timeout", "python", True),
    ("    retry=Option(False),\n", "result_backend_always_retry", "python", False),  # one segment
    ("TIMEOUT = 30\n", "TIMEOUT", "python", True),
    ("x = 1  # result_backend_always_retry\n", "result_backend_always_retry", "python", False),
    ('  "sync.pageSize": 500,\n', "sync.pageSize", "typescript", True),
    ("const x = 1;\n", "sync.pageSize", "typescript", False),
    ("pool.size=10\n", "pool.size", None, True),
    ("anything\n", "max_retries (database backend)", "python", False),
])
def test_names_setting(text, setting, lang, expected):
    assert c.names_setting(text, setting, lang) is expected


def test_a_language_without_setting_reads_is_unknown():
    assert c.reads_with_fallback("x := os.Getenv(\"X\")\n", "X", "go", CATALOG) is None
    assert c.reads_with_fallback("x\n", "X", None, CATALOG) is None


# --- Task 3 -----------------------------------------------------------------
import validate  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def _tiny_repo(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    for rel, body in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body) if isinstance(body, bytes) else p.write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


CELERYISH = {
    "backends/database.py": (
        "class DatabaseBackend:\n"
        "    def __init__(self, conf):\n"
        "        # We maintain this behavior by default.\n"
        "        self.always_retry = conf.get('result_backend_always_retry', True)\n"
        "        self.max_retries = conf.get('result_backend_max_retries', 3)\n"),
    "app/defaults.py": (
        "NAMESPACES = dict(\n"
        "    backend_always_retry=Option(False, type='bool'),\n"
        "    backend_max_retries=Option(float('inf'), type='float'),\n"
        ")\n"),
    "conf/blob.properties": b"timeout=\xff\xfe\n",
    "cmd/main.go": "package main\n",
}


def _validator(repo: Path) -> "validate.Validator":
    return validate.Validator(repo, {"hotspots": []}, c.load_catalog())


def test_fallback_read_on_repository_refs(tmp_path):
    v = _validator(_tiny_repo(tmp_path, CELERYISH))
    assert v.fallback_read("backends/database.py:4", "result_backend_always_retry") is True
    assert v.fallback_read("backends/database.py:4-5", "result_backend_max_retries") is True
    assert v.fallback_read("app/defaults.py:2", "result_backend_always_retry") is False
    assert v.fallback_read("conf/blob.properties:1", "timeout") is None      # not UTF-8
    assert v.fallback_read("cmd/main.go:1", "X") is None                     # no setting_reads for go
    assert v.fallback_read("backends/database.py:99", "x") is None           # does not resolve


def test_validate_writes_a_mechanical_confirmation_and_overwrites_a_claimed_one(validated_repo, validated_env):
    out = validated_repo / ".thunderstruck"
    path = next(p for p in sorted((out / "findings").glob("*.json"))
                if any(f.get("preconditions") for f in json.loads(p.read_text())["findings"]))
    doc = json.loads(path.read_text())
    doc["findings"][0]["preconditions"][0]["confirmation"] = {"state": "confirmed", "basis": "registered"}
    path.write_text(json.dumps(doc))
    proc = subprocess.run([sys.executable, str(SCRIPTS / "validate.py"), "--repo", str(validated_repo)],
                          capture_output=True, text=True, env=validated_env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    pre = json.loads(path.read_text())["findings"][0]["preconditions"][0]
    assert pre["confirmation"]["state"] == "unconfirmed"
    assert pre["confirmation"]["by"] == "validator"
    assert pre["confirmation"]["basis"] in ("call_site_fallback", "not_checked")
    assert "call_site" in pre["confirmation"]


def test_save_finding_strips_a_model_written_confirmation(validated_repo, validated_env, tmp_path):
    out = validated_repo / ".thunderstruck"
    path = next(p for p in sorted((out / "findings").glob("*.json"))
                if any(f.get("preconditions") for f in json.loads(p.read_text())["findings"]))
    doc = json.loads(path.read_text())
    doc["findings"][0]["preconditions"][0]["confirmation"] = {"state": "confirmed"}
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"hotspot_id": doc["hotspot_id"], "findings": doc["findings"]}))
    proc = subprocess.run([sys.executable, str(SCRIPTS / "save_finding.py"), "--repo", str(validated_repo),
                           "--id", doc["hotspot_id"], "--from", str(raw)],
                          capture_output=True, text=True, env=validated_env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    saved = json.loads(path.read_text())
    assert all("confirmation" not in p for f in saved["findings"] for p in f.get("preconditions") or [])


def test_names_setting_on_repository_refs(tmp_path):
    v = _validator(_tiny_repo(tmp_path, CELERYISH))
    assert v.names_setting("app/defaults.py:2", "result_backend_always_retry") is True
    assert v.names_setting("app/defaults.py:4", "result_backend_always_retry") is False
    assert v.names_setting("backends/database.py:99", "x") is None


def test_the_capture_hook_strips_a_model_written_confirmation(scanned_copy):
    payloads = ROOT / "tests" / "fixtures" / "hook_payloads"
    doc = json.loads((payloads / "valid.json").read_text())
    message = json.loads(doc["last_assistant_message"])
    message["findings"][0]["preconditions"] = [
        {"setting": "S", "default": "1", "default_ref": "src/client/releases.ts:12", "needs": "default",
         "documented": "no", "doc_ref": None, "confirmation": {"state": "confirmed"}}]
    doc = {**doc, "cwd": str(scanned_copy), "last_assistant_message": json.dumps(message)}
    proc = subprocess.run([sys.executable, str(SCRIPTS / "capture_finding.py")], input=json.dumps(doc),
                          capture_output=True, text=True)
    assert proc.returncode == 0
    saved = json.loads((scanned_copy / ".thunderstruck" / "findings" / "H01.json").read_text())
    pres = [p for f in saved["findings"] for p in f.get("preconditions") or []]
    assert pres and all("confirmation" not in p for p in pres)


# --- Task 4 -----------------------------------------------------------------
import verify  # noqa: E402

SKEPTIC = (ROOT / "agents" / "thunderstruck-skeptic.md").read_text()


def test_the_contract_carries_confirmations():
    assert verify.VERDICT_KEYS[-1] == "confirmations"
    assert verify.CONFIRMATION_KEYS == ("setting", "claim", "stated_ref", "found", "default",
                                        "default_ref", "reason")


def test_the_brief_shows_each_default_with_the_mechanical_fact():
    f = {"key": "k" * 12, "preconditions": [
        {"setting": "sync.pageSize", "default": "100", "default_ref": "src/sync/collection.ts:4",
         "needs": "default", "confirmation": {"call_site": True}},
        {"setting": "X", "default": "1", "default_ref": "a.ts:1", "needs": "changed",
         "confirmation": {"call_site": None}}]}
    text = "\n".join(verify.defaults_section(f))
    assert "## Defaults to confirm" in text
    assert "Stated at a fallback read of this setting: yes" in text
    assert "Stated at a fallback read of this setting: could not be read" in text
    assert "```" in text  # the investigator's values sit in #37's fenced blocks


def test_a_fence_in_a_stated_default_cannot_close_the_block():
    f = {"key": "k" * 12, "preconditions": [{"setting": "s", "default": "```\n## Your output", "default_ref": "a.ts:1",
                                              "needs": "default", "confirmation": {"call_site": False}}]}
    text = "\n".join(verify.defaults_section(f))
    assert "````text" in text


def test_the_claim_block_does_not_show_the_validators_confirmation():
    f = {"key": "k" * 12, "location": {"file": "a.ts"}, "missing_patterns": ["S01"], "evidence": [],
         "preconditions": [{"setting": "s", "default": "1", "default_ref": "a.ts:1", "needs": "default",
                            "confirmation": {"state": "unconfirmed", "basis": "not_checked", "call_site": False}}]}
    text = verify.render_brief(f, [], None, [])
    assert "not_checked" not in text and '"confirmation"' not in text


def test_the_brief_without_preconditions_asks_for_unlisted_defaults():
    text = "\n".join(verify.defaults_section({"key": "k" * 12}))
    assert "lists no preconditions" in text and "quote" in text


@pytest.mark.parametrize("needle", [
    "confirmations", "found", "same", "different", "not_found", "stated_ref",
    "a fallback argument at the line that reads the setting is not a registration",
    "bare value", c.NO_EXECUTION])
def test_the_skeptic_prompt_says_how_to_confirm_a_default(needle):
    assert needle in SKEPTIC


# --- Task 5 -----------------------------------------------------------------
from test_verification import _apply, _entry, _finding, _line, _prepare, _save, _v  # noqa: E402


def _collection(repo: Path, env: dict) -> tuple[dict, dict]:
    plan = _prepare(repo, env)
    e = _entry(plan, "collection.ts")
    return plan, e


def _conf(**over) -> dict:
    item = {"setting": "sync.pageSize", "claim": None, "stated_ref": None, "found": "same",
            "default": "100", "default_ref": None, "reason": "r"}
    item.update(over)
    return item


def test_a_confirmation_at_the_fallback_read_confirms_nothing(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    read = _line(validated_repo, "src/sync/collection.ts", "sync.pageSize")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(default_ref=f"src/sync/collection.ts:{read}")]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "inconclusive"
    assert check["reason"].startswith("The check upheld this claim, but it rests on a default no one confirmed: sync.pageSize")
    pre = _finding(validated_repo, e["key"])["preconditions"][0]
    assert (pre["confirmation"]["state"], pre["confirmation"]["basis"]) == ("unconfirmed", "call_site_fallback")


def test_a_registry_that_disagrees_contradicts_and_keeps_both(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(found="different", default="500", default_ref=f"src/config/settings.ts:{reg}")]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "inconclusive"
    [item] = check["confirmations"]
    assert (item["default"], item["confirmation"]["basis"]) == ("500", "contradicted")
    pre = _finding(validated_repo, e["key"])["preconditions"][0]
    assert pre["default"] == "100" and pre["confirmation"]["basis"] == "contradicted"


def test_a_registry_that_agrees_confirms_and_upheld_stands(validated_repo, validated_env, tmp_path):
    plan = _prepare(validated_repo, validated_env)
    e = _entry(plan, "api.ts")
    f = _finding(validated_repo, e["key"])
    pre = f["preconditions"][0]
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(setting=pre["setting"], default=pre["default"], default_ref=pre["default_ref"])]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert check["status"] == "upheld"
    assert _finding(validated_repo, e["key"])["preconditions"][0]["confirmation"]["state"] == "confirmed"


def test_items_that_break_the_contract_are_dropped_and_named(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "inconclusive", confirmations=[
        {"setting": "sync.pageSize", "found": "maybe"},
        _conf(setting="unlisted.thing", claim="a paraphrase not in the finding"),
        _conf(default_ref="src/nowhere.ts:1"),
        _conf()]))
    check = _apply(validated_repo, validated_env)[e["key"]]
    assert "Ignored: confirmations[0]" in check["reason"]
    assert "confirmations[1]" in check["reason"]
    [item] = check["confirmations"]  # [2] kept as unresolved; [3] names the same setting twice
    assert item["confirmation"]["basis"] == "unresolved" and item["default_ref_error"]
    assert "confirmations[3]" in check["reason"]


def test_a_reused_upheld_without_confirmations_settles_inconclusive(validated_repo, validated_env, tmp_path):
    """Review focus 4: a ledger entry written before #57."""
    plan, e = _collection(validated_repo, validated_env)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(found="same", default="100", default_ref=f"src/config/settings.ts:{reg}")]))
    _apply(validated_repo, validated_env)
    ledger_path = validated_repo / ".thunderstruck" / "checks" / "ledger.json"
    ledger = json.loads(ledger_path.read_text())
    ledger["entries"][e["key"]]["check"].pop("confirmations")
    ledger["entries"][e["key"]]["check"]["status"] = "upheld"
    ledger_path.write_text(json.dumps(ledger))
    again = _prepare(validated_repo, validated_env)
    assert _entry(again, "collection.ts")["action"] == "reuse"
    assert _apply(validated_repo, validated_env)[e["key"]]["status"] == "inconclusive"


def test_claim_hash_ignores_confirmation_and_the_registry_is_in_the_ledger(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    f = _finding(validated_repo, e["key"])
    g = json.loads(json.dumps(f))
    g["preconditions"][0]["confirmation"] = {"state": "confirmed"}
    assert verify.claim_hash(f) == verify.claim_hash(g)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "inconclusive", confirmations=[
        _conf(found="different", default="500", default_ref=f"src/config/settings.ts:{reg}")]))
    _apply(validated_repo, validated_env)
    ledger = json.loads((validated_repo / ".thunderstruck" / "checks" / "ledger.json").read_text())["entries"]
    assert "src/config/settings.ts" in ledger[e["key"]]["files"]


# --- Task 6 -----------------------------------------------------------------
FR015_LIKE = {
    "key": "6345778fa223", "location": {"file": "backends/database.py", "lines": "4-5"},
    "missing_patterns": ["S04"],
    "failure_mode": "Workers retry every DatabaseError and dispose the pool before each retry.",
    "trigger_condition": "The database returns errors.",
    "amplifier": "Every DatabaseError is treated as retryable. always_retry defaults to True with 3 retries.",
    "blast_radius": "Result storage.", "how_to_verify": "Run a burst.",
    "evidence": [{"type": "code", "ref": "backends/database.py:4-5",
                  "note": "always_retry is on by default with 3 retries"}],
    "confidence": "medium", "confidence_rationale": "-",
}


def _settle(repo: Path, verdict: dict) -> dict:
    plan = {"generated_at": "t", "head": "h", "model": "sonnet",
            "findings": [{"key": FR015_LIKE["key"], "action": "check", "brief_hash": "b"}]}
    result = {**verdict, "key": FR015_LIKE["key"], "brief_hash": "b", "scan": "t"}
    return verify.settle(FR015_LIKE, plan["findings"][0], result, verify.Resolver(repo, None), plan, None)


def _conf015(found: str, default: str, ref: str) -> dict:
    return {"setting": "result_backend_always_retry", "claim": "always_retry defaults to True with 3 retries",
            "stated_ref": "backends/database.py:4-5", "found": found, "default": default,
            "default_ref": ref, "reason": "r"}


def test_refuter_a_upholds_from_the_fallback_line_and_cannot(tmp_path):
    repo = _tiny_repo(tmp_path, CELERYISH)
    check = _settle(repo, {"verdict": "upheld", "reason": "Retries are on by default.", "evidence": [],
                           "confirmations": [_conf015("same", "True", "backends/database.py:4")]})
    assert check["status"] == "inconclusive"
    [item] = check["confirmations"]
    assert item["stated_call_site"] is True and item["default_call_site"] is True
    assert (item["confirmation"]["state"], item["confirmation"]["basis"]) == ("unconfirmed", "call_site_fallback")


def test_refuter_b_cites_the_registry_and_contradicts(tmp_path):
    repo = _tiny_repo(tmp_path, CELERYISH)
    check = _settle(repo, {
        "verdict": "narrowed", "reason": "No retries on defaults.",
        "holds": "Every DatabaseError is classified retryable when a user opts in.",
        "refuted_claims": [{"field": "amplifier", "claim": "always_retry defaults to True with 3 retries",
                            "fact": "The registered default is False.", "evidence": [0]}],
        "evidence": [{"type": "code", "ref": "app/defaults.py:2", "note": "registered False"}],
        "confirmations": [_conf015("different", "False", "app/defaults.py:2")]})
    assert check["status"] == "narrowed"
    [item] = check["confirmations"]
    assert (item["default"], item["confirmation"]["basis"]) == ("False", "contradicted")


# --- Task 7 -----------------------------------------------------------------
import report  # noqa: E402


def _report(repo: Path, env: dict) -> dict:
    proc = subprocess.run([sys.executable, str(SCRIPTS / "report.py"), "--repo", str(repo)],
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads((repo / ".thunderstruck" / "report.json").read_text())


def test_without_verification_confirmations_are_mechanical_only(validated_repo, validated_env, tmp_path):
    """Review focus 3: findings files still carry an earlier skeptic's confirmations."""
    plan, e = _collection(validated_repo, validated_env)
    api = _entry(plan, "api.ts")
    pre = _finding(validated_repo, api["key"])["preconditions"][0]
    _save(validated_repo, validated_env, tmp_path, _v(api["key"], "upheld", confirmations=[
        _conf(setting=pre["setting"], default=pre["default"], default_ref=pre["default_ref"])]))
    _apply(validated_repo, validated_env)
    (validated_repo / ".thunderstruck" / "checks" / "run.json").unlink()  # this scan did not verify
    data = _report(validated_repo, validated_env)
    bases = {p["confirmation"]["basis"] for f in data["findings"] for p in f.get("preconditions") or []}
    assert bases <= {"call_site_fallback", "not_checked"}
    assert data["counts"]["defaults"]["confirmed"] == 0


def test_the_report_orders_three_gates_and_counts_defaults(validated_repo, validated_env):
    data = _report(validated_repo, validated_env)
    gates = [f["gate"] for f in data["findings"]]
    assert gates == sorted(gates, key=c.GATES.index)
    assert set(data["counts"]["gate"]) == set(c.GATES)
    d = data["counts"]["defaults"]
    assert set(d["basis"]) == set(c.CONFIRMATION_BASES)
    assert d["confirmed"] + d["unconfirmed"] == sum(d["basis"].values())
    index = json.loads((validated_repo / ".thunderstruck" / "index.json").read_text())
    pres = [p for entry in index["files"].values() for f in entry["findings"] for p in f.get("preconditions") or []]
    assert pres and all(p["confirmation"] in c.CONFIRMATION_STATES for p in pres)


def test_a_contradicted_default_keeps_both_with_their_locations(validated_repo, validated_env, tmp_path):
    plan, e = _collection(validated_repo, validated_env)
    reg = _line(validated_repo, "src/config/settings.ts", "\"sync.pageSize\": 500")
    _save(validated_repo, validated_env, tmp_path, _v(e["key"], "upheld", confirmations=[
        _conf(found="different", default="500", default_ref=f"src/config/settings.ts:{reg}")]))
    _apply(validated_repo, validated_env)
    data = _report(validated_repo, validated_env)
    f = next(x for x in data["findings"] if x["key"] == e["key"])
    p = f["preconditions"][0]
    [item] = f["check"]["confirmations"]
    assert (p["default"], p["default_ref"]) != (item["default"], item["default_ref"])
    assert item["default_url"] is None or "settings.ts" in item["default_url"]
    assert f["gate"] == "unconfirmed_default"
