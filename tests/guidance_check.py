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
import sys
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
# --- The behaviours each document must state (spec §4) ------------------------

# id -> (document, kind, behaviour in the ticket's words). The wording here is
# the ticket's, never the documents'. `prose` rows pin a whole sentence, list
# item or table cell; `heading` rows pin a whole heading.
REQUIRED = {
    "fix-01-stop-and-ask": ("fix", "prose", "Stop and ask when an input is missing (AC-1)"),
    "fix-02-recheck-the-code": ("fix", "prose", "Re-check the code against the ticket (AC-1)"),
    "fix-03a-read-the-callers": ("fix", "prose", "Read the callers (AC-1)"),
    "fix-03b-read-the-numbers": ("fix", "prose", "Read the numbers (AC-1)"),
    "fix-03c-read-the-not-checked-items": ("fix", "prose", "Read the not-checked items (AC-1)"),
    "fix-04-write-down-implicit-guarantees": ("fix", "prose", "Write down the implicit guarantees (AC-1)"),
    "fix-05-human-decision-on-caller-visible-change": (
        "fix", "prose", "Get a human decision when caller-visible behaviour changes (AC-1)"),
    "fix-06-failing-test-first": ("fix", "prose", "Write a failing test first (AC-1)"),
    "fix-07-smallest-change": ("fix", "prose", "Make the smallest change (AC-1)"),
    "fix-08a-account-for-what-was-removed": ("fix", "prose", "Account for what the fix removed (AC-1)"),
    "fix-08b-account-for-what-is-not-fixed": ("fix", "prose", "Account for what the fix does not fix (AC-1)"),
    "fix-09-real-commands-and-results": ("fix", "prose", "Report real commands and real results (AC-1)"),
    "fix-10-integration-suites": ("fix", "prose", "Run integration suites when the environment supports it (AC-1)"),
    "fix-11a-never-invent-a-result": ("fix", "prose", "Never invent a result (AC-1)"),
    "fix-11b-never-push": ("fix", "prose", "Never push (AC-1)"),
    "fix-inputs-heading": ("fix", "heading", "The document begins with the inputs it needs (AC-4)"),
    "fix-inputs-missing": ("fix", "prose", "What to do when an input is missing (AC-4)"),
    "review-lens-1-state-and-concurrency": ("review", "heading", "Lens 1, state and concurrency, is a section of its own with its brief (AC-2)"),
    "review-lens-2-callers-and-behaviour-change": (
        "review", "heading", "Lens 2, callers and behaviour change, is a section of its own with its brief (AC-2)"),
    "review-lens-3-test-and-conventions": ("review", "heading", "Lens 3, test and conventions, is a section of its own with its brief (AC-2)"),
    "review-lens-4-whole-finding-coverage": (
        "review", "heading", "Lens 4, whole-finding coverage, is a section of its own with its brief (AC-2)"),
    "review-report-format-heading": ("review", "heading", "The one report format has its own section (AC-2)"),
    "review-report-format-shared": ("review", "prose", "All four lenses report in that one format (AC-2)"),
    "review-read-only": ("review", "prose", "Reviewers are read-only (AC-2)"),
    "review-no-implementer-conclusions": (
        "review", "prose", "Reviewers are not given the implementer's conclusions (AC-2)"),
    "review-inputs-heading": ("review", "heading", "The document begins with the inputs it needs (AC-4)"),
    "review-inputs-missing": ("review", "prose", "What to do when an input is missing (AC-4)"),
}
SECTION_ROWS = tuple(r for r in REQUIRED if r.startswith("review-lens-")) + ("review-report-format-heading",)
LENS_ROWS = tuple(r for r in REQUIRED if r.startswith("review-lens-"))
BRIEF_MIN_WORDS = 20           # the body under a lens or format heading
PROSE = ("paragraph", "item", "row")


def _where(rid: str) -> str:
    doc, _kind, what = REQUIRED[rid]
    return f"{PUBLISHED[doc]}: {rid} ({what})"


_CLOSERS = r"[)\"'*_`\]]*"
_SENTENCE_END = re.compile(r"[.!?]" + _CLOSERS + r"$")
_AFTER_SENTENCE = re.compile(r"[.!?]" + _CLOSERS + r"\s$")


def _whole(t: str, i: int, j: int) -> bool:
    """`t[i:j]` is a whole sentence, list item or table cell of the block text `t`:
    it starts at the block, at a cell or just after a sentence's end, and it ends
    at the block, at a cell or at a sentence's end."""
    head, tail = t[:i], t[j:]
    starts = i == 0 or head.endswith("| ") or _AFTER_SENTENCE.search(head) is not None
    ends = not tail or tail.startswith(" |") or (_SENTENCE_END.search(t[:j]) is not None and tail[:1] == " ")
    return starts and ends


