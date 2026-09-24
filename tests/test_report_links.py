"""Report links end to end: the fixture is scanned, a hand-written finding is
validated, and report.py renders it. Every URL must come from links.py over a
resolved ref, and every failure must leave the report rendered and plain."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import links as links_mod
import mdtext
import report
from build_fixture import add_remote
from test_pipeline import _hotspots, _valid_finding, _validate, _write_finding

BASE = "https://github.com/acme/fixture"


def _render(repo: Path, plugin_root: Path, mutate=None, tamper=None) -> tuple[str, dict, dict]:
    """`mutate` edits the finding before validation. `tamper` edits the saved,
    already validated file, which is how input the validator would reject can
    still reach the report and prove its defence in depth."""
    data = _hotspots(repo)
    hid, doc = _valid_finding(repo, data)
    if mutate:
        mutate(doc["findings"][0])
    _write_finding(repo, hid, doc)
    proc = _validate(repo, plugin_root)
    assert proc.returncode == 0, proc.stdout
    if tamper:
        path = repo / ".thunderstruck" / "findings" / f"{hid}.json"
        saved = json.loads(path.read_text())
        tamper(saved["findings"][0])
        tamper(doc["findings"][0])
        path.write_text(json.dumps(saved))
    proc = subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                           "--repo", str(repo)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = repo / ".thunderstruck"
    return ((out / "report.md").read_text(), json.loads((out / "report.json").read_text()),
            doc["findings"][0])


def _head(repo: Path) -> str:
    return _hotspots(repo)["repo"]["head"]


def _evidence_lines(md: str, etype: str) -> list[str]:
    return [line for line in md.splitlines() if line.startswith(f"- _{etype}_ ")]


# ---------------------------------------------------------------- report.md --


def test_every_resolved_ref_is_linked(linked_copy, plugin_root):
    md, _, finding = _render(linked_copy, plugin_root)
    head = _head(linked_copy)
    blob = re.escape(f"{BASE}/blob/{head}/")
    file = re.escape(finding["location"]["file"])

    assert re.search(rf"\*\* · \[`{file}:1-2`\]\({blob}{file}#L1-L2\)", md), md
    code = _evidence_lines(md, "code")
    assert code and re.match(rf"- _code_ \[`{file}:1`\]\({blob}{file}#L1\) — ", code[0])
    detector = _evidence_lines(md, "detector")
    assert detector and re.match(rf"- _detector_ \[`S\d+@{file}:\d+`\]\({blob}{file}#L\d+\)",
                                 detector[0]), detector
    commit = _evidence_lines(md, "commit")
    assert commit and re.match(
        rf"- _commit_ \[`[0-9a-f]{{7}}`\]\({re.escape(BASE)}/commit/[0-9a-f]{{40}}\) — ",
        commit[0]), commit
    assert "references are not linked" not in md


def test_commit_ref_keeps_its_subject(linked_copy, plugin_root):
    def with_subject(f):
        ev = next(e for e in f["evidence"] if e["type"] == "commit")
        ev["ref"] = ev["ref"] + "\tfix: retry storm"
    md, _, _ = _render(linked_copy, plugin_root, with_subject)
    commit = _evidence_lines(md, "commit")[0]
    assert re.match(r"- _commit_ \[`[0-9a-f]{7}`\]\([^)]+/commit/[0-9a-f]{40}\) `fix: retry storm` — ",
                    commit), commit


def test_unreadable_location_lines_link_the_whole_file(linked_copy, plugin_root):
    def odd_lines(f):
        f["location"]["lines"] = "L16"
    md, payload, finding = _render(linked_copy, plugin_root, tamper=odd_lines)
    file = finding["location"]["file"]
    url = f"{BASE}/blob/{_head(linked_copy)}/{file}"
    assert f"[`{file}:L16`]({url})" in md
    assert payload["findings"][0]["location"]["url"] == url


def test_no_remote_renders_plain_refs_and_says_why(scanned_copy, plugin_root):
    md, payload, finding = _render(scanned_copy, plugin_root)
    assert "](http" not in md
    assert f"`{finding['location']['file']}:1-2`" in md
    assert "references are not linked: no git remote" in md
    assert payload["links"] is None
    assert any("no git remote" in w for w in payload["warnings"])


def test_disabled_links_are_silent(scanned_copy, plugin_root):
    (scanned_copy / ".thunderstruck.toml").write_text("[links]\nenabled = false\n")
    md, payload, _ = _render(scanned_copy, plugin_root)
    assert "](http" not in md and "not linked" not in md
    assert payload["links"] is None


def test_invalid_profile_does_not_fail_the_report(linked_copy, plugin_root):
    (linked_copy / ".thunderstruck.toml").write_text("[links]\nprovider = 'gitea'\n")
    md, _, _ = _render(linked_copy, plugin_root)
    assert "](http" not in md
    assert mdtext.text("references are not linked: [links] provider") in md


def test_token_in_remote_never_reaches_output(scanned_copy, plugin_root):
    add_remote(scanned_copy, "https://bob:ghs_SECRET@github.com/acme/fixture.git")
    md, payload, _ = _render(scanned_copy, plugin_root)
    assert f"]({BASE}/" in md
    blob = md + json.dumps(payload)
    assert "ghs_SECRET" not in blob and "bob" not in blob


def test_file_edited_after_the_scan_is_not_linked(linked_copy, plugin_root):
    data = _hotspots(linked_copy)
    hid, doc = _valid_finding(linked_copy, data)
    _write_finding(linked_copy, hid, doc)
    assert _validate(linked_copy, plugin_root).returncode == 0
    file = doc["findings"][0]["location"]["file"]
    with (linked_copy / file).open("a") as fh:
        fh.write("\n// edited after the scan\n")
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(linked_copy)], check=True, capture_output=True)
    md = (linked_copy / ".thunderstruck" / "report.md").read_text()
    assert f"`{file}:1-2`" in md and f"[`{file}:1-2`]" not in md
    assert re.search(rf"differ from the scanned commit [0-9a-f]{{7}} or are not in it, "
                     rf"and are not linked: {re.escape(mdtext.text(file))}", md)
    # commits are not files: they stay linked
    assert "/commit/" in md


def test_unpushed_scan_is_linked_with_a_warning(scanned_copy, plugin_root):
    add_remote(scanned_copy, "https://github.com/acme/fixture.git", tracking=False)
    md, _, _ = _render(scanned_copy, plugin_root)
    assert f"]({BASE}/blob/" in md
    assert "their links resolve once pushed" in md


def test_finding_supplied_urls_are_overwritten(linked_copy, plugin_root):
    def planted(f):
        f["location"]["url"] = "https://evil.example/loc"
        for ev in f["evidence"]:
            ev["url"] = "https://evil.example/ev"
    md, payload, _ = _render(linked_copy, plugin_root, planted)
    assert "evil.example" not in md and "evil.example" not in json.dumps(payload)


def test_catalog_refs_are_never_linked(tmp_path):
    finding = {"location": {"file": "x.ts", "lines": "1"},
               "evidence": [{"type": "catalog", "ref": "dependsOn component:default/x"}]}
    report._set_urls([finding], None, tmp_path)
    assert finding["evidence"][0]["url"] is None
    assert report._evidence_ref(finding["evidence"][0]) == "`dependsOn component:default/x`"


# -------------------------------------------------------------- report.json --


def test_report_json_carries_the_same_links(linked_copy, plugin_root):
    md, payload, _ = _render(linked_copy, plugin_root)
    head = _head(linked_copy)
    assert payload["links"] == {"provider": "github", "base_url": BASE, "sha": head,
                                "remote": "origin"}
    f = payload["findings"][0]
    assert f["location"]["url"].startswith(f"{BASE}/blob/{head}/")
    for ev in f["evidence"]:
        assert "url" in ev
        assert ev["url"] and f"]({ev['url']})" in md


def test_link_warnings_are_in_report_json(scanned_copy, plugin_root):
    add_remote(scanned_copy, "https://github.com/acme/fixture.git", tracking=False)
    _, payload, _ = _render(scanned_copy, plugin_root)
    assert payload["warnings"][-1].endswith("their links resolve once pushed")


def test_index_and_finding_files_are_untouched(linked_copy, plugin_root):
    data = _hotspots(linked_copy)
    hid, doc = _valid_finding(linked_copy, data)
    _write_finding(linked_copy, hid, doc)
    assert _validate(linked_copy, plugin_root).returncode == 0
    finding_file = linked_copy / ".thunderstruck" / "findings" / f"{hid}.json"
    before = finding_file.read_bytes()
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(linked_copy)], check=True, capture_output=True)
    assert finding_file.read_bytes() == before
    index = (linked_copy / ".thunderstruck" / "index.json").read_text()
    assert '"url"' not in index


def test_a_report_listing_nothing_says_nothing_about_links(tmp_path):
    assert report.link_refs(tmp_path, "a" * 40, [], [], []) == (None, [], {})


# -------------------------------------------------------------- hardening --


def test_model_text_cannot_hijack_a_link(linked_copy, plugin_root):
    def inject(f):
        f["location"]["lines"] = "16`](https://evil.example/x) `"
        ev = next(e for e in f["evidence"] if e["type"] == "commit")
        ev["ref"] += " x`](https://evil.example/y) `"
    md, _, _ = _render(linked_copy, plugin_root, tamper=inject)
    for line in md.splitlines():
        # the attacker's target may appear inside a code span, never as a link target
        assert "](https://evil.example" not in re.sub(r"(`+).*?\1", "", line), line


def test_reversed_code_range_gets_an_ordered_anchor(linked_copy, plugin_root):
    def reverse(f):
        code = next(e for e in f["evidence"] if e["type"] == "code")
        code["ref"] = code["ref"].rsplit(":", 1)[0] + ":2-1"
    md, _, _ = _render(linked_copy, plugin_root, tamper=reverse)
    assert "#L1-L2)" in _evidence_lines(md, "code")[0]


def test_non_utf8_profile_is_reported_as_unreadable(linked_copy, plugin_root):
    (linked_copy / ".thunderstruck.toml").write_bytes(b"[links]\nprovider = '\xff'\n")
    data = _hotspots(linked_copy)
    hid, doc = _valid_finding(linked_copy, data)
    # the profile can't be read, so validate.py can't run; stand in for it
    doc["validated_with"] = report.c.VALIDATION_RULES
    _write_finding(linked_copy, hid, doc)
    (linked_copy / ".thunderstruck" / "validation.json").write_text(json.dumps(
        {"results": [{"hotspot_id": hid, "valid": True}]}))
    md = report.render_markdown(report.collect(linked_copy), linked_copy)
    assert mdtext.text("references are not linked: .thunderstruck.toml could not be read") in md


def test_code_spans_survive_backticks():
    assert report._code("a`b") == "``a`b``"
    assert report._code("`a") == "`` `a ``"
    assert report._code("x\ny") == "`x y`"


# ------------------------------------------- hotspot, clean, incomplete (#24) --


def _report(repo: Path, plugin_root: Path) -> tuple[str, dict]:
    subprocess.run([sys.executable, str(plugin_root / "scripts" / "report.py"),
                    "--repo", str(repo)], check=True, capture_output=True)
    out = repo / ".thunderstruck"
    return (out / "report.md").read_text(), json.loads((out / "report.json").read_text())


def _no_findings(repo: Path) -> None:
    """The session fixture may carry other tests' findings; start from none."""
    import shutil
    out = repo / ".thunderstruck"
    shutil.rmtree(out / "findings", ignore_errors=True)
    (out / "validation.json").unlink(missing_ok=True)


