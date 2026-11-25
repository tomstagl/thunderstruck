"""Env vars in code count by use in a call; in configuration, by name (#6, spec §2.2)."""

from __future__ import annotations

import pytest

import observed


@pytest.fixture(scope="module")
def rules():
    return observed.load_rules()


def env(text: str, rules, lang: str = "typescript", rel: str = "src/a.ts") -> list[str]:
    got = observed.observe_text(text, lang, rel, rules, [])
    return [f"{o['value']}:{o['line']}" for o in got.observations if o["kind"] == "env"]


def test_a_direct_read_is_not_a_shipped_form(rules):
    assert env("export const r = fetch(process.env.AUTH_SERVER);\n", rules) == []
    assert env('export const r = fetch(process.env["AUTH_SERVER"]);\n', rules) == []


def test_one_variable_observes_the_call_line_not_the_read(rules):
    text = ("const { AUTH_SERVER } = process.env;\n" + "\n" * 7
            + "export const r = fetch(`${AUTH_SERVER}/verify`);\n")
    assert env(text, rules) == ["AUTH_SERVER:9"]


def test_a_name_used_in_three_calls_gives_three(rules):
    text = ("const { AUTH_SERVER } = process.env;\n"
            "fetch(`${AUTH_SERVER}/a`);\nfetch(`${AUTH_SERVER}/b`);\nfetch(AUTH_SERVER);\n")
    assert env(text, rules) == ["AUTH_SERVER:2", "AUTH_SERVER:3", "AUTH_SERVER:4"]


def test_destructuring_with_a_default_and_with_an_alias(rules):
    text = ("const { CART_ADDR = '' } = process.env;\n"
            "const { SHIPPING_ADDR: ship } = process.env;\n"
            "const c = new CartServiceClient(CART_ADDR, ChannelCredentials.createInsecure());\n"
            "const q = fetch(`${ship}/get-quote`);\n")
    assert env(text, rules) == ["CART_ADDR:3", "SHIPPING_ADDR:4"]


def test_a_client_without_credentials_is_not_a_connect_form(rules):
    text = "const { X_ADDR } = process.env;\nconst f = new FooClient(X_ADDR);\n"
    assert env(text, rules) == []


def test_a_use_before_the_read_does_not_count(rules):
    text = "fetch(AUTH_SERVER);\nconst { AUTH_SERVER } = process.env;\n"
    assert env(text, rules) == []


def test_a_property_of_the_same_name_is_not_the_variable(rules):
    text = "const { AUTH_SERVER } = process.env;\nfetch(cfg.AUTH_SERVER);\n"
    assert env(text, rules) == []


@pytest.mark.parametrize("text", [
    "const { LOG_LEVEL } = process.env;\nexport const l = LOG_LEVEL;\n",
    "const { S3_URL } = process.env;\nexport const s = new S3Client({ endpoint: S3_URL });\n",
    'const { S3_URL } = process.env;\nconst b = S3_URL + "/v1";\nfetch(b);\n',
    "const { AUTH_URL } = process.env;\ncfg.auth = AUTH_URL;\nfetch(cfg.auth);\n",
    "const { X_URL } = process.env;\nexport const X = X_URL;\n",
], ids=["unused", "sdk-client", "second-hop", "object-field", "export-only"])
def test_documented_gaps_are_not_observed(rules, text):
    assert env(text, rules) == []


def test_a_read_in_one_file_used_in_another_is_not_observed(rules):
    assert env("const { X_URL } = process.env;\nexport { X_URL };\n", rules, rel="src/config.ts") == []
    assert env('import { X_URL } from "./config";\nfetch(X_URL);\n', rules, rel="src/use.ts") == []


def test_an_unbalanced_call_yields_nothing_and_does_not_raise(rules):
    text = "const { X_URL } = process.env;\nfetch(" + "a(" * 1000 + "X_URL" + "\n"
    assert env(text, rules) == []


def test_call_spans_balance_outside_strings(rules):
    text = 'fetch(")" + x, (y))'
    assert observed.call_spans(text, rules, "typescript") == [(5, len(text))]


def test_config_by_name(rules):
    k8s = ("spec:\n  containers:\n    - name: a\n      env:\n"
           "        - name: LEDGER_ADDR\n        - name: LEDGER_ADDRESS\n")
    assert env(k8s, rules, "yaml", "deploy/a.yaml") == ["LEDGER_ADDR:5"]
    placeholders = "a: ${PRODUCT_CATALOG_ADDR:localhost:3550}\nb: ${LEDGER_ADDRESS}\nc: ${LOG_LEVEL}\n"
    assert env(placeholders, rules, "yaml", "app.yaml") == ["PRODUCT_CATALOG_ADDR:1"]


def test_unmeasured_config_forms_are_not_observed(rules):
    assert env("a=${PRODUCT_CATALOG_ADDR}\n", rules, "properties", "app.properties") == []
    java = 'class A { @Value("${payments.base-url}") String base; }\n'
    assert env(java, rules, "java", "src/A.java") == []


def test_a_placeholder_in_an_unparseable_yaml_still_counts(rules):
    text = "{{- if .Values.on }}\nurl: ${LEDGER_URL}\n{{- end }}\n"
    got = observed.observe_text(text, "yaml", "chart/t.yaml", rules, [])
    assert [o["value"] for o in got.observations] == ["LEDGER_URL"]
    assert got.yaml_failed


# --- Repair round (code review) ----------------------------------------------

@pytest.mark.parametrize("text", [
    'const { PAY_URL } = process.env;\nfetch("PAY_URL");\n',
    "const { PAY_URL } = process.env;\nfetch('see PAY_URL docs');\n",
    "const { PAY_URL } = process.env;\nfetch(`PAY_URL is ${other}`);\n",
    "const { PAY_URL } = process.env;\nfetch(x, { PAY_URL: 1 });\n",
], ids=["double-quoted", "single-quoted", "template-text", "object-key"])
def test_a_string_or_key_equal_to_the_name_is_not_a_use(rules, text):
    assert env(text, rules) == []


def test_a_template_substitution_is_still_a_use(rules):
    text = "const { PAY_URL } = process.env;\nfetch(`${PAY_URL}/v1`, { a: PAY_URL });\n"
    assert env(text, rules) == ["PAY_URL:2"]


@pytest.mark.parametrize("text", ["a: &x [*x]\n",
                                  "a: &a [1, 2]\nb: &b [*a, *a, *a]\nc: &c [*b, *b, *b]\n"])
def test_recursive_and_nested_yaml_aliases_neither_crash_nor_hang(rules, text):
    got = observed.observe_text(text + "spec:\n  containers: []\n", "yaml", "a.yaml", rules, [])
    assert got.observations == []
