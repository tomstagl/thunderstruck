# Architecture context for system analysis — design

**Requirements:** [#1](https://github.com/tomstagl/thunderstruck/issues/1). The problem statement, user stories, scope, acceptance criteria (AC-n) and success measures live in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-23-architecture-context.md`
**Follow-up:** [#6](https://github.com/tomstagl/thunderstruck/issues/6), file-level linking of outbound edges.

This document describes how the feature works. Examples use generic names (`component:default/checkout`, `catalogctl`). Organisation-specific values belong only in that organisation's own `.thunderstruck.toml`.

## 1. Architecture

```
signals.py   →  hotspots.json
context.py   →  context.json           NEW · deterministic · runs the approved catalog command
bundle.py    →  bundles/*.md           + "Service context" section, + context_hash per bundle
investigator →  findings/*.json        may cite `catalog` evidence
validate.py  →  validation.json        resolves `catalog` refs against the pinned context
report.py    →  report.md/.json/index.json   + service context, + catalog_evidence
guardrail.py    reads index.json       + one factual line naming cited neighbours
```

`context.py` contains no model call. A configured command prints JSON, and `context_extract.py` narrows it to edge records. Every cited edge therefore traces back to a command the user approved and a parser covered by tests. This is what keeps CLAUDE.md's governing rule: models for judgment, scripts for anything that must be reproducible.

## 2. Configuration contract

The config is a `[context]` table in the repo's existing, committed profile, `.thunderstruck.toml`. It is not a separate file, because `.thunderstruck/` is gitignored scan output.

```toml
[context]
enabled = true                                   # false = the user declined setup; never prompt again
entity_ref = "component:default/checkout"        # detected from catalog-info.yaml, confirmed by the user
max_age_days = 30                                # cache lifetime; optional, default 30

[[context.sources]]
name = "catalog"
kind = "command"                                 # the only kind in v1
argv = ["catalogctl", "get", "entity", "{entity_ref}", "-o", "json"]
preflight = ["catalogctl", "auth", "status"]     # optional; must exit 0
timeout_s = 20                                   # per command, 1–60
extractor = "backstage-relations"                # the only extractor in v1
edge_types = { dependsOn = "outbound", dependencyOf = "inbound" }
neighbour_attributes = { tier = "example.com/criticality-tier" }   # label -> annotation key
```

Validation rules. A violation gives status `invalid_config`, with one warning per problem.

- **Entity refs** match `kind:namespace/name`, using characters `[A-Za-z0-9_.-]`.
- **Exactly one source in v1.** The list shape leaves room for an observed-topology source later.
- **`argv` and `preflight`** are non-empty lists of non-empty strings. `{entity_ref}` is the only placeholder. It is substituted per argument, and nothing runs through a shell.
- **`edge_types`** maps relation-type names (`^[A-Za-z][A-Za-z0-9_-]{0,63}$`) to `inbound` or `outbound`.
- **`neighbour_attributes`** labels match `^[a-z][a-z0-9_]{0,31}$`.
- **No credentials anywhere.** Commands inherit the environment, so whatever a CLI reads (tokens, config files) is set up outside thunderstruck.
- **`config_hash`** is the sha256 of the canonical JSON of `entity_ref` and the normalised source. It identifies the definition for trust and cache reuse. `max_age_days` is excluded, so changing the cache lifetime neither re-prompts for trust nor discards the cache.

## 3. Trust on first use

A committed `argv` is code execution. `context.py` runs a source only when one of these holds:
- `(absolute repo path, config_hash)` is listed in `$XDG_CONFIG_HOME/thunderstruck/trusted-sources.json` (default `~/.config/…`);
- `THUNDERSTRUCK_TRUST_CONTEXT=1` is set (CI, sample generation).

`context.py` is never interactive. The setup skill shows the exact `argv` and `preflight` to the user, asks for approval, and only then calls `context.py --approve`, which records the key. Any change to the definition changes `config_hash`, so the new definition has to be approved again.

## 4. Setup skill: `thunderstruck-context-config`

This is both the first-run dialog and the way to update the config later.

1. `context.py --detect-entity` reads `catalog-info.yaml` at the repo root. Exactly one Backstage `Component` document gives `component:<namespace|default>/<name>`. Zero or several give no answer, and the skill asks the user instead.
2. Ask for the command that prints that entity as JSON. Fill in the `[context]` table in `.thunderstruck.toml`.
3. Show `argv` and `preflight`, get explicit approval, then run `context.py --approve`.
4. Run `context.py --refresh`, show the extracted edges, and ask the user to confirm them.
5. On decline, write `[context]` with `enabled = false`.

`thunderstruck-scan` offers this skill only when `context.py` reports `not_configured` **and** the session can ask the user. Headless runs never prompt.

## 5. Fetch: `scripts/context.py`

**Statuses.** `context.json` always has one of these statuses. The three usable ones (`fresh`, `cached`, `stale`) put a Service context section in bundles.

| Status | When | In bundles | Warning |
|---|---|---|---|
| `not_configured` | no `[context]` table | no | none |
| `disabled` | `enabled = false` | no | none |
| `invalid_config` | the table fails validation | no | one per problem |
| `untrusted` | definition not approved on this machine | no | how to approve |
| `fresh` | fetched this run | yes | truncation, rejected attributes, budget, failed neighbours |
| `cached` | reused: same `config_hash`, younger than `max_age_days` | yes | the warnings recorded when fetched |
| `stale` | refresh failed; reused a cache with the same `config_hash`, younger than 2 × `max_age_days` | yes | `service context is N days old; refresh failed: <reason>` |
| `failed` | fetch failed, no usable cache | no | `service context unavailable: <reason>` |

`not_configured` and `disabled` deliberately emit no warning. A repo that never set this up must produce the same `report.md` as before (AC-7).

**Algorithm**, run once per scan before `bundle.py`:
1. Resolve the status up to `untrusted`, using §2 and §3.
2. **Cache.** Reuse the cache if it has the same `config_hash`, a usable status, an age below `max_age_days`, and `--refresh` wasn't given. Reuse runs no command at all.
3. **Preflight, then main fetch.** Run `preflight`, then `argv` for `entity_ref`, with these rules:
   - stdin is `/dev/null` and stderr is discarded (it may contain secrets);
   - each command runs in its own process group, so a timeout kills the CLI's children too. A browser-login helper that keeps stdout open must not hang the scan;
   - each command's timeout is `min(timeout_s, remaining budget)`;
   - **no retries**.
4. **Extract.** Apply the extractor (§6). Keep at most **25 edges per direction**, in sorted order, and record the rest in `truncated`.
5. **Neighbour attributes.** Only when `neighbour_attributes` is set, fetch each kept neighbour with the same `argv`:
   - at most **4 at once**;
   - one **total budget of 60 s** covers every command in the run;
   - a neighbour not started before the budget runs out is listed in a warning, and its edge is kept without attributes;
   - a neighbour whose fetch fails keeps its edge; only its attributes are dropped, with a warning.

   These are detail fetches on 1-hop neighbours. A neighbour's own relations are never read. Depth is a constant, not config.
6. **Result.** On success, the status is `fresh`. Raw successful responses go to `.thunderstruck/context/raw/` for audit, and are never read by bundles.
7. **Main fetch failed.** Use the stale fallback if §5's `stale` conditions hold; otherwise the status is `failed`.

**`context.json`** (`thunderstruck.context/v1`):

```json
{
  "schema": "thunderstruck.context/v1",
  "status": "fresh",
  "entity_ref": "component:default/checkout",
  "config_hash": "sha256:…",
  "context_hash": "sha256:…",
  "fetched_at": "2026-09-23T10:00:00+00:00",
  "edges": [
    {"ref": "dependencyOf component:default/web-frontend", "type": "dependencyOf",
     "direction": "inbound", "neighbour": "component:default/web-frontend",
     "source": "catalog", "attributes": {"tier": "2"}}
  ],
  "truncated": {"inbound": 0, "outbound": 0},
  "warnings": []
}
```

`context_hash` is the sha256 of the canonical JSON of `entity_ref`, `edges` and `truncated`. It never covers `fetched_at`, `status` or `warnings`. Volatile catalog fields (`uid`, `etag`, relation order) never reach it, so they can't force re-investigation.

## 6. Extraction: `backstage-relations`

Implemented in `scripts/context_extract.py` as pure functions.

- It reads Backstage's processed `relations[]`, never `spec.dependsOn`. Hand-written `spec.dependsOn` is outbound only, and real catalogs often omit it (confirmed by the spike).
- A relation becomes an edge when its `type` is a key of `edge_types` and its target is a valid entity ref. The target comes from `targetRef`, or from the older `target: {kind, namespace, name}` form.
- Edges are deduplicated on `(type, neighbour)` and sorted by it.
- **Ref grammar:** `<type> <neighbour_ref>`, for example `dependsOn component:default/payments-api`. Direction comes from the type. Our own entity is implied, since every edge is 1 hop from it.
- **Attributes** are copied from the neighbour's `metadata.annotations`, keyed by `neighbour_attributes`. They are kept only if they match `^[A-Za-z0-9_.:-]{1,32}$`. A rejected value is reported by neighbour and label, and never echoed. Configure coarse labels (`HIGH`), not floats: a changing score would change `context_hash`.
- Free text (descriptions, titles, links) never leaves this module. That is the whole prompt-injection surface: refs, types and short tokens.

## 7. Bundles

`bundle.py` loads `context.json`. When the status is usable, it adds this section after the repo profile, identical in every bundle of a scan:

```
## Service context (component-level, 1 hop)

From the service catalog. These edges describe the whole component, not this file. …

This component: `component:default/checkout`

**Depends on**
- `dependsOn component:default/payments-api` — tier: 1
**Depended on by**
- `dependencyOf component:default/web-frontend` — tier: 2
- … and 3 more not listed (cap 25)
```

- The section is never trimmed. The other sections share `budget − tokens(section)`, floored at half the budget, so the whole bundle stays within budget. Without context the budget is untouched, so bundles are byte-identical to before (AC-7).
- It never shows `status`, `fetched_at` or warnings. A stale fallback therefore leaves bundles byte-identical (AC-12).
- `bundles/index.json` records `context_hash` per bundle and at the top level.
- `section_profile` ignores the `[context]` key. A profile that holds only `[context]` renders no "Repo profile" section.

## 8. Evidence and validation

- New evidence type `catalog`. The item stays `{type, ref, note}`, and `ref` is copied verbatim from the Service context section.
- `validate.py` checks catalog refs in order and reports the first failure:
  1. the scan has usable context;
  2. the finding's bundle was built from the current `context_hash` (**snapshot pinning**; otherwise "context changed since bundling");
  3. the ref is an edge in `context.json`.
- The existing rule is unchanged: every finding needs a `code` item, so catalog-only findings fail.
- Prose isn't parsed. The validator doesn't look for service names in `blast_radius`.
- On success, every finding is stamped with `catalog_evidence: [{ref, direction, neighbour, attributes}]`, resolved from `context.json`, and `[]` when it cites none. Reports and the guardrail read attributes from this stamp, never from the investigator's text.
- Wording stays component-level ("web-frontend depends on this component"). The investigator prompt states this rule. It can't be enforced mechanically, and this document says so.

## 9. Report, index and guardrail

All schema changes are additive, so `thunderstruck.report/v1` and `thunderstruck.index/v1` keep their versions.

- **`report.md`**
  - Run warnings include `context.json` warnings.
  - A **Service context** section follows them, with the entity, edge count, `fetched YYYY-MM-DD (N days ago)`, a short `context_hash` and the edge table.
  - A finding that cites edges gets a **Dependents / dependencies** row.
  - Without usable context, none of this appears.
- **`report.json`**
  - Top-level `service_context`: `{status, entity_ref, context_hash, fetched_at, edges, truncated}` or `null`.
  - Every finding carries `catalog_evidence`.
- **`index.json`** entries carry `catalog_evidence` when it's non-empty.
- **`guardrail.py`** appends at most one line per direction to its existing message:
  - `Cited dependents of this component: web-frontend (tier: 2), mobile-bff.`
  - `Cited dependencies of this component: payments-api (tier: 1).`

  Each line shows at most 5 names, then `and N more`. These are statements of fact. The guardrail stays stdlib-only, always exits 0, and keeps a median under 100 ms.

## 10. Security

- **Trust on first use** (§3) gates every command.
- Only allow-listed, regex-checked fields reach bundles (§6).
- Stderr is discarded, and raw output is stored only for successful calls.
- `orchestration.md` "What leaves the machine" and README "Privacy" state the change: an approved context command may make network calls, and thunderstruck itself still makes none.

## 11. Test strategy

- **Stub CLI:** `tests/fixtures/fake_catalog.py`, driven by env vars. It can:
  - fail, time out, print bad JSON, sleep, or randomise volatile fields;
  - hold stdout open through a grandchild;
  - read stdin;
  - leave a marker file on every call.
- **Fixture:** `build_fixture.add_service_context()` writes `catalog-info.yaml` and a `[context]` table, both untracked, so the fixture's history and SHAs don't change.
- **Unit tests:** extractor (positive and negative samples), config validation, trust, and the command runner.
- **Fetch state machine:** every status, cache, refresh, stale fallback and its limits, budget, truncation, partial failure.
- **Pipeline tests** over a scanned fixture with context: bundles, determinism, pinning, report, index.
- **Guardrail:** dependents lines.
- **Generated sample:** `gen_sample_report.py` cites a catalog edge, and the docs-sync test asserts it.

## 12. Decisions and rationale

| Decision | Why |
|---|---|
| A command source, not MCP | Scripts can't call MCP. Fetching through an agent would put model output underneath validated evidence. A CLI that fronts an MCP works. |
| Component-level edges; outbound file linking deferred to #6 | Inbound edges can't be tied to our files. Outbound linking's real hit rate is unmeasured. |
| 1 hop as a constant | A cap you can raise isn't a cap. One neighbour's risk label is signal enough. |
| Config in `.thunderstruck.toml` | Committed and shared by the team. `.thunderstruck/` is gitignored output. |
| `max_age_days = 30`, stale fallback to 2 × | Catalogs change rarely. A lapsed login shouldn't cost two full re-investigation rounds. |
| Coarse attributes only | Keeps `context_hash` from changing on noise. |
| Guardrail line | The blast radius matters most when someone is about to edit. |
| Observability platforms (e.g. Dynatrace) later, as another `command` source with a per-vendor extractor | Vendor-agnostic in the same way the catalog source is. |

## 13. Open design questions

- **Observed-topology source.** Does the extractor interface fit a second vendor without changes? That needs a fixed query window for determinism and a stable mapping from catalog entities to the platform's service identities.
- **A second catalog extractor**, for non-Backstage catalogs. Deferred until a real user needs it.
