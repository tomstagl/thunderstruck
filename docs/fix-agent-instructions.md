# Fixing a finding

These instructions are for whoever fixes a failure that a ticket describes: a person, or an agent in any environment. They assume no particular tool. Do not rely on any plugin, hook or tool your environment may not have.

A ticket made from a finding states a hypothesis about how the code fails. Your job is to fix that failure without breaking what the code does well by accident, and to say exactly what you did and did not check.

## What you need before you start

You need the ticket, the repository at the commit the ticket names, and a way to run its tests.

Stop and ask when an input is missing. Name the input and wait for it; do not guess it, and do not start with only part of what you need.

## Before you change anything

1. Re-check the code against the ticket. Open the lines the ticket cites at the commit it names and confirm that they still say what the ticket claims. If they do not, stop and say so.
2. Read the callers. Find every place that calls the code you will change, and read how each one handles its result, including the failure path.
3. Read the numbers. Every figure the ticket gives, such as a timeout, a duration or a count, comes from a constant or a setting in the code. Read where it is defined and what else uses it, and correct the ticket's figure if it is wrong.
4. Read the not-checked items. The ticket lists what its author did not check and how to check each one. Resolve each by reading or running it before you rely on the claim, and say which you could not resolve.
5. Write down the implicit guarantees. List what the current code gives by accident, for example a lock that also makes sure only one caller fetches, and decide for each whether your change keeps it, replaces it or drops it on purpose.
6. Get a human decision when caller-visible behaviour changes. If your fix changes what a caller can see, such as a result, an error, an ordering, a timing or an event, describe the options and ask a person to choose. Do not choose for them.

## Change the code

7. Write a failing test first. Make it reproduce the failure the ticket describes, run it, and see it fail for the reason the ticket gives and not for a reason of the test setup.
8. Make the smallest change that makes the test pass. Stay inside the lines the ticket cites where you can, and leave refactoring and unrelated cleanup for another change.
9. Run the same test again, unchanged, and then the tests next to the code you changed. If the test needs editing to pass, either the test or the diagnosis was wrong: say so and go back.
10. Run the integration suites when your environment supports it. If it does not, say which suites you could not run and why.

## Account for the change

11. Account for what the fix removed. State which implicit guarantees from step 5 the change no longer gives, and what now covers each one, if anything.
12. Account for what the fix does not fix. Name the other callers, paths and conditions of the same failure that your change leaves as they were, for example a second path with the same flaw, or a total outage where the ticket describes a partial one.

## Report

Report the real commands you ran and the real results they printed. Paste the output, or the part of it that matters, and say which results you read and which you inferred.

Never invent a result. If you did not run something, say that you did not run it.

Never push. Leave the change, with your report, for a person to review.

Hand back, in this order: the failing test and where it lives; the change; the implicit guarantees and what became of each; what the fix does not fix; the commands you ran with their results; and any question that is still waiting for a person.
