# Reduce Consumption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A default scan consumes at least half of what it does today, with the same findings, and every scan reports what it consumed.

**Architecture:** A `SubagentStop` hook, `scripts/capture_finding.py`, saves each investigator's result to disk, so no result depends on the orchestrator re-typing or relaying it. A deterministic `scripts/usage.py` reads Claude Code's transcripts and writes `.thunderstruck/usage.json`, which `report.py` renders as a **Consumption** section. The investigator is pinned to Sonnet and reads less; the scan skill gets explicit orchestration rules, and the scripts print less.

**Tech Stack:** Python 3.11+ stdlib (the hook and `finding_shape.py`), `uv`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-03-reduce-consumption-design.md` (§n below refers to it). Requirements AC-1…AC-10 are in GitHub issue #5.

**Branch:** `feat/reduce-consumption`. One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

## Global Constraints

- `capture_finding.py` and `finding_shape.py` import the stdlib only: no `yaml`, no `lizard`, no `_common` (§3.3). `capture_finding.py` may import `finding_shape`.
- The hook always exits 0, prints nothing, and its median runtime on the fixture is under 100 ms (§3.3).
- The hook builds every path it writes from `bundles/index.json`, never from the payload, and writes only under `<root>/.thunderstruck/findings/` and `<root>/.thunderstruck/agents/` (§3.2, §6).
- Nothing but `<ID>.json` is ever written to `findings/`, because `validate.py:510` reads every `findings/*.json` as a finding.
- Bundle bytes, `bundle_hash`, `VALIDATION_RULES` and the finding contract do not change (§5.4, AC-9).
- `examples/sample-report.md` stays byte-identical; `gen_sample_report.py --check` passes on every commit (§7).
- `usage.json` contains no text from any transcript: only counts, model names, ids and timestamps (§6).
- Input-equivalent weights, exactly: input 1, cache write 5-minute 1.25, cache write 1-hour 2, cache write without TTL 1.25, cache read 0.1, output 5 (§2.3).
- No money figure anywhere (ticket, product decision).
- Do not declare `hooks` in `plugin.json` (CLAUDE.md).

## Review Focus

1. **A session started in a subdirectory of the repository.** The hook's `cwd` is that subdirectory; it must still find `<root>/.thunderstruck/` by walking up to the directory holding `.git`. Pinned in Task 2.
2. **A second scan in the same session and directory.** `agents/` still holds the first scan's records, and an old `usage.json` exists. Only records whose `bundle_hash` matches the current index count, and `report.py` ignores a `usage.json` whose `window.from` is not this scan's `generated_at`. Pinned in Tasks 4 and 5.
3. **An investigator answering with prose before the JSON** ("Here is the result:\n{…}"). The hook writes nothing, exactly as `save_finding.py` would reject it today; `--check` reports `missing`; the orchestrator's fallback then records `--failed`. Pinned in Tasks 2 and 3.
4. **Transcript entries that are not API calls**: user and tool-result lines, and assistant lines with model `<synthetic>`. None is counted. Pinned in Task 4.
5. **A repair round delivered after the first attempt was already saved.** The first attempt moves to `agents/<ID>.attempt1.json`, `findings/` holds only the repaired `<ID>.json`, and the agent record lists both agents. Pinned in Task 2.

---

### Task 0: Baseline measurement (maintainer, before any other task)

**Files:** `docs/calibration/consumption.md` (new), committed to `main` by the maintainer in its own PR. The measuring script itself is not committed (§9).

This needs a real repository, a fresh interactive session and a real scan. The nightly ticket agent cannot do it. **Agent rule:** if `docs/calibration/consumption.md` does not exist on `origin/main`, or has no line starting `Read cap: `, stop at Task 0 as *Blocked* with the gap "the baseline is not recorded".

- [ ] Pick one real repository with at least 10 hotspots. Note its commit, and fix the window as an ISO date one year before that commit's date. `--since 12m` is relative to today, so Task N, run weeks later, would rank different hotspots.
- [ ] Twice: delete its `.thunderstruck/findings/`, start a fresh Claude Code session in it, check out the noted commit, and run `/thunderstruck-scan --since <the ISO date>` with otherwise default arguments using the current plugin. Record the exact arguments.
- [ ] In a scratch directory, write a throwaway script that reads that session's transcript and its `subagents/agent-*.jsonl`, deduplicates entries by `message.id`, skips `<synthetic>`, and applies the §2.3 weights. Window: from `hotspots.json`'s `generated_at` to the last entry.
- [ ] Record, per scan and as the mean of the two: input-equivalent totals for the orchestrator and for investigators, each split by token type and model; agents per hotspot; extra `Read`/`Grep`/`Glob` calls per investigator (median, 90th percentile); finding count; validation pass rate (`validation.json` `valid`/`checked` before the repair round).
- [ ] Write `docs/calibration/consumption.md` in the form of `docs/calibration/config.md`, with no organisation-specific names, and end it with exactly these two lines:
  - `Investigator tokens per bundle token: <mean investigator input-equivalent per investigator ÷ mean bundle tokens_estimated, one decimal>`
  - `Read cap: <5 if the 90th percentile of extra reads is under 5, else that percentile rounded up>`

### Task 1: Move finding shaping into a stdlib module

**Files:** `scripts/finding_shape.py` (new), `scripts/save_finding.py`, `scripts/_common.py`, `tests/test_finding_shape.py` (new).

A refactor with no behaviour change, so Task 2's hook and `save_finding.py` produce byte-identical files (§3.4).

**Interfaces:**
- Produces, in `scripts/finding_shape.py`:
  - `FINDING_SCHEMA_VERSION = "thunderstruck.finding/v1"` (moved; `_common.py` re-exports it with `from finding_shape import FINDING_SCHEMA_VERSION`).
  - `normalise(doc: dict) -> list[str]` (moved unchanged from `save_finding.py`, with its helpers `_PATH_LINES`, `_COMMIT_PREFIX`, `_TYPE_ALIASES`, `_lines_of`).
  - `parse_result(raw: str) -> dict` — strip whitespace and one markdown fence, `json.loads`; raises `ValueError` with today's message text if it is not JSON or not an object.
  - `shape(doc: dict, entry: dict) -> dict` — everything `save_finding.main` does between parsing and writing: `normalise` (set or pop `normalised`), `setdefault` `hotspot_id`/`file` from `entry`, pop `validated_with` and the owned per-finding keys (`key`, `content_hash`, `catalog_evidence`, `evidence_hashes`), stamp `bundle_hash` and `schema`. Returns `doc`.
  - `failed_doc(entry: dict) -> dict` — today's `--failed` document, stamped the same way.
  - `write_json_atomic(path: Path, payload) -> None` — same bytes as `_common.write_json` (`json.dumps(payload, indent=2, sort_keys=False) + "\n"`), via a temp file opened with `O_CREAT | O_EXCL | O_NOFOLLOW` and `os.replace`.
  - `find_entry(index: dict, hotspot_id: str) -> dict | None` — the `bundles` list entry whose `id` equals `hotspot_id`, compared as an exact string; `None` for anything else.
  - `record_agent(out: Path, entry: dict, agent: dict) -> None` — writes `out/agents/<entry id>.json` as `{"hotspot_id", "bundle_hash", "agents": [...]}`; appends `agent` when the stored `bundle_hash` equals `entry["bundle_hash"]`, otherwise starts a new list.
- `save_finding.py` keeps `from finding_shape import normalise` at module level, so `tests/test_investigator_contract.py:23` keeps working.

- [ ] Write `tests/test_finding_shape.py`, failing:
  - `parse_result` accepts a fenced and an unfenced object, and raises `ValueError` for `"Here is the result:\n{}"`, for `[]` and for invalid JSON;
  - `shape` on the fixture's canned findings (from `tests/test_pipeline.py`'s `_valid_finding`) equals what today's `save_finding.py --from` writes, byte for byte, through `write_json_atomic`;
  - `write_json_atomic` refuses to write through a symlinked destination directory (`OSError`) and leaves no `.tmp` behind;
  - `find_entry` returns `None` for `"../H01"`, `"H01 "`, `1` and an absent id;
  - `record_agent` appends for the same `bundle_hash` and resets for a different one;
  - an AST test that `finding_shape.py` imports nothing outside `sys.stdlib_module_names`.
- [ ] Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_finding_shape.py -q`. Expected: `ModuleNotFoundError: finding_shape`.
- [ ] Create `finding_shape.py` by moving the code; make `save_finding.main` call `parse_result`, `shape`, `failed_doc` and `c.write_json`. Its printed output is unchanged.
- [ ] Run the new tests, then the full suite, then `uv run scripts/gen_sample_report.py --check`.
- [ ] Commit: `Move finding shaping into a stdlib module (#5)`.

### Task 2: The `SubagentStop` capture hook (AC-5, AC-10)

**Files:** `scripts/capture_finding.py` (new), `hooks/hooks.json`, `tests/test_capture_finding.py` (new), `tests/fixtures/hook_payloads/*.json` (new), `tests/test_guardrail.py` (the manifest test).

**Interfaces:**
- Consumes: Task 1's `parse_result`, `shape`, `find_entry`, `write_json_atomic`, `record_agent`.
- Produces: `capture_finding.main(stdin_text: str) -> None` and the script entry point. Writes `findings/<ID>.json`, `agents/<ID>.json`, and on a second delivery `agents/<ID>.attempt1.json`.

- [ ] Add payload fixtures, each a `SubagentStop` input with `session_id`, `transcript_path`, `cwd` (rewritten by the test to its temp repo), `hook_event_name`, `agent_id`, `agent_type: "plugin:thunderstruck:thunderstruck-investigator"`, `stop_reason: "completed"` and `last_assistant_message`: `valid.json` (a canned finding for `H01`), `fenced.json`, `prose_first.json` (Review Focus 3), `unknown_id.json` (`H99`), `path_id.json` (`"../../etc/x"`), `other_agent.json` (`agent_type: "Explore"`), `not_json.json`, `no_fields.json` (no `agent_type`, no `last_assistant_message`, the pre-2.1.206 shape).
- [ ] Write `tests/test_capture_finding.py`, failing. Each test builds the fixture repo, runs `signals.py` and `bundle.py`, then runs the hook as `python3 scripts/capture_finding.py` with the payload on stdin:
  - `valid` writes `findings/H01.json` byte-identical to `save_finding.py --id H01 --from <same JSON>`, and `agents/H01.json` with one agent;
  - `fenced` is the same as `valid`;
  - `prose_first`, `unknown_id`, `path_id`, `other_agent`, `not_json`, `no_fields`: nothing is written anywhere under `.thunderstruck/`;
  - a payload over 1 MB: nothing written;
  - no `.thunderstruck/bundles/index.json`: nothing written;
  - `cwd` set to `<repo>/src` (Review Focus 1): `findings/H01.json` is written under `<repo>/.thunderstruck/`;
  - `valid` delivered twice with different `agent_id`s (Review Focus 5): `agents/H01.attempt1.json` holds the first, `findings/H01.json` the second, `agents/H01.json` lists both with `kind` `first` then `respawn`, and `findings/` contains exactly one file; the same with a `validation.json` listing `H01` invalid gives `first` then `repair`;
  - every case exits 0 with empty stdout and stderr;
  - median of 20 runs of `valid` under 100 ms (copy the guardrail's latency test);
  - the source contains none of `import yaml`, `import lizard`, `from yaml`, `import _common`, and its AST imports only stdlib names and `finding_shape`.
- [ ] Run: `uv run --with pytest --with pyyaml --with lizard pytest tests/test_capture_finding.py -q`. Expected: failures, the script does not exist.
- [ ] Implement `scripts/capture_finding.py` (§3.2), with the shebang and `# /// script` header of `guardrail.py` and the whole body in one `try/except BaseException: pass`, then `sys.exit(0)`:

```python
def _root(cwd: str) -> Path | None:
    p = Path(cwd).resolve()
    for d in (p, *p.parents):
        if (d / ".git").exists():
            return d
    return None


def main(stdin_text: str) -> None:
    if len(stdin_text) > 1_000_000:
        return
    payload = json.loads(stdin_text)
    if not str(payload.get("agent_type", "")).endswith("thunderstruck-investigator"):
        return
    root = _root(payload.get("cwd") or os.getcwd())
    out = root / ".thunderstruck" if root else None
    index_path = out / "bundles" / "index.json" if out else None
    if not index_path or not index_path.is_file():
        return
    message = payload.get("last_assistant_message")
    if not isinstance(message, str):
        return
    doc = finding_shape.parse_result(message)
    entry = finding_shape.find_entry(json.loads(index_path.read_text("utf-8")),
                                     doc.get("hotspot_id"))
    if entry is None:
        return
    dest = out / "findings" / f"{entry['id']}.json"
    previous = _load(dest)
    if previous and previous.get("bundle_hash") == entry["bundle_hash"]:
        finding_shape.write_json_atomic(out / "agents" / f"{entry['id']}.attempt1.json", previous)
    kind = "first"
    if previous and previous.get("bundle_hash") == entry["bundle_hash"]:
        kind = "repair" if _listed_invalid(out, entry["id"]) else "respawn"
    finding_shape.write_json_atomic(dest, finding_shape.shape(doc, entry))
    agent = {k: payload.get(k) for k in ("agent_id", "session_id", "transcript_path", "stop_reason")}
    finding_shape.record_agent(out, entry, {**agent, "kind": kind})
```

  `_load` returns `None` on any read or parse error. `_listed_invalid(out, hid)` is true when `out/validation.json`'s `results` has an entry with `hotspot_id == hid` and `valid: false`; false on any read error. `entry["id"]` comes from the index, so the destination never contains payload text.
- [ ] Add the `SubagentStop` entry to `hooks/hooks.json` exactly as §3.1. Extend `test_hooks_json_matches_current_tool_names` (or add a sibling test) to assert `hooks.json` has exactly the keys `PreToolUse` and `SubagentStop`, one entry each, and that the `SubagentStop` command runs `capture_finding.py` with `|| exit 0`.
- [ ] Run the new tests, the full suite, and `claude plugin validate . --strict`.
- [ ] Commit: `Save investigator results from a SubagentStop hook (#5)`.

### Task 3: `save_finding.py --check`, `--fallback` and `--usage` (AC-5, AC-6)

**Files:** `scripts/save_finding.py`, `tests/test_save_finding_check.py` (new).

**Interfaces:**
- Consumes: Task 1's `find_entry`, `record_agent`.
- Produces, on the command line:
  - `save_finding.py --check H01 H02 …` prints one line per id, `H01 saved` / `H01 missing` / `H01 failed`, and exits 0. `saved`: `findings/<ID>.json` exists with the current `bundle_hash` and no `analysis_failed`. `failed`: same hash, `analysis_failed: true`. Otherwise `missing`, including an unknown id.
  - `--fallback` with `--id … --from …` or `--failed` records `{"fallback": true}` in `agents/<ID>.json`.
  - `--usage '<json>'` with `--id` records `{"relayed_usage": {…}}` in `agents/<ID>.json`, keeping only the four integer keys `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`; an absent key stays absent (§2.5). Malformed JSON is a `c.die` with exit 2.
  - `--id` is no longer required when `--check` is given; `--check` and `--id` together are an error.

- [ ] Write `tests/test_save_finding_check.py`, failing: `saved` after a normal save; `missing` before any save; `missing` for a finding whose `bundle_hash` is from an older bundle (edit the bundle's source line and re-run `bundle.py`); `failed` after `--failed`; `missing` for `H99`; `--fallback` and `--usage '{"input_tokens": 5, "output_tokens": 2, "note": "x"}'` record `fallback: true` and `relayed_usage == {"input_tokens": 5, "output_tokens": 2}`; Review Focus 3: a prose-first result through `--from` exits 2 and `--check` still says `missing`.
- [ ] Run them; they fail (`unrecognized arguments: --check`).
- [ ] Implement in `save_finding.main`.
- [ ] Run the new tests and the full suite.
- [ ] Commit: `Check which investigator results reached disk (#5)`.

### Task 4: `usage.py` (AC-1, AC-2)

**Files:** `scripts/usage.py` (new), `scripts/_common.py`, `tests/test_usage.py` (new), `tests/fixtures/transcripts/` (new).

**Interfaces:**
- Consumes: `agents/<ID>.json` from Tasks 2–3; `bundles/index.json`; `hotspots.json` `generated_at`.
- Produces:
  - In `_common.py`: `INPUT_EQUIVALENT_WEIGHTS = {"input": 1.0, "cache_write_5m": 1.25, "cache_write_1h": 2.0, "cache_write": 1.25, "cache_read": 0.1, "output": 5.0}` with a comment naming Anthropic's pricing page; `USAGE_SCHEMA = "thunderstruck.usage/v1"`.
  - In `usage.py`:
    - `projects_root() -> Path` — `Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"`.
    - `safe_transcript(path: str | None) -> Path | None` — the resolved path if it is under `projects_root().resolve()` and ends in `.jsonl`, else `None`.
    - `read_entries(path: Path, since: str | None = None, until: str | None = None) -> list[dict] | None` — `None` if unreadable; otherwise one `{"model": str, "usage": dict}` per distinct `message.id` (falling back to `requestId`) among `type == "assistant"` lines with a dict `message.usage` and `message.model != "<synthetic>"`, inside the ISO window when given. Lines that are not JSON are skipped and counted.
    - `split(usage: dict) -> dict[str, int]` — the six bucket keys of `INPUT_EQUIVALENT_WEIGHTS`; `cache_creation_input_tokens` goes to `cache_write_5m`/`cache_write_1h` from `usage["cache_creation"]` when present, else to `cache_write`.
    - `input_equivalent(buckets: dict[str, int]) -> int` — `round(sum(weight × count))`.
    - `tally(entries: list[dict]) -> dict` — `{"calls": n, "by_model": {model: {**buckets, "input_equivalent": n}}}`, models sorted.
    - `build(repo: Path, now: str) -> dict` — the §2.4 document.
  - CLI: `usage.py [--repo P]` writes `.thunderstruck/usage.json` and prints one line: `usage: <source>, ~<total>k input-equivalent tokens -> <path>`. Exit 0 even when `source` is `unavailable`; exit 2 only when there is no `hotspots.json`.

`build` in order:
1. `since = hotspots["generated_at"]`, `until = now`.
2. For each non-cached index entry, load `agents/<ID>.json`; drop it if its `bundle_hash` differs from the entry's (Review Focus 2). No record: add `"<ID>: no agent record, the hook did not fire"` to `missing`.
3. For each agent: `safe_transcript(transcript_path)`, then `Path(t).with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl"`, `read_entries` without a window. Unreadable: use `relayed_usage` if the record has one (as a single entry with model `"unknown"`), else add to `missing`.
4. `agents` = number of agent entries across records; `repairs` and `respawns` = entries with that `kind`; `fallback_saves` = records with `fallback: true`.
5. Orchestrator: the first readable `transcript_path` among the records, `read_entries(path, since, until)`. None readable: `missing` gets `"orchestrator: session transcript not readable"`.
6. `source`: `transcripts` when `missing` is empty, `unavailable` when no entry at all was read, otherwise `partial`.

- [ ] Write the transcript fixtures as small JSONL files built by a helper in the test (not checked-in blobs), under a temp `CLAUDE_CONFIG_DIR`: a session file with entries before and inside the window, a split response (three lines, same `message.id`), a `<synthetic>` line, a user line and a tool-result line; two subagent files.
- [ ] Write `tests/test_usage.py`, failing:
  - weights: one entry of each bucket at 1000 tokens gives `input_equivalent == 1000 + 1250 + 2000 + 1250 + 100 + 5000`;
  - the split response counts once; `<synthetic>`, user and tool lines count zero (Review Focus 4); entries before `generated_at` are excluded from the orchestrator and subagent entries are never windowed;
  - a normal run gives `source: transcripts`, `missing == []`, `agents == 2`, `respawns == 0`;
  - a record with agents of kind `first` and `respawn` gives `respawns == 1`; `first` and `repair` gives `repairs == 1` and `respawns == 0`;
  - a deleted subagent file with `relayed_usage` gives `source: partial`, that hotspot from the relayed figures under model `unknown`, and a `missing` line naming it;
  - a record from an older `bundle_hash` is ignored (Review Focus 2);
  - no agent records at all gives `source: unavailable`;
  - a `transcript_path` outside `projects_root()` (e.g. `/etc/passwd`, or a `.jsonl` in the temp dir but outside it) is never opened: patch `Path.open` to fail the test if called with it;
  - `usage.json` serialised contains none of the fixture's message text strings.
- [ ] Run them; they fail (`ModuleNotFoundError: usage`).
- [ ] Implement `usage.py` with PEP 723 metadata like the other scripts.
- [ ] Run the new tests and the full suite.
- [ ] Commit: `Measure a scan's consumption from Claude Code transcripts (#5)`.

### Task 5: The Consumption section (AC-1, AC-2, AC-9)

**Files:** `scripts/report.py`, `tests/test_report_consumption.py` (new).

**Interfaces:**
- Consumes: `usage.json` (Task 4).
- Produces: `collect()` adds `data["usage"]` (the document, or `None`); `render_consumption(usage: dict | None) -> list[str]`; `render_json` adds `"consumption": usage or None`; one new run warning text.

- [ ] Write `tests/test_report_consumption.py`, failing:
  - with a `transcripts` `usage.json` whose `window.from` equals `generated_at`, `report.md` has `## Consumption` right after Run warnings (or after the header block when there are none), in the §2.6 wording: totals in thousands with a `k` suffix (`round(n / 1000)`), the orchestrator's models and call count, the investigator total, agent count, models, repairs and re-spawns, and the weights line;
  - `fallback_saves > 0` adds `N result(s) saved by the orchestrator because the hook did not deliver them.`;
  - `partial` prints `Covers: <parts measured>. Not measured: <each missing line>.` instead of presenting a total as complete (AC-2);
  - `unavailable` prints `Consumption was not measured: <missing lines>.`;
  - a `usage.json` whose `window.from` differs from `generated_at`: no section, and the run warning `usage.json is from an earlier scan and was ignored` (Review Focus 2);
  - no `usage.json`: `report.md` byte-identical to the same run without the feature (compare against `render_markdown` with `data["usage"] = None`), and `report.json` has `"consumption": null`;
  - model names render through `md.code`: a model `"[x](http://e)"` appears as inert code, checked with the rendering helpers in `tests/test_inert_report.py`.
- [ ] Run them; they fail.
- [ ] Implement. `render_consumption` builds every value with `md.code` or plain integers. `report.html` (#3) is not changed: it reads `report.json`, ignores the new `consumption` key, and `tests/test_report_html.py` must pass unchanged.
- [ ] In Task 8's step 5 edit, keep #3's order: `usage.py`, then `report.py`, then `report_html.py` (`test_scan_step_5_renders_html_after_the_markdown_and_never_fails`).
- [ ] Run the new tests, the full suite and `uv run scripts/gen_sample_report.py --check`.
- [ ] Commit: `Report what a scan consumed (#5)`.

### Task 6: Quieter scripts and the estimate line (AC-3, AC-7)

**Files:** `scripts/bundle.py`, `scripts/validate.py`, `scripts/_common.py`, `tests/test_quiet_output.py` (new), any existing test that asserts on per-bundle or `ok` lines (find them with `grep -rn '"ok  \|tokens  ' tests/`).

**Interfaces:**
- Produces: `--verbose` on `bundle.py` and `validate.py`; `INVESTIGATOR_TOKENS_PER_BUNDLE_TOKEN: float` in `_common.py`, set to Task 0's recorded value with a comment citing `docs/calibration/consumption.md`; `bundle.estimate_line(todo_tokens: list[int]) -> list[str]`.

- [ ] Write `tests/test_quiet_output.py`, failing:
  - `bundle.py` default stdout has no line matching `^[HD]\d\d  ~`, still has the `need investigating` line, and ends with the two §2.7 estimate lines; with `--verbose` the per-bundle lines are back;
  - the estimate is `round(sum(todo tokens) × INVESTIGATOR_TOKENS_PER_BUNDLE_TOKEN / 1000)` thousand, and with zero bundles to investigate it reads `estimate: no investigators to run`;
  - `validate.py` default stdout has no `ok  ` line, has every `FAIL` line with each error indented beneath it, and the summary line; `--verbose` restores `ok  ` lines; `--quiet` still prints nothing;
  - bundle files and `index.json` are byte-identical with and without `--verbose`.
- [ ] Run them; they fail.
- [ ] Implement; update the existing tests that read the removed lines to pass `--verbose`.
- [ ] Run the full suite and `gen_sample_report.py --check`.
- [ ] Commit: `Print summaries by default and estimate investigator consumption (#5)`.

### Task 7: The investigator prompt (AC-4, AC-8)

**Files:** `agents/thunderstruck-investigator.md`, `tests/test_investigator_contract.py`.

- [ ] Add failing tests to `tests/test_investigator_contract.py`:
  - the frontmatter parses (split on the `---` lines, `yaml.safe_load`) and has `model: sonnet`, and still `tools: Read, Grep, Glob`;
  - the prompt contains `up to **<Read cap>** additional files`, where `<Read cap>` is the integer from `docs/calibration/consumption.md`'s `Read cap:` line (skip if the file is absent, so the suite runs before Task 0 lands);
  - the prompt contains the sentences on not re-reading a full-source bundle file and preferring `Grep`, and the output-length rule;
  - `test_the_prompt_example_is_a_complete_valid_shape` still passes unchanged.
- [ ] Run them; they fail.
- [ ] Edit the agent file (§5):
  - frontmatter: add `model: sonnet`;
  - "Your inputs": replace the 10-file paragraph with: "The bundle's Source section holds the hotspot file, and says when it was trimmed. Do not Read a file whose full source is already in the bundle. Re-read a trimmed file only for the line range a lead needs. You may open up to **<Read cap>** additional files with Read/Grep/Glob to confirm or reject a lead; prefer a `Grep` with a narrow pattern over reading a whole file. Prefer the files the bundle names as imports, call sites or temporally coupled. If <Read cap> reads are not enough to settle a lead, say so in `confidence_rationale` rather than guessing.";
  - "Output": add "Keep each evidence `note` to one short sentence and `confidence_rationale` to at most two sentences."
- [ ] Run the contract tests and the full suite.
- [ ] Commit: `Pin investigators to Sonnet and have them read less (#5)`.

### Task 8: Orchestration rules, `--model`, docs and release (AC-4, AC-6, AC-7)

**Files:** `skills/thunderstruck-scan/SKILL.md`, `skills/thunderstruck-scan/references/orchestration.md`, `skills/thunderstruck-scan/references/report-format.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`, `tests/test_docs_in_sync.py`.

- [ ] Add failing tests to `tests/test_docs_in_sync.py`:
  - `SKILL.md`'s argument table has a `--model` row with default `sonnet`;
  - step 3 names `save_finding.py" --check`, `--fallback` and `model:`, and contains each of `SendMessage`, `ListAgents` and `agent teams` only in a "never" sentence (assert the sentence containing each also contains `Never`);
  - step 5 runs `usage.py` before `report.py`;
  - `orchestration.md` no longer contains `about 80k tokens`.
- [ ] Run them; they fail.
- [ ] Edit `SKILL.md`:
  - arguments: `| --model M | sonnet | Model for the investigators: haiku, sonnet or opus. The repair round uses the same one. |`;
  - step 2's dry-run paragraph: also relay `bundle.py`'s estimate lines;
  - step 3: the §4.1 rules as a list under a "How to run them" heading, the `--check` step after each batch, and the §4.2 fallback, replacing "Save each result immediately…" (the hook now does that). Keep the save and `--failed` commands in the fallback;
  - step 4: the hook captures the repair; after it, `--check` and the same fallback;
  - step 5: run `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/usage.py"` first; its failure never stops the report, and step 6 then says consumption was not measured, quoting its error line;
  - step 6: summarise from `report.json` (`counts`, the top findings, `consumption`), and include the Consumption line.
- [ ] Rewrite `orchestration.md`'s Cost control with Task 0's measured figures and the input-equivalent weights, and add a row to "When things fail": *Hook did not save a result → `--check` says `missing`; save it with `--fallback`; the report counts it.* Add `usage.json` and `agents/` to `report-format.md`'s output list, and add a line under "What leaves the machine": `usage.py` reads Claude Code's own transcripts on this machine and writes counts only.
- [ ] Bump the minor version in all four places (the next minor above `main`'s at the time; `0.10.0` if `main` is still `0.9.0`) and add a CHANGELOG entry in the 0.8.2 entry's form: *Added* (Consumption section and `usage.py`; the capture hook; `--model`; the dry-run estimate), *Changed* (investigators default to Sonnet and read at most <Read cap> extra files; `bundle.py` and `validate.py` print summaries unless `--verbose`; orchestration rules).
- [ ] Run the full suite, `gen_catalog_docs.py --check`, `gen_sample_report.py --check`, `claude plugin validate . --strict`, then install from this checkout and confirm `claude plugin list` says `enabled`.
- [ ] Commit: `Orchestration rules, --model and docs for consumption (#5)`.

### Task N: Comparison measurement (maintainer, after merge)

**Files:** `docs/calibration/consumption.md`; possibly `scripts/_common.py`.

- [ ] Install the released plugin. On the same repository and commit as Task 0, twice: delete `findings/`, fresh session, `/thunderstruck-scan` with exactly Task 0's recorded arguments.
- [ ] Record `usage.json`'s figures beside Task 0's, as means of the two runs, and the same quality numbers. Record which matcher form the `SubagentStop` hook fired with (§11) and whether either session compacted.
- [ ] Verdict against the ticket's success measures: weighted total ≤ 50% of baseline; zero re-spawns; finding count down by no more than one per five hotspots; validation pass rate not lower.
- [ ] Update `INVESTIGATOR_TOKENS_PER_BUNDLE_TOKEN` to the measured post-change ratio in the same PR, and regenerate nothing else.
- [ ] If the verdict fails, open a follow-up ticket with the numbers; do not tune in place.
