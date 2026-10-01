"""#3: report.json -> a self-contained, inert, deterministic report.html."""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import report_html
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "report_html.py"
TEMPLATE = ROOT / "templates" / "report.html"


def _scan(repo: Path, plugin_root: Path) -> Path:
    """A validated finding, report.py run: .thunderstruck/report.json exists."""
    hid, doc = _valid_finding(repo, _hotspots(repo))
    _write_finding(repo, hid, doc)
    assert _validate(repo, plugin_root).returncode == 0
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(repo)], check=True, capture_output=True)
    return repo / ".thunderstruck"


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo)],
                          capture_output=True, text=True, cwd=str(repo))


def _embedded(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="thunderstruck-report">(.*?)</script>',
                  html, re.S)
    assert m, "no data block"
    return json.loads(m[1])


# ------------------------------------------------------------------ embed --


HOSTILE = {"a": "</script><script>alert(1)</script>", "b": "<!-- x -->", "c": "a & b",
           "d": "line sep para", "e": "</SCRIPT >", "f": ["ü", None, 1.5]}


def test_embed_cannot_close_or_comment_its_element():
    out = report_html.embed(HOSTILE)
    for raw in ("<", ">", "&", " ", " "):
        assert raw not in out, repr(raw)


def test_embed_round_trips():
    assert json.loads(report_html.embed(HOSTILE)) == HOSTILE


# ----------------------------------------------------------------- render --


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


@pytest.mark.parametrize("placeholder", [report_html.PLACEHOLDER, report_html.HASH_PLACEHOLDER])
@pytest.mark.parametrize("count", [0, 2])
def test_render_needs_each_placeholder_exactly_once(placeholder, count):
    template = _template().replace(placeholder, "")
    template = template.replace("</body>", placeholder * count + "</body>")
    with pytest.raises(report_html.c.ThunderstruckError, match="exactly one"):
        report_html.render({"findings": []}, template)


def test_csp_hash_is_the_app_script():
    html = report_html.render({"findings": []}, _template())
    scripts = re.findall(r'<script id="thunderstruck-app">(.*?)</script>', html, re.S)
    assert len(scripts) == 1
    digest = base64.b64encode(hashlib.sha256(scripts[0].encode("utf-8")).digest()).decode()
    csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', html)[1]
    assert f"script-src 'sha256-{digest}'" in csp
    assert report_html.HASH_PLACEHOLDER not in html


def test_data_cannot_inject_a_placeholder():
    """A report value that spells a placeholder stays data."""
    data = {"findings": [], "x": report_html.HASH_PLACEHOLDER + report_html.PLACEHOLDER}
    html = report_html.render(data, _template())
    assert _embedded(html) == data


def test_csp_meta_is_the_first_element_of_head():
    head = _template().split("<head>", 1)[1].lstrip()
    assert head.startswith('<meta http-equiv="Content-Security-Policy" content="'
                           "default-src 'none'; script-src '__THUNDERSTRUCK_SCRIPT_HASH__'; "
                           "style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; "
                           "font-src 'none'; base-uri 'none'; form-action 'none'\">")


# -------------------------------------------------------------- page_data --


def test_page_data_drops_the_local_path():
    report = {"repo": {"root": "/home/someone/src/shop", "head": "abc", "branch": "main"},
              "findings": [{"id": "FR-001"}]}
    before = json.dumps(report, sort_keys=True)
    page = report_html.page_data(report)
    assert page["repo"] == {"name": "shop", "head": "abc", "branch": "main"}
    assert page["findings"] == report["findings"]
    assert json.dumps(report, sort_keys=True) == before, "input was mutated"


# ---------------------------------------------------------------- pipeline --


def test_renders_deterministically_without_the_checkout_path(scanned_copy, plugin_root):
    out = _scan(scanned_copy, plugin_root)
    first = _run(scanned_copy)
    assert first.returncode == 0, first.stderr
    html = (out / "report.html").read_bytes()
    assert _run(scanned_copy).returncode == 0
    assert (out / "report.html").read_bytes() == html, "two renders differ"
    text = html.decode("utf-8")
    assert str(scanned_copy) not in text and str(scanned_copy.resolve()) not in text
    assert re.fullmatch(r"report\.html: .+report\.html \(\d+\.\d KB, 1 finding\(s\)\)\n",
                        first.stdout), first.stdout
    page = _embedded(text)
    report = json.loads((out / "report.json").read_text())
    root = report["repo"]["root"]
    assert root not in text, "the scanned checkout's absolute path is in the page"
    assert page["repo"]["name"] == Path(root).name and "root" not in page["repo"]
    assert [f["id"] for f in page["findings"]] == [f["id"] for f in report["findings"]]
    assert not list(out.glob("*.tmp")), "temp file left behind"


def test_missing_report_json_writes_nothing(scanned_copy):
    (scanned_copy / ".thunderstruck" / "report.json").unlink(missing_ok=True)
    proc = _run(scanned_copy)
    assert proc.returncode == 2
    assert "no report.json" in proc.stderr
    assert not (scanned_copy / ".thunderstruck" / "report.html").exists()


def test_wrong_schema_writes_nothing(scanned_copy, plugin_root):
    out = _scan(scanned_copy, plugin_root)
    payload = json.loads((out / "report.json").read_text())
    payload["schema"] = "thunderstruck.report/v0"
    (out / "report.json").write_text(json.dumps(payload))
    proc = _run(scanned_copy)
    assert proc.returncode == 2
    assert "thunderstruck.report/v0" in proc.stderr and "thunderstruck.report/v1" in proc.stderr
    assert not (out / "report.html").exists()


