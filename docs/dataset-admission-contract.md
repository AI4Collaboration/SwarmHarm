# Reporting baseline dataset admission

This admission contract validates the existing reporting dataset. The SwarmForm
research plan and new mechanism admission are maintained in the
[study design](formation-study-design.md) and [coverage audit](swarmform-coverage.md).

The four-agent reporting input is one continuous task, session and shared world. Each reporting
rollout is end to end and produces two independent labels from the same trajectory:
**Phase 1** is autonomous formation; **Phase 2** is the registered consequence.
Neither label unlocks or gates the other. Discovery, communication and business
effects have separate [evidence criteria](business-outcome-criteria.md).
The [machine-readable contract](dataset-admission-contract.json) records gates
and evidence paths; check it with `scripts/check_dataset_admission_contract.py`.

The [cross-account formation case](phase2-design.md)
has both registered verdicts. [Eight additional formation cases](research/phase1-native-trajectory-archives.json)
have their own frozen source and full archives. The [headline matrix](research/balanced-study-v2-results.json)
reports the 12 registered consequence verdicts,
with its [offline input readiness](research/balanced-study-v2-readiness.json)
recorded separately.

Every admitted result needs matching frozen inputs, complete native traces,
validated ATIF and independently reviewed terminal evidence. Preserve corrections
and negative outcomes. Label supplied conditions and offline-only reachability.
A mechanism can be implemented and tested without a positive model example.
