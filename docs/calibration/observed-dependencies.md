# Observed dependencies spike

The spike for #6 (spec `2026-09-25-observed-dependencies-design.md` §12,
plan Task 0). A throwaway script, not committed, applied §2 (all three kinds,
the §2.4 exclusions) and §3 rule 3 (exact name only, no profile map) to one
repository and its `context.json`. It printed counts and shares; a person
reviewed 30 unmatched values by hand.

| Repo | Commit | Scope walked |
|---|---|---|
| a private web service (Next.js, TypeScript) | private | every tracked TS/JS, YAML and properties file the shared filter keeps: 992 files |

thunderstruck at `14d440c`. The repository and its hosts are not named here.

## The catalog

The repository has no catalog entry, so `context.json` was written by hand by
the maintainer. That weakens every figure below: nobody maintained this
catalog independently of the code.

- **Run 1**, written before the script ran: 3 outbound edges, named as the
  infrastructure names them (the queue and the database by their Terraform
  and RDS identifiers, the downstream service by its project name).
- **Run 2**, rewritten after run 1's output: the queue and the database
  renamed to the role names the code uses, and five undocumented
  dependencies from run 1 added. 8 outbound edges. **Run 2's linkage is fitted
  to run 1 and is not evidence.** It is recorded only for what the two edges
  that still failed show.

## Counts

| | Run 1 | Run 2 |
|---|---|---|
| Documented outbound edges linked to at least one file | 0/3 (0%) | 6/8 (75%), fitted |
| Distinct values: documented | 0 | 6 (host 3, env 3) |
| Distinct values: dependent_only, ambiguous | 0, 0 | 0, 0 |
| Distinct values: unmatched | 126 (host 108, env 18) | 120 (host 105, env 15) |
| Secret values observed | 0 | 0 |

Dropped occurrences, identical in both runs:

| Kind | Dropped | By reason |
|---|---|---|
| host | 54 | loopback 24, templated 23, identifier 3, malformed 2, documentation 1, reserved 1 |
| env | 365 | no address suffix 361, malformed 4 |
| secret | 0 | |

## Why run 1 linked nothing

Both dependencies the catalog listed are read by the code, as
`ENRICHMENT_QUEUE_URL` and `DATABASE_URL`. Rule 3 derives `enrichment-queue`
and `database` from them; the catalog names them by their infrastructure
identifiers. Exact names cannot meet. The third edge, the downstream service,
is reached only through the queue, and no code names it.

In run 2, with the names aligned, two edges still did not link:

- `api.<vendor>.com` derives `api`: the first DNS label is a generic word for
  most SaaS APIs.
- The service behind the queue: a dependency reached through a queue has no
  observation of its own.

One vendor also took two names: its host derives `<vendor>`, its
`<VENDOR>_API_URL` variable `<vendor>-api`.

## Hand review

Every 4th unmatched value of the sorted list, 30 per run. The maintainer
decided that music-press and review sites count as noise.

| | Run 1 | Run 2 |
|---|---|---|
| Real dependency | 8 | 5 |
| Noise: press and review sites | 15 | 15 |
| Noise: other | 7 | 10 |
| **Noise** | **22/30** | **25/30** |
| Noise if press sites the code fetches count as real | 19/30 | 20/30 |

