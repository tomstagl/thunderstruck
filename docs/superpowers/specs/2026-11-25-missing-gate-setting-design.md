# Missing gate setting: a check can say a finding needs a non-default setting

**Requirements:** [#144](https://github.com/tomstagl/thunderstruck/issues/144). The problem, stories, scope and acceptance criteria (AC-n) are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-25-missing-gate-setting.md`.
**Extends:** `2026-10-03-finding-verification-design.md` §8.3 and §14 (#37). Nothing there changes meaning.
**Evidence:** `agents/thunderstruck-skeptic.md` ("Verdicts", rules 2 and 8, the output example); `scripts/verify.py` (`_decide`, `SETTING_KEYS`, `run_verdict`); `scripts/_common.py` (`skeptic_settings`, `finding_gate`, `MISSING_GATE_PHRASE`).

## 1. What is wrong

The verdict contract lets a `preconditions` claim carry a `setting` object, and only such a claim gates a finding. The shipped instructions say "the `setting` it needs" and never show the object. Two consequences:

- A skeptic that finds a gate writes the claim without the object. `_decide` keeps the claim and says nothing about the missing object, so the check reads as a plain narrowing.
- A skeptic that writes the object with a JSON scalar (`"default": false`) loses it: the value must be a string. #57 already normalises such scalars for `confirmations`; `setting` was left out.

## 2. The instructions (measured, not shipped)

**Not shipped** (maintainer, 2026-11-25; §8 decision 5). The text below was built at `e268b57` (pull request #148), measured (§7) and taken out again, because it produced false marks (§9). `agents/thunderstruck-skeptic.md` is unchanged, so AC-1 is not met. What follows describes what was measured.

`agents/thunderstruck-skeptic.md` changes in two places, and nowhere else.

**"Verdicts".** The paragraph on a failure that needs a setting changed gains the shape of the claim, as a JSON object of its own, and two sentences:

- A failure that still happens once the setting is changed is `narrowed`, never `refuted`; `holds` says what happens on that setting. This is #37 §14's rule, stated where the verdict is chosen.
- `setting` has four string keys: `setting` (the name the code reads), `default` (the registered value), `default_ref` (where it is registered, resolved like any evidence ref) and `value` (what the failure needs).

**Rule 2** names `setting` as the key a `preconditions` claim may carry.

The example uses an invented setting, `upload_keepalive`, in an invented file. It shares no setting name, file or wording with either benchmark set: an example that resembled a labelled finding would fit the set it is measured on.

The output example of the prompt's last section is unchanged. A second claim in it would change what every verdict looks like, not only a gating one.

## 3. A gate without a usable setting

In `_decide`, a kept `preconditions` claim always ends in one of two states:

| The claim's `setting` | Kept claim |
|---|---|
| An object with exactly the four keys, each a non-empty string after normalising, whose `default_ref` resolves | `setting`, as today |
| Anything else, absence included | `gate_problem`: one sentence naming why |

- **Normalising.** A `bool`, an `int` or a finite `float` in `default` or `value` becomes its `str()`, the rule `resolve_confirmations` applies. `setting` and `default_ref` must be strings. A key outside the four, or a missing one, is a problem.
- **`gate_problem`** is one of: `names no setting`; `setting needs the keys setting, default, default_ref, value, each a non-empty string`; or the resolver's own error for the `default_ref`.
- The same text goes to `ignored`, so it is also in the check's `reason`, as every other dropped part of a verdict is.
- A claim with a `gate_problem` never has a `setting`, so `skeptic_settings`, `finding_gate` and `run_verdict` need no change and cannot gate on it. A `preconditions` claim whose evidence does not resolve, or that does not quote the finding, is dropped before this point, as today.

A `preconditions` claim that refutes a precondition the finding lists gets the same treatment: without a setting it does not gate either, and the check says so.

`gate_problem` is stored under `check.refuted_claims[]`, which model output cannot write (`REFUTED_CLAIM_KEYS` has no such key, so a verdict that contains one has that claim dropped). A check stored in the ledger before this change has no `gate_problem` and renders as it did.

## 4. Rendering

`report.md` and the HTML report add one sentence to the claim's line: "The check says a setting must be changed but names none it can use (<gate_problem>), so this finding is not gated." The text goes through `md.text` and `textContent`. `report.json` passes it through with the claim. `index.json` and the guardrail do not carry claims and do not change.

## 5. Degradation

Nothing new can fail a scan. A malformed `setting` of any JSON type ends in a `gate_problem`.

## 6. Tests

- Measured version only, removed with §2: the prompt's example object is read from the agent file, put into a verdict on the fixture (with its file created there), settled by the real `verify.py`, and must gate the finding: status `narrowed`, `finding_gate` `non_default_setting`, `run_verdict` `upheld_but_gated` (AC-1).
- Measured version only, removed with §2: the example's words appear in no frozen finding or bundle of either set. The holdout is compared by its `scan/` files only; no label is read.
- `_decide`, parametrised over `setting`: absent, `null`, a string, a list, a missing key, an extra key, an empty string, a `default_ref` that does not resolve; each keeps the claim, sets `gate_problem`, names it in `reason`, and gates nothing (AC-2). A scalar `default` and `value` are normalised and gate.
- A verdict that writes `gate_problem` itself has that claim dropped.
- `report.md` and the HTML report show the sentence, inert.

## 7. Measurement (AC-3, AC-4, AC-5)

**Predicted before any run** (recorded in this file's first commit):

1. From the surviving raw output of the last recorded run: supplying the setting moves one finding to the right class and one to the wrong one, net 0 on the same-class count.
2. The mean same-class count on Celery after the change is within 1 of the mean before it, and below 15 of 21. The change is therefore **not** expected to meet #54's AC-2.
3. At least one verdict of the three runs after the change is `upheld_but_gated`, and the number of `preconditions` claims that name a setting rises from near 0.
4. No direction is predicted for the holdout.

**Arms.** *Before* is the skeptic prompt of `main` at the release the branch starts from. *After* differs from it in `agents/thunderstruck-skeptic.md` alone. Both arms' saved skeptic output is settled with the same `verify.py`, the one of this branch, so a difference is the prompt's.

**Runs.** Three per arm and per set: Celery (21 findings) and the holdout (15). A run is one fresh headless Claude Code session that carries out step 4b of the scan on `verify.py prepare --frozen <set>/scan`, with the plugin under test installed as a local-directory marketplace, one skeptic per finding on the default skeptic model, at most four at a time, none re-spawned, `checks/` deleted first. Each run is named by its session id and start time (a frozen run's `generated_at` is the frozen scan's, so every run of a set shares it). A run whose session did not spawn one skeptic per finding is reported as that and not scored.

**Reported per run:** same-class count of the set (a finding without a verdict counts as not agreeing), correct refuted, `high` above deserved confidence, gated verdicts, `preconditions` claims, and how many name a usable setting. Per arm: the mean, the range and the 95% Wilson interval of the mean. For the holdout, totals only, without `--reveal`.

**`high` above deserved.** A run's confidence is `_common.effective_confidence(claim, status)` with the frozen finding's claimed confidence, the function `report.py` uses.

## 8. Decisions

1. **Show the object, do not relax the contract.** Accepting a setting named in prose would let a script guess a gate from a sentence, which the governing rule forbids.
2. **Name the problem on the claim, not as a new status.** A status is settled in one place and feeds confidence; a missing object is a defect of the output, not a verdict.
3. **No repair round.** Skeptics get none (#37).
4. **`VERIFY_BY_DEFAULT` is out of scope here** and stays as measured.
5. **The instructions of §2 are not shipped; §3 and §4 are** (maintainer, 2026-11-25). In three of three runs they marked a correct default-path finding as needing a setting changed, and a false positive on correct code is a worse bug than a missed detection. Without them a skeptic rarely writes the object (0 of 12 claims), so almost no check gates a finding; §3 makes that visible in the report.

## 9. Open design questions

- **A setting that belongs to a refuted detail marks the whole finding.** #37 §14 gates a narrowed finding on any `preconditions` claim with a setting. Measured on Celery, that marked FR-014 although the failure happens on defaults (`docs/calibration/verification.md`, "Missing gate setting"). Candidates: tell the skeptic that the claim is about the failure and not a detail; or gate only when every kept refuted claim is a gate, as `run_verdict` does. The second can be read off the recorded figures: it leaves one of the nine Celery marks (FR-003) and drops five right ones with the three wrong. Neither is chosen, and either needs its own prediction and runs. §2 ships only once this is settled.
