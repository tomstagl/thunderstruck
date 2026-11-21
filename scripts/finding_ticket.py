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
