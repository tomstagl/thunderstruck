#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Write a ticket for one finding of the last scan (#108).

A finding ticket is the text a scan runner files in the scanned repository's
tracker: the claim, the code it cites copied from the scanned commit, links,
what is traced and what is inferred, and where the fix and review guidance is.
Every section comes from `.thunderstruck/report.json` and git. The four
judgement sections (fix options, acceptance criteria, out of scope, rollout and
rollback) are in no finding: they come from an optional file a model may write,
validated here and shown as a proposal, otherwise they read "not assessed".

    uv run scripts/finding_ticket.py --list
    uv run scripts/finding_ticket.py --key 483fd943cc43
    uv run scripts/finding_ticket.py --key 483fd943cc43 --status "Fix proposed"

Writes `.thunderstruck/tickets/<key>.md` and nothing else. It stops, naming the
cause and writing nothing, when a cited file is no longer the scanned commit's.
"""

from __future__ import annotations

import argparse
import copy
import getpass
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
import links  # noqa: E402
import mdtext as md  # noqa: E402
import report  # noqa: E402
from validate import CODE_REF  # noqa: E402

TICKETS_DIRNAME = "tickets"
STATUSES = ("Hypothesis", "Reproduced", "Fix proposed", "Fix reviewed")
KEY_SHAPE = re.compile(r"[0-9a-f]{12}\Z")
MAX_LISTED_KEYS = 20


def stop(message: str) -> c.ThunderstruckError:
    return c.ThunderstruckError(message)


def load_report(repo: Path) -> dict:
    """report.json of the last scan, in the one schema this reads."""
    rep = c.load_json(c.out_dir(repo) / "report.json")
    if not isinstance(rep, dict) or not rep:
        raise stop("no report.json: run /thunderstruck-scan, or report.py, first.")
    if rep.get("schema") != c.REPORT_SCHEMA_VERSION:
        raise stop(f"report.json has schema {rep.get('schema')!r}; this version reads "
                   f"{c.REPORT_SCHEMA_VERSION!r}. Re-run the scan.")
    if not isinstance(rep.get("findings"), list):
        raise stop("report.json holds no list of findings. Re-run the scan.")
    return rep


def _one_line(value, limit: int) -> str:
    """Terminal-safe: one line, controls dropped, clipped."""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(value or ""))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _reported(rep: dict) -> list[dict]:
    return [f for f in rep.get("findings") or [] if isinstance(f, dict)]


def list_findings(rep: dict) -> list[str]:
    """One line per reported finding: `key · id · location · failure mode`."""
    out = []
    for f in _reported(rep):
        loc = f.get("location") if isinstance(f.get("location"), dict) else {}
        where = f"{loc.get('file', '?')}" + (f":{loc['lines']}" if loc.get("lines") else "")
        out.append(f"{_one_line(f.get('key'), 12)} · {_one_line(f.get('id'), 12)} · "
                   f"{_one_line(where, 80)} · {_one_line(f.get('failure_mode'), 100)}")
    return out


def _normalised(finding: dict) -> dict:
    """A copy with the `check` report.collect gives every finding, so the renderers
    can index it: a missing or unrecognised status reads as unchecked."""
    f = copy.deepcopy(finding)
    stored = f.get("check") if isinstance(f.get("check"), dict) else {}
    f["check"] = {"by": None, "reason": None, **stored, "status": c.check_status(f)}
    return f


def find_finding(rep: dict, key: str) -> dict:
    """The reported finding with this `key` (never its display id, which renumbers),
    or a refusal that says what to do instead."""
    if not isinstance(key, str) or not KEY_SHAPE.match(key):
        raise stop(f"a finding key is 12 lowercase hex characters, as `--list` prints them; "
                   f"got {json.dumps(key)[:60]}.")
    for f in _reported(rep):
        if f.get("key") == key:
            return _normalised(f)
    for f in rep.get("refuted") or []:
        if isinstance(f, dict) and f.get("key") == key:
            raise stop(f"finding {key} was refuted by verification, so no ticket is made for it. "
                       "It is listed under 'Refuted by verification' in report.md.")
    for f in _reported(rep):
        for at in f.get("also_at") or []:
            if isinstance(at, dict) and at.get("key") == key:
                raise stop(f"finding {key} is a duplicate: it is reported as also at the location "
                           f"of finding {f.get('key')}. Make the ticket for that key.")
    listing = list_findings(rep)
    shown = "\n  ".join(listing[:MAX_LISTED_KEYS])
    more = f"\n  … and {len(listing) - MAX_LISTED_KEYS} more" if len(listing) > MAX_LISTED_KEYS else ""
    raise stop(f"no finding with key {key} in this scan. Findings:\n  {shown}{more}"
               if listing else f"no finding with key {key}: this scan reported no findings.")


def parse_status(value: str) -> str:
    """One of the four statuses, case-insensitive, `-` or `_` for a space."""
    wanted = re.sub(r"[-_\s]+", " ", str(value).strip()).lower()
    for status in STATUSES:
        if status.lower() == wanted:
            return status
    raise argparse.ArgumentTypeError(f"status must be one of {', '.join(STATUSES)}")


def recorded_reproduction(finding: dict) -> dict | None:
    """The finding's recorded failing reproduction, or None.

    Nothing records one yet: `/thunderstruck-verify` leaves no data. #103 will, and
    the follow-up that lets `Reproduced` read that record changes this function.
    """
    return None


def require_status(status: str, finding: dict) -> None:
    """`Reproduced` is the one claim the plugin can check: it needs a recorded reproduction."""
    if status == "Reproduced" and recorded_reproduction(finding) is None:
        raise stop(f"status Reproduced refused for finding {finding.get('key')}: no failing "
                   "reproduction is recorded for it. A reproduction is a failing test that a "
                   "verification run left behind and recorded; thunderstruck does not record one "
                   "yet (issue #103 in the thunderstruck repository). Ask for Hypothesis, or "
                   "record a reproduction first. No ticket was written.")


FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
GIT_TIMEOUT = 30
WAY_FORWARD = ("Rescan with /thunderstruck-scan, or check out the scanned commit {sha} "
               "(`git switch --detach {sha}`; stash or commit edits to those files first) "
               "and run this again. If it then stops with \"changed since the scan recorded it\", "
               "the scan saw that file in another state, and only a rescan fixes that.")
WAY_RESCAN = ("Rescan with /thunderstruck-scan. The scan saw a file above in a state the scanned "
              "commit does not have, so checking out the commit cannot fix that.")
SCAN_SAW_OTHER = ("changed since the scan recorded it", "has no hash recorded by the scan")


def quoted_files(finding: dict) -> list[str]:
    """The files a ticket quotes or links, canonical, once each: the finding's own file
    and every file it cites as code."""
    loc = finding.get("location") if isinstance(finding.get("location"), dict) else {}
    out = [c.ref_path(loc["file"])] if loc.get("file") else []
    for ev in finding.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("type") == "code":
            m = CODE_REF.match(str(ev.get("ref") or "").strip())
            if m:
                out.append(c.ref_path(m["path"]))
    return list(dict.fromkeys(out))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=GIT_TIMEOUT)


def _why_stale(repo: Path, sha: str, rel: str, index: dict | None) -> str:
    """Why a file links would leave unlinked is not the scanned commit's, for the message
    only: the decision was made by links.stale_paths."""
    if index is None:
        return "differs from the scanned commit, or is not in it"
    mode = index.get(rel)
    if mode is None:
        return "is not tracked by git"
    if mode == "120000":
        return "is a symbolic link"
    if mode == "160000":
        return "is a submodule"
    if not os.path.lexists(repo / rel):
        return "is missing from the working tree"
    if _git(repo, "cat-file", "-e", f"{sha}:{rel}").returncode != 0:
        return "is not in the scanned commit"
    return "differs from the scanned commit"


def check_snapshot(repo: Path, rep: dict, finding: dict) -> None:
    """Raise unless every file the ticket quotes is the scanned commit's file, and is
    the file the scan recorded: the snippets are read from that commit, and a ticket
    over other code would send a fixer to the wrong place."""
    repo_block = rep.get("repo") if isinstance(rep.get("repo"), dict) else {}
    sha = repo_block.get("head")
    if not isinstance(sha, str) or not FULL_SHA.match(sha):
        raise stop("report.json records no scanned commit (repo.head is not a 40-character sha), so "
                   "the cited code cannot be checked against it. Rescan with /thunderstruck-scan.")
    files = quoted_files(finding)
    try:
        if _git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
            raise stop(f"the scanned commit {sha} is not in this repository (a shallow or a "
                       "different clone?). Fetch it, or rescan with /thunderstruck-scan.")
        for rel in files:
            if (why := c.path_problem(rel)):
                raise stop(f"the finding cites {json.dumps(rel)}, which {why}. "
                           "Rescan with /thunderstruck-scan.")
        try:
            stale = links.stale_paths(repo, sha, files)
        except (c.ThunderstruckError, OSError):
            raise stop("git failed while comparing the cited files with the scanned commit. "
                       "Check the repository, then run this again.") from None
        problems: dict[str, str] = {}
        if stale:
            try:
                index = c.tracked_index(repo)
            except (c.ThunderstruckError, OSError):
                index = None
            problems = {rel: _why_stale(repo, sha, rel, index) for rel in files if rel in stale}
    except subprocess.TimeoutExpired:
        raise stop(f"git did not answer within {GIT_TIMEOUT}s while checking the cited files.") from None
    except OSError:
        raise stop("git could not be run.") from None
    loc = finding.get("location") if isinstance(finding.get("location"), dict) else {}
    by_path = finding.get("evidence_hashes") if isinstance(finding.get("evidence_hashes"), dict) else {}
    for rel in files:
        if rel in problems:
            continue
        recorded = {h for h in (finding.get("content_hash") if loc.get("file") and
                                c.ref_path(loc["file"]) == rel else None, by_path.get(rel))
                    if isinstance(h, str)}
        if not recorded:
            problems[rel] = "has no hash recorded by the scan"
        elif any(h != c.sha256_file(repo / rel) for h in recorded):
            problems[rel] = "changed since the scan recorded it"
    if problems:
        rows = [f"{json.dumps(rel)}: {why}" for rel, why in problems.items()]
        more = len(rows) - links.MAX_NAMED
        way = (WAY_RESCAN if any(why in SCAN_SAW_OTHER for why in problems.values())
               else WAY_FORWARD.format(sha=sha))
        raise stop(f"no ticket was written for finding {finding.get('key')}: the code it cites is "
                   "not the scan's.\n  " + "\n  ".join(rows[:links.MAX_NAMED])
                   + (f"\n  … and {more} more" if more > 0 else "") + "\n" + way)


URL_KEYS = frozenset({"url", "default_url", "doc_url", "history_url"})
_URL_OK = re.compile(r"https?://[^\s<>()\[\]\"'\\`]+\Z")


def safe_url(url) -> bool:
    """A plain web address that cannot end a Markdown link or open another one. The
    tool made every `url` in report.json; this also holds against a hand-edited file."""
    return isinstance(url, str) and _URL_OK.match(url) is not None


def clean_urls(value):
    """Set every link field that is not a safe address to None, in place, at any depth."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in URL_KEYS:
                if item is not None and not safe_url(item):
                    value[key] = None
            else:
                clean_urls(item)
    elif isinstance(value, list):
        for item in value:
            clean_urls(item)
    return value


