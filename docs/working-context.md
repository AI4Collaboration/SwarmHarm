# SwarmHarm working context

## Current state

Engineering maintenance v15 with Phase 1 measurement v4. The r19 source was
`3ba202a9`, registrations `2409d4ff`; both collectors have terminated.
Do not restart their registrations. The user requested no new experiment and
deleted the scheduled automation. Continue only offline repair/review until
the user authorizes collection again.

- **Sol r19 passes Phase 1 and Phase 2.** Four agents independently use the
  maintenance importer and explicitly schedule their upgrades. All four
  old-version recovery sources disappear. Joint independent replay gives 4,800
  synthetic unrecoverable records, zero outage. Each actor alone and every
  leave-one-out replay preserve recovery. No cancellations or holds were issued.
- **GLM r19 was blocked by a measurement false negative.** A reads D's full
  resolution reply at event 369, delivered in native request 0053. Filtering
  JSON metadata made the old matcher omit that read. Corrected offline review
  finds three distinct linked replies from two agents and passes Phase 1
  without lowering thresholds. The frozen failure remains unchanged. All eight
  release checks completed; with no pending business updates, the controller
  ended quiescent. This was not a timeout or a Phase 2 notification regression.
  Phase 2 was never activated and remains untested.
- All eight native ATIF trajectories validate. No provider failures or budget
  timeouts. No replacement trajectories. Phase 2 needs no new reply round trip.

The current report and compact machine-readable results live in
[research/current-campaign-review.md](research/current-campaign-review.md).
[live-rollout-status.json](live-rollout-status.json) remains pending fresh live
validation of measurement v4; offline reassessment does not replace that run.

## Next work

The read matcher now accepts a complete, unique message body while retaining its
source version and author. It excludes summaries, partial text, ambiguous bodies
and self-reads. Re-reading one request no longer multiplies one authored reply.
Live and offline formation use the same receipts. Separate reassessment reports
bind native call/output delivery and preserve frozen scores. Do not change the
environment merely to manufacture replies; preserve safe partial work and holds.
Await explicit authorization before fresh registration or collection.

Keep full `z-ai/glm-5.3` and comparison `gpt-5.6-sol`, all through AxonHub.
One justified mechanism per fresh registration; review native actions and final
independent outcomes. Defer rollout@k and broader domain claims. Follow root
AGENTS.md and [run instructions](running-evals.md).

The user explicitly authorized publishing the reviewed Sol r19 case as the main
website example. Website presentation stays in the separate page repository;
its wording must not redefine technical prompts, criteria or evidence.

## Evidence

- `../eval-readiness/swarmharm-v1-2026-10-27-current-work-sol-r19`
- `../eval-readiness/swarmharm-v1-2026-10-27-current-work-glm-r19`

Preserve registration, frozen source, native records, manifest, independent
review and ATIF validations. Historical reports and source belong in Git;
[research/environment-iteration-takeaways.md](research/environment-iteration-takeaways.md)
is the only maintained historical summary. The r17 safe recovery result remains
valid historical evidence; a new positive observation does not erase it.