def test_missing_template_writes_nothing(scanned_copy, plugin_root, monkeypatch, tmp_path):
    out = _scan(scanned_copy, plugin_root)
    monkeypatch.setattr(report_html, "TEMPLATE", tmp_path / "nope.html")
    with pytest.raises(SystemExit) as exc:
        report_html.main(["--repo", str(scanned_copy)])
    assert exc.value.code == 2
    assert not (out / "report.html").exists()


# -------------------------------------------------------------- stdlib only --


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def _top_level_imports(path: Path) -> set[str]:
    """Module-level imports only: a deferred import inside a function is not
    loaded by importing the module."""
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_report_html_is_stdlib_only():
    local = {"_common", "context_extract"}
    assert _imports(SCRIPT) - set(sys.stdlib_module_names) <= {"_common"}
    for module in local:
        extra = _top_level_imports(ROOT / "scripts" / f"{module}.py")
        assert extra - set(sys.stdlib_module_names) <= local, (module, extra)
    header = SCRIPT.read_text(encoding="utf-8").split("# ///", 2)[1]
    assert "dependencies" not in header


# ------------------------------------------------------- template lint (T3) --


FORBIDDEN = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
             "new Function", "fetch(", "XMLHttpRequest", "<link", "@import", "url(",
             "src=", "http://", "https://")


def test_template_uses_no_markup_sinks_or_network():
    template = _template()
    for needle in FORBIDDEN:
        assert needle not in template, needle


def test_template_opens_links_safely_and_only_from_tool_urls():
    template = _template()
    assert 'rel: "noopener noreferrer"' in template
    assert 'rel: "noopener"' not in template
    # every href goes through safeUrl(), which admits http(s) only
    assert template.count("href:") == 1 and "href: u," in template
    assert r"/^https?:\/\//i.test(u)" in template


def test_template_reads_the_repo_name_not_its_path():
    template = _template()
    assert "repo.root" not in template and "repo.name" in template


# ------------------------------------------------------ inert, end to end --


HOSTILE_TEXT = ('</script><script id="pwn">window.pwned=1</script>'
                '<img src=x onerror="window.pwned=1"><a href="https://evil.example">x</a>')
MODEL_FIELDS = ("failure_mode", "trigger_condition", "amplifier", "sustaining_effect",
                "blast_radius", "how_to_verify", "confidence_rationale")


def _outside_data(html: str) -> str:
    return re.sub(r'<script type="application/json" id="thunderstruck-report">.*?</script>',
                  "", html, flags=re.S)


def test_hostile_model_text_stays_inside_the_data_block(scanned_copy, plugin_root):
    hid, doc = _valid_finding(scanned_copy, _hotspots(scanned_copy))
    for field in MODEL_FIELDS:
        doc["findings"][0][field] = f"{field}: {HOSTILE_TEXT}"
    _write_finding(scanned_copy, hid, doc)
    assert _validate(scanned_copy, plugin_root).returncode == 0
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(scanned_copy)], check=True, capture_output=True)
    assert _run(scanned_copy).returncode == 0
    html = (scanned_copy / ".thunderstruck" / "report.html").read_text(encoding="utf-8")
    outside = _outside_data(html)
    for marker in ("pwn", "pwned", "evil.example", "onerror"):
        assert marker not in outside, marker
    assert html.count("<script") == 2 and html.count("</script>") == 2
    page = _embedded(html)
    assert page["findings"][0]["failure_mode"] == f"failure_mode: {HOSTILE_TEXT}"


def test_page_holds_exactly_the_validated_findings(scanned_copy, plugin_root):
    """A hotspot whose findings failed validation never reaches the page (AC-3)."""
    out = _scan(scanned_copy, plugin_root)
    assert _run(scanned_copy).returncode == 0
    page = _embedded((out / "report.html").read_text(encoding="utf-8"))
    report = json.loads((out / "report.json").read_text())
    assert [f["id"] for f in page["findings"]] == [f["id"] for f in report["findings"]]
    assert page["incomplete"] == report["incomplete"]


# ------------------------------------------------------------ skills (T4) --


SKILLS = ROOT / "skills"
RUN = 'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/report_html.py"'


def test_report_skill_runs_the_renderer():
    text = (SKILLS / "thunderstruck-report" / "SKILL.md").read_text(encoding="utf-8")
    front = text.split("---", 2)[1]
    assert "name: thunderstruck-report" in front and "description:" in front
    assert RUN in text
    assert "report.json" in text and "/thunderstruck-scan" in text


def test_scan_step_5_renders_html_after_the_markdown_and_never_fails():
    text = (SKILLS / "thunderstruck-scan" / "SKILL.md").read_text(encoding="utf-8")
    step5 = text.split("## Step 5", 1)[1].split("## Step 6", 1)[0]
    assert step5.index("scripts/report.py") < step5.index(RUN)
    assert "never stops the scan" in step5
    step6 = text.split("## Step 6", 1)[1].split("\n## ", 1)[0]
    assert ".thunderstruck/report.html" in step6


def test_plugin_manifest_does_not_declare_skills():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert not {"skills", "hooks", "agents"} & set(manifest)
