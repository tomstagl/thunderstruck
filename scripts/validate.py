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

Anything that fails gets one repair round with the error text, then it is
recorded as analysis_failed. No retry loops.

    uv run scripts/validate.py            # validate everything
    uv run scripts/validate.py --file .thunderstruck/findings/H01.json
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import stat
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
    "amplifier", "sustaining_effect", "blast_radius", "evidence",
    "confidence", "confidence_rationale", "how_to_verify",
]

# [0-9] and \Z, not \d and $: "١٦" and a trailing newline are not line numbers
CODE_REF = re.compile(r"^(?P<path>[^:]+):(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?\Z")
DETECTOR_REF = re.compile(r"^(?P<pid>[A-Z]+\d+)@(?P<path>[^:]+):(?P<line>\d+)$")
SHA_REF = re.compile(r"^[0-9a-fA-F]{4,40}$")
LINE_RANGE = re.compile(r"^(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?\Z")
RANGE_FORM = 'a line ("42") or a range ("42-118") with start ≤ end'


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
                 bundle_context: dict[str, str | None] | None = None) -> None:
        self.repo = repo
        self.valid_ids = c.catalog_ids(catalog)
        self.detector_refs: set[str] = set()
        for hs in hotspots.get("hotspots", []):
            for hit in hs.get("detector_hits", []):
                self.detector_refs.add(hit["ref"])
        self.context_hash = context.get("context_hash") if context else None
        self.catalog_edges: dict[str, dict] = (
            {e["ref"]: e for e in context.get("edges") or []} if context else {})
        self.bundle_context = bundle_context or {}
        self._pinned: str | None = None
        self._line_cache: dict[str, int | None] = {}
        self._sha_cache: dict[str, bool] = {}
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

    def _resolves_to_itself(self, path: Path, rel: str) -> bool:
        try:
            return path.resolve() == self.repo.resolve() / rel
        except (OSError, RuntimeError):  # a symlink loop raises on Python 3.11
            return False

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
        elif mode == "120000":
            error = "is a symbolic link; cite the file it points to"
        elif mode == "160000":
            error = "is a submodule, not a file"
        elif not self._resolves_to_itself(path, rel):
            # a tracked path replaced locally by a link, even to a file inside
            # the repository such as an ignored .env, is not what git tracks
            error = "passes through a symbolic link in the working tree"
        else:
            try:
                st = os.lstat(path)
            except OSError as exc:
                st = None
                if exc.errno == errno.ELOOP:   # Python 3.13+ resolves loops without raising
                    error = "passes through a symbolic link in the working tree"
            if error:
                pass
            elif st is None:
                error = ("is tracked but missing from the working tree (deleted locally, "
                         "or outside a sparse checkout)")
            elif not stat.S_ISREG(st.st_mode):
                error = "is not a regular file in the working tree"
            elif (total := self._lines_in(rel)) is None:
                error = "could not be read"
        self._resolved[key] = (rel, total, error)
        return self._resolved[key]

    def _sha_ok(self, sha: str) -> bool:
        if sha not in self._sha_cache:
            self._sha_cache[sha] = c.commit_exists(self.repo, sha)
        return self._sha_cache[sha]

    def check_evidence(self, ev: Any, where: str, errors: list[str]) -> str | None:
        if not isinstance(ev, dict):
            errors.append(f"{where} is not an object")
            return None
        etype, ref = ev.get("type"), ev.get("ref")
        if etype not in EVIDENCE_TYPES:
            errors.append(f"{where}.type {etype!r} is not one of {sorted(EVIDENCE_TYPES)}")
            return None
        if not isinstance(ref, str) or not ref.strip():
            errors.append(f"{where}.ref is missing")
            return None
        ref = ref.strip()

        if etype == "code":
            m = CODE_REF.match(ref)
            raw_path = m["path"] if m else ref.rpartition(":")[0]
            if not m and (not raw_path or re.search(r":[0-9]+\Z", raw_path)):
                errors.append(f"{where}.ref {ref!r} is not path:line or path:start-end")
                return etype
            rel, total, problem = self._resolve(raw_path)
            if problem:
                errors.append(f"{where}.ref {ref!r} — {raw_path!r} {problem}")
            elif not m or not range_fits((int(m["start"]), int(m["end"] or m["start"])), total):
                errors.append(f"{where}.ref {ref!r} — {range_error(rel, total)}")
        elif etype == "commit":
            short = ref.split()[0]
            if not SHA_REF.match(short):
                errors.append(f"{where}.ref {ref!r} is not a commit SHA")
            elif not self._sha_ok(short):
                errors.append(
                    f"{where}.ref {ref!r} — no such commit in this repository. "
                    f"Use a SHA from the bundle's change history.")
        elif etype == "detector":
            m = DETECTOR_REF.match(ref)
            if not m:
                errors.append(f"{where}.ref {ref!r} is not S0x@path:line")
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

    # ------------------------------------------------------------ findings

    def check_finding(self, f: Any, idx: int, errors: list[str]) -> None:
        where = f"findings[{idx}]"
        if not isinstance(f, dict):
            errors.append(f"{where} is not an object")
            return

        for key in REQUIRED_FIELDS:
            if key not in f:
                errors.append(f"{where}.{key} is missing"
                              + (" (it may be null, but the key must be present)"
                                 if key == "sustaining_effect" else ""))

        loc = f.get("location")
        if not isinstance(loc, dict) or not loc.get("file"):
            errors.append(f"{where}.location.file is missing")
        else:
            rel, total, problem = self._resolve(loc["file"])
            if problem:
                errors.append(f"{where}.location.file {loc['file']!r} {problem}")
            elif loc.get("lines") is not None and not range_fits(parse_range(loc["lines"]), total):
                errors.append(f"{where}.location.lines {loc['lines']!r} — "
                              f"{range_error(rel, total)} (leave it out for a whole-file finding)")

        pats = f.get("missing_patterns")
        if not isinstance(pats, list) or not pats:
            errors.append(f"{where}.missing_patterns must be a non-empty list")
        else:
            unknown = [p for p in pats if p not in self.valid_ids]
            if unknown:
                errors.append(
                    f"{where}.missing_patterns contains unknown id(s) {unknown}. "
                    f"Use a catalog ID or 'OTHER'.")

        conf = f.get("confidence")
        if conf not in CONFIDENCES:
            errors.append(f"{where}.confidence {conf!r} is not one of {sorted(CONFIDENCES)}")

        for field in ("failure_mode", "trigger_condition", "how_to_verify"):
            value = f.get(field)
            if field in f and (not isinstance(value, str) or not value.strip()):
                errors.append(f"{where}.{field} must be a non-empty string")

        evidence = f.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{where}.evidence must be a non-empty list")
            return
        types = [self.check_evidence(ev, f"{where}.evidence[{i}]", errors)
                 for i, ev in enumerate(evidence)]
        self.check_commits_touch(f, evidence, types, where, errors)
        if "code" not in types:
            errors.append(
                f"{where}.evidence has no item of type 'code'. A detector hit on "
                f"its own never justifies a finding — cite the code that fails.")
        if conf == "high" and "commit" not in types:
            errors.append(
                f"{where}.confidence is 'high' but there is no 'commit' evidence. "
                f"High confidence needs both code and history; otherwise use 'medium'.")

    def check_commits_touch(self, f: dict, evidence: list, types: list,
                            where: str, errors: list[str]) -> None:
        """A commit is evidence only if it changed the code the finding is
        about. Without this, any SHA from the bundle buys 'high' confidence."""
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
            return
        for i, (ev, etype) in enumerate(zip(evidence, types)):
            if etype != "commit":
                continue
            short = str(ev["ref"]).strip().split()[0]
            if not self._sha_ok(short):
                continue  # already reported as unresolvable
            if not c.commit_touches(self.repo, short, files):
                errors.append(
                    f"{where}.evidence[{i}].ref {short!r} does not touch "
                    f"{files[0] if files else 'the finding'} or any file cited as "
                    f"code evidence. Cite a commit from this file's change history.")

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
            errors.append("findings is missing (use [] when there is nothing to report)")
            return errors
        if not isinstance(findings, list):
            errors.append("findings must be a list")
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
            m = CODE_REF.match(str(ev.get("ref") or "").strip())
            if m:
                rng = m["start"] + (f"-{m['end']}" if m["end"] else "")
                ev["ref"] = f"{c.ref_path(m['path'])}:{rng}"


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

    validator = Validator(repo, hotspots, catalog,
                          context=c.load_service_context(repo),
                          bundle_context=_bundle_context(repo))
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
            mark = "ok  " if r["valid"] else "FAIL"
            print(f"{mark} {r['hotspot_id']}  {r['findings']} finding(s)")
            for err in r["errors"]:
                print(f"       - {err}")
        print(f"\n{payload['valid']}/{payload['checked']} valid, "
              f"{payload['findings_total']} findings")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