MAX_STEPS = 12
MAX_SNIPPET_LINES = 40
MAX_LINE_CHARS = 240


@dataclass(frozen=True)
class Step:
    label: str          # path:start or path:start-end, rebuilt from the numbers, never copied
    start: int
    end: int
    lines: list[str]    # as cut: at most MAX_SNIPPET_LINES lines of at most MAX_LINE_CHARS
    hidden: int         # lines of the citation not shown
    shortened: int      # shown lines cut to MAX_LINE_CHARS
    url: str | None
    note: str


def blob_lines(repo: Path, sha: str, rel: str) -> list[str]:
    """The lines of `rel` at `sha`, counted as validate.py and git blame count them: split
    at \n only, the empty string after a final newline dropped, one trailing \r dropped
    per line, an empty file one empty line. A file git stores as an LFS pointer is a stop: the
    working tree may hold the real content, but the commit holds the pointer."""
    proc = _git(repo, "cat-file", "blob", f"{sha}:{rel}")
    if proc.returncode != 0:
        raise stop(f"{json.dumps(rel)} is not in the scanned commit. Rescan with /thunderstruck-scan.")
    if proc.stdout.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise stop(f"{json.dumps(rel)} is stored with Git LFS at the scanned commit: the commit holds a "
                   "pointer, not the code, so no snippet can be taken from it.")
    parts = proc.stdout.split(b"\n")
    if parts[-1] == b"":
        parts.pop()
    return [(p[:-1] if p.endswith(b"\r") else p).decode("utf-8", "replace") for p in parts] or [""]


