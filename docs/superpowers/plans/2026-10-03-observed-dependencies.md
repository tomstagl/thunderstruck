# Observed Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A scan links each documented outbound dependency to the files and lines that call it, lets a finding cite such a link as checked evidence, and reports catalog drift in both directions.

**Architecture:** A new deterministic step, `scripts/observed.py`, reads the repository's tracked files, `hotspots.json` and `context.json` and writes `.thunderstruck/observed.json`. Hosts are observed only at call sites and env vars in code by use (spec §2). `context.py` gains the service's own hosts from one catalog annotation. `bundle.py` briefs each hotspot with its file's observations, `validate.py` resolves `observed` evidence, and `report.py` renders a **Catalog drift** section. No model call and no network call are added anywhere.

**Tech Stack:** Python 3.11+, PyYAML (`yaml.compose_all` for line numbers), `uv`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-observed-dependencies-design.md`, as amended on 2026-10-22 (§n below refers to it). Requirements AC-1…AC-12 are in GitHub issue #6.

**Branch:** `feat/observed-dependencies`. One commit per task. The full suite passes on every commit, and its real exit code is checked, never piped through `tail`:

```bash
uv run --with pytest --with pyyaml --with lizard --with markdown-it-py==4.2.0 --with linkify-it-py==2.2.0 --with cmarkgfm==2025.10.22 pytest tests/ -q; echo "exit=$?"
```

## Global Constraints

- `observed.py` imports no network library and runs no subprocess other than `git` through `_common` (§10).
- Detection, matching, hashing and rendering never depend on model output (CLAUDE.md, governing rule).
- Bundles, `observed.json` and the drift section are byte-identical across runs on an unchanged repository and catalog (AC-11). No timestamp, absolute path or dict-order dependence.
- Without usable service context, every bundle and the report are byte-identical to `main` (AC-10).
- Without the own-hosts annotation, `context.json` and its `context_hash` are byte-identical to `main` (§2.6).
- Every repository-sourced value reaches Markdown only through `mdtext.code`; every location link through `mdtext.linked` (AC-12).
- No secret value, URL userinfo, URL path or source-line text in any file under `.thunderstruck/` (AC-8, §10). `own_hosts` never appears in a bundle or the report (§2.6).
- **Only measured forms ship** (§12): every request, response, connect, read, configuration and mesh form in `catalog/observed.yaml` has its id in the calibration doc's *Measured forms* table. Task 1 adds the test that enforces it.
- `VALIDATION_RULES` stays at its current value (§7).
- At most one warning per invalid `[observed]` entry; an invalid entry never disables the feature (§4).
- Caps: 2000 observations total, 20 per distinct value, observations in ranked hotspot files never capped; 15 bundle lines; 3 report locations per value; `--limit` 3000 files; argument lists at most 2000 characters (§2.2, §2.5, §5, §6, §8).

## Review Focus

1. **A URL whose userinfo holds an `@` or a `/`** (`postgres://u:p@ss/w@db.internal/x`): only `db.internal` may be observed, and no fragment of the password anywhere. Pinned in Task 1's secret-safety sample.
2. **The same host in a comment and in code on adjacent lines**: only the code line is an observation. Pinned in Task 1's samples.
3. **A minified or generated file** whose call parentheses don't balance within 2000 characters: no env use from that call, no crash, no warning (§9). Pinned in Task 2.
4. **A neighbour name equal in two namespaces** (`component:a/ledger`, `component:b/ledger`): `ambiguous`, never `documented`, and neither candidate edge appears in `not_observed` or `no_mapping`. Pinned in Task 4.
5. **`observed.json` edited by hand** without recomputing `observed_hash`: it is treated as missing (§9), so no ref is accepted from it. Edited *and* rehashed after bundling: rule 2 rejects every ref. Pinned in Tasks 5 and 8.

---

### Task 0: The spike re-run (maintainer, before any other task)

