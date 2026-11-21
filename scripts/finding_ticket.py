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


SECTIONS_HEADINGS = ("Header", "Summary", "Trigger", "Mechanism", "Persistence", "Blast radius",
                     "Implicit guarantees at risk", "Evidence status",
                     "Assumptions and open questions", "Reproduce", "Detection", "Fix options",
                     "Acceptance criteria", "Out of scope", "Rollout and rollback", "Provenance",
                     "Disclaimer")
MAX_TITLE = 100
# A ticket is pasted into a tracker. GitHub is widely reported to limit an issue body to 65,536
# but does not document it, and whether the unit is characters or bytes is unconfirmed: verify
# against the tracker's current limit before relying on the figure. Bytes are never fewer than
# characters, so the cap is in UTF-8 bytes and holds under either reading. The margin below the
# limit is for what the cap cannot drop: every section but the mechanism steps.
TRACKER_BODY_LIMIT = 65_536
TICKET_MARGIN = 5_536
MAX_TICKET_BYTES = TRACKER_BODY_LIMIT - TICKET_MARGIN
# An account name that is the same on every machine says nothing about this one.
GENERIC_ACCOUNTS = frozenset({"root", "admin", "administrator", "user", "runner", "ubuntu", "vscode",
                              "node", "nobody", "daemon"})
# Keys whose values are references, links or ids the ticket must keep exactly.
SCRUB_SKIP = frozenset({"key", "id", "hotspot_id", "type", "ref", "file", "default_ref", "doc_ref", "sha",
                        "url", "default_url", "doc_url", "history_url", "content_hash", "evidence_hashes"})
PROPOSAL = "**Proposal, not verified** — drafted by a model from this finding. Nothing checked it."
DISCLAIMER = ("This ticket was generated by thunderstruck from a scan. The finding is a hypothesis "
              "with a way to prove it wrong, not a confirmed defect, and the code may have changed "
              "since the scan. A section marked as a proposal was drafted by a model and is not "
              "verified. Check the code before acting on it.")
REASONS = {
    "persistence": "the finding states no sustaining effect; it is given only when the code shows one",
    "mechanism": "the finding cites no code",
    "detection": "a finding records no detection signal (the log line, metric or alert that would "
                 "show the failure)",
    "draft": "no proposal was drafted for this section; a finding records none and the plugin "
             "proposes none",
}


def title(finding: dict) -> str:
    """The failure mode on one short line. #47 will give a finding a title of its own."""
    text = " ".join(str(finding.get("failure_mode") or "").split())
    if not text:
        return "(no failure mode)"
    if len(text) <= MAX_TITLE:
        return text
    head = text[:MAX_TITLE]
    if text[MAX_TITLE] != " " and " " in head:
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,;:.") + "…"


def machine_values() -> tuple[str | None, str | None, str | None]:
    """The scanning machine's home directory, login name and host name, as far as they can be read."""
    try:
        home = str(Path.home())
    except (RuntimeError, OSError):
        home = None
    try:
        user = getpass.getuser()
    except (OSError, KeyError, ImportError):
        user = None
    try:
        host = socket.gethostname()
    except OSError:
        host = None
    return home, user, host


def scrubber(roots, machine=(None, None, None)):
    """A function that removes what names the machine that ran the scan from any string, list or
    object a model or the repository wrote: the repository's path becomes <repo>, the home
    directory <home>, the login name <user>, the host name <host>. References, links and ids
    (SCRUB_SKIP) are left exactly as they are, and so is a snippet, which is the repository's own
    text. A generic account name (root) is not a machine value and is left alone."""
    home, user, host = machine
    found = sorted({r.rstrip("/\\") for r in roots if isinstance(r, str) and len(r.rstrip("/\\")) > 1},
                   key=len, reverse=True)
    home = home.rstrip("/\\") if isinstance(home, str) and len(home.rstrip("/\\")) > 1 else None
    names = []
    if isinstance(user, str) and len(user) >= 3 and user.lower() not in GENERIC_ACCOUNTS:
        names.append((user, "<user>"))
    if isinstance(host, str):
        names += [(h, "<host>") for h in dict.fromkeys([host, host.split(".")[0]])
                  if len(h) >= 4 and h.lower() != "localhost"]
    words = [(re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])"), shown) for name, shown in names]

    def text(value: str) -> str:
        for root in found:
            value = value.replace(root, "<repo>")
        if home:
            value = value.replace(home, "<home>")
        for pattern, shown in words:
            value = pattern.sub(shown, value)
        return value

    def scrub(value, key=None):
        if key in SCRUB_SKIP:
            return value
        if isinstance(value, str):
            return text(value)
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            return {k: scrub(item, k) for k, item in value.items()}
        return value
    return scrub


def _not_assessed(reason: str) -> str:
    return f"Not assessed: {reason}."


