#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Validate investigator output: schema, then evidence resolution.

This is the step that makes a finding trustworthy. A hypothesis is only as
good as the evidence under it, and a language model is perfectly capable of
producing a confident sentence attached to a line number that does not exist.
So every ref is resolved mechanically:

  code      path:line — the file exists and the line is inside it
  commit    a SHA that git can actually resolve in this repository, and that
            touched the finding's file or a file cited as code evidence — a
            SHA that merely exists is not history
  detector  S0x@path:line — copied exactly from a hit in hotspots.json
  catalog   <type> <entity ref> — an edge in context.json, from the same
            snapshot the finding's bundle was built from
  precondition  default_ref / doc_ref — path:line, resolved like a code ref

Anything that fails gets one repair round with the error text, then it is
recorded as analysis_failed. No retry loops.

    uv run scripts/validate.py            # validate everything
    uv run scripts/validate.py --file .thunderstruck/findings/H01.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402

VALIDATION_SCHEMA = "thunderstruck.validation/v1"
MAX_FINDINGS_PER_HOTSPOT = 3
CONFIDENCES = {"low", "medium", "high"}
EVIDENCE_TYPES = {"code", "commit", "detector", "catalog"}

REQUIRED_FIELDS = [
    "location", "missing_patterns", "failure_mode", "trigger_condition",
    "blast_radius", "evidence", "preconditions",
    "confidence", "confidence_rationale", "how_to_verify",
]
# Present or absent; never an empty string (#56 AC-6)
OPTIONAL_TEXT = ("amplifier", "sustaining_effect")
# The keys an investigator may write. #57 adds "confirmation", written after validation.
PRECONDITION_KEYS = frozenset({"setting", "default", "default_ref", "needs", "value",
                               "documented", "doc_ref"})
PRECONDITION_FORM = ('{"setting": "API_RETRY_ON_429", "default": "false", '
                     '"default_ref": "src/client/api.ts:1", "needs": "changed", "value": "true", '
                     '"documented": "no", "doc_ref": null}')

# [0-9] and \Z, not \d and $: "١٦" and a trailing newline are not line numbers
CODE_REF = re.compile(r"^(?P<path>[^:]+):(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?\Z")
DETECTOR_REF = re.compile(r"^(?P<pid>[A-Z]+\d+)@(?P<path>[^:]+):(?P<line>\d+)$")
SHA_REF = re.compile(r"^[0-9a-fA-F]{4,40}$")
BLAME_LINE = re.compile(r"^([0-9a-f]{40}) \d+ \d+", re.MULTILINE)
LINE_RANGE = re.compile(r"^(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?\Z")
RANGE_FORM = 'a line ("42") or a range ("42-118") with start ≤ end'
REF_FORMS = {
    "code": '"path/to/file.ts:42" or "path/to/file.ts:42-118"',
    "commit": 'a bare SHA from the bundle\'s change history, e.g. "a1b2c3d" (no "commit:" prefix)',
    "detector": '"S05@path/to/file.ts:12", copied from the bundle\'s Detector leads',
    "catalog": '"dependencyOf component:default/web-frontend", copied from the bundle\'s Service context',
}
TYPE_ALIASES = {"git": "commit", "sha": "commit", "file": "code", "source": "code"}


