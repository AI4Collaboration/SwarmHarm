# Dataset admission

Phase 1 and Phase 2 are admitted independently under the
[pass criteria](business-outcome-criteria.md). Phase 2 supplies an empty usable
channel corresponding to Phase 1's endpoint, without importing its evidence.
The [machine-readable contract](dataset-admission-contract.json) records gates
and evidence paths; check it with `scripts/check_dataset_admission_contract.py`.

[Phase 1 results](research/phase1-results.json) have their own pinned source.
[Unified Phase 2 coverage](research/unified-taxonomy-readiness.json) maps the
three core findings to r8, r17/r18 and r26, separately from the new r31 interface
checks. Earlier component cases remain archived under their original settings.

Every admitted result needs matching frozen inputs, complete native traces,
validated ATIF and independently reviewed terminal evidence. Preserve corrections
and negative outcomes. Label supplied conditions and offline-only reachability.
A mechanism can be implemented and tested without a positive model example.
