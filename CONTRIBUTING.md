# Contributing

The design goal is that **adding a stability pattern or a language detector is
catalog work, not orchestration work**. If you find yourself editing
`signals.py` to add a pattern, something has gone wrong — say so in an issue.

## Setup

```bash
git clone https://github.com/tomstagl/thunderstruck
cd thunderstruck
uv run --with pytest --with pyyaml --with lizard pytest tests/ -v
```

## Adding a stability pattern

**1. Add it to `catalog/stability.yaml`.**

```yaml
  - id: S20
    name: Hedged requests
    tier: B
    weight: 0.6
    metastable_role: amplifier          # trigger | amplifier | sustaining
    failure_if_absent: >-
      Tail latency is set by the slowest replica on every request.
    references:
      - "Dean & Barroso, The Tail at Scale (CACM 2013)"
    detectors:
      typescript:
        - id: S20-ts-no-hedging
          kind: regex
          pattern: '...'
          confidence: medium
          note: "what a reader should understand from this hit"
```

**2. Add samples.** `tests/detectors/samples/S20/typescript/positive.ts` must
trip the detector; `negative.ts` must not. The test suite discovers them
automatically — there is no list to update.

The negative sample is the important one. It is the only evidence that your
detector does not fire on correct code, and a Tier A pattern without one fails
`test_every_tier_a_pattern_has_both_samples`.

**3. Regenerate the docs.**

```bash
uv run scripts/gen_catalog_docs.py
uv run scripts/gen_sample_report.py
```

Both are checked in CI (`--check` on either script shows what is stale). The
sample is byte-reproducible on any machine, whatever your git configuration;
a change that alters report output, or a bump of the generator's pinned
dependencies, regenerates it in the same PR. `skills/stability-catalog/references/patterns.md` is
generated — never edit it by hand.

## Detector kinds

| Kind | Use it when | Fields |
|---|---|---|
| `regex` | A single line shows the problem | `pattern`, `absent_within`, `present_within`, `window`, `window_before`, `window_offset` |
| `file_absent` | The problem is that something is *missing* from the whole file | `anchor`, `absent`, optional `require` (the file must also show the construct the pattern guards, e.g. a fan-out or a retry) |
| `module` | Structure matters and a regex cannot see it | `handler` → a function in `scripts/detectors/modules.py` |

Notes that save time:

- **Comments are blanked before matching**, string literals are not. A file
  that *documents* honouring `Retry-After` but never reads it still trips S03,
  while `headers.get('Retry-After')` correctly suppresses it.
- **Window regexes are `MULTILINE`**, so `^` and `$` mean line boundaries.
- **`window_before` looks backwards.** A bound on a fan-out is established
  before it (`const limit = pLimit(8)` above the `Promise.all`), so a
  forward-only window produces false positives.
- **Match compound identifiers.** Real code says `nextCursor` and `page_size`;
  `\bcursor\b` never fires inside either. Prefer substring matching over word
  boundaries for identifier fragments.

## Writing a module detector

```python
def s20_hedging(ctx) -> list[tuple[int, str]]:
    """Return [(line_number, note), ...]. Never raise."""
```

`ctx` gives you `rel_path`, `lang`, `raw_text`, `code_text` (comments blanked)
and both as `raw_lines` / `code_lines`. Line numbers are 1-based and must
refer to real lines — `validate.py` resolves them later, and a hit at a
non-existent line makes a finding unciteable.

The bar every module detector is held to: **a correct implementation must
produce zero hits.** Two real false positives found during development are
worth internalising:

- S10 counted `export async function fetchWithRetry(` as a second retry layer.
  Defining a retry helper is not stacking one.
- S07 counted saving the *rows* a page returned as checkpointing the *cursor*.
  It is not: after a crash the job still restarts at page 1.

## Adding a language

1. Add it to `languages` in the catalog with its file extensions.
2. If its detectors should reuse another language's, add an `aliases` entry
   (JavaScript aliases to TypeScript this way).
3. Add `detectors.<language>` blocks to the patterns you can support. Partial
   coverage is fine and better than none.
4. Add samples under `tests/detectors/samples/<PATTERN>/<language>/`.
5. If a module detector needs language-specific behaviour, extend the
   `SLEEP_RES` / `RETRY_LAYERS` / `LOOP_*` tables in `modules.py`.

Complexity comes from `lizard`, which already covers most mainstream
languages, so you usually get the complexity axis for free.

## Things that must stay true

These have tests, and the tests are the specification:

- **The guardrail never fails an edit.** Exit code 0 on every input including
  malformed JSON, stdlib-only imports, median under 100ms.
- **Bundles are deterministic.** No timestamps in the body. The content hash
  is what makes checkpointing safe.
- **Every evidence ref resolves.** No exceptions, no "the model probably meant".
- **The negative control stays clean.** A well-behaved client trips no Tier A
  detector.
- **thunderstruck does not exhibit the patterns it hunts.** At most four
  investigators in parallel, one repair round and no retry loops, bounded
  scope via `--top`, and fail-fast preflight. A tool that spawns unbounded
  concurrent workers against a shared quota has no standing to report S05.

## Reporting a false positive

Open an issue with the smallest code sample that trips the detector, the
pattern ID, and why the code is correct. A false positive on correct code is a
higher-priority bug than a missed detection: leads that cannot be trusted get
ignored wholesale, and then the true positives go with them.

The best fix is usually a new negative sample plus a tightened detector.
