# Source links in the report — design

**Requirements:** [#22](https://github.com/tomstagl/thunderstruck/issues/22). The problem, user stories, scope, acceptance criteria (AC-n) and success measures are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-09-24-source-links.md`

This document describes how the feature works. Examples use generic names (`git.example.com`, `acme/checkout`).

## 1. Architecture

```
signals.py    unchanged
bundle.py     unchanged    bundles stay byte-identical; checkpointing is untouched
investigator  unchanged    never writes or sees a URL
validate.py   refactor     path normalisation moves to _common.ref_path (no behaviour change)
report.py     + links      one link_context() call after collect(), then wraps refs
  links.py    NEW          remote parsing, URL building, and the only git calls for linking
guardrail.py  unchanged    index.json keeps its shape
```

Links are built only in `report.py`, and only for refs that `validate.py` resolved: every `code`, `detector` and `commit` ref, and every `location.file`. A URL comes from three inputs only: git (the remote, the scanned tree, commit ids), the profile (`[links]`) and the resolved ref. It is never taken from model output or from repository text. If a finding JSON carries a `url` field, it is overwritten. This follows CLAUDE.md's governing rule: the model decides *which* line matters, and a script decides *how to point at it*.

**The location line range is not validated.** `validate.py` checks that `location.file` exists but treats `location.lines` as free text. The link code therefore parses `lines` itself, strictly (§5), and falls back to a file-level link when the value does not parse. `validate.py` is not tightened in this feature. Rejecting findings that are valid today would change the finding contract. That belongs in its own ticket (§12).

`scripts/links.py` is stdlib-only. Every git call made for linking lives in `link_context()`. All other functions are pure.

## 2. Configuration contract

`[links]` is an optional table in the repo's committed profile, `.thunderstruck.toml`. Without it, a repo whose remote is on github.com, gitlab.com or bitbucket.org is linked with no setup.

```toml
[links]
enabled  = true                  # false: plain refs as before, and no warning
remote   = "upstream"            # default: "origin", else the repo's only remote
provider = "gitlab"              # github | gitlab | bitbucket
base_url = "https://git.example.com/acme/checkout"   # web base; replaces the one derived from the remote

# For hosts with another URL scheme (e.g. Bitbucket Data Center). Both or neither.
# When set, provider is ignored.
code_template   = "{base}/browse/{path}?at={sha}#{start}-{end}"
commit_template = "{base}/commits/{sha}"
```

Validation (`config_from_profile`). Any failure disables linking and produces exactly one warning, which names the key:

- `enabled` is not a bool, or `remote`, `provider`, `base_url` or a template is not a string.
- `provider` is not one of the three.
- `base_url` has a scheme other than `http`/`https`, has no host, or contains `{`, `}` or whitespace.
- Only one of the two templates is set.
- A template uses a placeholder other than `{base} {sha} {path} {start} {end}`.

A profile that fails to load (bad TOML) produces the warning *"references are not linked: .thunderstruck.toml could not be read"*. The report is still rendered.

## 3. Resolving the web base and provider

1. `enabled = false` → no links, no warning.
2. **Remote name.** If `remote` is set, that remote must exist. If it does not, the warning is *"remote 'x' named in [links] does not exist"*: linking continues when `base_url` is set, and stops otherwise. If `remote` is unset, use `origin`, else the only remote when there is exactly one, else none.
3. **Base.** `base_url` from the profile, else `parse_remote(git remote get-url <name>)`. If neither yields a base, the warning is *"references are not linked: no git remote to link to; set remote or base_url in [links]"*.
4. **Provider.** The templates, else `provider`, else auto-detection from the **exact** hosts `github.com`, `gitlab.com` and `bitbucket.org`. If no provider is found, the warning is *"references are not linked: host H is not recognised; set provider (and base_url if H is an SSH alias) in [links]"*. We do not guess from substrings in the host name: a wrong guess produces links that silently 404.

`parse_remote` accepts:

| Form | Example | Web base |
|---|---|---|
| https / http | `https://user:tok@github.com/acme/checkout.git` | `https://github.com/acme/checkout` |
| scp-like | `git@gitlab.com:acme/platform/checkout.git` | `https://gitlab.com/acme/platform/checkout` |
| ssh URL | `ssh://git@git.example.com:2222/acme/checkout.git` | `https://git.example.com/acme/checkout` |
| git protocol | `git://git.example.com/acme/checkout` | `https://git.example.com/acme/checkout` |
| local path, `file://`, empty path, invalid port | `/srv/git/checkout.git` | none |

Rules:

- **Userinfo is always dropped**, whether user, password or token. CI remotes routinely carry `x-access-token:…@`.
- The ssh port is dropped, because it is not the web port. An https or http port is kept.
- A trailing `.git` and any trailing `/` are stripped. GitLab subgroups are kept.
- A base containing `{`, `}` or whitespace is rejected, so it can never feed template substitution.
- An SSH host alias from `~/.ssh/config` (`git@github-work:acme/x`) parses to host `github-work`. That is not an exact host, so the warning asks for `provider` and `base_url`.

## 4. Building URLs

The SHA is always the full `repo.head` from `hotspots.json`, the commit that was scanned. It is never a branch name.

| Provider | Code, range | Code, single line | Code, whole file | Commit |
|---|---|---|---|---|
| github | `{base}/blob/{sha}/{path}#L{s}-L{e}` | `…#L{s}` | `{base}/blob/{sha}/{path}` | `{base}/commit/{sha}` |
| gitlab | `{base}/-/blob/{sha}/{path}#L{s}-{e}` | `…#L{s}` | `{base}/-/blob/{sha}/{path}` | `{base}/-/commit/{sha}` |
| bitbucket | `{base}/src/{sha}/{path}#lines-{s}:{e}` | `…#lines-{s}` | `{base}/src/{sha}/{path}` | `{base}/commits/{sha}` |

- **Rendered files.** GitHub and GitLab render Markdown-like files and ignore line anchors on them. For those two providers, a code link to a path ending in `.md .markdown .mdown .mkd .rst .adoc .asciidoc .org .textile .rdoc .ipynb` gets `?plain=1` before the `#` fragment.
- **Templates.** With a single line, `{end}` = `{start}`. For a whole-file link, the template is cut at its first `#` and `{start}`/`{end}` are removed. If a placeholder remains in the part before the `#`, no file-level link is emitted.
- **Substitution** is a single `re.sub` pass over the template with a fixed mapping, so a value can never be re-expanded. Never `str.format`.
- **Paths.** The path is first normalised with `_common.ref_path`, the same rule the validator applies (`str(path).lstrip("./")`), so the path that is linked is the path that was resolved. Each `/`-separated segment is then encoded with `urllib.parse.quote(seg, safe="")`. That encodes space, `#`, `?`, `%`, `(`, `)`, `[`, `]` and non-ASCII, so a file name cannot end the Markdown link or add a fragment.

## 5. What gets linked, and how refs are read

| Ref | Parsed with | Rendered | Links to |
|---|---|---|---|
| Finding location | `location.file` + `location.lines` (below) | [`file:lines`](…) | file + range, or whole file |
| `code` evidence | `validate.CODE_REF` | [`file:16-28`](…) | file + range |
| `detector` evidence | `validate.DETECTOR_REF` | [`S02@file:16`](…) | file + line |
| `commit` evidence | first whitespace-separated token, as `validate.py` does | [`cab143e`](…) followed by the rest of the ref in backticks, when there is any | commit page |
| `catalog` evidence | — | unchanged | none |

**`location.lines`.** An int, or a string matching `^\s*(\d+)(?:\s*-\s*(\d+))?\s*$`, with `1 ≤ start ≤ end ≤` the number of lines in the file on disk. The file is unchanged since the scanned commit (§6), so that count is the count at the scanned commit. Anything else, such as `"L16"`, an en dash, a list, or a range past the end of the file, gives a whole-file link. The displayed text stays exactly as the model wrote it.

A ref that fails to parse is shown exactly as today, unlinked. The hotspot table, the clean and incomplete lists, `index.json` and the guardrail are out of scope (see the ticket).

## 6. Links must never show other lines

`validate.py` checks refs against the **working tree**. A permalink shows the **scanned commit**. `link_context` receives every cited path and leaves a path unlinked in any of these cases:

| Check | Command | Why |
|---|---|---|
| Path absent at the scanned commit, or a symlink (`120000`), or a submodule (`160000`) | `git --literal-pathspecs ls-tree -z --full-tree <sha> -- <paths>` | The file is untracked, ignored, new or deleted. For a symlink or submodule, the host page is not the file that was read. |
| Working tree or index differs from the scanned commit | `git --literal-pathspecs diff --name-only -z <sha> -- <paths>` | Covers edits, staged changes, **and commits made after the scan**. The check compares against the scanned SHA, not the current HEAD. |

`--literal-pathspecs` stops paths like `src/[id].ts` from being read as globs. Paths are sorted and deduplicated first, so the warning text is deterministic: *"2 cited file(s) differ from the scanned commit abc1234 or are not in it, and are not linked: src/a.ts, src/b.ts"*.

**Push state.** Links pinned to a commit the host does not have will 404 until it is pushed. For the scanned SHA and every cited commit, `git branch -r --contains <sha> --format=%(refname)` must list a ref under `refs/remotes/<remote>/`. This check is offline: it reads remote-tracking refs and never contacts the host. Commits that fail the check are still linked, because the links start working once the commits are pushed. The warning is *"3 linked commit(s) are on no branch of origin known locally (abc1234, …; normal in a detached or shallow CI checkout); their links resolve once pushed"*. The check is skipped when the base came from `base_url` with no remote, because there is nothing to check against.

**Commit ids.** Cited commit tokens are expanded with `git rev-parse --verify <token>^{commit}` inside `link_context`, which returns a token→full-SHA map. A token that does not expand is left unlinked.

**Failure handling.** Every git call uses a 30-second timeout. `ThunderstruckError`, `subprocess.TimeoutExpired` and `OSError` all end in *"references are not linked: <reason>"* with no links at all. `report.py` also wraps the whole linking step, so an unexpected exception degrades to that warning and never fails the report.

## 7. Output contracts

**report.md.** Links as described in §5. Link warnings are printed in *Run warnings* after the scan and context warnings.

**report.json.** The changes are additive, and the schema stays `thunderstruck.report/v1`:

```json
"links": {"provider": "github", "base_url": "https://github.com/acme/checkout",
          "sha": "<40 hex>", "remote": "origin"},
"warnings": ["…scan warnings…", "…link warnings…"],
"findings": [{"location": {"file": "…", "lines": "16-28", "url": "https://…"},
              "evidence": [{"type": "code", "ref": "…", "url": "https://…"},
                           {"type": "catalog", "ref": "…", "url": null}]}]
```

`links` is `null` when linking is off or impossible, and then every `url` is `null`. `provider` is `null` when templates are used. `remote` is `null` when only `base_url` was used. Top-level `warnings` is the scan warnings followed by the link warnings. Context warnings stay out of `report.json`, as they are today. URLs are computed once, in `collect()`, on deep copies of the findings. Both renderers read the same values, and `.thunderstruck/findings/*.json` is never written.

**index.json and guardrail.** Unchanged.

## 8. Security

- No credentials in output (§3). A test runs with a token-bearing remote and checks that `report.md` and `report.json` contain neither the token nor the username.
- Only `http`/`https` URLs are emitted, whether they come from the remote or from `base_url`.
- Templates are substituted in a single pass. A base containing braces is rejected, and unknown placeholders are rejected (§2, §4).
- Path encoding (§4) prevents Markdown and link injection through file names. Finding prose is not touched by this feature.
- No network access.
- The report now names the remote's web base. The README's *Privacy* section says so.

## 9. Degradation

| Situation | Refs | Warning |
|---|---|---|
| `enabled = false` | plain | none |
| profile unreadable, or `[links]` invalid | plain | names the file or key |
| named remote missing, no `base_url` | plain | names the remote |
| no remote and no `base_url` | plain | asks for `remote` or `base_url` |
| host not recognised (incl. SSH alias) | plain | names the host, `provider` and `base_url` |
| git call fails or times out | plain | reason |
| cited file changed, absent, symlink or submodule | that file plain | lists the files |
| `location.lines` unreadable or out of range | whole-file link | none (the text shows what was cited) |
| scanned or cited commit not on a remote-tracking ref | linked | lists the commits |

## 10. Test strategy

- **`tests/test_links.py`** (unit, table-driven, no git):
  - every row of the §3 table, plus invalid ports and empty paths;
  - userinfo and token removal, ssh port removal, subgroups, braces rejected;
  - exact-host provider detection;
  - URL shapes per provider: range, single line, whole file, and `?plain=1` on `.md`;
  - template substitution: single pass, whole-file cut at `#`;
  - path normalisation and encoding (`./`, `../`, space, `#`, `%`, brackets, unicode);
  - `location.lines` parsing: int, `"16"`, `"16-28"`, `" 16 - 28 "`, `"L16"`, en dash, reversed and out-of-range values;
  - every `config_from_profile` failure.
- **`tests/test_links.py`** (git, `tmp_path` repos), for `link_context`:
  - remote selection: origin, sole remote, explicitly named remote, missing named remote, `base_url` only;
  - an unrecognised host;
  - a modified file, a staged file, a file committed after the scan, an untracked file, an ignored file, a symlink and a `[id]` path;
  - commit expansion, including a token that does not expand;
  - push state, for the scanned SHA and for an unpushed cited commit;
  - a git failure.
- **`tests/test_pipeline.py`** (fixture, derived from `scanned_copy` / `context_scanned_copy`):
  - every ref type is linked;
  - a commit ref with a subject keeps its subject;
  - catalog refs stay plain;
  - no remote gives plain refs and a warning;
  - `enabled = false` is silent;
  - a malformed `location.lines` gives a whole-file link;
  - a token-bearing remote leaks nothing;
  - a finding-supplied `url` is overwritten;
  - `report.json` URLs and `links`;
  - `index.json` has no `url`;
  - the findings files are byte-identical after `report.py`.
- **Determinism:** `test_bundles_are_within_budget_and_deterministic` is unchanged and must pass.
- **Sample report:** a new shape test checks that every `_code_`, `_detector_` and `_commit_` evidence line and every finding location in `examples/sample-report.md` is a link. This is *not* a freshness check. `gen_sample_report.py --check` only tests that the file exists (see §12).

## 11. Decisions

| Decision | Rationale |
|---|---|
| Web permalinks only | The user chose this. `.thunderstruck/` is gitignored, and `vscode://` URIs need absolute paths that make reports unshareable. |
| Pin links to the scanned SHA; check staleness against that SHA, not HEAD | A finding describes one version of the code. A scan spans minutes, and the user may commit in between. |
| Build links in `report.py`; all linking git calls in `link_context` | Presentation only, so checkpointing and bundles cannot be affected. It is also one place to test and to time out. |
| Parse `location.lines` in the link code; do not tighten `validate.py` | Tightening would reject findings that are valid today, which is a contract change for another ticket. A whole-file link is never wrong. |
| Exact-host auto-detection only | A guessed provider produces confident, broken links. |
| A changed or absent file gets no link; an unpushed commit still gets a link | The first would show the wrong lines permanently. The second becomes correct once the commit is pushed. |
| `?plain=1` on rendered file types (GitHub and GitLab) | Otherwise the anchor is ignored and the reader lands at the top of the rendered page. |
| Additive `report.json` fields, no schema bump | Existing consumers keep working. |
| The sample report uses `https://github.example.com/acme/fixture` with `provider = "github"` | `example.com` is reserved (RFC 2606), so a sample link can never point at a real repository. It also exercises the self-hosted path. The generated header says the links do not resolve. |
| Shallow CI checkouts get the push warning | We cannot tell offline. The wording names that case so it reads as expected. |

## 12. Open design questions and follow-ups

- **`validate.py` should check `location.lines`**: format, and bounds against the file. This is a separate ticket, because it changes which findings pass.
- **`_common.ref_path`'s `lstrip("./")` also strips the leading dot of dotfiles** (`.github/x.yml` → `github/x.yml`). That is a pre-existing validator bug, and this feature deliberately matches the validator. A fix belongs with the ticket above.
- **`gen_sample_report.py --check` does not compare content, and CI does not run it**, even though CLAUDE.md says both generated files are checked. Making it a real check needs the scan date in the report to be pinned or normalised. This is a separate ticket.
- Linking the hotspot table and the clean and incomplete lists would reuse the same `LinkContext` (ticket, open question).
- Bitbucket Data Center, Gitea and Forgejo are covered only through templates.
