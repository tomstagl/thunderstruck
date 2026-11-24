# Social variants — thunderstruck 0.13.0

Post: https://github.com/tomstagl/thunderstruck (README and CHANGELOG 0.13.0, 2026-11-11)
Facts used: (README) "Hotspot analysis tells you where risk concentrates; thunderstruck tells you why that code is fragile: the concrete failure mode, what triggers it, what amplifies it, what keeps it failing." Scripts rank fracture points and validate every claim; subagents read the code and its history. Churn × complexity × missing stability patterns. Every evidence ref resolves to a real file:line and commit. 23 stability patterns drawn from Nygard's *Release It!*, the Amazon Builders' Library, the Google SRE book and the metastable-failure literature (catalog cites SRE book ch. 21, 22, 24). (CHANGELOG 0.13.0) a read-only skeptic subagent tries to refute each finding; verdicts upheld, narrowed, refuted, inconclusive; `--verify` is opt-in. README: "Not a fixer." License MIT (marketplace.json). No numbers beyond the pattern count.

Added (README, service context): incoming and outgoing dependencies come from a catalog command the user approves; without one a scan sees the repository only.

Status: draft. Nothing is posted. Handles are blank until verified.

## X

Main post (265 of 280 characters, link counted as 23):

```
Hotspot tools show where code is risky. thunderstruck shows how it breaks: trigger, amplifier, what keeps it failing.

Connect your service catalog and it sees who calls you and who you call.

Claude Code plugin, open source
github.com/tomstagl/thunderstruck
#resilience #SRE
```

Attach: the 16:9 video.

Reply to it, for credits (187 of 280):

```
The stability patterns behind it come from Michael Nygard's Release It! and the Google SRE book (Betsy Beyer, Chris Jones, Jennifer Petoff, Niall Murphy). Thank you for writing them down.
```

Tags, to add only once verified on x.com: Nygard `@____`, Beyer `@____`, Jones `@____`, Petoff `@____`, Murphy `@niallm` (one source only, check it).

Why this angle: the first sentence names the gap every hotspot-tool user already feels. Engagement that shows it worked: replies asking what a finding looks like, and link clicks from the video.

## LinkedIn

Attach: the 1:1 video.

```
Have you ever looked at a hotspot report and thought: fine, this file changes a lot. But how will it actually break?

That gap is why I built thunderstruck, a Claude Code plugin that finds where a repository is most likely to fail in production.

1. Scripts rank the fracture points: churn × complexity × missing stability patterns (timeouts, capped backoff with jitter, Retry-After, idempotent jobs).
2. Subagents read the flagged code and its git history and write down the failure: what triggers it, what amplifies it, what keeps it failing.
3. Every claim must resolve to a real file:line and commit, or it does not reach the report.

It works best with your service catalog connected. You point it at a command that returns each service's incoming and outgoing dependencies (Backstage relations, for example), and it lists who calls you and who you call next to every flagged file. Without that access it reads the repository only and cannot see the neighbours.

New in 0.13.0: an optional skeptic agent tries to refute each finding before you see it. Upheld, narrowed or refuted.

It does not fix anything. It tells you where to look, why, and how to prove it.

The patterns come from Michael Nygard's Release It! and the Google SRE book, edited by Betsy Beyer, Chris Jones, Jennifer Petoff and Niall Richard Murphy. [tag them in the LinkedIn editor]

Open source, MIT: github.com/tomstagl/thunderstruck

P.S. Try it on the repo you are least comfortable deploying on a Friday 😃

#resilience #SRE #ClaudeCode
```

Why this angle: the opening question is the reader's own thought, and the three steps show how it works without a demo. Engagement that shows it worked: comments naming the repo they would try it on, and profile visits from the tagged authors' networks.
