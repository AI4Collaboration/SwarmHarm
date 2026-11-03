# Experiment package

Two independent studies share one evidence harness:

- `phase1/`: autonomous communication discovery.
- `phase2/`: collective actions and terminal outcomes.
- `scenarios/`: domain facts.
- `tests/`: offline contracts.
- `registrations/`: current registration only.
- `run.py`, `launch.py`, `review.py`, `export_atif.py`: rollout lifecycle.

Harness adapters are in `../runtime/`. Phase 2 currently uses four independent
Sol 5.6 contexts through Pi SDK and AxonHub. No rollout is active.

See [findings](../../docs/phase2-design.md),
[pass criteria](../../docs/business-outcome-criteria.md),
[architecture](../../docs/architecture/shared-core-and-phases.md) and
[running guide](../../docs/running-evals.md).
