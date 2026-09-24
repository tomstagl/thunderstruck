# Source links in the report: design

**Requirements:** [#22](https://github.com/tomstagl/thunderstruck/issues/22). The problem, user stories, scope, acceptance criteria (AC-n) and success measures are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-24-source-links.md`

This document describes how the feature works. Examples use generic names (`git.example.com`, `acme/checkout`).

## 1. Architecture

```
signals.py    unchanged
bundle.py     unchanged    bundles stay byte-identical; checkpointing is untouched
investigator  unchanged    never writes or sees a URL
validate.py   unchanged    resolves refs exactly as today
report.py     + links      builds a LinkContext once, then wraps each resolved ref in a link
  links.py    NEW          pure functions: parse a remote, build a URL, encode a path
guardrail.py  unchanged    index.json has the same shape as before
```

Links are built only in `report.py`, and only after `validate.py` has resolved every ref. A URL is computed from three inputs: git config (the remote), the profile (`[links]`) and a ref that has already been resolved. It is never taken from model output or from repository text. If a finding JSON contains a `url` field, the report ignores it and overwrites it. This follows CLAUDE.md's governing rule: the model decides *which* line matters, and a script decides *how to point at it*.

`scripts/links.py` imports only the stdlib and has no side effects except `git` subprocess calls, which live in a single function (`link_context`). Everything else is a pure function, which keeps the unit tests table-driven and fast.

## 2. Configuration contract

`[links]` is an optional table in the repo's committed profile, `.thunderstruck.toml`. Without it, the defaults apply and a repo on github.com, gitlab.com or bitbucket.org gets links with no setup.

```toml
[links]
enabled  = true                       # false: plain refs as before, and no warning
remote   = "origin"                   # which git remote to read
provider = "gitlab"                   # github | gitlab | bitbucket; required for self-hosted hosts
base_url = "https://git.example.com/acme/checkout"   # overrides the web base derived from the remote

# Escape hatch for hosts whose URL scheme is none of the three (e.g. Bitbucket Data Center).
# When both templates are set, provider is ignored.
code_template   = "{base}/browse/{path}?at={sha}#{start}-{end}"
commit_template = "{base}/commits/{sha}"
```

Validation:

- An unknown `provider`, a `base_url` whose scheme is not `http`/`https`, or a template that uses a placeholder outside `{base} {sha} {path} {start} {end}` makes the report drop links entirely and print one warning naming the key. Nothing crashes, and there are no partial links.
- Only one of `code_template`/`commit_template` set → the same failure, handled the same way.
- Placeholders are substituted with literal `str.replace`, never `str.format`, so `{sha.__class__}` stays inert text and is rejected by the placeholder check.

## 3. Resolving the remote

`link_context(repo, profile, head)` returns `LinkContext | None` plus a list of warnings.

1. `enabled = false` → `None`, no warning.
2. Remote name: `[links] remote`, else `origin`. If `origin` does not exist and the repo has exactly one remote, that remote is used. Otherwise there is no remote.
3. `git remote get-url <name>` → `parse_remote(url)`.
4. `base_url` from the profile replaces the parsed base. When the base came only from the profile, no remote is needed.

`parse_remote` accepts:

| Form | Example | Web base |
|---|---|---|
| https / http | `https://user:tok@github.com/acme/checkout.git` | `https://github.com/acme/checkout` |
| scp-like | `git@gitlab.com:acme/platform/checkout.git` | `https://gitlab.com/acme/platform/checkout` |
| ssh URL | `ssh://git@git.example.com:2222/acme/checkout.git` | `https://git.example.com/acme/checkout` |
| git protocol | `git://git.example.com/acme/checkout` | `https://git.example.com/acme/checkout` |
| local path / `file://` | `/srv/git/checkout.git` | none |

Rules:

- **Userinfo is always dropped**: user, password and token alike. CI remotes routinely carry `x-access-token:…@`. It must never reach `report.md` or `report.json`.
- The ssh port is dropped, because it is not the web port. An https port is kept.
- A trailing `.git` and a trailing `/` are stripped. Nested groups (GitLab subgroups) are kept.
- The provider is auto-detected **only** from the exact hosts `github.com`, `gitlab.com` and `bitbucket.org`. Any other host needs `provider` (or the templates) and produces the warning *"references are not linked: host git.example.com is not recognised; set provider in [links]"*. We do not guess from substrings like `gitlab` in the host name: a wrong guess produces links that silently 404, which is the link equivalent of a false positive.

## 4. Building URLs

The SHA is always the full `repo.head` from `hotspots.json`, the commit that was scanned. It is never a branch name, so a link keeps pointing at the code the finding describes after the branch moves on.

| Provider | Code, range | Code, single line | Commit |
|---|---|---|---|
| github | `{base}/blob/{sha}/{path}#L{s}-L{e}` | `…#L{s}` | `{base}/commit/{sha}` |
| gitlab | `{base}/-/blob/{sha}/{path}#L{s}-{e}` | `…#L{s}` | `{base}/-/commit/{sha}` |
| bitbucket | `{base}/src/{sha}/{path}#lines-{s}:{e}` | `…#lines-{s}` | `{base}/commits/{sha}` |

Templates get `{end}` = `{start}` for a single line.

**Path encoding.** A leading `./` is stripped, and each `/`-separated segment is encoded with `urllib.parse.quote(seg, safe="")`. That encodes space, `#`, `?`, `(`, `)`, `[`, `]` and non-ASCII, so a file name cannot end the Markdown link early or smuggle in a fragment. For example, a file named `a](javascript:x).ts` becomes `a%5D%28javascript%3Ax%29.ts`.

**Commit refs.** The validator accepts short SHAs. The report expands each one with `git rev-parse --verify <ref>^{commit}` (local and deterministic) for the URL and shows the first 7 characters as link text. If it cannot be expanded (in practice, never after validation), the ref is shown unlinked.

## 5. What gets linked

| Ref | Rendered as | Links to |
|---|---|---|
| Finding location | [`src/client/releases.ts:16-28`](…) | file, line range |
| `code` evidence | [`src/client/releases.ts:16`](…) | file, line or range |
| `detector` evidence | [`S02@src/client/releases.ts:16`](…) | file, line |
| `commit` evidence | [`cab143e`](…) | commit page |
| `catalog` evidence | unchanged | none (not a location in this repo) |
| Hotspot table, clean and incomplete lists, index.json, guardrail | unchanged | out of scope (ticket) |

The link text keeps today's backticked ref, apart from the shortened commit SHA, so a report read as plain text still shows exactly what was cited.

## 6. Staleness: when a link would lie

`validate.py` checks line numbers against the **working tree**, but a permalink shows the file **at the scanned commit**. They differ when the scan runs on a dirty tree.

- **Changed or untracked cited file.** `git status --porcelain -z -- <every cited path>` runs once. A path that is modified, added, deleted, renamed or untracked is left **unlinked**, and one warning lists those paths: *"2 cited file(s) differ from the scanned commit abc1234 and are not linked: src/a.ts, src/b.ts"*. A link that lands on the wrong line is worse than no link. The report already prints the file:line in plain text, so nothing is lost.
- **Scanned commit not pushed.** If `git branch -r --contains <head>` finds no ref under `refs/remotes/<remote>/`, links are still emitted (they start working once the commit is pushed), and the report warns: *"the scanned commit abc1234 is on no branch of origin known locally; links resolve once it is pushed"*. This check is offline: it reads remote-tracking refs and never contacts the host. A shallow CI checkout without remote-tracking refs gets the same warning, which is accurate: we cannot tell.

## 7. Output contracts

**report.md.** Links as in §5. Link warnings are added to *Run warnings* after the scan and context warnings.

**report.json.** The changes are additive only, so the schema stays `thunderstruck.report/v1`:

```json
"links": {"provider": "github", "base_url": "https://github.com/acme/checkout",
          "sha": "<40 hex>", "remote": "origin"},
"findings": [{"location": {"file": "…", "lines": "16-28", "url": "https://…"},
              "evidence": [{"type": "code", "ref": "…", "url": "https://…"},
                           {"type": "catalog", "ref": "…", "url": null}]}]
```

`links` is `null` when linking is disabled or impossible, and then `url` is `null` everywhere. Link warnings are appended to the top-level `warnings` list, the same list the Markdown prints. `url` is added to copies of the finding dicts. `.thunderstruck/findings/*.json` is never rewritten.

**index.json and guardrail.** Unchanged. The guardrail's constraints (stdlib, <100ms, statements of fact) make it the wrong place for a feature the user can already get with one click in the report.

## 8. Security

- No credentials in output (§3). A test asserts that a token-bearing remote produces no `@`, token substring or username anywhere in `report.md` or `report.json`.
- Only `http`/`https` URLs are emitted. The profile's `base_url` scheme is checked, and the parsed remote is always rewritten to `https` (or kept `http` when the remote was `http`).
- Path encoding (§4) prevents Markdown or link injection through file names. Finding text (failure mode, notes) is not linked or re-encoded by this feature. Its handling is unchanged.
- No network access at any point.
- The report now names the remote's web base. It already names the repo and branch, and it stays in the gitignored `.thunderstruck/` directory.

## 9. Degradation

| Situation | Refs | Warning |
|---|---|---|
| `enabled = false` | plain | none |
| no remote, no `base_url` | plain | "references are not linked: no git remote 'origin'; set [links] in .thunderstruck.toml" |
| unrecognised host, no `provider` | plain | names the host and the key to set |
| invalid `[links]` config | plain | names the key |
| cited file dirty or untracked | that file plain | lists the files |
| scanned commit not on a remote-tracking branch | linked | "links resolve once it is pushed" |
| `git` call fails | plain | "references are not linked: <reason>" |

`report.py` never exits non-zero because of linking.

## 10. Test strategy

- **`tests/test_links.py`** (unit, table-driven): every row of the §3 table; userinfo and token removal; ssh port removal; `.git` and slash stripping; GitLab subgroups; unknown host → no provider; URL shapes for each provider, range and single line; path encoding (space, `#`, parentheses, brackets, unicode, `./` prefix); template substitution, unknown placeholder rejected, `{sha.__class__}` rejected; non-http `base_url` rejected.
- **`tests/test_pipeline.py`** (fixture): with a github.com remote and a matching remote-tracking ref, the rendered report contains a link for the location and for each code, commit and detector ref, and `report.json` carries `url`s. A dirty cited file is unlinked and named. No remote → plain refs plus the warning. `enabled = false` → no warning. `index.json` has no `url` key. A token-bearing remote leaks nothing.
- **Determinism**: `test_bundles_are_within_budget_and_deterministic` is unchanged and must still pass. The bundler is not touched.
- **Sample report**: `gen_sample_report.py` gives the fixture a remote on a reserved placeholder host and a remote-tracking ref (§11). The regenerated sample shows links, and `--check` guards it.

## 11. Decisions

| Decision | Rationale |
|---|---|
| Web permalinks only, no relative or editor links | The user's choice. `.thunderstruck/` is gitignored, so relative links would not render on a host anyway, and `vscode://` URIs need absolute paths that make reports unshareable. |
| Pin to the scanned SHA, never the branch | A finding describes one version of the code. Branch links drift as soon as someone edits the file. |
| Build links in `report.py`, not in `signals.py` | This is presentation. Keeping it out of the scan and the bundles guarantees that checkpointing and bundle determinism cannot be affected. `report.py` already reads the repo. |
| Exact-host auto-detection only | A guessed provider produces confident, broken links. |
| Leave dirty files unlinked; still link an unpushed commit | A dirty file's link shows the wrong lines permanently. An unpushed commit's link becomes correct once it is pushed. |
| Additive `report.json` fields, no schema bump | Existing consumers keep working. The `v1` contract only ever gains optional keys. |
| Sample report uses `https://github.example.com/acme/fixture` with `provider = "github"` | `example.com` is reserved (RFC 2606), so the links cannot point at someone's real repository. It also exercises the self-hosted path through the profile. The cost is that the sample's links do not resolve. The generated header says so. |

## 12. Open design questions

- Should a later version also link the ranked-hotspot table and the clean and incomplete lists? The ticket keeps them out of scope. The same `LinkContext` would cover them with no design change.
- Bitbucket Data Center and Gitea/Forgejo are covered only through templates. If they turn out to be common, they could become first-class providers.