def code_steps(repo: Path, sha: str, finding: dict) -> tuple[list[Step], int]:
    """One step per `code` evidence item, in the finding's order: the cited lines of the
    file at the scanned commit, cut to the caps. Also how many items the cap left out."""
    files: dict[str, list[str]] = {}
    steps: list[Step] = []
    omitted = 0
    for ev in finding.get("evidence") or []:
        if not (isinstance(ev, dict) and ev.get("type") == "code"):
            continue
        m = CODE_REF.match(str(ev.get("ref") or "").strip())
        if not m:
            continue
        rel = c.ref_path(m["path"])
        start = int(m["start"])
        end = int(m["end"] or m["start"])
        if rel not in files:
            files[rel] = blob_lines(repo, sha, rel)
        total = len(files[rel])
        if not 1 <= start <= end <= total:
            raise stop(f"the finding cites {json.dumps(rel)} lines {start}-{end}, but the file at the "
                       f"scanned commit has {total} lines. Rescan with /thunderstruck-scan.")
        if len(steps) >= MAX_STEPS:
            omitted += 1
            continue
        taken = files[rel][start - 1:end]
        shown = taken[:MAX_SNIPPET_LINES]
        steps.append(Step(label=f"{rel}:{start}" + (f"-{end}" if end != start else ""),
                          start=start, end=end,
                          lines=[line[:MAX_LINE_CHARS] for line in shown],
                          hidden=len(taken) - len(shown),
                          shortened=sum(1 for line in shown if len(line) > MAX_LINE_CHARS),
                          url=ev.get("url") if safe_url(ev.get("url")) else None,
                          note=str(ev.get("note") or "")))
    return steps, omitted


