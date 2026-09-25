#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Render validated findings into the three outputs.

  report.md    the human artefact — run header, pattern coverage, ranked findings
  report.json  stable versioned schema, so a later run can compare against it
  index.json   file -> findings, the lookup the PreToolUse guardrail does

Display IDs (FR-001...) renumber as ranking changes. Each finding also carries
a `key` derived from its file and failure mode, which does not — that is what
prediction tracking will match on later.

    uv run scripts/report.py
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
import links  # noqa: E402
import mdtext as md  # noqa: E402
from validate import CODE_REF, DETECTOR_REF, _count_lines  # noqa: E402

CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}
MAX_CONTEXT_WARNINGS = 20
BADGE = {"high": "high", "medium": "medium", "low": "low"}


def collect(repo: Path) -> dict[str, Any]:
    out = c.out_dir(repo)
    hotspots = c.load_json(out / "hotspots.json")
    if not hotspots:
        raise c.ThunderstruckError("no hotspots.json — run signals.py first.")
    validation = c.load_json(out / "validation.json", {}) or {}
    by_hotspot = {r["hotspot_id"]: r for r in validation.get("results", [])}

    scores = {h["id"]: h["scores"]["score"] for h in hotspots["hotspots"]}
    findings: list[dict] = []
    failed: list[dict] = []
    clean: list[dict] = []

    for hs in hotspots["hotspots"]:
        hid = hs["id"]
        result = by_hotspot.get(hid)
        path = out / "findings" / f"{hid}.json"
        if result is None and not path.is_file():
            failed.append({"hotspot_id": hid, "file": hs["file"],
                           "reason": "no investigator output (analysis_failed)"})
            continue
        if result is not None and not result.get("valid"):
            failed.append({"hotspot_id": hid, "file": hs["file"],
                           "reason": "findings did not validate after one repair round",
                           "errors": result.get("errors", [])[:5]})
            continue
        doc = c.load_json(path, {}) or {}
        items = doc.get("findings") or []
        if items and doc.get("validated_with") != c.VALIDATION_RULES:
            # saved after the last validation, or validated under older rules:
            # nothing reaches the report that today's validator hasn't passed
            failed.append({"hotspot_id": hid, "file": hs["file"],
                           "reason": "findings not validated by this version's rules "
                                     "— re-run the scan"})
            continue
        if not items:
            clean.append({"hotspot_id": hid, "file": hs["file"],
                          "notes": doc.get("notes", "")})
            continue
        for f in items:
            f = copy.deepcopy(f)  # urls are added below; the finding files stay untouched
            f["hotspot_id"] = hid
            f["hotspot_score"] = scores.get(hid)
            findings.append(f)

    findings.sort(key=lambda f: (
        CONFIDENCE_RANK.get(f.get("confidence"), 9),
        -(f.get("hotspot_score") or 0.0),
        str(f.get("location", {}).get("file", "")),
    ))
    for n, f in enumerate(findings, 1):
        f["id"] = f"FR-{n:03d}"
    _attach_commit_subjects(repo, findings)
    context_doc = c.load_json(out / c.CONTEXT_FILENAME, {}) or {}
    if not isinstance(context_doc, dict):
        context_doc = {}
    raw_warnings = context_doc.get("warnings")
    link_meta, link_warnings, hotspot_links = link_refs(
        repo, hotspots["repo"]["head"], findings, hotspots["hotspots"], clean + failed)
    return {"hotspots": hotspots, "findings": findings,
            "failed": failed, "clean": clean, "validation": validation,
            "context": c.load_service_context(repo),
            "context_warnings": _context_warnings(raw_warnings),
            "links": link_meta, "link_warnings": link_warnings,
            "hotspot_links": hotspot_links}


