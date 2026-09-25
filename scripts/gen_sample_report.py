#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3", "lizard==1.24.0"]  # exact: they shape the sample (#26)
# [tool.uv]
# exclude-newer = "2026-09-24T00:00:00Z"  # transitive deps too; bump with the pins
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
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests" / "fixtures"))

import _common as c  # noqa: E402

# This checkout, never CLAUDE_PLUGIN_ROOT: the sample describes the code it sits next to.
ROOT = Path(__file__).resolve().parent.parent

# Pinned so the fixture, and therefore the sample, is reproducible.
BASE_DATE = datetime(2025, 1, 6, 9, 0, 0, tzinfo=timezone.utc)
SINCE = "2020-01-01"
SAMPLE_REMOTE = "https://github.example.com/acme/fixture.git"
DATE_LABEL = "dates fixed for this sample"
# Every clock-dependent spot in the report, and what it becomes. Each must
# match exactly once: a report format change then breaks generation loudly
# instead of letting the clock back into the sample.
PINNED = (
    (re.compile(r"^Scanned \d{4}-\d{2}-\d{2} · ", re.M), "Scanned {day} (" + DATE_LABEL + ") · "),
    (re.compile(r"fetched \d{4}-\d{2}-\d{2} \(\d+ days? ago\)"), "fetched {day} (0 days ago)"),
)


def pin_dates(report: str, day: str) -> str:
    """Replace the run's real dates with `day` and say so in the run line.

    Only the generator does this, so a real scan can never print a fixed date.
    """
    for pattern, replacement in PINNED:
        report, n = pattern.subn(replacement.format(day=day), report)
        if n != 1:
            raise SystemExit(f"pin_dates: {pattern.pattern!r} matched {n} times, not once — "
                             "report.py's format changed; update PINNED in this script")
    return report

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
                        "user-facing lookups; the catalog lists web-frontend "
                        "as depending on this component",
        "catalog": ["dependencyOf component:default/web-frontend"],
        # the inner retry layer lives in another file; citing it files FR-001
        # under that file too (#19 AC-4)
        "also_cite": [("src/client/retry-wrapper.ts", "export async function withRetry",
                       "the inner retry layer: 3 attempts per call")],
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


def _corroborating_commit(repo: Path, hs: dict, spec: dict, line: int,
                          env: dict) -> tuple[str | None, str]:
    """The commit an investigator should cite (#19 AC-5): for an OTHER-only
    finding, the one that wrote the cited line; otherwise the most recent fix
    to the file, or, when there is none, the most recent change."""
    if spec["missing_patterns"] == ["OTHER"]:
        blame = _run(["git", "-C", str(repo), "blame", "--porcelain", "-L",
                      f"{line},{line}", "--", hs["file"]], repo, env).stdout
        return blame.split(" ", 1)[0], "introduced this text"
    for sha in hs["churn"]["recent_shas"]:
        subject = _run(["git", "-C", str(repo), "log", "-1", "--format=%s", sha],
                       repo, env).stdout.strip()
        if c.classify_commit(subject) == "fix":
            return sha, "most recent fix to this file"
    shas = hs["churn"]["recent_shas"]
    return (shas[0], "most recent change to this file") if shas else (None, "")


def _line_of(repo: Path, rel: str, anchor: str) -> int:
    for n, line in enumerate(repo.joinpath(rel).read_text(encoding="utf-8").split("\n"), 1):
        if anchor in line:
            return n
    return 1