def _placeholders(text: str) -> int:
    """The sections that read "Not assessed": lines that begin with it outside a code fence, so
    a quoted line of code or a sentence of model text that says it is not counted."""
    count, fence = 0, None
    for line in text.split("\n"):
        run = re.match(r"`{3,}", line)
        if run and (fence is None or (len(run.group(0)) >= fence and not line.strip("`"))):
            fence = None if fence is not None else len(run.group(0))
        elif fence is None and line.startswith("Not assessed: "):
            count += 1
    return count


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def render(rep: dict, f: dict, steps: list[Step], omitted: int, drafts: Drafts, status: str,
           scrub, dropped: int = 0) -> str:
    """The ticket as Markdown. `f` is a normalised, scrubbed finding with safe links. `dropped`
    is how many steps the caller left out so that the ticket fits MAX_TICKET_BYTES."""
    built = links_reason(rep) is None
    loc = f.get("location") if isinstance(f.get("location"), dict) else {}
    where = f"{loc.get('file', '?')}" + (f":{loc['lines']}" if loc.get("lines") else "")
    claimed = f.get("confidence_claimed")
    stamp = rep.get("scanned_at")
    date = str(stamp)[:10] if isinstance(stamp, str) and re.match(r"\d{4}-\d{2}-\d{2}", stamp) else "not recorded"
    reason = links_reason(rep)
    L = [f"# {md.text(title(f), heading=True)}", "", "## Header", "",
         f"- **Location** — {md.linked(where, loc.get('url'))}"
         + (f" · {md.code(loc['symbol'])}" if loc.get("symbol") else ""),
         f"- **Confidence** — {md.text(f.get('confidence'))}"
         + (f" (claimed {claimed})" if claimed in c.CONFIDENCE_LEVELS and claimed != f.get("confidence") else ""),
         f"- **Check status** — {f['check']['status']}",
         f"- **Status** — {status}",
         f"- **Key** — {md.code(f.get('key'))}",
         f"- **Scan date** — {date}",
         "- **Links** — " + ("built from the repository's link settings; they open the cited lines at "
                             "the scanned commit." if built
                             else f"Not built. The report records: {md.text(scrub(reason))}"),
         "", "## Summary", "", f"**Failure mode** — {md.text(f.get('failure_mode'))}", ""]
    if f.get("prediction"):
        L += [f"**Prediction** — {md.text(f['prediction'])}", ""]
    L += ["## Trigger", "", f"**Trigger** — {md.text(f.get('trigger_condition'))}", ""]
    if f.get("gate") in c.GATE_MARKERS:
        L += [f"This failure {c.GATE_MARKERS[f['gate']]}.", ""]
    L += report.render_preconditions(f)
    L += ["## Mechanism", "",
          f"**Amplifier** — {md.text(f['amplifier'])}" if f.get("amplifier") else "**Amplifier** — not stated.",
          ""]
    if steps:
        for n, step in enumerate(steps, 1):
            L += render_step(n, step)
    else:
        L += [_not_assessed(REASONS["mechanism"]), ""]
    if omitted:
        L += [f"{omitted} further code {_plural(omitted, 'reference is', 'references are')} "
              "listed under Evidence status.", ""]
    if dropped:
        L += [f"{dropped} further {_plural(dropped, 'step is', 'steps are')} left out so that the ticket "
              f"fits a tracker (at most {MAX_TICKET_BYTES:,} bytes); the code "
              f"{_plural(dropped, 'reference is', 'references are')} listed under Evidence status.", ""]
    L += ["## Persistence", "",
          f"**Sustaining effect** — {md.text(f['sustaining_effect'])}" if f.get("sustaining_effect")
          else _not_assessed(REASONS["persistence"]), ""]
    L += ["## Blast radius", "", f"**Summary** — {md.text(f.get('blast_radius'))}", "",
          *report.render_impact(f)]
    L += ["## Implicit guarantees at risk", "", *report.render_guarantees(f)]
    evidence = [e for e in f.get("evidence") or [] if isinstance(e, dict)]
    cited = [e for e in f["check"].get("evidence") or [] if isinstance(e, dict)]
    L += ["## Evidence status", "", *report.render_check(f), "**Evidence**", "",
          *([evidence_line(e, built) for e in evidence] or ["none"]), ""]
    if cited:
        L += ["**Cited by the check**", "", *[evidence_line(e, built) for e in cited], ""]
    L += report.render_history(f)
    L += ["## Assumptions and open questions", "", *report.render_not_checked(f),
          f"**Why this confidence** — {md.text(f.get('confidence_rationale'))}", ""]
    L += ["## Reproduce", "", f"**Verify** — {md.text(f.get('how_to_verify'))}", "",
          "No reproduction is recorded for this finding.", ""]
    L += ["## Detection", "", _not_assessed(REASONS["detection"]), ""]
    for sid, label in JUDGEMENT:
        L += [f"## {label}", ""]
        if sid in drafts.sections:
            L += [PROPOSAL, "", *[f"- {md.text(scrub(item))}" for item in drafts.sections[sid]], ""]
        elif sid in drafts.unused:
            L += [_not_assessed(f"the draft for this section was not used: {drafts.unused[sid]}"), ""]
        else:
            L += [_not_assessed(REASONS["draft"]), ""]
        if sid in ("fix_options", "acceptance_criteria"):
            L += [guidance_line(), ""]
    proposals = [label for sid, label in JUDGEMENT if sid in drafts.sections]
    verification = rep.get("verification") if isinstance(rep.get("verification"), dict) else {}
    L += ["## Provenance", "",
          f"- Generated by thunderstruck from a scan of commit {md.code(rep['repo']['head'])}"
          + (f" at {md.code(stamp)}" if isinstance(stamp, str) else "") + ".",
          f"- Finding {md.code(f.get('key'))} · hotspot {md.text(f.get('hotspot_id'))} · "
          f"report schema {md.code(rep.get('schema'))}.",
          f"- Verification {'ran' if verification.get('ran') else 'did not run'} for this scan.",
          (f"- Proposals: {', '.join(proposals)} drafted by a model from this finding "
           f"(file {md.code(drafts.digest)})." if proposals else "- Proposals: none drafted."),
          *[f"- {note}" for note in drafts.notes], "",
          "## Disclaimer", "", DISCLAIMER]
    return "\n".join(L) + "\n"


