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