def render_step(n: int, step: Step) -> list[str]:
    """`### Step n`, the link, the code in a fence, what to notice. Whatever was cut or
    shown as an escape is said after the fence, so the fence holds only the file's text."""
    block, escaped = md.verbatim(step.lines)
    notes = []
    if step.hidden:
        first = step.start + len(step.lines)
        where = f"Line {first}" if first == step.end else f"Lines {first}-{step.end}"
        notes.append(f"{where} ({step.hidden} line{'s' if step.hidden != 1 else ''}) not shown: "
                     "open the link or the file.")
    if step.shortened:
        notes.append(f"{step.shortened} {'line was' if step.shortened == 1 else 'lines were'} "
                     f"shortened to {MAX_LINE_CHARS} characters.")
    if escaped:
        notes.append(f"{escaped} control or bidirectional "
                     f"{'character is' if escaped == 1 else 'characters are'} shown as \\uXXXX.")
    L = [f"### Step {n}", "", md.linked(step.label, step.url), "", block, ""]
    if notes:
        L += [" ".join(notes), ""]
    note = md.text(step.note) if step.note.strip() else "not stated."
    return L + [f"What to notice: {note}", ""]


SECTIONS_SCHEMA = "thunderstruck.ticket-sections/v1"
JUDGEMENT = (("fix_options", "Fix options"), ("acceptance_criteria", "Acceptance criteria"),
             ("out_of_scope", "Out of scope"), ("rollout_and_rollback", "Rollout and rollback"))
MAX_SECTION_ITEMS = 8
MAX_ITEM_CHARS = 400
MAX_SECTIONS_BYTES = 64 * 1024
# Where the guidance documents live in the plugin repository (#107). A test pins this
# to tests/guidance_check.PUBLISHED; a script never imports from tests/.
GUIDANCE = {"fix": "docs/fix-agent-instructions.md", "review": "docs/review-briefs.md"}
UNLINKED = {"catalog": "catalog data has no source location",
            "dependency": "a dependency's source is not in this repository",
            "commit": "commit not found in this repository"}


@dataclass(frozen=True)
class Drafts:
    sections: dict[str, list[str]]   # section id -> validated items, only the usable ones
    unused: dict[str, str]           # section id -> why its draft is not used
    notes: list[str]                 # for Provenance: markdown built from fixed words and code spans
    digest: str | None               # sha256 of the file when there was one


def sections_path(repo: Path, key: str) -> Path:
    return c.out_dir(repo) / TICKETS_DIRNAME / f"{key}.sections.json"


