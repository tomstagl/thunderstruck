# Observed dependencies and catalog drift: design

**Requirements:** [#6](https://github.com/tomstagl/thunderstruck/issues/6). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** to follow once this spec is reviewed.
**Builds on:** `docs/superpowers/specs/2026-09-23-architecture-context-design.md` (#1), cited below as *context spec §n*.

Examples use generic names (`component:default/checkout`, `payments-api`, `ledger.internal`).

## 1. Architecture

```
signals.py    →  hotspots.json
context.py    →  context.json
observed.py   →  observed.json          NEW · deterministic · reads tracked files, never the network
bundle.py     →  bundles/*.md           + "Dependencies observed in this file", + observed_hash
investigator  →  findings/*.json        may cite `observed` evidence
validate.py   →  validation.json        resolves `observed` refs against the pinned observed.json
report.py     →  report.md/.json        + "Catalog drift"
```

`observed.py` makes no model call and no network call. It reads the repository's tracked files and `context.json`, and writes one file. Detection, matching and the drift lists are therefore reproducible, and a finding can only cite what this step produced. That keeps CLAUDE.md's governing rule.

The scan skill runs `observed.py` right after `context.py`. It runs in every scan. Without usable context it writes a `skipped` document and nothing downstream changes (§9).

## 2. What is observed

An **observation** is one occurrence of one value of one kind, at one line of one file. There are three kinds.

### 2.1 `host`

- **In code and config:** the host part of a URL whose scheme matches `[a-z][a-z0-9+.-]{1,15}://`. That includes `https`, `grpc`, `amqp`, `postgres`, `redis` and `kafka`.
- **In service-mesh config:** in a YAML document whose `kind` is `VirtualService`, `DestinationRule` or `ServiceEntry`, the values of `spec.hosts[]`, `spec.host` and `route[].destination.host`.

Normalisation: lowercase, strip the port and a trailing dot. The value must match `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?)*$` and be at most 253 characters. Anything else is dropped and counted (§5).

Only the host is kept. Userinfo, path, query and fragment are never extracted, so `postgres://app:hunter2@db.internal/app` yields `db.internal` and nothing else (AC-8). The match anchors on `://` and skips optional userinfo (everything up to an `@` before the next `/`, whitespace or quote) before capturing the host.

### 2.2 `env`

The name of an environment variable the code or config reads, when the name ends in an address suffix: `_URL`, `_URI`, `_HOST`, `_HOSTNAME`, `_ENDPOINT`, `_ADDR`, `_ADDRESS` or `_DSN`. The suffix rule keeps `LOG_LEVEL` and `API_KEY` out. The read forms are:

| Language | Forms |
|---|---|
| TypeScript/JavaScript | `process.env.NAME`, `process.env["NAME"]` |
| Python | `os.environ["NAME"]`, `os.environ.get("NAME"`, `os.getenv("NAME"` |
| Java | `System.getenv("NAME")`, `@Value("${name.with.dots}")` (see below) |
| YAML | a Kubernetes container `env[].name` |
| properties / YAML | `${NAME}` and `${NAME:default}` placeholders |

The value must match `^[A-Z][A-Z0-9_]{0,63}$`. A Spring `@Value("${payments.base-url}")` property key isn't an environment variable. It is converted by Spring's relaxed binding (`.` and `-` become `_`, then uppercase: `PAYMENTS_BASE_URL`), and is kept only if that form ends in an address suffix.

### 2.3 `secret`

A reference to a secret by path or name. Only these forms count:

- in YAML, an `ExternalSecret`'s `spec.data[].remoteRef.key` and `spec.dataFrom[].extract.key`;
- in YAML, a pod annotation `vault.hashicorp.com/agent-inject-secret-<name>: <path>`, whose value is the path;
- in YAML, a Secrets Store CSI `SecretProviderClass`'s `objectName` / `secretPath` parameters;
- in code, a string literal passed as the first argument, or as `path=`, to a call whose name ends in `read_secret_version`, `read_secret`, `readSecret` or `getSecretValue` (`SecretId:` for the AWS SDK).

The value must match `^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}$`. A path is never resolved and never looked up anywhere (AC-8). A value that looks like a secret rather than a name (32 or more characters with no `/`, `-` or `_`) is dropped. That rule is defence in depth against a literal secret passed where a name was expected.

### 2.4 Never observed (AC-9)

The constant exclusions live in `catalog/observed.yaml`, so adding one is a data change with a negative sample, not a code change:

- **loopback and unspecified:** `localhost`, `*.localhost`, `127.0.0.0/8`, `::1`, `0.0.0.0`;
- **reserved names** (RFC 2606, RFC 6761): `example.com`, `example.org`, `example.net` and their subdomains, and `*.example`, `*.test`, `*.invalid`;
- **identifier hosts**, URLs that name a schema or a namespace rather than a server: `www.w3.org`, `json-schema.org`, `schemas.xmlsoap.org`, `schemas.microsoft.com`, `xmlns.com`, `purl.org`, `maven.apache.org`, `www.apache.org` and `schemas.android.com`;
- **documentation hosts**, in string literals that are only a URL, such as a link in an error message: `github.com`, `gitlab.com`, `docs.*`, `*.readthedocs.io`, `developer.mozilla.org`, `stackoverflow.com`;
- **templated values:** a host or name containing `$`, `{`, `}`, `%` or `<` (`${HOST}`, `{{ .Values.host }}`) is not a value. The template's *variable* is observed through §2.2 where it qualifies.

### 2.5 Which files

Tracked files that §3 of the citable-ranking spec would accept (`tracked_file_problem`, `path_problem`, valid UTF-8), in a language from the catalog, that the profile's filters don't exclude. That means tests, fixtures, vendored code and CI config are out, as for ranking. Files are read in sorted order. The walk stops after `--limit` files (default 3000, the same as `--dormant-limit`), with a warning naming the limit.

**Comments are blanked before matching, and string literals are not**, as for detectors. A commented-out URL is not a dependency, while `fetch("https://ledger.internal/…")` is.

## 3. Matching

Each distinct `(kind, value)` resolves once, in this order. The first rule that applies wins.

1. **Ignore rule** in the profile (§4) → `ignored`, counted against the rule.
2. **Declared mapping** in the profile → the declared entity, `via: "map"`.
3. **Exact name** against the neighbours in `context.json`, `via: "name"`:
   - `host`: the first DNS label equals the neighbour's name. `payments-api.prod.svc.cluster.local` matches `component:default/payments-api`; `payments.internal` does not;
   - `env`: strip the address suffix, lowercase, and replace `_` with `-`. `PAYMENTS_API_URL` → `payments-api`;
   - `secret`: the last path segment, lowercased. `secret/data/payments-api` → `payments-api`.

   Only names that are exactly equal count (AC-7). A name that equals two neighbours (the same name in two namespaces) matches neither, and the resolution is `ambiguous` with both refs listed.
4. Otherwise `unmatched`.

A resolved entity is then classified against `context.json`:

| Entity is | Resolution |
|---|---|
| an outbound neighbour | `documented`, with its edge ref (`dependsOn component:default/payments-api`) |
| only an inbound neighbour | `dependent_only` (AC-5) |
| declared in the map, but in neither list | `mapped_undocumented`: the team knows the entity, the catalog doesn't list the edge. It is drift. |
| — | `unmatched` |

`documented` and `dependent_only` compare against **all** edges, including the ones `context.py` truncated at 25 per direction. `context.json` records only the kept edges. So when `truncated` is non-zero, an unmatched value may be one of the dropped edges. The drift section says so in a note, and `observed.json` carries the count.

## 4. Configuration

A new `[observed]` table in `.thunderstruck.toml`. It is **not** part of `[context]`: it runs no command, so it doesn't belong in `config_hash`, and changing it never asks for trust again.

```toml
[[observed.map]]
entity  = "component:default/ledger"
hosts   = ["ledger.internal", "ledger-ro.internal"]
env     = ["LEDGER_DSN"]
secrets = ["secret/data/ledger-db"]

[[observed.ignore]]
host   = "api.analytics-vendor.example"   # or env = "…" / secret = "…"; exactly one
reason = "third-party analytics; tracked outside the catalog"
```

Validation follows `[[suppress]]` (#19): an invalid entry is ignored with a warning.

- `entity` must match the entity-ref grammar. Values must pass the same pattern as their kind (§2). A value may appear in at most one map entry.
- An ignore rule names exactly one of `host`, `env`, `secret`, and needs a non-empty `reason`. A `host` rule may use a leading `*.` for subdomains; nothing else is a wildcard.
- A violation drops that entry, with one warning naming the entry. It never disables the whole feature. A typo in one mapping must not silently change every other result.

`map_hash` is the sha256 of the canonical JSON of the valid map and ignore entries.

## 5. `observed.json`

Schema `thunderstruck.observed/v1`:

```json
{
  "schema": "thunderstruck.observed/v1",
  "status": "ok",
  "context_hash": "sha256:…",
  "map_hash": "sha256:…",
  "observed_hash": "sha256:…",
  "files_scanned": 412,
  "observations": [
    {"ref": "observed host:payments-api.prod.svc.cluster.local src/pay/client.ts:18",
     "kind": "host", "value": "payments-api.prod.svc.cluster.local",
     "file": "src/pay/client.ts", "line": 18}
  ],
  "resolutions": [
    {"kind": "host", "value": "payments-api.prod.svc.cluster.local",
     "resolution": "documented", "entity": "component:default/payments-api",
     "edge": "dependsOn component:default/payments-api", "via": "name",
     "occurrences": 2}
  ],
  "not_observed": ["dependsOn component:default/legacy-billing"],
  "ignored": [{"rule": "host api.analytics-vendor.example", "reason": "…", "hits": 3}],
  "truncated": {"observations": 0, "catalog_edges": 0},
  "dropped": {"host": 1, "env": 0, "secret": 0},
  "warnings": []
}
```

- **Ref grammar:** `observed <kind>:<value> <file>:<line>`. It is unique per occurrence and copied verbatim into evidence.
- **Order:** observations sorted by `(file, line, kind, value)`, resolutions by `(kind, value)`. Nothing depends on dict order or walk order.
- **Caps:** at most 2000 observations in total, and 20 per distinct value. The rest are counted in `truncated.observations`, and a warning is raised. Resolutions are never capped: the drift section must be complete, even when the per-occurrence list isn't.
- **`observed_hash`** is the sha256 of the canonical JSON of `observations`, `resolutions`, `not_observed` and `truncated`. It never covers `warnings` or `files_scanned`, so a new warning can't force re-investigation (AC-11).
- **`dropped`** counts values that failed their kind's pattern. They never appear, so repository text that isn't a plausible name can't reach any output (AC-12).
- **Statuses:** `ok`; `skipped` (no usable context, §9), which carries a `reason` and nothing else.

## 6. Bundles (AC-1)

When `observed.json` is `ok`, the hotspot's file has at least one observation, and the context is usable, `bundle.py` adds a section after *Service context*:

```
## Dependencies observed in this file

Found deterministically in this file's code and config. Cite one as `observed`
evidence by copying its ref verbatim, only alongside `code` evidence. A value
that matches no documented dependency is a lead, not a finding.

- `observed host:payments-api.prod.svc.cluster.local src/pay/client.ts:18` → documented: `dependsOn component:default/payments-api` (matched by name)
- `observed env:LEDGER_DSN src/pay/ledger.ts:7` → not in the catalog (declared as `component:default/ledger`)
- `observed host:fx-rates.internal src/pay/fx.ts:30` → matches no documented dependency
```

- At most 15 lines, sorted by the ref, then `… and N more observed in this file`. The section is never trimmed. It is taken out of the `context` share, as the Service context section is (*context spec §7*).
- The wording is fixed per resolution. No value appears outside the backticked ref and the backticked edge. Both go through `mdtext.code`.
- `bundles/index.json` records `observed_hash` per bundle and at the top level, next to `context_hash`.
- A file with no observations gets no section, so its bundle is unchanged. Enabling the feature re-investigates only hotspots that call something, once. The CHANGELOG says so.

## 7. Evidence and validation (AC-2)

New evidence type `observed`: `{type: "observed", ref, note}`. `validate.py` checks it in order, like `catalog` refs, and reports the first failure:

1. `observed.json` is `ok` → otherwise "this scan observed no dependencies, so none can be cited";
2. the finding's bundle carries the current `observed_hash` → otherwise "observations changed since bundling";
3. the ref is an observation in `observed.json` → otherwise "no such observation; copy a ref verbatim from the bundle's 'Dependencies observed in this file' section";
4. the observation's file is the finding's `location.file` or a file it cites as `code` evidence. That is the same "touches the finding" rule that `commit` refs follow.

The existing rule still holds: a finding needs a `code` item, so a finding resting on observations alone fails. On success, a finding is stamped with `observed_evidence: [{ref, kind, value, resolution, edge}]`, resolved from `observed.json`. Reports read the resolution from the stamp, never from the investigator's text. `VALIDATION_RULES` does not change: no old finding can carry an `observed` ref.

The investigator prompt gains one rule. An undocumented dependency is not, by itself, a finding. A finding still needs a failure mode, such as an undocumented dependency called without a timeout, whose failure nobody would trace here.

## 8. Report (AC-3 to AC-6)

After the Service context section, when `observed.json` is `ok`:

```
## Catalog drift

Compares the dependencies this scan observed in the code and configuration with
the service catalog. These are leads to check, not findings.

**Observed, not in the catalog** (4)
| Kind | Value | Where | Occurrences |
| host | `fx-rates.internal` | src/pay/fx.ts:30, src/pay/fx.ts:44 | 2 |
| env  | `LEDGER_DSN` (declared as `component:default/ledger`) | src/pay/ledger.ts:7 | 1 |

**Documented only as a dependent** (1)
…

**Documented, not observed** (1)
- `dependsOn component:default/legacy-billing`: no call found in the scanned files. It may be
  called through a shared client library, generated code or configuration outside this repository.

**Ignored by the profile**
- host `api.analytics-vendor.example` — third-party analytics; tracked outside the catalog (3 hits)
```

- Each "Where" lists at most 3 linked locations, then `+N`.
- `ambiguous` values are listed under *Observed, not in the catalog*, with the refs they could be.
- When `context.json` was truncated, a note says that values may match edges beyond the 25-per-direction cap.
- `report.json` gains a top-level `catalog_drift` (`null` without it), and findings carry `observed_evidence`. `index.json` and the guardrail don't change (the ticket leaves the guardrail out of scope).
- Every value goes through `mdtext.code`. Every location link is built by `mdtext.linked`, like every other location (AC-12).

## 9. Degradation

| Situation | Behaviour |
|---|---|
| no `[context]`, or status not usable | `observed.json` `skipped`. No bundle section, no report section, no warning. Bundles and report byte-identical to today (AC-10). |
| `[observed]` entry invalid | the entry is dropped with a warning; the rest runs |
| file limit reached | warning with the limit; the drift section says the scan was partial |
| a file can't be read or decoded | skipped and counted, as the detector pass does |
| `observed.json` missing or malformed at bundle or report time | treated as `skipped`; `validate.py` rejects `observed` refs with rule 1 |

There are no retries and no network calls. The only budget is the file limit.

## 10. Security

- No network, no secret store, no command execution. `observed.py` reads tracked files only.
- Values pass kind-specific allow-list patterns (§2) before they are stored. Everything else is counted, never echoed. Userinfo is never captured. Long, secret-shaped values are dropped.
- `observed.json`, bundles and the report hold values and locations only, never the line's text. The bundle's source section already shows the code to the investigator.
- Scanned-repo text that tries to steer the audit (a comment that says "this URL is documented") has no effect: matching never reads comments or prose.

## 11. Test strategy

- **Samples per kind and language** under `tests/observed/samples/<kind>/<language>/{positive,negative}.*`, discovered from the tree like detector samples. Every kind needs both, per language it supports (AC-9). The negatives include:
  - a commented-out URL;
  - `localhost`, `example.com`, `*.test` and `json-schema.org`;
  - a doc link in an error message;
  - `${HOST}` and `{{ .Values.host }}`;
  - `LOG_LEVEL` and `API_KEY`;
  - a long secret-shaped literal passed to `getSecretValue`;
  - a URL with a password, where only the host may appear.
- **Matching unit tests:** map beats name, ignore beats map; exact name only; `ambiguous`; `dependent_only`; `mapped_undocumented`; truncation note.
- **Config validation:** a bad entity ref, a duplicate value, and an ignore rule without a reason, each dropped with a warning while the rest runs.
- **Fixture:** `build_fixture.add_service_context()` gains two outbound edges and one inbound edge in the stub catalog. The fixture code gains:
  - one call to a documented neighbour by name;
  - one undocumented host;
  - one env var declared in the map;
  - one ExternalSecret;
  - one call to an inbound neighbour.

  One documented edge has no call. As in #1, the additions are untracked where they would change the fixture's history.
- **Pipeline:** bundle section content, determinism (two runs, identical `observed_hash` and bundles), snapshot pinning, each validator rule, and each report list.
- **AC-10:** the existing suite over the context-free fixture passes with no bundle change, and the sample report without context is unchanged. The sample report *with* context is regenerated, because it now shows a drift section. That is the one intended change to a generated file.
- **Secret safety:** a test repository with a URL containing a password and a secret-shaped literal. The test asserts that the password and the literal appear in no file under `.thunderstruck/`.

## 12. The spike

The spike runs before the build. It is what the ticket's success measures ask for.

- A throwaway script, not committed, that applies §2 and §3 to one real repository with its real `context.json`.
- It prints only counts and shares:
  - documented outbound edges linked to at least one file;
  - distinct values per resolution;
  - dropped values.
- A person reviews a sample of 30 unmatched values by hand, and marks each one a real dependency or noise.
- The results go into `docs/calibration/` without any organisation-specific names, in the same form as the #19 calibration logs.
- The ticket's go/no-go threshold decides whether the build proceeds as specified. The alternative is to narrow the kinds, for example to hosts only.

## 13. Decisions

| Decision | Rationale |
|---|---|
| A separate deterministic step, `observed.py` | Drift is repo-wide, not per hotspot. Detectors look for stability patterns, and this is inventory. Keeping it apart keeps the catalog of patterns clean. |
| Observations are leads; drift is a report section, not a finding | The ticket's decision. Findings stay falsifiable failure hypotheses. |
| Exact name matching only, after a fixed normalisation | The ticket's decision (AC-7). A fuzzy match that is wrong is a false positive on correct code, which CLAUDE.md ranks worse than a miss. |
| A declared map in the profile, outside `[context]` | The catalog here holds little beyond names. The map runs no command, so it must not re-prompt for trust. |
| Secret references by path from repo files only | The ticket's decision. Reading a secret store would be a network call, and a credential risk. |
| Only the host of a URL is kept | Paths add little to matching, and userinfo is a credential. |
| Ref per occurrence, pinned by `observed_hash` | The same pattern as `detector` refs and `catalog` snapshot pinning. A cited observation is always one the current scan produced. |
| Constant exclusions in `catalog/observed.yaml` | Additions are data with samples. That matches "the catalog is the source of truth". |
| Validator rule 4 (observation in a cited file) | A finding about `a.ts` must not borrow a call made in `b.ts`. The commit-ref rule has the same shape. |

## 14. Open design questions

- **Language coverage.** §2's read forms cover TypeScript/JavaScript, Python, Java, YAML and properties. Go and Kotlin have no detectors yet (#19's warning). They get no observations either, and the drift section's "partial" note should name them.
- **Generated clients.** Calls through an OpenAPI-generated client name no host in our code. *Documented, not observed* will list such dependencies. The wording in §8 says so. Whether a declared map entry should be able to name a client package is left to the spike.
- **Queues and topics.** Kafka topic names or SQS queue URLs are dependencies too. SQS URLs are covered by `host`; topic names are not. They are left out until the spike shows whether they matter.
- **Guardrail line.** "This file calls payments-api (tier 1)" would be cheap to add from `observed_evidence`. The ticket leaves it out of scope.
