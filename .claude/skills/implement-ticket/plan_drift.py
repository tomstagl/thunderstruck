#!/usr/bin/env python3
"""What changed on main since a ticket's spec and plan were last agreed (#79).

The spec and plan are written against the code as it was. This lists the
commits that landed afterwards on files they name, so the agent reads those
diffs before building instead of meeting the conflict at Task 7. It narrows;
it never decides whether a commit contradicts the plan.

    python3 plan_drift.py --plan docs/…/plan.md --spec docs/…/spec-design.md --ref origin/main

Exit 0 with JSON on stdout. Exit 2 when the ref, the plan or the spec is
unusable. Stdlib only; it never touches the network.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

CAP = 30
EXTENSIONS = (".py", ".md", ".yaml", ".yml", ".json", ".html", ".toml", ".txt", ".sh", ".cfg")
# Any word of the text may be a path: in a sentence, a code span, a command or
# a fenced block. Words that are not files in the tree are dropped later.
WORD_RE = re.compile(r"[^\s`'\"(),;<>\[\]{}|*?]+")
# `tests/x.py::test_y` and `scripts/x.py:123-145` name the file.
SUFFIX_RE = re.compile(r"(::.*|:\d+(?:-\d+)?)$")


class BadInput(Exception):
    pass


def git(*args: str) -> str:
    proc = subprocess.run(["git", "--literal-pathspecs", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise BadInput(proc.stderr.strip() or f"git {args[0]} failed")
    return proc.stdout


def tree(ref: str) -> set[str]:
    return set(git("ls-tree", "-r", "--name-only", "-z", ref).split("\0")) - {""}


def named_tokens(text: str) -> set[str]:
    found = set()
    for word in WORD_RE.findall(text):
        word = SUFFIX_RE.sub("", word.rstrip(".:"))
        word = word[2:] if word.startswith("./") else word
        if word and "://" not in word and ("/" in word or word.endswith(EXTENSIONS)):
            found.add(word)
    return found


def base_commit(ref: str, plan: str, spec: str) -> str:
    sha = git("log", "-1", "--format=%H", ref, "--", plan, spec).strip()
    if not sha:
        raise BadInput(f"neither {plan} nor {spec} is on {ref}")
    return sha


def renames(base: str, ref: str) -> dict[str, str]:
    parts = git("diff", "--name-status", "-M", "-z", base, ref).split("\0")
    moved, i = {}, 0
    while i < len(parts) and parts[i]:
        code = parts[i]
        if code[0] in "RC":
            if code[0] == "R":
                moved[parts[i + 1]] = parts[i + 2]
            i += 3
        else:
            i += 2
    return moved


def drift(plan: str, spec: str, ref: str) -> dict:
    # A shallow clone makes the last commit on the plan the clone's boundary,
    # which reports no drift at all. Refusing is honest; guessing is not.
    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        raise BadInput("shallow clone: history is incomplete (git fetch --unshallow)")
    for path in (plan, spec):
        git("cat-file", "-e", f"{ref}:{path}")  # BadInput when absent
    base = base_commit(ref, plan, spec)
    before, after = tree(base), tree(ref)
    text = git("show", f"{ref}:{plan}") + "\n" + git("show", f"{ref}:{spec}")
    named = named_tokens(text) & (before | after)

    drifted = []
    if named:
        log = git("log", "--no-merges", "--no-renames", "--name-only",
                  "--format=%x01%H%x00%s", f"{base}..{ref}", "--", *sorted(named))
        for block in log.split("\x01")[1:]:
            head, _, files = block.partition("\n")
            sha, _, subject = head.partition("\x00")
            touched = sorted(set(files.split("\n")) & named)
            if touched:
                drifted.append({"sha": sha, "subject": subject, "paths": touched})

    moved = renames(base, ref)
    gone = []
    for path in sorted((named & before) - after):
        entry = {"path": path, "change": "renamed" if path in moved else "deleted"}
        if path in moved:
            entry["to"] = moved[path]
        gone.append(entry)

    return {"base": base, "named": len(named), "drifted": drifted[:CAP], "gone": gone,
            "truncated": len(drifted) > CAP}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--ref", default="origin/main")
    args = ap.parse_args(argv)
    try:
        result = drift(args.plan, args.spec, args.ref)
    except BadInput as exc:
        print(f"plan_drift: {exc}", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