def _all_clean(repo: Path) -> dict:
    _no_findings(repo)
    data = _hotspots(repo)
    for h in data["hotspots"]:
        _write_finding(repo, h["id"], {"hotspot_id": h["id"], "file": h["file"],
                                       "findings": [], "notes": "nothing found"})
    return data


def _row(md: str, hid: str) -> str:
    return next(line for line in md.splitlines() if line.startswith(f"| {hid} | "))


def _item(md: str, hid: str) -> str:
    return next(line for line in md.splitlines() if line.startswith(f"- **{hid}** "))


def _linked_row(head: str, file: str) -> str:
    return (f"[`{file}`]({BASE}/blob/{head}/{file}) · "
            f"[history]({BASE}/commits/{head}/{file})")


def test_ranked_hotspots_link_code_and_history(linked_copy, plugin_root):
    md, payload, _ = _render(linked_copy, plugin_root)
    head = _head(linked_copy)
    for h in _hotspots(linked_copy)["hotspots"]:
        assert f"| {h['id']} | {_linked_row(head, h['file'])} | " in _row(md, h["id"])
    for h in payload["hotspots"]:
        assert h["url"] == f"{BASE}/blob/{head}/{h['file']}"
        assert h["history_url"] == f"{BASE}/commits/{head}/{h['file']}"