def load_sections(path: Path, key: str, scanned_at) -> Drafts:
    """The drafted judgement sections, validated like any model output: untrusted, bound to
    this finding and scan, shape-checked, never raising. What is not usable is said."""
    if not os.path.lexists(path):
        return Drafts({}, {}, [], None)
    digest: str | None = None

    def whole(reason: str) -> Drafts:
        return Drafts({}, {sid: reason for sid, _ in JUDGEMENT},
                      [f"The drafts file was not used: {reason}."], digest)

    try:
        if path.is_symlink() or not path.is_file():
            return whole("it is not a regular file")
        if path.stat().st_size > MAX_SECTIONS_BYTES:
            return whole(f"it is larger than {MAX_SECTIONS_BYTES // 1024} KB")
        data = path.read_bytes()
    except OSError:
        return whole("it could not be read")
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    try:
        doc = json.loads(data.decode("utf-8"))
    except ValueError:
        return whole("it is not valid UTF-8 JSON")
    if not isinstance(doc, dict):
        return whole("it is not a JSON object")
    if doc.get("schema") != SECTIONS_SCHEMA:
        return whole(f"its schema is not {SECTIONS_SCHEMA}")
    if doc.get("key") != key or not isinstance(scanned_at, str) or doc.get("scanned_at") != scanned_at:
        return whole("it was written for another finding or an earlier scan")
    body = doc.get("sections")
    if not isinstance(body, dict):
        return whole("`sections` is not an object")
    known = dict(JUDGEMENT)
    sections: dict[str, list[str]] = {}
    unused: dict[str, str] = {}
    notes = [f"The drafts file names a section that does not exist, {md.code(str(sid)[:40])}; "
             "it was ignored." for sid in body if sid not in known]
    for sid, label in JUDGEMENT:
        if sid not in body:
            continue
        items = body[sid]
        if not isinstance(items, list) or not items:
            reason = "the draft is not a non-empty list"
        elif len(items) > MAX_SECTION_ITEMS:
            reason = f"the draft has more than {MAX_SECTION_ITEMS} items"
        elif not all(isinstance(i, str) and i.strip() and len(i) <= MAX_ITEM_CHARS for i in items):
            reason = f"an item is not a string of 1 to {MAX_ITEM_CHARS} characters"
        else:
            sections[sid] = list(items)
            continue
        unused[sid] = reason
        notes.append(f"{label}: the draft was not used because {reason}.")
    return Drafts(sections, unused, notes, digest)


def plugin_repository() -> str | None:
    """The plugin repository's web address from its own manifest, or None when there is no
    usable one. A fork that names its own repository there links to it."""
    doc = c.load_json(c.plugin_root() / ".claude-plugin" / "plugin.json", {})
    url = doc.get("repository") if isinstance(doc, dict) else None
    return url.rstrip("/") if isinstance(url, str) and links.valid_base_url(url) else None


def guidance_line() -> str:
    """The fix instructions and the review briefs, linked by an absolute address: the ticket
    is filed in a repository that has neither, so a relative path would be a dead link."""
    base = plugin_repository()
    if base is None:
        return ("fix-agent-instructions.md and review-briefs.md in the thunderstruck "
                "repository (no link could be built)")
    fix, review = (f"{base}/blob/main/{path}" for path in GUIDANCE.values())
    return (f"How to fix: {md.linked(Path(GUIDANCE['fix']).name, fix)} · "
            f"how to review: {md.linked(Path(GUIDANCE['review']).name, review)}")


def links_reason(rep: dict) -> str | None:
    """None when links were built; otherwise the reason the report recorded, or, for the one
    silent case, the link settings turning them off."""
    if isinstance(rep.get("links"), dict):
        return None
    for warning in [*(rep.get("run_warnings") or []), *(rep.get("warnings") or [])]:
        if isinstance(warning, str) and warning.startswith(links.NOT_LINKED):
            return warning
    return links.NOT_LINKED + "disabled in the repository's link settings (enabled = false)"


def evidence_line(ev: dict, links_built: bool) -> str:
    """One evidence item: linked by the tool, or labelled with why it is not."""
    kind = ev.get("type")
    line = f"- _{md.text(kind)}_ {report._evidence_ref(ev)}"
    if ev.get("note"):
        line += f" — {md.text(ev['note'])}"
    if not ev.get("url"):
        if kind in ("catalog", "dependency"):
            why = UNLINKED[kind]
        elif not links_built:
            why = "links could not be built (see Header)"
        elif kind == "commit":
            why = UNLINKED["commit"]
        else:
            why = "no link could be built"
        line += f" (not linked: {why})"
    return line