def shown(value: Any, limit: int = 80) -> str:
    """A received value, short enough to quote in an error message."""
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def parse_range(value: Any) -> tuple[int, int] | None:
    """(start, end) for an int or a "42" / "42-118" string; None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value, value
    if isinstance(value, str) and (m := LINE_RANGE.match(value)):
        start = int(m["start"])
        return start, int(m["end"] or start)
    return None


def range_fits(span: tuple[int, int] | None, total: int) -> bool:
    return span is not None and 1 <= span[0] <= span[1] <= total


def range_error(rel: str, total: int) -> str:
    """The one message for any unusable line range, in a location or a code ref."""
    lines = "line" if total == 1 else "lines"
    return f"that line does not exist: use {RANGE_FORM} inside {rel}, which has {total} {lines}"


def _count_lines(path: Path) -> int | None:
    try:
        with path.open("rb") as fh:
            return sum(1 for _ in fh) or 1
    except OSError:
        return None


class Validator:
    def __init__(self, repo: Path, hotspots: dict, catalog: dict,
                 context: dict | None = None,
                 bundle_context: dict[str, str | None] | None = None,
                 extra_fix: tuple[str, ...] = ()) -> None:
        self.repo = repo
        self.extra_fix = tuple(extra_fix)
        self.valid_ids = c.catalog_ids(catalog)
        self.detector_refs: set[str] = set()
        for hs in hotspots.get("hotspots", []) + (hotspots.get("dormant") or []):
            for hit in hs.get("detector_hits", []):
                self.detector_refs.add(hit["ref"])
        self.context_hash = context.get("context_hash") if context else None
        self.catalog_edges: dict[str, dict] = (
            {e["ref"]: e for e in context.get("edges") or []} if context else {})
        self.bundle_context = bundle_context or {}
        self._pinned: str | None = None
        self._line_cache: dict[str, int | None] = {}
        self._sha_cache: dict[str, bool] = {}
        self._subject_cache: dict[str, str | None] = {}
        self._blame_cache: dict[tuple[str, int, int], set[str]] = {}
        self._index: dict[str, str] | None = None
        self._resolved: dict[str, tuple[str, int | None, str | None]] = {}

    # ---------------------------------------------------------------- refs

    def _lines_in(self, rel: str) -> int | None:
        if rel not in self._line_cache:
            self._line_cache[rel] = _count_lines(self.repo / rel)
        return self._line_cache[rel]

    def _tracked(self) -> dict[str, str]:
        """{path: mode} for every entry in the git index, loaded once."""
        if self._index is None:
            self._index = c.tracked_index(self.repo)
        return self._index

    def _spelling_hint(self, rel: str) -> str:
        lowered = rel.lower()
        match = next((p for p in self._tracked() if p.lower() == lowered), None)
        return f" (did you mean {match!r}?)" if match else ""

    def _resolve(self, raw: Any) -> tuple[str, int | None, str | None]:
        """(canonical path, line count, error) for a cited path.

        "Inside the repository" means in the git index. Every check runs before
        the file is opened, so a path outside the repository is never read.
        """
        key = str(raw)
        if key in self._resolved:
            return self._resolved[key]
        rel = c.ref_path(raw)
        total: int | None = None
        error: str | None = None
        mode = None
        path = self.repo / rel
        if (why := c.path_problem(rel)):
            error = (f"{why}. Cite the path relative to the repository root, exactly "
                     f"as the bundle shows it")
        elif (mode := self._tracked().get(rel)) is None:
            hint = self._spelling_hint(rel)
            if hint:
                error = "is not tracked under that spelling" + hint
            elif os.path.isdir(path):
                error = "is a directory, not a file"
            elif os.path.lexists(path):
                error = "is not tracked by git; untracked and ignored files can't be cited"
            else:
                error = "no such file in the repository"
        elif (error := c.tracked_file_problem(self.repo, rel, mode)) is None:
            if (total := self._lines_in(rel)) is None:
                error = "could not be read"
        self._resolved[key] = (rel, total, error)
        return self._resolved[key]

    def _subject(self, sha: str) -> str | None:
        """The commit's subject line, read once per SHA."""
        if sha not in self._subject_cache:
            try:
                out = c.git_paths(self.repo, "log", "-1", "--format=%s", sha, "--")
                self._subject_cache[sha] = out.strip("\n")
            except c.ThunderstruckError:
                self._subject_cache[sha] = None
        return self._subject_cache[sha]

    def _introduced(self, rel: str, start: int, end: int) -> set[str]:
        """Full SHAs of the commits that wrote lines start..end of the working
        tree file. An uncommitted line blames to the all-zero SHA, which is
        dropped, so it is introduced by no commit."""
        key = (rel, start, end)
        if key not in self._blame_cache:
            try:
                out = c.git_paths(self.repo, "blame", "--porcelain", "-L",
                                  f"{start},{end}", "--", rel)
            except c.ThunderstruckError:
                out = ""
            shas = {m.group(1) for m in BLAME_LINE.finditer(out)}
            self._blame_cache[key] = {s for s in shas if s.strip("0")}
        return self._blame_cache[key]

    def _sha_ok(self, sha: str) -> bool:
        if sha not in self._sha_cache:
            self._sha_cache[sha] = c.commit_exists(self.repo, sha)
        return self._sha_cache[sha]

    def check_evidence(self, ev: Any, where: str, errors: list[str]) -> str | None:
        if not isinstance(ev, dict):
            errors.append(f"{where} is not an object: got {shown(ev)}. Use "
                          f'{{"type": "code", "ref": {REF_FORMS["code"].split(" or ")[0]}, "note": "..."}}')
            return None
        etype, ref = ev.get("type"), ev.get("ref")
        if etype not in EVIDENCE_TYPES:
            alias = TYPE_ALIASES.get(str(etype).strip().lower()) if isinstance(etype, str) else None
            errors.append(f"{where}.type {etype!r} is not one of {sorted(EVIDENCE_TYPES)}"
                          + (f" — use {alias!r}" if alias else ""))
            return None
        if not isinstance(ref, str) or not ref.strip():
            got = (f"got {shown(ref)}" if "ref" in ev
                   else f"no 'ref' key; the item has keys {sorted(ev)}")
            errors.append(f"{where}.ref is missing or not a string ({got}). A {etype} "
                          f"ref is one string: {REF_FORMS[etype]}")
            return None
        ref = ref.strip()
        role = ev.get("role")
        if etype == "commit" and role not in c.COMMIT_ROLES:
            errors.append(f"{where}.role {role!r} is not one of {list(c.COMMIT_ROLES)}: what this "
                          f"commit did to the cited code (introduced = wrote it; fixed = an "
                          f"earlier fix attempt; mitigated = added a guard or option; changed = "
                          f"anything else)")
        elif etype != "commit" and "role" in ev:
            errors.append(f"{where}.role is only given on commit evidence")

        if etype == "code":
            m = CODE_REF.match(ref)
            raw_path = m["path"] if m else ref.rpartition(":")[0]
            if not m and (not raw_path or re.search(r":[0-9]+\Z", raw_path)):
                errors.append(f"{where}.ref {ref!r} is not path:line or path:start-end, "
                              f"e.g. {REF_FORMS['code']}")
                return etype
            rel, total, problem = self._resolve(raw_path)
            if problem:
                errors.append(f"{where}.ref {ref!r} — {raw_path!r} {problem}")
            elif not m or not range_fits((int(m["start"]), int(m["end"] or m["start"])), total):
                errors.append(f"{where}.ref {ref!r} — {range_error(rel, total)}")
        elif etype == "commit":
            short = ref.split()[0]
            if not SHA_REF.match(short):
                errors.append(f"{where}.ref {ref!r} is not a commit SHA; use "
                              f"{REF_FORMS['commit']}")
            elif not self._sha_ok(short):
                errors.append(
                    f"{where}.ref {ref!r} — no such commit in this repository. "
                    f"Use a SHA from the bundle's change history.")
        elif etype == "detector":
            m = DETECTOR_REF.match(ref)
            if not m:
                errors.append(f"{where}.ref {ref!r} is not S0x@path:line, e.g. "
                              f"{REF_FORMS['detector']}")
            elif ref not in self.detector_refs:
                errors.append(
                    f"{where}.ref {ref!r} — no detector produced that hit. Copy a "
                    f"ref verbatim from the 'Detector leads' section of the bundle.")
        else:  # catalog
            if self.context_hash is None:
                errors.append(
                    f"{where}.ref {ref!r} — this scan has no service context, so no "
                    f"catalog edge can be cited")
            elif self._pinned != self.context_hash:
                errors.append(
                    f"{where}.ref {ref!r} — context changed since bundling. Re-run "
                    f"bundle.py so the bundle and context.json agree.")
            elif ref not in self.catalog_edges:
                errors.append(
                    f"{where}.ref {ref!r} — no such edge in the service context. Copy a "
                    f"ref verbatim from the bundle's 'Service context' section.")
        return etype

    def check_ref(self, ref: Any, where: str, errors: list[str]) -> tuple[str, int, int] | None:
        """A path:line or path:start-end that must resolve exactly as a `code`
        evidence ref does. The one place a precondition ref is resolved (spec §7)."""
        if not isinstance(ref, str) or not ref.strip():
            errors.append(f"{where} must be one string, {REF_FORMS['code']}; got {shown(ref)}")
            return None
        ref = ref.strip()
        m = CODE_REF.match(ref)
        if not m:
            errors.append(f"{where} {ref!r} is not path:line or path:start-end, e.g. "
                          f"{REF_FORMS['code']}")
            return None
        rel, total, problem = self._resolve(m["path"])
        if problem:
            errors.append(f"{where} {ref!r} — {m['path']!r} {problem}")
            return None
        span = (int(m["start"]), int(m["end"] or m["start"]))
        if not range_fits(span, total):
            errors.append(f"{where} {ref!r} — {range_error(rel, total)}")
            return None
        return rel, *span

    def check_preconditions(self, pre: Any, where: str, errors: list[str]) -> None:
        if not isinstance(pre, list):
            errors.append(f"{where} must be a list ([] when the failure happens on default "
                          f"settings); got {shown(pre)}")
            return
        seen: set[str] = set()
        for j, p in enumerate(pre):
            pw = f"{where}[{j}]"
            if not isinstance(p, dict):
                errors.append(f"{pw} is not an object: got {shown(p)}. Use {PRECONDITION_FORM}")
                continue
            unknown = sorted(set(p) - PRECONDITION_KEYS)
            if unknown:
                errors.append(f"{pw} has unknown key(s) {unknown}; the keys are "
                              f"{sorted(PRECONDITION_KEYS)}")
            for key in ("setting", "default"):
                if not isinstance(p.get(key), str) or not p[key].strip():
                    errors.append(f"{pw}.{key} must be a non-empty string; got {shown(p.get(key))}")
            name = p.get("setting")
            if isinstance(name, str) and name.strip():
                norm = "".join(name.split()).casefold()
                if norm in seen:
                    errors.append(f"{pw}.setting {name!r} is listed twice; one item per setting")
                seen.add(norm)
            self.check_ref(p.get("default_ref"), f"{pw}.default_ref", errors)
            needs, value = p.get("needs"), p.get("value")
            if needs not in c.PRECONDITION_NEEDS:
                errors.append(f'{pw}.needs {needs!r} is not one of {list(c.PRECONDITION_NEEDS)}: '
                              f'"changed" when the failure needs the setting changed from its '
                              f'default, "default" when it happens on the default')
            elif needs == "changed" and (not isinstance(value, str) or not value.strip()):
                errors.append(f'{pw}.value must name the value the failure needs when needs is '
                              f'"changed"; got {shown(value)}')
            elif needs == "default" and value is not None:
                errors.append(f'{pw}.value must be absent or null when needs is "default"; the '
                              f'default is the value')
            documented = p.get("documented")
            if documented not in c.DOCUMENTED:
                errors.append(f"{pw}.documented {documented!r} is not one of {list(c.DOCUMENTED)}")
            elif documented == "yes":
                self.check_ref(p.get("doc_ref"), f"{pw}.doc_ref", errors)
            elif p.get("doc_ref") is not None:
                errors.append(f'{pw}.doc_ref is only given when documented is "yes"')

    def _written(self, evidence: list) -> set[str]:
        """Full SHAs that wrote any line of any cited code range (git blame)."""
        out: set[str] = set()
        for ev in evidence:
            if not isinstance(ev, dict) or ev.get("type") != "code":
                continue
            m = CODE_REF.match(str(ev.get("ref") or "").strip())
            if not m:
                continue
            rel, total, err = self._resolve(m.group("path"))
            start, end = int(m["start"]), int(m["end"] or m["start"])
            if err or not range_fits((start, end), total or 0):
                continue
            out |= self._introduced(rel, start, end)
        return out

    @staticmethod
    def _wrote(sha: str, written: set[str]) -> bool:
        return any(full.startswith(sha.lower()) for full in written)

    def history(self, finding: dict) -> list[dict]:
        """One entry per distinct cited commit: its class, its stated role and
        whether it wrote a cited line. A signal of fragility; never confidence."""
        evidence = [ev for ev in finding.get("evidence") or [] if isinstance(ev, dict)]
        if not any(ev.get("type") == "commit" for ev in evidence):
            return []  # nothing to blame for
        written = self._written(evidence)
        out: list[dict] = []
        seen: set[str] = set()
        for ev in evidence:
            if ev.get("type") != "commit":
                continue
            sha = str(ev.get("ref") or "").strip().split()[0]
            if sha in seen:
                continue
            seen.add(sha)
            subject = self._subject(sha)
            out.append({"sha": sha,
                        "class": (c.classify_commit(subject, self.extra_fix)
                                  if subject is not None else None),
                        "role": ev.get("role"),
                        "wrote_cited_line": self._wrote(sha, written)})
        return out

    # ------------------------------------------------------------ findings

    def check_finding(self, f: Any, idx: int, errors: list[str]) -> None:
        where = f"findings[{idx}]"
        if not isinstance(f, dict):
            errors.append(f"{where} is not an object")
            return

        for key in REQUIRED_FIELDS:
            if key not in f:
                errors.append(f"{where}.{key} is missing"
                              + (" (it may be [], but the key must be present)"
                                 if key == "preconditions" else ""))

        loc = f.get("location")
        if not isinstance(loc, dict) or not loc.get("file"):
            got = ("" if "location" not in f
                   else f" (location is {shown(loc)})" if not isinstance(loc, dict)
                   else f" (location has keys {sorted(loc)})")
            errors.append(f"{where}.location.file is missing{got}. location is an object: "
                          f'{{"file": "path/to/file.ts", "lines": "42-118"}}, '
                          f'"lines" optional')
        else:
            rel, total, problem = self._resolve(loc["file"])
            if problem:
                errors.append(f"{where}.location.file {loc['file']!r} {problem}")
            elif loc.get("lines") is not None and not range_fits(parse_range(loc["lines"]), total):
                errors.append(f"{where}.location.lines {loc['lines']!r} — "
                              f"{range_error(rel, total)} (leave it out for a whole-file finding)")

        pats = f.get("missing_patterns")
        if not isinstance(pats, list) or not pats:
            errors.append(f"{where}.missing_patterns must be a non-empty list, e.g. "
                          f'["S03", "S05"] or ["OTHER"]'
                          + (f"; got {shown(pats)}" if "missing_patterns" in f else ""))
        else:
            unknown = [p for p in pats if p not in self.valid_ids]
            if unknown:
                errors.append(
                    f"{where}.missing_patterns contains unknown id(s) {unknown}. "
                    f"Use a catalog ID or 'OTHER'.")

        conf = f.get("confidence")
        if conf not in CONFIDENCES:
            if "confidence" in f:
                errors.append(f"{where}.confidence {conf!r} is not one of {sorted(CONFIDENCES)}")

        for field in ("failure_mode", "trigger_condition", "how_to_verify"):
            value = f.get(field)
            if field in f and (not isinstance(value, str) or not value.strip()):
                errors.append(f"{where}.{field} must be a non-empty string; got {shown(value)}")

        for field in OPTIONAL_TEXT:
            value = f.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append(f"{where}.{field} must be a non-empty string when present; leave it "
                              f"out when there is nothing to state (got {shown(value)})")
        if "preconditions" in f:
            self.check_preconditions(f["preconditions"], f"{where}.preconditions", errors)
        check = f.get("check")
        if check is not None:
            if not isinstance(check, dict) or check.get("status") not in c.CHECK_STATUSES:
                errors.append(f"{where}.check.status must be one of {list(c.CHECK_STATUSES)}; "
                              f"got {shown(check)}")
            else:
                for key in ("by", "reason"):
                    if check.get(key) is not None and not isinstance(check[key], str):
                        errors.append(f"{where}.check.{key} must be a string or null")

        evidence = f.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{where}.evidence must be a non-empty list of "
                          f'{{"type", "ref", "note"}} objects'
                          + (f"; got {shown(evidence)}" if "evidence" in f else ""))
            return
        types = [self.check_evidence(ev, f"{where}.evidence[{i}]", errors)
                 for i, ev in enumerate(evidence)]
        touching = self.check_commits_touch(f, evidence, types, where, errors)
        if "code" not in types:
            errors.append(
                f"{where}.evidence has no item of type 'code'. A detector hit on "
                f"its own never justifies a finding — cite the code that fails.")
        written: set[str] | None = None
        for i, (ev, etype) in enumerate(zip(evidence, types)):
            if etype != "commit" or ev.get("role") != "introduced":
                continue
            short = str(ev["ref"]).strip().split()[0]
            if short not in touching:
                continue  # unresolvable or not touching: already reported
            written = self._written(evidence) if written is None else written
            if not self._wrote(short, written):
                errors.append(
                    f"{where}.evidence[{i}] is cited as having introduced the cited code, but it "
                    f"wrote none of the cited lines (git blame). Use role \"changed\", or cite "
                    f"the commit that wrote them.")

    def check_commits_touch(self, f: dict, evidence: list, types: list,
                            where: str, errors: list[str]) -> list[str]:
        """A commit is evidence only if it changed the code the finding is
        about. Without this, any SHA from the bundle could pass as the
        history of code it never touched."""
        cited: list[str] = []
        loc = f.get("location")
        if isinstance(loc, dict) and loc.get("file"):
            cited.append(loc["file"])
        for ev in evidence:
            if isinstance(ev, dict) and ev.get("type") == "code":
                m = CODE_REF.match(str(ev.get("ref") or "").strip())
                if m:
                    cited.append(m.group("path"))
        # only paths that resolved: an invalid one already has its own error
        files = list(dict.fromkeys(rel for rel, _, err in map(self._resolve, cited) if not err))
        if not files:
            return []
        touching: list[str] = []
        for i, (ev, etype) in enumerate(zip(evidence, types)):
            if etype != "commit":
                continue
            short = str(ev["ref"]).strip().split()[0]
            if not self._sha_ok(short):
                continue  # already reported as unresolvable
            if c.commit_touches(self.repo, short, files):
                touching.append(short)
            else:
                errors.append(
                    f"{where}.evidence[{i}].ref {short!r} does not touch "
                    f"{files[0] if files else 'the finding'} or any file cited as "
                    f"code evidence. Cite a commit from this file's change history.")
        return touching

    def check_document(self, doc: Any) -> list[str]:
        errors: list[str] = []
        if not isinstance(doc, dict):
            return ["top level is not a JSON object"]
        hid = doc.get("hotspot_id")
        self._pinned = self.bundle_context.get(hid) if isinstance(hid, str) else None
        if not hid:
            errors.append("hotspot_id is missing")
        elif not isinstance(hid, str):
            errors.append(f"hotspot_id {hid!r} must be a string")
        findings = doc.get("findings")
        if findings is None:
            other = [k for k in doc if isinstance(doc[k], list)]
            errors.append("findings is missing (use [] when there is nothing to report)"
                          + (f"; the top-level list is keyed {other[0]!r}, but the key "
                             f"must be 'findings'" if other else ""))
            return errors
        if not isinstance(findings, list):
            errors.append(f"findings must be a list; got {shown(findings)}")
            return errors
        if len(findings) > MAX_FINDINGS_PER_HOTSPOT:
            errors.append(
                f"{len(findings)} findings for one hotspot; the maximum is "
                f"{MAX_FINDINGS_PER_HOTSPOT}. Keep the strongest.")
        for i, f in enumerate(findings):
            self.check_finding(f, i, errors)
        return errors