def test_report_without_findings_links_every_listed_file(linked_copy, plugin_root):
    data = _all_clean(linked_copy)
    md, payload = _report(linked_copy, plugin_root)
    head = _head(linked_copy)
    assert payload["counts"]["findings"] == 0 and payload["links"]["sha"] == head
    for h in data["hotspots"]:
        assert _item(md, h["id"]) == (f"- **{h['id']}** [`{h['file']}`]"
                                      f"({BASE}/blob/{head}/{h['file']}) — nothing found")
        assert _linked_row(head, h["file"]) in _row(md, h["id"])
    assert all(e["url"] == f"{BASE}/blob/{head}/{e['file']}" for e in payload["clean"])
    assert "not linked" not in md


def test_incomplete_hotspots_are_linked(linked_copy, plugin_root):
    _no_findings(linked_copy)
    md, payload = _report(linked_copy, plugin_root)  # no investigator output at all
    head = _head(linked_copy)
    for h in _hotspots(linked_copy)["hotspots"]:
        assert _item(md, h["id"]).startswith(
            f"- **{h['id']}** [`{h['file']}`]({BASE}/blob/{head}/{h['file']}) — no investigator")
    assert payload["incomplete"] and all(
        e["url"] == f"{BASE}/blob/{head}/{e['file']}" for e in payload["incomplete"])


