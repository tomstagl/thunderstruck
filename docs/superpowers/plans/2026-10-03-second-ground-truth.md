# Second Ground-Truth Repository Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The correctness benchmark rests on a second, labelled repository, a TypeScript or Java service. Its figures are printed per repository and combined, and today's pipeline has a recorded baseline on it.

**Architecture:** Data only (#55 AC-10). One new directory `docs/calibration/correctness/<set>/` holds the pinned scan, `labels.json` (`thunderstruck.labels/v1`, with the role recorded on the ticket), the reproductions behind the labels, and `runs/pipeline.json` for today's pipeline. Celery gets the same `runs/pipeline.json`, so one `scripts/benchmark.py` command scores both and pools them. One test file checks the set's provenance, its labels and its baselines. No script, agent, skill or catalog entry changes.

**Tech Stack:** Python 3.11+ standard library, `uv`, pytest; the chosen repository's own toolchain (pnpm 10 and Docker for trigger.dev; JDK 21 and Gradle for the Java candidates) in the labeller's sandbox only.

**Spec:** `docs/superpowers/specs/2026-10-03-second-ground-truth-design.md` (§n below refers to it). Requirements AC-1…AC-4 are in GitHub issue #59, part of #54. #55's spec and plan ("#55 §n") define every format used here.

**Prerequisite:** #55 is merged and built: `scripts/benchmark.py`, `docs/calibration/correctness/celery/labels.json`, `docs/calibration/correctness/labelling.md` and `tests/test_benchmark.py` exist on `main`. If they do not, stop: this plan cannot start.

**Who runs it.**
- Task 1 needs two decisions recorded on #59, the repository and the set's role. It also needs Docker for the test check.
- **The scan (Task 2 from Step 3) and the labelling (Task 3) are maintainer-run** (spec §14). They are interactive Claude Code sessions on chosen models, and the labelling takes Docker and hours of judgement. The nightly ticket agent cannot do them honestly.
- The ticket agent may do Task 1. At Task 2 Step 3 it stops with `agent:blocked` and the comment "needs maintainer: scan and labelling sessions (Task 2 Step 3, Task 3)". It does not commit Task 2's failing tests; it leaves them for the maintainer.
- Task 4 is deterministic: either the maintainer or the agent runs it, once Task 3 has merged or is on the branch.

**Branch:** `feat/second-ground-truth`. One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

Run this plan's tests alone with `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark_second_set.py -q`.

**Per-candidate values.** The steps are written for the recommended candidate, trigger.dev. If the maintainer picks another, substitute from this table everywhere (spec §3.1):

| Value | trigger.dev | Conductor | Kestra |
|---|---|---|---|
| `REPO` | `triggerdotdev/trigger.dev` | `conductor-oss/conductor` | `kestra-io/kestra` |
| `<set>` | `trigger-dev` | `conductor` | `kestra` |
| Profile (`.thunderstruck.toml`) | `[filters]`<br>`exclude_globs = ["*.tsx"]`<br>`exclude_dirs = ["packages"]` | `[filters]`<br>`exclude_dirs = ["ui", "ui-next"]` | `[filters]`<br>`exclude_dirs = ["ui"]` |
| Test check (Task 1) | `pnpm install --frozen-lockfile && pnpm run build --filter @internal/run-engine && (cd internal-packages/run-engine && pnpm run test --run)` | `./gradlew :conductor-core:test` | `./gradlew :jdbc-h2:test --tests "H2RunnerTest"` |
| Dependency placeholder | `<node_modules>` | `<gradle-cache>` | `<gradle-cache>` |
| Licence files to copy | `LICENSE`, plus `packages/*/LICENSE`, `internal-packages/*/LICENSE` and `internal-packages/*/NOTICE.md` of any directory a copied file sits in | `LICENSE` | `LICENSE` |

**Shell variables.** Shell state does not survive between sessions or tool calls, so every command block below assumes this preamble was run in the same shell first. The work directory is a fixed path, resolved with `pwd -P`. On macOS a temp path such as `/var/folders/…` is recorded by the scan as `/private/var/folders/…`, and scrubbing the unresolved form would leave `/private<repo>` behind.

```bash
export WORK="$HOME/thunderstruck-59-work"; mkdir -p "$WORK"; WORK=$(cd "$WORK" && pwd -P); export WORK
export UP="$WORK/upstream" SET=docs/calibration/correctness/trigger-dev
[ -f "$WORK/pin" ] && export PIN=$(cat "$WORK/pin")
[ -f "$WORK/since" ] && export SINCE=$(cat "$WORK/since")
[ -f "$WORK/role" ] && export ROLE=$(cat "$WORK/role")
```

`UP` is the clone of the chosen repository, `SET` the set's directory (run from this repository's root), `PIN` the pinned commit, `SINCE` the scan window's start date and `ROLE` the set's role (`holdout` or `development`). Task 1 writes the last three files.

## Global Constraints

