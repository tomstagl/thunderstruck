# Reviewing a fix

A fix for a failure that a ticket describes is reviewed through four lenses. Each lens is run by its own reviewer, a person or an agent in any environment, and each reviewer works alone from the ticket and the change. Run each lens in a separate session. Do not rely on any plugin, hook or tool your environment may not have.

## What you need before you start

You need the ticket, the diff of the fix, and the repository at the commit the diff applies to.

If an input is missing, say which one in your report and stop; do not guess it.

## Rules for every reviewer

Be read-only: change no file, run nothing that changes state, and fix nothing yourself, however small the fix.

Do not ask for the implementer's conclusions, and ignore them if they reach you: judge the change against the ticket and the code alone.

Report what you saw. Label anything you inferred as inference, and say what you could not check.

## Lens 1: State and concurrency

Look for state that the change leaves wrong. Ask what happens when two callers arrive at once, when the same call is repeated, when a step fails halfway, and when a value changes after it was checked. Check every sibling path that does the same work: a guarantee that one path had by accident, such as a lock that also stopped duplicate work, may be missing on another.

## Lens 2: Callers and behaviour change

Find every caller of the changed code and read how each one handles the result, including the failure path. Ask what a caller can now see that it could not see before, or can no longer see: a result, an error, an ordering, a timing, an event. Check each mapping that the ticket or the change relies on against the code, as the code is written and not as remembered.

## Lens 3: Test and conventions

Run the new test without the fix and confirm that it fails for the reason the ticket gives and not for a reason of the test setup. Do this on a separate clean checkout of the commit the diff applies to, never by removing the fix from the working tree you were given; if you cannot, say so and judge by reading whether it would fail. Ask what a mock or a stub in the test cannot show, and whether an integration suite covers it. Check the change against the repository's own conventions for naming, errors, logging and structure, and against the tests next to it.

## Lens 4: Whole-finding coverage

Read the finding as a whole and ask whether the change covers all of it: every path, caller and condition it names, the numbers it gives, the implicit guarantees at risk and the items marked as not checked. Check that what the implementer says the fix leaves unfixed is accurate and complete, and that no claim in the ticket was left unresolved.

## Report format

All four lenses report in this one format. Start with the lens, then give one entry per finding, then a verdict.

Each entry has these parts:

- Severity: blocker, major or minor. A blocker leaves the failure in place or breaks behaviour a caller depends on. A major finding would be caught late. A minor finding is a matter of care or convention.
- Location: the file and line, or the step of the ticket.
- What is wrong: one or two sentences.
- Evidence: the code you read, or the command you ran and what it printed.
- Suggested fix: optional, one or two sentences. You do not make the fix.

End with a verdict of approve, approve with changes, or reject, and a list of what you could not check. If you found nothing, say so and list what you did check.