def fit_ticket(rep: dict, f: dict, steps: list[Step], omitted: int, drafts: Drafts, status: str,
               scrub) -> str:
    """The ticket, with mechanism steps dropped from the end until it fits MAX_TICKET_BYTES (UTF-8
    bytes), and the note that says so. A ticket that does not fit even without steps is a stop,
    not a cut."""
    kept = len(steps)
    while True:
        text = render(rep, f, steps[:kept], omitted, drafts, status, scrub, dropped=len(steps) - kept)
        size = len(text.encode("utf-8"))
        if size <= MAX_TICKET_BYTES:
            return text
        if kept == 0:
            raise stop(f"no ticket was written for finding {f.get('key')}: it is {size:,} bytes "
                       f"even without a code step, more than the {MAX_TICKET_BYTES:,} bytes a tracker takes. "
                       "A field of the finding is too long.")
        kept -= 1


def write_ticket(repo: Path, key: str, text: str) -> Path:
    """Replace `.thunderstruck/tickets/<key>.md` atomically. Nothing is written outside the
    repository's own output folder: a link in the way is refused, not followed."""
    out = c.out_dir(repo)
    tickets = out / TICKETS_DIRNAME
    if out.is_symlink() or tickets.is_symlink():
        raise stop("`.thunderstruck` or `.thunderstruck/tickets` is a symbolic link; thunderstruck "
                   "writes only inside the repository's own output folder.")
    tickets.mkdir(parents=True, exist_ok=True)
    dest = tickets / f"{key}.md"
    # a fresh name, created exclusively and without following a link: a link planted at a
    # name this run could guess is refused, never written through
    tmp = tickets / f".{key}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o666)
    except OSError:
        raise stop("could not create a temporary file in .thunderstruck/tickets, so nothing was written.") from None
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        os.replace(tmp, dest)      # replaces a link at `dest`, never follows it
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="finding_ticket.py",
                                 description="write a ticket for one finding of the last scan")
    ap.add_argument("--repo", default=None)
    pick = ap.add_mutually_exclusive_group(required=True)
    pick.add_argument("--key", help="the finding's stable key (12 hex characters)")
    pick.add_argument("--list", action="store_true", help="list the findings and their keys")
    ap.add_argument("--status", type=parse_status, default="Hypothesis",
                    help=f"one of {', '.join(STATUSES)} (default Hypothesis)")
    args = ap.parse_args(argv)
    try:
        repo = c.find_repo_root(args.repo)
        rep = load_report(repo)
        if args.list:
            print("\n".join(list_findings(rep)) or "this scan reported no findings")
            return 0
        scrub = scrubber([(rep.get("repo") or {}).get("root") if isinstance(rep.get("repo"), dict) else None,
                          str(repo)], machine_values())
        finding = clean_urls(scrub(find_finding(rep, args.key)))
        require_status(args.status, finding)
        check_snapshot(repo, rep, finding)
        steps, omitted = code_steps(repo, rep["repo"]["head"], finding)
        drafts = load_sections(sections_path(repo, finding["key"]), finding["key"], rep.get("scanned_at"))
        text = fit_ticket(rep, finding, steps, omitted, drafts, args.status, scrub)
        dest = write_ticket(repo, finding["key"], text)
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2
    except subprocess.TimeoutExpired:
        c.die(f"git did not answer within {GIT_TIMEOUT}s.")
        return 2
    except OSError as exc:
        c.die(f"could not read or write under {c.OUTPUT_DIRNAME}/: {exc.strerror or type(exc).__name__}.")
        return 2
    count = _placeholders(text)
    print(f"ticket for {finding['key']}: {c.OUTPUT_DIRNAME}/{TICKETS_DIRNAME}/{dest.name} "
          f"({count} {_plural(count, 'section', 'sections')} not assessed, "
          f"{len(drafts.sections)} drafted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
