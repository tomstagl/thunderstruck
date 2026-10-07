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

    # dormant files are reported like hotspots only when they were investigated
    dormant = hotspots.get("dormant") or []
    briefed = {b.get("id") for b in (c.load_json(out / "bundles" / "index.json", {}) or {})
               .get("bundles", []) if isinstance(b, dict)}
    investigated = hotspots["hotspots"] + [d for d in dormant if d["id"] in briefed]
    scores = {h["id"]: h["scores"]["score"] for h in investigated}
    findings: list[dict] = []
    failed: list[dict] = []
    clean: list[dict] = []

    for hs in investigated:
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
            status = c.check_status(f)
            stored = f.get("check") if isinstance(f.get("check"), dict) else {}
            f["_check_fallback"] = stored.get("status") != status
            f["check"] = {"by": None, "reason": None, **stored, "status": status}
            f["confidence_claimed"] = f.get("confidence")
            f["confidence"] = c.effective_confidence(f["confidence_claimed"], status)
            f["gate"] = c.finding_gate(f)
            findings.append(f)

    findings.sort(key=order_key)
    for n, f in enumerate(findings, 1):
        f["id"] = f"FR-{n:03d}"
    check_warnings = [f"{f['id']}: check status missing or unrecognised in its findings file; "
                      f"reported as unchecked" for f in findings if f.pop("_check_fallback")]
    _attach_commit_subjects(repo, findings)
    shared = shared_code(findings)
    for f in findings:
        f["shares_code_with"] = shared.get(f["id"], [])
    context_doc = c.load_json(out / c.CONTEXT_FILENAME, {}) or {}
    if not isinstance(context_doc, dict):
        context_doc = {}
    raw_warnings = context_doc.get("warnings")
    link_meta, link_warnings, hotspot_links = link_refs(
        repo, hotspots["repo"]["head"], findings, hotspots["hotspots"] + dormant,
        clean + failed)
    failed_ids = {e["hotspot_id"] for e in failed}
    usage, usage_warnings = _usage(out, hotspots["generated_at"])
    return {"hotspots": hotspots, "findings": findings,
            "failed": failed, "clean": clean, "validation": validation,
            # what an investigator actually read: briefed, and not incomplete
            "read": [h for h in investigated if h["id"] not in failed_ids],
            "context": c.load_service_context(repo),
            "context_warnings": _context_warnings(raw_warnings),
            "links": link_meta, "link_warnings": link_warnings,
            "hotspot_links": hotspot_links,
            "usage": usage, "usage_warnings": usage_warnings,
            "check_warnings": check_warnings}


def _usage(out: Path, generated_at: str) -> tuple[dict | None, list[str]]:
    """usage.json, if usage.py measured this scan; an older one is ignored."""
    doc = c.load_json(out / "usage.json", None)
    if doc is None:
        return None, []
    window = doc.get("window") if isinstance(doc, dict) else None
    if not isinstance(window, dict) or window.get("from") != generated_at:
        return None, ["usage.json is from an earlier scan and was ignored"]
    return doc, []


def _attach_commit_subjects(repo: Path, findings: list[dict]) -> None:
    """Give every cited commit its subject, so a reader sees the history
    itself. The class is in `history`. The refs were already resolved by
    validate.py; a failure here renders as unavailable and never fails the
    report."""
    cache: dict[str, str | None] = {}

    def subject(sha: str) -> str | None:
        if sha not in cache:
            try:
                cache[sha] = c.git_paths(repo, "log", "-1", "--format=%s", sha, "--").strip("\n")
            except (c.ThunderstruckError, OSError, subprocess.SubprocessError):
                cache[sha] = None
        return cache[sha]

    for f in findings:
        for ev in _evidence(f):
            if ev.get("type") == "commit" and str(ev.get("ref") or "").strip():
                ev["subject"] = subject(str(ev["ref"]).split()[0])
        for h in _history(f):
            if h.get("sha"):
                h["subject"] = subject(str(h["sha"]))


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