def _git(repo: Path, *args: str) -> str:
    from build_fixture import isolated_git_env
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=isolated_git_env()).stdout.strip()


@pytest.mark.parametrize("change", ["edited", "staged", "committed_after_scan", "untracked",
                                    "assume_unchanged", "symlink"])
def test_hotspot_that_differs_from_the_scanned_commit_is_plain(linked_copy, plugin_root,
                                                                 change):
    _no_findings(linked_copy)
    data = _hotspots(linked_copy)
    h = data["hotspots"][0]
    file = h["file"]
    path = linked_copy / file
    if change == "edited":
        path.write_text(path.read_text() + "\n// edited\n")
    elif change == "staged":
        path.write_text(path.read_text() + "\n// staged\n")
        _git(linked_copy, "add", file)
    elif change == "committed_after_scan":
        path.write_text(path.read_text() + "\n// later\n")
        _git(linked_copy, "commit", "-qam", "later")
    elif change == "untracked":
        _git(linked_copy, "rm", "-q", "--cached", file)
    elif change == "assume_unchanged":
        _git(linked_copy, "update-index", "--assume-unchanged", file)
        path.write_text(path.read_text() + "\n// hidden\n")
    elif change == "symlink":
        file = "src/link.ts"
        (linked_copy / file).symlink_to(Path(h["file"]).name)
        _git(linked_copy, "add", file)
        _git(linked_copy, "commit", "-qm", "link")
        _git(linked_copy, "update-ref", "refs/remotes/origin/main", "HEAD")
        data["repo"]["head"] = _git(linked_copy, "rev-parse", "HEAD")
        h["file"] = file
        (linked_copy / ".thunderstruck" / "hotspots.json").write_text(json.dumps(data))
    md, payload = _report(linked_copy, plugin_root)
    assert _row(md, h["id"]).startswith(f"| {h['id']} | `{file}` | ")
    assert _item(md, h["id"]).startswith(f"- **{h['id']}** `{file}` — ")
    other = data["hotspots"][1]
    assert f"[`{other['file']}`](" in _row(md, other["id"]), "unchanged files stay linked"
    stale = [w for w in payload["warnings"] if "differ from the scanned commit" in w]
    assert len(stale) == 1 and file in stale[0]
    entry = next(e for e in payload["hotspots"] if e["id"] == h["id"])
    assert entry["url"] is None and entry["history_url"] is None