def _attach_commit_subjects(repo: Path, findings: list[dict]) -> None:
    """Give every commit evidence item its subject and class, so a reader sees
    the history itself rather than only the investigator's note on it. The
    refs were already resolved by validate.py; a failure here renders as
    unavailable and never fails the report."""
    try:
        extra_fix = c.profile_fix_keywords(c.load_profile(repo))
    except c.ThunderstruckError:
        extra_fix = ()
    cache: dict[str, str | None] = {}
    for f in findings:
        for ev in _evidence(f):
            if ev.get("type") != "commit" or not str(ev.get("ref") or "").strip():
                continue
            sha = str(ev["ref"]).split()[0]
            if sha not in cache:
                try:
                    cache[sha] = c.git_paths(repo, "log", "-1", "--format=%s", sha,
                                             "--").strip("\n")
                except (c.ThunderstruckError, OSError, subprocess.SubprocessError):
                    cache[sha] = None
            subject = cache[sha]
            ev["subject"] = subject
            ev["kind"] = c.classify_commit(subject, extra_fix) if subject is not None else None


def _context_warnings(raw: Any) -> list[str]:
    """context.json is a file on disk, not trusted structure: strings only,
    capped, and the cap says what it left out."""
    kept = [w for w in raw if isinstance(w, str)] if isinstance(raw, list) else []
    if len(kept) > MAX_CONTEXT_WARNINGS:
        hidden = len(kept) - MAX_CONTEXT_WARNINGS
        kept = kept[:MAX_CONTEXT_WARNINGS] + [f"{hidden} more context warning(s) not shown; "
                                              f"see {c.CONTEXT_FILENAME}"]
    return kept


# --------------------------------------------------------------------------
# source links
# --------------------------------------------------------------------------


def link_refs(repo: Path, head: str, findings: list[dict], hotspots: list[dict] | None = None,
              listed: list[dict] | None = None) -> tuple[dict | None, list[str], dict]:
    """Set a `url` on every finding location and evidence item, and on every
    listed (clean or incomplete) entry, in place; return the hotspot links.

    URLs come only from links.py, over refs validate.py resolved or files
    signals.py ranked; a `url` the investigator wrote is overwritten. Linking
    never fails the report.
    """
    hotspots, listed = hotspots or [], listed or []
    if not (findings or hotspots or listed):
        return None, [], {}

    def unlinked(warnings: list[str]) -> tuple[None, list[str], dict]:
        _set_urls(findings, None, repo)
        return None, warnings, _set_file_urls(hotspots, listed, None)

    try:
        try:
            profile = c.load_profile(repo)
        except (c.ThunderstruckError, ValueError):  # ValueError covers non-UTF-8 bytes
            return unlinked([f"{links.NOT_LINKED}.thunderstruck.toml could not be read"])
        paths: set[str] = {str(e["file"]) for e in [*hotspots, *listed] if e.get("file")}
        commits: set[str] = set()
        for f in findings:
            loc = f.get("location")
            if isinstance(loc, dict) and loc.get("file"):
                paths.add(str(loc["file"]))
            for ev in _evidence(f):
                ref, etype = str(ev.get("ref") or "").strip(), ev.get("type")
                if etype == "code" and (m := CODE_REF.match(ref)):
                    paths.add(m["path"])
                elif etype == "detector" and (m := DETECTOR_REF.match(ref)):
                    paths.add(m["path"])
                elif etype == "commit" and ref:
                    commits.add(ref.split()[0])
        result = links.link_context(repo, profile, head, paths, commits)
        _set_urls(findings, result, repo)
        hotspot_links = _set_file_urls(hotspots, listed, result.ctx)
        ctx = result.ctx
        warnings = list(result.warnings)
        if ctx and ctx.code_file is None and (hotspots or listed):
            warnings.append("listed files are not linked: code_template puts {start} or {end} "
                            "before '#', so it has no whole-file form")
        meta = ({"provider": ctx.provider, "base_url": ctx.base, "sha": ctx.sha,
                 "remote": ctx.remote} if ctx else None)
        return meta, warnings, hotspot_links
    except Exception as exc:  # noqa: BLE001 — a presentation feature must not sink the report
        return unlinked([f"{links.NOT_LINKED}internal error ({type(exc).__name__})"])


