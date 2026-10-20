"""Boundary rules (#58): a boundary is a call, never a name.

Samples live in tests/boundaries/samples/<label-slug>/<language>/. In a
positive_<shape> sample every line that must be tagged ends with a
`boundary: <label>` comment, and the matcher must tag exactly those lines
with exactly those labels. Any other stem must not be tagged with the
directory's label, and samples under none/ must not be tagged at all. An
`own-packages: a, b` comment names the packages the sample's project owns;
without it the project owns none. Comments are blank to the matcher, so
neither marker can change what it finds. Samples are discovered from the
tree; there is no list to update.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from detectors import find_boundaries

SAMPLES = Path(__file__).parent / "samples"
EXT_LANG = {".py": "python", ".ts": "typescript", ".java": "java"}
LABELS = {"http": "HTTP", "database": "database", "queue-messaging": "queue/messaging",
          "llm": "LLM", "cloud-sdk": "cloud SDK", "filesystem": "filesystem",
          "scheduler": "scheduler"}
NONE_SHAPES = {"python": ("comment", "docstring", "import"),
               "typescript": ("comment", "import"), "java": ("comment", "import")}


MARK = re.compile(r"(?:#|//)\s*boundary:\s*(.+?)\s*$")
OWN = re.compile(r"^\s*(?:#|//)\s*own-packages:\s*(.+?)\s*$", re.M)


def _marked(text: str) -> set[tuple[int, str]]:
    return {(i, m.group(1)) for i, line in enumerate(text.split("\n"), 1)
            if (m := MARK.search(line))}


def _own(text: str, lang: str) -> dict[str, list[str]]:
    m = OWN.search(text)
    return {lang: m.group(1).replace(",", " ").split()} if m else {}


def _cases() -> list[tuple[str, str, str, Path]]:
    return [(p.parent.parent.name, p.parent.name, p.stem, p)
            for p in sorted(SAMPLES.glob("*/*/*")) if p.suffix in EXT_LANG]


CASES = _cases()


@pytest.mark.parametrize("slug,lang,stem,path", CASES,
                         ids=[f"{s}-{lang}-{stem}" for s, lang, stem, _ in CASES])
def test_sample(catalog, slug, lang, stem, path):
    text = path.read_text(encoding="utf-8")
    found = find_boundaries(catalog, f"src/{path.name}", text, lang, _own(text, lang))
    assert found is not None, f"no boundary rules for {lang}"
    got = {(b.line, b.label) for b in found}
    seen = [(b.label, b.rule_id, b.line) for b in found]
    marked = _marked(text)
    if slug == "none":
        assert not found and not marked, f"{path} must cross no boundary, got {seen}"
    elif stem.startswith("positive"):
        assert any(label == LABELS[slug] for _, label in marked), (
            f"{path} marks no line {LABELS[slug]!r}")
        assert got == marked, f"{path}: marked {sorted(marked)}, tagged {seen}"
    else:
        assert not marked, f"{path}: a negative sample marks no line"
        assert LABELS[slug] not in {b.label for b in found}, (
            f"{path} is wrongly tagged {LABELS[slug]!r}: {seen}")


def test_every_label_with_a_rule_has_both_samples(catalog):
    missing = []
    for lang, rules in catalog["boundaries"].items():
        for label in sorted({r["label"] for r in rules}):
            slug = next(s for s, lb in LABELS.items() if lb == label)
            for polarity in ("positive", "negative"):
                if not any(c[0] == slug and c[1] == lang and c[2].startswith(polarity)
                           for c in CASES):
                    missing.append(f"{slug}/{lang}/{polarity}")
        for shape in NONE_SHAPES.get(lang, ()):
            if not any(c[0] == "none" and c[1] == lang and c[2] == f"negative_{shape}"
                       for c in CASES):
                missing.append(f"none/{lang}/negative_{shape}")
    assert not missing, "boundary rules without samples: " + ", ".join(missing)


def test_boundary_rules_are_well_formed(catalog):
    seen, bad = set(), []
    for lang, rules in catalog["boundaries"].items():
        for rule in rules:
            if rule["id"] in seen:
                bad.append(f"duplicate id {rule['id']}")
            seen.add(rule["id"])
            if rule.get("label") not in LABELS.values():
                bad.append(f"{rule['id']}: unknown label {rule.get('label')!r}")
            for key in ("pattern", "require"):
                if key in rule:
                    try:
                        re.compile(rule[key])
                    except re.error as exc:
                        bad.append(f"{rule['id']}.{key}: {exc}")
    assert not bad, "\n".join(bad)


def test_a_language_without_rules_is_not_looked_at(catalog):
    assert find_boundaries(catalog, "deploy/values.yaml", "url: http://x\n", "yaml", {}) is None


def test_javascript_uses_the_typescript_rules(catalog):
    found = find_boundaries(catalog, "a.mjs", "const r = await fetch(url);\n", "javascript", {})
    assert [(b.label, b.line) for b in found] == [("HTTP", 1)]


def test_one_label_per_line_and_line_order(catalog):
    src = ("import requests\n"
           "def sync(session):\n"
           "    rows = session.query(Row).all()\n"
           "    requests.post('https://x', json=rows, timeout=3)\n")
    found = find_boundaries(catalog, "a.py", src, "python", {})
    assert [(b.label, b.line, b.rule_id) for b in found] == [
        ("database", 3, "B-py-session"), ("HTTP", 4, "B-py-requests")]
    assert found[1].snippet == "requests.post('https://x', json=rows, timeout=3)"


def test_library_name_with_a_non_http_method_is_not_http(catalog):
    src = ("import requests\n"
           "from celery.worker.state import requests as active\n"
           "active.pop(r.id, None)\n"
           "requests.pop(r.id, None)\n"
           "requests.get(url, timeout=3)\n")
    found = find_boundaries(catalog, "a.py", src, "python", {})
    assert [(b.label, b.line) for b in found] == [("HTTP", 5)]


def test_crlf_lines_still_match(catalog):
    src = "import requests\r\nrequests.get(url, timeout=3)\r\n"
    found = find_boundaries(catalog, "a.py", src, "python", {})
    assert [(b.label, b.line) for b in found] == [("HTTP", 2)]


def test_a_malformed_rule_is_skipped(catalog):
    broken = {"boundaries": {"python": [{"id": "B-x", "label": "HTTP", "pattern": "("},
                                        *catalog["boundaries"]["python"]]},
              "aliases": {}}
    found = find_boundaries(broken, "a.py", "import requests\nrequests.get(u)\n", "python", {})
    assert [b.rule_id for b in found] == ["B-py-requests"]


@pytest.mark.parametrize("lang,src,own", [
    ("python", "import celery\nfrom celery.app import task\nx.apply_async()\n", ["celery"]),
    ("python", "import celery.app.task as t\nx.delay()\n", ["celery"]),
    ("python", "import celery, os\nx.delay()\n", ["celery"]),
    ("python", "import celery\r\nx.delay()\r\n", ["celery"]),
    ("typescript", 'import { S3Client } from "@aws-sdk/client-s3";\n'
                   'await client.send(new GetObjectCommand({}));\n', ["@aws-sdk/client-s3"]),
    ("typescript", 'const s3 = require("@aws-sdk/client-s3");\n'
                   'await client.send(new GetObjectCommand({}));\n', ["@aws-sdk/client-s3"]),
    ("java", "import org.springframework.web.client.RestTemplate;\n"
             "class A { P g() { return rest.getForObject(u, P.class); } }\n",
     ["org.springframework.web.client"]),
    ("java", "import org.springframework.web.client.*;\n"
             "class A { P g() { return rest.getForObject(u, P.class); } }\n",
     ["org.springframework.web.client"]),
])
def test_an_import_of_the_projects_own_package_never_satisfies_a_gate(catalog, lang, src, own):
    assert find_boundaries(catalog, "a", src, lang, {lang: own}) == []
    assert find_boundaries(catalog, "a", src, lang, {}), "the gate opens without own packages"


def test_a_library_import_beside_an_own_import_still_satisfies_the_gate(catalog):
    src = "import proj, requests\nfrom proj import api\nrequests.get(u, timeout=3)\n"
    found = find_boundaries(catalog, "a.py", src, "python", {"python": ["proj"]})
    assert [(b.label, b.line) for b in found] == [("HTTP", 3)]


def test_unknown_own_packages_skip_gated_rules_only(catalog):
    src = "import requests\nrequests.get(u, timeout=3)\ncur.execute(q)\n"
    found = find_boundaries(catalog, "a.py", src, "python", None)
    assert [(b.rule_id, b.line) for b in found] == [("B-py-execute", 3)]
