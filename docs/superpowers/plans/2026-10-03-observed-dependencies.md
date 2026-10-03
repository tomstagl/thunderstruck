# Observed Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A scan links each documented outbound dependency to the files and lines that call it, lets a finding cite such a link as checked evidence, and reports catalog drift in both directions.

**Architecture:** A new deterministic step, `scripts/observed.py`, reads the repository's tracked files and `context.json` and writes `.thunderstruck/observed.json`. `bundle.py` briefs each hotspot with its file's observations, `validate.py` resolves `observed` evidence against that file, and `report.py` renders a **Catalog drift** section. No model call and no network call are added anywhere.

**Tech Stack:** Python 3.11+, PyYAML (`yaml.compose_all` for line numbers), `uv`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-observed-dependencies-design.md` (§n below refers to it). Requirements AC-1…AC-12 are in GitHub issue #6.

**Branch:** `feat/observed-dependencies`. One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

## Global Constraints

- `observed.py` imports no network library and runs no subprocess other than `git` through `_common` (§10).
- Detection, matching, hashing and rendering never depend on model output (CLAUDE.md, governing rule).
- Bundles, `observed.json` and the drift section are byte-identical across runs on an unchanged repository and catalog (AC-11). No timestamp, absolute path or dict-order dependence.
- Without usable service context, every bundle and the report are byte-identical to `main` (AC-10).
- Every repository-sourced value reaches Markdown only through `mdtext.code`; every location link through `mdtext.linked` (AC-12).
- No secret value, URL userinfo or source-line text in any file under `.thunderstruck/` (AC-8, §10).
- `VALIDATION_RULES` stays at its current value (§7).
- At most one warning per invalid `[observed]` entry; an invalid entry never disables the feature (§4).
- Caps: 2000 observations total, 20 per distinct value, 15 bundle lines, 3 report locations per value, `--limit` 3000 files (§2.5, §5, §6, §8).

## Review Focus

1. **A URL whose userinfo holds an `@` or a `/`** (`postgres://u:p@ss/w@db.internal/x`): only `db.internal` may be observed, and no fragment of the password anywhere. Pinned in Task 1's secret-safety sample.
2. **The same host in a comment and in code on adjacent lines**: only the code line is an observation. Pinned in Task 1's samples.
3. **A Helm template** (`{{ .Values.x }}` makes the YAML unparseable): URL hosts and `${NAME}` still observed, structural forms skipped, one warning. Pinned in Task 3.
4. **A neighbour name equal in two namespaces** (`component:a/ledger`, `component:b/ledger`): `ambiguous`, never `documented`. Pinned in Task 2.
5. **`observed.json` edited by hand** without recomputing `observed_hash`: it is treated as missing (§9), so no ref is accepted from it. Edited *and* rehashed after bundling: rule 2 rejects every ref. Pinned in Tasks 3 and 6.

---

### Task 0: The spike (maintainer, before any other task)

**Files:** `docs/calibration/observed-dependencies.md` (new), committed to `main` by the maintainer in its own PR. The spike script itself is not committed (§12).

This task needs a real repository with a real catalog, and a person to review the sample. The nightly ticket agent cannot do it. **Agent rule:** if `docs/calibration/observed-dependencies.md` does not exist on `origin/main`, or does not contain the line `Verdict: go`, stop at Task 0 as *Blocked* with the gap "the spike is not recorded".