def _file_url(ctx: "links.LinkContext | None", file) -> str | None:
    if not ctx or not file or c.path_problem(c.ref_path(str(file))):
        return None
    return ctx.code(str(file))


def _set_file_urls(hotspots: list[dict], listed: list[dict],
                   ctx: "links.LinkContext | None") -> dict[str, dict]:
    """A whole-file `url` on each listed entry; {hotspot id: url, history_url}."""
    for entry in listed:
        entry["url"] = _file_url(ctx, entry.get("file"))
    out: dict[str, dict] = {}
    for h in hotspots:
        url = _file_url(ctx, h.get("file"))
        out[h["id"]] = {"url": url, "history_url": ctx.history(str(h["file"])) if url else None}
    return out


def _evidence(f: dict) -> list[dict]:
    return [ev for ev in (f.get("evidence") or []) if isinstance(ev, dict)]


def _set_urls(findings: list[dict], result: "links.LinkResult | None", repo: Path) -> None:
    ctx = result.ctx if result else None
    for f in findings:
        loc = f.get("location")
        if isinstance(loc, dict):
            loc["url"] = _location_url(ctx, loc, repo) if ctx else None
        for ev in _evidence(f):
            ev["url"] = _evidence_url(ctx, result, ev) if ctx else None


def _location_url(ctx: "links.LinkContext", loc: dict, repo: Path) -> str | None:
    if not loc.get("file"):
        return None
    rel = c.ref_path(loc["file"])
    if c.path_problem(rel):
        return None  # never count lines of a path that could leave the repository
    span = links.parse_lines(loc.get("lines"), _count_lines(repo / rel))
    return ctx.code(rel, *span) if span else ctx.code(rel)


def _evidence_url(ctx: "links.LinkContext", result: "links.LinkResult", ev: dict) -> str | None:
    ref, etype = str(ev.get("ref") or "").strip(), ev.get("type")
    if etype == "code" and (m := CODE_REF.match(ref)):
        start, end = int(m["start"]), int(m["end"] or m["start"])
        # validate.py rejects a reversed range; this guards a tampered file
        return ctx.code(m["path"], min(start, end), max(start, end))
    if etype == "detector" and (m := DETECTOR_REF.match(ref)):
        return ctx.code(m["path"], int(m["line"]))
    if etype == "commit" and ref:
        full = result.commits.get(ref.split()[0])
        return ctx.commit(full) if full else None
    return None


# Every value the report did not write itself goes through mdtext (#28).
_code = md.code
_linked = md.linked


def _evidence_ref(ev: dict) -> str:
    ref = str(ev.get("ref") or "").strip()
    url = ev.get("url")
    if ev.get("type") == "commit" and ref:
        sha, *rest = ref.split(None, 1)
        out = (_linked(sha[:7], url) + (f" {_code(rest[0])}" if rest else "")
               if url else _linked(ref, None))
        if "subject" in ev:
            subject = ev.get("subject")
            # the subject is repository text: inert, like every other value (#28)
            out += (f" — “{md.text(subject)}” ({md.text(ev.get('kind') or '?')})"
                    if isinstance(subject, str) else " — (subject unavailable)")
        return out
    return _linked(str(ev.get("ref")), url)


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------


def _edge_attrs(edge: dict, cell: bool = True) -> str:
    attrs = edge.get("attributes") or {}
    return "; ".join(f"{md.text(k, cell)}: {md.text(v, cell)}" for k, v in sorted(attrs.items()))


def _deps(deps: list[dict]) -> str:
    return ", ".join(
        f"{md.code(d['neighbour'], cell=True)} ({md.text(d['direction'], cell=True)}"
        + (f"; {_edge_attrs(d)}" if d.get("attributes") else "") + ")"
        for d in deps)


def _age_days(iso: str, now: datetime) -> int | None:
    try:
        return max(0, (now - datetime.fromisoformat(iso)).days)
    except (TypeError, ValueError):
        return None