def test_many_stale_hotspots_are_summarised(linked_copy, plugin_root):
    hotspots = _hotspots(linked_copy)["hotspots"]
    assert len(hotspots) >= 7
    for h in hotspots:
        with (linked_copy / h["file"]).open("a") as fh:
            fh.write("\n// edited\n")
    md, _ = _report(linked_copy, plugin_root)
    names = sorted(h["file"] for h in hotspots)
    expected = (f"{len(names)} file(s) differ from the scanned commit "
                f"{_head(linked_copy)[:7]} or are not in it, and are not linked: "
                + ", ".join(names[:5]) + f" … and {len(names) - 5} more")
    assert f"- {mdtext.text(expected)}" in md.splitlines()


def _section(md: str, title: str) -> str:
    return md.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


def test_unlinkable_report_without_findings_warns_once_and_renders_as_before(
        scanned_copy, plugin_root):
    _all_clean(scanned_copy)
    md, payload = _report(scanned_copy, plugin_root)
    assert [w for w in payload["warnings"] if "not linked" in w] == [
        f"{links_mod.NOT_LINKED}no git remote to link to; set remote or base_url in [links] "
        "in .thunderstruck.toml"]
    assert "](http" not in md and md.count("references are not linked") == 1
    assert all(e["url"] is None for e in payload["clean"])
    assert all(h["url"] is None and h["history_url"] is None for h in payload["hotspots"])

    (scanned_copy / ".thunderstruck.toml").write_text("[links]\nenabled = false\n")
    plain, plain_payload = _report(scanned_copy, plugin_root)
    assert "not linked" not in plain and plain_payload["links"] is None
    for title in ("Ranked hotspots", "Hotspots investigated with no finding"):
        assert _section(md, title) == _section(plain, title)

    _no_findings(scanned_copy)
    (scanned_copy / ".thunderstruck.toml").unlink()
    _, incomplete = _report(scanned_copy, plugin_root)
    assert incomplete["incomplete"] and all(e["url"] is None for e in incomplete["incomplete"])


def test_custom_templates_link_code_without_history(linked_copy, plugin_root):
    (linked_copy / ".thunderstruck.toml").write_text(
        "[links]\nbase_url = 'https://git.example.com/acme/fixture'\n"
        "code_template = '{base}/browse/{path}?at={sha}#{start}-{end}'\n"
        "commit_template = '{base}/commits/{sha}'\n")
    md, payload = _report(linked_copy, plugin_root)
    head = _head(linked_copy)
    h = payload["hotspots"][0]
    assert h["url"] == f"https://git.example.com/acme/fixture/browse/{h['file']}?at={head}"
    assert h["history_url"] is None
    assert "[history]" not in md and f"[`{h['file']}`](https://git.example.com/" in _row(md, h["id"])


def test_templates_without_a_whole_file_form_say_so(linked_copy, plugin_root):
    (linked_copy / ".thunderstruck.toml").write_text(
        "[links]\nbase_url = 'https://git.example.com/acme/fixture'\n"
        "code_template = '{base}/file?name={path}&ci={sha}&ln={start}-{end}'\n"
        "commit_template = '{base}/commits/{sha}'\n")
    _no_findings(linked_copy)
    md, payload = _report(linked_copy, plugin_root)
    assert all(e["url"] is None for e in payload["incomplete"])
    assert [w for w in payload["warnings"] if "no whole-file form" in w] == [
        "listed files are not linked: code_template puts {start} or {end} before '#', "
        "so it has no whole-file form"]
    assert "](http" not in _section(md, "Ranked hotspots")


def test_listed_paths_that_could_leave_the_repo_are_never_linked():
    ctx = links_mod.LinkContext.for_provider("github", base=BASE, sha="a" * 40)
    listed = [{"file": "..\\secret.ts"}, {"file": "/etc/passwd"}, {"file": "src/ok.ts"}]
    out = report._set_file_urls([{"id": "H01", "file": "a\\b.ts"}], listed, ctx)
    assert out == {"H01": {"url": None, "history_url": None}}
    assert [e["url"] for e in listed] == [None, None, f"{BASE}/blob/{'a' * 40}/src/ok.ts"]
