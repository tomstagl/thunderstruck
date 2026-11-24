#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Record the outcome of a reproduction of one finding (#103).

    uv run scripts/reproduction.py record --key K --status S --test PATH --command CMD [--repo R]
    uv run scripts/reproduction.py show --key K [--repo R]

`/thunderstruck-verify` calls `record` after the user's own test run, with the
outcome that run gave. This script cannot know the test failed: it records what
the verify session says happened, with the test file's hash, the repository's
HEAD and the finding's `content_hash`, so the report can tell when the record no
longer applies. It runs, imports and builds nothing of the repository, and the
command is stored as text and never executed.

One record per finding key, in `.thunderstruck/reproductions/<key>.json`, a
directory no scan replaces. A record is read for display only: it never changes
a rank, a confidence, a check status, a gate, a bundle or a brief.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402

SCHEMA = "thunderstruck.reproduction/v1"
DIRNAME = "reproductions"
STATUSES = ("fails_as_predicted", "passes", "blocked")
MAX_COMMAND = 300
# A key names a file: the finding keys are hex, and nothing else is looked up.
_KEY = re.compile(r"[A-Za-z0-9_-]{1,128}")


def records_dir(repo: Path) -> Path:
    return c.out_dir(repo) / DIRNAME


def _finding(repo: Path, key: str) -> dict[str, Any]:
    report = c.load_json(c.out_dir(repo) / "report.json")
    if not isinstance(report, dict) or not isinstance(report.get("findings"), list):
        raise c.ThunderstruckError("no readable report.json — run a scan first.")
    for f in report["findings"]:
        if isinstance(f, dict) and f.get("key") == key:
            return f
    raise c.ThunderstruckError(f"{key!r} is not a finding in the current report.json; "
                               "refer to a finding by its key.")


def _test_path(repo: Path, test: str) -> str:
    rel = c.ref_path(test)
    problem = c.path_problem(rel) or c.tracked_file_problem(repo, rel, "100644")
    if problem:
        raise c.ThunderstruckError(f"test path {test!r} {problem}.")
    return rel


def record(repo: Path, key: str, status: str, test: str, command: str,
           now: datetime | None = None) -> dict[str, Any]:
    """Check the arguments, then write and return the record. Raises
    ThunderstruckError, writing nothing, on any refusal."""
    if status not in STATUSES:
        raise c.ThunderstruckError(f"status {status!r} is not one of {', '.join(STATUSES)}.")
    if not isinstance(command, str) or not command.strip():
        raise c.ThunderstruckError("the command the user ran is required.")
    if len(command) > MAX_COMMAND:
        raise c.ThunderstruckError(f"the command is {len(command)} characters; at most "
                                   f"{MAX_COMMAND} are stored.")
    if not _KEY.fullmatch(key or ""):
        raise c.ThunderstruckError(f"{key!r} is not a finding in the current report.json.")
    finding = _finding(repo, key)
    rel = _test_path(repo, test)
    rec = {"schema": SCHEMA, "key": key, "status": status,
           "test": {"path": rel, "sha256": c.sha256_file(repo / rel)},
           "command": command,
           "head": c.git(repo, "rev-parse", "HEAD").strip(),
           "finding_hash": finding.get("content_hash"),
           "recorded_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
    dest = records_dir(repo) / f"{key}.json"
    try:
        c.write_json(dest, rec)
    except OSError as exc:
        raise c.ThunderstruckError(f"cannot write {dest}: {exc.strerror or exc}") from None
    return rec


def show(repo: Path, key: str) -> dict[str, Any]:
    if not _KEY.fullmatch(key or ""):
        raise c.ThunderstruckError(f"no reproduction recorded for {key!r}.")
    path = records_dir(repo) / f"{key}.json"
    if not path.is_file():
        raise c.ThunderstruckError(f"no reproduction recorded for {key!r}.")
    rec = c.load_json(path)
    if not isinstance(rec, dict):
        raise c.ThunderstruckError(f"the reproduction recorded for {key!r} is unreadable.")
    return rec


def _unreadable() -> dict[str, Any]:
    return {"status": None, "state": "unreadable", "test_path": None, "command": None,
            "recorded_head": None, "stale_because": []}


def _readable(rec: Any, key: str) -> bool:
    test = rec.get("test") if isinstance(rec, dict) else None
    return (isinstance(rec, dict) and rec.get("schema") == SCHEMA and rec.get("key") == key
            and rec.get("status") in STATUSES and isinstance(test, dict)
            and isinstance(test.get("path"), str) and isinstance(test.get("sha256"), str)
            and isinstance(rec.get("command"), str))


def state(repo: Path, rec: dict[str, Any], finding: dict[str, Any]) -> tuple[str, list[str]]:
    """`current` when the test file and the finding are what the record saw,
    else `stale` with what changed (spec §2.2). Reads the test file's bytes to
    hash them, and nothing else of the repository."""
    because = []
    rel = rec["test"]["path"]
    if c.path_problem(rel) or c.tracked_file_problem(repo, rel, "100644"):
        because.append("the test file is gone")
    elif c.sha256_file(repo / rel) != rec["test"]["sha256"]:
        because.append("the test file changed")
    if rec.get("finding_hash") != finding.get("content_hash"):
        because.append("the finding changed")
    return ("stale" if because else "current"), because


def summaries(repo: Path, findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{key: summary} for each finding with a record. A record whose key is in
    no finding is neither shown nor deleted; a malformed one is `unreadable`."""
    base = records_dir(repo)
    if not base.is_dir():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for f in findings:
        key = f.get("key") if isinstance(f, dict) else None
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            continue
        path = base / f"{key}.json"
        if not path.is_file():
            continue
        rec = c.load_json(path)
        if not _readable(rec, key):
            out[key] = _unreadable()
            continue
        st, because = state(repo, rec, f)
        out[key] = {"status": rec["status"], "state": st, "test_path": rec["test"]["path"],
                    "command": rec["command"], "recorded_head": rec.get("head"),
                    "stale_because": because}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="reproduction.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="record the outcome of a reproduction")
    rec.add_argument("--repo", default=None)
    rec.add_argument("--key", required=True)
    rec.add_argument("--status", required=True)
    rec.add_argument("--test", required=True, help="the test file, relative to the repository")
    rec.add_argument("--command", required=True, help="the command the user ran (stored, never run)")
    sh = sub.add_parser("show", help="print the record for a key")
    sh.add_argument("--repo", default=None)
    sh.add_argument("--key", required=True)
    args = ap.parse_args(argv)
    try:
        repo = c.find_repo_root(args.repo)
        if args.cmd == "record":
            out = record(repo, args.key, args.status, args.test, args.command)
        else:
            out = show(repo, args.key)
    except c.ThunderstruckError as exc:
        print(f"thunderstruck: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
