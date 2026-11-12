# Fix and review guidance: design

**Requirements:** [#107](https://github.com/tomstagl/thunderstruck/issues/107), part of [#104](https://github.com/tomstagl/thunderstruck/issues/104). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-12-fix-and-review-guidance.md`.
**Evidence:** an install of a checkout at 0.13.0 into an empty home directory (§2); `tests/test_plugin_paths.py`; `.claude/skills/implement-ticket/SKILL.md`. Every other claim cites file:line. The source PRD's R-40 to R-42 are context only.

This ticket writes no guidance. The two documents are the maintainer's: committed before the build, checked and linked here, never edited. What it designs is where they live, how the README reaches them, and the checks that keep them neutral, complete and in place. The documents were not available while this was written; §6 says how the checks are run on them once before the ticket loses `DRAFT`.

## 1. Architecture

```
maintainer  writes   docs/fix-agent-instructions.md              the documents (§2)
                     docs/review-briefs.md
tests/guidance/neutrality.yaml   rules + samples    what neither document may name (§3)
tests/guidance/behaviours.yaml   pinned quotes      what each must state           (§4)
tests/guidance_check.py          reads a document, the rules and the quotes; prints the table
tests/test_fix_guidance.py       proves the checker on samples; applies it to the documents;
                                 checks the README links, the paths, and that a scan ignores them
README.md   links both documents by their published paths                          (§2)
------------------------ nothing below reads the documents ---------------------------
signals.py · bundle.py · … · report.py                                  unchanged  (§5)
```

The governing rule holds in one place. At build time the agent reads the documents once and chooses a quote per behaviour, which is a reading task. From then on the suite is deterministic and no model decides anything.

What reaches plugin users: the two documents and one README section. The checker is development code under `tests/`, not `scripts/`: nothing a scan or a ticket runs needs it.

## 2. Where the documents live (AC-5)

**Published paths:** `docs/fix-agent-instructions.md` and `docs/review-briefs.md`, the source PRD's filenames at the root of `docs/`. `PUBLISHED` in `tests/guidance_check.py` holds them, and a test pins both.

**What ships.** `marketplace.json` has `"source": "./"` (`.claude-plugin/marketplace.json:11`) and the README says the installed copy holds everything the plugin needs (`README.md:47-48`). The install experiment: `claude plugin marketplace add` and `install` of a checkout into an empty home produced `cache/thunderstruck/thunderstruck/0.13.0/` holding the whole tree, `docs/` included, and `claude plugin list --json` named that folder as `installPath` (proved). A GitHub install, as opposed to a local-directory one, was not run; it uses the same marketplace entry (inferred).

**What is stable.** The installed folder is named for the version, so an absolute plugin path changes with every update (proved by the same install; `tests/test_plugin_paths.py:95` models an installed copy as a versioned folder). Nothing may store one. Three forms do hold:

| Form | Used by | Why it holds |
|---|---|---|
| `docs/<name>.md`, relative to the repository and plugin root | this spec, the tests | the same in a checkout, on GitHub and in an installed copy; a test pins it |
| a relative Markdown link to that path | the README | resolves in all three; GitHub and the link test catch a rename |
| `<repository>/blob/main/docs/<name>.md`, `repository` read from `plugin.json` | a ticket in another repository (#108) | a public URL that moves only with the path |

**Why `docs/` and not `skills/<x>/references/`.** A file under `skills/` is plugin content for the plugin's own agents: `tests/test_plugin_paths.py:24-27` scans `skills/**/*.md` and would require any plugin path in it to carry `${CLAUDE_PLUGIN_ROOT}`, the opposite of AC-3. A reader in another environment looks in `docs/`, not in a skill's folder. And a skill is a harness concept these documents must not lean on. `docs/` today holds maintainer material only (specs, plans, calibration); these are its first user-facing files. No subfolder: it buys nothing, and the filenames are the maintainer's.

**README.** A section `## From a finding to a reviewed fix`, placed before `## The catalog`, links both documents by relative path. It says only what the ticket's AC-1 and AC-2 say and paraphrases neither document. #108 may extend the section; it keeps the heading, which the README test finds.

**Other names or places.** If a document is on `main` under another path or filename, Task 0 stops (§6). Moving the file and changing the published path (here, in the plan and in #108) are both reasonable, and the second changes what a later ticket links, so a human decides. It is not an amendment PR, which is for plan or spec wording that has one clear fix, and not a move.

## 3. Harness neutrality (AC-3)

The check forbids things by *form*, never by plain word. "Tool", "agent", "plugin", "hook" and "skill" are ordinary words, and `Read`, `Write` and `Edit` are ordinary verbs. A neutral document may say "do not rely on any plugin, hook or tool your environment may not have", and may begin a sentence "Read the callers". A word list would flag both, and a false positive on a legitimate sentence is the worse bug (CLAUDE.md, the negative-control discipline).

| Rule | Forbids | Still passes |
|---|---|---|
| N01 | a harness variable: `CLAUDE_` and capitals (`${CLAUDE_PLUGIN_ROOT}`) | `API_TIMEOUT` |
| N02 | a harness instruction file or plugin directory: `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `copilot-instructions.md`, `.cursorrules`, `.claude/`, `.claude-plugin/`, `.thunderstruck/`, `.thunderstruck.toml` | `README.md`, `CONTRIBUTING.md`, the word "thunderstruck" |
| N03 | `mcp__…`, `MCP`, `Model Context Protocol` | `McpClient` |
| N04 | a hook event: `PreToolUse`, `PostToolUse`, `SubagentStop`, `SessionStart`, `UserPromptSubmit` | "pre-commit hooks" |
| N05 | a compound tool name: `TodoWrite`, `WebFetch`, `WebSearch`, `NotebookEdit`, `MultiEdit`, `SendMessage`, `ToolSearch`, `AskUserQuestion`, `ExitPlanMode`, `EnterPlanMode`, `BashOutput`, `KillShell` | "web search", "todo list" |
| N06 | a single-word tool name used as a name: "the Read tool", "your `Bash` tool" (Read, Write, Edit, Bash, Grep, Glob, Task, Agent, Skill, then "tool", after the, a, an, this, that, your or a backtick) | "Read tool output before …", "Edit the test", "the task of the fixer" |
| N07 | a coding assistant's name: Claude Code, Claude, GitHub Copilot, Copilot, Codex, Aider, Windsurf, Gemini CLI | "your team's coding assistant" |
| N08 | a harness feature: subagent, sub-agent, slash command, plan mode, agent team, permission mode | "a separate session, by a person or an agent", "the last slash" |
| N09 | the built-in commands `/plugin` and `/compact` | `GET /health`, `/etc/hosts`, `docs/plugin.md`, `/plugins` |
| N20 | a skill or agent name read from the tree (`thunderstruck-scan`, `thunderstruck-skeptic`, `stability-catalog`, `implement-ticket`, …), alone or as `/name` | "a scan of the repository", "stability catalog" |
| N21 | a file the plugin ships, as `<plugin dir>/…/<name>` or, for a name that is not also an ordinary one, alone in a code span: names read from `scripts/`, `catalog/`, `hooks/`, `templates/`, `examples/`, `agents/`, `skills/`, `.claude/`, `.claude-plugin/` | `src/report.py`, `scripts/deploy.sh`, `README.md`, `report.md`, `report.json`, `validate.py` alone |

Against AC-3: tool names are N04 to N06, plugin paths N01, N02, N21, scripts N21, skill names and slash commands N20, N09 and N08, harness features N02, N03, N04, N08. A document that opens with a front-matter block fails too: it is a skill or agent file, not a plain document.

N09 lists two commands. `/agents`, `/hooks` and `/model` can be a service's own route, and a miss costs less than a false hit.

**Derived rules.** N20 and N21 are built when the tests import the checker: N20 from `skills/*`, `.claude/skills/*` and `agents/*.md`; N21 from every file under the plugin's directories, minus `generic_files` (`README.md`, `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `__init__.py`). A new script is forbidden in the documents from the day it exists, with no list to update. Two limits keep ordinary words free. `bare_ok` lists plugin files that are also ordinary names (`validate.py`, `verify.py`, `report.py`, `context.py`, `links.py`, `usage.py`, `deps.py`, `bundle.py`, `modules.py`, `report.html`): alone in a code span they pass, because a document about another repository may name one, but after a plugin directory (`scripts/validate.py`) they are still forbidden. And a scan's own output names (`report.md`, `report.json`, `index.json`, `hotspots.json`, `context.json`) are not plugin paths: a review brief may tell a reviewer to write `report.md`, and the one path that would name the plugin's output, `.thunderstruck/`, is caught by N02. A new script whose name a document legitimately puts in a code span fails the suite; the remedy is to add it to `bare_ok` with a negative sample, a human edit of the YAML.

**Matching unit.** A Markdown block with its wrapped lines joined, so "the Read↵tool" is found. Fenced code is matched line by line. Headings count.

**The check is tested like a detector.** Every rule in `tests/guidance/neutrality.yaml` has a positive and a negative sample. A positive sample trips its own rule. A negative sample trips *no* rule, so a rule cannot grow over another's legitimate text. A `legitimate` list holds sentences a neutral document may contain, starting with the ticket's own behaviours worded plainly. Derived rules take their positive samples from the tree and their negatives from the YAML. There is no inline waiver: a marker inside a document is how a violation would hide. To allow a phrase, narrow the rule and add a negative sample, as a change to this section.

**What it does not catch**, stated so nobody assumes it does: a tool name used as a bare verb ("Use Grep to find callers"); a plugin file named in prose outside a code span; a harness or tool no rule lists; a route such as `/agents`. Reading the table (§4) and the document in review covers these; extending the check is data plus a sample.

## 4. The behaviours each document must state (AC-1, AC-2, AC-4)

The checker cannot know the maintainer's wording. The building agent reads the documents once and pins, for each behaviour, the whole sentence of the document that states it (AC-1 and AC-2 have the PR show that sentence); the suite then holds the sentence in place and the PR shows the table.

**Rows.** `REQUIRED` in `tests/guidance_check.py` holds 27 ids, each with its document, its kind (`prose` or `heading`) and the behaviour in the ticket's words. The wording is the ticket's, never the documents'.

| Rows | Behaviour |
|---|---|
| `fix-01` to `fix-11b` (15 rows: behaviours 3, 8 and 11 have clauses) | AC-1's eleven behaviours, in the ticket's order |
| `fix-inputs-heading`, `fix-inputs-missing`, `review-inputs-heading`, `review-inputs-missing` | AC-4 |
| `review-lens-1` to `review-lens-4` (headings), `review-report-format-heading`, `review-report-format-shared`, `review-read-only`, `review-no-implementer-conclusions` | AC-2 |

**Data.** `tests/guidance/behaviours.yaml` is `rows: [{id, quote}, …]`, one per id and no other; an unknown or repeated id fails. Document and kind come from `REQUIRED`, so a row carries only what the agent produces.

**Quote rules.** A *prose* row's quote is the whole sentence, in the document's own punctuation, with no length limit. A sentence runs from the block's start, or from the first character after the previous sentence's final `.`, `!` or `?` (with any closing `)`, `"`, `'`, `*`, `_`, backtick or `]`) and its space, to its own final `.`, `!` or `?` with its closing marks, or to the block's end. A list item or table cell with no sentence end is quoted whole, without its list marker or `|`. The quote is copied character for character (case, punctuation, markup, non-ASCII), lies inside one paragraph, list item or table row, and reads a wrapped line as a single space. A one-word sentence ("Never push.") is a sentence. If the sentence occurs more than once and its first occurrence is followed by another sentence in its block, the quote is extended with that next sentence, and so on; if the first occurrence is the last sentence of its block, or a whole item or cell, it is kept and the row is satisfied by its first occurrence, because extension cannot separate two identical list items. The check enforces the boundaries mechanically: a quote that starts or ends inside a sentence is refused. A *heading* row's quote is the heading text without its `#` marks, and exactly one heading reads it. One passage may serve several rows. Which passage states a behaviour is a reading judgement, bounded by one rule: it must tell the reader to do, or not to do, the thing, and not merely mention it; if several do, the first in the document. The plan's Task 4 repeats these as steps, so two agents produce the same table except where that one judgement differs.

**What the suite checks.**

- **Rows** (`row_problems`): each quote follows the rules above, and a quote found only in a heading, in code or inside a longer sentence is refused with that reason.
- **Inputs first** (`inputs_problems`, AC-4): the first heading after the title (a level-1 heading) is the inputs heading, and the sentence about a missing input lies inside its section (up to the next heading of the same or a higher level). Prose or a contents list before that heading is allowed: AC-4 asks that the first *section* be the inputs, and a preamble is not a section.
- **Briefs** (`lens_problems`, AC-2): each lens heading and the report-format heading has at least 20 words under it, and the four lens rows pin four different headings.
- **Links** (`link_problems`): each relative link or image in a document resolves from its folder. URLs and anchors are not checked.

**What it does not check** is that the pinned text *states* the behaviour. A quote can be the right words in the wrong meaning. That is the reviewer's, with `python tests/guidance_check.py --table`: one row per behaviour with the ticket's wording, the pinned text in a code span, for a heading row the first sentence under that heading (the sentence the PR shows for each lens), and the starting line. Task 4 prints it for the PR body.

**A behaviour not found** means the document has a gap. The agent stops as `agent:blocked`, names the row and the behaviour and the headings it read, and edits nothing. The maintainer adds the passage, or the ticket's AC changes first.

**A later change.** Dropping or rewording a pinned text fails `test_every_pinned_text_is_a_whole_sentence_of_its_document` with the row, the text and the remedy: update the quote in the same PR and show the table. Adding a harness name fails the neutrality test. An edit elsewhere fails nothing, because no content hash is pinned: a typo fix needs no ceremony. The cost is that an unrelated weakening of a behaviour is not detected; review covers it.

**Teeth.** The real-document tests pass on their first run when the documents are good, so they carry in-suite mutation tests: a violation appended to the real text must be caught by every rule, and for each row the block its text sits in is taken out of the real text *by line* (every such block for a prose row, the heading line for a heading row) and the row must fail. Deleting by line matters: a lens name that also appears in an intro paragraph would otherwise be removed there and leave its heading standing.

## 5. Staying out of the pipeline (AC-6)

No file under `scripts/`, `hooks/`, `agents/`, `skills/`, `catalog/`, `templates/` or `examples/` changes. The README gains a section, `CLAUDE.md` a rule, `CHANGELOG.md` an entry, and the versions bump. Three checks:

- **A scan ignores the documents.** `test_a_scan_writes_the_same_bundles_with_and_without_the_documents` ranks and bundles the fixture twice, once with a plugin tree holding only `scripts/` and `catalog/` and once with the real tree, and compares the bytes of every Markdown file the scan wrote (the bundles and the catalog brief). Proved to have teeth: a script appending a document's text to `catalog-brief.md` makes it fail. Not covered: a script after bundling (`report.py`, `report_html.py`, the hooks) that read a document and used it only in a message. Their output is covered by the sample check below and the scope check.
- **No generated file changes.** `gen_catalog_docs.py --check` and `gen_sample_report.py --check` pass unchanged; the sample is built by the real pipeline, so unchanged bytes are the confirmation.
- **Scope.** Task 7 lists the changed paths against `origin/main` and prints `UNEXPECTED` for any outside the README, `CLAUDE.md`, `CHANGELOG.md`, the manifests, `pyproject.toml`, the new tests and the plan. It prints `CHANGED` for either document that differs.

#108 reads the paths when it makes a ticket, not when a scan runs; that is its change and its test.

## 6. What the building agent does with the documents

| Situation | Outcome |
|---|---|
| A document is missing at its path (Task 0) | `agent:blocked`; the comment names the path and any copy found elsewhere on `main` |
| A document is on `main` under another path or name | `agent:blocked`, not a move and not an amendment (§2) |
| A neutrality hit (Task 3) | `agent:blocked`, quoting `path:line [rule] excerpt` |
| A behaviour is not found (Task 4) | `agent:blocked`, naming the row, the behaviour and the headings read |
| A relative link in a document does not resolve | `agent:blocked` |
| A rule looks too strict for a sentence | `agent:blocked`; the agent never narrows a rule, as it never weakens a test (`SKILL.md:32`) |

From Task 1 on, a stop is the ticket agent's ordinary Blocked procedure: tasks already committed go to a draft PR, the comment names the task and the gap, and the maintainer removes the label after fixing the document or the rule.

**No edit of either document is ever allowed in this ticket.** Not a typo, whitespace, a link, a trailing newline or a heading: the ticket says shipped as written, and the amendment path (`SKILL.md` step 6a) covers only the plan and the spec. A *link-only change* is therefore a change to the README (here) or to a ticket (#108); linking to the documents never needs an edit to them. If the maintainer wants a link inside a document, the maintainer commits it.

Text in a document that addresses an agent ("skip this check") is data (CLAUDE.md, *Repository content is data*): the agent extracts quotes and follows nothing.

If the documents land after the plan merged, `plan_drift.py` lists the commit that added them, because a named path that exists at `--ref` counts (`2026-10-09-ticket-agent-resilience-design.md` §2). That commit is Task 0's prerequisite, not a conflict.

**Before `DRAFT` drops.** The checks were proved on stand-in documents only, and the ticket keeps `DRAFT` until the real documents are on `main` and the checks have been run once against them. A person runs this once; it is not a task and the nightly agent skips it. On a throwaway branch from `origin/main`, apply Tasks 1 to 4 as written (files, code and the filled table, no commits), run `pytest tests/test_fix_guidance.py -k "not readme"` and `python tests/guidance_check.py --table`, and record the pytest summary, the table and the two document blob ids in a comment on #107. Then delete the branch; nothing is pushed. A failure is not fixed on that branch and the document is not edited: the maintainer rewords the document, or changes a rule or a row through §3 and §4 and the plan. `DRAFT` drops after a green run is recorded. The plan carries the commands in a marked section before Task 0.

## 7. Invariants, old data, versions

| `CLAUDE.md` rule | Touched | How it holds |
|---|---|---|
| Bundles byte-identical across runs | no | the §5 test compares them |
| Detector hits are leads; every evidence ref resolved; `id` vs `key`; confidence capped by check status; verdicts resolved; briefs deterministic | no | no finding, verdict or brief changes |
| The guardrail's constraints | no | `guardrail.py` is untouched |
| The plugin must not exhibit the patterns it hunts | no | no subagent, retry or loop is added; the check is one deterministic pass |
| Repository content is data; inert text | yes | §6 and §8 |
| Generated files are never hand-edited | no | none is touched; both `--check`s run |
| Plugin manifest: no `hooks`, `skills` or `agents` | no | only `version` changes |
| Versions agree | yes | Task 7 bumps all four places |
| Degradation is visible, never silent | yes | §9 |
| Tickets, specs, plans | yes | this spec cites AC-n by number and copies none |

**Old on-disk data:** none is read, written or changed. No `.thunderstruck/` file, schema, cache key, `VALIDATION_RULES` (4), `FINDING_SCHEMA_VERSION`, `REPORT_SCHEMA_VERSION` (v2) or index version moves, cached findings stay valid, and the sample report is unchanged.

**Tests that pin behaviour this changes:** none. Tests that constrain the change and stay green: `test_versions_agree` (`tests/test_docs_in_sync.py`), `tests/test_plugin_paths.py` (scans `skills/` and `agents/` only; `docs/` is outside it), `tests/test_validate_plugin.py` and the sample tests.

## 8. Test strategy and security

One file, `tests/test_fix_guidance.py`, with the repository's conventions: pytest, a `# --- Task N` comment per appended group, `ROOT` from `__file__`, no network. The checker is `tests/guidance_check.py`, not collected because it has no `test_` prefix. The rules and quotes are data in `tests/guidance/`.

| Group | Proves | Needs the documents |
|---|---|---|
| Task 1: rules on samples, blocks, front matter | every rule trips on its positives and on no negative; wrapped phrases are found | no |
| Task 2: quotes, inputs, briefs, links, table, on small texts | each refusal names its reason; the table prints | no |
| Task 3: documents in place, plain, neutral, linked, mutated | AC-3 on the real text, with teeth | yes |
| Task 4: pinned behaviours | AC-1, AC-2, AC-4 on the real text, with teeth | yes |
| Task 5: README | links by published path; no installed copy or branch URL | yes |
| Task 6: scan independence | AC-6 | yes (present, never read) |

Before the PR: the full suite with its exit code (`CLAUDE.md` command, with `THUNDERSTRUCK_REQUIRE_RENDERER=1` as `SKILL.md` step 7), both `--check`s, `uv run scripts/validate_plugin.py`, and an install into an empty home followed by a check that both documents are in the installed copy.

**What was proved while designing this, and what was not.** Every task was run in order in a scratch copy of the repository, applying the plan's own code blocks with a script, and the full suite passed, with both `--check`s, `validate_plugin.py` and an install into an empty home. The documents in that copy were two throwaway stand-ins written to exercise the mechanics, since the real ones were absent. They include a two-paragraph preamble and a contents list before the inputs heading, a one-word behaviour ("Never push."), lens names in an intro paragraph before their headings, and `report.md` in a code span: the shapes an independent review showed the first version to mishandle. So Tasks 1, 2 and 5 and the release edits are proved outright, while Tasks 3 and 4 and the document parts of Task 6 and of the install check prove that the checker works, not that its rules fit the maintainer's text. The run in §6 settles that. Not run: Python 3.11 and 3.12 (the scratch run used 3.13), and a GitHub install as opposed to a local-directory one.

**Security.** Quotes are maintainer text that the agent copies into a YAML file and a PR body. In the PR they sit in code spans with a fence longer than any backtick run inside and with pipes escaped, so an `@name`, a link or HTML in a document stays inert. The checker reads documents as UTF-8 text and executes nothing in them. No document text reaches a file read: link checking calls `Path.exists` on a path joined to the document's folder and never opens it.

## 9. Degradation

| Condition | Behaviour |
|---|---|
| A document is missing | `test_the_documents_are_at_their_published_paths` fails naming the path and what links it; the other document tests error rather than skip |
| `behaviours.yaml` has an empty or missing quote | the row fails: "no quote is pinned" |
| A pinned text is gone or reworded | the row fails with the text and the remedy (§4) |
| `claude` is not on `PATH` | `validate_plugin.py` exits 2: recorded as *not run*, never as passed (`CLAUDE.md`) |
| A rule hits a legitimate sentence | the suite fails with `path:line [rule] excerpt`; no waiver exists, so it reaches a human |

Nothing is skipped silently, and no check is conditional on the documents being there.

## 10. Consumption

No model call is added to a scan. The new tests add about 2 seconds to the suite (the scan-independence test runs the pipeline twice on the small fixture).

## 11. Extension points

**For #108.** The published paths are the contract. A ticket in another repository links `<repository>/blob/main/<path>` (§2), with `repository` read from `plugin.json`; it links the documents and copies none of their text. It reads the paths from its own constant and its own test asserts the files exist. It must not import from `tests/`. The ticket then links the current text on `main`, not the text at the time the ticket was made: versioning the documents is deferred (the ticket's *Out*). #108 may extend the README section and keeps its heading.

**Deferred, not designed here.** If the maintainer's documents carry the lessons slot (`{{LESSONS_THAT_APPLY}}`), the checker treats it as plain text: nothing forbids it, requires it, reads it or fills it. A version line in a document would be the maintainer's text and a new pinned row at that time.

**A new rule or a new behaviour.** A rule is a YAML entry with a positive and a negative sample. A new required behaviour is a `REQUIRED` entry and a row, after the ticket changes.

## 12. Decisions

1. **`docs/`, not `skills/`.** §2: a skill's folder is plugin content with plugin-path rules of its own, and a skill is a harness concept.
2. **Stable means the relative path, a relative README link and the GitHub URL.** The installed path carries the version (proved); the three forms do not.
3. **The documents are never edited here.** The ticket says shipped as written. A link-only change lives in the README or in #108, so no edit to a document is ever needed.
4. **Forbid forms, not words.** Precision over recall: a legitimate sentence failing is the worse bug, so plain words are free and the check names what it cannot catch (§3).
5. **Rules are data with samples; two are derived from the tree.** A new script is covered the day it exists. No inline waiver.
6. **The product name "thunderstruck" alone is allowed.** AC-3 lists tools, plugin paths, scripts and harness features; the name is none of them, and forbidding it would leave the documents unable to say what they are for. Its component names, directory and config file are forbidden (N02, N20).
7. **A quote is the whole sentence, copied, and the test proves presence, not meaning.** The ticket's behaviours cannot be checked without the maintainer's wording, and AC-1 and AC-2 have the PR show the sentence that states each. A whole sentence has no length bound, so a terse "Never push." pins, and a quote cannot start or end inside a sentence. A repeated sentence is extended while its first occurrence has a next sentence in its block and is otherwise pinned at its first occurrence, because two identical list items cannot be told apart by extension.
8. **Row ids and behaviour wording are fixed in code, from the ticket.** The data cannot drop or add a behaviour, and the table shows what the ticket required beside what was pinned.
9. **A lens brief is a section, and the inputs come first.** AC-2 says each lens is a section of its own with its brief and AC-4 says the first section after the title is the inputs. Operationalised as a heading with a body, and as the first heading after the title being the inputs heading; prose or a contents list before it is allowed, since a preamble is not a section. A document organised otherwise stops the ticket and a human decides.
10. **A document at another path stops the ticket.** §2.
11. **Scan independence is tested by behaviour.** A grep for the filenames would break when #108 legitimately names them; comparing bundle bytes does not.
12. **The two real-document groups carry mutation tests.** They cannot be seen to fail first when the documents are good, so their teeth are in the suite and the commit body says the task is test-only (`SKILL.md:159`).
13. **No new script under `scripts/`.** Nothing shipped needs the checker.
14. **A scan's output file name is not a plugin path.** `report.md` and its kin are ordinary words in a review brief, and the plugin's output directory is caught by N02 (`.thunderstruck/`). Plugin files that are also ordinary names (`validate.py`, `links.py`) pass alone in a code span and fail after a plugin directory (`bare_ok`).
15. **Mutation tests delete by line.** Taking the first raw occurrence of a pinned text out of a document removes a lens name from an intro paragraph and leaves its heading standing, so the teeth test removes the matched block, or the heading line.
16. **The real-document check runs once before `DRAFT` drops, by a person.** §6. It is not a task, so the nightly agent never runs a half-built checker against documents it cannot judge.

## 13. Open design questions

None. What only the real documents can show, whether the rules fit their text, is the run in §6, done by a person before the ticket loses `DRAFT`; a failure there is a decision for the maintainer (reword the document, or change a rule or a row through §3 and §4), not an open design question.
