# Reporting baseline dataset admission

This contract validates retained reporting evidence. Current SwarmHarm input admission follows the [six-configuration ledger](../swarmharm/docs/research/mechanism-input-status.json). The retained SwarmForm channel study has its own [protocol](../swarmform/docs/formation-study-design.md) and [coverage audit](../swarmform/docs/swarmform-coverage.md); the current API task matrix is documented in the [SwarmForm run guide](../README.md#swarmform).

The four-agent reporting input is one continuous task, session and shared world. Each reporting
rollout is end to end and produces two independent labels from the same trajectory:
**Phase 1** is autonomous formation; **Phase 2** is the registered consequence.
Neither label unlocks or gates the other. Discovery, communication and business
effects have separate [evidence criteria](../swarmharm/docs/business-outcome-criteria.md).
The [machine-readable contract](dataset-admission-contract.json) records gates
and evidence paths; check it with `scripts/check_dataset_admission_contract.py`.

The [cross-account formation case](../swarmharm/docs/phase2-design.md)
has both registered verdicts. [Eight additional formation cases](../swarmharm/docs/research/phase1-native-trajectory-archives.json)
have their own frozen source and full archives. The [headline matrix](../swarmharm/docs/research/balanced-study-v2-results.json)
reports the 12 registered consequence verdicts,
with its [offline input readiness](../swarmharm/docs/research/balanced-study-v2-readiness.json)
recorded separately.

Every admitted positive result needs matching frozen inputs, complete native traces,
validated ATIF and independently reviewed terminal evidence. Record corrections
and negative outcomes as takeaways—what failed and why; negative traces need not
be retained. Label supplied conditions and offline-only reachability.
A mechanism can be implemented and tested without a positive model example.
