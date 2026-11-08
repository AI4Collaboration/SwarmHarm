# Experiment package

The active [SwarmForm work order](../../docs/formation-study-design.md#overnight-work-and-acceptance-criteria) covers all four domains. `swarmform/fulfillment.py` implements the three-agent Data Analysis input and verifier. The rollout commands below describe the four-agent reporting baseline.

Use `--study-mode unified` for one continuous reporting workflow: autonomous
discovery through business records, communication and downstream actions share
the same task, session and state. Every fresh rollout runs end to end. Phase 1
labels autonomous formation and Phase 2 labels the registered consequence from
the same trajectory; there is no phase transition or formation gate.

Package layout:

- `phase1/`: shared workstation, record and formation helpers.
- `phase2/`: unified reporting, business notes, actions and outcome review.
- `phase2/workload_sources.py`: current domain source work; `delivery_data.py`: reports and independent truth.
- `scenarios/`: workstation initialization and offline fixtures.
- `configs/`: headline and cross-account routing settings. Additional test worlds live in `tests/worlds/`.
- `tests/`: offline contracts.
- `registrations/`: sealed inputs for the current reviewed matrix and its
  end-to-end validations.
- `run.py`, `launch.py`, `review.py`, `export_atif.py`: rollout lifecycle.

Harness adapters are in `../runtime/`. All inference uses AxonHub; Claude uses
Claude Code and OpenAI uses Codex.

For the fail-closed headline comparison, select
`--comparison-design balanced-headline-v1` with
`configs/unified-balanced-envelope.json`. Knowledge Work is primary and
Engineering is the sole replication domain; the four-domain suite is a separate
workload-stress block. The comparison contract rejects changes beyond model,
domain payload, one named binding and its registered claim.

See [findings](../../docs/phase2-design.md),
[pass criteria](../../docs/business-outcome-criteria.md),
[architecture](../../docs/architecture/shared-core-and-phases.md) and
[running guide](../../docs/running-evals.md).
