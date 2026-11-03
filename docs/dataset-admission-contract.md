# Dataset admission

Phase 1 and Phase 2 are admitted independently under the
[pass criteria](business-outcome-criteria.md).
The [machine-readable contract](dataset-admission-contract.json) records gates
and evidence paths; validate it with `scripts/check_dataset_admission_contract.py`.

R136 is the selected Phase 1 example. Phase 2's representative evidence and
remaining compositional coverage are mapped in [Phase 2 evidence](phase2-design.md).

Every admitted result needs matching frozen inputs, complete native traces,
validated ATIF output and independently reviewed terminal evidence. Preserve
corrections and negative outcomes. Label supplied methods and offline-only
conditions. Historical connected results retain their original contract;
they are not current launch targets.