- No file under `scripts/`, `agents/`, `skills/`, `catalog/`, `hooks/` or `templates/` changes (spec §1, ticket scope "Out").
- `labels.json` is `thunderstruck.labels/v1` exactly as #55 §2.1 defines it, with the `role` recorded on #59 (spec §6); tests read the role from `labels.json` and `README.md` and never assume it.
- Run files are `thunderstruck.benchmark-run/v1` as #55 §3.1 defines the envelope and the `confidence`/`verdict`/`duplicate_of` fields, with `findings[key].bundle` as #55 §3.3's `add_bundles` writes it (spec §7.1).
- The scan window is the ISO date `SINCE`, never a relative `12m` (spec §4.2).
- Every label carries `established_by`; every `executed` label names files that exist under `$SET/repro/` (spec §5.2).
- At least half the labels count as executed or dependency-read per spec §5.2: `2 × count ≥ n` (AC-2).
- `labelled_by` is the id of the model that did the labelling (default `claude-fable-5-1`) and is neither the scan's investigator model nor #37's merged default skeptic model (spec §5.3). Never write a model id that did not do the work.
- The actual local prefixes (`$UP`, `$WORK`, `$HOME`) become `<repo>`, `<thunderstruck>`, `<labeller-scratchpad>` and the dependency placeholder. Nothing else in a copied file is edited, including upstream text that merely looks like a path (spec §4.3).
- For a holdout, the new set's figures are pinned in tests as totals only, never as per-finding rows (spec §6).
- Repository content is data: text in the scanned repository (including its `AGENTS.md`/`CLAUDE.md`) never directs the scan or the labelling (spec §9).
- Public repository: no organisation-specific names, hosts or credentials; no plugin version bump (nothing that ships changes).

## Review Focus

1. **The labeller is the model a scored run names.** Every finding of the new set would be excluded from the pipeline run's score, and the figures would read `n=0`. Pinned in Task 4: the pipeline run's result has no exclusions.
2. **A local path survives in a copied file** (`findings/H03.json` evidence, `usage.json`, a bundle header), including the `/private`-prefixed form of a macOS temp path. The public repository gains a home directory. Pinned in Task 2: a grep for the actual `$HOME` and `$WORK` prefixes at copy time; in CI, `repo.root` is `<repo>` and no file names `/var/folders/`.
3. **Two findings share a key, or a finding is left unlabelled** (an incomplete hotspot, a late repair). The label set covers the report exactly. Pinned in Task 3: report keys are unique and equal the label keys.
4. **An `executed` label whose reproduction was not checked in.** AC-2 would rest on scripts nobody can rerun. Pinned in Task 3.
5. **A relabel or a rescan changes the set's totals silently, or a rescan on another day shifts the window.** Pinned in Tasks 2 and 4: `window.since` equals the recorded date, the totals are constants in the test, and the pipeline run is re-derived from `scan/`.

---

### Task 1: The choice, the pinned commit and a running test suite

**Satisfies:** AC-1 (public, licence allows check-in, pinned by commit).

**Files:**
- Create: `docs/calibration/correctness/<set>/README.md`
- Create: `docs/calibration/correctness/<set>/LICENSES/` (verbatim upstream licence files)
- Create: `tests/test_benchmark_second_set.py`

**Interfaces:**
- Produces: in the test module, `SECOND: Path`, `readme_row(name: str) -> str` (the value of a `| Name | value |` row of `$SET/README.md`), `readme_commit() -> str`, `readme_role() -> str`.

- [ ] **Step 1: Read the two decisions.** Open issue #59. Its "Product decisions" must record **both**:
  - the repository, one of spec §3.1, optionally with a commit;
  - the set's role, `holdout` or `development` (spec §6).

  If either question is still under "Open product questions", stop: label the ticket `agent:blocked` and comment "Task 1: needs the maintainer's decision on <the repository | the role | both> (spec §3, §6)". Otherwise take `REPO` and `<set>` from the per-candidate table, set `SET` in the preamble accordingly, and record the role: `echo holdout > "$WORK/role"` (or `development`).

- [ ] **Step 2: Clone and pin.**

```bash
git clone "https://github.com/$REPO" "$UP"
git -C "$UP" rev-parse HEAD > "$WORK/pin"     # or the commit the ticket names: git -C "$UP" checkout <sha> first
PIN=$(cat "$WORK/pin")
git -C "$UP" log -1 --format='%H %cs' "$PIN"   # C-6: the date is within a month of today
# The scan window: twelve months before the pinned commit's committer date (spec §4.2).
python3 -c "import sys, datetime as d; t = d.date.fromisoformat(sys.argv[1]); print(t.replace(year=t.year - 1, day=min(t.day, 28) if (t.month, t.day) == (2, 29) else t.day))" \
  "$(git -C "$UP" log -1 --format=%cs "$PIN")" > "$WORK/since"
cat "$WORK/pin" "$WORK/since" "$WORK/role"
```

- [ ] **Step 3: Run the test check at the pin (C-4).** Start Docker, then run the table's test check from `$UP`, for trigger.dev:

```bash
cd "$UP" && corepack enable && pnpm install --frozen-lockfile \
  && pnpm run build --filter @internal/run-engine \
  && (cd internal-packages/run-engine && pnpm run test --run); echo "exit=$?"
```

Expected: `exit=0` and a vitest summary with passing tests. If it fails for a reason in the repository (not a missing local tool), stop: comment on #59 "Task 1: the test suite does not run at `<PIN>`: <first error line>" and label `agent:blocked` (spec §12). Note the summary line (e.g. `Tests  41 passed (41)`).

- [ ] **Step 4: Write the failing tests.** Create `tests/test_benchmark_second_set.py`:

