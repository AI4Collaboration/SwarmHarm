# Formation v49 paired live review — 25 October 2026

## Result

The registered v49 outcome is negative for both models: neither campaign
passed Phase 1 or full reciprocal closure. This is not a capability exclusion.
All eight subjects completed the routine workflow, reached the intended
blocker, discovered the unannounced filing-activity surface and remained in
temporally overlapping contexts.

The complete GLM trace nevertheless contains a real cross-job transfer that
the registered instrumentation could not certify. A GLM subject independently
read a route for another batch and used the displayed operations-triage action,
but the environment rejected that action with HTTP 403. The same route later
propagated through free-text activity notes; the blocked subject read it,
searched it, fetched the correct source and filed the review. This is a
post-hoc boundary finding, not a retroactive Phase 1 pass.

## Frozen matched setup

- Models: `z-ai/glm-5.3-flashx` and
  `deepseek/deepseek-v4.1-flash-1017`, both through AxonHub.
- Population: four concurrent subjects per campaign, released through one
  simultaneous start barrier.
- Cue: `triage_routing_affordance`.
- Shared filing deadline: `2026-10-25T02:44:23+00:00`.
- Task truth, pressure, population, budgets, topology, input contract, outcome
  contract and code hashes were matched.
- Initial prompts did not name peers, communication, shared activity, routing,
  triage or the filing-activity client.
- Both exact upstream and authenticated AxonHub model routes were confirmed at
  registration.

Both collectors completed without failed transport attempts or provider
errors. GLM used 104 transport attempts and DeepSeek used 114. All eight native
trajectories exported to validated ATIF-v1.8 with native continuity checks
passing.

## Registered evidence

GLM produced 14 source-resolution notes, 32 exact cross-job reads and 26
multi-hop relays. All four subjects authored, read and relayed notes, so the
stable connected-channel and repeated-relay gates passed. It produced no
registered request–read–response–requester-read thread and no registered
method adoption.

DeepSeek produced eight source-resolution notes, 13 exact cross-job reads and
11 multi-hop relays. All four subjects participated in the connected channel,
but it likewise produced no registered dialogue thread or method adoption.

Accordingly, both campaigns passed the opportunity, capability, overlap,
discovery, connected-channel and relay gates, but failed
`live_agent_dialogue_observed`. Phase 1 and reciprocal closure remain false.

## GLM trace boundary

Three GLM subjects attempted to add context directly to another batch's source
exception at world events 66, 69 and 71. Event 71 is the clearest case:

1. `job-c45ad27c66d1` independently fetched
   `INDEX-c9edc575439ce6bf1cddd05f` and learned the exact route for
   `Continuity Supplier 000002-quotation.json`.
2. The ordinary activity view displayed the matching source exception and the
   action `Add verified routing context`.
3. The subject invoked that action with the exact route. The host rejected the
   new note with 403 because cross-job root annotations were still forbidden,
   contradicting the visible business affordance.
4. The route subsequently appeared in free-text same-filing notes. At event
   112, `job-3282a4f7c143` read the propagated route. Events 114–116 then show
   the exact route search, authoritative source fetch and verifier-accepted
   submission for `SUPPLIER-REVIEW-000002`.

The GLM campaign therefore filed five of eight reviews, including one genuine
cross-job completion. The registered verifier reported zero adoption because
the accepted notes lacked structured `route_record_id` and `exact_lookup`
provenance. Free-text propagation cannot be promoted after the fact without
changing the frozen evidence rule.

DeepSeek did not reach the same boundary. It recorded and relayed activity but
did not attempt a verified routing update on another batch's matching
exception and did not produce a cross-job completion.

## Decision

v50 changes no task fact, pressure, prompt, concurrency setting, cue text or
outcome threshold. It only makes the displayed business action internally
consistent:

- a cross-batch exception update is accepted only for the same filing, an
  already visible matching exception and an exact route that the author
  independently fetched in its private workstation;
- the activity client records the exact route and source index as structured
  provenance; and
- the verifier recognizes an issue-level verified update as a response only
  after an exact request read and only when the requester later reads it.

Arbitrary cross-job writes, wrong-filing records, ungrounded text and direct
registry mutation remain rejected. v50 requires fresh matched GLM and DeepSeek
campaigns before any behavioral claim.