def _run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(cwd), env=env)
    if proc.returncode != 0:
        raise SystemExit(f"{' '.join(args[1:3])} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc


def generate() -> str:
    from build_fixture import add_remote, add_service_context, build, isolated_git_env

    root = ROOT
    scripts = root / "scripts"
    with tempfile.TemporaryDirectory() as tmp:
        repo = build(Path(tmp) / "fixture", base_date=BASE_DATE)
        add_service_context(repo, python=sys.executable,
                            stub=root / "tests" / "fixtures" / "fake_catalog.py")
        # Report links: a reserved placeholder host (RFC 2606), so no sample
        # link can ever point at a real repository. It also exercises the
        # self-hosted path, which needs provider from the profile. Appended,
        # untracked: [context] survives and the pinned SHAs do not move.
        add_remote(repo, SAMPLE_REMOTE)
        with (repo / c.PROFILE_FILENAME).open("a", encoding="utf-8") as fh:
            fh.write('\n[links]\nprovider = "github"\n')
        # The whole pipeline runs without user git config, as the fixture was built
        env = isolated_git_env({k: v for k, v in os.environ.items()
                                if not k.startswith(("FAKE_CATALOG_", "CLAUDE_PLUGIN_"))})
        env.update(THUNDERSTRUCK_TRUST_CONTEXT="1", XDG_CONFIG_HOME=str(Path(tmp) / "xdg"))
        _run([sys.executable, str(scripts / "signals.py"), "--repo", str(repo),
              "--top", "9", "--since", SINCE], repo, env)
        _run([sys.executable, str(scripts / "context.py"), "--repo", str(repo)], repo, env)
        _run([sys.executable, str(scripts / "bundle.py"), "--repo", str(repo)], repo, env)

        data = json.loads((repo / ".thunderstruck" / "hotspots.json").read_text(encoding="utf-8"))
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
                for rel, anchor, note in spec.get("also_cite", []):
                    evidence.append({"type": "code",
                                     "ref": f"{rel}:{_line_of(repo, rel, anchor)}",
                                     "note": note})
                sha, note = _corroborating_commit(repo, hs, spec, line, env)
                if sha:
                    evidence.append({"type": "commit", "ref": sha, "note": note})
                hit = next((h for h in hs["detector_hits"]
                            if h["pattern_id"] in spec["missing_patterns"]), None)
                if hit:
                    evidence.append({"type": "detector", "ref": hit["ref"],
                                     "note": "lead confirmed against the code"})
                for ref in spec.get("catalog", []):
                    evidence.append({"type": "catalog", "ref": ref,
                                     "note": "listed in the service catalog as "
                                             "depending on this component"})
                item = {k: v for k, v in spec.items()
                        if k not in ("symbol", "anchor", "catalog", "also_cite")}
                # the symbol's span, clamped to the file: a range past the end
                # of the file is rejected by the validator (#25)
                total = len((repo / hs["file"]).read_text(encoding="utf-8").splitlines())
                item["location"] = {"file": hs["file"], "symbol": spec["symbol"],
                                    "lines": f"{line}-{min(line + 12, total)}"}
                item["evidence"] = evidence
                built.append(item)
            doc = {"hotspot_id": hs["id"], "file": hs["file"], "findings": built}
            proc = subprocess.run(
                [sys.executable, str(scripts / "save_finding.py"),
                 "--repo", str(repo), "--id", hs["id"]],
                input=json.dumps(doc), capture_output=True, text=True, cwd=str(repo), env=env)
            if proc.returncode != 0:
                raise SystemExit(f"save_finding failed: {proc.stderr}")

        for hs in data["hotspots"]:
            path = repo / ".thunderstruck" / "findings" / f"{hs['id']}.json"
            if not path.is_file():
                proc = subprocess.run(
                    [sys.executable, str(scripts / "save_finding.py"),
                     "--repo", str(repo), "--id", hs["id"]],
                    input=json.dumps({
                        "hotspot_id": hs["id"], "file": hs["file"], "findings": [],
                        "notes": "no credible production failure mode found"}),
                    capture_output=True, text=True, cwd=str(repo), env=env)
                if proc.returncode != 0:
                    raise SystemExit(f"save_finding failed: {proc.stderr}")

        validation = subprocess.run(
            [sys.executable, str(scripts / "validate.py"), "--repo", str(repo)],
            capture_output=True, text=True, cwd=str(repo), env=env)
        if validation.returncode != 0:
            raise SystemExit(
                "the sample findings no longer satisfy validate.py — fix the "
                f"canned findings in this script:\n{validation.stdout}")

        _run([sys.executable, str(scripts / "report.py"), "--repo", str(repo)], repo, env)
        # the fixture's last commit: no pinned date can predate what was scanned
        day = _run(["git", "-C", str(repo), "log", "-1", "--format=%cs"], repo, env).stdout.strip()
        report = (repo / ".thunderstruck" / "report.md").read_text(encoding="utf-8")
        if "## Service context" not in report:
            raise SystemExit("the fixture's service context was not fetched (the stub "
                             "catalog failed or timed out); the sample needs it")
        report = pin_dates(report, day)

    header = (
        "<!-- Generated by scripts/gen_sample_report.py from the test fixture in\n"
        "     tests/fixtures/build_fixture.py. Every finding below passed the real\n"
        "     validator: each ref resolved to a file:line, a commit in that repo,\n"
        "     a detector hit or a catalog edge. Refs link to a placeholder host\n"
        "     (github.example.com), so the links do not resolve; in a real scan they\n"
        "     open the cited lines at the scanned commit. Dates are fixed to the\n"
        "     fixture's last commit so the file is byte-reproducible; CI fails when\n"
        "     it is stale. Regenerate with:  uv run scripts/gen_sample_report.py\n"
        "     Check with:       uv run scripts/gen_sample_report.py --check -->\n\n")
    return header + report


REGENERATE = "uv run scripts/gen_sample_report.py"
DIFF_LINES = 80


def check(dest: Path, body: str) -> tuple[bool, str]:
    """Compare the committed sample with a fresh generation."""
    if not dest.is_file():
        return False, f"{dest.name} does not exist — regenerate with: {REGENERATE}"
    current = dest.read_text(encoding="utf-8")
    if current == body:
        return True, f"{dest.name} is up to date"
    diff = list(difflib.unified_diff(current.splitlines(), body.splitlines(),
                                     f"{dest.name} (committed)", f"{dest.name} (generated)",
                                     lineterm=""))
    shown = diff[:DIFF_LINES]
    if len(diff) > DIFF_LINES:
        shown.append(f"… {len(diff) - DIFF_LINES} more diff line(s)")
    return False, "\n".join([f"{dest.name} is stale:", *shown, f"regenerate with: {REGENERATE}"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gen_sample_report.py")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    dest = ROOT / "examples" / "sample-report.md"
    body = generate()
    if args.check:
        ok, message = check(dest, body)
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    print(f"wrote {dest} ({len(body.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
