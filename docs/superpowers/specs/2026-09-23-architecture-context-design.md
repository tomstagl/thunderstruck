# Architecture context for system analysis — design spec

Tracks GitHub issue [#1](https://github.com/tomstagl/thunderstruck/issues/1).

## Problem

Thunderstruck currently analyses one repository in isolation. A hotspot's
`blast_radius` field is free-text prose written by the investigator from
in-repo evidence only (call sites, imports, other hotspots in the same scan —
see `scripts/bundle.py`'s "related" section). It cannot say a change also
risks breaking a *different* service, because it has no notion that other
services exist.

The issue asks to connect external architecture information — starting with
whatever is reachable over MCP — so cross-service impact can inform findings,
not just single-repo blast radius.

## Goal (v1)

Let a scan know which other services depend on the one being scanned, sourced
from the org's own service catalog (e.g. Backstage), and let a finding's
`blast_radius` cite a specific dependency edge as mechanically-verified
evidence — with the same rigor `code`/`commit`/`detector` evidence already
gets.

Every org's tooling differs (this project's own author uses Backstage +
an ADR registry + agentic docs; another org will have none of those). The
contract must not hardcode Backstage or any other vendor.

## Non-goals (v1)

- ADR/decision-registry context, agentic-docs context — same category
  contract should accommodate them later, but v1 ships catalog +
  dependencies only.
- Architecture-diagram sources (e.g. IcePanel) mentioned in the issue.
- CLI-tool-backed context sources — considered and explicitly deferred;
  the setup dialog only detects and suggests MCP servers.
- Multi-repo scanning or ranking hotspots across repos. This is single-repo
  scanning enriched with one fact about its neighbours, not a fleet-wide
  scan.

## Configuration & setup flow

A new skill, **`thunderstruck-context-config`**, matching the naming of
`thunderstruck-scan` / `thunderstruck-verify`:

- Runs an interactive dialog: lists MCP servers already connected in the
  environment as suggested candidates (no manual server-name typing unless
  none match), asks the user to pick the one that serves their service
  catalog, then asks which catalog entity this repo maps to.
- Persists the result to `.thunderstruck/context.yml`, committed to the
  repo (same treatment as the existing `.thunderstruck/profile.yml`):
  server reference and entity id only — never credentials or tokens.
- Re-runnable any time the mapping needs to change (server renamed,
  entity renamed, repo re-pointed at a different service).

**Trigger:** `thunderstruck-scan` auto-prompts this dialog on first run if
`.thunderstruck/context.yml` doesn't exist yet. Declining just proceeds
without architecture context, identical to today's behaviour. On later
scans, if the configured server or entity no longer resolves, the scan
prints a visible warning (same slot as the existing "lizard missing"
warning) pointing at `thunderstruck-context-config` to fix it — it does not
silently drop the context step.

## Fetch mechanism

A new agent, **`thunderstruck-context-fetcher`**, with a single narrow job:
given `.thunderstruck/context.yml`, call the configured MCP server's catalog
tools for the mapped entity and emit a fixed-schema JSON document listing its
dependency edges:

```json
{
  "entity": "checkout-service",
  "edges": [
    { "name": "payments-api", "type": "depends_on", "direction": "outbound" },
    { "name": "web-frontend", "type": "depended_on_by", "direction": "inbound" }
  ]
}
```

This is a deliberate, scoped exception to "no MCP tools in agents": its only
output is this fixed schema, and that output is mechanically re-validated
immediately afterward (see Evidence below) — the same way the investigator's
own findings are never trusted at face value. It carries no judgment calls
about findings, only a translation from whatever tool shape the org's MCP
server exposes into thunderstruck's fixed edge format.

Runs once per scan, before bundling, writing `.thunderstruck/context.json`.
Cached by content hash: if the fetched edge list is byte-identical to the
last run's, downstream bundles built from it don't change either, preserving
the existing bundle-caching guarantee (`test_bundles_are_within_budget_and_deterministic`
already covers bundle-side determinism; the fetcher's own output is what's
allowed to legitimately change between scans, exactly like git history does).

## Data flow into bundles

`context-fetcher` → `.thunderstruck/context.json` → `bundle.py` embeds the
edges relevant to a hotspot's file into that hotspot's bundle as a new
section, alongside the existing "related" section → the investigator can now
cite a specific edge when writing `blast_radius`.

## Evidence schema

A 4th evidence type, `catalog`, referencing one edge by
`catalog:<entity>-><dependency>`. `validate.py` resolves it by checking the
edge exists in `context.json`, exactly as a `detector` ref must match a hit
already present in `hotspots.json`. A `blast_radius` naming another service
without a matching `catalog` evidence ref is rejected the same way an
unresolvable `code` ref is today — this is what keeps the claim from being
just more unverified prose.

## Degradation

No context configured, entity unresolvable, or server unreachable at fetch
time → scan proceeds exactly as it does today: no `catalog` evidence type is
available that run, `blast_radius` stays prose-only, and a warning names the
reason (matches "Degradation is visible, never silent" in CLAUDE.md).

## Testing

- `context-fetcher` output validated against a fixture MCP server stub
  (no real Backstage dependency in tests).
- `validate.py` cases for the new `catalog` evidence type: valid edge,
  edge absent from `context.json`, edge naming the wrong repo/entity.
- Pipeline test: scan with no `.thunderstruck/context.yml` present
  degrades cleanly (matches today's behaviour, no crash, warning emitted
  only when a config exists but fails to resolve).
- `thunderstruck-context-config` dialog: manual/exploratory only for v1
  (interactive dialogs aren't a natural fit for the existing pytest suite);
  covered by the same "plugin manifest install" smoke check used for other
  interactive surfaces.

## Open questions for implementation planning

- Exact MCP tool-call shape thunderstruck's context-fetcher expects a
  catalog server to expose (tool name/args) — likely needs to tolerate
  variation across Backstage-MCP implementations rather than assuming one
  fixed tool signature.
- Whether `context.yml` needs a schema version field from day one, given
  `profile.yml` precedent.