def occurrences(bl: list[Block], q: str) -> list[tuple[Block, int]]:
    """Every place `q` is a whole sentence, item or cell of a prose block, in
    document order."""
    found = []
    for b in bl:
        if b.kind not in PROSE:
            continue
        i = b.text.find(q)
        while i != -1:
            if _whole(b.text, i, i + len(q)):
                found.append((b, i))
            i = b.text.find(q, i + 1)
    return found


def row_problems(rid: str, text: str, quote) -> list[str]:
    """Why `quote` does not pin `rid` in `text`; empty when it does."""
    doc, kind, _what = REQUIRED[rid]
    where = _where(rid)
    if not isinstance(quote, str) or not quote.strip():
        return [f"{where}: no quote is pinned"]
    q = _flat(quote)
    bl = blocks(text)
    if kind == "heading":
        n = sum(1 for b in bl if b.kind == "heading" and b.text == q)
        return [] if n == 1 else [f"{where}: {n} headings read {q!r}, expected exactly 1"]
    found = occurrences(bl, q)
    if not found:
        if any(q in b.text for b in bl if b.kind in PROSE):
            return [f"{where}: {q!r} is part of a sentence, not the whole of one; "
                    f"quote the whole sentence, list item or table cell"]
        other = next((b.kind for b in bl if q in b.text), None)
        if other:
            return [f"{where}: {q!r} is in a {other}, not in prose"]
        return [f"{where}: {q!r} is not in the document"]
    if len(found) > 1:
        b, i = found[0]
        after = b.text[i + len(q):].lstrip()
        if after and not after.startswith("|"):
            return [f"{where}: {q!r} occurs {len(found)} times and its first occurrence (line {b.line}) "
                    f"is followed by another sentence; extend the quote with that sentence"]
    return []


def without_row(rid: str, text: str, quote) -> tuple[str, int]:
    """`text` with every block that satisfies the row taken out, by line, and
    how many blocks that was: the mutation a pinned text must fail."""
    _doc, kind, _what = REQUIRED[rid]
    q = _flat(quote)
    bl = blocks(text)
    if kind == "heading":
        hit = [b for b in bl if b.kind == "heading" and b.text == q]
    else:
        hit = [b for b, _ in occurrences(bl, q)]
    gone = {n for b in hit for n in range(b.line, b.end + 1)}
    kept = [ln for n, ln in enumerate(text.splitlines(), 1) if n not in gone]
    return "\n".join(kept) + "\n", len(hit)


def first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(?=\s|$)", text)
    return m.group(1) if m else text


def section_of(bl: list[Block], heading: str) -> list[Block]:
    """The blocks under the heading with this text, up to the next heading of
    the same or a higher level."""
    for i, b in enumerate(bl):
        if b.kind == "heading" and b.text == heading:
            for j in range(i + 1, len(bl)):
                if bl[j].kind == "heading" and bl[j].level <= b.level:
                    return bl[i + 1:j]
            return bl[i + 1:]
    return []


def inputs_problems(doc: str, text: str, heading, missing) -> list[str]:
    """A document begins with its inputs: the first heading after the title is
    the inputs heading (prose or a contents list may come before it), and the
    sentence that says what to do about a missing input lies inside its section."""
    where = f"{PUBLISHED[doc]}: {doc}-inputs-heading (the document begins with the inputs it needs)"
    bl = blocks(text)
    heads = [i for i, b in enumerate(bl) if b.kind == "heading"]
    if heads and bl[heads[0]].level == 1:
        heads = heads[1:]
    h, m = _flat(heading), _flat(missing)
    if not heads or bl[heads[0]].text != h:
        first = bl[heads[0]].text if heads else None
        return [f"{where}: the first heading after the title is {first!r}, expected {h!r}"]
    if not any(m in b.text for b in section_of(bl, h) if b.kind in PROSE):
        return [f"{where}: {m!r} is not inside the section under {h!r}"]
    return []


def section_problems(rid: str, text: str, heading) -> list[str]:
    """A lens heading, or the report format heading, has a body."""
    words = sum(len(b.text.split()) for b in section_of(blocks(text), _flat(heading)) if b.kind != "heading")
    if words >= BRIEF_MIN_WORDS:
        return []
    return [f"{_where(rid)}: the section under {_flat(heading)!r} has {words} words, "
            f"expected at least {BRIEF_MIN_WORDS}"]


