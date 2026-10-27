# Observed dependencies and catalog drift: design

**Requirements:** [#6](https://github.com/tomstagl/thunderstruck/issues/6). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-10-03-observed-dependencies.md`.
**Builds on:** `docs/superpowers/specs/2026-09-23-architecture-context-design.md` (#1), cited below as *context spec §n*.

**Amended 2026-10-22** after the spike's no-go (`docs/calibration/observed-dependencies.md`): hosts are observed only at call sites, env vars by use, the service's own hosts come from its catalog entry, a documented dependency without a mapping is reported as such, and the spike is re-run against a public demo (§2, §3, §8, §12, §13).

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

**Which line:** the line that names the dependency. For a host, the URL literal's line, which is often a `const BASE = …` above the call; the bundle's source section shows the call. For an env var used directly in a call, that line. For one used through a variable, the line of the call that uses the variable, since that is the line that makes the call (AC-1); the read's line is not an observation. A variable used in three calls gives three observations.

The guiding rule, from the spike: **something is a dependency when the code processes what comes back from it.** A URL in a list of press links, a footer, a font or an image the browser loads is not one. Vendor SDK clients (an AWS, Anthropic or Google client) are dependencies too, but they name no host in our code; they are a separate ticket, and #6 does not observe them.

### 2.1 `host`

A host is observed from a URL literal only at a call site. A URL literal is the host part of a URL whose scheme matches `[a-z][a-z0-9+.-]{1,15}://` (`https`, `grpc`, `amqp`, `postgres`, `redis`, `kafka` and so on). It is observed only when all three hold:

1. **The file calls out and reads the answer.** After comments are blanked (§2.5), the file matches at least one *request form* and at least one *response form* of its language. Both lists are data in `catalog/observed.yaml`:

   | Language | Request forms | Response forms |
   |---|---|---|
   | TypeScript/JavaScript | a call whose name contains `fetch`, `Fetch`, `request` or `Request` (so `fetchWithRetry(` counts); `axios`; `got(`; `ky.`; `https.request(` / `https.get(`; `undici`; `.request(` | `.json()`, `.text()`, `.status`, `.ok`, `.data`, `.headers`, `.arrayBuffer()`, `.blob()` |
   | Python | `requests.get/post/put/delete/request(`; `httpx.`; `.request(` | `.json()`, `.text`, `.status_code`, `.content`, `.headers` |
   | Java | `HttpClient` `.send(` / `.sendAsync(`; `RestTemplate` `getForObject` / `getForEntity` / `exchange(`; `WebClient` `.retrieve()` | `.body()`, `.getBody()`, `.statusCode()`, `.getStatusCode()`, `.bodyToMono(` |

   Only the TypeScript/JavaScript row was measured in the spike (rule v2). The Python and Java rows were not. The re-run (§12) includes a Python and a Java service to test them, and an unmeasured form doesn't ship (§12, *Measured forms*).
2. **The URL names a resource or an API.** It has a path beyond `/`, or the literal is the value of a name containing `api`, `base` or `endpoint` (any case: `apiBase =`, `BASE_URL:`) or the argument of `new URL(`. A bare `https://example-shop.com` in a link table does not qualify.
3. **The host is not one of the service's own** (§2.6).

**In YAML and properties files**, which have no call to look at, a URL host counts by its key, as env vars in configuration count by name (§2.2): the key's last segment contains `url`, `uri`, `endpoint`, `host`, `base` or `api`, in any case (`payments.base-url: https://…`, `ledgerEndpoint=grpc://…`). For YAML this is read from the line, `key: value`, so it still applies to a file that doesn't parse. Rule 3 applies. Spring services name their downstream base URLs this way. The form is unmeasured, so it ships only if the re-run measures it (§12).

**Service-mesh config:** in a YAML document whose `kind` is `ServiceEntry`, the values of `spec.hosts[]`. A `ServiceEntry` declares traffic leaving the mesh, so it names something this service calls. `VirtualService` and `DestinationRule` describe how traffic reaches a service, usually this one, and are not observed. None of the spike's repositories had mesh config, so this form is unmeasured too (§12).

Normalisation: lowercase, strip the port and a trailing dot. The value must match `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?)*$` and be at most 253 characters. Anything else is dropped and counted (§5).

Only the host is kept. Userinfo, path, query and fragment are never extracted, so `postgres://app:hunter2@db.internal/app` yields `db.internal` and nothing else (AC-8). The match anchors on `://` and skips optional userinfo (everything up to an `@` before the next `/`, whitespace or quote) before capturing the host. Rule 2 reads whether a path follows; it never stores it.

**Known gap: URLs kept in configuration tables.** A crawler's start URLs or a table of review sites the code fetches later sit in a file with no request form, or with no API name, so they are not observed. Catching them would bring back the link lists that made the first run no-go, because both are tables of URLs. The spike saw this twice in four repositories. The drift section's note says that hosts held in configuration tables are not observed.

### 2.2 `env`

An env var is observed in two ways: in code, **by use**, whatever its name; in configuration, **by name**.

**In code: by use.** A read counts when its value goes into a call that reaches another system:

- **directly**, inside the argument list of a request form (§2.1) or a connect form, alone or within a template or concatenation: `fetch(`${process.env.AUTH_SERVER}/verify`)`, `mongoose.connect(process.env.DB_CONNECT)`;
- **through one local variable** in the same file: the read is assigned to a name (`const base = process.env.AUTH_SERVER`, `url = os.environ["X"]`, `String u = System.getenv("X")`), or destructured (`const { CART_ADDR = '' } = process.env` binds `CART_ADDR`; `{ CART_ADDR: addr }` binds `addr`), and that name appears inside the argument list of a later request or connect form in the file.

Connect forms are data in `catalog/observed.yaml`, like request forms. They cover clients built from an address: database pools and connections (`mongoose.connect`, `new Pool(`, `createConnection(`, `MongoClient(`, `psycopg.connect(`, `create_engine(`, `DriverManager.getConnection(`), caches (`createClient(`, `redis.Redis(`, `Redis.from_url(`) and gRPC channels and clients (`grpc.insecure_channel(`, `grpc.secure_channel(`, `ManagedChannelBuilder.forTarget(`, and a generated client `new <Name>Client(` whose arguments include `ChannelCredentials` or `credentials.`). For a database, a queue or a gRPC service, "the answer is processed" becomes "a client is built from it".

An argument list runs from the call's opening parenthesis to its balanced closing one in the comment-blanked text, at most 2000 characters. If the parentheses don't balance within that, the call is skipped.

The read forms:

| Language | Forms |
|---|---|
| TypeScript/JavaScript | `process.env.NAME`, `process.env["NAME"]`, `const { NAME } = process.env` (with an optional default or alias) |
| Python | `os.environ["NAME"]`, `os.environ.get("NAME"`, `os.getenv("NAME"` |
| Java | `System.getenv("NAME")` |

Not followed, and documented as known gaps:

- a second hop (`const a = process.env.X; const b = a + '/v1'; fetch(b)`);
- object fields (`config.auth = process.env.X`, then `fetch(config.auth)`);
- a value read in one file and used in another, which is the usual `config.ts` pattern. The re-run (§12) counts how often this happens.

A name bound twice in a file, or reassigned, still counts. The rule can over-report within one file, never across files.

An env var read only by an SDK client (`new S3Client(…)`, `Anthropic(…)`) is not observed. That belongs with the vendor-SDK ticket.

**In configuration: by name.** These forms have no call to look at, so a name counts when it ends in an address suffix: `_URL`, `_URI`, `_HOST`, `_HOSTNAME`, `_ENDPOINT`, `_ADDR`, `_DSN`, `_CONNECT` or `_SERVER`. The spike dropped `_ADDRESS`, which was all noise, and added `_CONNECT` and `_SERVER`, which carried real dependencies.

| Language | Forms |
|---|---|
| YAML | a Kubernetes container `env[].name` |
| properties / YAML | `${NAME}` and `${NAME:default}` placeholders |
| Java | `@Value("${name.with.dots}")` (see below) |

A Spring `@Value("${payments.base-url}")` property key isn't an environment variable. It is converted by Spring's relaxed binding (`.` and `-` become `_`, then uppercase: `PAYMENTS_BASE_URL`), and is kept only if that form ends in an address suffix. It is a declaration on a field, not a use, so it follows the configuration rule.

Every env value must match `^[A-Z][A-Z0-9_]{0,63}$`.

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
- **documentation hosts**, which code links to (a link in an error message) rather than calls. They are excluded wherever they appear: `github.com`, `gitlab.com`, `docs.*`, `*.readthedocs.io`, `developer.mozilla.org`, `stackoverflow.com`;
- **templated values:** a host or name containing `$`, `{`, `}`, `%` or `<` (`${HOST}`, `{{ .Values.host }}`) is not a value. The template's *variable* is observed through §2.2 where it qualifies.

### 2.5 Which files

Tracked files that §3 of the citable-ranking spec would accept (`tracked_file_problem`, `path_problem`, valid UTF-8), in a language from the catalog, that the profile's filters don't exclude. That means tests, fixtures, vendored code and CI config are out, as for ranking. It follows the scan's own scope: `observed.py` reads `hotspots.json`'s `config` and applies its `path` and `include_tests`, so scanning one service of a monorepo observes only that service's files. Files are read in sorted order. The walk stops after `--limit` files (default 3000, the same as `--dormant-limit`), with a warning naming the limit.

**Comments are blanked before matching, and string literals are not**, as for detectors. A commented-out URL is not a dependency, while `fetch("https://ledger.internal/…")` is.

Committed build output (a `storybook-static/` folder, minified bundles) passes these filters today, and a bundle contains request and response forms. In the spike it was the only source of noise left after the call-site rule. Excluding it changes the shared file filter, so the ranking of every scan, and is a separate ticket (§14).

### 2.6 The service's own hosts

A host equal to one of the service's own hosts, or a subdomain of one, is not observed (§2.1 rule 3). The service's own site and API were a large share of the first run's noise.

The own hosts come from the service's own catalog entry, the one `context.py` already fetches, through one annotation. The key is `own_hosts_annotation` in the `[observed]` table (§4), default `thunderstruck.io/own-hosts`. Its value is a comma-separated list, for example `shop.example-corp.com, *.api.example-corp.com`.

- `context.py` reads that one annotation from the entity itself (not from a neighbour) and writes `own_hosts` into `context.json`. Each entry must pass the §2.1 host pattern, with an optional leading `*.`. A bad entry is dropped with a warning that names the annotation but not the value. *Context spec §6* keeps free text out of `context.json`; this is a list of host-shaped tokens, which is the same surface as the neighbour attributes.
- `own_hosts` is used only to exclude. It never appears in a bundle, a prompt or the report, and adds nothing to the prompt-injection surface.
- `context.json` gets the field only when the annotation is present and yields at least one host, so `context_hash` doesn't change for a team that doesn't use it. When it changes, `context_hash` changes, which is right: the observations change too.
- Without it, nothing is excluded and the drift section says the service's own hosts are unknown (§9).
- It takes effect on the next catalog fetch. While `context.py` reuses a cached `context.json` (*context spec §5*), a new annotation, or a changed `own_hosts_annotation`, is not seen; the setup skill says so and names the refresh. The key stays out of `config_hash` because it runs no command and must not ask for trust again.
- A team that can't annotate its catalog entry uses `[[observed.ignore]] host = "*.own-domain"`, with a reason. The setup skill offers that route.

`metadata.links` is not used. Links also point at dashboards, runbooks and vendor API docs, and a link to a vendor's API docs would exclude the vendor's API, which is the dependency a team most wants to see.

Own env vars (`BASE_URL`, `NEXTAUTH_URL`) need no mechanism: the use rule (§2.2) already drops those that no call uses, and a remaining one goes into `[[observed.ignore]]`.

## 3. Matching

**The declared map is the expected route.** The spike linked 0 of 3 documented dependencies by exact name: a catalog names a database or a queue as an entity (`resource:default/orders-db`), while the code names it `DATABASE_URL` or a queue URL. Those never line up, so databases, queues and other infrastructure are linked by `[[observed.map]]` entries (§4). Exact names are a fallback that mostly works for service-to-service hosts such as `payments-api.prod.svc.cluster.local`. The setup skill, the docs and the drift section say so.

Each distinct `(kind, value)` resolves once, in this order. The first rule that applies wins.

1. **Ignore rule** in the profile (§4) → `ignored`, counted against the rule.
2. **Declared mapping** in the profile → the declared entity, `via: "map"`.
3. **Exact name** against the neighbours in `context.json`, `via: "name"`:
   - `host`: the first DNS label equals the neighbour's name. `payments-api.prod.svc.cluster.local` matches `component:default/payments-api`; `payments.internal` does not. A generic first label (`api`, `www`, `app`, `cdn`, `static`, a list in `catalog/observed.yaml`) is never compared, so `api.vendor.com` can't match a neighbour called `api`;
   - `env`: strip an address suffix from the §2.2 configuration list if the name ends in one, lowercase, and replace `_` with `-`. `PAYMENTS_API_URL` → `payments-api`, `CART_ADDR` → `cart`, `DB_CONNECT` → `db`. A name with no suffix is compared whole;
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

Each documented outbound edge with no resolution pointing at it is then classified once:

| The edge's entity | List |
|---|---|
| has an `[[observed.map]]` entry | `not_observed`: the team said how it is reached, and none of those values appears in the scanned files |
| has no map entry | `no_mapping`: the tool can't tell whether the code uses it. Without this split, a team with no map yet would see its database and queue as "not observed" while the code uses both, which is the "unused" reading AC-4 rules out |

An edge reached by an exact-name resolution counts as observed, mapped or not. The split applies only to edges with no observation.

`documented` and `dependent_only` compare against the edges `context.json` kept. `context.py` truncates at 25 per direction and records only the kept edges, with a count of the rest. So when `truncated` is non-zero, an unmatched value may be one of the dropped edges. The drift section says so in a note, and `observed.json` carries the count.

## 4. Configuration

A new `[observed]` table in `.thunderstruck.toml`. It is **not** part of `[context]`: it runs no command, so it doesn't belong in `config_hash`, and changing it never asks for trust again.

```toml
[observed]
own_hosts_annotation = "thunderstruck.io/own-hosts"   # optional; this is the default (§2.6)

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
  "no_mapping": ["dependsOn resource:default/orders-db"],
  "ignored": [{"rule": "host api.analytics-vendor.example", "reason": "…", "hits": 3}],
  "own_hosts_known": true,
  "truncated": {"observations": 0, "catalog_edges": 0},
  "dropped": {"host": 1, "env": 0, "secret": 0},
  "excluded": {"own_host": 4},
  "warnings": []
}
```

- **Ref grammar:** `observed <kind>:<value> <file>:<line>`. It is unique per occurrence and copied verbatim into evidence.
- **Order:** observations sorted by `(file, line, kind, value)`, resolutions by `(kind, value)`. Nothing depends on dict order or walk order.
- **Caps:** at most 2000 observations in total, and 20 per distinct value. Observations in a file that `hotspots.json` ranks are kept first and are never dropped by either cap, so a hotspot's bundle can always cite its own calls (AC-1, AC-2); the caps apply to the rest in `(file, line)` order. The rest are counted in `truncated.observations`, and a warning is raised. Resolutions are never capped: the drift section must be complete, even when the per-occurrence list isn't.
- **`observed_hash`** is the sha256 of the canonical JSON of `observations`, `resolutions`, `not_observed`, `no_mapping` and `truncated`. It never covers `warnings` or `files_scanned`, so a new warning can't force re-investigation (AC-11).
- **`dropped`** counts values that failed their kind's pattern. They never appear, so repository text that isn't a plausible name can't reach any output (AC-12).
- **`excluded.own_host`** counts URL hosts that §2.6 excluded. The hosts themselves never appear. `own_hosts_known` is false when `context.json` has no `own_hosts`.
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
- An observation that an `[[observed.ignore]]` rule covers stays in `observations`, in the bundle and citable, worded "ignored by the profile: <reason>". Ignoring a vendor stops the drift listing, not a finding about a timeout-less call to it (AC-2).
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
- `dependsOn component:default/legacy-billing`: none of its mapped values appear in the scanned
  files. It may be called through a shared client library, generated code or configuration
  outside this repository.

**No mapping declared** (1)
- `dependsOn resource:default/orders-db`: no observation could be linked to it, so this scan can't
  tell whether the code uses it. An `[[observed.map]]` entry naming its hosts, env vars or
  secrets would let it tell.

**Ignored by the profile**
- host `api.analytics-vendor.example` — third-party analytics; tracked outside the catalog (3 hits)
```

- Each "Where" lists at most 3 linked locations, then `+N`.
- `ambiguous` values have their own list, **Ambiguous**, with the refs each could be. An edge that is a candidate of an ambiguous value is listed there and in neither *Documented, not observed* nor *No mapping declared*, so the same entity never appears as both "could be" and "not observed". A map entry resolves it.
- When `context.json` was truncated, a note says that values may match edges beyond the 25-per-direction cap.
- A fixed note under the heading states what is not observed: hosts held only in configuration tables, env values passed through more than one variable or across files, and vendor SDK clients (§2.1, §2.2). When `own_hosts_known` is false, it adds that the service's own hosts are unknown, so its own URLs may be listed.
- `report.json` gains a top-level `catalog_drift` (`null` without it), and findings carry `observed_evidence`. `index.json` and the guardrail don't change (the ticket leaves the guardrail out of scope).
- Every value goes through `mdtext.code`. Every location link is built by `mdtext.linked`, like every other location (AC-12).

## 9. Degradation

| Situation | Behaviour |
|---|---|
| no `[context]`, or status not usable | `observed.json` `skipped`. No bundle section, no report section, no warning. Bundles and report byte-identical to today (AC-10). |
| `[observed]` entry invalid | the entry is dropped with a warning; the rest runs |
| no own-hosts annotation, or none of its entries valid | nothing is excluded by §2.6; the drift section says the own hosts are unknown. A bad entry is dropped with a warning that doesn't echo it |
| a call's argument list doesn't balance within 2000 characters | that call yields no env use (§2.2); no warning, since it is ordinary minified or generated code |
| file limit reached | warning with the limit; the drift section says the scan was partial |
| a file can't be read or decoded | skipped and counted, as the detector pass does |
| a YAML file that doesn't parse (a Helm template, say) | the structural forms (mesh hosts, container `env[].name`, the §2.3 YAML forms) are skipped for that file; the line forms (URL hosts under a qualifying key, §2.1, and `${NAME}` placeholders) still apply. One warning counts such files. |
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
  - a URL with a password, where only the host may appear;
  - a table of press or footer links in a file with no request form, and the same table in a file that has one but where the URLs have no path and no API name (§2.1);
  - a URL in a file that requests but never reads a response;
  - a `VirtualService` host;
  - an own host and its subdomain (§2.6);
  - an env var read but never used in a call, an env var used only in an SDK constructor, a second hop, an object field, and a read in one file used in another (§2.2's gaps, pinned so a change to them is deliberate).

  The positives include `fetchWithRetry(` with a path, `new URL("https://…")`, an `apiBase =` without a path, an env var used directly in `fetch` and in `mongoose.connect`, one through a variable, one through destructuring with a default and with an alias, a generated gRPC client, and a `ServiceEntry` host.
- **Matching unit tests:** map beats name, ignore beats map; exact name only; a generic first label never matches; env suffix stripping with and without a suffix; `ambiguous`; `dependent_only`; `mapped_undocumented`; `not_observed` versus `no_mapping`, including an exact-name match counting as observed without a map; truncation note.
- **Own hosts:** `context.py` writes `own_hosts` from the annotation, drops a bad entry without echoing it, and writes no field (and an unchanged `context_hash`) without the annotation.
- **Config validation:** a bad entity ref, a duplicate value, and an ignore rule without a reason, each dropped with a warning while the rest runs.
- **Fixture:** `build_fixture.add_service_context()` gains three outbound edges and one inbound edge in the stub catalog, and an own-hosts annotation. The fixture code gains:
  - one call to a documented neighbour by name;
  - one undocumented host;
  - one env var declared in the map;
  - one ExternalSecret;
  - one call to an inbound neighbour;
  - one URL on the own host.

  One documented edge has no call but a map entry (`not_observed`), and one has neither (`no_mapping`). `observed.py` reads tracked files only (§2.5), so unlike #1's untracked profile and `catalog-info.yaml`, the code and config additions are committed: one extra commit on top of the built history, dated one day after its last commit, and made only where service context is added. The context-free fixture and its history are unchanged (AC-10). The `[observed]` profile entries stay untracked, like `[context]`.
- **Pipeline:** bundle section content, determinism (two runs, identical `observed_hash` and bundles), snapshot pinning, each validator rule, and each report list.
- **AC-10:** the existing suite over the context-free fixture passes with no bundle change, and the sample report without context is unchanged. The sample report *with* context is regenerated, because it now shows a drift section. That is the one intended change to a generated file.
- **Secret safety:** a test repository with a URL containing a password and a secret-shaped literal. The test asserts that the password and the literal appear in no file under `.thunderstruck/`.

## 12. The spike

The spike runs before the build. It is what the ticket's success measures ask for.

**The first run** (recorded in `docs/calibration/observed-dependencies.md`) applied the original §2 to one private service: 22 and 25 of 30 reviewed unmatched values were noise, and exact names linked 0 of 3 documented dependencies. Verdict no-go. Designing this amendment, the call-site rule was then tried on three more repositories, with no catalog or a hand-written one. Those runs shaped the rule, so none of the four repositories is held out any more.

**The re-run** tests this amended §2 and §3 on a repository none of them was tuned on, with ground truth written down before the run.

- **Repository:** the OpenTelemetry demo, `open-telemetry/opentelemetry-demo` at `ad06a6f9df40abde6c1f0c58b29b92f1076a74ec`. It is public, so the calibration doc names it. Its service-to-service calls sit in covered languages: the frontend (TypeScript, Next.js) reaches seven services through `*_ADDR` env vars, and the recommendation service is Java.
- **Services under test**, each scanned as one service (`--path` to its directory, §2.5):
  - `src/frontend` (TypeScript): seven services through `*_ADDR` env vars, by gRPC client and by `fetch`;
  - `src/recommendation` (Java): the product catalog through a `${PRODUCT_CATALOG_ADDR:…}` placeholder in `application.yaml`, so the configuration rule;
  - `src/ad` (Java), which builds a gRPC channel with `ManagedChannelBuilder`, and `src/chatbot` (Python), which calls out with `requests.post`. They are the first test of the Java and Python rows of §2.1 and §2.2. Their edges come from the same documentation; a service the documentation gives no edges for is dropped from linkage and recall, and the doc says so.
- **Ground truth, written and hashed before the run:**
  - the catalog: each service's outbound edges, taken only from the demo's published architecture documentation on opentelemetry.io, never from the code;
  - the map: for each edge, the env vars and hosts that reach it, taken from the demo's deployment configuration (`docker-compose.yml` and `.env`), as a team would write it from its own config;
  - the own hosts: from the same documentation.
- **Freeze:** a throwaway script, not committed, implements the amended §2 and §3. Its sha256, the commit and the ground-truth hashes are recorded before it runs. The script is not changed after the run.
- **What was seen before the freeze:** while designing this amendment, two files of the frontend were read (`src/frontend/gateways/rpc/Cart.gateway.ts` and `src/frontend/gateways/http/Shipping.gateway.ts`), together with a code-search list of the paths that mention `_ADDR`. They led to the gRPC client and destructuring forms in §2.2. The doc lists them, so frontend recall is not reported as fully blind.
- **Measures**, counts and shares only:
  - linkage: documented outbound edges of each service linked to at least one file;
  - recall: every mapped edge that has no observation, each with the reason it was missed;
  - distinct values per resolution, dropped values per kind, and own hosts excluded;
  - how many env reads were used in a call in a different file from the read (the §2.2 cross-file gap).
- **Noise review:** a person reviews 30 unmatched values from the services under test, pooled, every k-th of the sorted list, or all of them if there are fewer, and marks each a real dependency or noise.
- **Gate:** `Verdict: go` only if both hold:
  - at most one in five reviewed values is noise (the ticket's threshold: 6 of 30);
  - every mapped edge missed by the recall check is missed for a reason §2 documents as a known gap.

  Otherwise `Verdict: no-go — <what to narrow>`, and §2 changes again before the build.
- The results are added to `docs/calibration/observed-dependencies.md` as a second run, in the same form.

**Measured forms.** A false positive on correct code costs more than a miss (CLAUDE.md), so a form ships only once a spike run has measured it. A form is measured when the run observed at least one real dependency through it and its values were in the noise review. The calibration doc lists, per language, which request, response, connect, read and configuration forms (§2.1, §2.2) and which mesh form the re-run measured. `catalog/observed.yaml` holds only those. A form the re-run didn't reach stays out, the drift section's note names the languages with no measured forms, and adding one later is a data change backed by a new calibration run. A run that observes nothing through a form isn't a failure of the gate; it only keeps that form out.

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
| Hosts only at call sites: request and response forms in the file, a path or an API name, not an own host | The first run was no-go on link noise: press lists, footers, social links, the service's own site. The maintainer's rule: a dependency is something whose answer the code processes. On the spike's four repositories the call-site rule removed that noise every time. |
| URLs in configuration tables are a known gap | Catching a crawler's start URLs would bring back the press lists, since both are tables of URLs. The maintainer accepted the miss, documented, over the noise. |
| Env vars in code by use, whatever the name; in config by suffix | Real dependencies came through `DB_CONNECT` and `AUTH_SERVER`, which no suffix list caught. Config has no call to look at, so the name is all there is. |
| Follow one local variable, not more | `const base = process.env.X; fetch(base + …)` is common. Two hops, object fields and cross-file flow would need data-flow analysis; they are documented gaps, and the re-run counts the cross-file case. |
| Own hosts from one annotation on the service's own catalog entry, not from `metadata.links` | Links also point at vendor API docs, and excluding a vendor's API would hide the dependency a team most wants to see. |
| The declared map is the expected route; exact names are a fallback | A catalog's database and queue entities never share a name with `DATABASE_URL` or a queue URL. The spike linked 0 of 3 by name. |
| `no_mapping` separate from `not_observed` | Without a map the tool can't tell whether an edge is used. Reporting it as "not observed" would read as "unused" (AC-4). |
| Vendor SDK clients and committed build output are separate tickets | SDK clients name no host in our code and need the `boundaries:` route. Build output changes the shared file filter, so every scan's ranking. Keeping #6 on hosts and env keeps it reviewable. |
| Only measured forms ship | The maintainer's call. Python and Java request forms, the YAML key rule and the mesh form had met no real dependency when this was written. A form that has never been checked against real code is the likeliest source of the false positives that made the first run no-go. |
| Re-run on the OpenTelemetry demo, with ground truth from its published docs | No independently maintained catalog was available. The demo's documentation is someone else's, written before our run, and its service-to-service calls are in covered languages. Online Boutique was rejected: most of its edges are in Go, which thunderstruck doesn't support. |

## 14. Open design questions

- **Language coverage.** §2's read forms cover TypeScript/JavaScript, Python, Java, YAML and properties. Go and Kotlin have no detectors yet (#19's warning). They get no observations either, and the drift section's "partial" note should name them.
- **Generated clients.** Calls through an OpenAPI-generated client name no host in our code. *Documented, not observed* will list such dependencies. The wording in §8 says so. Whether a declared map entry should be able to name a client package is left to the vendor-SDK ticket, which faces the same question. Generated gRPC clients built from an address are covered by §2.2's connect forms.
- **Queues and topics.** Kafka topic names or SQS queue URLs are dependencies too. An SQS queue URL in an env var is observed when a client is built from it, which today is an SDK call, so it falls to the vendor-SDK ticket. Topic names are not observed.
- **Helper-wrapped calls.** A call whose name contains `fetch` or `request` (`fetchWithRetry(`) counts as a request form. No repository in the spike had a real dependency behind such a helper after that rule was written, so it is untested until the re-run meets one.
- **Committed build output.** A separate ticket for the shared file filter (§2.5).
- **Guardrail line.** "This file calls payments-api (tier 1)" would be cheap to add from `observed_evidence`. The ticket leaves it out of scope.