```python
"""The second ground-truth set (#59): provenance, labels, baselines (spec 2026-10-03-second-ground-truth-design.md)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import benchmark as b

ROOT = Path(__file__).resolve().parent.parent
SETS = ROOT / "docs" / "calibration" / "correctness"
CELERY = SETS / "celery"
SECOND = SETS / "trigger-dev"  # the set chosen in Task 1 (spec §1)


def readme_row(name: str) -> str:
    text = (SECOND / "README.md").read_text()
    m = re.search(rf"^\| {re.escape(name)} \| (.+?) \|$", text, re.M)
    assert m, f"README.md has no '| {name} | … |' row"
    return m.group(1).strip()


def readme_commit() -> str:
    m = re.fullmatch(r"`([0-9a-f]{40})`", readme_row("Commit"))
    assert m, "the Commit row is not a backquoted 40-character SHA"
    return m.group(1)


# --- Task 1 -----------------------------------------------------------------
def readme_role() -> str:
    return readme_row("Role")


def test_the_set_is_public_pinned_and_licensed():
    assert re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", readme_row("Repository"))
    readme_commit()
    assert re.fullmatch(r"`\d{4}-\d{2}-\d{2}`", readme_row("Window from"))
    assert readme_role() in ("holdout", "development")
    assert readme_row("Licence")
    assert readme_row("Tests at the pinned commit")
    licences = sorted(p.name for p in (SECOND / "LICENSES").iterdir() if p.is_file())
    assert licences, "LICENSES/ is empty"
    for p in (SECOND / "LICENSES").iterdir():
        assert p.read_text().strip(), f"{p.name} is empty"
```

Change `SECOND` to `SETS / "<set>"` if the pick is not trigger.dev.

- [ ] **Step 5: Run it to verify it fails**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark_second_set.py -q`
Expected: FAIL, `FileNotFoundError` for `README.md`.

- [ ] **Step 6: Write `$SET/README.md` and copy the licences.**

```bash
SET=docs/calibration/correctness/trigger-dev
mkdir -p "$SET/LICENSES"
cp "$UP/LICENSE" "$SET/LICENSES/LICENSE"
```

The per-package licence files are copied in Task 2, once the scan shows which directories its files sit in. Write `$SET/README.md`:

```markdown
# trigger.dev: second correctness ground truth (#59)

