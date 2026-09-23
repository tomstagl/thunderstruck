# Architecture context for system analysis — PRD & design

Tracks [#1](https://github.com/tomstagl/thunderstruck/issues/1). Follow-up: [#6](https://github.com/tomstagl/thunderstruck/issues/6) (file-level linking of outbound edges).

Status: draft v2 (revised after critique and a feasibility spike against a real Backstage catalog).

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
- **Guardrail changes.** `guardrail.py` is untouched in v1.

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
5. Write `.thunderstruck/context.json`: the edges plus a `fetched_at` timestamp and source metadata. Raw responses go to `.thunderstruck/context/raw/` for audit. They are never embedded in bundles.

**Caching.** `context.json` is reused without running any command if both hold:
- it is younger than `max_age` (default 24h);
- the source-definition hash is unchanged.

`--refresh-context` forces a fetch.

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

A real catalog change changes this section and therefore every bundle, so every hotspot is investigated again. This is intended: the blast radius of every finding may have changed. Coarse attribute values keep this from happening on noise.

## 9. Evidence: `catalog` type

- Evidence items stay `{type, ref}`. A `catalog` ref is the edge string copied verbatim from the bundle, e.g. `dependencyOf component:default/web-frontend`. Our own entity is implied, because every edge is 1 hop from it.
- `validate.py` accepts a `catalog` ref only if it exactly matches an edge in `context.json`. This is the same rule as `detector` refs against `hotspots.json`.
- The existing rule still applies: every finding needs at least one `code` evidence item. A finding resting only on catalog evidence is rejected.
- The validator does **not** parse `blast_radius` prose for service names. Short names like `api` make that unreliable. Instead, the report shows cited catalog edges, with attributes taken from `context.json`, as structured data beside the prose. The report is the source of truth for the attributes; the investigator's text isn't.
- Wording is component-level: "web-frontend depends on this component", not "on this file". The investigator prompt states this rule. It can't be enforced mechanically, and the spec says so.

## 10. Report

- `report.md` / `report.json` gain a **Service context** section listing the edge table once.
- Each finding lists its cited catalog edges with their attributes.
- Warnings cover:
  - skipped sources, with the reason;
  - truncated neighbour lists;
  - dropped attribute values;
  - untrusted sources.
- `index.json` (the guardrail's input) is unchanged in v1.

## 11. Security & data handling

- **Catalog content is data, not instruction.** Only structured fields enter bundles: relation types, entity refs and allow-listed attribute values that pass the value regex. Free-text descriptions are never copied, which shrinks the prompt-injection surface.
- **Trust on first use** gates every command (see §5).
- **Update `orchestration.md` → "What leaves the machine".** A configured context source runs a user-approved command, and that command may make network calls. Thunderstruck itself still makes none.

## 12. Degradation

In every one of these cases the scan behaves exactly as it does today, with no `catalog` evidence available that run, plus a visible warning naming the reason:
- no config, or context declined;
- untrusted source in a non-interactive run;
- preflight or command failure;
- timeout.

## 13. Acceptance criteria

1. Scanning a repo with a valid `context.yml` produces a `context.json` holding exactly the configured relation types from `relations[]`, sorted and deduplicated.
2. Two scans against an unchanged catalog produce byte-identical bundles, even when raw responses differ in volatile fields.
3. A finding citing a `catalog` ref absent from `context.json` fails validation. A finding with only catalog evidence fails validation.
4. A checked-in source never runs without approval on that machine. Changing its `argv` requires approval again.
5. A headless scan never prompts. With a failing or unauthenticated command it finishes, and a warning names the reason, within `timeout_s` plus normal scan time.
6. Neighbour lists over 25 per direction are truncated with the count reported. Depth never exceeds 1 hop.
7. A repo without `context.yml` scans exactly as before this feature.
8. The checked-in sample report contains at least one validated finding that cites a `catalog` edge.

## 14. Testing

- **Fixture.** The fixture repo gains a `catalog-info.yaml` and a stub CLI: a small Python script that prints canned Backstage JSON and can simulate timeout, non-zero exit and bad JSON. Every test is deterministic, with no real catalog involved.
- **Extractor samples**, following the negative-control discipline:
  - positive: relations present;
  - positive: `relations[]` present while `spec.dependsOn` is absent;
  - duplicates;
  - unknown relation types ignored;
  - negative: an injection-shaped annotation value is rejected.
- **`validate.py`:** valid catalog ref; ref not in `context.json`; catalog-only finding.
- **`context.py`:** timeout; non-zero exit; bad JSON; preflight failure; untrusted source not executed; headless skip; cache hit; `--refresh-context`; truncation at the cap.
- **Determinism:** raw responses that differ only in volatile fields produce identical `context.json` edges and identical bundles.
- **`gen_sample_report.py`** exercises the new evidence type (criterion 8).
- **The dialog skill** is verified manually. The plugin install check does *not* exercise it.

## 15. Open questions

- **Dynatrace as a second source:** the working `dtctl` query, stable entity-id mapping between catalog and APM, and sensitivity to the query window. Declared vs observed edges is the key question.
- **Default `max_age`:** 24h is a guess.
- **A second extractor**, for non-Backstage catalogs. Deferred until a real non-Backstage user appears.