def _cited_code_files(f: dict) -> list[str]:
    """Files a finding cites as code evidence, in citation order, once each."""
    out: list[str] = []
    for ev in _evidence(f):
        if ev.get("type") == "code" and (m := CODE_REF.match(str(ev.get("ref") or "").strip())):
            if m["path"] not in out:
                out.append(m["path"])
    return out


def _code_ranges(f: dict) -> list[tuple[str, str, int, int]]:
    out = []
    for ev in _evidence(f):
        ref = str(ev.get("ref") or "").strip()
        if ev.get("type") == "code" and (m := CODE_REF.match(ref)):
            start = int(m["start"])
            out.append((ref, m["path"], start, int(m["end"] or start)))
    return out


def shared_code(findings: list[dict]) -> dict[str, list[dict]]:
    """Findings from different hotspots whose code refs intersect (spec §2.5).
    Investigators never see each other's findings, so one defect can be
    reported from both sides. Linked, never merged: that is judgment."""
    ranges = [(f, _code_ranges(f)) for f in findings]
    out: dict[str, list[dict]] = {}
    for f, mine in ranges:
        for g, theirs in ranges:
            if g is f or g.get("hotspot_id") == f.get("hotspot_id"):
                continue
            refs = [ref for ref, path, a, b in mine
                    if any(p == path and a <= d and c_ <= b for _, p, c_, d in theirs)]
            if refs:
                out.setdefault(f["id"], []).append(
                    {"id": g["id"], "key": g.get("key"), "refs": list(dict.fromkeys(refs))})
    for links in out.values():
        links.sort(key=lambda s: s["id"])
    return out


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
            for p in _preconditions(f):
                for key in ("default_ref", "doc_ref"):
                    if (m := CODE_REF.match(str(p.get(key) or "").strip())):
                        paths.add(m["path"])
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


def _preconditions(f: dict) -> list[dict]:
    return [p for p in (f.get("preconditions") or []) if isinstance(p, dict)]


def _history(f: dict) -> list[dict]:
    return [h for h in (f.get("history") or []) if isinstance(h, dict)]


def order_key(f: dict) -> tuple:
    """Default-path findings first (#56 AC-5); inside a gate, today's order."""
    return (c.GATES.index(f.get("gate", "none")) if f.get("gate", "none") in c.GATES else len(c.GATES),
            CONFIDENCE_RANK.get(f.get("confidence"), 9),
            -(f.get("hotspot_score") or 0.0),
            str(f.get("location", {}).get("file", "")))


def _set_urls(findings: list[dict], result: "links.LinkResult | None", repo: Path) -> None:
    ctx = result.ctx if result else None
    for f in findings:
        loc = f.get("location")
        if isinstance(loc, dict):
            loc["url"] = _location_url(ctx, loc, repo) if ctx else None
        for ev in _evidence(f):
            ev["url"] = _evidence_url(ctx, result, ev) if ctx else None
        for p in _preconditions(f):
            p["default_url"] = _ref_url(ctx, p.get("default_ref"))
            p["doc_url"] = _ref_url(ctx, p.get("doc_ref"))
        for h in _history(f):
            full = result.commits.get(str(h.get("sha"))) if (ctx and result) else None
            h["url"] = ctx.commit(full) if full else None


