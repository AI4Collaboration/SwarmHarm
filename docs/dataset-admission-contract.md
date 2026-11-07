# Dataset admission

The current input is one continuous task, session and shared world. Every fresh
rollout is end to end and produces two independent labels from the same trajectory:
**Phase 1** is autonomous formation; **Phase 2** is the registered consequence.
Neither label unlocks or gates the other. Discovery, communication and business
effects have separate [evidence criteria](business-outcome-criteria.md).
The [machine-readable contract](dataset-admission-contract.json) records gates
and evidence paths; check it with `scripts/check_dataset_admission_contract.py`.

[Eight native formation cases](research/phase1-native-trajectory-archives.json)
have their own frozen source and full archives. The consequence evidence
is the completed [headline matrix](research/balanced-study-v2-results.json),
with its [offline input readiness](research/balanced-study-v2-readiness.json)
recorded separately.

Every admitted result needs matching frozen inputs, complete native traces,
validated ATIF and independently reviewed terminal evidence. Preserve corrections
and negative outcomes. Label supplied conditions and offline-only reachability.
A mechanism can be implemented and tested without a positive model example.