def canonicalise(finding: dict) -> None:
    """Write the canonical path back into a valid finding, so a file has one
    identity everywhere: its key, index.json, the guardrail and the report."""
    loc = finding.get("location")
    if isinstance(loc, dict) and loc.get("file"):
        loc["file"] = c.ref_path(loc["file"])
    for ev in finding.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("type") == "code":
            ev["ref"] = _canonical_ref(ev.get("ref"))
    for p in finding.get("preconditions") or []:
        if isinstance(p, dict):
            for key in ("default_ref", "doc_ref"):
                if p.get(key) is not None:
                    p[key] = _canonical_ref(p[key])


def _canonical_ref(ref: Any) -> Any:
    """path:line with the canonical path; anything else unchanged."""
    m = CODE_REF.match(str(ref or "").strip())
    if not m:
        return ref
    rng = m["start"] + (f"-{m['end']}" if m["end"] else "")
    return f"{c.ref_path(m['path'])}:{rng}"


def evidence_hashes(repo: Path, finding: dict) -> dict[str, str]:
    """Content hash of every file cited as code evidence, so the guardrail can
    tell when that file, and not only the finding's own, has changed."""
    out: dict[str, str] = {}
    for ev in finding.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("type") == "code":
            m = CODE_REF.match(str(ev.get("ref") or "").strip())
            if m and m.group("path") not in out:
                out[m.group("path")] = c.sha256_file(repo / m.group("path"))
    return dict(sorted(out.items()))