def _ref_url(ctx: "links.LinkContext | None", ref) -> str | None:
    m = CODE_REF.match(str(ref or "").strip())
    if not ctx or not m:
        return None
    start, end = int(m["start"]), int(m["end"] or m["start"])
    return ctx.code(m["path"], min(start, end), max(start, end))


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
            out += (f" — “{md.text(subject)}”"
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


def _shared_line(f: dict) -> list[str]:
    links = f.get("shares_code_with") or []
    if not links:
        return []
    parts = [f"{s['id']} ({', '.join(md.code(r) for r in s['refs'])})" for s in links]
    return [f"Shares cited code with {', '.join(parts)}: one fix may close "
            f"{'both' if len(links) == 1 else 'all of them'}.", ""]


def _not_stated(value) -> str:
    return md.text(value, cell=True) if value else "_not stated_"


def render_check(f: dict) -> list[str]:
    status = f["check"]["status"]
    line = f"**Check** — {status}. {c.CHECK_SENTENCES[status]}"
    claimed = f.get("confidence_claimed")
    if claimed in c.CONFIDENCE_LEVELS and claimed != f.get("confidence"):
        line += (f", so it is reported at {md.text(f.get('confidence') or '?')} confidence "
                 f"(claimed {claimed})")
    line += "."
    if f["check"].get("reason"):
        line += f" {md.text(f['check']['reason'])}"
    return [line, ""]


def _precondition_line(p: dict) -> str:
    setting, default = md.code(p.get("setting")), md.code(p.get("default"))
    where = _linked(str(p.get("default_ref")), p.get("default_url"))
    if p.get("needs") == "changed":
        line = f"{setting} set to {md.code(p.get('value'))}; default {default}, registered at {where}."
    else:
        line = f"{setting} left at its default {default}, registered at {where}."
    if p.get("documented") == "yes":
        line += f" The docs describe this behaviour: {_linked(str(p.get('doc_ref')), p.get('doc_url'))}."
    elif p.get("documented") == "no":
        line += " The docs do not describe this behaviour."
    else:
        line += " Docs not checked."
    return f"- {line}"


def render_preconditions(f: dict) -> list[str]:
    items = _preconditions(f)
    if not items:
        return ["**Preconditions** — none: the failure happens on default settings.", ""]
    L = ["**Preconditions**", ""]
    if f.get("gate") == "none":
        L += ["The failure happens on default settings and rests on these defaults:", ""]
    return L + [_precondition_line(p) for p in items] + [""]


def render_history(f: dict) -> list[str]:
    items = _history(f)
    if not items:
        return ["**History** — none cited.", ""]
    L = ["**History** — a signal of how often this code changed, not of whether the claim holds.", ""]
    for h in items:
        cls = md.text(h["class"]) if h.get("class") else "class unavailable"
        wrote = "wrote a cited line" if h.get("wrote_cited_line") else "wrote none of the cited lines"
        L.append(f"- {_linked(str(h.get('sha'))[:7], h.get('url'))} {cls} · "
                 f"stated role: {md.text(h.get('role') or '?')} · {wrote}")
    return L + [""]


def render_dormant(data: dict) -> list[str]:
    """Untouched files that carry integration-point leads (#19 AC-7)."""
    rows = data["hotspots"].get("dormant") or []
    if not rows:
        return []
    L = ["", "## Dormant integration points", "",
         "No commit touched these files in the window, so they cannot rank on churn. "
         "They carry integration-point leads (timeouts, retries, pushback, blocking "
         "calls), and code nobody changes is often code everything depends on. They "
         "are investigated only with `--investigate-dormant N`."
         + (" Files marked *script* sit in a scripts, tools or examples directory and "
            "are listed last: they are usually run by hand, not in production."
            if any(d.get("script") for d in rows) else ""), "",
         "| # | File | Last change | Leads |",
         "|---|---|---|---|"]
    for d in rows:
        pats = ", ".join(md.text(p, cell=True) for p in d["stability"]["patterns"]) or "—"
        file_cell = _linked(d["file"], _hotspot_link(data, d["id"], "url"), cell=True)
        if d.get("script"):
            file_cell += " · script"
        when = md.text((d["churn"].get("last_modified") or "—")[:10], cell=True)
        L.append(f"| {d['id']} | {file_cell} | {when} | {pats} |")
    return L


def lead_precision(data: dict) -> dict[str, dict[str, int]]:
    """Per pattern: detector hits in the files an investigator read (hotspots
    and investigated dormant files, not incomplete ones), and the distinct
    ones cited by a finding whose citations resolved (confirmed). Over many runs this is
    the detector's precision on code we never see (#19 AC-2)."""
    out: dict[str, dict[str, int]] = {}
    read = data.get("read")
    for h in data["hotspots"]["hotspots"] if read is None else read:
        for hit in h.get("detector_hits") or []:
            out.setdefault(hit["pattern_id"], {"read": 0, "confirmed": 0})["read"] += 1
    confirmed: set[str] = set()
    for f in data["findings"]:
        for ev in _evidence(f):
            if ev.get("type") == "detector" and (m := DETECTOR_REF.match(str(ev.get("ref") or ""))):
                confirmed.add(m.group(0))
    for ref in confirmed:
        pid = DETECTOR_REF.match(ref)["pid"]
        out.setdefault(pid, {"read": 0, "confirmed": 0})["confirmed"] += 1
    return dict(sorted(out.items()))


GAP_LABELS = {"test": "test code", "generated": "generated code", "vendored": "vendored code",
              "build": "build output", "migration": "database migrations",
              "asset": "lock files and assets", "tooling": "CI and tooling configuration",
              "profile": "excluded by the repo profile", "path": "outside --path"}


def _plain(value) -> str:
    return str(value)


def not_scanned(gaps: dict | None, code=_plain, text=_plain) -> dict | None:
    """The **Not scanned** sentences. `code` and `text` format the spans:
    report.md passes the mdtext ones, report.json keeps plain text."""
    if not isinstance(gaps, dict):
        return None
    items = []
    if gaps.get("unchanged"):
        items.append(f"{gaps['unchanged']} in a supported language had no commit in the "
                     f"window, so they could not rank on churn")
    if gaps.get("not_citable"):
        items.append(f"{gaps['not_citable']} are not citable (symbolic links, submodules, "
                     f"or names that are not UTF-8)")
    for reason, n in (gaps.get("excluded") or {}).items():
        items.append(f"{n} excluded: {text(GAP_LABELS.get(reason, reason))}")
    unsupported = gaps.get("unsupported") or {}
    if unsupported:
        kinds = ", ".join(f"{n} {code(ext) if ext != 'other' else 'other'}"
                          for ext, n in sorted(unsupported.items(), key=lambda kv: (-kv[1], kv[0])))
        items.append(f"no detectors for their language or format: {kinds}")
    return {"intro": f"Of {gaps.get('tracked', 0)} tracked files, {gaps.get('considered', 0)} "
                     f"changed in the window in a supported language and were considered "
                     f"for ranking.",
            "items": items}


def render_not_scanned(gaps: dict | None) -> list[str]:
    """What the scan did not look at, and why. Degradation is visible (#19 AC-1)."""
    section = not_scanned(gaps, code=md.code, text=md.text)
    if section is None:
        return []
    return ["## Not scanned", "", section["intro"], "",
            *[f"- {item}" for item in section["items"]], ""]


def run_warnings(data: dict) -> list[str]:
    """The list under **Run warnings**: hotspot, context and link warnings."""
    return (list(data["hotspots"].get("warnings") or [])
            + list(data.get("context_warnings") or [])
            + list(data.get("link_warnings") or [])
            + list(data.get("usage_warnings") or [])
            + list(data.get("check_warnings") or []))


def _k(n: int) -> str:
    return f"{round(n / 1000)}k"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _part(part: dict) -> tuple[int, str]:
    by_model = part.get("by_model") or {}
    weighted = sum(row.get("weighted") or 0 for row in by_model.values())
    return weighted, ", ".join(md.code(m) for m in by_model)


def render_consumption(usage: dict | None) -> list[str]:
    """## Consumption: what the scan consumed, or why it was not measured (#5)."""
    if not usage:
        return []
    missing = [md.text(m) for m in usage.get("missing") or []]
    if usage.get("source") == "unavailable":
        return ["## Consumption", "", f"Consumption was not measured: {'; '.join(missing)}.", ""]
    orch, inv = usage.get("orchestrator") or {}, usage.get("investigators") or {}
    o_weighted, o_models = _part(orch)
    i_weighted, i_models = _part(inv)
    partial = usage.get("source") != "transcripts"
    total = f"{_k(usage.get('total_weighted') or 0)} weighted tokens"
    lines = [f"Signals to report, measured parts only: {total}." if partial
             else f"Signals to report: {total}."]
    if orch.get("by_model"):
        lines.append(f"Orchestrator {_k(o_weighted)} ({o_models}, "
                     f"{_plural(orch.get('calls') or 0, 'call')}).")
    else:
        lines.append("Orchestrator not measured.")
    lines.append(f"Investigators {_k(i_weighted)} across "
                 f"{_plural(inv.get('agents') or 0, 'agent')} ({i_models or 'none measured'}), "
                 f"{_plural(inv.get('repairs') or 0, 'repair')}, "
                 f"{_plural(inv.get('respawns') or 0, 're-spawn')}.")
    if inv.get("fallback_saves"):
        lines.append(f"{inv['fallback_saves']} result(s) saved by the orchestrator because "
                     f"the hook did not deliver them.")
    if partial:
        covers = (["the orchestrator"] if orch.get("by_model") else []) + \
            [f"investigators for {_plural(len(inv.get('by_hotspot') or {}), 'hotspot')}"]
        lines.append(f"Covers: {' and '.join(covers)}. Not measured: {'; '.join(missing)}.")
    lines.append("Weighted by published price per model and token type, "
                 "Claude Sonnet 5.5 input = 1.")
    return ["## Consumption", "", *[f"{line}  " for line in lines[:-1]], lines[-1], ""]


def coverage_rows(data: dict) -> list[dict]:
    """The **Pattern coverage** table, one dict per row in report.md order.
    The OTHER row, when present, has None where report.md shows a dash."""
    hs, findings = data["hotspots"], data["findings"]
    lead_files = {pid: cov["files"] for pid, cov in hs["pattern_coverage"].items()}
    per_pattern: dict[str, int] = {}
    for f in findings:
        for pid in f.get("missing_patterns") or []:
            per_pattern[pid] = per_pattern.get(pid, 0) + 1
    precision = lead_precision(data)
    confirmed_files: dict[str, set[str]] = {}
    ranked_files = {h["file"] for h in hs["hotspots"]}  # lead_files counts ranked candidates
    for f in findings:
        for ev in _evidence(f):
            if ev.get("type") == "detector" and (m := DETECTOR_REF.match(str(ev.get("ref") or ""))):
                if m["path"] in ranked_files:
                    confirmed_files.setdefault(m["pid"], set()).add(m["path"])
    rows = []
    for pid, cov in sorted(hs["pattern_coverage"].items()):
        if not cov.get("scanned"):
            continue
        p = precision.get(pid, {"read": 0, "confirmed": 0})
        rows.append({"id": pid, "name": cov["name"], "tier": cov["tier"],
                     "unconfirmed_files": max(0, lead_files.get(pid, 0)
                                              - len(confirmed_files.get(pid, ()))),
                     "leads_read": p["read"], "leads_confirmed": p["confirmed"],
                     "findings": per_pattern.get(pid, 0)})
    if per_pattern.get("OTHER"):
        rows.append({"id": "OTHER", "name": "Not in the catalog", "tier": None,
                     "unconfirmed_files": None, "leads_read": None, "leads_confirmed": None,
                     "findings": per_pattern["OTHER"]})
    return rows


def clean_cited_by(findings: list[dict]) -> dict[str, list[str]]:
    """File -> ids of findings that cite it as code evidence but are not
    located in it: a clean hotspot with "no finding of its own"."""
    cited_by: dict[str, list[str]] = {}
    for f in findings:
        for cited in _cited_code_files(f):
            if cited != (f.get("location") or {}).get("file"):
                cited_by.setdefault(cited, []).append(f["id"])
    return cited_by


def _files_affected(findings: list[dict]) -> int:
    return len({f["location"]["file"] for f in findings if f.get("location")})


def render_markdown(data: dict, repo: Path, now: datetime | None = None) -> str:
    hs, findings = data["hotspots"], data["findings"]
    repo_name = Path(hs["repo"]["root"]).name
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.get("confidence", "?")] = counts.get(f.get("confidence", "?"), 0) + 1
    breakdown = ", ".join(f"{n} {md.text(k)}" for k, n in
                          sorted(counts.items(), key=lambda kv: CONFIDENCE_RANK.get(kv[0], 9)))
    files_affected = _files_affected(findings)
    by_status = [(s, sum(1 for f in findings if f["check"]["status"] == s)) for s in c.CHECK_STATUSES]
    gated = sum(1 for f in findings if f["gate"] != "none")
    check_line = ("Check status: " + " · ".join(f"{n} {s}" for s, n in by_status if n)
                  + (f" · {gated} {'finding needs' if gated == 1 else 'findings need'} a "
                     f"non-default setting and {'is' if gated == 1 else 'are'} listed last"
                     if gated else "")) if findings else None

    L: list[str] = [
        f"# thunderstruck — {md.text(repo_name, heading=True)}",
        "",
        f"**{md.text(repo_name)}** · {md.code(hs['repo']['branch'])} @ {md.code(hs['repo']['head'][:7])}  ",
        f"Scanned {hs['generated_at'][:10]} · window {md.code(hs['window']['since'])} "
        f"(since {md.text(hs['window']['since_date'])}, {hs['window']['commits']} commits) · "
        f"{hs['counts']['files_considered']} files considered · "
        f"{hs['counts']['hotspots']} hotspots investigated  ",
        f"**{len(findings)} finding(s)** across {files_affected} file(s)"
        + (f" — {breakdown}" if breakdown else "") + "  ",
        *([check_line] if check_line else []),
        "",
        "> Findings are **falsifiable hypotheses**. Every citation in them was resolved "
        "mechanically: each cited file:line, commit, detector hit and catalog edge exists. "
        "That is all validation proves. Whether a claim holds is its **check status**; a "
        "finding nobody has tried to refute is `unchecked`, and its confidence is at most "
        "`medium`. Check the `Verify` line before you act on one.",
        "",
    ]

    warnings = run_warnings(data)
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
    L += render_consumption(data.get("usage"))
    L += render_not_scanned(hs.get("coverage_gaps"))
    L += render_service_context(data.get("context"), now or datetime.now(timezone.utc))

    # ---- coverage table
    L += ["## Pattern coverage", "",
          "Leads are detector hits — mechanical, noisy, and never a finding on "
          "their own. Findings are what survived an investigator reading the code. "
          "*Leads read* counts the hits inside investigated hotspots; *Leads "
          "confirmed* counts those cited by a finding whose citations resolved.",
          "",
          "| ID | Pattern | Tier | Files with an unconfirmed lead | Leads read "
          "| Leads confirmed | Findings |",
          "|---|---|---|---|---|---|---|"]
    for row in coverage_rows(data):
        if row["id"] == "OTHER":
            L.append(f"| `OTHER` | Not in the catalog | — | — | — | — | {row['findings']} |")
            continue
        L.append(f"| {md.code(row['id'], cell=True)} | {md.text(row['name'], cell=True)} | "
                 f"{md.text(row['tier'], cell=True)} | {row['unconfirmed_files']} | "
                 f"{row['leads_read']} | {row['leads_confirmed']} | {row['findings']} |")
    L += ["", "<sub>“0” leads means no file matched the detector's anchor. It "
          "does not mean the pattern is present.</sub>", ""]

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
                    f"| Amplifier | {_not_stated(f.get('amplifier'))} |",
                    f"| Sustaining effect | {_not_stated(f.get('sustaining_effect'))} |",
                    f"| Blast radius | {md.text(f.get('blast_radius', '—'), cell=True)} |"]
            if f.get("catalog_evidence"):
                rows.append(f"| Dependents / dependencies | {_deps(f['catalog_evidence'])} |")
            rows.append(f"| Missing patterns | {', '.join(md.code(p, cell=True) for p in f.get('missing_patterns') or []) or '—'} |")
            marker = f" · {c.GATE_MARKERS[f['gate']]}" if f["gate"] in c.GATE_MARKERS else ""
            badge = (f"**{BADGE.get(f.get('confidence'), '?')} confidence** · "
                     f"{f['check']['status']}{marker} · ")
            L += [f"### {f['id']} · {md.text(f.get('failure_mode', '(no failure mode)'), heading=True)}",
                  "",
                  badge + f"{where}{symbol} · hotspot {f['hotspot_id']} (score {f.get('hotspot_score')})",
                  "",
                  *_shared_line(f),
                  *rows,
                  "",
                  "**Evidence**", ""]
            for ev in f.get("evidence") or []:
                note = f" — {md.text(ev['note'])}" if ev.get("note") else ""
                L.append(f"- _{md.text(ev.get('type'))}_ {_evidence_ref(ev)}{note}")
            L += ["", *render_check(f), *render_preconditions(f), *render_history(f),
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
        cited_by = clean_cited_by(findings)
        for entry in data["clean"]:
            note = f" — {md.text(entry['notes'])}" if entry.get("notes") else ""
            if entry["file"] in cited_by:
                note = (" — no finding of its own; cited as evidence by "
                        + ", ".join(cited_by[entry["file"]]) + note)
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
    L += render_dormant(data)
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
    cited_by = clean_cited_by(data["findings"])
    return {
        "schema": c.REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scanned_at": hs["generated_at"],
        "repo": hs["repo"],
        "window": hs["window"],
        "catalog_schema": hs.get("schema"),
        "counts": {
            "hotspots": hs["counts"]["hotspots"],
            "files_considered": hs["counts"]["files_considered"],
            "findings": len(data["findings"]),
            "clean_hotspots": len(data["clean"]),
            "failed_hotspots": len(data["failed"]),
            "check_status": {s: sum(1 for f in data["findings"] if f["check"]["status"] == s)
                             for s in c.CHECK_STATUSES},
            "gate": {g: sum(1 for f in data["findings"] if f["gate"] == g) for g in c.GATES},
        },
        "warnings": list(hs.get("warnings") or []) + list(data.get("link_warnings") or []),
        "run_warnings": run_warnings(data),
        "suppressed": [{"detector": r["detector"], "path": r["path"], "hits": r["hits"],
                        "reason": r["reason"]} for r in hs.get("suppressed") or []],
        "links": data.get("links"),
        "degraded": hs.get("degraded", {}),
        "service_context": ({k: data["context"].get(k) for k in
                             ("status", "entity_ref", "context_hash", "fetched_at",
                              "edges", "truncated")}
                            if data.get("context") else None),
        "pattern_coverage": hs["pattern_coverage"],
        "coverage_rows": coverage_rows(data),
        "files_affected": _files_affected(data["findings"]),
        "coverage_gaps": hs.get("coverage_gaps"),
        "not_scanned": not_scanned(hs.get("coverage_gaps")),
        "dormant": [{"id": d["id"], "file": d["file"], "script": bool(d.get("script")),
                     "last_modified": d["churn"].get("last_modified"),
                     "patterns": d["stability"]["patterns"],
                     "url": _hotspot_link(data, d["id"], "url")}
                    for d in hs.get("dormant") or []],
        "lead_precision": lead_precision(data),
        "consumption": data.get("usage") or None,
        "findings": data["findings"],
        "clean": [{**e, "cited_by": cited_by.get(e["file"], [])} for e in data["clean"]],
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
    secondary: list[tuple[str, dict, str]] = []
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
            "check_status": f["check"]["status"],
            "gate": f["gate"],
            "preconditions": [{k: p.get(k) for k in ("setting", "default", "needs", "value")}
                              for p in _preconditions(f)],
            "history": [{k: h.get(k) for k in ("sha", "class", "wrote_cited_line")}
                        for h in _history(f)],
        }
        if f.get("sustaining_effect"):
            item["sustaining_effect"] = f["sustaining_effect"]
        if f.get("catalog_evidence"):
            item["catalog_evidence"] = f["catalog_evidence"]
        entry["findings"].append(item)
        for cited in _cited_code_files(f):
            if cited != path:
                secondary.append((cited, item, path))
    # A finding also warns on every other file it cites as code evidence. Paths
    # are canonical (#25), so one file never gets two entries.
    hashes = {cited: h for f in data["findings"]
              for cited, h in (f.get("evidence_hashes") or {}).items()}
    for cited, item, anchor in secondary:
        entry = files.setdefault(cited, {"content_hash": hashes.get(cited), "findings": []})
        entry["findings"].append({**item, "via": "evidence", "anchor": anchor})
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
