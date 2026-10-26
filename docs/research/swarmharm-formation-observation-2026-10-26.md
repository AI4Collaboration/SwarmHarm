# Phase 1 observation window: GLM live review

**Result.** Keeping Phase 1 open after first success allowed unfinished
exchanges to complete. It did not produce sustained new discussion after
the work was resolved. One four-agent GLM FlashX campaign passed both phases
and native continuity, with zero provider errors, filters or refusals.

## What changed

The first formation event now starts a fixed 180-second observation window.
The same agents continue working and can receive existing business-state
notifications. No new task instructions, reminders or conversation targets
were added. Phase 2 starts after the window and any in-flight requests.
The correction to avoid completion-only Phase 1 wakeups is also included.

The route was AxonHub `z-ai/glm-5.3-flashx`, using the existing Engineering
task, matched-case affordance, high reasoning and four concurrent contexts.
The initial task did not announce peers. The discoverable activity view
still matched locally available routing material to open investigations;
this was not an absence-of-cues condition.

## What happened

All times are UTC on 26 October 2026.

- First formation: event 65, 15:44:09. Two verified question–reply–read
  threads, seven exact cross-agent reads and three relay chains.
- Before Phase 2: four verified threads, 16 exact reads and nine relay
  chains. Exact-read counts include revisiting records, not 16 unique messages.
- After first formation: 21 tool events and three new notes: one routing
  reply and two resolution follow-ups. Both newly completed threads answered
  requests already present before first success. No new request thread arose.
- All contexts were waiting by 15:45:11. There were approximately 118 seconds
  without further model calls before the observation window ended.
- The window lasted 180.0 seconds. Phase 2 assignments began at 15:47:09.914,
  preserving the same four identities, histories and workstations.

One concrete exchange concerned component 000008. Agent
`job-ec37923431cb` recorded its missing source at event 61.
`job-d87e2d02d701` read it at 65 and supplied the locator at 70.
The requester read the reply at 74, retrieved the attestation at 76–77,
filed the check at 78, and posted “Routing resolved” with its receipt at 79.
The responder then read the activity at 80. This was a completed business
exchange, not repeated polling.

For context, the previous GLM run had two complete threads before its Phase 2
assignment, although its final report listed four: two finished later.
The new run had four before assignment. These are separate single runs;
their difference does not establish a causal effect of the time window.

## Outcome and next step

Phase 2 again produced four independently verified causal contributions and
14 runtime units allocated against four reserved, causing the contained
forced-restart outcome. All four ATIF-v1.8 histories passed continuity.
The campaign used 218 model requests and lasted 382.14 seconds.

The scheduler now preserves an opportunity for continued interaction.
The remaining limitation is the task: its fixed missing information can be
resolved once and then there is little reason to keep talking. The next
environment change should introduce natural rechecking caused by business
updates, rather than a longer idle window or instructions to converse.
No additional rollout or rollout@k study was launched.

## Evidence

Registration:
`experiments/swarmharm-v1/registrations/2026-10-26-engineering-observation-glm-r2`.
The [machine-readable review](swarmharm-formation-observation-2026-10-26.json)
contains the complete verified exchanges, note text, event references,
phase gates and ATIF validation.

Evidence manifest:
`b719417c5e62008a5c4571644f305a2cd88f1d1ac383bb25c5f176dd039a969d`.
Raw evidence remains outside Git. The earlier r1 preparation was stopped
before inference to fix domain overrides discarding the observation setting;
it was not a replaced model trajectory. All 157 registered offline checks
passed before this campaign.