Some press values are API base URLs a review client fetches (3 in run 1's
sample, 5 in run 2's). By the spec's test they are real dependencies; the
last row counts them so. The verdict holds either way, and holds on the
"other" noise alone (7 and 10, against a threshold of 6).

The noise that is not press, by what the code does with the value:

| Kind of value | Run 1 | Run 2 |
|---|---|---|
| A link: attribution, `href`, search link | 3 | 4 |
| The service's own URL or domain | 3 | 2 |
| Sample or placeholder data | 1 | 1 |
| An identifier, not a host: OAuth scope | 0 | 1 |
| An embed check (`hostname === …`) | 0 | 1 |
| An email address with an `_ADDRESS` suffix | 0 | 1 |

One value came from a file under `docs/` and one from a design-tool preview
directory: the shared filter keeps both.

## Checks on the spike

**Reproduction.** Both runs were repeated at the same commit with the same
two `context.json` files. Every count and both 30-value samples came out
identical.

**The script against the spec.** The examples in §2 and §3 were written as 13
asserts (userinfo, port and case stripped, mesh hosts, each env form and
Spring relaxed binding, each secret form, every §2.4 exclusion, comment
blanking, exact and ambiguous names, `dependent_only`). One failed: a
`path=` secret call was counted twice. The fix changed no figure here, since
the repository has no secret values and distinct values were never doubled.

**Missed calls.** Every tracked file with a call site (`fetch`, an HTTP
client, an SDK client constructor) was checked for observations. 76 files
had none. 64 call the service's own API by relative path, which is
correct. The rest construct SDK clients with default endpoints (object
storage, an identity provider, a payment provider, an LLM API, an email
API), which §2 cannot see: there is no URL and no address variable.
Those are real dependencies the spike does not count, so the noise share
above is, if anything, low. The catalog's `boundaries:` already recognise
some of these clients (the AWS SDK, Prisma).

**Sampling.** All 126 run-1 values (120 in run 2) were classified by the same
rules, which reproduce the hand-marked offset-0 samples exactly. Every
other every-4th sample stays far above the threshold:

| Sample | Run 1 noise | Run 2 noise |
|---|---|---|
| offset 0 (the reviewed sample) | 22/30 | 25/30 |
| offset 1 | 21/30 | 22/30 |
| offset 2 | 23/30 | 21/30 |
| offset 3 | 24/30 | 27/30 |
| whole population | 96/126 (76%) | 95/120 (79%) |
| whole population, fetched press counted real | 86/126 (68%) | 85/120 (71%) |

Not done: a second, blind reviewer of the 30 values, and a catalog
maintained independently of this spike.

## What to narrow

- **host:** observe a URL only where the code calls it (an argument to an
  HTTP call or a client's base URL), not in every string literal. Links,
  attribution URLs, CSP lists and OAuth scopes are most of the noise.
- **host matching:** skip a generic first label (`api`, `www`) and use the
  next one.
- **env:** drop `_ADDRESS`, which also names email addresses.
- **The service's own URL:** `BASE_URL`, `NEXTAUTH_URL` and the service's own
  domain are not dependencies. The spec has no rule for them.
- **SDK clients:** a client built with its default endpoint is a dependency
  with no host and no variable. Observing the catalog's boundaries would
  find them; §2 as written never will.
- **Matching:** exact names linked 0 of 3 edges against a catalog that names
  infrastructure. Without the profile map (§3 rule 2) the drift section would
  list every documented dependency as missing. A second spike against a
  catalog someone maintains is needed before the map's share of the work is
  known.

Verdict: no-go — observe hosts only at call sites, skip generic first labels, drop `_ADDRESS`, exclude the service's own URLs, and re-run against an independently maintained catalog

## Re-run on the OpenTelemetry demo

The re-run of spec §12 (as amended in #89), on a public repository none of
the earlier runs was tuned on, with the ground truth written and hashed
before the run.

| Repo | Commit | Services scanned (each as one service) |
|---|---|---|
| `open-telemetry/opentelemetry-demo` | `ad06a6f9df40abde6c1f0c58b29b92f1076a74ec` | `src/frontend` (TypeScript, 104 files), `src/recommendation` (Java, 6), `src/ad` (Java, 5), `src/chatbot` (Python, 3) |

thunderstruck at `65d48e6`. Frozen 2026-10-23T06:40:44Z:

| File | sha256 |
|---|---|
| spike script (not committed) | `d829ce27e2becc2854d69cbcbbdd7fa68210a0d64046bc76bf72cf0bc512cd42` |
| `catalog.json` | `e87f6751dde940f62a82abf04652c0da44a9350efbf9c326594de0731d212146` |
| `map.toml` | `63f7189239e00c907e3864bc1ef519226b88de5ba33cf91aa59d0f2188599084` |
| `own_hosts.txt` | `cbc1581cd35c0a424deb5cb5ffc658aade5cbc8f4ed326510ec75ba7d0e670d6` |
| `seen.txt` | `080c2c6c59d742389a9b91a15da9f82c329465244f411e26f612cd6b52014f8a` |

- **Catalog:** the architecture page and the frontend, recommendation, ad
  and chatbot pages on opentelemetry.io. 11 outbound edges: the frontend to
  seven services, recommendation to product-catalog and flagd, ad to flagd,
  the chatbot to the agent.
- **Map:** from `compose.yaml`, `compose.agent.yaml` and `.env`. The demo has
  no `docker-compose.yml`; `compose.yaml` replaced it. One entry per entity,
  each with its host and its `*_ADDR` variable (`FLAGD_HOST` for flagd).
- **Own hosts:** the documentation names none.
- **Seen before the freeze** (`seen.txt`): `Cart.gateway.ts` and
  `Shipping.gateway.ts` in the frontend, and code-search path lists for
  `_ADDR` (11 paths), `httpx` (4), `requests.post` (1),
  `ManagedChannelBuilder` (1) and `HttpClient` (none). Frontend recall is
  not blind.

| Service | Documented edges linked | Missed edge and why (read after the run) |
|---|---|---|
| frontend | 7/7, all through the map | |
| recommendation | 1/2 | flagd: `new FlagdProvider(…)` reads its env itself. An env var read only by an SDK client (§2.2). |
| ad | 0/1 | flagd: the same. |
| chatbot | 0/1 | agent: the URL is built into a config object's field and called as `requests.post(self.config.agentBaseUrl, …)`. Object fields (§2.2). |

8 distinct values, all env, all documented. Unmatched 0, dependent_only 0,
ambiguous 0. Dropped 0. Own hosts excluded 0. No host was observed. The
cross-file counter's one hit (the chatbot) is the object-field case above,
not a read used in another file.

**Review:** no unmatched values, so nothing to review.

## Re-run on Bank of Anthos

The OpenTelemetry demo observed no host, no Python or Java form and nothing
to review, so a second public repository was run with the same frozen script
and its own ground truth.

| Repo | Commit | Services scanned (each as one service) |
|---|---|---|
| `GoogleCloudPlatform/bank-of-anthos` | `db35fea9fd090150e2398106aadb475576f80d94` | `src/frontend` (Python, 22 files), `src/accounts/userservice` (Python, 11), `src/accounts/contacts` (Python, 10), `src/ledger/ledgerwriter`, `balancereader`, `transactionhistory` (Java, 15 each), `src/loadgenerator` (Python, 5) |

thunderstruck at `65d48e6`. Frozen 2026-10-23T15:21:55Z:

| File | sha256 |
|---|---|
| spike script (unchanged) | `d829ce27e2becc2854d69cbcbbdd7fa68210a0d64046bc76bf72cf0bc512cd42` |
| `catalog.json` | `d230cbd6e10ee2a2587c15148ff5889e67e2ef1355ce38041244e03a3e8e05e6` |
| `map.toml` | `d0c7e9f1bb49ae7e9b9fd9d53a06575d3afa37f1ae03cb727deb6478a3ac5381` |
| `own_hosts.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty) |
| `seen.txt` | `2f8ab520e45002359f2ff0a82a788c8cf78ce2af9684fb1bb9b432c72d327473` |

- **Catalog:** the README's service table (names) and
  `docs/img/architecture.png` (edges). 11 outbound edges: loadgenerator to
  the frontend, the frontend to the five backends, userservice and contacts
  to accounts-db, the three ledger services to ledger-db.
- **Map:** from `kubernetes-manifests/`: Service names, the
  `service-api-config` and `*-db-config` ConfigMaps (`*_API_ADDR`,
  `ACCOUNTS_DB_URI`, `SPRING_DATASOURCE_URL`) and the load generator's
  `FRONTEND_ADDR`.
- **Own hosts:** the documentation names none.
- **Seen before the freeze:** the README, the diagram, the map sources and
  directory listings. No file under `src/` was opened or searched.

| Service | Documented edges linked | Missed edge and why (read after the run) |
|---|---|---|
| loadgenerator | 1/1 (`FRONTEND_ADDR` in its Kubernetes env) | |
| frontend | 0/5 | each backend: `app.config["BALANCES_URI"] = 'http://{}/balances'.format(os.environ.get('BALANCES_API_ADDR'))`, then `requests.post(url=app.config[…])`. Object fields (§2.2), here a config dict's key. |
| userservice, contacts | 0/2 | accounts-db: `UserDb(os.environ.get("ACCOUNTS_DB_URI"))`, and `create_engine(uri)` in `db.py`. A value used in another file (§2.2). |
| ledgerwriter, balancereader, transactionhistory | 0/3 | ledger-db: Spring Boot reads `SPRING_DATASOURCE_URL` itself; no code uses it. Counted as an env var read only by an SDK client (§2.2), with the framework as the client: the maintainer's reading. |

Not in the diagram, and so outside the gate: ledgerwriter calls
balancereader (`@Value("http://${BALANCES_API_ADDR}/balances")`, then
`restTemplate.exchange`). It was not observed either: the placeholder sits
inside a URL, and the value reaches the call through a field.

2 distinct values: env documented 1, env unmatched 1. Dropped: host
templated 8 (7 in the frontend, 1 in ledgerwriter). Own hosts excluded 0.
No host was observed.

**Review:** the one unmatched value, `ALLOWED_OAUTH_REDIRECT_URI` (the
frontend's Kubernetes env, `config.env.k8s-name`), is **noise**: the code
only compares a request parameter against it, and calls nothing with it.

## What the re-runs show

- **Linkage:** 9 of 22 documented edges. All 13 misses are gaps §2.2
  documents: object fields 6, an env var read only by an SDK client 5 (flagd
  twice, the Spring datasource three times), a value used in another file 2.
- **Noise:** 1 value reviewed across both runs, and it was noise. The gate's
  threshold is 6 noise values in a review of 30; one value cannot exceed it,
  and cannot show a rate either. The call-site rule produced almost nothing
  to review on these two repositories, which is the behaviour the amendment
  wanted, but these runs are no measure of its precision.
- **The commonest miss is a config key in the same file** (6 of 13): typical
  for Python services. It is a gap, so it does not fail the gate, but it
  costs most of the recall on Python. #91 tracks observing it.
- **Hosts:** none observed on either repository, so no response form and
  neither `config.host.key` nor `mesh.service-entry` is measured. Python and
  Java have no measured code form.

## Measured forms

A form is measured when a run observed at least one real dependency through
it and its values were in the noise review (§12). Both runs reviewed every
unmatched value, so each form below had all its unmatched values reviewed:
none for the first four, one (noise) for `config.env.k8s-name`.

| Id | Language | Real dependencies observed through it |
|---|---|---|
| `ts.read.destructure` | typescript | 7: the OpenTelemetry frontend's seven `*_ADDR` variables |
| `ts.connect.grpc-client` | typescript | 6: ad, cart, checkout, currency, product-catalog, recommendation |
| `ts.request.fetchlike` | typescript | 1: `SHIPPING_ADDR` |
| `config.env.placeholder` | yaml | 1: `PRODUCT_CATALOG_ADDR` in the recommendation service's `application.yaml` |
| `config.env.k8s-name` | yaml | 1: `FRONTEND_ADDR` in the load generator's Kubernetes env (and the one noise value) |

Every other candidate form is unmeasured and does not ship. Python and Java
have no measured form.

Verdict: go
