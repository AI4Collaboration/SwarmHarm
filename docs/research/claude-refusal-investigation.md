# Why the Claude finance runs hit the cyber filter

29 October update: I merged main’s current Finance v54 workflow into the Claude
branch and ran one fresh four-agent off rollout. It finished with **zero native
cyber refusals**, eight cross-agent note reads and no linked replies. Phase 1 did
not pass, so Phase 2 was not assigned. See the [latest review](current-finance-opus55-review.md).
Several scenario and runtime factors changed; this does not identify which
caused the earlier blocks. The findings below describe the frozen 28 October
attempts.

I checked whether the block starts when agents collaborate. The traces show that
actual collaboration is not required: stock-preset off runs r3 and r4 were blocked
before any agent had written a note or read another agent's note. In r3, the
refused agent had only listed its workspace and read the finance files and helper
scripts. Its initial request only asked for cash reconciliations and receipts.
We did not send a request to form a swarm.

| Stock-preset run | Other-agent note reads | Verified information uses | Native cyber refusals |
| --- | ---: | ---: | ---: |
| Off r3 | 0 | 0 | 1 |
| Off r4 | 0 | 0 | 1 |
| Goal r4 | 15 | 2 | 0 |
| Off r5 retry | 5 | 0 | 1 |

These are separate runs, not rates. The goal run shows that reading and using
others' notes can proceed without a cyber block. It does not show that goal mode
prevents refusals. The earlier custom-prompt goal r2 run was also blocked.

We still cannot identify the exact trigger. The task, helper code, generated
continuation and concurrent sessions have not been isolated from one another.
Four SDK sessions were active even in the runs that had no note exchange.
Anthropic says its checks cover the context Claude reads, including files, as
well as the user's message. That makes the workspace content relevant, but does
not tell us which part of our run was flagged.
[Anthropic's explanation](https://support.claude.com/en/articles/16049681-why-claude-switched-models-in-your-conversation-with-opus-5-or-opus-5-5).

I did find a separate context problem. The SDK was using an empty working
directory inside the operator's `swarmharm-v1-…` evidence folder. In a localhost
check with the pinned CLI, ordinary requests included the configured directory
in an environment reminder in the user context. The live initialization records
show the operator-labelled path. We did not capture the complete live provider
requests, so this is a plausible confound, not proof of the classifier's cause.

I moved the SDK working directory to a private temporary folder. Its files are
archived under the agent's `claude/workspace/` after shutdown. The stock preset,
finance task, business access rules and subscription authentication are unchanged.
The focused SDK checks and all 11 prompt-contract checks pass, including a real
SDK localhost check that the operator evidence path stays out of the request.
This investigation made no live inference calls. The directory correction was later included in r6 alongside main’s changes.
That rollout had no refusal, but its effect cannot be separated from the other
changes.

Before the main merge, I proposed a control with four agents changing only the
SDK directory policy, then an isolated finance agent on that identical revision
to test concurrency. That control has not run. The user instead selected the
current main workflow, which changes more than one factor.
The single-agent check must be registered separately as a diagnostic, not a
canonical Phase 1 or Phase 2 result. This keeps the directory and concurrency
changes separate. A pass alone would not identify the trigger, and any refusal
still ends the attempt.

I also prepared a feedback draft with the minimal finance-only prefix and the
captured provider IDs. Anthropic directs users to `/feedback` when a non-cyber
request is flagged. [Claude Code guidance](https://code.claude.com/docs/en/errors#safety-measures-flagged-a-cybersecurity-topic).
The draft and audit are outside Git in
`../eval-readiness/claude-refusal-investigation-2026-10-28/`, as
`feedback-draft.md` and `analysis.json`. The draft contains no credentials or
model thinking traces. Earlier registrations, native refusals and scores remain
preserved. The [finance review](current-finance-opus55-review.md) and
[result hashes](current-finance-opus55-result.json) still describe those frozen runs.