- [ ] In a scratch directory, write a throwaway script that applies §2 (all three kinds, the §2.4 exclusions) and §3 rule 3 (exact name only, no profile map) to one real repository and its `.thunderstruck/context.json`.
- [ ] Run it. Record only counts and shares: documented outbound edges linked to at least one file; distinct values per resolution; dropped values per kind.
- [ ] Review 30 unmatched values by hand, chosen as every k-th of the sorted list. Mark each "real dependency" or "noise".
- [ ] Write `docs/calibration/observed-dependencies.md` in the form of `docs/calibration/config.md`, with no organisation-specific names, and end it with exactly one of:
  - `Verdict: go` — at most 6 of the 30 are noise (the ticket's one-in-five threshold);
  - `Verdict: no-go — <what to narrow>` — then change the spec (§2) before this plan continues.

### Task 1: Exclusions catalog and observation extraction (AC-8, AC-9)

**Files:** `catalog/observed.yaml` (new), `scripts/observed.py` (new; extraction only), `tests/observed/samples/<kind>/<language>/…` (new), `tests/observed/test_observed_samples.py` (new).

**Interfaces:**
- Produces, in `scripts/observed.py`:
  - `load_rules(root: Path | None = None) -> dict` — `catalog/observed.yaml` parsed, with compiled patterns.
  - `observe_text(text: str, lang: str, rel: str, rules: dict) -> tuple[list[dict], dict[str, int], bool]` — observations `{"kind", "value", "file", "line"}` in file order, the `dropped` counts per kind, and whether a YAML file failed to parse.
  - `ref(obs: dict) -> str` — `f"observed {kind}:{value} {file}:{line}"`.

- [ ] Write `catalog/observed.yaml`. It holds the data parts of §2 and §2.4, so a later addition is a data change with a sample:

```yaml
schema: thunderstruck.observed-rules/v1
kinds:
  host:   {languages: [typescript, javascript, python, java, yaml, properties]}
  env:    {languages: [typescript, javascript, python, java, yaml, properties]}
  secret: {languages: [typescript, javascript, python, java, yaml]}
env_suffixes: [_URL, _URI, _HOST, _HOSTNAME, _ENDPOINT, _ADDR, _ADDRESS, _DSN]
secret_calls: [read_secret_version, read_secret, readSecret, getSecretValue]
exclude_hosts:
  exact: [localhost, "::1", 0.0.0.0, example.com, example.org, example.net,
          www.w3.org, json-schema.org, schemas.xmlsoap.org, schemas.microsoft.com,
          xmlns.com, purl.org, maven.apache.org, www.apache.org, schemas.android.com,
          github.com, gitlab.com, developer.mozilla.org, stackoverflow.com]
  suffix: [.localhost, .example.com, .example.org, .example.net, .example, .test,
           .invalid, .readthedocs.io]
  prefix: [docs.]
  ipv4_loopback: true          # 127.0.0.0/8
```

- [ ] Add the samples. Layout: `tests/observed/samples/<kind>/<language>/{positive,negative}_<topic>.<ext>`. Every positive file has a sibling `<file>.expected` with one `<kind>:<value>:<line>` per line, sorted. A negative file must yield no observation of its directory's kind. At minimum (§11 list, plus Review Focus 1–2):
  - `host`: per language one positive (a `fetch`/`requests`/`HttpClient`/YAML/properties URL, a userinfo URL `postgres://app:hunter2@db.internal/app` expecting only `db.internal`, and `postgres://u:p@ss/w@db.internal/x` expecting only `db.internal`); `yaml/positive_mesh.yaml` with a `VirtualService` (`spec.hosts`, `route[].destination.host`) and a `DestinationRule` (`spec.host`); a positive with the same URL commented out on the line above the call, whose `.expected` lists only the call's line (Review Focus 2); negatives: a commented-out URL alone, `localhost`/`127.0.0.2`/`example.com`/`svc.test`/`json-schema.org`/`docs.python.org`, a `${HOST}` URL and a `{{ .Values.host }}` URL.
  - `env`: per language a positive for every read form in the §2.2 table, including `@Value("${payments.base-url}")` expecting `env:PAYMENTS_BASE_URL`; a YAML container `env[].name`; negatives `LOG_LEVEL`, `API_KEY`, and a commented-out read.
  - `secret`: `yaml/positive_externalsecret.yaml` (`data[].remoteRef.key` and `dataFrom[].extract.key`), `yaml/positive_vault_annotation.yaml`, `yaml/positive_csi.yaml`, one code positive per language; negatives: a 40-character `[A-Za-z0-9]` literal passed to `getSecretValue` (dropped), a secret call in a comment.
- [ ] Write `tests/observed/test_observed_samples.py`: discover the samples from the tree (no list); for each positive, `observe_text` output projected to `kind:value:line` equals the `.expected` file; for each negative, no observation of that kind; `test_every_kind_has_both_samples` asserts a positive and a negative per `(kind, language)` in `observed.yaml` for every language in `observed.yaml` except those the catalog's `aliases` map onto another (`javascript` → `typescript`), which the target language's samples cover; a secret-safety test asserts that `hunter2`, `p@ss` and the 40-character literal appear in no `observe_text` output, serialised.
- [ ] Run them; they fail with `ModuleNotFoundError: observed`.
- [ ] Implement extraction in `scripts/observed.py` (§2):
  - `lang` is what `c.detect_language` returns. Blank comments first with `c.strip_comments(text, lang)`; string contents stay. `javascript` uses the `typescript` read forms.
  - Host: `(?P<scheme>[a-z][a-z0-9+.-]{1,15})://(?:[^\s/'"`@]*@)*(?P<host>[^\s/'"`:?#\]\[]+)`. The repeated userinfo group consumes every `…@` before the host, which covers Review Focus 1. Normalise (lowercase, strip port and trailing dot), then the §2.1 pattern and length check, then the exclusions. A value with `$ { } % <` is not a value (§2.4).
  - Env: one regex per §2.2 form; keep a name only if it matches `^[A-Z][A-Z0-9_]{0,63}$` and ends in an `env_suffixes` entry. Spring keys: `.`/`-` → `_`, uppercase.
  - Secret: §2.3 forms; the value pattern `^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}$`; drop a value of 32 or more characters with none of `/ - _`.
  - YAML structural forms: walk `yaml.compose_all(text)` nodes; a scalar's line is `node.start_mark.line + 1`. On `yaml.YAMLError`, skip the structural forms for that file and return `True` as the third value (spec §9).
  - A value that fails its kind's pattern increments `dropped[kind]` and is never returned.
- [ ] Run the sample tests, then the full suite.
- [ ] Commit: `Observe hosts, address env vars and secret references in tracked files (#6)`.

### Task 2: Matching and the `[observed]` profile table (AC-5, AC-6, AC-7)

**Files:** `scripts/observed.py`, `tests/test_observed_match.py` (new).

**Interfaces:**
- Consumes: Task 1's observation dicts; `context.json` edges `{"ref", "type", "direction", "neighbour", "attributes"}`.
- Produces:
  - `load_config(profile: dict) -> tuple[dict, list[str]]` — `{"map": [{"entity", "host": [...], "env": [...], "secret": [...]}], "ignore": [{"kind", "value", "reason"}]}` plus one warning per dropped entry.
  - `map_hash(cfg: dict) -> str` — `c.sha256_text(json.dumps(cfg, sort_keys=True, separators=(",", ":")))`.
  - `match_name(kind: str, value: str) -> str` — the §3 rule 3 normalised name.
  - `resolve(observations: list[dict], edges: list[dict], cfg: dict) -> dict` — `{"resolutions": [...], "not_observed": [...], "ignored": [...]}` in the §5 shapes, sorted per §5.

- [ ] Write failing unit tests (spec §11 "Matching unit tests", "Config validation"):
  - ignore beats map, map beats name;
  - `host` uses the first DNS label (`payments-api.prod.svc.cluster.local` → `payments-api`; `payments.internal` does not match `payments-api`); `env` strips the suffix (`PAYMENTS_API_URL` → `payments-api`); `secret` takes the last segment, lowercased;
  - an exact-name match against an `outbound` edge is `documented` with `edge` = the edge's `ref`; against an `inbound` edge only, `dependent_only`; a map entity in neither list, `mapped_undocumented`; otherwise `unmatched`;
  - `component:a/ledger` and `component:b/ledger` both outbound: `ledger.internal` is `ambiguous` with both refs listed (Review Focus 4);
  - `not_observed` lists every outbound edge `ref` with no `documented` resolution, sorted;
  - `ignored` carries `rule` (`"host api.vendor.internal"`), `reason` and `hits` (occurrences);
  - a `*.vendor.internal` ignore rule matches `a.vendor.internal`, not `vendor.internal`;
  - config: a bad entity ref, a value claimed by two map entries (the second entry is dropped), an ignore rule with two kinds, and one without a reason each yield one warning and leave the other entries working.
- [ ] Run; they fail.
- [ ] Implement `load_config`, `map_hash`, `match_name` and `resolve`. Neighbour names are the part after `/` in the entity ref, lowercased. The entity-ref check uses `context_extract.ENTITY_REF`.
- [ ] Run the tests, then the full suite.
- [ ] Commit: `Match observations to documented dependencies by declared map or exact name (#6)`.

### Task 3: `observed.py` writes `observed.json` (AC-10, AC-11)

**Files:** `scripts/observed.py` (CLI, file walk, document), `tests/test_observed_doc.py` (new).

**Interfaces:**
- Consumes: Tasks 1–2; `c.load_service_context`, `c.tracked_index`, `c.path_problem`, `c.tracked_file_problem`, `c.is_utf8`, `c.Filters.from_profile`, `c.language_map`, `c.detect_language`.
- Produces: `run(repo: Path, limit: int = 3000) -> dict` and `main(argv) -> int`; `.thunderstruck/observed.json` with schema `thunderstruck.observed/v1` and exactly the §5 fields; `OBSERVED_FILENAME = "observed.json"` and `OBSERVED_SCHEMA` in `_common.py`; `c.load_observed(repo) -> dict | None` returning the document only when `status == "ok"`, the schema matches and `observed_hash` equals the hash recomputed from its content; otherwise `None`, which every stage treats as `skipped` (§9).

- [ ] Write failing tests over a small `tmp_path` git repository built with `isolated_git_env()` and a hand-written `context.json` (status `fresh`, a valid `context_hash` from `context_extract.context_hash`):
  - no `context.json`, or status `untrusted`: `{"schema", "status": "skipped", "reason"}` and nothing else;
  - `ok`: the fields of §5; observations sorted by `(file, line, kind, value)`; `observed_hash` covers exactly `observations`, `resolutions`, `not_observed`, `truncated`;
  - two runs give byte-identical files (AC-11), and adding a warning (an invalid map entry) leaves `observed_hash` unchanged;
  - caps: 21 occurrences of one host keep 20 and count 1 in `truncated.observations`; `--limit 2` stops after two files with a warning naming the limit;
  - untracked files, files under `tests/`, and files the profile's `[filters]` exclude are not read;
  - a Helm-style YAML file with `{{ .Values.x }}` and a `https://ledger.internal` URL yields the host and one warning `1 YAML file(s) could not be parsed; …` (Review Focus 3);
  - `c.load_observed` returns `None` for a document whose content was edited without recomputing `observed_hash` (Review Focus 5);
  - `context.json` with `truncated.outbound > 0` sets `truncated.catalog_edges` to that count;
  - no file under `.thunderstruck/` contains `hunter2` after scanning a file with `postgres://app:hunter2@db.internal/app` (§11 "Secret safety").
- [ ] Run; they fail.
- [ ] Implement the walk (§2.5): files from `c.tracked_index(repo)`, the same acceptance checks `signals.py` applies to ranked files (`c.is_utf8`, `c.path_problem`, `c.tracked_file_problem`, `filters.excludes_path`), a language from `language_map`, sorted, stopped at `--limit`. Then caps, `resolve`, hashes and `c.write_json`. Print one line: `observed: <n> observation(s), <d> documented, <u> not in the catalog, <m> not observed` or `observed: skipped (<reason>)`.
- [ ] Run the tests, then the full suite.
- [ ] Commit: `Write observed.json from tracked files and the service context (#6)`.

### Task 4: Fixture with planted dependencies (success measure "after the build")

**Files:** `tests/fixtures/fake_catalog.py`, `tests/fixtures/build_fixture.py`, `tests/conftest.py`, `tests/test_observed_fixture.py` (new).

**Interfaces:**
- Produces: `build_fixture.add_observed_dependencies(repo: Path) -> None`; `context_scanned_repo` now also runs `observed.py` between `context.py` and `bundle.py`.

- [ ] In `fake_catalog.py`, add to the main entity's relations two outbound edges, `component:default/search-api` and `component:default/legacy-billing`, and one inbound edge, `component:default/reporting-job`, each with a `neighbour(...)` entry like the existing ones.
- [ ] Add `add_observed_dependencies` to `build_fixture.py` (spec §11, as amended). It appends to the three top-ranked files only, so the ranking stays as close to the base fixture as possible:

```python
OBSERVED_ADDITIONS = {
    "src/client/releases.ts":
        '\nexport const RELEASES_URL = process.env.RELEASES_API_URL'
        ' ?? "https://releases-api.prod.svc.cluster.local";\n'
        'export const CHARGES_URL = "https://payments-api.internal/charges";\n',
    "src/sync/collection.ts":
        '\nexport const FX_RATES_URL = "https://fx-rates.internal/v1/latest";\n'
        'export const LEDGER_DSN = process.env.LEDGER_DSN;\n',
    "src/sync/scheduler.ts":
        '\nexport const SYNC_DONE_HOOK = "https://reporting-job.internal/hooks/sync-done";\n'
        'export const ANALYTICS_URL = "https://collector.analytics-vendor.internal/events";\n',
}
SEARCH_SECRET = """apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: search
spec:
  data:
    - secretKey: token
      remoteRef:
        key: secret/data/search-api
"""
OBSERVED_PROFILE = """
[[observed.map]]
entity = "component:default/ledger"
env = ["LEDGER_DSN"]

[[observed.ignore]]
host = "collector.analytics-vendor.internal"
reason = "third-party analytics; tracked outside the catalog"
"""


def add_observed_dependencies(repo: Path) -> None:
    """Plant one case per drift list (spec §11). observed.py reads tracked
    files only, so the code is committed: one commit, one day after the last
    one. The [observed] profile stays untracked, like [context]."""
    for rel, text in OBSERVED_ADDITIONS.items():
        with (repo / rel).open("a", encoding="utf-8") as fh:
            fh.write(text)
    (repo / "deploy" / "search-externalsecret.yaml").write_text(SEARCH_SECRET, encoding="utf-8")
    last = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%cI"], check=True,
                          capture_output=True, text=True, env=isolated_git_env()).stdout.strip()
    when = (datetime.fromisoformat(last) + timedelta(days=1)).isoformat()
    run(repo, "add", *OBSERVED_ADDITIONS, "deploy/search-externalsecret.yaml")
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "feat: wire the downstream clients"],
                   check=True, capture_output=True, text=True,
                   env={**isolated_git_env(), "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when,
                        "GIT_AUTHOR_NAME": "Fixture Author", "GIT_AUTHOR_EMAIL": "fixture@example.com",
                        "GIT_COMMITTER_NAME": "Fixture Author",
                        "GIT_COMMITTER_EMAIL": "fixture@example.com"})
    with (repo / ".thunderstruck.toml").open("a", encoding="utf-8") as fh:
        fh.write(OBSERVED_PROFILE)
```

- [ ] In `conftest.py`, call `add_observed_dependencies(repo)` in `context_repo_template` after `add_service_context`, and add `["observed.py"]` to `context_scanned_repo`'s steps after `["context.py"]`. `fixture_repo` and `scanned_repo` do not change.
- [ ] Write `tests/test_observed_fixture.py` over `context_scanned_repo`, asserting the resolutions exactly:

| kind:value | resolution |
|---|---|
| `host:releases-api.prod.svc.cluster.local`, `env:RELEASES_API_URL` | `documented`, `dependsOn component:default/releases-api` |
| `host:payments-api.internal` | `documented`, `dependsOn component:default/payments-api` |
| `secret:secret/data/search-api` | `documented`, `dependsOn component:default/search-api` |
| `host:fx-rates.internal` | `unmatched` |
| `env:LEDGER_DSN` | `mapped_undocumented`, `component:default/ledger`, `via: "map"` |
| `host:reporting-job.internal` | `dependent_only` |

  Also: `not_observed == ["dependsOn component:default/legacy-billing"]`; `ignored` has the analytics rule with `hits == 1`; no observation of `api.example.com` or `legacy.example.com`.
- [ ] Run; the new test fails until the fixture change is in. Then run the full suite: the existing context tests must pass unchanged. None of them looks up a hotspot by id except `test_malformed_hotspot_id_is_rejected_not_crashed`, which uses `H01` (`releases.ts` stays H01).
- [ ] Commit: `Plant observed dependencies in the context fixture (#6)`.

### Task 5: Bundles brief each hotspot with its file's observations (AC-1, AC-10, AC-11)

**Files:** `scripts/bundle.py`, `tests/test_observed_pipeline.py` (new).

**Interfaces:**
- Consumes: `c.load_observed(repo)`, `observed.ref`.
- Produces: `section_observed(obs_doc: dict | None, rel: str) -> str`; `bundles/index.json` gains `observed_hash` per bundle and at the top level (`null` when skipped).

- [ ] Write failing tests over `context_scanned_repo`:
  - H01 (`src/client/releases.ts`) contains `## Dependencies observed in this file` directly after the Service context section, with the three refs from Task 4, each line in the §6 wording for its resolution;
  - H02 (`src/sync/collection.ts`) shows `not in the catalog (declared as \`component:default/ledger\`)` and `matches no documented dependency`;
  - a hotspot whose file has no observation has no such section;
  - the index carries `observed_hash` per bundle, equal to `observed.json`'s;
  - 16 observations in one file render 15 lines and `… and 1 more observed in this file` (build the document by hand and call `section_observed` directly);
  - two `observed.py` + `bundle.py` runs give byte-identical bundles (AC-11);
  - over `scanned_repo` (no context), `observed.json` is `skipped` and every bundle hash equals the one before this task (run the existing `test_no_context_means_no_section` and `test_bundles_are_within_budget_and_deterministic`; AC-10).
- [ ] Run; they fail.
- [ ] Implement `section_observed` (§6 wording verbatim, `md.code` for every ref and edge) and add it to `build_bundle` right after `service`, inside the never-trimmed part: `rest` subtracts its tokens too. Load the document once in `main` with `c.load_observed`, pass it into `build_bundle`, and write `observed_hash` into the index next to `context_hash`.
- [ ] Run the tests, then the full suite.
- [ ] Commit: `Brief each hotspot with the dependencies observed in its file (#6)`.

### Task 6: `observed` evidence and validation (AC-2)

**Files:** `scripts/validate.py`, `scripts/save_finding.py`, `scripts/bundle.py` (re-validation call), `agents/thunderstruck-investigator.md`, `tests/test_observed_pipeline.py`.

**Interfaces:**
- Consumes: `c.load_observed`, the index's per-bundle `observed_hash`.
- Produces: `EVIDENCE_TYPES` gains `"observed"`; `Validator(..., observed: dict | None = None, bundle_observed: dict[str, str | None] | None = None)`; `observed_evidence(finding, by_ref) -> list[dict]` stamping `{ref, kind, value, resolution, edge}`.

- [ ] Write failing tests, mirroring the `catalog` ones in `tests/test_context_pipeline.py` (`_catalog_finding`, `_validate`), one per rule in §7's order:
  - a finding on H01 citing `code` plus `observed host:releases-api.prod.svc.cluster.local src/client/releases.ts:<line>` validates and is stamped with `observed_evidence` (resolution `documented`, edge `dependsOn component:default/releases-api`);
  - rule 1: over `scanned_copy` (skipped), the ref is rejected with "this scan observed no dependencies, so none can be cited";
  - rule 2: after bundling, drop one observation from `observed.json` and recompute its `observed_hash` (as a re-run on a changed repository would) → every `observed` ref fails with "observations changed since bundling" (Review Focus 5);
  - rule 3: a ref with a wrong line → "no such observation; copy a ref verbatim from the bundle's 'Dependencies observed in this file' section";
  - rule 4: a finding on H01 citing H02's `observed host:fx-rates.internal src/sync/collection.ts:<line>` without citing `src/sync/collection.ts` as code → rejected; with that code ref → accepted;
  - a finding with only `observed` evidence → rejected by the existing code-evidence rule;
  - `save_finding.py` strips an investigator-supplied `observed_evidence`.
- [ ] Run; they fail.
- [ ] Implement: the evidence branch in `Validator.check_evidence` (rules 1–4, first failure reported); `_bundle_observed(repo)` beside `_bundle_context`; the stamp in `main` beside `catalog_evidence`; `"observed_evidence"` added to `save_finding.py`'s owned fields; `bundle.py`'s re-validation passes the same two arguments. Add the `observed` row to `validate.py`'s example map.
- [ ] In `agents/thunderstruck-investigator.md`, add the `observed` row to the evidence table (`an observation copied exactly from the "Dependencies observed in this file" section`) and the one rule from §7: an undocumented dependency is not by itself a finding.
- [ ] Run the tests, then the full suite. `tests/test_investigator_contract.py` must still pass.
- [ ] Commit: `Let a finding cite an observed dependency as checked evidence (#6)`.

### Task 7: The Catalog drift report section (AC-3, AC-4, AC-5, AC-6, AC-12)

**Files:** `scripts/report.py`, `skills/thunderstruck-scan/references/report-format.md`, `tests/test_observed_report.py` (new).

**Interfaces:**
- Consumes: `c.load_observed`; `links` location URLs as `_location_url` builds them.
- Produces: `render_catalog_drift(obs: dict | None, ...) -> list[str]`; `report.json` top-level `catalog_drift` (`null` when skipped) with `observed_not_documented`, `dependent_only`, `not_observed`, `ignored`, `truncated`; findings in `report.json` carry `observed_evidence`. `index.json` does not change.

- [ ] Write failing tests over the context fixture's report:
  - `## Catalog drift` follows `## Service context`, with the §8 intro sentence;
  - *Observed, not in the catalog* lists `fx-rates.internal` and `LEDGER_DSN` (with `(declared as \`component:default/ledger\`)`), each with kind, value, linked locations and count;
  - *Documented only as a dependent* lists `reporting-job.internal`;
  - *Documented, not observed* lists `dependsOn component:default/legacy-billing` in the §8 wording, which says the call may live in a shared client, generated code or outside this repository (AC-4);
  - *Ignored by the profile* prints the analytics rule, its reason and `(1 hits)`;
  - a value with more than 3 locations shows 3 and `+N`;
  - a `truncated.catalog_edges > 0` document prints the 25-per-direction note;
  - over `scanned_copy`, the report has no `Catalog drift` heading and `report.json`'s `catalog_drift` is `null` (AC-10; `test_report_without_context_is_unchanged` still passes);
  - an observed value `` evil`](x)<b> `` can't occur (it fails the §2 patterns), so inject one into `observed.json` by hand and assert `report.md` renders it inert: add the case to the existing inert-text tests in `tests/test_inert_report.py` (AC-12).
- [ ] Run; they fail.
- [ ] Implement `render_catalog_drift` with every value through `md.code` and every location through `md.linked`, call it right after `render_service_context` in `render_markdown`, and add `catalog_drift` to `render_json`. Document both fields in `report-format.md`.
- [ ] Run the tests, then the full suite.
- [ ] Commit: `Report catalog drift in both directions (#6)`.

### Task 8: Scan skill, sample report, docs and version

**Files:** `skills/thunderstruck-scan/SKILL.md`, `skills/thunderstruck-scan/references/orchestration.md`, `scripts/gen_sample_report.py`, `examples/sample-report.md` (generated), `README.md`, `CLAUDE.md` (Commands, Architecture), `CHANGELOG.md`, and the version in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`.

- [ ] Add **Step 1c — observed dependencies** to the scan skill, after Step 1b: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/observed.py"`; relay its warnings as in step 1; it never stops the scan. Mirror it in `orchestration.md`. `tests/test_plugin_paths.py` covers the `${CLAUDE_PLUGIN_ROOT}` form; run it.
- [ ] In `gen_sample_report.py`, call `add_observed_dependencies(repo)` after `add_service_context`, run `observed.py` between `context.py` and `bundle.py`, and give the `client/releases.ts` canned finding an `"observed": ["host:releases-api.prod.svc.cluster.local"]` entry that the generator turns into the full ref with `_line_of(repo, hs["file"], "releases-api.prod.svc.cluster.local")`. Add `"observed"` to the keys the generator leaves out of the finding item, next to `"catalog"`. Fail generation, like the Service context check, if `## Catalog drift` is missing.
- [ ] Regenerate: `uv run scripts/gen_sample_report.py`, then `uv run scripts/gen_sample_report.py --check` exits 0. This is the one intended change to a generated file (§11).
- [ ] Docs: add `observed.py` to the CLAUDE.md architecture diagram and Commands block (`uv run scripts/observed.py --repo /path/to/repo`), a README paragraph on catalog drift and the `[observed]` table, and the `[observed]` example to `examples/thunderstruck.toml.example`.
- [ ] CHANGELOG: a new minor version (`0.9.0` if `main` is still on `0.8.x`, else the next minor after `main`'s) stating that enabling the feature re-investigates, once, only hotspots whose file calls something (§6). Update the three manifests to the same version; `test_versions_agree` passes.
- [ ] Run the four checks from the ticket agent's step 7: the full suite, `gen_catalog_docs.py --check`, `gen_sample_report.py --check`, `claude plugin validate . --strict`.
- [ ] Commit: `Run observed.py in every scan and show catalog drift in the sample (#6)`.
