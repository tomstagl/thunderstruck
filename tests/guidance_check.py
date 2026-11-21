"""Checks for the fix instructions and the review briefs (#107).

Both documents are the maintainer's and are shipped verbatim: nothing here
edits them. This module reads them and answers three questions: do they stay
free of harness names, plugin paths and plugin script names (neutrality); do
they still state the behaviours the ticket requires (quotes); do their links
resolve. Design: docs/superpowers/specs/2026-11-12-fix-and-review-guidance-design.md.

Test data is in tests/guidance/. Not a test module: pytest does not collect it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "guidance"

# The published paths, relative to the plugin root (spec §2). Tickets that are
# already filed and the README link them: do not move one.
PUBLISHED = {
    "fix": "docs/fix-agent-instructions.md",
    "review": "docs/review-briefs.md",
}

# --- Markdown blocks ----------------------------------------------------------


@dataclass(frozen=True)
class Block:
    kind: str    # heading | paragraph | item | row | code
    line: int    # 1-based line where the block starts
    text: str    # lines joined by one space, whitespace collapsed; a list item loses its marker
    level: int = 0  # headings: the number of '#'
    end: int = 0    # 1-based last line of the block


_FENCE = re.compile(r"^ {0,3}(?:```|~~~)")
_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])\s+")
_ROW = re.compile(r"^\s*\|")
_QUOTE = re.compile(r"^\s*>\s?")


def _flat(text: str) -> str:
    return " ".join(text.split())


def blocks(text: str) -> list[Block]:
    """Split Markdown into headings, paragraphs, list items, table rows and
    code lines. A wrapped line joins its block, so a phrase broken across two
    lines is one string, and a list item's marker is dropped. Fenced code is
    one block per non-empty line."""
    out: list[Block] = []
    cur: list | None = None
    fenced = False

    def flush() -> None:
        nonlocal cur
        if cur:
            out.append(Block(cur[0], cur[1], _flat(" ".join(cur[2])), 0, cur[3]))
        cur = None

    for n, raw in enumerate(text.splitlines(), 1):
        if _FENCE.match(raw):
            flush()
            fenced = not fenced
            continue
        if fenced:
            if raw.strip():
                out.append(Block("code", n, _flat(raw), 0, n))
            continue
        line = _QUOTE.sub("", raw)
        if not line.strip():
            flush()
            continue
        m = _HEADING.match(line)
        if m:
            flush()
            out.append(Block("heading", n, _flat(m.group(2)), len(m.group(1)), n))
        elif _ROW.match(line):
            flush()
            out.append(Block("row", n, _flat(line.strip().strip("|")), 0, n))
        elif _ITEM.match(line):
            flush()
            cur = ["item", n, [_ITEM.sub("", line, count=1)], n]
        elif cur is None:
            cur = ["paragraph", n, [line], n]
        else:
            cur[2].append(line)
            cur[3] = n
    flush()
    return out


def has_front_matter(text: str) -> bool:
    """A leading YAML block makes a file a skill or agent definition, not a
    plain document."""
    lines = text.lstrip("\ufeff").splitlines()
    return bool(lines) and lines[0].strip() == "---" and any(
        ln.strip() in ("---", "...") for ln in lines[1:60])


# --- Neutrality (spec §3) -----------------------------------------------------

PLUGIN_DIRS = ("scripts", "catalog", "hooks", "templates", "examples",
               "agents", "skills", "planes", ".claude", ".claude-plugin")


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    regex: re.Pattern
    why: str
    positive: tuple[str, ...]
    negative: tuple[str, ...]


@dataclass(frozen=True)
class Hit:
    line: int
    rule: str
    name: str
    excerpt: str


def _alt(names) -> str:
    return "|".join(re.escape(n) for n in sorted(set(names), key=lambda n: (-len(n), n)))


def plugin_components(root: Path = ROOT) -> list[str]:
    """The names of the skills and agents the plugin ships, read from its tree."""
    names: set[str] = set()
    for base in (root / "skills", root / ".claude" / "skills"):
        if base.is_dir():
            names.update(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("_"))
    if (root / "agents").is_dir():
        names.update(p.stem for p in (root / "agents").glob("*.md"))
    return sorted(names)


def plugin_files(root: Path, skip) -> list[str]:
    """File names under the plugin's own directories, except the generic ones."""
    names: set[str] = set()
    for top in PLUGIN_DIRS:
        base = root / top
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if (p.is_file() and "__pycache__" not in p.parts
                    and p.suffix != ".pyc" and p.name not in skip):
                names.add(p.name)
    return sorted(names)


def _data() -> dict:
    return yaml.safe_load((DATA / "neutrality.yaml").read_text(encoding="utf-8"))


def load_legitimate() -> list[str]:
    return list(_data()["legitimate"])


def load_bare_ok() -> set[str]:
    """Plugin file names that are also ordinary names, allowed alone in a code
    span but still forbidden after a plugin directory (`scripts/validate.py`)."""
    return set(_data()["bare_ok"])


def load_rules(root: Path = ROOT) -> list[Rule]:
    data = _data()
    rules = [Rule(r["id"], r["name"], re.compile(r["pattern"]), r["why"],
                  tuple(r["positive"]), tuple(r["negative"])) for r in data["rules"]]

    components = plugin_components(root)
    files = plugin_files(root, set(data["generic_files"]))
    alone = [n for n in files if n not in set(data["bare_ok"])]
    scripts = sorted(p.name for p in (root / "scripts").glob("*.py"))
    dirs = "|".join(re.escape(d) for d in PLUGIN_DIRS)
    derived = data["derived"]
    rules.append(Rule(
        "N20", "plugin-component-name",
        re.compile(rf"(?<![\w-])(?:{_alt(components)})(?![\w-])"),
        derived["N20"]["why"],
        (f"Run /{components[0]} first.", f"Hand it to the {components[-1]} agent."),
        tuple(derived["N20"]["negative"])))
    rules.append(Rule(
        "N21", "plugin-file",
        re.compile(rf"(?<![\w.-])(?:{dirs})/(?:[\w.-]+/)*(?:{_alt(files)})(?![\w-])"
                   rf"|`(?:\./)?(?:{_alt(alone)})`"),
        derived["N21"]["why"],
        (f"Run `scripts/{scripts[0]}` first.", f"Open `{alone[0]}` and read it.",
         *derived["N21"]["positive"]),
        tuple(derived["N21"]["negative"])))
    ids = [r.id for r in rules]
    assert len(ids) == len(set(ids)), f"duplicate rule ids: {ids}"
    return rules


def _excerpt(text: str, m: re.Match, pad: int = 25) -> str:
    a, b = max(0, m.start() - pad), min(len(text), m.end() + pad)
    return ("..." if a else "") + text[a:b] + ("..." if b < len(text) else "")


def lint(text: str, rules: list[Rule]) -> list[Hit]:
    """Every rule that matches in any block, with the block's first line."""
    hits = []
    for b in blocks(text):
        for r in rules:
            m = r.regex.search(b.text)
            if m:
                hits.append(Hit(b.line, r.id, r.name, _excerpt(b.text, m)))
    return hits