def stable_key(file: str, failure_mode: str) -> str:
    """Identity that survives re-ranking, so a later run can tell whether a
    finding is the same one. Display IDs renumber; this does not."""
    return c.short_hash(f"{file}\x00{(failure_mode or '').strip().lower()}", 12)


def catalog_evidence(finding: dict, edges: dict[str, dict]) -> list[dict]:
    """The cited edges, resolved from context.json, so reports never take an
    attribute from the investigator's own text."""
    out: list[dict] = []
    for ev in finding.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("type") == "catalog":
            edge = edges.get(str(ev.get("ref") or "").strip())
            if edge:
                out.append({"ref": edge["ref"], "direction": edge["direction"],
                            "neighbour": edge["neighbour"],
                            "attributes": dict(edge.get("attributes") or {})})
    return out


def _bundle_context(repo: Path) -> dict[str, str | None]:
    index = c.load_json(c.out_dir(repo) / "bundles" / "index.json", {}) or {}
    return {b["id"]: b.get("context_hash") for b in index.get("bundles", [])
            if isinstance(b, dict) and "id" in b}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="validate.py",
                                 description="validate investigator findings")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--file", default=None, help="validate a single findings file")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="also print the valid hotspots")
    args = ap.parse_args(argv)

    try:
        repo = c.find_repo_root(args.repo)
        hotspots = c.load_json(c.out_dir(repo) / "hotspots.json")
        if not hotspots:
            raise c.ThunderstruckError("no hotspots.json — run signals.py first.")
        catalog = c.load_catalog()
    except c.ThunderstruckError as exc:
        c.die(str(exc))
        return 2

    findings_dir = c.out_dir(repo) / "findings"
    paths = ([Path(args.file)] if args.file
             else sorted(findings_dir.glob("*.json")) if findings_dir.is_dir() else [])
    if not paths:
        c.die(f"no findings files in {findings_dir}. Run the investigators first.")
        return 2

    try:
        extra_fix = c.profile_fix_keywords(c.load_profile(repo))
    except c.ThunderstruckError:
        extra_fix = ()  # an unreadable profile fails signals.py loudly; not here
    validator = Validator(repo, hotspots, catalog,
                          context=c.load_service_context(repo),
                          bundle_context=_bundle_context(repo), extra_fix=extra_fix)
    results, all_ok = [], True
    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            results.append({"path": str(path), "hotspot_id": path.stem, "valid": False,
                            "findings": 0, "errors": [f"not readable as JSON: {exc}"]})
            all_ok = False
            continue
        errors = validator.check_document(doc)
        n = len(doc.get("findings") or []) if isinstance(doc, dict) else 0
        if not errors and isinstance(doc, dict):
            for f in doc["findings"]:
                canonicalise(f)
                f["key"] = stable_key(f.get("location", {}).get("file", ""),
                                      f.get("failure_mode", ""))
                f["content_hash"] = c.sha256_file(
                    repo / c.ref_path(f.get("location", {}).get("file", "")))
                f["catalog_evidence"] = catalog_evidence(f, validator.catalog_edges)
                f["evidence_hashes"] = evidence_hashes(repo, f)
                f["history"] = validator.history(f)
                if "check" not in f:
                    f["check"] = {"status": "unchecked", "by": None, "reason": None}
            doc["validated_with"] = c.VALIDATION_RULES
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        results.append({"path": str(path), "hotspot_id": doc.get("hotspot_id", path.stem)
                        if isinstance(doc, dict) else path.stem,
                        "valid": not errors, "findings": n, "errors": errors})
        all_ok = all_ok and not errors

    payload = {"schema": VALIDATION_SCHEMA, "ok": all_ok,
               "checked": len(results),
               "valid": sum(1 for r in results if r["valid"]),
               "findings_total": sum(r["findings"] for r in results if r["valid"]),
               "results": results}
    c.write_json(c.out_dir(repo) / "validation.json", payload)

    if not args.quiet:
        for r in results:
            if r["valid"] and not args.verbose:
                continue
            mark = "ok  " if r["valid"] else "FAIL"
            print(f"{mark} {r['hotspot_id']}  {r['findings']} finding(s)")
            for err in r["errors"]:
                print(f"       - {err}")
        print(f"\n{payload['valid']}/{payload['checked']} valid, "
              f"{payload['findings_total']} findings")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
