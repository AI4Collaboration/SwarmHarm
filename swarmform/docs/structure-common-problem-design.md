# Retained proposal: eight-agent research in ten-minute increments

This is an unimplemented historical proposal, retained for references from the
structure-study records. It does not configure the current API runner or define
handoff work. Use the [SwarmForm API guide](../../rollouts/README.md) for the
current three task triplets, four communication conditions and N=4,8,16 commands.

The retained results use their own original registrations; they do not validate
this proposed interval policy.

## Task and matched conditions

Retain Navier–Stokes theoretical exploration with eight agents per condition,
the same mathematical task and initial materials. Intended discloses that
eight agents share the task and supplies peer addresses and the message
interface. Unintended supplies no peer roster or communication convention;
any discovery and use of the available shared substrate must arise in the run.
Neither condition receives division-of-work, aggregation, hierarchy or
orchestrator instructions. Do not reward message volume or tell unintended
agents to publish for peers. Use the same model, reasoning, context policy,
scheduler and cumulative resource allowances in both conditions.

## Ten minutes, then another ten if needed

- Start with one 600-second research interval per condition, concurrently.
  At each boundary, stop or add exactly one further 600-second interval to
  both conditions: 10 → 20 → 30 minutes, and so on as justified. There is no
  precommitted 30- or 90-minute run and no unbounded automatic extension.
- These are observation and extension checkpoints within the same pair,
  not independent replicates, agent rounds or required research duration.
  Keep the same eight identities, native sessions, private context, files,
  pending events and task state. Never reset cumulative usage at a boundary.
- Register identical finite token, model-response and tool-call caps before
  collection. Adding time does not replenish those caps. Actual consumption
  can differ; report it rather than padding either condition's work.
- Record each paired extension decision and its reason. Reasons may include
  substantive research still in progress or an unfinished feedback chain.
  Apply the same rule to both conditions. Absence of an orchestrator alone
  is not a reason to continue until a positive result appears.
- Keep an accepted extension continuous. Without an extension, dispatch no
  work past the current boundary; bound cancellation and record its overhead
  separately. A later continuation requires validated state preservation,
  not replacement agents or a controller-written summary.
- Stop early on exhausted resources, user stop, infrastructure failure, or
  verified quiescence: all agents explicitly paused and no model/tool work,
  background jobs, pending notices or unsettled publication changes remain.
  A response ending, a claimed solution or 30 seconds of silence is not
  sufficient. If one condition terminates, do not silently extend the other;
  record the reason and use the common observed horizon for paired reporting.

## Asynchronous work and neutral notifications

Each agent advances independently, without a cohort round barrier or fixed
sleep between useful steps. Actual stable file changes trigger deduplicated,
path-only notices. Retain immediate eligible continuations and event-driven
wakes in both conditions. Deliver pending notices as soon as the validated
native interface permits; busy-model delivery must be measured separately
from controller enqueue time. Do not invent messages or supply content
summaries to accelerate interaction.

Remove the participant-facing 90-minute commitment. Common lifecycle wording
should ask agents to pursue justified next steps while resources remain,
retain useful partial work and concrete obstacles, and avoid repetition merely
to stay active. The ten-minute checkpoint is operator-side: do not send a
periodic request to organize, summarize, assign work or announce a leader.

## Observation at every boundary

Retain complete new trajectories and segmented timing once collection is
authorized. Report the latest interval and cumulative evidence: actual reads,
downstream use, replies and return receipts; model/tool time, notification
discovery, queueing, native receipt and idle time; resource consumption and
pending work at cutoff. Notification counts alone are not interaction counts.

Use the README's 3×3 taxonomy over time, including subgroup and ambiguous
states. Aggregation can itself be structure; distinguish it from accepted
coordination. Verify multilevel delegation through a linked task, onward
delegation, execution and returned results. Record who performs each function,
when others use it, and any transfer, overlap or dissolution of responsibilities.
Keep exact event times within each ten-minute interval. Adaptive observations
from one pair do not establish emergence rates or a causal condition advantage.

## Implementation boundary

Existing responsive scheduling, timing and opaque-context fixes remain
available. The current sustained runtime still hard-codes 5,400 seconds and
terminal session closure. It does not yet implement this interval policy.
Before collection, implement and test paired deadline extension, bounded
timeouts, cumulative accounting, boundary state retention and early stopping;
verify context maintenance at a boundary, including interrupted maintenance.
Changing only 5,400 to 600 is insufficient. Keep historical policies unchanged.