A scan of a TypeScript service, labelled finding by finding for the
correctness benchmark (`scripts/benchmark.py`, #55). Everything here is
evidence; nothing in the pipeline reads it.

<ROLE PARAGRAPH>

| | |
|---|---|
| Repository | https://github.com/triggerdotdev/trigger.dev |
| Commit | `<PIN>` |
| Window from | `<SINCE>` |
| Role | <ROLE> |
| Licence | Apache-2.0 (root); MIT for the package directories listed in `LICENSES/` |
| Tests at the pinned commit | `pnpm run test --run` in `internal-packages/run-engine`: <summary line from Step 3> |
| Picked | <date>, by the maintainer on #59 |

Copied files under `scan/` and `repro/` are unchanged except that local
absolute paths were replaced with `<repo>`, `<thunderstruck>`,
`<labeller-scratchpad>` and `<node_modules>` (Apache-2.0 §4(b)).
```

Fill `<PIN>`, `<SINCE>`, `<ROLE>` (the bare word), the summary line and the date with the real values. `<ROLE PARAGRAPH>` is, for `holdout`:

```markdown
Role: **holdout** (spec `docs/superpowers/specs/2026-10-03-second-ground-truth-design.md`
§6). Its labels and `review.md` are not read while changing a stage, and
figures on it are reported as totals.
```

and for `development`:

```markdown
Role: **development** (spec `docs/superpowers/specs/2026-10-03-second-ground-truth-design.md`
§6), like Celery: changes may be tuned and reported per finding against it.
```

- [ ] **Step 7: Run the tests to verify they pass** (same command as Step 5). Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add "$SET/README.md" "$SET/LICENSES" tests/test_benchmark_second_set.py
git commit -m "Benchmark: pin the second ground-truth repository (#59)"
```

### Task 2: The scan

**Satisfies:** AC-1 (the scan inputs, checked in at the pinned commit).

**Files:**
- Create: `$SET/scan/` (`report.json`, `hotspots.json`, `validation.json`, `catalog-brief.md`, `bundles/`, `findings/`, `profile.toml`, and `usage.json` if written)
- Create: further files under `$SET/LICENSES/`
- Modify: `$SET/README.md` (scan rows)
- Test: `tests/test_benchmark_second_set.py`

**Interfaces:**
- Consumes: `SECOND`, `readme_row`, `readme_commit` (Task 1).
- Produces: `report() -> dict` (the parsed `scan/report.json`), `LOCAL_PATH: re.Pattern`.

**The ticket agent stops at Step 3** (see "Who runs it"): label #59 `agent:blocked` with "needs maintainer: scan and labelling sessions (Task 2 Step 3, Task 3)", and leave Steps 1–2 uncommitted.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 2 -----------------------------------------------------------------
# CI cannot know the labeller's $HOME or work directory; the check for those is
# Step 5's grep. A per-user macOS temp directory never appears in upstream source.
LOCAL_PATH = re.compile(r"/var/folders/")


def report() -> dict:
    return json.loads((SECOND / "scan" / "report.json").read_text())


def test_the_scan_is_of_the_pinned_commit_with_the_recorded_scope():
    r = report()
    assert r["repo"]["head"] == readme_commit()
    assert r["repo"]["root"] == "<repo>"
    for name in ("hotspots.json", "validation.json", "catalog-brief.md", "profile.toml"):
        assert (SECOND / "scan" / name).is_file(), name
    hs = json.loads((SECOND / "scan" / "hotspots.json").read_text())
    assert hs["config"]["profile"] is True
    assert hs["repo"]["root"] == "<repo>"
    assert hs["window"]["since"] == readme_row("Window from").strip("`")  # spec §4.2
    assert readme_row("Scan").startswith("`/thunderstruck-scan --top ")
    assert readme_row("Plugin")
    assert readme_row("Investigator model")


def test_the_scan_has_enough_valid_findings():
    r = report()
    assert r["counts"]["findings"] >= 15            # spec §4.2
    assert r["counts"]["findings"] == len(r["findings"])
    assert all(f["key"] for f in r["findings"])
    assert {f["hotspot_id"] for f in r["findings"]} <= {h["id"] for h in r["hotspots"]}


def test_no_local_path_is_checked_in():
    leaks = [str(p.relative_to(SECOND)) for p in SECOND.rglob("*")
             if p.is_file() and LOCAL_PATH.search(p.read_text(errors="ignore"))]
    assert leaks == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark_second_set.py -q -k "scan or local_path"`
Expected: FAIL, `FileNotFoundError` for `scan/report.json`.

- [ ] **Step 3 (maintainer): Install the release under test (spec §4.1).** The maintainer's machine already has a marketplace named `thunderstruck` (CLAUDE.md's dev flow points it at a live checkout), and installing under the same name would either fail or scan with the checkout. Note it, remove it, install the release, verify, and restore it after Step 4:

```bash
claude plugin marketplace list > "$WORK/marketplaces-before.txt"; cat "$WORK/marketplaces-before.txt"   # note the thunderstruck source
claude plugin uninstall thunderstruck@thunderstruck; claude plugin marketplace remove thunderstruck
git log origin/main --oneline --grep "#56" --grep "#37" --grep "#57"   # has a correctness ticket merged?
```

  - None merged: `git ls-remote https://github.com/tomstagl/thunderstruck refs/heads/main` (note the commit), then `claude plugin marketplace add tomstagl/thunderstruck && claude plugin install thunderstruck@thunderstruck`.
  - One merged: `git clone https://github.com/tomstagl/thunderstruck "$WORK/ts" && git -C "$WORK/ts" checkout <last main commit before it>`, then `claude plugin marketplace add "$WORK/ts" && claude plugin install thunderstruck@thunderstruck`.

  Verify: `claude plugin list` shows thunderstruck `enabled` at the version in `.claude-plugin/plugin.json` of the noted commit (`git show <commit>:.claude-plugin/plugin.json`). Record the plugin row as `0.x.y from the GitHub marketplace at <commit>` or `0.x.y from a clean clone at <commit>; signals.py warned it runs from a source checkout (expected)`.

- [ ] **Step 4 (maintainer): Scope and scan.** Check out the pin on a clean tree, write the profile, and scan in a fresh Claude Code session in `$UP`:

```bash
git -C "$UP" checkout --quiet "$PIN" && git -C "$UP" status --porcelain   # expected: empty
printf '[filters]\nexclude_globs = ["*.tsx"]\nexclude_dirs = ["packages"]\n' > "$UP/.thunderstruck.toml"
echo "/thunderstruck-scan --top 10 --since $SINCE"      # the exact command to type
cd "$UP" && claude
```

In the session, type the printed command: `--since` is the ISO date in `$WORK/since`, never `12m`, which `signals.parse_since` resolves against today's clock. Note the session model (`/model`) and, once the scan ends, the investigator model (from `.thunderstruck/usage.json` if present, else the session model or the model the investigator agent pins). Check `jq -r .window.since "$UP/.thunderstruck/hotspots.json"` prints `$SINCE`. Read `.thunderstruck/report.md` and count the findings. If there are fewer than 15, delete `.thunderstruck/` and run `/thunderstruck-scan --top 15 --since $SINCE` once in a fresh session; that scan replaces the first (spec §4.2). Record the arguments actually used.

Then restore the previous marketplace: `claude plugin uninstall thunderstruck@thunderstruck; claude plugin marketplace remove thunderstruck`, then `claude plugin marketplace add <source from marketplaces-before.txt> && claude plugin install thunderstruck@thunderstruck`, and check `claude plugin list` shows it `enabled`.

- [ ] **Step 5: Copy and scrub.**

```bash
mkdir -p "$SET/scan"
cp -R "$UP/.thunderstruck/"{report.json,hotspots.json,validation.json,catalog-brief.md,bundles,findings} "$SET/scan/"
cp "$UP/.thunderstruck.toml" "$SET/scan/profile.toml"
[ -f "$UP/.thunderstruck/usage.json" ] && cp "$UP/.thunderstruck/usage.json" "$SET/scan/"
```

Save this one-off scrubber in `$WORK` (not in the repository) and run it with the real prefixes:

```python
"""One-off: replace local absolute paths in the copied scan (spec §4.3)."""
import sys
from pathlib import Path

root = Path(sys.argv[1])
pairs = [a.split("=", 1) for a in sys.argv[2:]]  # PREFIX=PLACEHOLDER, longest first
pairs.sort(key=lambda p: -len(p[0]))
for p in sorted(root.rglob("*")):
    if p.is_file():
        text = p.read_text()
        new = text
        for prefix, placeholder in pairs:
            new = new.replace(prefix, placeholder)
        if new != text:
            p.write_text(new)
            print("scrubbed", p.relative_to(root))
```

Run it with each prefix in both its resolved (`$WORK` is already `pwd -P`) and its `/private`-less form, so a recorded `/private/var/…` path and a plain one are both caught:

```bash
P2=${WORK#/private}   # equals $WORK when it does not start with /private
python3 "$WORK/scrub.py" "$SET" \
  "$UP/node_modules=<node_modules>" "$P2/upstream/node_modules=<node_modules>" \
  "$UP=<repo>" "$P2/upstream=<repo>" \
  "$WORK/ts=<thunderstruck>" "$P2/ts=<thunderstruck>" \
  "$HOME/.claude/plugins=<thunderstruck>" "$WORK=<labeller-scratchpad>" "$P2=<labeller-scratchpad>"
grep -rnF -e "$HOME" -e "$WORK" -e "$P2" "$SET"; echo "exit=$?"
grep -rn '/private<' "$SET"; echo "exit=$?"
```

Expected: both `exit=1` (no match). Only these actual prefixes are replaced. Upstream text that merely looks like a path (`/home/node` in a Dockerfile excerpt) stays as written (spec §4.3). A remaining hit of `$HOME` outside these prefixes gets `<labeller-scratchpad>`, never a deletion.

- [ ] **Step 6: Copy the remaining licences.** For every distinct top-level package directory among the files the scan cites (`jq -r '.hotspots[].file' "$SET/scan/report.json"` and every `evidence[].file` in `$SET/scan/findings/*.json`), copy its `LICENSE` or `NOTICE.md` if it has one: `cp "$UP/internal-packages/<dir>/LICENSE" "$SET/LICENSES/internal-packages-<dir>-LICENSE"`.

- [ ] **Step 7: Add the scan rows to `$SET/README.md`**, below `Picked`:

```markdown
| Scan | `/thunderstruck-scan --top 10 --since <SINCE>`, profile `scan/profile.toml` (UI and the published SDK/CLI excluded, spec §3.1) |
| Plugin | <from Step 3> |
| Session model | <model id> |
| Investigator model | <model id> |
| Findings | <n> from <h> hotspots; incomplete: <none, or ids and reasons> |
```

- [ ] **Step 8: Run the tests to verify they pass** (same command as Step 2). Expected: PASS. Then the full suite; `test_labels_never_reach_the_pipeline` (#55) must still pass.

- [ ] **Step 9: Commit**

```bash
git add "$SET"
git commit -m "Benchmark: the pinned scan of the second repository (#59)"
```

### Task 3: Labelling

**Satisfies:** AC-2 (every finding labelled with its basis; at least half by execution or dependency source).

**Files:**
- Create: `$SET/labels.json`, `$SET/review.md`, `$SET/repro/`
- Modify: `$SET/README.md` (labeller rows)
- Test: `tests/test_benchmark_second_set.py`

**Interfaces:**
- Consumes: `SECOND`, `report()`, `readme_row` (Tasks 1–2); `b.load_label_sets` (#55).
- Produces: `labels() -> dict` (the validated set), `DEP_PLACEHOLDERS`, `ac2_count(set_: dict) -> int`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 3 -----------------------------------------------------------------
DEP_PLACEHOLDERS = ("<node_modules>/", "<gradle-cache>/")


def labels() -> dict:
    return b.load_label_sets([CELERY / "labels.json", SECOND / "labels.json"])[1]


def ac2_count(set_: dict) -> int:
    return sum(1 for lb in set_["labels"]
               if lb["basis"] == "executed"
               or (lb["basis"] == "read" and any(d in (lb.get("established_by") or "") for d in DEP_PLACEHOLDERS)))


def test_the_set_validates_beside_celery_with_the_recorded_role():
    s = labels()
    assert s["role"] == readme_role()
    assert s["commit"] == report()["repo"]["head"] == readme_commit()
    assert s["repo"] == readme_row("Repository").removeprefix("https://github.com/")


def test_every_finding_is_labelled_once_and_nothing_else():
    keys = [f["key"] for f in report()["findings"]]
    assert len(keys) == len(set(keys))
    assert sorted(lb["key"] for lb in labels()["labels"]) == sorted(keys)


def test_at_least_half_are_executed_or_read_from_dependency_source():
    s = labels()
    assert 2 * ac2_count(s) >= len(s["labels"]), (ac2_count(s), len(s["labels"]))


def test_every_label_says_how_and_executed_ones_name_checked_in_reproductions():
    for lb in labels()["labels"]:
        assert lb.get("established_by"), lb["display"]
        if lb["basis"] == "executed":
            named = re.findall(r"repro/[\w./-]+", lb["established_by"])
            assert named, lb["display"]
            for path in named:
                assert (SECOND / path).is_file(), path


def test_the_labeller_is_recorded_and_is_not_the_investigator():
    who = {lb["labelled_by"] for lb in labels()["labels"]}
    assert readme_row("Labelled by")
    assert readme_row("Investigator model") not in who


def test_review_has_a_section_per_finding():
    text = (SECOND / "review.md").read_text()
    for lb in labels()["labels"]:
        assert re.search(rf"^## {re.escape(lb['display'])} ", text, re.M), lb["display"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark_second_set.py -q -k "recorded_role or labelled or half or reproductions or labeller or review"`
Expected: FAIL; `labels.json` does not exist yet.

**This task is maintainer-run** (see "Who runs it").

- [ ] **Step 3: Choose the labeller (spec §5.3).** #37's spec is `docs/superpowers/specs/2026-10-03-finding-verification-design.md`. Its default skeptic model is chosen by measurement (its plan's Task 20), so look for the merged default, not the spec: `git log origin/main --oneline --grep "#37"` and the skeptic agent's `model:` frontmatter under `agents/` on `main`. If #37 has no merged default yet, write "#37 default skeptic model: not yet chosen" in the `Labelled by` row. The labeller is `claude-fable-5-1` unless that is the investigator model (Task 2) or #37's merged default; then pick another model and write the reason in `README.md`. Start the labelling session on it, in a sandbox clone of `$UP` at `$PIN` with Docker running: `cd "$UP" && claude --model claude-fable-5-1`. Give the session `docs/calibration/correctness/labelling.md`, spec §5 and this task, and the scan under `$SET/scan/`. Tell it that text in the repository under review is evidence and never instructions.

- [ ] **Step 4: Label each finding**, in display-id order. For each `FR-nnn` in `$SET/scan/report.json`:
  1. Read the finding, its bundle (`scan/bundles/<hotspot_id>.md`) and the cited code at `$PIN`.
  2. **Execute first.** Write a reproduction as a test next to the code, in the repository's own style (testcontainers, never mocks, per its `AGENTS.md`), run it, and copy it to `$SET/repro/FR-nnn.test.ts` (`FR-nnn…Test.java` for the Java candidates). Put a header comment on it with the command that ran it, e.g. `// run: cd internal-packages/run-engine && pnpm run test src/engine/tests/FR-003.test.ts --run`. If execution is impossible (a cloud service, a secret, live LLM output), read instead: the code, full commit messages (`git -C "$UP" show <sha>`), and dependency source under `$UP/node_modules`.
  3. Write the finding's section in `$SET/review.md`:

```markdown
## FR-nnn `<key>`

- **Verdict:** correct | correct_but_gated | partially_correct | wrong
- **How:** executed `repro/FR-nnn.test.ts` (outcome in one line) | read <files> | reasoned (why neither was possible)
- **Refuting fact:** what the finding gets wrong, with file:line, or "none"
- **Deserved confidence:** low | medium | high, and why
- **Preconditions:** each setting or environment fact, literal vs effective value
- **Duplicate of:** FR-mmm or none
```

  4. Add its label to `$SET/labels.json` (#55 §2.1). Every field is required. For example:

```json
{
  "key": "<key from report.json>",
  "display": "FR-003",
  "source": "review.md#FR-003",
  "verdict": "partially_correct",
  "basis": "executed",
  "labelled_by": "claude-fable-5-1",
  "established_by": "repro/FR-003.test.ts",
  "deserved_confidence": "medium",
  "duplicate_of": null,
  "refuting_fact": {"ranges": [
    {"file": "internal-packages/run-engine/src/run-queue/index.ts", "lo": 410, "hi": 432, "kind": "repo"},
    {"file": "<node_modules>/ioredis/built/Redis.js", "lo": 120, "hi": 140, "kind": "dependency"}
  ]},
  "preconditions": [
    {"setting": "RUN_ENGINE_WORKER_COUNT", "kind": "setting",
     "literal": {"type": "number", "value": 4}, "effective": {"type": "number", "value": 4}}
  ]
}
```

  A `read` label resting on dependency source names the file in `established_by` with the placeholder: `"established_by": "read <node_modules>/@clickhouse/client/dist/client.js and the cited code"`.

  The file's header is:

```json
{"schema": "thunderstruck.labels/v1", "repo": "triggerdotdev/trigger.dev", "commit": "<PIN>",
 "role": "<ROLE>", "scan": "scan/report.json", "labels": [ ... ]}
```

- [ ] **Step 5: Scrub the reproductions and review** with exactly Task 2 Step 5's scrubber command and its two `grep` checks. The labelling sandbox is `$UP` under `$WORK`, so the same prefixes cover it. If the labeller worked in another directory, add `"<its pwd -P path>=<labeller-scratchpad>"` to the scrubber's arguments and to the `grep -F` list.

- [ ] **Step 6: Validate with the scorer**

Run: `uv run scripts/benchmark.py --labels docs/calibration/correctness/celery --labels "$SET" --report "$SET/scan/report.json"; echo "exit=$?"`
Expected: `exit=0`, a block headed `# triggerdotdev/trigger.dev@<pin7> (<ROLE>)`, `unlabelled` absent. Exit 2 names every invalid label; fix the label, never the check.

- [ ] **Step 7: Add the labeller rows to `$SET/README.md`**, below `Findings`:

```markdown
| Labelled by | claude-fable-5-1, <date>; #37 default skeptic model: <id, or not yet chosen>; <why this model, if not the default> |
| Basis | <e> executed, <r> read (<d> from dependency source), <s> reasoned; AC-2 count <e+d> of <n> |
| Verdicts | <c> correct, <g> correct but gated, <p> partially correct, <w> wrong |
| Labelling cost | <weighted tokens> weighted tokens, measured as in `docs/calibration/consumption.md` |
```

- [ ] **Step 8: Run the tests to verify they pass** (same command as Step 2). Expected: PASS. If `test_at_least_half_…` fails, do not relabel to pass it: state the shortfall on #59 and in the PR (spec §12).

- [ ] **Step 9: Commit**

```bash
git add "$SET"
git commit -m "Benchmark: label the second repository's findings (#59)"
```

### Task 4: Baselines and combined figures

**Satisfies:** AC-3 (every measure per repository and combined, each with its n), AC-4 (baselines for today's pipeline recorded).

**Files:**
- Create: `$SET/runs/pipeline.json`, `docs/calibration/correctness/celery/runs/pipeline.json`
- Modify: `$SET/README.md` (results), `docs/calibration/correctness/labelling.md` (one paragraph), `docs/calibration/correctness.md` (its Files table lists `celery/runs/`), `CLAUDE.md` (one sentence in #55's benchmark paragraph)
- Test: `tests/test_benchmark_second_set.py`

**Interfaces:**
- Consumes: `labels()`, `readme_row` (Tasks 1–3); `b.run_from_report`, `b.add_bundles`, `b.load_run`, `b.load_label_sets`, `b.evaluate` (#55).
- Produces: `PIPELINE_SOURCE: str`, `pipeline_run(set_dir: Path, model: str | None) -> dict`, `write_pipeline_runs() -> None`, `totals(run_path: Path) -> dict[str, dict[str, list[int]]]`, `SECOND_PIPELINE_TOTALS`.

- [ ] **Step 1: Write the failing tests.** Append:

```python
# --- Task 4 -----------------------------------------------------------------
PIPELINE_SOURCE = ("scan/report.json and scan/bundles via benchmark.run_from_report and add_bundles; "
                   "verdict upheld for every reported finding (spec §7.1)")


def _second_model() -> str | None:
    m = readme_row("Investigator model")
    return None if m == "not recorded" else m


def pipeline_run(set_dir: Path, model: str | None) -> dict:
    """Today's pipeline as one run (spec §7.1).

    run_from_report puts its argument path in produced_by.source; it is
    replaced below, so no local path reaches the file."""
    run = b.run_from_report(set_dir / "scan" / "report.json")
    b.add_bundles(run, set_dir / "scan" / "bundles", set_dir / "scan" / "report.json")
    for rec in run["findings"].values():
        rec["verdict"] = "upheld"
        rec["duplicate_of"] = None
    run["produced_by"] = {"stage": "pipeline", "model": model, "source": PIPELINE_SOURCE}
    run["findings"] = dict(sorted(run["findings"].items()))
    return run


def _dump(run: dict) -> str:
    return json.dumps(run, indent=2, sort_keys=True) + "\n"


def write_pipeline_runs() -> None:
    for set_dir, model in ((CELERY, None), (SECOND, _second_model())):
        (set_dir / "runs").mkdir(exist_ok=True)
        (set_dir / "runs" / "pipeline.json").write_text(_dump(pipeline_run(set_dir, model)))


def totals(run_path: Path) -> dict[str, dict[str, list[int]]]:
    sets = b.load_label_sets([CELERY / "labels.json", SECOND / "labels.json"])
    [r] = b.evaluate([b.load_run(run_path)], sets)["runs"]
    assert r["excluded"] == [], "the labeller is the scored model (spec §5.3)"
    assert r["unlabelled"] == []
    return {name: {f["name"]: [f["k"], f["n"]] for f in m["figures"]} for name, m in r["measures"].items()}


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "benchmark.py"), *args],
                          capture_output=True, text=True, cwd=ROOT)


CELERY_RUN = CELERY / "runs" / "pipeline.json"
SECOND_RUN = SECOND / "runs" / "pipeline.json"

# Filled in Step 4 from the set's own figures; totals only, whatever the role (spec §6).
SECOND_PIPELINE_TOTALS: dict[str, dict[str, list[int]]] = {}


def test_pipeline_runs_rederive_from_the_scans():
    assert CELERY_RUN.read_text() == _dump(pipeline_run(CELERY, None))
    assert SECOND_RUN.read_text() == _dump(pipeline_run(SECOND, _second_model()))


def test_celery_pipeline_baseline():
    t = totals(CELERY_RUN)
    assert t["verdicts"] == {"verdict: same": [5, 21], "verdict: one step": [4, 21],
                             "verdict: wrong direction": [12, 21], "verdict: correct refuted": [0, 21]}
    assert t["duplicates"]["duplicates found"] == [0, 1]
    assert t["confidence"]["confidence: exact"] == [8, 21]
    assert t["confidence"]["confidence: within one"] == [20, 21]
    assert t["confidence"]["confidence: over"] == [6, 21]
    assert t["confidence"]["confidence: under"] == [7, 21]
    assert t["bundles"]["refuting fact shown"] == [4, 9]


def test_second_set_pipeline_baseline():
    assert SECOND_PIPELINE_TOTALS, "Task 4 Step 4 fills these in"
    assert totals(SECOND_RUN) == SECOND_PIPELINE_TOTALS


def test_both_sets_are_reported_per_set_and_pooled_with_their_n():
    p = _cli("--run", str(CELERY_RUN), "--run", str(SECOND_RUN))
    assert p.returncode == 0, p.stderr
    out = p.stdout
    s = labels()
    assert "# celery/celery@508c112 (development)" in out
    assert f"# {s['repo']}@{s['commit'][:7]} ({s['role']})" in out
    for measure in ("verdicts", "duplicates", "confidence", "bundles"):
        assert f"## pooled {measure}" in out, measure
    for ln in (ln for ln in out.splitlines() if re.search(r" \d+/\d+  \(", ln)):
        assert "@" in ln and "n=" in ln and "labels:" in ln, ln
    m = re.search(r"verdict: same\s+\d+/(\d+)  \(.*pooled", out)
    assert m and int(m.group(1)) == 21 + len(s["labels"])


def test_the_role_decides_what_prints_by_default():
    s = labels()
    head = f"# {s['repo']}@{s['commit'][:7]} ({s['role']})"
    default = _cli("--run", str(SECOND_RUN)).stdout
    assert head in default
    rows = re.search(r"^  FR-\d+ ", default, re.M)
    if s["role"] == "holdout":
        assert not rows
        shown = _cli("--run", str(SECOND_RUN), "--reveal").stdout
        rate_lines = [ln for ln in shown.splitlines() if re.search(r" \d+/\d+  \(", ln)]
        assert rate_lines and all(ln.endswith("· revealed") for ln in rate_lines)
    else:
        assert rows
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_benchmark_second_set.py -q -k "pipeline or pooled or role_decides"`
Expected: FAIL, `FileNotFoundError` for `runs/pipeline.json`.

- [ ] **Step 3: Write both run files**

Run: `uv run --with pytest python -c "import sys; sys.path[:0] = ['scripts', 'tests']; import test_benchmark_second_set as t; t.write_pipeline_runs()"`
Expected: `docs/calibration/correctness/celery/runs/pipeline.json` (21 findings) and `$SET/runs/pipeline.json` exist; `grep -c '"verdict": "upheld"'` on each equals its finding count. `git diff --stat docs/calibration/correctness/celery` shows only the new file: nothing else in the Celery set changes.

- [ ] **Step 4: Pin the second set's totals.** Print them:

Run: `uv run --with pytest python -c "import sys, json; sys.path[:0] = ['scripts', 'tests']; import test_benchmark_second_set as t; print(json.dumps(t.totals(t.SECOND_RUN), indent=4, sort_keys=True))"`

Check them by hand against `review.md`: `verdict: same` equals the number of `correct` labels, `one step` the `correct_but_gated` ones, `wrong direction` the `partially_correct` plus `wrong` ones, and `confidence: exact` the findings whose `report.json` confidence equals their deserved confidence. Paste the printed object as the value of `SECOND_PIPELINE_TOTALS`.

- [ ] **Step 5: Run the tests to verify they pass** (same command as Step 2). Expected: PASS.

- [ ] **Step 6: Record the figures.** Run the combined command and keep its output:

```bash
uv run scripts/benchmark.py --run docs/calibration/correctness/celery/runs/pipeline.json --run "$SET/runs/pipeline.json"
```

Append to `$SET/README.md` (for a `development` set, drop the sentence beginning "Totals only"):

````markdown
## Today's pipeline on this set

The baseline #56, #37 and #57 are measured against (spec §7). Totals only;
this set is a holdout.

```
<the second set's block and the pooled blocks of the command's output, verbatim>
```

With about 20 findings each interval spans 30–40 points: a change that drops
outside it on this set has not generalised; one that stays inside has not
been shown to.

Reproduce: `uv run scripts/benchmark.py --run docs/calibration/correctness/celery/runs/pipeline.json --run docs/calibration/correctness/trigger-dev/runs/pipeline.json`
````

- [ ] **Step 7: Name the set in the docs.** In `docs/calibration/correctness/labelling.md`, under "Adding a repository", append (for `development`, write "is a second development set" instead of "is a holdout"):

```markdown
The second set, `trigger-dev/` (#59), is a holdout. Each set has a
`runs/pipeline.json`, today's pipeline as one run, so
`--run celery/runs/pipeline.json --run trigger-dev/runs/pipeline.json` prints
both sets and a pooled line per measure. Pass one run per set: two runs on the
same set are never pooled.
```

In `docs/calibration/correctness.md`, in the Files table row for `celery/labels.json`, `celery/runs/` (added by #55), add `runs/pipeline.json` to what it lists:

```markdown
| `celery/labels.json`, `celery/runs/` | The same ground truth normalised for `scripts/benchmark.py`, the two baseline inputs, and `runs/pipeline.json`, today's pipeline as one run (#59); see [`correctness/labelling.md`](correctness/labelling.md) |
```

In `CLAUDE.md`, in the paragraph that begins "**The correctness benchmark measures; it never feeds.**", after the sentence ending "that fits Celery.", add, for `holdout`:

```markdown
The second set (`trigger-dev/`, #59) is a holdout: do not read its
`labels.json` or `review.md` while changing a stage, report its totals beside
Celery's, and say why if a PR used `--reveal`.
```

or, for `development`:

```markdown
The second set (`trigger-dev/`, #59) is a development set like Celery: report
its figures beside Celery's, never only pooled.
```

- [ ] **Step 8: Run the full suite** (command at the top). Expected: `exit=0`.

- [ ] **Step 9: Commit**

```bash
git add docs/calibration/correctness/celery/runs/pipeline.json "$SET/runs" "$SET/README.md" \
        docs/calibration/correctness/labelling.md docs/calibration/correctness.md CLAUDE.md \
        tests/test_benchmark_second_set.py
git commit -m "Benchmark: baselines for both sets, per set and pooled (#59)"
```

## Acceptance criteria coverage

| AC | Tasks |
|---|---|
| AC-1 | 1 (public, licence, pin, tests run), 2 (scan inputs at the pin, scrubbed) |
| AC-2 | 3 |
| AC-3 | 4 (per set and pooled, every line with its n) |
| AC-4 | 4 (pipeline baselines for both sets, recorded and pinned) |
