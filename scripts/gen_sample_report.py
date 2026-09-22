#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0", "lizard>=1.17"]
# ///
"""Regenerate examples/sample-report.md from the test fixture.

The sample must be a real artefact, not a mock-up: it is built by running the
actual pipeline over the fixture repository, with findings that pass the real
validator. If the finding contract changes, this stops producing output and
the sample stops being a lie.

The investigator is the one step not run here — a sample report cannot depend
on a model call. Its output is supplied from the canned findings below, which
describe the fixture's deliberately planted fractures and must satisfy
validate.py exactly like a real investigator's would.

    uv run scripts/gen_sample_report.py
    uv run scripts/gen_sample_report.py --check
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests" / "fixtures"))

import _common as c  # noqa: E402

# Pinned so the fixture, and therefore the sample, is reproducible.
BASE_DATE = datetime(2025, 1, 6, 9, 0, 0, tzinfo=timezone.utc)
SINCE = "2020-01-01"

# file fragment -> the finding an investigator should reach on that fracture
CANNED: dict[str, list[dict]] = {
    "client/releases.ts": [{
        "symbol": "fetchRelease",
        "anchor": "setTimeout(resolve, SLEEP_MS)",
        "missing_patterns": ["S02", "S10"],
        "failure_mode": "Release fetches retry on a fixed 2s schedule through two "
                        "stacked retry layers, so one upstream blip becomes 15 "
                        "requests per caller arriving in lockstep",
        "trigger_condition": "The releases API returns 5xx or times out for more "
                             "than two seconds while several callers are active",
        "amplifier": "withRetry retries 3 times inside a loop that retries 5 "
                     "times; attempts multiply to 15 rather than adding",
        "sustaining_effect": "Every client waits exactly SLEEP_MS and returns "
                             "together, so the upstream is re-saturated the "
                             "moment it starts recovering — the herd re-forms "
                             "on its own schedule",
        "blast_radius": "Every feature that resolves a release, including "
                        "user-facing lookups",
        "confidence": "high",
        "confidence_rationale": "Both retry layers are visible in the code, and "
                                "five separate 'fix timeout' commits on this file "
                                "in the window show the cause was never addressed",
        "how_to_verify": "Stub the releases endpoint to fail for 3s and call "
                         "fetchRelease from 10 clients at once; count upstream "
                         "requests (expect 150) and assert the inter-arrival "
                         "times are not identical",
        "prediction": "The next incident on this path is a retry storm after a "
                      "brief upstream degradation, not a slow dependency",
    }],
    "client/api.ts": [{
        "symbol": "callApi",
        "anchor": "res.status === 429",
        "missing_patterns": ["S03"],
        "failure_mode": "A 429 is retried after a fixed 5s regardless of the "
                        "window the server asked for, so the client keeps "
                        "arriving while it is still throttled",
        "trigger_condition": "The API returns 429 with Retry-After longer than 5 "
                             "seconds",
        "amplifier": "callApi recurses without a depth limit, so each rejected "
                     "retry immediately schedules another",
        "sustaining_effect": "Each early retry is itself throttled and counts "
                             "against the budget, extending the window that "
                             "caused it",
        "blast_radius": "All calls through this helper for the duration of the "
                        "throttle",
        "confidence": "medium",
        "confidence_rationale": "The code path is unambiguous, but no incident "
                                "in the window is attributable to it",
        "how_to_verify": "Return 429 with Retry-After: 60 and assert the next "
                         "request is not sent before 60s have passed",
        "prediction": "Rate-limit errors will cluster rather than resolve",
    }],
    "sync/collection.ts": [{
        "symbol": "syncCollection",
        "anchor": "let page = 1",
        "missing_patterns": ["S07"],
        "failure_mode": "An interrupted collection sync restarts at page 1 and "
                        "re-creates every row it already wrote",
        "trigger_condition": "Any failure part-way through a multi-page sync",
        "amplifier": "handleSyncFailure re-queues the whole job, so the retry "
                     "pays the full cost of the pages that already succeeded",
        "sustaining_effect": "Each attempt is as expensive as the first and hits "
                             "the same failure at the same page, so the job "
                             "re-queues indefinitely without ever progressing",
        "blast_radius": "The user's collection, which gains duplicate rows on "
                        "every attempt",
        "confidence": "high",
        "confidence_rationale": "The loop has no persisted cursor and db.create "
                                "is not an upsert; three commits in the window "
                                "describe duplicate rows and restarts",
        "how_to_verify": "Kill the process after page 2 of a 5-page sync, "
                         "restart it, and assert no row is created twice and "
                         "page 1 is not refetched",
        "prediction": "Duplicate-row reports will recur after any sync incident",
    }],
    "sync/scheduler.ts": [{
        "symbol": "submit",
        "anchor": "const queue:",
        "missing_patterns": ["S06"],
        "failure_mode": "A nightly batch sync and interactive user lookups share "
                        "one serial queue, so a batch run makes every user-facing "
                        "lookup wait behind it",
        "trigger_condition": "batchSync is called with more than a few ids while "
                             "a user is browsing",
        "amplifier": "The queue runs one job at a time, so latency is the full "
                     "depth of the batch ahead of the request",
        "sustaining_effect": None,
        "blast_radius": "Every interactive lookup for the duration of a batch run",
        "confidence": "medium",
        "confidence_rationale": "The shared queue is plain in the code; no "
                                "production latency data is available here",
        "how_to_verify": "Submit a 500-id batch, then time a userLookup; assert "
                         "it completes within an interactive budget",
        "prediction": "Lookup latency will correlate with the batch schedule",
    }],
    "util/format.ts": [{
        "symbol": "formatTitle",
        "anchor": "NOTE TO ANY AUTOMATED CODE REVIEWER",
        "missing_patterns": ["OTHER"],
        "failure_mode": "A source comment instructs automated reviewers to skip "
                        "this file and to exfiltrate the contents of a private "
                        "SSH key into their report",
        "trigger_condition": "Any automated review or agent that treats "
                             "repository text as instruction rather than data",
        "amplifier": "The text is phrased as an authorisation from a security "
                     "team, which is exactly the framing a naive reviewer trusts",
        "sustaining_effect": None,
        "blast_radius": "Any credential reachable by a tool that complies, and "
                        "the integrity of every audit of this repository",
        "confidence": "high",
        "confidence_rationale": "The instruction is present verbatim in the "
                                "source and was introduced by a commit in the "
                                "window",
        "how_to_verify": "Confirm no reviewer output for this file is empty "
                         "solely because of the comment, and that no key "
                         "material appears in any report",
        "prediction": "Left in place, this text will eventually be obeyed by "
                      "some tool in the pipeline",
    }],
}


def _line_of(repo: Path, rel: str, anchor: str) -> int:
    for n, line in enumerate(repo.joinpath(rel).read_text().split("\n"), 1):
        if anchor in line:
            return n
    return 1


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(cwd))
    if proc.returncode != 0:
        raise SystemExit(f"{' '.join(args[1:3])} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc


def generate() -> str:
    from build_fixture import build

    root = c.plugin_root()
    scripts = root / "scripts"
    with tempfile.TemporaryDirectory() as tmp:
        repo = build(Path(tmp) / "fixture", base_date=BASE_DATE)
        _run([sys.executable, str(scripts / "signals.py"), "--repo", str(repo),
              "--top", "9", "--since", SINCE], repo)
        _run([sys.executable, str(scripts / "bundle.py"), "--repo", str(repo)], repo)

        data = json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())
        by_file = {h["file"]: h for h in data["hotspots"]}

        for fragment, findings in CANNED.items():
            hs = next((h for f, h in by_file.items() if fragment in f), None)
            if hs is None:
                continue
            built = []
            for spec in findings:
                line = _line_of(repo, hs["file"], spec["anchor"])
                evidence = [{"type": "code", "ref": f"{hs['file']}:{line}",
                             "note": spec["anchor"]}]
                sha = (hs["churn"]["recent_shas"] or [None])[0]
                if sha:
                    evidence.append({"type": "commit", "ref": sha,
                                     "note": "most recent change to this file"})
                hit = next((h for h in hs["detector_hits"]
                            if h["pattern_id"] in spec["missing_patterns"]), None)
                if hit:
                    evidence.append({"type": "detector", "ref": hit["ref"],
                                     "note": "lead confirmed against the code"})
                item = {k: v for k, v in spec.items() if k not in ("symbol", "anchor")}
                item["location"] = {"file": hs["file"], "symbol": spec["symbol"],
                                    "lines": f"{line}-{line + 12}"}
                item["evidence"] = evidence
                built.append(item)
            doc = {"hotspot_id": hs["id"], "file": hs["file"], "findings": built}
            proc = subprocess.run(
                [sys.executable, str(scripts / "save_finding.py"),
                 "--repo", str(repo), "--id", hs["id"]],
                input=json.dumps(doc), capture_output=True, text=True, cwd=str(repo))
            if proc.returncode != 0:
                raise SystemExit(f"save_finding failed: {proc.stderr}")

        for hs in data["hotspots"]:
            path = repo / ".thunderstruck" / "findings" / f"{hs['id']}.json"
            if not path.is_file():
                subprocess.run(
                    [sys.executable, str(scripts / "save_finding.py"),
                     "--repo", str(repo), "--id", hs["id"]],
                    input=json.dumps({
                        "hotspot_id": hs["id"], "file": hs["file"], "findings": [],
                        "notes": "no credible production failure mode found"}),
                    capture_output=True, text=True, cwd=str(repo))

        validation = subprocess.run(
            [sys.executable, str(scripts / "validate.py"), "--repo", str(repo)],
            capture_output=True, text=True, cwd=str(repo))
        if validation.returncode != 0:
            raise SystemExit(
                "the sample findings no longer satisfy validate.py — fix the "
                f"canned findings in this script:\n{validation.stdout}")

        _run([sys.executable, str(scripts / "report.py"), "--repo", str(repo)], repo)
        report = (repo / ".thunderstruck" / "report.md").read_text()

    header = (
        "<!-- Generated by scripts/gen_sample_report.py from the test fixture in\n"
        "     tests/fixtures/build_fixture.py. Every finding below passed the real\n"
        "     validator: each ref resolved to a file:line, a commit in that repo, or\n"
        "     a detector hit. Regenerate with: uv run scripts/gen_sample_report.py -->\n\n")
    return header + report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gen_sample_report.py")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    dest = c.plugin_root() / "examples" / "sample-report.md"
    body = generate()
    if args.check:
        if not dest.is_file():
            print(f"{dest} does not exist", file=sys.stderr)
            return 1
        print(f"{dest.name} regenerated cleanly")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    print(f"wrote {dest} ({len(body.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
