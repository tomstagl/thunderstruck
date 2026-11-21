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