def lens_problems(texts: dict, quotes: dict) -> list[str]:
    """The four lens headings are four different headings, each with a body,
    and so is the report format; skips a row that has no usable quote."""
    out = []
    for rid in SECTION_ROWS:
        if not row_problems(rid, texts["review"], quotes.get(rid)):
            out += section_problems(rid, texts["review"], quotes[rid])
    heads = [_flat(quotes[r]) for r in LENS_ROWS if isinstance(quotes.get(r), str) and quotes[r].strip()]
    if len(heads) != len(set(heads)):
        out.append(f"{PUBLISHED['review']}: the four lens rows must pin four different headings, got {heads}")
    return out


_LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


def link_problems(text: str, base: Path) -> list[str]:
    """Relative links and images that do not resolve from the document's folder.
    URLs and in-page anchors are not checked; code is skipped."""
    out = []
    for b in blocks(text):
        if b.kind == "code":
            continue
        for target in _LINK.findall(b.text):
            if _SCHEME.match(target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0].split("?", 1)[0]
            if path and not (base / path).exists():
                out.append(f"line {b.line}: the link to {target!r} does not resolve")
    return out


# --- The table: loading, checking, printing -----------------------------------

def read_documents(root: Path = ROOT) -> dict[str, str]:
    return {d: (root / p).read_text(encoding="utf-8") for d, p in PUBLISHED.items()}


def load_rows() -> list[dict]:
    data = yaml.safe_load((DATA / "behaviours.yaml").read_text(encoding="utf-8")) or {}
    return list(data.get("rows") or [])


def pinned(rows: list[dict]) -> tuple[dict, list[str]]:
    """The quote per row id, and the problems with the rows themselves."""
    quotes: dict = {}
    out = []
    for r in rows:
        rid = r.get("id") if isinstance(r, dict) else None
        if rid not in REQUIRED:
            out.append(f"unknown row {rid!r}: the table holds exactly the required rows")
        elif rid in quotes:
            out.append(f"{rid} is pinned twice")
        else:
            quotes[rid] = r.get("quote")
    return quotes, out


def quote_problems(texts: dict, rows: list[dict]) -> list[str]:
    quotes, out = pinned(rows)
    for rid, (doc, _kind, _what) in REQUIRED.items():
        out += row_problems(rid, texts[doc], quotes.get(rid))
    return out


def inputs_all_problems(texts: dict, rows: list[dict]) -> list[str]:
    quotes, _ = pinned(rows)
    out = []
    for doc in PUBLISHED:
        h, m = f"{doc}-inputs-heading", f"{doc}-inputs-missing"
        if not row_problems(h, texts[doc], quotes.get(h)) and not row_problems(m, texts[doc], quotes.get(m)):
            out += inputs_problems(doc, texts[doc], quotes[h], quotes[m])
    return out


def _code_span(s: str) -> str:
    fence = "`" * (max((len(r) for r in re.findall(r"`+", s)), default=0) + 1)
    return f"{fence} {s.replace('|', chr(92) + '|')} {fence}"


def table(texts: dict, rows: list[dict]) -> str:
    """The behaviour table for a pull request: what the ticket requires, the
    text pinned for it, the first sentence under a pinned heading, and the line
    the text starts on. Quotes sit in code spans."""
    quotes, _ = pinned(rows)
    out = ["| Row | Document | Behaviour the ticket requires | Pinned text | Opens with | Line |",
           "|---|---|---|---|---|---|"]
    for rid, (doc, kind, what) in REQUIRED.items():
        quote = quotes.get(rid)
        cell, opens, line = "MISSING", "", "-"
        if isinstance(quote, str) and quote.strip():
            q = _flat(quote)
            bl = blocks(texts[doc])
            cell = _code_span(q)
            if kind == "heading":
                at = [b.line for b in bl if b.kind == "heading" and b.text == q]
                first = next((b for b in section_of(bl, q) if b.kind in PROSE), None)
                opens = _code_span(first_sentence(first.text)) if first else ""
            else:
                at = [b.line for b, _ in occurrences(bl, q)]
            line = str(at[0]) if at else "NOT FOUND"
        out.append(f"| `{rid}` | `{PUBLISHED[doc]}` | {what} | {cell} | {opens} | {line} |")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if argv != ["--table"]:
        print("usage: python tests/guidance_check.py --table", file=sys.stderr)
        return 2
    texts, rows = read_documents(), load_rows()
    print(table(texts, rows))
    problems = quote_problems(texts, rows) + inputs_all_problems(texts, rows)
    for p in problems:
        print(f"problem: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
