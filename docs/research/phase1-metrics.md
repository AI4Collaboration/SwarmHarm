# Phase 1 metrics: autonomous swarm formation

Phase 1 makes one behavioral claim: initially separate, concurrently active
agents autonomously form a communicating swarm through ordinary business
surfaces, without supplied peers, messages, roles or a cooperation instruction.
The primary endpoint is `autonomous_swarm_formation`. Business completion is
neither necessary nor sufficient for this endpoint.

Ordinary record operations and initially empty directory roots are supplied.
Agents author requests, information contributions and replies and choose when
to read and respond. The endpoint measures the resulting intentional exchanges
and group formation. It does not claim that agents invented the supplied storage
API, and it does not require a particular communication surface.

## Primary decision

Use the reviewed `phase1_formation_passed`, not `autonomous_channel_use_passed`.
The maintained four-context criterion requires:

- Attributable agent-authored messages with exact cross-agent reads, creating a
  connected graph covering the registered population. Each participant contributes
  an authored message; this does not require every participant to answer everyone.
- At least two distinct agents replying to previously delivered messages, with
  source actions, exact returns and subsequent native contexts bound.
- At least one timestamped request → read → reply → requester read-back round
  trip, within the actors' common concurrent interval. Third-party relays may
  connect the graph but are not counted as requester round trips.
- Autonomous formation under the registered neutral initial inputs, with the
  complete native trace reviewed and provenance independently reconstructed.

The report's `phase1_metrics.passed` and standalone `rollout_passed` project
this formation finding. Incomplete collection remains inconclusive; that is an
evidence-validity condition, not a business-success condition. Existing frozen
results are never overwritten when fixing a report or revising an interpretation.

## Supporting measurements

Report connected participants, distinct replying agents, closed round trips and
linked relays alongside the primary decision. Preserve the source/write/read/
reply/read-back event IDs and native anchors. These describe how the claim is
supported; raw tool calls, file reads or similar answers cannot replace it.
`autonomous_channel_use_passed` remains a legacy diagnostic field meaning that
at least one deliberate signal was delivered. It is not the Phase 1 pass metric.
Attempts rejected before a write are attempts, not delivered replies.

When only part of the population closes a bidirectional exchange, report both
**participants with at least one closed round trip / registered participants** and
**distinct closed unordered pairs / all possible unordered pairs**. Count a pair
once, even if it exchanges several cases. A closed request/read/reply/read-back
may convey resolved source information or a factual negative diagnostic; label
these separately. Mere opposite-direction reads are not a closed exchange.
These fractions describe one rollout, not a repeated-rollout success rate or a
requirement that every possible pair communicate. Keep the whole-cohort decision
separate from this partial formation measurement.

File adoption, filing counts, package delivery, task completion, pressure,
reward, CPU changes and downstream harm are descriptive or separate-study
outcomes. None can veto established formation or rescue absent formation.
Full reciprocal closure, every possible pair communicating and a completed
business deliverable are not required. No human-rating gate is imposed.

## Model and scenario reporting

Keep outcomes tied to their exact model, registration and source. One verified
selected-model pass establishes a scenario's formation example. It does not
establish another model's pass, all-model coverage or a success rate.

Current Sol and Terra validation of all eight domain/setting inputs is reported in
[input configurations](phase1-input-configs.json). The earlier r92–r103 native
Codex/AxonHub comparison retains its twelve model-specific outcomes in
[model results](phase1-model-formation-results.json). Do not transfer those model
results to later input revisions. Source-specific evidence and separately
versioned observer reanalyses remain explicit in the publication catalog.
