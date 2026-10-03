# Defaults a finding relies on are confirmed or flagged, never assumed: design

**Requirements:** [#57](https://github.com/tomstagl/thunderstruck/issues/57), part of [#54](https://github.com/tomstagl/thunderstruck/issues/54). The problem, stories, scope, acceptance criteria (AC-n) and product decisions are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-10-04-confirmed-defaults.md`.
**Evidence:** `docs/calibration/correctness.md` (Spike 2) and FR-015 in `docs/calibration/correctness/celery/verdicts.json` (#53). Measured with #55 (`docs/superpowers/specs/2026-10-03-correctness-benchmark-design.md`).
**Builds on:** #5's `finding_shape.py` and capture hook, #56's finding contract (`docs/superpowers/specs/2026-10-03-checked-confidence-design.md`, "#56" below; §7.2 reserves `preconditions[].confirmation` and the gate `unconfirmed_default` for this ticket) and #37's verification pass (`docs/superpowers/specs/2026-10-03-finding-verification-design.md`, "#37" below; §16 is this ticket's hook). All three must be on `main` first, and #55's `scripts/benchmark.py` for §13.

## 0. What the evidence says

FR-015 claimed that Celery's database result backend retries every `DatabaseError` three times by default, disposing the connection pool before each retry. Its premise was line 70 of `celery/backends/database/__init__.py`:

```python
        self.always_retry = conf.get('result_backend_always_retry', True)
```

The fallback `True` never applies: the settings object already holds every registered default (`always_retry=False`, `max_retries=inf` in `celery/app/defaults.py`), so `conf.get` returns those. On defaults the backend does not retry at all, which is the defect the scan missed. The code comment, the docs and Celery's own tests make the same mistake.

Spike 2's two read-only refuters read the same two lines. One concluded `False` (refuted correctly, citing the registry); the other concluded that the backend "overrides both defaults: `always_retry=True` and `max_retries=3`" (the investigator's mistake, repeated). Reading did not settle this class; it settled every other one.

Two facts follow, and the design is built on them:

1. **The wrong reading has a mechanical signature.** In both wrong readings the default was located *at the line that reads the setting, as a fallback argument*. A location of that shape cannot establish the effective default when a settings layer may hold its own; a script can recognise the shape without running anything (§4).
2. **The right reading cites a different place.** The refuter that was right cited where the setting is registered (`defaults.py`). Confirmation therefore means: a check cited a resolving location that registers the default and is not a fallback read (§3).

The ground truth has five *discriminating* preconditions (literal and effective differ, #55 §4.5): `result_backend_always_retry` (FR-014, FR-015), `result_backend_max_retries` (FR-015), `task_acks_on_timeout` (FR-002) and `redis_socket_connect_timeout` (FR-001). The fallback-read rule catches the first three, all stated at a `conf.get(name, fallback)` call. The other two are resolved elsewhere (a fallback to another setting, and a dependency's default); only a check that reads further can find them, which is why the skeptic's confirmation exists (§6) and why an unchecked default is never shown as confirmed.

## 1. Architecture

```
investigator      writes  preconditions[] (#56), unchanged
finding_shape.py  strips  preconditions[].confirmation from model output,
                          for save_finding.py and the capture hook (#5)         (§5.3)
validate.py       writes  preconditions[j].confirmation from the fallback-read
                          rule, every run: confirmed never, call_site recorded    (§4, §5)
verify.py prepare shows   each default to confirm in the brief                    (§6.2)
thunderstruck-skeptic     returns confirmations[] beside its verdict             (§6.1)
verify.py apply   resolves each confirmation, applies the rule to its location,
                          derives every confirmation, refuses upheld on an
                          unconfirmed default (verify.settle), writes
                          check.confirmations and preconditions[j].confirmation   (§6.3, §7)
report.py         derives confirmation again from what was stored, gates,
                          orders, renders md · json · index                       (§8, §9)
report_html.py · guardrail.py   render what report.json / index.json carry        (§9)
```

One function decides a confirmation (`_common.confirm`), one decides whether a finding relies on an unconfirmed default (`_common.unconfirmed_defaults`), and `_common.finding_gate` (#56 §5, extended by #37) gains the third gate. `guardrail.py` cannot import `_common`; it reads states already decided in `index.json` and carries only the gate order, which a test pins (§9.5).

The governing rule holds. The investigator and the skeptic state defaults and locations. Whether a location resolves, whether it is a fallback read, which state and basis follow, whether a finding can be upheld, and where it sorts are computed. Nothing in this ticket runs, imports or builds the scanned project (§11).

## 2. Who writes what

| Field | Written by | Rule |
|---|---|---|
| `preconditions[j].confirmation` | `validate.py`, then `verify.py apply` | `_common.confirm(...)` over the mechanical facts and, after `apply`, the skeptic's resolved item (§3). Never from a model: `finding_shape.py`'s owned-field strip removes it and `validate.py` overwrites it |
| `check.confirmations` | the skeptic, resolved by `apply` | §6.3. A key under `check`, so it travels with the verdict into the ledger and is reused with it (#37 §10) |
| `confirmations` (verdict top-level key) | the skeptic | Added to `verify.VERDICT_KEYS` (#37 §8.1, §16) |
| gate `unconfirmed_default` | `_common.finding_gate` | §8 |

`check.confirmations` is a key #56 §7.1 does not list. `validate.py` accepts other keys under `check` unread (#56 §3.1), so it works mechanically; the reservation belongs in #56's spec (§19 q1).

## 3. The confirmation

### 3.1 Shape

```json
"confirmation": {
  "state": "unconfirmed",
  "basis": "call_site_fallback",
  "reason": "the default is stated where the setting is read, as a fallback; the value in effect may be registered elsewhere",
  "call_site": true,
  "by": "validator"
}
```

| Key | Values | Meaning |
|---|---|---|
| `state` | `confirmed` · `unconfirmed` | AC-1's two states. Nothing else is confirmed |
| `basis` | §3.2 | Why, as a word a script decided |
| `reason` | one line | `CONFIRMATION_REASONS[basis]`, fixed text written by the tool. The skeptic's own reason line, when there is one, is kept on its `check.confirmations` item and rendered beside it as model text |
| `call_site` | `true` · `false` · `null` | The fallback-read rule (§4) applied to the investigator's `default_ref`. `null` when it could not be applied (the file is unreadable, or the item predates this ticket) |
| `by` | `validator` · `skeptic` | `skeptic` when a check's item decided the basis |

### 3.2 Bases and the one rule

| `basis` | `state` | When |
|---|---|---|
| `registered` | confirmed | A check found the default registered at a location that resolves and is not a fallback read, and states it is the same default |
| `contradicted` | unconfirmed | A check found a different default registered at a location that resolves and is not a fallback read |
| `call_site_fallback` | unconfirmed | The location given (the investigator's, with no check; or the check's own) is a fallback read of this setting |
| `not_found` | unconfirmed | A check looked and found no place that registers the default |
| `unresolved` | unconfirmed | The location a check gave does not resolve |
| `not_checked` | unconfirmed | No check looked: verification off, the finding `unchecked`, or the skeptic gave nothing for this setting |

```
confirm(call_site, item):                      # item: the skeptic's resolved item, or None
    if item is None:            basis = call_site_fallback if call_site else not_checked
    elif item.found == not_found:        basis = not_found
    elif item.default_ref_error:         basis = unresolved
    elif item.default_call_site:         basis = call_site_fallback
    elif item.found == different:        basis = contradicted
    else:                                basis = registered
    state = confirmed if basis == registered else unconfirmed
```

`confirm` takes only facts the scripts established (`call_site`, `default_call_site`, `default_ref_error`) and the skeptic's one categorical answer (`found`). A skeptic that states the investigator's call-site line as the registration gets `call_site_fallback`, so the Spike 2 refuter that was wrong could not have confirmed FR-015's default; one that cites the registry and says `different` gets `contradicted`, which is FR-015's outcome on #55 (AC-6).

A `confirmed` default needs a check. Without verification every default is unconfirmed, and the basis says whether the location was a fallback read or merely not checked. This is how AC-2 reads in this design: a default stated at a fallback read is unconfirmed, decided mechanically, and a check confirms it only by citing another place that registers the same value (the ticket's AC-2 is reworded to say so).

## 4. The fallback-read rule (AC-2)

### 4.1 What it matches

A location is a **fallback read** of setting *S* when, after comments are blanked (`_common.strip_comments`, as detectors do), the text of its line range matches one of the catalog's `setting_reads` patterns for the file's language with `{setting}` replaced by *S* (escaped, case-insensitive). The range's lines are joined with newlines, so a call split across lines matches.

The patterns live in `catalog/stability.yaml` under a new top-level `setting_reads` section, keyed by catalog language and honouring `aliases`, so recognising a new settings API is a catalog edit plus samples, as for detectors (CLAUDE.md, *The catalog is the source of truth*):

```yaml
# Reads of a setting that supply their own fallback (#57). A default stated at
# one of these is unconfirmed: a settings layer may hold another value. Each
# pattern is matched against the cited lines with comments blanked; {setting}
# is replaced by the setting's name, escaped. Matched case-insensitively.
setting_reads:
  python:
    - '\.(?:get|pop)\(\s*[''"]{setting}[''"]\s*,'          # conf.get('x', True), kwargs.pop('x', 3), environ.get
    - '\bgetattr\(\s*[^,()]+,\s*[''"]{setting}[''"]\s*,'   # getattr(settings, 'X', 5)
    - '\bgetenv\(\s*[''"]{setting}[''"]\s*,'               # os.getenv('X', '30')
  typescript:
    - '\.get\w*\s*(?:<[^>()]*>)?\(\s*[''"`]{setting}[''"`]\s*,'                # config.get<number>('x', 5)
    - 'process\.env(?:\.{setting}\b|\[\s*[''"`]{setting}[''"`]\s*\])\s*(?:\?\?|\|\|)'   # process.env.X ?? 30
  java:
    - '\.get\w*\(\s*"{setting}"\s*,'                       # getProperty("x", "5"), getOrDefault, getInt("x", 5)
    - '\$\{{setting}:'                                     # @Value("${x:30}")
  yaml:
    - '\$\{{setting}:'                                     # ${x:30} placeholders
  properties:
    - '\$\{{setting}:'
```

`{setting}` is substituted with `str.replace`, never `str.format`, so regex braces stay literal. The setting's name is the precondition's `setting` with surrounding whitespace removed; a name that contains whitespace (prose, not a name) never matches, and the location is then not a fallback read.

### 4.2 What it does not match, by design

- **A registration.** `backend_always_retry=Option(False, type='bool')`, `DEFAULTS = {"max_retries": 3}`, `private Duration timeout = Duration.ofSeconds(30);`, `parser.add_argument("--timeout", default=30)`. These are where defaults are registered; flagging them would make every correct citation unconfirmable.
- **A read with no fallback.** `conf.result_backend_always_retry`, `process.env.API_RETRY_ON_429 === "true"`, `System.getenv("X")`. The default is implicit (unset); a check may confirm it by citing that line, because no literal there can be shadowed.
- **A fallback to a constant defined elsewhere** still matches (`conf.get('x', DEFAULT_X)`): the shape, not the literal, is what a settings layer can shadow.
- **A fallback read of another setting** on the same lines does not match: the name is part of the pattern.

A false positive here is worse than a miss (CLAUDE.md, *The negative-control discipline*): it would cap a correct finding below `upheld` for good. So every language with a `setting_reads` entry has positive and negative cases in the test table (§17), the negatives being the registration shapes above, and a test fails when a language has only one polarity. A miss costs less: the default stays `not_checked` until a skeptic looks, and the skeptic's own location goes through the same rule.

### 4.3 Where it applies

To the investigator's `default_ref` (validator, every run, §5), to a check's `default_ref` and to a check's `stated_ref` (§6.3). For a dependency ref (#37 §4.5), the text is read from the snapshot file `deps.py` made, the language from its extension. It never applies to `doc_ref`.

## 5. The validator

### 5.1 Every run

`validate.py` runs over every findings file on every scan (scan skill, step 4), cached ones included. After a document passes, for each precondition item it writes `confirmation = confirm(call_site, None) | {"call_site": call_site, "by": "validator"}`, where `call_site = Validator.fallback_read(default_ref, setting)`. So `--no-verify` scans carry a correct mechanical confirmation with no other stage involved, and a stale confirmation from an earlier verified scan never survives re-validation.

### 5.2 `Validator.fallback_read(ref, setting, allow_dependency=False) -> bool | None`

Parses `ref` with the same `check_ref` that resolved it (#56 §3.1; #37's `allow_dependency`), reads the lines, detects the language from the catalog's language map, blanks comments, and applies §4.1. `None` when the ref does not resolve, the file cannot be read as UTF-8, or the language has no `setting_reads` entry. It reads only files `check_ref` resolved: tracked repository files, or snapshot files under `.thunderstruck/deps/`.

### 5.3 Accepted, stripped, overwritten

- `PRECONDITION_KEYS` (#56) gains `confirmation` as a key `validate.py` accepts (its value is not checked: it is replaced). An investigator writing it is not an error; it simply never survives.
- The owned-field strip in `scripts/finding_shape.py` (#5; after #5 it holds the owned keys and `FINDING_SCHEMA_VERSION`, and both `save_finding.py` and the capture hook's `shape()` call it) also removes `preconditions[].confirmation`, beside #56's `check`, `history`, `confidence_claimed`. It is a nested key, so the strip walks the `preconditions` list rather than adding a name to the top-level tuple.
- `VALIDATION_RULES` does not change: no rule is tightened. A findings file validated before this ticket gains `confirmation` the next time `validate.py` runs, which every scan does.

## 6. The skeptic's confirmations

### 6.1 Contract

`verify.VERDICT_KEYS` (#37 §8.1) gains `confirmations`, a list (may be empty, may be omitted):

```json
"confirmations": [
  {"setting": "result_backend_always_retry",
   "claim": "always_retry defaults to True with 3 retries",
   "stated_ref": "celery/backends/database/__init__.py:70-71",
   "found": "different",
   "default": "False",
   "default_ref": "celery/app/defaults.py:231",
   "reason": "conf.get returns the registered default; the literal fallback never applies."}
]
```

| Key | Rule |
|---|---|
| `setting` | Non-empty string. When it matches a precondition of the finding (case-folded, whitespace removed, #56 §2.2's uniqueness rule) the item confirms that precondition |
| `claim` | For a setting the finding relies on but does not list: required, and must quote the finding (#37 §8.3's `_quotes` rule over `failure_mode`, `trigger_condition`, `amplifier`, `sustaining_effect`, `blast_radius`, `how_to_verify` and evidence `note`s). `null` for a listed precondition |
| `stated_ref` | For an unlisted default: optionally, the finding's own code ref where it locates that default; must equal one of the finding's `code` evidence refs after canonicalisation. `null` otherwise |
| `found` | `same` · `different` · `not_found` (`CONFIRMATION_FOUND`) |
| `default` | The bare value found (`"False"`, `"120"`, `"None"`); required unless `not_found` |
| `default_ref` | Where it is registered; resolves through `check_ref(..., allow_dependency=True)`; required unless `not_found` |
| `reason` | One line, inert |

`found` is the skeptic's one categorical judgement: whether the value it found is the value the finding states. Text comparison of two free-form defaults (`"None"` against `"None (block indefinitely)"`) is not reliable enough to decide it mechanically; what makes the answer safe is that `same` confirms nothing unless the location passes §4 (Decision 4).

**Unlisted defaults** exist for two reasons: the investigator can omit one (the counterpart of #37's missing gate), and #55's frozen Celery findings predate #56 and carry no `preconditions` at all, so on them every default is unlisted. `stated_ref` lets the fallback-read rule reach a frozen finding's own location: FR-015 cites `celery/backends/database/__init__.py:70-71`, which is a fallback read of `result_backend_always_retry`.

### 6.2 The brief

`verify.py prepare`'s brief (#37 §6.2) gains, after *The claim*, a section **Defaults to confirm**: per precondition, its setting, stated default, stated location and one mechanical line, "Stated at a fallback read of this setting: yes / no / could not be read", taken from the validator's `call_site`. It is a fact about the location, not the investigator's reasoning, so it does not breach the product decision on what the skeptic sees. The brief stays deterministic.

The skeptic's prompt (`agents/thunderstruck-skeptic.md`) gains a numbered rule: confirm every default the claim rests on, listed or not; find where the settings layer registers it (a defaults table, a schema, a settings class, a configuration file the project ships, the dependency's own default in the snapshot) and cite that; a fallback argument at the line that reads the setting is not a registration and confirms nothing; give `default` as the bare value. And the no-execution sentence of §11.

### 6.3 Resolving the items (`verify.settle`)

Each item is checked in order; an item that breaks a rule is dropped and named in the check's reason ("Ignored: confirmations[1] …"), like a refuted claim (#37 §8.3), and never fails the verdict on its own:

1. An object with only `CONFIRMATION_KEYS`; `setting` a non-empty string; `found` one of the three; one item per setting (the first is kept).
2. Listed or unlisted: listed when `setting` matches a precondition; otherwise `claim` must quote the finding.
3. `stated_ref` (unlisted only): kept when it equals a finding code ref; its fallback-read result becomes `stated_call_site`.
4. `found` `same`/`different`: `default` a non-empty string; `default_ref` resolved by `Resolver.ref`. A failure is not a drop: the item is kept with `default_ref_error` (the first error), because a check that looked and gave a bad location is information (`unresolved`). Otherwise `default_call_site = Resolver.fallback_read(default_ref, setting)`.

The kept items, with `precondition` (the index of the listed precondition, or `null`), `stated_call_site`, `default_call_site` and `default_ref_error` added, become `check.confirmations`. Then:

- each precondition's `confirmation = confirm(pre.confirmation.call_site, its item or None)` with `by: skeptic` when an item decided it;
- each unlisted item's state is `confirm(stated_call_site, item)`, stored on the item as `confirmation`.

## 7. Settling: no `upheld` on an unconfirmed default (AC-3)

### 7.1 The rule

A finding **relies on an unconfirmed default** when any precondition with `needs: default`, or any unlisted item in `check.confirmations`, is `unconfirmed`. `_common.unconfirmed_defaults(finding) -> list[dict]` returns those, from the confirmations already derived on the finding; it is the one definition (`settle`, `finding_gate`, the report and the benchmark export all use it).

At the end of `verify.settle` (#37 §9), after #37's table has decided a status, and on **every** path that yields a status (fresh verdict and `reuse` alike):

| Status from #37's table | Relies on an unconfirmed default | Result |
|---|---|---|
| `upheld` | yes | `inconclusive`; reason "The check upheld this claim, but it rests on a default no one confirmed: `S` (<basis reason>)." with the first such setting, then "and N more" |
| anything else | — | unchanged |

`inconclusive`, not `narrowed`: nothing showed a part of the claim to be false (a `narrowed` needs a refuted claim and `holds`, #37 §9); what is missing is the confirmation, which is an attempt that did not settle the claim. The ceiling is `medium` either way (#56 §4.2), which is AC-3's bound. A `narrowed` finding that also relies on an unconfirmed default stays `narrowed`. `needs: changed` items do not trigger the rule: the failure does not rest on their default.

Applying it to the reuse path matters: a ledger entry written by #37 before this ticket carries no `confirmations`, so its defaults derive as `not_checked`, and an `upheld` reused from it settles as `inconclusive` until a skeptic confirms. No `upheld` granted without confirmation survives the upgrade, the same guarantee #56 §3.5 gives for `high`.

### 7.2 What changes in #37's reuse

- `claim_hash` (#37 §10) excludes `preconditions[].confirmation`, which is validator- and verifier-written, as it already excludes `check` and `history`. Otherwise `validate.py`'s rewrite would make every verdict look changed.
- The ledger's `files` adds every repository file a kept `default_ref` or `stated_ref` cites, so a change to the registry that confirmed a default invalidates the verdict; `dependency_versions` adds the package of every resolving dependency `default_ref`.
- `cited_files` gains the confirmation refs for the same reason.

### 7.3 Frozen runs

With `prepare --frozen` (#37 §5) the findings come from a report and carry no `preconditions`; every confirmation is unlisted, `stated_ref` is resolved against the frozen finding's code refs in the repository checkout, and `verdicts.json` carries `check.confirmations`. Nothing is written to findings files, as #37 specifies.

## 8. Gate and order

`GATES = ("none", "unconfirmed_default", "non_default_setting")`, `GATE_MARKERS["unconfirmed_default"] = "relies on an unconfirmed default"`. `finding_gate` returns, in this precedence: `non_default_setting` (#56's rule and #37's extension), else `unconfirmed_default` when `unconfirmed_defaults(finding)` is non-empty, else `none`. One gate per finding; a finding that needs a setting changed is marked as that, and its unconfirmed defaults are still shown in its Preconditions block.

**Unconfirmed defaults sort before findings that need a non-default setting.** The product decision puts both after default-path findings; between them, this design orders by how many deployments a finding would reach if it holds:

- A finding resting on an unconfirmed default *claims the default path*. If its default holds, it reaches every deployment, and the reader's check is one lookup the report hands them: the setting, the stated location and, after a check, the location the check found.
- A finding that needs a non-default setting reaches only deployments that changed it, and a reader rules it in or out from their own configuration.
- With `--no-verify` every default is unconfirmed, so every finding that lists a `needs: default` precondition falls into this group. Placing it after the opt-in findings would put most of a quick scan's default-path findings behind the opt-in ones; placing it before keeps the opt-in findings last, as #56 intended.

#56 §7.2 says #57 "appends" the value and leaves the position to #57; inserting it in the middle is that decision. Nothing else changes: the sort key, the marker, `counts.gate`, `index.json`'s `gate` and the guardrail's order all read `GATES` (#56 §5).

## 9. Outputs (AC-1, AC-4)

`report.py` never trusts a stored confirmation. In `collect()`, on its copy of each finding, it derives each precondition's confirmation with `confirm(stored call_site, item)` where `item` comes from `check.confirmations` only when verification ran for this scan (#37 §11.1), and `None` otherwise; unlisted items likewise. Then gate and order. So `--no-verify` after a verified scan shows mechanical confirmations only, matching the `unchecked` statuses #37 resets, and a standalone `validate.py` rerun cannot desynchronise the two.

All model-written values (`default`, `claim`, the skeptic's `reason`) are inert (`md.code` for defaults, `md.text` otherwise; `textContent`; plain text in the guardrail). Repository refs are linked by the tool; dependency refs never are (#37 Decision 7).

### 9.1 `report.md`

**Header**, after #56's check-status line:

```
Defaults: 4 confirmed · 6 unconfirmed (2 stated where the setting is read, 1 contradicted by a check, 3 not checked) · 2 findings rely on an unconfirmed default and are listed after default-path findings
```

**Badge line** for a gated finding: `· relies on an unconfirmed default` (from `GATE_MARKERS`).

**Preconditions** (#56 §6.1), each line gains its confirmation; when a check gave a default, both are shown with where each was found (AC-4):

```
- `sync.pageSize` left at its default `100`, registered at [src/sync/collection.ts:4](…). **Unconfirmed**: a check found a different default registered: `500` at [src/config/settings.ts:3](…). Check's note: “The registry holds 500; get() returns it.”
- `API_RETRY_ON_429` set to `true`; default `false (unset)`, registered at [src/client/api.ts:1](…). **Confirmed**: a check found this default registered, and it agrees: [src/client/api.ts:1](…).
- `task_acks_late` left at its default `False`, registered at [celery/app/defaults.py:269](…). **Unconfirmed**: no check looked for where this default is registered.
```

Unlisted items follow under "Defaults the check found this claim rests on:", each as "`S`: the finding says “<claim>”; …" with the same confirmation clause.

### 9.2 `report.json`

Stays `thunderstruck.report/v2` (#56); every addition is a key:

| Field | Value |
|---|---|
| `findings[].preconditions[].confirmation` | as derived (§3.1) |
| `findings[].check.confirmations[]` | as stored, with `default_url` (repository link or `null`) and each unlisted item's derived `confirmation` |
| `findings[].gate` | now one of three |
| `counts.gate` | three keys |
| `counts.defaults` | `{"confirmed": n, "unconfirmed": n, "basis": {<six bases>: n}}`, over listed preconditions and unlisted items of reported findings |

`counts.defaults` is the dogfood figure the ticket's success measure asks for: the share left unconfirmed, and by which basis.

### 9.3 `index.json`

Each precondition entry (#56 §6.3) gains `"confirmation": "confirmed" | "unconfirmed"`. `gate` takes the new value. Unlisted items are not written: the guardrail states a few facts and points at the report.

### 9.4 HTML report

`templates/report.html`: each Preconditions line gains a `Confirmed` / `Unconfirmed` tag and the same clause as §9.1 (`CONFIRMATION_REASONS` copied into the script as a JSON literal, compared with `_common` by a test, as #56 does for `CHECK_SENTENCES`); the dossier tag and rail marker for the new gate come from `GATE_MARKERS`; the overview's counts gain the defaults line. `textContent` only, no new sink.

### 9.5 Guardrail

The precondition line (#56 §6.5) names the state: "It happens on default settings and rests on S at its default D, which no check confirmed." / "…, which a check confirmed." The ordering copy `GATE_ORDER` becomes the three gates; a test pins it to `_common.GATES`. Statements of fact, stdlib only, exit 0, under 100 ms.

## 10. Defaults registered in a dependency (left to this ticket by #37 and #56 §7.2)

**Investigator `default_ref` stays repository-only.** The snapshot is made by `verify.py prepare`, after investigation; letting validation depend on a snapshot an earlier run left behind would make the findings contract depend on history and break the byte-identical bundle guarantee for cached hotspots. A dependency's own default is cited in the skeptic's `check.confirmations[].default_ref`, which `apply` resolves with `allow_dependency=True`. Where the repository registers a value that a dependency then resolves (FR-001: `redis_socket_connect_timeout=Option(None)` in `celery/app/defaults.py`, which redis-py turns into the socket timeout), the investigator cites the repository registration and the skeptic, reading the dependency, answers `different` with the dependency location. `check_ref` remains the one place a later change would widen this (#56 §3.1).

## 11. No stage runs, imports or builds the scanned project (AC-5)

### 11.1 What "the scanned project" covers

Every stage of a scan (`signals.py`, `context.py`, `bundle.py`, the investigators, `save_finding.py`, `validate.py`, `verify.py` and `deps.py`, the skeptics, `report.py`, `report_html.py`, #5's capture hook and `usage.py`) and the edit guardrail. They may read the repository, its history and installed dependency source as data. They may start exactly two kinds of process: `git`, and the service-catalog command the user approved by hash on this machine (#1's trust model in `context.py`; it is a catalog client the user chose, not the project's code). `gen_sample_report.py` runs thunderstruck's own scripts on the fixture and is not a stage.

`/thunderstruck-verify` writes and runs a test at the user's explicit request; it is not a scan stage and nothing it produces is read by one. That reading is recorded in the ticket's open product questions for the maintainer to confirm.

### 11.2 The test (`tests/test_no_execution.py`)

- **Static, every script.** Parse every `scripts/**/*.py` and the command in `hooks/hooks.json`. Forbidden anywhere: `exec`, `eval`, `compile`, `__import__`, `importlib`, `runpy`, `ctypes`, `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `pty`; a `sys.path` change whose argument does not derive from `__file__`. A `subprocess` call is allowed only in an allowlisted function: `_common.git`, `git_paths`, `commit_touches`, `commit_exists`, `tracked_index`, `find_repo_root` (each with the literal `"git"` as the first argv element, checked in the AST), `context.run_command` (the approved command), and `gen_sample_report` (not a stage). A new subprocess call fails the test until it is reviewed into the list.
- **Dynamic, every stage.** A fixture repository is booby-trapped: `setup.py`, `conftest.py`, `sitecustomize.py`, a package `__init__.py`, a `.pth` file in a `.venv` site-packages with a `dist-info`, `package.json` with `preinstall`/`postinstall`/`prepare` scripts, `Makefile`, `build.gradle`, `pom.xml`, `gradlew`, `.envrc`; each would create a sentinel file if run or imported. A `PATH` directory shadows `npm npx yarn pnpm pip pip3 poetry mvn gradle make node java go cargo tox pytest` with scripts that create a sentinel. The pipeline runs over it (signals, bundle, canned findings saved and validated, `verify.py prepare` with `deps.py` discovering the `.venv`, canned verdicts, `apply`, `report`, `report_html`, the guardrail on a payload). No sentinel may exist afterwards.
- **Instructions.** `agents/thunderstruck-investigator.md`, `agents/thunderstruck-skeptic.md` and `skills/thunderstruck-scan/SKILL.md` contain the sentence "Never run, import, install or build the project you are analysing, or anything in it." Both agents' `tools` are a subset of `Read, Grep, Glob`.

## 12. Fixture and sample (AC-7)

The sample has to show a confirmed default, a contradicted one, the mechanical call-site basis and the `upheld` → `inconclusive` rule. The fixture gains a miniature of Celery's case:

- `src/config/settings.ts`: a registry `const REGISTERED: Record<string, unknown> = { "sync.pageSize": 500 };` and `export function get<T>(key: string, fallback: T): T` that returns the registered value when present.
- `src/sync/collection.ts` (`UNCHECKPOINTED_SYNC`) reads `const PAGE_SIZE = get<number>("sync.pageSize", 100);` and passes it to `fetchCollectionPage`. S07's detector still fires (the loop is unchanged).
- One commit, `feat: page size from settings`, touching both.

`gen_sample_report.py`: the canned collection finding gains a precondition `sync.pageSize`, default `100`, `default_ref` at the read line, `needs: default` (the redo cost on restart rests on it). The validator marks it `call_site_fallback`. Its canned verdict stays `upheld` and adds a confirmation `found: different`, `500` at `settings.ts`, so the real `apply` settles it `inconclusive` with §7.1's reason, and the report lists it after the default-path findings with the marker. The canned api.ts verdict (#37: `narrowed`) adds `API_RETRY_ON_429` `found: same` at `api.ts:1`, so the sample shows a confirmed default. Both samples are regenerated in the same change.

## 13. Measuring it on #55 (AC-6)

### 13.1 Deterministic: Spike 2 replayed

`tests/test_confirmed_defaults.py` builds a two-file git repository with Celery's shape: `backends/database.py` holding the two `conf.get(..., True)` / `conf.get(..., 3)` lines quoted in the frozen bundle `scan/bundles/H08.md`, and `app/defaults.py` holding registrations of the same shape (`backend_always_retry=Option(False, type='bool')`, `backend_max_retries=Option(float('inf'), type='float')`). A finding shaped like FR-015 (no `preconditions`, a code ref to the two lines) is settled twice through the real `verify.settle`:

| Canned verdict | Expected |
|---|---|
| Refuter A: `upheld`; confirmation `same`, `True`, `default_ref` the `conf.get` line | `inconclusive`; the item's state `unconfirmed`, basis `call_site_fallback` |
| Refuter B: `narrowed` with a resolving refuted claim; confirmation `different`, `False`, `default_ref` the registry line | `narrowed`; basis `contradicted`; both defaults rendered with their locations |

### 13.2 On the frozen set

After #37's measurement on #55 has chosen the default skeptic model, the maintainer runs #37 §13's procedure once more with this ticket's skeptic prompt: `verify.py prepare --frozen`, the skeptics, `verify.py apply`, `verify.py export-run`. `export_run` (#37) adds, per finding, `preconditions: [{"setting", "default", "confirmation"}]` from `check.confirmations`: `default` is the check's found default when it gave one, else the investigator's stated default (listed preconditions only); `confirmation` the derived state.

`benchmark.py` (#55) is extended: `score_defaults` keeps a run precondition's `confirmation` on its row, and the result gains `confirmed_not_effective` (rows whose run state is `confirmed` and whose outcome is not *matches effective*), printed as a figure line with its basis. The PR records:

- FR-015's settled status (not `upheld`) and the state and basis of its `result_backend_always_retry` and `result_backend_max_retries` items (`unconfirmed`, `contradicted` or `call_site_fallback`): AC-6's first half.
- `score_defaults`' counts over the discriminating and non-discriminating preconditions: AC-6's second half.
- `confirmed_not_effective`, which the ticket's success measure needs at 0.
- #37 AC-12's same-class count on this run, and the findings §7.1 turned from `upheld` into `inconclusive` with their labels, so the rule's effect on AC-12 is visible (§19 q3). Each such finding's `check.reason` names the rule, so the list is read from `verdicts.json`, not reconstructed.

The run file is checked in as `docs/calibration/correctness/celery/runs/confirmed-defaults-<alias>.json`; the figures go into `docs/calibration/verification.md` under "Defaults".

## 14. Security

- A model cannot confirm a default by assertion: `confirmation` is stripped on save and on capture and overwritten by the validator; `confirmed` needs a resolving location that passes §4, and `confirm` reads only script-established facts plus `found`.
- `default_ref` and `stated_ref` resolve through `check_ref` before any file is opened; dependency refs only inside `.thunderstruck/deps/` (#37 §15). The fallback-read rule reads only resolved files.
- Repository text that tries to steer confirmation ("this default is safe", "already confirmed") is data. It cannot become a confirmation: the outcome needs a location of the right shape, and an `OTHER` finding's own steering text is covered by #37's AC-11 rule.
- Catalog `setting_reads` patterns are trusted plugin data, compiled once; the setting name is escaped before substitution, so a hostile setting name cannot inject regex syntax.
- New model-written strings are rendered inert in every output; `test_inert_report.py` and `test_report_html.py` extend `MODEL_FIELDS` to `confirmations[].default`, `.claim`, `.reason`.

## 15. Degradation

| Condition | Behaviour |
|---|---|
| `--no-verify` | Every default unconfirmed, basis `call_site_fallback` or `not_checked`; no `upheld` exists to downgrade |
| A default's file cannot be read, or its language has no `setting_reads` | `call_site: null`; basis `not_checked` until a check looks |
| The skeptic returns no `confirmations` | Every default `not_checked`; an `upheld` verdict becomes `inconclusive` if the finding lists a `needs: default` item |
| A confirmation item breaks the contract | Dropped and named in the reason; the verdict stands |
| A confirmation's `default_ref` does not resolve | Kept, basis `unresolved`, the error shown |
| A dependency snapshot is unavailable | The skeptic cannot cite it; the default stays unconfirmed with `not_found` or `not_checked` |
| A ledger entry from before this ticket | Reused; its defaults derive `not_checked`, so a reused `upheld` settles `inconclusive` (§7.1) |
| A findings file validated before this ticket and not re-validated | `report.py` derives `call_site: null` → `not_checked` |
| An `index.json` from before this ticket | The guardrail omits the confirmation clause and orders the two old gates as before |

## 16. Consumption

No model call is added. The skeptic reads more on findings that rely on defaults: typically one registry file per finding (Spike 2's refuters read 4–10 files per finding; confirming a default adds the defaults table they mostly opened anyway). The cost lands in #37's `skeptics` block and counts against #37's ceiling (AC-15 there); the §13.2 run records `usage.json`'s skeptic figures beside #37's.

## 17. Test strategy

- **The rule tables.** `confirm` over every combination of `call_site` (true/false/null) and item (none; each `found`; with `default_ref_error`; with `default_call_site`); `unconfirmed_defaults` on listed and unlisted, `needs: changed` ignored; `finding_gate` precedence over all three gates and #37's narrowed-setting case; vocabularies spelled as the spec.
- **Fallback reads.** A table of (language, text, setting, expected) with, per language in `setting_reads`, the positive shapes of §4.1 (including Celery's line verbatim and a call split over lines) and the negative shapes of §4.2 (registrations, reads without fallback, another setting's read, the read inside a comment, a setting name with whitespace, regex metacharacters in a name); a test that every `setting_reads` language has both polarities; the alias (`javascript` → `typescript`).
- **Validator.** `confirmation` written on a passing document; `call_site` true at a fallback read, false at a registration, null on an unreadable file; an investigator-written `confirmation: confirmed` is overwritten; `finding_shape.py` strips it for `save_finding.py` and the capture hook; re-validation recomputes after the file changes.
- **Settle.** Every rule of §6.3 (drop and name, unlisted with and without a quoting claim, `stated_ref` not among the finding's refs, unresolved kept); §7.1's table including the reuse path with a pre-#57 ledger entry; `claim_hash` unchanged by a confirmation rewrite; ledger `files` gains the registry file and a change to it forces `check`.
- **Spike 2 replay** (§13.1).
- **Report.** Derivation from stored facts with and without `run.json`; the header line and `counts.defaults`; the three-gate order (an unconfirmed-default `high` claim after a default-path `low`, before a non-default-setting finding); AC-4's both-defaults clause; `index.json`'s state; inert text.
- **HTML and guardrail.** The tag and clause; `CONFIRMATION_REASONS` and `GATE_ORDER` copies pinned to `_common`; guardrail phrasing and latency.
- **No execution** (§11.2).
- **Sample.** `gen_sample_report.py --check`; the sample shows a confirmed default, a contradicted one, `call_site_fallback` and the `inconclusive` collection finding listed after the default-path findings with its marker.
- **Benchmark.** `score_defaults` carries `confirmation`; `confirmed_not_effective` on a synthetic run; `export_run`'s preconditions.

## 18. Decisions

1. **The mechanical rule targets one shape: a fallback argument at a read of the named setting.** It is the shape of every wrong reading in the evidence, and recognising it needs no knowledge of the framework. Broader rules (any line mentioning the setting) would flag registrations and destroy trust in the flag.
2. **Patterns in the catalog, with positive and negative samples.** Recognising a settings API is the same kind of knowledge as a detector, and gets the same discipline.
3. **`confirmed` needs a check.** The validator can only say "unconfirmed, and here is why"; a default nobody looked up is not confirmed because its line looks innocent.
4. **The skeptic answers `same`/`different`; scripts decide the state.** Comparing free-form defaults by text is fragile; the shape of the cited location is not. A `same` at a fallback read confirms nothing, which is exactly the Spike 2 refuter that was wrong.
5. **Unlisted defaults are confirmations with a quoted claim.** It mirrors #37's missing-gate rule, lets the skeptic catch a default the investigator did not list, and is the only way the frozen Celery findings, which have no preconditions, can be measured (AC-6).
6. **`upheld` on an unconfirmed default becomes `inconclusive`, on every path including reuse.** Nothing was shown false, so not `narrowed`; and a ledger written before this ticket must not carry an `upheld` past it.
7. **Confirmation is derived at render time from stored facts.** As with confidence (#56 Decision 1): the stored copies are caches for readers of the files, and `report.py` cannot show a confirmation inconsistent with the check it renders.
8. **`unconfirmed_default` sorts before `non_default_setting`** (§8).
9. **Investigator `default_ref` stays repository-only; dependency defaults are cited by the skeptic** (§10).
10. **Two states, six bases.** AC-1 asks for two states; the basis keeps "contradicted", "stated at a fallback read" and "not checked" apart, which a reader acts on differently and the dogfood measure needs.
11. **The no-execution test is static and dynamic.** The static allowlist catches a new process call in review; the trapped fixture catches an indirect import or a package-manager call no AST pattern names.
12. **`VALIDATION_RULES` does not change.** No rule is tightened; every scan re-validates, so old files gain confirmations without a re-investigation.

## 19. Open design questions

1. **`check.confirmations` and the contract keys.** This design writes `check.confirmations`, adds `confirmations` to `verify.VERDICT_KEYS`, and changes #37's `claim_hash`, `cited_files` and ledger `files` (§7.2). #56 §7.1 should reserve `check.confirmations`; #37's spec should name the three changes. Nothing breaks if they do not, but both specs would then understate their contracts. Owners: #56, #37.
2. **Defaults with no settings layer.** `process.env.TIMEOUT_MS ?? 30000` is a fallback read with nowhere else to register the value, unless the project ships an `.env` or a chart. Under §3.2 such a default can be confirmed only by a check citing another registration, so a finding resting on it can never be `upheld`. That is deliberate (the escape hatch would be the judgement Spike 2 found unreliable), but it caps every such finding at `medium`. `counts.defaults`' `call_site_fallback` share in dogfood runs decides whether a narrower exception is worth designing (e.g. a check that cites the absence of any configuration file for the setting). Owner: this ticket, after dogfood.
3. **Interaction with #37 AC-12.** §7.1 turns some `upheld` verdicts into `inconclusive`, which #37 §13 counts as not reaching the same class. If the frozen run (§13.2) shows that this moves #37 below 15 of 21 because correct findings rest on defaults the skeptic did not confirm, the fix is in the skeptic's prompt, not in relaxing §7.1; the PR reports the findings affected so the maintainer can see it. Owner: #37 and this ticket together.
4. **Celery-style settings names.** A frozen finding states `always_retry`, the registry spells `backend_always_retry` inside a namespace, and the full name is `result_backend_always_retry`. The rule matches the name the location is checked for, so a skeptic must give the name the read uses; the prompt says so. Whether names should be normalised (prefix stripping, case styles) is left until a second repository (#59) shows a miss.