**Files:** `docs/calibration/observed-dependencies.md` (from PR #88, which merges first), extended by the maintainer in its own PR with a second run. The spike script and the ground-truth files are not committed (§12).

This task needs hand-written ground truth and a person to review the sample. The nightly ticket agent cannot do it. **Agent rule:** stop at Task 0 as *Blocked* with the gap "the spike re-run is not recorded" unless `docs/calibration/observed-dependencies.md` on `origin/main` has a `## Measured forms` table and its **last** line starting `Verdict:` is `Verdict: go`. (Run 1's `Verdict: no-go …` line stays in the doc above it.)

**Candidate forms.** The spike script, the doc and `catalog/observed.yaml` name each form by this id. A form ships only if the doc lists it as measured. The patterns are the spec's (§2.1, §2.2) written out; they run over comment-blanked text.

| Id | Language | Kind | Pattern |
|---|---|---|---|
| `ts.request.fetchlike` | typescript | request | `\b\w*(?:fetch\|Fetch\|request\|Request)\w*\(` |
| `ts.request.axios` | typescript | request | `\baxios\b` |
| `ts.request.got` | typescript | request | `\bgot\(` |
| `ts.request.ky` | typescript | request | `\bky\.` |
| `ts.request.node-https` | typescript | request | `\bhttps?\.(?:request\|get)\(` |
| `ts.request.undici` | typescript | request | `\bundici\b` |
| `ts.response.json` / `.text` / `.status` / `.ok` / `.data` / `.headers` / `.arraybuffer` / `.blob` | typescript | response | `\.json\(\)`, `\.text\(\)`, `\.status\b`, `\.ok\b`, `\.data\b`, `\.headers\b`, `\.arrayBuffer\(\)`, `\.blob\(\)` |
| `ts.connect.grpc-client` | typescript | connect | `\bnew\s+\w+Client\(` whose argument list matches `ChannelCredentials\|credentials\.` |
| `ts.connect.mongoose` / `.pool` / `.create-connection` / `.mongo-client` / `.create-client` | typescript | connect | `\bmongoose\.connect\(`, `\bnew\s+Pool\(`, `\bcreateConnection\(`, `\bnew\s+MongoClient\(`, `\bcreateClient\(` |
| `ts.read.dot` / `.bracket` / `.destructure` | typescript | read | `process\.env\.([A-Z][A-Z0-9_]*)`, `process\.env\[\s*['"]([A-Z][A-Z0-9_]*)['"]\s*\]`, `\{([^}]*)\}\s*=\s*process\.env\b` |
| `py.request.requests` / `.httpx` / `.dot-request` | python | request | `\brequests\.(?:get\|post\|put\|patch\|delete\|request)\(`, `\bhttpx\.`, `\.request\(` |
| `py.response.json` / `.text` / `.status-code` / `.content` / `.headers` | python | response | `\.json\(\)`, `\.text\b`, `\.status_code\b`, `\.content\b`, `\.headers\b` |
| `py.connect.grpc-channel` / `.psycopg` / `.create-engine` / `.redis` / `.redis-url` / `.mongo-client` | python | connect | `\bgrpc\.(?:insecure\|secure)_channel\(`, `\bpsycopg2?\.connect\(`, `\bcreate_engine\(`, `\bredis\.Redis\(`, `\bRedis\.from_url\(`, `\bMongoClient\(` |
| `py.read.environ-index` / `.environ-get` / `.getenv` | python | read | `os\.environ\[\s*['"](NAME)['"]\s*\]`, `os\.environ\.get\(\s*['"](NAME)['"]`, `os\.getenv\(\s*['"](NAME)['"]` |
| `java.request.httpclient` / `.resttemplate` / `.webclient` | java | request | `\.send(?:Async)?\(`, `\b(?:getForObject\|getForEntity\|postForObject\|exchange)\(`, `\.retrieve\(\)` |
| `java.response.body` / `.get-body` / `.status-code` / `.get-status-code` / `.body-to-mono` | java | response | `\.body\(\)`, `\.getBody\(\)`, `\.statusCode\(\)`, `\.getStatusCode\(\)`, `\.bodyToMono\(` |
| `java.connect.managed-channel` / `.driver-manager` | java | connect | `\bManagedChannelBuilder\.forTarget\(`, `\bDriverManager\.getConnection\(` |
| `java.read.getenv` | java | read | `System\.getenv\(\s*"(NAME)"\s*\)` |
| `config.env.k8s-name` | yaml | config | a Kubernetes container `env[].name` |
| `config.env.placeholder` | yaml, properties | config | `\$\{(NAME)(?::[^}]*)?\}` |
| `config.env.spring-value` | java | config | `@Value\(\s*"\$\{([a-z0-9.-]+)(?::[^}]*)?\}"` |
| `config.host.key` | yaml, properties | config | a URL value whose key's last segment contains `url`, `uri`, `endpoint`, `host`, `base` or `api` (any case) |
| `mesh.service-entry` | yaml | mesh | `ServiceEntry` `spec.hosts[]` |

`NAME` is `[A-Z][A-Z0-9_]{0,63}`. The variable binding forms of §2.2 (assignment, destructuring) are part of the `read` ids, not separate forms.

- [ ] Confirm PR #88 has merged, so `docs/calibration/observed-dependencies.md` is on `main`.
- [ ] Clone `open-telemetry/opentelemetry-demo` into a scratch directory and check out `ad06a6f9df40abde6c1f0c58b29b92f1076a74ec`.
- [ ] Write the ground truth, before running anything, into a scratch `prereg/` directory outside the clone:
  - `catalog.json`: for each service under test (`src/frontend`, `src/recommendation`, `src/ad`, `src/chatbot`), its outbound edges as `dependsOn component:default/<service>`, taken only from the demo's architecture documentation on opentelemetry.io (note the page URLs). A service the documentation gives no edges for is dropped from linkage and recall, and the doc says so;
  - `map.toml`: one `[[observed.map]]` per edge, naming the env vars and hosts that reach it, taken from the clone's `docker-compose.yml` and `.env` (both excluded from scanning by the shared filter);
  - `own_hosts.txt`: per service, its own hosts from the same documentation, or empty;
  - `seen.txt`: the files read before the freeze (`src/frontend/gateways/rpc/Cart.gateway.ts`, `src/frontend/gateways/http/Shipping.gateway.ts`, and a code-search path list for `_ADDR`, `httpx`, `requests.post`, `ManagedChannelBuilder`, `HttpClient`).
- [ ] Write the throwaway spike script: §2 with every candidate form above, §2.4–§2.6, §3 including the map, and the §3 classification. Per observation it records which form ids matched, and per file which request and response forms passed the file gate. It runs per service with that service's directory as the path.
- [ ] Freeze: record in `prereg/freeze.txt` the demo commit, the script's sha256 and the sha256 of each ground-truth file. Do not change the script after this point; a bug found later is reported, not fixed in this run.
- [ ] Run it per service. Record counts only: linkage (documented outbound edges linked to at least one file, per service); every mapped edge with no observation and the reason it was missed; distinct values per resolution; dropped values per kind; own hosts excluded; env reads used in a call in a different file (the cross-file gap, counted by searching each mapped env var across the service).
- [ ] Review the unmatched values of the four services, pooled: 30, every k-th of the sorted list, or all if there are fewer. Mark each "real dependency" or "noise".
- [ ] Derive the measured forms: a form is measured when at least one observation that the review or the ground truth marks real was made through it (for a response form: the observation's file passed the gate through it), and that form's values were in the noise review. Every other candidate is unmeasured.
- [ ] Add a `## Run 2: OpenTelemetry demo` section to `docs/calibration/observed-dependencies.md` with the repository and commit, the ground-truth sources and hashes, `seen.txt`, the counts, the review, and a `## Measured forms` table, one row per measured form: `| Id | Language | Real dependencies observed through it |`. End the doc with exactly one of:
  - `Verdict: go` — at most one in five reviewed values is noise (6 of 30), and every missed mapped edge is missed for a reason §2 documents as a known gap;
  - `Verdict: no-go — <what to narrow>` — then change the spec (§2) before this plan continues.

### Task 1: Rules catalog, host and secret extraction (AC-8, AC-9)

**Files:** `catalog/observed.yaml` (new), `scripts/observed.py` (new; extraction only), `tests/observed/samples/<kind>/<language>/…` (new), `tests/observed/test_observed_samples.py` (new), `tests/observed/test_measured_forms.py` (new).

**Interfaces:**
- Produces, in `scripts/observed.py`:
  - `load_rules(root: Path | None = None) -> dict`: `catalog/observed.yaml` parsed, patterns compiled, forms grouped as `rules["forms"][lang][kind] -> list[(id, pattern)]`.
  - `observe_text(text: str, lang: str, rel: str, rules: dict, own_hosts: list[str]) -> Extraction`, where `Extraction` is a dataclass with `observations: list[dict]` (`{"kind", "value", "file", "line"}`, file order), `dropped: dict[str, int]`, `excluded_own_host: int`, `yaml_failed: bool`. Task 2 adds env to the same function.
  - `ref(obs: dict) -> str`: `f"observed {kind}:{value} {file}:{line}"`.
  - `is_own_host(host: str, own_hosts: list[str]) -> bool`.

- [ ] Write `catalog/observed.yaml` with schema `thunderstruck.observed-rules/v2`:
  - `forms`: per language, per kind (`request`, `response`, `connect`, `read`, `config`, `mesh`), a list of `{id, pattern}`. **Only the ids in the calibration doc's *Measured forms* table**, with the patterns from Task 0's candidate table. `javascript` is covered by the catalog's `aliases`.
  - `api_name`: `(?i)(?:\b\w*(?:api|base|endpoint)\w*\s*[:=]\s*|new\s+URL\(\s*)` (§2.1 rule 2, matched against the 60 characters before the literal's opening quote).
  - `config_env_suffixes: [_URL, _URI, _HOST, _HOSTNAME, _ENDPOINT, _ADDR, _DSN, _CONNECT, _SERVER]`.
  - `config_host_key_words: [url, uri, endpoint, host, base, api]`.
  - `generic_first_labels: [api, www, app, cdn, static]` (used by Task 4).
  - `secret_calls`, `exclude_hosts` (`exact`, `suffix`, `prefix: [docs.]`, `ipv4_loopback: true`) unchanged from the spec's §2.3–§2.4 lists.
- [ ] Write `tests/observed/test_measured_forms.py`: `test_only_measured_forms_ship` parses the `## Measured forms` table of `docs/calibration/observed-dependencies.md` and asserts every form id in `observed.yaml` is in it; `test_every_form_has_a_positive_sample` asserts each id appears in at least one sample's `.expected` provenance (see the next step).
- [ ] Add the host and secret samples. Layout: `tests/observed/samples/<kind>/<language>/{positive,negative}_<topic>.<ext>`. Every positive has a sibling `<file>.expected` with one `<kind>:<value>:<line>` per line, sorted, and a first comment line `# forms: <id>, <id>` naming the forms it exercises. A negative yields no observation of its directory's kind. Only samples for shipped forms exist. At minimum (§11, Review Focus 1–2):
  - `host` positives: `fetchWithRetry("https://ledger.internal/v1/x")` then `.json()`; `const apiBase = "https://ledger.internal"` with a `fetch(` and `.ok` in the file; `new URL("https://ledger.internal")`; the userinfo URLs `postgres://app:hunter2@db.internal/app` and `postgres://u:p@ss/w@db.internal/x` in a requesting file, each expecting only `db.internal`; the same URL commented out on the line above the call, expecting only the call's line; `yaml/positive_key.yaml` (`payments.base-url: https://payments-api.internal/v1`) if `config.host.key` shipped; `yaml/positive_service_entry.yaml` if `mesh.service-entry` shipped.
  - `host` negatives: a press/footer link table (`https://news-site.internal/review/1`) in a file with no request form; the same table in a requesting file but as bare hosts with no path or API name; a URL in a file that requests but reads no response; a `VirtualService` and a `DestinationRule`; an own host and its subdomain (`own_hosts=["fixture-app.internal"]`, passed by the test); `localhost`, `127.0.0.2`, `example.com`, `svc.test`, `json-schema.org`, `docs.python.org`, `${HOST}`, `{{ .Values.host }}`; a commented-out URL alone.
  - `secret`: as specified before the amendment: `yaml/positive_externalsecret.yaml` (`data[].remoteRef.key`, `dataFrom[].extract.key`), `yaml/positive_vault_annotation.yaml`, `yaml/positive_csi.yaml`, one code positive per language; negatives a 40-character `[A-Za-z0-9]` literal passed to `getSecretValue` and a secret call in a comment.
- [ ] Write `tests/observed/test_observed_samples.py`: discover samples from the tree; each positive's projection to `kind:value:line` equals `.expected`; each negative yields nothing of its kind; `test_every_kind_has_both_samples` for every `(kind, language)` that has at least one shipped form (aliases excluded as before); a secret-safety test that `hunter2`, `p@ss`, the 40-character literal and any URL path appear in no serialised `observe_text` output; an own-host test that the excluded host is counted in `excluded_own_host` and never returned.
- [ ] Run them; they fail with `ModuleNotFoundError: observed`.
- [ ] Implement host and secret extraction in `scripts/observed.py`:
  - Blank comments with `c.strip_comments(text, lang)`; string contents stay.
  - File gate (§2.1 rule 1): the blanked text matches at least one shipped `request` and one shipped `response` pattern of the language. YAML and properties have no gate; they use `config.host.key` and `mesh.service-entry` only.
  - URL: `(?P<scheme>[a-z][a-z0-9+.-]{1,15})://(?:[^\s/'"`@]*@)*(?P<host>[^\s/'"`:?#\]\[]+)(?::\d+)?(?P<path>/[^\s'"`]*)?`. Rule 2: `path` is longer than `/`, or `api_name` matches the 60 characters before the opening quote. `path` is read and discarded.
  - Normalise (lowercase, strip port and trailing dot), the §2.1 pattern and 253-character check, the §2.4 exclusions, then `is_own_host` (equal, or ends with `.` + entry; a `*.x` entry matches subdomains of `x` only).
  - YAML structural forms via `yaml.compose_all`; a scalar's line is `node.start_mark.line + 1`. On `yaml.YAMLError`, skip structural forms and set `yaml_failed`. `config.host.key` is a line form: `^\s*([\w.-]+)\s*[:=]\s*['"]?<URL>`.
  - Secret forms as §2.3. A value failing its kind's pattern increments `dropped[kind]` and is never returned.
- [ ] Run the sample tests, then the full suite.
- [ ] Commit: `Observe hosts at call sites and secret references in tracked files (#6)`.

### Task 2: Env vars by use and by name (AC-9)

**Files:** `scripts/observed.py`, `tests/observed/samples/env/<language>/…`, `tests/observed/test_env_use.py` (new).

**Interfaces:**
- Consumes: Task 1's `load_rules`, `Extraction`, the shipped `request` and `connect` forms.
- Produces: `observe_text` also returns `env` observations; `call_spans(blanked: str, rules: dict, lang: str) -> list[tuple[int, int]]` (start and end offsets of each request or connect call's argument list).

- [ ] Write failing tests in `test_env_use.py` and env samples (each `.expected` names its forms):
  - direct: ``fetch(`${process.env.AUTH_SERVER}/verify`)`` → `env:AUTH_SERVER` on that line; `mongoose.connect(process.env.DB_CONNECT)` → `env:DB_CONNECT` (if `ts.connect.mongoose` shipped);
  - one variable: `const base = process.env.AUTH_SERVER;` then on line 9 `fetch(base + "/verify")` → `env:AUTH_SERVER` at line 9, not at the read's line; a variable used in three calls → three observations;
  - destructuring: `const { CART_ADDR = '' } = process.env;` then `new CartServiceClient(CART_ADDR, ChannelCredentials.createInsecure())` → `env:CART_ADDR` at the client line; `const { SHIPPING_ADDR: ship } = process.env;` then ``fetch(`${ship}/get-quote`)`` → `env:SHIPPING_ADDR`;
  - Python `addr = os.environ.get("PRODUCT_CATALOG_ADDR", "")` then `grpc.insecure_channel(addr)`, and Java `String t = System.getenv("X_ADDR");` then `ManagedChannelBuilder.forTarget(t)`, only for shipped forms;
  - config by name: a container `env[].name: LEDGER_ADDR` and `${PRODUCT_CATALOG_ADDR:localhost:3550}` observed; `${LEDGER_ADDRESS}` and `${LOG_LEVEL}` not; `@Value("${payments.base-url}")` → `env:PAYMENTS_BASE_URL`;
  - not observed (the §2.2 gaps, pinned): `process.env.LOG_LEVEL` read and never used in a call; `new S3Client({ endpoint: process.env.S3_URL })`; a second hop (`const b = a + "/v1"; fetch(b)`); an object field (`cfg.auth = process.env.X; fetch(cfg.auth)`); `export const X = process.env.X_URL` used by no call in the file;
  - Review Focus 3: a 3000-character single-line call with an unbalanced `(` containing `process.env.X_URL` → no observation, no exception, no warning.
- [ ] Run; they fail.
- [ ] Implement:
  - `call_spans`: for each shipped `request` or `connect` match, scan from its `(` to the balancing `)` in the blanked text, counting only parentheses outside string literals; give up after 2000 characters. `ts.connect.grpc-client` keeps a span only if it matches `ChannelCredentials|credentials\.`.
  - Reads: every shipped `read` match with its offset. Bindings: a read that is the whole right-hand side of `(?:const|let|var)\s+(\w+)\s*=`, `^\s*(\w+)\s*=` (Python) or `\b\w+\s+(\w+)\s*=` (Java) binds that name; `ts.read.destructure` binds each `NAME`, or its alias after `:`, with an optional `= default`.
  - Observations: a read whose offset lies inside a span → at the read's line. A bound name matching `\bname\b` inside a later span → at that occurrence's line, valued with the env var's name. A read not used either way yields nothing.
  - Config forms: `config.env.*` with the `config_env_suffixes` rule; Spring keys `.`/`-` → `_`, uppercase.
- [ ] Run the tests, then the full suite.
- [ ] Commit: `Observe env vars by their use in a call, and by name in configuration (#6)`.

### Task 3: The service's own hosts from its catalog entry (§2.6)

**Files:** `scripts/context.py`, `scripts/context_extract.py`, `scripts/_common.py` (`_well_formed_context`), `tests/test_context_own_hosts.py` (new).

**Interfaces:**
- Produces:
  - `context_extract.extract_own_hosts(entity: dict, annotation: str) -> tuple[list[str], int]`: the valid hosts, sorted and deduplicated, and the count of rejected entries.
  - `context_extract.context_hash(entity_ref, edges, truncated, own_hosts: list[str] | None = None)`: `own_hosts` is in the canonical JSON only when non-empty, so the hash is unchanged without it.
  - `context.json` gains `own_hosts: [...]` only when non-empty.
  - `context.DEFAULT_OWN_HOSTS_ANNOTATION = "thunderstruck.io/own-hosts"`, read from the profile's `[observed] own_hosts_annotation`.

- [ ] Write failing tests:
  - an entity with `thunderstruck.io/own-hosts: "shop.internal, *.api.shop.internal"` → `own_hosts == ["*.api.shop.internal", "shop.internal"]` in a `fresh` `context.json`;
  - a bad entry (`"shop.internal, not a host!"`) is dropped with one warning that names the annotation and contains no part of the bad value;
  - without the annotation, `context.json` has no `own_hosts` key and `context_hash` equals the value `main` computes for the same edges (call `context_hash` without the argument and compare);
  - `[observed] own_hosts_annotation = "example.com/hosts"` reads that key instead, and changing it does not change `config_hash` (no re-approval);
  - a `cached` document keeps its `own_hosts`, and `_reusable` recomputes the hash including them;
  - `c.load_service_context` accepts a document with `own_hosts` and rejects one where it is not a list of strings.
- [ ] Run; they fail.
- [ ] Implement: in `fetch_source`, after extracting edges, call `extract_own_hosts(main.doc, annotation)` (the annotation passed in from `resolve`, which reads it from `profile.get("observed", {})`); carry the hosts on `SourceResult`; pass them to `context_hash` and into the document in `resolve` and `_reusable`; extend `_well_formed_context`. Each entry must match the §2.1 host pattern with an optional leading `*.`.
- [ ] Run the tests, then the context suites (`tests/test_context_*.py`) and the full suite.
- [ ] Commit: `Read the service's own hosts from one catalog annotation (#6)`.

### Task 4: Matching and the `[observed]` profile table (AC-4, AC-5, AC-6, AC-7)

**Files:** `scripts/observed.py`, `tests/test_observed_match.py` (new).

**Interfaces:**
- Consumes: observation dicts from Tasks 1–2; `context.json` edges `{"ref", "type", "direction", "neighbour", "attributes"}`.
- Produces:
  - `load_config(profile: dict) -> tuple[dict, list[str]]`: `{"own_hosts_annotation": str, "map": [{"entity", "host": [...], "env": [...], "secret": [...]}], "ignore": [{"kind", "value", "reason"}]}` plus one warning per dropped entry.
  - `map_hash(cfg: dict) -> str`: sha256 of the canonical JSON of `map` and `ignore`.
  - `match_name(kind: str, value: str, rules: dict) -> str | None`: the §3 rule 3 name, or `None` for a generic first label.
  - `resolve(observations: list[dict], edges: list[dict], cfg: dict, rules: dict) -> dict`: `{"resolutions", "not_observed", "no_mapping", "ignored"}` in the §5 shapes, sorted per §5.

- [ ] Write failing unit tests (§11 "Matching unit tests", "Config validation"):
  - ignore beats map, map beats name; an ignored observation's resolution is `ignored` and it stays in the input list (Task 5 keeps it in `observations`);
  - `host` first label: `payments-api.prod.svc.cluster.local` → `payments-api`; `payments.internal` doesn't match `payments-api`; `api.vendor.internal` → `None`, even with a neighbour called `api`;
  - `env`: `PAYMENTS_API_URL` → `payments-api`, `CART_ADDR` → `cart`, `DB_CONNECT` → `db`, `LEDGER_ADDRESS` → `ledger-address` (not a suffix any more), `AUTH` → `auth`;
  - `secret`: last segment, lowercased;
  - `documented`, `dependent_only`, `mapped_undocumented`, `unmatched` as before;
  - `ambiguous` for `component:a/ledger` and `component:b/ledger`, with both refs; neither edge appears in `not_observed` or `no_mapping` (Review Focus 4);
  - an outbound edge with a map entry and no observation → `not_observed`; without a map entry → `no_mapping`; an edge reached by an exact-name match without a map entry → in neither list;
  - `ignored` carries `rule` (`"host api.vendor.internal"`), `reason`, `hits`; `*.vendor.internal` matches `a.vendor.internal`, not `vendor.internal`;
  - config: a bad entity ref, a value in two map entries (the second dropped), an ignore rule with two kinds, one without a reason, and a non-string `own_hosts_annotation` each yield one warning and leave the rest working.
- [ ] Run; they fail.
- [ ] Implement `load_config`, `map_hash`, `match_name` and `resolve`. Neighbour names are the part after `/` in the entity ref, lowercased. The entity-ref check uses `context_extract.ENTITY_REF`.
- [ ] Run the tests, then the full suite.
- [ ] Commit: `Match observations by declared map first, then exact name (#6)`.

### Task 5: `observed.py` writes `observed.json` (AC-10, AC-11)

**Files:** `scripts/observed.py` (CLI, file walk, document), `scripts/_common.py`, `tests/test_observed_doc.py` (new).

**Interfaces:**
- Consumes: Tasks 1–4; `c.load_service_context`, `c.tracked_index`, `c.path_problem`, `c.tracked_file_problem`, `c.is_utf8`, `c.Filters.from_profile`, `c.language_map`, `c.detect_language`; `hotspots.json` (`config.path`, `config.include_tests`, the ranked files).
- Produces: `run(repo: Path, limit: int = 3000) -> dict` and `main(argv) -> int`; `.thunderstruck/observed.json` with schema `thunderstruck.observed/v1` and exactly the §5 fields (including `no_mapping`, `own_hosts_known`, `excluded`); `OBSERVED_FILENAME = "observed.json"` and `OBSERVED_SCHEMA` in `_common.py`; `c.load_observed(repo) -> dict | None`, returning the document only when `status == "ok"`, the schema matches and `observed_hash` equals the hash recomputed from its content.

- [ ] Write failing tests over a small `tmp_path` git repository built with `isolated_git_env()`, a hand-written `context.json` (status `fresh`, a valid `context_hash`) and a hand-written `hotspots.json`:
  - no `context.json`, or status `untrusted`: `{"schema", "status": "skipped", "reason"}` and nothing else;
  - `ok`: the §5 fields; observations sorted by `(file, line, kind, value)`; `observed_hash` covers exactly `observations`, `resolutions`, `not_observed`, `no_mapping`, `truncated`; an ignored observation is in `observations`;
  - `own_hosts_known` is false without `own_hosts` in `context.json`; `excluded.own_host` counts an own-host URL that is never listed;
  - `hotspots.json` with `config.path = "svc-a"` → files outside `svc-a/` are not read; `include_tests: true` → a `tests/` file is read; no `hotspots.json` → the whole repository, with one warning;
  - two runs give byte-identical files (AC-11), and adding a warning leaves `observed_hash` unchanged;
  - caps: 21 occurrences of one host in a non-hotspot file keep 20 and count 1 in `truncated.observations`; 21 in a ranked hotspot file keep all 21; `--limit 2` stops after two files with a warning naming the limit;
  - untracked files and files the profile's `[filters]` exclude are not read;
  - a Helm-style YAML file with `{{ .Values.x }}` and `${LEDGER_URL}` yields `env:LEDGER_URL` and one warning `1 YAML file(s) could not be parsed; …` (if `config.env.placeholder` shipped);
  - `c.load_observed` returns `None` for a document edited without recomputing `observed_hash` (Review Focus 5);
  - `truncated.outbound > 0` in `context.json` sets `truncated.catalog_edges`;
  - no file under `.thunderstruck/` contains `hunter2` or a URL path after scanning `fetch("postgres://app:hunter2@db.internal/app/secret-path")` (§11 "Secret safety").
- [ ] Run; they fail.
- [ ] Implement the walk (§2.5): files from `c.tracked_index(repo)`, the acceptance checks `signals.py` applies to ranked files, the `hotspots.json` path and test scope, a language from `language_map`, sorted, stopped at `--limit`. Then caps (hotspot files first), `resolve`, hashes and `c.write_json`. Print one line: `observed: <n> observation(s), <d> documented, <u> not in the catalog, <m> not observed, <k> no mapping` or `observed: skipped (<reason>)`.
- [ ] Run the tests, then the full suite.
- [ ] Commit: `Write observed.json from tracked files and the service context (#6)`.

### Task 6: Fixture with planted dependencies (success measure "after the build")

**Files:** `tests/fixtures/fake_catalog.py`, `tests/fixtures/build_fixture.py`, `tests/conftest.py`, `tests/test_observed_fixture.py` (new).

**Interfaces:**
- Produces: `build_fixture.add_observed_dependencies(repo: Path) -> None`; `context_scanned_repo` also runs `observed.py` between `context.py` and `bundle.py`.

The additions use only forms the OpenTelemetry frontend exercises (`ts.request.fetchlike`, `ts.response.ok`/`.json`, `ts.read.destructure`, `ts.connect.grpc-client`). If Task 0 did not ship one of them, replace it with a shipped form before starting and say so in the PR.

- [ ] In `fake_catalog.py`, add to the main entity three outbound edges (`component:default/search-api`, `component:default/legacy-billing`, `resource:default/orders-db`) and one inbound edge (`component:default/reporting-job`), each with a `neighbour(...)` entry, and the annotation `"thunderstruck.io/own-hosts": "fixture-app.internal"`.
- [ ] Add `add_observed_dependencies` to `build_fixture.py`. It appends to the three top-ranked files, writes `deploy/search-externalsecret.yaml` (an `external-secrets.io/v1beta1` `ExternalSecret` named `search` whose `spec.data[0]` is `{secretKey: token, remoteRef: {key: secret/data/search-api}}`), commits them in one commit dated one day after the last (as `add_service_context`'s neighbours do, with the fixture author), and appends the untracked profile entries. The planted lines:

| File | Appended code | Expect |
|---|---|---|
| `src/client/releases.ts` | `const { RELEASES_API_URL = '' } = process.env;` and a function doing ``fetch(`${RELEASES_API_URL}/v1/releases`)`` then `res.json()` | `env:RELEASES_API_URL` documented by name (`releases-api`) |
| same | `export const PAYMENTS_API_BASE = "https://payments-api.internal";` | `host:payments-api.internal` documented by name |
| `src/sync/collection.ts` | a function fetching `"https://fx-rates.internal/v1/latest"`, reading `res.ok` | `unmatched` |
| same | `const { LEDGER_ADDR = '' } = process.env;` and `new LedgerServiceClient(LEDGER_ADDR, ChannelCredentials.createInsecure())` | `mapped_undocumented`, `component:default/ledger`, `via: "map"` |
| `src/sync/scheduler.ts` | fetches of `"https://reporting-job.internal/hooks/sync-done"`, `"https://collector.analytics-vendor.internal/events"` and `"https://fixture-app.internal/api/ping"`, reading `res.ok` | `dependent_only`; `ignored`; excluded as own host |

  Profile entries: a map `entity = "component:default/ledger"`, `env = ["LEDGER_ADDR"]`; a map `entity = "component:default/legacy-billing"`, `host = ["billing.internal"]`; the analytics ignore rule with its reason.
- [ ] In `conftest.py`, call `add_observed_dependencies(repo)` in `context_repo_template` after `add_service_context`, and add `["observed.py"]` to `context_scanned_repo` after `["context.py"]`. `fixture_repo` and `scanned_repo` don't change.
- [ ] Write `tests/test_observed_fixture.py` over `context_scanned_repo`, asserting the table's resolutions exactly, plus: `secret:secret/data/search-api` documented; `not_observed == ["dependsOn component:default/legacy-billing"]`; `no_mapping == ["dependsOn resource:default/orders-db"]`; `ignored` has the analytics rule with `hits == 1`; `excluded.own_host == 1`; no observation of `api.example.com` or `legacy.example.com`.
- [ ] Run; the new test fails until the fixture change is in. Then the full suite: the existing context tests pass unchanged except those that pin the context fixture's edge list or `context_hash`, which get the new edges and annotation. `releases.ts` stays H01; check `test_malformed_hotspot_id_is_rejected_not_crashed`.
- [ ] Commit: `Plant observed dependencies in the context fixture (#6)`.

### Task 7: Bundles brief each hotspot with its file's observations (AC-1, AC-10, AC-11)

**Files:** `scripts/bundle.py`, `tests/test_observed_pipeline.py` (new).

**Interfaces:**
- Consumes: `c.load_observed(repo)`, `observed.ref`.
- Produces: `section_observed(obs_doc: dict | None, rel: str) -> str`; `bundles/index.json` gains `observed_hash` per bundle and at the top level (`null` when skipped).

- [ ] Write failing tests over `context_scanned_repo`:
  - H01 (`src/client/releases.ts`) has `## Dependencies observed in this file` directly after the Service context section, with its two refs, each in the §6 wording for its resolution;
  - H02 (`src/sync/collection.ts`) shows `not in the catalog (declared as \`component:default/ledger\`)` and `matches no documented dependency`;
  - the scheduler's analytics ref is listed as `ignored by the profile: third-party analytics; tracked outside the catalog`, and the own-host URL is not listed;
  - a hotspot whose file has no observation has no such section;
  - the index carries `observed_hash` per bundle, equal to `observed.json`'s;
  - 16 observations in one file render 15 lines and `… and 1 more observed in this file` (call `section_observed` directly);
  - two `observed.py` + `bundle.py` runs give byte-identical bundles (AC-11);
  - over `scanned_repo` (no context), `observed.json` is `skipped` and every bundle hash equals the one before this task (`test_no_context_means_no_section`, `test_bundles_are_within_budget_and_deterministic`; AC-10).
- [ ] Run; they fail.
- [ ] Implement `section_observed` (§6 wording verbatim, `md.code` for every ref and edge) and add it to `build_bundle` right after `service`, inside the never-trimmed part. Load the document once in `main` with `c.load_observed`, and write `observed_hash` into the index next to `context_hash`.
- [ ] Run the tests, then the full suite.
- [ ] Commit: `Brief each hotspot with the dependencies observed in its file (#6)`.

### Task 8: `observed` evidence and validation (AC-2)

**Files:** `scripts/validate.py`, `scripts/save_finding.py`, `scripts/bundle.py` (re-validation call), `agents/thunderstruck-investigator.md`, `tests/test_observed_pipeline.py`.

**Interfaces:**
- Consumes: `c.load_observed`, the index's per-bundle `observed_hash`.
- Produces: `EVIDENCE_TYPES` gains `"observed"`; `Validator(..., observed: dict | None = None, bundle_observed: dict[str, str | None] | None = None)`; `observed_evidence(finding, by_ref) -> list[dict]` stamping `{ref, kind, value, resolution, edge}`.

- [ ] Write failing tests, mirroring the `catalog` ones in `tests/test_context_pipeline.py`, one per rule in §7's order:
  - a finding on H01 citing `code` plus `observed env:RELEASES_API_URL src/client/releases.ts:<line>` validates and is stamped (resolution `documented`, edge `dependsOn component:default/releases-api`);
  - a finding citing the ignored analytics observation validates (ignored stays citable, §6);
  - rule 1: over `scanned_copy` (skipped) → "this scan observed no dependencies, so none can be cited";
  - rule 2: drop one observation from `observed.json` after bundling and recompute its hash → every `observed` ref fails with "observations changed since bundling" (Review Focus 5);
  - rule 3: a wrong line → "no such observation; copy a ref verbatim from the bundle's 'Dependencies observed in this file' section";
  - rule 4: a finding on H01 citing H02's `fx-rates.internal` ref without citing `src/sync/collection.ts` as code → rejected; with it → accepted;
  - only `observed` evidence → rejected by the existing code-evidence rule;
  - `save_finding.py` strips an investigator-supplied `observed_evidence`.
- [ ] Run; they fail.
- [ ] Implement: the evidence branch in `Validator.check_evidence` (rules 1–4, first failure reported); `_bundle_observed(repo)` beside `_bundle_context`; the stamp beside `catalog_evidence`; `"observed_evidence"` in `save_finding.py`'s owned fields; `bundle.py`'s re-validation passes the same two arguments; the `observed` row in `validate.py`'s example map.
- [ ] In `agents/thunderstruck-investigator.md`, add the `observed` row to the evidence table and the §7 rule: an undocumented dependency is not by itself a finding.
- [ ] Run the tests, then the full suite. `tests/test_investigator_contract.py` must still pass.
- [ ] Commit: `Let a finding cite an observed dependency as checked evidence (#6)`.

### Task 9: The Catalog drift report section (AC-3, AC-4, AC-5, AC-6, AC-12)

**Files:** `scripts/report.py`, `skills/thunderstruck-scan/references/report-format.md`, `tests/test_observed_report.py` (new), `tests/test_inert_report.py`.

**Interfaces:**
- Consumes: `c.load_observed`; location URLs as `_location_url` builds them.
- Produces: `render_catalog_drift(obs: dict | None, ...) -> list[str]`; `report.json` top-level `catalog_drift` (`null` when skipped) with `observed_not_documented`, `ambiguous`, `dependent_only`, `not_observed`, `no_mapping`, `ignored`, `own_hosts_known`, `truncated`; findings carry `observed_evidence`. `index.json` doesn't change.

- [ ] Write failing tests over the context fixture's report:
  - `## Catalog drift` follows `## Service context`, with the §8 intro sentence and the fixed note on what is not observed (configuration tables, more than one variable or across files, vendor SDK clients);
  - *Observed, not in the catalog* lists `fx-rates.internal` and `LEDGER_ADDR` (with `(declared as \`component:default/ledger\`)`), each with kind, value, linked locations and count;
  - *Documented only as a dependent* lists `reporting-job.internal`;
  - *Documented, not observed* lists `dependsOn component:default/legacy-billing` in the §8 wording (AC-4);
  - *No mapping declared* lists `dependsOn resource:default/orders-db` in the §8 wording, naming the `[[observed.map]]` entry that would let the scan tell;
  - *Ambiguous*, from a hand-built document with two `ledger` neighbours, lists the value with both refs, and neither edge appears in the two lists above;
  - *Ignored by the profile* prints the analytics rule, its reason and `(1 hits)`;
  - with `own_hosts_known: false` (hand-built), the note says the service's own hosts are unknown; the fixture's own host appears nowhere in `report.md` or `report.json`;
  - a value with more than 3 locations shows 3 and `+N`; `truncated.catalog_edges > 0` prints the 25-per-direction note;
  - over `scanned_copy`, no `Catalog drift` heading and `catalog_drift` is `null` (AC-10; `test_report_without_context_is_unchanged` still passes);
  - in `tests/test_inert_report.py`, an injected value `` evil`](x)<b> `` renders inert (AC-12).
- [ ] Run; they fail.
- [ ] Implement `render_catalog_drift` (every value through `md.code`, every location through `md.linked`), call it right after `render_service_context`, add `catalog_drift` to `render_json`, and document the fields in `report-format.md`.
- [ ] Run the tests, then the full suite.
- [ ] Commit: `Report catalog drift in both directions (#6)`.

### Task 10: Scan skill, setup skill, sample report, docs and version

**Files:** `skills/thunderstruck-scan/SKILL.md`, `skills/thunderstruck-scan/references/orchestration.md`, `skills/thunderstruck-context-config/SKILL.md`, `scripts/gen_sample_report.py`, `examples/sample-report.md` and `examples/sample-report.html` (generated), `examples/thunderstruck.toml.example`, `README.md`, `CLAUDE.md` (Commands, Architecture), `CHANGELOG.md`, and the version in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`.

- [ ] Add **Step 1c — observed dependencies** to the scan skill, after Step 1b: `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/observed.py"`; relay its warnings; it never stops the scan. Mirror it in `orchestration.md`. Run `tests/test_plugin_paths.py`.
- [ ] In the context-config skill, state that databases, queues and other infrastructure are linked by `[[observed.map]]` entries (§3), explain the `thunderstruck.io/own-hosts` annotation, that it takes effect on the next catalog fetch, and the `[[observed.ignore]] host = "*.own-domain"` fallback (§2.6).
- [ ] In `gen_sample_report.py`, call `add_observed_dependencies(repo)` after `add_service_context`, run `observed.py` between `context.py` and `bundle.py`, and give the `client/releases.ts` canned finding an `"observed": ["env:RELEASES_API_URL"]` entry that the generator turns into the full ref with `_line_of(repo, hs["file"], "${RELEASES_API_URL}")`. Leave `"observed"` out of the finding item next to `"catalog"`. Fail generation if `## Catalog drift` is missing.
- [ ] Regenerate: `uv run scripts/gen_sample_report.py`, then `uv run scripts/gen_sample_report.py --check` exits 0. This is the one intended change to a generated file (§11).
- [ ] Docs: `observed.py` in the CLAUDE.md architecture diagram and Commands block (`uv run scripts/observed.py --repo /path/to/repo`); a README paragraph on catalog drift, the map as the expected route, and the known gaps; the `[observed]` example, including `own_hosts_annotation`, in `examples/thunderstruck.toml.example`.
- [ ] CHANGELOG: the next minor version after `main`'s, stating that enabling the feature re-investigates, once, only hotspots whose file calls something (§6), and that `context.json` gains `own_hosts` only for entries with the annotation. Update the three manifests; `test_versions_agree` passes.
- [ ] Run the four checks from the ticket agent's step 7: the full suite, `gen_catalog_docs.py --check`, `gen_sample_report.py --check`, `uv run scripts/validate_plugin.py`.
- [ ] Commit: `Run observed.py in every scan and show catalog drift in the sample (#6)`.
