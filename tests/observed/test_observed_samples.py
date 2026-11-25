"""Every kind of observation fires on its positive samples and stays silent on
its negative ones, per language (#6, AC-8, AC-9).

Samples live in tests/observed/samples/<kind>/<language>/{positive,negative}_<topic>.<ext>.
A positive has a sibling `<file>.expected`: a first line `# forms: <id>, ...`
naming the shipped forms it exercises, then one `<kind>:<value>:<line>` per
line, sorted. Discovered from the tree; there is no list to update.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

import observed

SAMPLES = Path(__file__).parent / "samples"
EXT_LANG = {".ts": "typescript", ".js": "javascript", ".py": "python", ".java": "java",
            ".yaml": "yaml", ".yml": "yaml", ".properties": "properties"}
SECRET_LANGS = ("typescript", "python", "java", "yaml")


def _cases() -> list[tuple[str, str, str, Path]]:
    out = []
    for kind_dir in sorted(p for p in SAMPLES.iterdir() if p.is_dir()):
        for lang_dir in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
            for sample in sorted(lang_dir.iterdir()):
                if sample.suffix in EXT_LANG:
                    out.append((kind_dir.name, lang_dir.name, sample.stem, sample))
    return out


CASES = _cases()


@pytest.fixture(scope="module")
def rules():
    return observed.load_rules()


def expected_of(path: Path) -> tuple[list[str], list[str]]:
    lines = (path.parent / (path.name + ".expected")).read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].startswith("# forms:"), f"{path}.expected needs a '# forms:' line"
    forms = [f.strip() for f in lines[0][len("# forms:"):].split(",") if f.strip()]
    return forms, [line for line in lines[1:] if line.strip()]


def project(extraction, kind: str | None = None) -> list[str]:
    return sorted(f"{o['kind']}:{o['value']}:{o['line']}" for o in extraction.observations
                  if kind is None or o["kind"] == kind)


def test_samples_exist():
    assert CASES


@pytest.mark.parametrize("kind,lang,stem,path", CASES,
                         ids=[f"{k}-{lang}-{s}" for k, lang, s, _ in CASES])
def test_sample(rules, kind, lang, stem, path):
    text = path.read_text(encoding="utf-8")
    got = observed.observe_text(text, EXT_LANG[path.suffix], f"src/{path.name}", rules, [])
    if stem.startswith("positive"):
        _, want = expected_of(path)
        assert project(got) == want, f"{path}:\n{text}"
    else:
        assert project(got, kind) == [], f"{kind} observed in negative sample {path}"


def shipped_kinds(rules) -> set[tuple[str, str]]:
    """(kind, language) pairs that have at least one shipped form."""
    pairs = {("secret", lang) for lang in SECRET_LANGS}
    for lang, kinds in rules["forms"].items():
        if "read" in kinds or any(f[0].startswith("config.env.") for f in kinds.get("config", [])):
            pairs.add(("env", lang))
        if ("request" in kinds and "response" in kinds) or "mesh" in kinds \
                or any(f[0] == "config.host.key" for f in kinds.get("config", [])):
            pairs.add(("host", lang))
    return pairs


def test_every_kind_has_both_samples(rules):
    missing = [f"{kind}/{lang}/{pol}" for kind, lang in sorted(shipped_kinds(rules))
               for pol in ("positive", "negative")
               if not any(c[0] == kind and c[1] == lang and c[2].startswith(pol) for c in CASES)]
    assert not missing, f"missing samples: {missing}"


def with_test_host_forms(rules: dict) -> dict:
    """A rules dict with a request and a response form no calibration measured.
    Used only here, to exercise the host machinery; never in observed.yaml."""
    out = copy.deepcopy(rules)
    ts = out["forms"].setdefault("typescript", {})
    ts["request"] = [("test.request", re.compile(r"\bfetch\("), None)]
    ts["response"] = [("test.response", re.compile(r"\.json\(\)"), None)]
    return out


SAFETY = """\
export async function load() {
  const a = await fetch("postgres://app:hunter2@db.internal/app/secret-path");
  const b = await fetch("postgres://u:p@ss/w@db.internal/x");
  const s = await sm.getSecretValue({ SecretId: "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd" });
  return [await a.json(), await b.json(), s];
}
"""


def test_only_the_host_of_a_url_is_kept(rules):
    got = observed.observe_text(SAFETY, "typescript", "src/a.ts", with_test_host_forms(rules), [])
    assert project(got) == ["host:db.internal:2", "host:db.internal:3"]
    blob = json.dumps([got.observations, got.dropped])
    for leak in ("hunter2", "p@ss", "ss/w", "secret-path", "/app", "/x",
                 "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd"):
        assert leak not in blob
    assert got.dropped["secret"] == 1


def test_comment_beside_code_yields_only_the_code_line(rules):
    text = ('// fetch("https://ledger.internal/v1/x")\n'
            'const r = await fetch("https://ledger.internal/v1/x"); r.json();\n')
    got = observed.observe_text(text, "typescript", "src/a.ts", with_test_host_forms(rules), [])
    assert project(got) == ["host:ledger.internal:2"]


def test_api_name_or_path_qualifies_a_url(rules):
    text = ('const apiBase = "https://ledger.internal";\n'
            'const footer = "https://social.internal";\n'
            'const u = new URL("https://rates.internal");\n'
            'const r = await fetch(apiBase); r.json();\n')
    got = observed.observe_text(text, "typescript", "src/a.ts", with_test_host_forms(rules), [])
    assert project(got) == ["host:ledger.internal:1", "host:rates.internal:3"]


def test_own_host_and_subdomain_are_excluded_and_counted(rules):
    text = ('const a = await fetch("https://fixture-app.internal/v1/x");\n'
            'const b = await fetch("https://api.fixture-app.internal/v1/x");\n'
            'const c = await fetch("https://ledger.internal/v1/x");\n'
            'a.json();\n')
    got = observed.observe_text(text, "typescript", "src/a.ts", with_test_host_forms(rules),
                                ["fixture-app.internal"])
    assert project(got) == ["host:ledger.internal:3"]
    assert got.excluded_own_host == 2
    assert "fixture-app" not in json.dumps(got.observations)


def test_is_own_host():
    assert observed.is_own_host("shop.internal", ["shop.internal"])
    assert observed.is_own_host("a.shop.internal", ["shop.internal"])
    assert not observed.is_own_host("myshop.internal", ["shop.internal"])
    assert observed.is_own_host("x.api.shop.internal", ["*.api.shop.internal"])
    assert not observed.is_own_host("api.shop.internal", ["*.api.shop.internal"])


def test_ref_grammar():
    assert observed.ref({"kind": "env", "value": "X_URL", "file": "src/a.ts", "line": 3}) \
        == "observed env:X_URL src/a.ts:3"


def test_reserved_hosts_are_never_observed_even_at_a_call_site(rules):
    path = SAMPLES / "host" / "typescript" / "negative_reserved.ts"
    got = observed.observe_text(path.read_text(), "typescript", "src/r.ts",
                                with_test_host_forms(rules), [])
    assert project(got, "host") == []
    assert got.dropped["host"] == 1   # `${HOST}`; `{{ .Values.host }}` has no path, so rule 2 skips it first


def test_userinfo_never_reaches_into_the_query(rules):
    text = ('const a = await fetch("https://u:p@api.internal/send?to=ops@corp.internal");\n'
            'a.json();\n')
    got = observed.observe_text(text, "typescript", "src/a.ts", with_test_host_forms(rules), [])
    assert project(got) == ["host:api.internal:1"]