def render_service_context(ctx: dict | None, now: datetime) -> list[str]:
    if not ctx:
        return []
    fetched = str(ctx.get("fetched_at") or "")
    age = _age_days(fetched, now)
    L = ["## Service context", "",
         f"{md.code(ctx['entity_ref'])} · {len(ctx['edges'])} edge(s), 1 hop · fetched "
         f"{md.text(fetched[:10])}" + (f" ({age} days ago)" if age is not None else "")
         + f" · context {md.code(str(ctx.get('context_hash'))[:19])}", "",
         "Component-level context from the service catalog: it describes the whole "
         "component, not a file.", "",
         "| Edge | Direction | Attributes |", "|---|---|---|"]
    for edge in ctx["edges"]:
        L.append(f"| {md.code(edge['ref'], cell=True)} | {md.text(edge['direction'], cell=True)} "
                 f"| {_edge_attrs(edge) or '—'} |")
    hidden = [f"{n} {md.text(d)}" for d, n in sorted((ctx.get("truncated") or {}).items()) if n]
    if hidden:
        L += ["", f"_… and {', '.join(hidden)} not listed "
                  f"(cap {c.MAX_NEIGHBOURS_PER_DIRECTION} per direction)._"]
    L.append("")
    return L


def render_markdown(data: dict, repo: Path, now: datetime | None = None) -> str:
    hs, findings = data["hotspots"], data["findings"]
    repo_name = Path(hs["repo"]["root"]).name
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.get("confidence", "?")] = counts.get(f.get("confidence", "?"), 0) + 1
    breakdown = ", ".join(f"{n} {md.text(k)}" for k, n in
                          sorted(counts.items(), key=lambda kv: CONFIDENCE_RANK.get(kv[0], 9)))
    files_affected = len({f["location"]["file"] for f in findings if f.get("location")})

    L: list[str] = [
        f"# thunderstruck — {md.text(repo_name, heading=True)}",
        "",
        f"**{md.text(repo_name)}** · {md.code(hs['repo']['branch'])} @ {md.code(hs['repo']['head'][:7])}  ",
        f"Scanned {hs['generated_at'][:10]} · window {md.code(hs['window']['since'])} "
        f"(since {md.text(hs['window']['since_date'])}, {hs['window']['commits']} commits) · "
        f"{hs['counts']['files_considered']} files considered · "
        f"{hs['counts']['hotspots']} hotspots investigated  ",
        f"**{len(findings)} finding(s)** across {files_affected} file(s)"
        + (f" — {breakdown}" if breakdown else ""),
        "",
        "> Findings are **falsifiable hypotheses**, not verified defects. Every "
        "claim cites evidence that resolved to a real file:line, commit, "
        "detector hit or catalog edge, and every finding names one concrete way to prove it "
        "wrong. Check the `Verify` line before you act on one.",
        "",
    ]

    warnings = (list(hs.get("warnings") or []) + list(data.get("context_warnings") or [])
                + list(data.get("link_warnings") or []))
    suppressed = hs.get("suppressed") or []
    if warnings or suppressed:
        L += ["## Run warnings", ""]
        L += [f"- {md.text(w)}" for w in warnings]
        if suppressed:
            L.append(f"- **Suppressed leads** — {len(suppressed)} rule(s) in "
                     f"{md.code(c.PROFILE_FILENAME)} silence detector hits before ranking:")
            L += [f"  - {md.code(r['detector'])} on {md.code(r['path'])}: "
                  f"{r['hits']} hit(s) — {md.text(r['reason'])}" for r in suppressed]
        L.append("")
    L += render_service_context(data.get("context"), now or datetime.now(timezone.utc))

    # ---- coverage table
    lead_files = {pid: cov["files"] for pid, cov in hs["pattern_coverage"].items()}
    per_pattern: dict[str, int] = {}
    for f in findings:
        for pid in f.get("missing_patterns") or []:
            per_pattern[pid] = per_pattern.get(pid, 0) + 1
    L += ["## Pattern coverage", "",
          "Leads are detector hits — mechanical, noisy, and never a finding on "
          "their own. Findings are what survived an investigator reading the code.",
          "",
          "| ID | Pattern | Tier | Files with a lead | Findings |",
          "|---|---|---|---|---|"]
    for pid, cov in sorted(hs["pattern_coverage"].items()):
        if not cov.get("scanned"):
            continue
        L.append(f"| {md.code(pid, cell=True)} | {md.text(cov['name'], cell=True)} | {md.text(cov['tier'], cell=True)} | "
                 f"{lead_files.get(pid, 0)} | {per_pattern.get(pid, 0)} |")
    other = per_pattern.get("OTHER", 0)
    if other:
        L.append(f"| `OTHER` | Not in the catalog | — | — | {other} |")
    L.append("")

    # ---- findings
    if findings:
        L += ["## Findings", ""]
        for f in findings:
            loc = f.get("location") or {}
            symbol = f" · {md.code(loc['symbol'])}" if loc.get("symbol") else ""
            lines = f":{loc['lines']}" if loc.get("lines") else ""
            where = _linked(f"{loc.get('file', '?')}{lines}", loc.get("url"))
            rows = ["| | |", "|---|---|",
                    f"| Trigger | {md.text(f.get('trigger_condition', '—'), cell=True)} |",
                    f"| Amplifier | {md.text(f.get('amplifier', '—'), cell=True)} |",
                    f"| Sustaining effect | "
                    f"{md.text(f['sustaining_effect'], cell=True) if f.get('sustaining_effect') else '_none — this one stops when the trigger stops_'} |",
                    f"| Blast radius | {md.text(f.get('blast_radius', '—'), cell=True)} |"]
            if f.get("catalog_evidence"):
                rows.append(f"| Dependents / dependencies | {_deps(f['catalog_evidence'])} |")
            rows.append(f"| Missing patterns | {', '.join(md.code(p, cell=True) for p in f.get('missing_patterns') or []) or '—'} |")
            L += [f"### {f['id']} · {md.text(f.get('failure_mode', '(no failure mode)'), heading=True)}",
                  "",
                  f"**{BADGE.get(f.get('confidence'), '?')} confidence** · "
                  f"{where}{symbol} · "
                  f"hotspot {f['hotspot_id']} (score {f.get('hotspot_score')})",
                  "",
                  *rows,
                  "",
                  "**Evidence**", ""]
            for ev in f.get("evidence") or []:
                note = f" — {md.text(ev['note'])}" if ev.get("note") else ""
                L.append(f"- _{md.text(ev.get('type'))}_ {_evidence_ref(ev)}{note}")
            L += ["",
                  f"**Verify** — {md.text(f.get('how_to_verify', '—'))}  ",
                  f"**Why this confidence** — {md.text(f.get('confidence_rationale', '—'))}  "]
            if f.get("prediction"):
                L.append(f"**Prediction** — {md.text(f['prediction'])}  ")
            L += ["", f"<sub>stable key {md.code(f.get('key', '—'))}</sub>", "", "---", ""]
    else:
        L += ["## Findings", "",
              "None. Every investigated hotspot came back clean — see below for "
              "what each one checked.", ""]

    if data["clean"]:
        L += ["## Hotspots investigated with no finding", ""]
        for entry in data["clean"]:
            note = f" — {md.text(entry['notes'])}" if entry.get("notes") else ""
            L.append(f"- **{entry['hotspot_id']}** {_linked(entry['file'], entry.get('url'))}{note}")
        L.append("")

    if data["failed"]:
        L += ["## Incomplete", "",
              "These hotspots were ranked but produced no usable analysis. The "
              "report is partial.", ""]
        for entry in data["failed"]:
            L.append(f"- **{entry['hotspot_id']}** {_linked(entry['file'], entry.get('url'))} "
                     f"— {md.text(entry['reason'])}")
            for err in entry.get("errors", [])[:3]:
                L.append(f"  - {md.text(err)}")
        L.append("")

    L += ["## Ranked hotspots", "",
          "| # | File | Score | Commits | Fixes | Max CCN | Leads |",
          "|---|---|---|---|---|---|---|"]
    for h in hs["hotspots"]:
        cx = h.get("complexity") or {}
        pats = ", ".join(md.text(p, cell=True) for p in h["stability"]["patterns"]) or "—"
        file_cell = _linked(h["file"], _hotspot_link(data, h["id"], "url"), cell=True)
        if (history := _hotspot_link(data, h["id"], "history_url")):
            file_cell += f" · [history]({history})"
        L.append(f"| {h['id']} | {file_cell} | {h['scores']['score']} | "
                 f"{h['churn']['commits']} | {h['churn']['fix_commits']} | "
                 f"{cx.get('ccn_max', '—')} | {pats} |")
    L += ["",
          f"<sub>thunderstruck · catalog `{hs.get('schema')}` · "
          f"report `{c.REPORT_SCHEMA_VERSION}`</sub>", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------
# json outputs
# --------------------------------------------------------------------------


def _hotspot_link(data: dict, hid: str, key: str) -> str | None:
    return ((data.get("hotspot_links") or {}).get(hid) or {}).get(key)


def render_json(data: dict) -> dict:
    hs = data["hotspots"]
    return {
        "schema": c.REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": hs["repo"],
        "window": hs["window"],
        "catalog_schema": hs.get("schema"),
        "counts": {
            "hotspots": hs["counts"]["hotspots"],
            "files_considered": hs["counts"]["files_considered"],
            "findings": len(data["findings"]),
            "clean_hotspots": len(data["clean"]),
            "failed_hotspots": len(data["failed"]),
        },
        "warnings": list(hs.get("warnings") or []) + list(data.get("link_warnings") or []),
        "links": data.get("links"),
        "degraded": hs.get("degraded", {}),
        "service_context": ({k: data["context"].get(k) for k in
                             ("status", "entity_ref", "context_hash", "fetched_at",
                              "edges", "truncated")}
                            if data.get("context") else None),
        "pattern_coverage": hs["pattern_coverage"],
        "findings": data["findings"],
        "clean": data["clean"],
        "incomplete": data["failed"],
        "hotspots": [{"id": h["id"], "file": h["file"],
                      "url": _hotspot_link(data, h["id"], "url"),
                      "history_url": _hotspot_link(data, h["id"], "history_url"),
                      "score": h["scores"]["score"],
                      "churn": h["churn"], "complexity": h.get("complexity"),
                      "patterns": h["stability"]["patterns"]}
                     for h in hs["hotspots"]],
    }


def render_index(data: dict) -> dict:
    files: dict[str, dict] = {}
    for f in data["findings"]:
        loc = f.get("location") or {}
        path = loc.get("file")
        if not path:
            continue
        entry = files.setdefault(path, {"content_hash": f.get("content_hash"),
                                        "findings": []})
        item = {
            "id": f["id"], "key": f.get("key"), "lines": loc.get("lines"),
            "symbol": loc.get("symbol"),
            "failure_mode": f.get("failure_mode"),
            "missing_patterns": f.get("missing_patterns") or [],
            "confidence": f.get("confidence"),
            "sustaining_effect": f.get("sustaining_effect"),
        }
        if f.get("catalog_evidence"):
            item["catalog_evidence"] = f["catalog_evidence"]
        entry["findings"].append(item)
    return {"schema": "thunderstruck.index/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "head": data["hotspots"]["repo"]["head"],
            "report": f"{c.OUTPUT_DIRNAME}/report.md",
            "files": files}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="report.py", description="render the thunderstruck report")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--stdout", action="store_true", help="print the markdown instead of writing")
    args = ap.parse_args(argv)

    try:
        repo = c.find_repo_root(args.repo)
        data = collect(repo)
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2

    markdown = render_markdown(data, repo)
    if args.stdout:
        print(markdown)
        return 0

    out = c.out_dir(repo)
    (out / "report.md").write_text(markdown, encoding="utf-8")
    c.write_json(out / "report.json", render_json(data))
    c.write_json(out / "index.json", render_index(data))

    print(f"{len(data['findings'])} finding(s), "
          f"{len(data['clean'])} clean hotspot(s), "
          f"{len(data['failed'])} incomplete -> {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
