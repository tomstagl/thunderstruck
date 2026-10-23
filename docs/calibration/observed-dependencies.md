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
