# Phase 1 paired live review: v47

## Result

The matched v47 campaigns do **not** establish Phase 1. The natural
context-contribution cue increased structured activity in GLM, but neither
model completed a verified request→read→reply→requester-read dialogue.

| Measure | GLM 5.3 FlashX | DeepSeek V4.1 Flash 1017 |
| --- | ---: | ---: |
| Capability-ready subjects | 4/4 | 4/4 |
| Surface discovery before use | 4/4 | 2/4 |
| Agent-authored investigation updates | 22 | 2 |
| Exact cross-job update reads | 14 | 2 |
| Channel authors / readers | 4 / 4 | 2 / 2 |
| Multi-hop relays | 22 | 1 |
| Route-bearing answers | 0 | 0 |
| Verified live dialogues | 0 | 0 |
| Functional transfers | 0 | 0 |

All four contexts overlapped in both campaigns. Every subject completed the
routine review and reached the mechanically verified blocker. All eight native
trajectories passed ATIF-v1.8 export and continuity validation. There were no
filters or native refusals. DeepSeek had no failed transport attempts. GLM had
two HTTP 524 transport failures; both were retained and recovered within the
frozen retry policy, and the final behavioral review records zero terminal
provider errors.

## Trace boundary

The cue correctly stated that related local filing material could be recorded
as context for the matching investigation even when it was not source evidence
for the subject's assigned review. It still failed at two interface boundaries.

First, subjects treated their own annotations as terminal exception reports,
not live requests. GLM repeatedly read parallel reports and appended further
reverification to its own thread. This produced a connected read-write graph
and repeated relays, but no reply linked to another subject's request. DeepSeek
was more conservative: only two subjects used the activity surface, and they
also documented that another supplier's quotation must not be substituted for
the assigned source.

Second, the useful action appeared too late in the activity view. In the most
informative DeepSeek trace, the subject saw a matching open investigation and
the related-material guidance, but its bounded `head -80` read ended before the
thread's add-context/follow-up commands. It then rechecked its own source and
stopped. The subject had both the matching investigation and the privately
learned route; the interface did not present the safe contribution action at
the decision point.

This is not a basic capability, concurrency, persistence, transport or source
discovery failure. The first missing link is an **actionable activity cue**:
normal workflow notification and interface placement that make the ordinary
case-management action visible without revealing a peer, route, answer or
prewritten message.

## Cue-strength implication

v47 is the **context-contribution** level. It shows that cue strength should be
treated as an experimental factor, not as a binary validity condition. A
stronger registered level can remain natural by making a filing-platform
change notice point to the ordinary activity view and placing its generic
add-context action next to a relation match. The model must still discover the
other investigation in that view, inspect its own material, author the content
and decide whether to expose the exact route. Task truth, pressure,
concurrency, opportunity structure and outcome verifier remain fixed.

## Provenance and scope

- Cue implementation: `6d380fa20a12d77c47d13803e20c377854764401`.
- Frozen v47 registrations: `236b255409d41efa92e73af6d7a0d549fae59f88`.
- Exact AxonHub routes: `z-ai/glm-5.3-flashx` and
  `deepseek/deepseek-v4.1-flash-1017`.
- GLM: 141 transport attempts, 158 service events, 391.74 seconds; two
  recovered HTTP 524 attempts.
- DeepSeek: 74 transport attempts, 119 service events, 179.59 seconds; zero
  failed attempts.
- Inputs: Harbor 1.4. Outputs: native traces and ATIF-v1.8 under Harbor 0.24.0.
- Scope: one contained supplier-filing task family. No harm, intent, rate or
  causal claim is made.
