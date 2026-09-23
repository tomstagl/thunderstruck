# Architecture context for system analysis — PRD & design

Tracks [#1](https://github.com/tomstagl/thunderstruck/issues/1). Follow-up: [#6](https://github.com/tomstagl/thunderstruck/issues/6) (file-level linking of outbound edges).

Status: draft v3. Revised after the critique, after a feasibility spike against a real Backstage catalog, and again after a gap review.

## 1. Problem

Thunderstruck analyses one repository in isolation. A finding's `blast_radius` is prose written from in-repo evidence only. Nothing in a scan knows that other services exist, so it cannot say that a failure here reaches a service that depends on this one.

## 2. Goal

Let a scan know the scanned component's direct neighbours in the org's service catalog: who it depends on and who depends on it. Those neighbours then appear in bundles, in findings and in the report. Every cited edge must be mechanically verified, with the same rigour as `code`/`commit`/`detector` evidence.

The mechanism must be **company-agnostic**. Thunderstruck ships a generic source type and a generic extractor. Everything specific to one organisation (CLI name, catalog namespace, annotation keys) lives in that organisation's checked-in config, never in plugin code.

## 3. Users & stories

- **Developer scanning a service repo.** Sees which services depend on this component, with the risk labels their catalog provides, next to findings, and can judge how far a failure spreads.
- **Maintainer at another company.** Points thunderstruck at their own catalog by writing config. No plugin code changes.
- **CI owner.** Runs scans headless. A scan never hangs on a login prompt or an interactive dialog.
- **Anyone scanning a repo they don't control.** A checked-in config never runs a command on their machine without their explicit approval.

## 4. Scope

### In (v1)
- One context category: **service catalog, 1-hop dependencies**, both directions.
- One source kind: **`command`**. Thunderstruck runs a configured CLI that prints JSON.
- One built-in extractor: **`backstage-relations`**. It reads Backstage's processed `relations[]` graph, so it works against any Backstage instance, whatever CLI fronts it.
- Edges are **component-level** context. They are not tied to specific files.

### Out (v1)
- **File-level linking of outbound edges.** Tracked in #6.
- **MCP-only sources.** A deterministic script cannot call MCP; only an agent can. An agent-based fetch would put model output underneath mechanically validated evidence. A catalog reachable only through MCP is unsupported in v1. Any CLI, including `curl` against a REST API, qualifies as a command source.
- **Observed topology from APM tools** (e.g. Dynatrace via `dtctl`). It is the natural second source and is expected to reuse the `command` kind. It is deferred until a spike confirms a working query and measures how much the edge set changes with the query window. Comparing declared and observed edges is the most valuable open question.
- **ADR registries, agentic docs, architecture diagrams.** These are future context categories.
- **Graph walks beyond 1 hop.**

## 5. Configuration

`.thunderstruck/context.yml` is committed to the repo, next to `profile.yml`. Example with generic names:

```yaml
version: 1
enabled: true                                  # false = user declined; never prompt again
entity_ref: component:default/checkout         # detected from catalog-info.yaml, confirmed by the user
sources:
  - name: catalog
    kind: command
    argv: [catalogctl, get, entity, "{entity_ref}", -o, json]
    preflight: [catalogctl, auth, status]      # optional; must exit 0 or the source is skipped
    timeout_s: 20
    extractor: backstage-relations
    edge_types:                                # relation type -> direction; others ignored
      dependsOn: outbound
      dependencyOf: inbound
    neighbour_attributes:                      # label -> annotation key, copied verbatim
      tier: example.com/criticality-tier
```

Rules:
- **No secrets in the file.** Commands inherit the environment. Credentials are whatever the CLI already reads, and CI sets them the way it sets any other env var. Thunderstruck never reads, stores or passes tokens.
- `{entity_ref}` is the only placeholder. Substitution happens per argument. A command runs as an argument list and **never through a shell**.
- `edge_types` is config because catalogs model dependencies differently. Some use `dependsOn`/`dependencyOf`; many use `consumesApi`/`apiConsumedBy`.
- **Depth is a constant (1 hop), not config.** A hard cap you can raise isn't a cap.

### Trust on first use

A checked-in `argv` is code execution. Before a source runs for the first time on a machine, thunderstruck:
1. shows the exact `argv` and `preflight`;
2. asks for approval;
3. stores the approval outside the repo, in `~/.config/thunderstruck/trusted-sources.json`, keyed by the repo's absolute path plus the sha256 of the source definition.

Any change to the source definition requires approval again. In non-interactive runs an untrusted source is skipped with a warning. CI can pre-approve with `THUNDERSTRUCK_TRUST_CONTEXT=1`.

## 6. Setup: `thunderstruck-context-config` skill

This skill has the same naming shape as `thunderstruck-scan` and `thunderstruck-verify`. It runs the first-time setup, and it's the one way to update the config later.

1. Look for `catalog-info.yaml` (or any `apiVersion: backstage.io` document). Propose `entity_ref` as `<kind>:<namespace|default>/<metadata.name>`.
2. Ask for the command that fetches an entity as JSON. Test-run it once, after trust approval.
3. Show the extracted edges and ask the user to confirm them.
4. Write `context.yml`. If the user declines, write `enabled: false`.

`thunderstruck-scan` runs this dialog automatically only when **all** of these hold:
- the session is interactive;
- no `context.yml` exists;
- the user hasn't declined before.

In every other case the scan continues without context.

## 7. Fetch: `scripts/context.py`

This is a deterministic step, no model involved. It runs once per scan, before `bundle.py`:

1. Load `context.yml`. If context is disabled, missing or untrusted, write nothing and emit a warning.
2. Run `preflight`, then `argv`, with stdin closed and `timeout_s` applied. **No retries.** A failure (timeout, non-zero exit, unparsable JSON) skips the source with the reason in `warnings`.
3. Extract edges from `relations[]`:
   - keep only types listed in `edge_types`;
   - record the neighbour ref;
   - deduplicate and sort by `(type, ref)`.
4. For each neighbour, up to **25 per direction**, fetch the neighbour entity with the same `argv` and copy `neighbour_attributes`:
   - values must match `^[A-Za-z0-9_.:-]{1,32}$`, otherwise they're dropped with a warning;
   - coarse labels only: a label like `HIGH` qualifies, and floats should be configured out.

   Anything over the cap is recorded as a count and shown as "and N more", never silently dropped. Neighbour fetches are *detail fetches*, not graph expansion. A neighbour's own neighbours are never read.

   **Budget.** At most 4 neighbour fetches run at once, matching the plugin's existing concurrency limit. All fetches together, the main one included, share a **total budget of 60s**. When the budget runs out, no new fetches start, and the neighbours that weren't fetched are listed as incomplete in `warnings`.

   **Partial failure.** If one neighbour fetch fails (timeout, non-zero exit, bad JSON), its edge is kept and only its attributes are dropped, with a warning. Only a failure of the main entity fetch skips the whole source.
5. Write `.thunderstruck/context.json` containing:
   - the edges;
   - `context_hash`: sha256 of the canonical, sorted edges and attributes;
   - a `fetched_at` timestamp;
   - source metadata.

   Raw responses go to `.thunderstruck/context/raw/` for audit. They are never embedded in bundles.

**Caching.** `context.json` is reused without running any command if both hold:
- it is younger than `max_age` (default 30 days; catalog entries change rarely, and a refresh with unchanged edges costs no re-investigation anyway);
- the source-definition hash is unchanged.

`--refresh-context` forces a fetch.

**Stale fallback.** If the cache has expired and the refresh fails (preflight failure, lapsed login, timeout, bad JSON), the scan keeps using the existing `context.json`. The report then carries a visible warning, e.g. `service context is 34 days old; refresh failed: preflight exited 1`. Three limits apply:
- **Same source only.** The fallback applies only while the source-definition hash is unchanged. Data fetched for a different `entity_ref` or command is never reused.
- **Hard age limit.** The fallback is allowed until the context is 2 × `max_age` old (60 days by default). Past that, the context is dropped and the scan degrades as in §12.
- **No retry.** The failed refresh is not retried within the scan. The next scan tries again.

This matters because dropping the context removes the Service context section from every bundle, so every hotspot is investigated again twice: once without the context and once more when the refresh succeeds. Keeping the old edges avoids both rounds.

**Determinism.** The cache and bundle hashes are computed over the extracted, sorted edges and attributes, never over raw responses. Volatile catalog fields (`uid`, `etag`, timestamps, relation order) therefore cannot trigger re-investigation. `fetched_at` never enters a bundle.

## 8. Bundles

`bundle.py` adds a **Service context** section, identical in every bundle of a scan:

```
## Service context (component-level, 1 hop)
This component: component:default/checkout
Depends on:     dependsOn component:default/payments-api   [tier: 1]
Depended on by: dependencyOf component:default/web-frontend [tier: 2]
                … and 3 more (cap 25)
```

Each edge line starts with its exact **catalog ref**: `<type> <neighbour_ref>`.

`bundles/index.json` records the `context_hash` each bundle was built from.

A real catalog change changes this section and therefore every bundle, so every hotspot is investigated again. This is intended: the blast radius of every finding may have changed. Coarse attribute values keep this from happening on noise.

## 9. Evidence: `catalog` type

- Evidence items stay `{type, ref}`. A `catalog` ref is the edge string copied verbatim from the bundle, e.g. `dependencyOf component:default/web-frontend`. Our own entity is implied, because every edge is 1 hop from it.
- `validate.py` accepts a `catalog` ref only if it exactly matches an edge in `context.json`. This is the same rule as `detector` refs against `hotspots.json`.
- Validation is **pinned to the snapshot** each bundle was built from. If the `context_hash` recorded for a finding's bundle doesn't equal the current `context.json`'s hash (e.g. the cache expired and refreshed mid-scan), the finding's catalog refs fail validation with a "context changed since bundling" reason. The finding goes to the repair round, or is listed under **Incomplete**. It is never validated against newer data.
- The existing rule still applies: every finding needs at least one `code` evidence item. A finding resting only on catalog evidence is rejected.
- The validator does **not** parse `blast_radius` prose for service names. Short names like `api` make that unreliable. Instead, the report shows cited catalog edges, with attributes taken from `context.json`, as structured data beside the prose. The report is the source of truth for the attributes; the investigator's text isn't.
- Wording is component-level: "web-frontend depends on this component", not "on this file". The investigator prompt states this rule. It can't be enforced mechanically, and the spec says so.

## 10. Report & guardrail

All schema changes are **additive**. `thunderstruck.report/v1` and `thunderstruck.index/v1` keep their version, because existing consumers ignore unknown fields. `skills/thunderstruck-scan/references/report-format.md` documents the new fields.

**`report.md`**
- A **Service context** section after the summary: the edge table once (ref, direction, attributes), the `context_hash`, and when the context was fetched (e.g. "fetched 2026-09-01, 22 days ago"). The report isn't a bundle, so a date here doesn't affect caching.
- Each finding's table gains a **Dependents / dependencies** row listing its cited catalog refs with attributes. The attributes are taken from `context.json`, not from the investigator's text.
- Warnings cover:
  - skipped sources, with the reason;
  - truncated neighbour lists;
  - incomplete fetches (budget exhausted);
  - dropped attribute values;
  - untrusted sources.

**`report.json`**
- Top-level `service_context`: `{entity_ref, context_hash, edges: [{ref, type, direction, neighbour, attributes}], truncated: {inbound: n, outbound: n}}`, or `null` when no context was used.
- Per finding: `catalog_evidence: [{ref, direction, attributes}]`. It's resolved from `context.json` and is empty when the finding cites none.

**`index.json` → guardrail**
- `render_index()` copies each finding's `catalog_evidence` into its index entry.
- `guardrail.py` appends **one statement-of-fact line** per warned file when any finding there cites catalog edges, e.g. `Cited dependents of this component: web-frontend (tier: 2), mobile-bff (tier: 1).`
- At most 5 neighbours on that line, then "and N more".
- The existing hard constraints are unchanged: stdlib only, always exit 0, median under 100ms, facts rather than instructions.

## 11. Security & data handling

- **Catalog content is data, not instruction.** Only structured fields enter bundles: relation types, entity refs and allow-listed attribute values that pass the value regex. Free-text descriptions are never copied, which shrinks the prompt-injection surface.
- **Trust on first use** gates every command (see §5).
- **Update `orchestration.md` → "What leaves the machine".** A configured context source runs a user-approved command, and that command may make network calls. Thunderstruck itself still makes none.

## 12. Degradation

A failed refresh with a usable cache is **not** degradation. It uses the stale fallback from §7.

In every one of these cases the scan behaves exactly as it does today, with no `catalog` evidence available that run, plus a visible warning naming the reason:
- no config, or context declined;
- untrusted source in a non-interactive run;
- preflight or command failure;
- timeout;
- stale fallback past its hard age limit, or a source definition that has changed since the cache was written.

## 13. Acceptance criteria

1. Scanning a repo with a valid `context.yml` produces a `context.json` holding exactly the configured relation types from `relations[]`, sorted and deduplicated.
2. Two scans against an unchanged catalog produce byte-identical bundles, even when raw responses differ in volatile fields.
3. A finding citing a `catalog` ref absent from `context.json` fails validation. A finding with only catalog evidence fails validation.
4. A checked-in source never runs without approval on that machine. Changing its `argv` requires approval again.
5. A headless scan never prompts. With a failing or unauthenticated command it finishes, and a warning names the reason, within `timeout_s` plus normal scan time.
6. Neighbour lists over 25 per direction are truncated with the count reported. Depth never exceeds 1 hop.
7. A repo without `context.yml` scans exactly as before this feature.
8. The checked-in sample report contains at least one validated finding that cites a `catalog` edge.
9. The context step never takes more than 60s in total, whatever the neighbour count or how slow the command is. Neighbours not fetched are listed as incomplete.
10. Editing a file whose finding cites catalog edges makes the guardrail emit the dependents line. The guardrail latency test still passes.
11. A catalog ref validated against a `context.json` other than the one its bundle was built from is rejected.
12. When the cache has expired and the refresh fails, the scan reuses the old context and emits a warning showing its age and the failure reason. Bundles stay byte-identical, so no hotspot is investigated again. Past 2 × `max_age`, or after a source-definition change, the old context is not used.

## 13a. Success measures

These are the outcome targets, measured by hand while dogfooding. They're separate from the functional acceptance criteria above.

- **Relevance:** on the first 3 real repos, ≥ 70% of cited catalog edges are judged relevant by the repo owner. Sample: about 20 findings.
- **Coverage:** every dogfooded repo with a configured catalog gets ≥ 1 validated finding that cites an edge.
- **Cost:** the context step adds ≤ 60s to a scan. This is enforced by the budget, so it's measured only to confirm typical runs sit well below it.
- **No regression:** a repo without `context.yml` produces a byte-identical report to a scan without this feature, apart from the timestamp.

## 14. Testing

- **Fixture.** The fixture repo gains a `catalog-info.yaml` and a stub CLI: a small Python script that prints canned Backstage JSON and can simulate timeout, non-zero exit and bad JSON. Every test is deterministic, with no real catalog involved.
- **Extractor samples**, following the negative-control discipline:
  - positive: relations present;
  - positive: `relations[]` present while `spec.dependsOn` is absent;
  - duplicates;
  - unknown relation types ignored;
  - negative: an injection-shaped annotation value is rejected.
- **`validate.py`:** valid catalog ref; ref not in `context.json`; catalog-only finding.
- **`context.py`:**
  - failures: timeout, non-zero exit, bad JSON, preflight failure;
  - trust and headless: untrusted source not executed, headless skip;
  - caching: cache hit, `--refresh-context`;
  - stale fallback:
    - expired cache plus a failing refresh reuses the old context and warns;
    - fallback past 2 × `max_age` is refused;
    - fallback after a source-definition change is refused;
    - a successful refresh with identical edges leaves bundles unchanged;
  - neighbour handling: truncation at the cap, total-budget exhaustion (the stub sleeps), a neighbour fetch failing while its edge is kept.
- **`validate.py` snapshot pinning:** a catalog ref checked against a changed `context_hash` is rejected.
- **Determinism:** raw responses that differ only in volatile fields produce identical `context.json` edges, an identical `context_hash` and identical bundles.
- **`gen_sample_report.py`** exercises the new evidence type (criterion 8). Generation and CI run with `THUNDERSTRUCK_TRUST_CONTEXT=1`, so the stub CLI passes the trust gate non-interactively.
- **Report and guardrail:**
  - `report.json` `service_context` and `catalog_evidence` shape;
  - `index.json` carries `catalog_evidence`;
  - the guardrail emits the dependents line, capped at 5;
  - the existing latency and stdlib-only AST tests still pass.
- **Setup dialog:** `entity_ref` detection from `catalog-info.yaml` is a plain function with pytest cases (namespace present or absent, multiple documents in one file, no Backstage document). The conversation itself is verified manually. The plugin install check does *not* exercise it.

## 15. Open questions

- **Dynatrace as a second source:** the working `dtctl` query, stable entity-id mapping between catalog and APM, and sensitivity to the query window. Declared vs observed edges is the key question.
- **A second extractor**, for non-Backstage catalogs. Deferred until a real non-Backstage user appears.
