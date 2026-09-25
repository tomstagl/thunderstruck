#!/usr/bin/env python3
"""Pick the one ticket the nightly agent builds, or none, and say why (#39).

The model gathers issues, writers and open PRs through the GitHub tools and
writes them to candidates.json; this script decides. Readiness is a rule, so
it is decided here and never by a model (spec §2).

    python3 pick_ticket.py candidates.json --ref origin/main --now 2026-09-26T01:52:00Z

Exit 0 with JSON on stdout, whether or not a ticket was picked. Exit 2 when
the input or the ref is unusable. Stdlib only; it never touches the network.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

CLAIM = "agent:in-progress"
BLOCKED = "agent:blocked"
STALE_AFTER = timedelta(hours=24)

# A placeholder such as YYYY-MM-DD-topic-design.md never matches, so a ticket
# whose spec is "to be written" reports that it has no spec path.
_EDGE = r"(?<![\w.-])"  # a "/" may precede: a blob URL names the same path
SPEC_RE = re.compile(_EDGE + r"docs/superpowers/specs/\d{4}-\d{2}-\d{2}-[a-z0-9-]+-design\.md")
PLAN_RE = re.compile(_EDGE + r"docs/superpowers/plans/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md")


class BadInput(Exception):
    pass


def mentions(text: str, number: int) -> bool:
    """`#39` as a whole token: not `#390`, not `x#39`."""
    return re.search(rf"(?<![\w#/])#{number}(?!\w)", text or "") is not None


def _parse_time(value: str) -> datetime:
    """ISO 8601; a timestamp without a zone is read as UTC."""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class Ref:
    def __init__(self, ref: str):
        self.ref = ref
        proc = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise BadInput(f"unknown ref: {ref}")

    def read(self, path: str) -> str | None:
        # An object name, not a pathspec, so glob characters are literal.
        proc = subprocess.run(["git", "cat-file", "blob", f"{self.ref}:{path}"],
                              capture_output=True)
        if proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", "replace")


def _one_path(pattern: re.Pattern, body: str, kind: str) -> tuple[str | None, str | None]:
    found = sorted(set(pattern.findall(body or "")))
    if not found:
        return None, f"no {kind} path in ticket"
    if len(found) > 1:
        return None, f"more than one {kind} path in ticket"
    return found[0], None


def skip_reason(issue: dict, writers: set[str], prs: list[dict], ref: Ref,
                now: datetime) -> tuple[str | None, dict]:
    """The first rule the ticket fails (spec §2, rules 3–12), or None."""
    n = issue["number"]
    author = str(issue.get("author") or "")
    if author.casefold() not in writers:
        return f"author {author} has no write access", {}

    body = issue.get("body") or ""
    spec, why = _one_path(SPEC_RE, body, "spec")
    if why:
        return why, {}
    plan, why = _one_path(PLAN_RE, body, "plan")
    if why:
        return why, {}

    spec_text = ref.read(spec)
    if spec_text is None:
        return f"spec not on {ref.ref}: {spec}", {}
    plan_text = ref.read(plan)
    if plan_text is None:
        return f"plan not on {ref.ref}: {plan}", {}
    if not mentions(spec_text, n):
        return f"spec does not reference #{n}", {}
    if not mentions(plan_text, n):
        return f"plan does not reference #{n}", {}

    labels = {str(label).casefold() for label in issue.get("labels") or []}
    if CLAIM in labels:
        claimed_at = issue.get("claimed_at")
        if claimed_at and now - _parse_time(claimed_at) > STALE_AFTER:
            return f"stale claim since {claimed_at}", {}
        return "already claimed", {}
    if BLOCKED in labels:
        return "blocked, see ticket comments", {}

    for pr in prs:
        if mentions(pr.get("title") or "", n) or mentions(pr.get("body") or "", n):
            return f"open PR #{pr['number']} references it", {}

    return None, {"spec": spec, "plan": plan}


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise BadInput(f"cannot read {path}: {exc}") from None
    if not isinstance(data, dict):
        raise BadInput("candidates must be a JSON object")
    # A missing list would silently pass a rule (no PRs → nothing references
    # the ticket), so every list is required.
    for key in ("issues", "writers", "open_prs"):
        if not isinstance(data.get(key), list):
            raise BadInput(f"candidates.{key} must be a list")
    for item in data["issues"]:
        if not isinstance(item, dict) or not isinstance(item.get("number"), int) \
                or not isinstance(item.get("title"), str):
            raise BadInput("every issue needs an integer number and a string title")
    for item in data["open_prs"]:
        if not isinstance(item, dict) or not isinstance(item.get("number"), int):
            raise BadInput("every open PR needs an integer number")
    return data


def pick(data: dict, ref: Ref, now: datetime) -> dict:
    writers = {str(w).casefold() for w in data["writers"]}
    picked, skipped, drafts = None, [], []
    for issue in sorted(data["issues"], key=lambda i: i["number"]):
        if str(issue.get("state", "open")).lower() != "open":
            continue
        if "draft" in issue["title"].casefold():
            drafts.append(issue["number"])
            continue
        if picked is not None:
            continue  # not skipped, just not first (AC-2)
        why, paths = skip_reason(issue, writers, data["open_prs"], ref, now)
        if why:
            skipped.append({"number": issue["number"], "reason": why})
        else:
            picked = {"number": issue["number"], "title": issue["title"], **paths}
    return {"picked": picked, "skipped": skipped, "ignored_drafts": drafts}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("candidates")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--now", required=True, help="ISO timestamp; never read from the clock")
    args = ap.parse_args(argv)
    try:
        now = _parse_time(args.now)
        data = _load(args.candidates)
        result = pick(data, Ref(args.ref), now)
    except (BadInput, ValueError) as exc:
        print(f"pick_ticket: {exc}", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
