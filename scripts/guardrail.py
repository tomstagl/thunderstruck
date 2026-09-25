#!/usr/bin/env python3
"""PreToolUse guardrail: surface open findings for a file about to be edited.

Contract, in order of importance:

1. **It never blocks.** Exit code is always 0. Any error at all is a silent
   no-op — a forensic tool that stops you editing your own code is worse than
   no forensic tool.
2. **It is fast.** Pure file lookup: no LLM, no git, no yaml. Stdlib only, so
   it runs on bare python3 without uv resolving anything. Budget < 100ms.
3. **It is quiet.** Once per file per session, medium/high confidence only,
   and nothing at all for a file with no findings.

PreToolUse (not PostToolUse) because the current hooks reference documents
`hookSpecificOutput.additionalContext` for it, so the warning arrives *before*
the edit rather than after.

The text is phrased as statements of fact. Claude Code's own documentation
warns that imperative, system-command-shaped context trips prompt-injection
defences and gets surfaced to the user instead of used.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

MAX_PARENTS = 8
MIN_CONFIDENCE = ("medium", "high")
MAX_FINDINGS_SHOWN = 3
OUTPUT_DIRNAME = ".thunderstruck"
MAX_NEIGHBOURS_SHOWN = 5
EDGE_PHRASES = (("inbound", "Cited dependents of this component"),
                ("outbound", "Cited dependencies of this component"))


def _project_dir(hook_input: dict) -> Path | None:
    for candidate in (os.environ.get("CLAUDE_PROJECT_DIR"), hook_input.get("cwd"), os.getcwd()):
        if not candidate:
            continue
        here = Path(candidate)
        for _ in range(MAX_PARENTS):
            if (here / OUTPUT_DIRNAME / "index.json").is_file():
                return here
            if here.parent == here:
                break
            here = here.parent
    return None


def _relative(path: str, root: Path) -> str | None:
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        return None


def _seen_store(hook_input: dict, session_id: str) -> Path:
    base = hook_input.get("scratchpad_dir") or tempfile.gettempdir()
    safe = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in "-_")[:64]
    return Path(base) / f"thunderstruck-guard-{safe or 'nosession'}.txt"


def _already_warned(store: Path, rel: str) -> bool:
    try:
        return rel in store.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False


def _mark_warned(store: Path, rel: str) -> None:
    try:
        store.parent.mkdir(parents=True, exist_ok=True)
        with store.open("a", encoding="utf-8") as fh:
            fh.write(rel + "\n")
    except OSError:
        pass  # a store we cannot write just means we may warn twice


def _current_hash(path: Path) -> str | None:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _neighbour_lines(findings: list[dict]) -> list[str]:
    lines = []
    for direction, phrase in EDGE_PHRASES:
        names: dict[str, str] = {}
        for f in findings:
            evidence = f.get("catalog_evidence")
            for ev in evidence if isinstance(evidence, list) else []:
                if not isinstance(ev, dict) or ev.get("direction") != direction:
                    continue
                ref = ev.get("neighbour")
                if not isinstance(ref, str) or not ref or ref in names:
                    continue
                attrs = ev.get("attributes") if isinstance(ev.get("attributes"), dict) else {}
                detail = "; ".join(f"{k}: {v}" for k, v in sorted(attrs.items()))
                label = ref.rsplit("/", 1)[-1]
                names[ref] = f"{label} ({detail})" if detail else label
        if names:
            shown = list(names.values())
            text = ", ".join(shown[:MAX_NEIGHBOURS_SHOWN])
            if len(shown) > MAX_NEIGHBOURS_SHOWN:
                text += f" and {len(shown) - MAX_NEIGHBOURS_SHOWN} more"
            lines.append(f"{phrase}: {text}.")
    return lines


def build_context(entry: dict, rel: str, stale: bool) -> str | None:
    findings = [f for f in entry.get("findings", [])
                if f.get("confidence") in MIN_CONFIDENCE]
    if not findings:
        return None
    order = {"high": 0, "medium": 1}
    findings.sort(key=lambda f: order.get(f.get("confidence"), 9))
    shown, extra = findings[:MAX_FINDINGS_SHOWN], len(findings) - MAX_FINDINGS_SHOWN

    lines = [f"thunderstruck has {len(findings)} open finding(s) on {rel}."]
    if stale:
        lines.append(
            "This file has changed since the scan that produced them, so the "
            "line numbers and the findings themselves may be out of date.")
    lines.append("")
    for f in shown:
        pats = ", ".join(f.get("missing_patterns") or []) or "—"
        where = f" (lines {f['lines']})" if f.get("lines") else ""
        if f.get("via") == "evidence":
            where = f" (cited as evidence; finding is on {f.get('anchor', '?')})"
        lines.append(f"- {f.get('id', '?')}{where}: {f.get('failure_mode', '')}")
        lines.append(f"  missing patterns: {pats}; confidence: {f.get('confidence')}")
        if f.get("sustaining_effect"):
            lines.append(f"  what keeps it failing: {f['sustaining_effect']}")
    if extra > 0:
        lines.append(f"- and {extra} more, in .thunderstruck/report.md")
    neighbours = _neighbour_lines(findings)
    if neighbours:
        lines.append("")
        lines += neighbours
    lines.append("")
    lines.append("The full report is at .thunderstruck/report.md. These are "
                 "hypotheses from a past scan, not verified defects.")
    return "\n".join(lines)


def run(hook_input: dict) -> dict | None:
    tool_input = hook_input.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path")
    if not path:
        return None

    root = _project_dir(hook_input)
    if root is None:
        return None

    index = json.loads((root / OUTPUT_DIRNAME / "index.json").read_text(encoding="utf-8"))
    files = index.get("files") or {}
    if not files:
        return None

    rel = _relative(path, root)
    entry = files.get(rel) if rel else None
    if entry is None:
        return None

    session_id = hook_input.get("session_id") or ""
    store = _seen_store(hook_input, session_id)
    if _already_warned(store, rel):
        return None

    recorded = entry.get("content_hash")
    stale = bool(recorded and _current_hash(root / rel) not in (None, recorded))

    context = build_context(entry, rel, stale)
    if context is None:
        return None

    _mark_warned(store, rel)
    return {"hookSpecificOutput": {
        "hookEventName": hook_input.get("hook_event_name") or "PreToolUse",
        "additionalContext": context,
    }}


def main() -> int:
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
        result = run(hook_input)
        if result:
            print(json.dumps(result))
    except Exception:
        # Fail open, and stay silent while doing it. If THUNDERSTRUCK_DEBUG is
        # set the reason goes to stderr, which exit 0 still keeps non-blocking.
        if os.environ.get("THUNDERSTRUCK_DEBUG"):
            import traceback
            traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
