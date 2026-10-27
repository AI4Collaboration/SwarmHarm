# Environment iteration takeaways

This is the only maintained historical summary. Git preserves retired source
and reports; external raw archives preserve every trajectory and frozen score.
Current findings belong in the [current review](current-campaign-review.md).

- **Measure message exposure, not JSON formatting.** GLM r19 received a peer's
  complete reply after removing metadata; whole-file matching falsely blocked
  Phase 1. Match complete unique message bodies to their source version and
  author, verify actual delivery, and reject partial or ambiguous text. Repeated
  reads must not multiply one reply. Preserve frozen scores and label corrected
  offline interpretations; never claim that a blocked Phase 2 happened.
- **Communication can preserve the system.** In r17 Sol used the alternative
  importer, then coordinated a recovery-host swap and retained one old-format
  replica. Measured loss stayed zero. Do not equate discovery, adoption or
  orchestration with harm, or delete a valid corrective option to force harm.
- **Persistent reminders are not new information.** Long allowances produced
  many repeated blocked-work checks and final answers. Keep real business-state
  changes distinct from repeated prompting. A reminder must refer to current
  work, not accidentally send an agent back to an already completed phase.
  Route old-record updates through the current assignment after handover.
  Check individual completion before scheduling a reminder: an open customer
  workflow does not mean every assignment is unfinished. Completed contexts
  remain available for real changes; a safe hold stays a valid incomplete result.
- **Information exchange need not be repeated dialogue.** GLM r16 solved work
  from peers' problem notes but missed the repeated-reply criterion; unchanged
  Phase 1 inputs passed in r17. One missed gate is not a fixed model limitation.
  Stable lookup routes may make new builds mere rechecking. Keep the criterion
  fixed and useful old notes readable.
- **A booking is not an execution decision.** Sol r16 rebooked while writing an
  execution hold. Its frozen scheduler ignored free-text holds and replayed
  4,800 lost records. Preserve that score but qualify its meaning. The repaired
  interface exposes scheduled/held state; pending and held records do not run.
  Test hold→release→hold, rescheduling, stale handovers and cancellation against
  full-sequence replay. Report prose/state contradictions rather than inferring
  harmful intent. [Earlier review](https://github.com/AI4Collaboration/SwarmHarm/blob/6e90f620/docs/research/current-campaign-review.md).
- **Formation and harm need separate evidence.** Phase 2 needs no new reply
  round trip after Phase 1. Earlier extra-dialogue gates obscured outcomes.
  Preserve original frozen scores and label later interpretation separately.
  Dialogue, adoption, composition, amplification and orchestration are analysis
  dimensions, not mandatory mechanisms.
- **Do not manufacture discovery.** System-opened requests, private-record
  matching and supplied sharing commands add cues. Preserve the distinction
  between system records and authored messages. Historical Flash successes used
  different cues and runtime conditions; they are not a clean model comparison.
- **Verify the blocker and the alternative independently.** Failure does not
  prove impossibility; accepted imports do not prove harm. Keep truth outside
  subject control and replay each actor's complete sequence, including holds,
  corrections and cancellations. Deliberate action does not establish harmful
  intent.
- **Keep one continuous campaign.** Preserve agents, histories, shared state and
  real chronology. Do not stitch one run's dialogue to another's outcome.
  Virtual schedules may accelerate business time, never fabricate overlapping
  contexts or conversations. Never replace a negative or provider-failed run.
- **One depleted key is not an unavailable model.** Check all existing eligible
  routes, keep model identity fixed, and record actual execution provenance.
  Recovered transport errors, terminal budget limits and provider refusals are
  different observations. Local sealed hashes do not freeze remote routing.
