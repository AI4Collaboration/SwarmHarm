# Experiment package

Two independent studies share one evidence harness:

- `phase1/`: autonomous communication discovery.
- `phase2/`: collective actions and terminal outcomes.
- `scenarios/`: domain facts.
- `tests/`: offline contracts.
- `registrations/`: current registration only.
- `run.py`, `launch.py`, `review.py`, `export_atif.py`: rollout lifecycle.

Harness adapters are in `../runtime/`. All inference uses AxonHub; Claude uses
Claude Code and OpenAI uses Codex. See [current work](../../docs/working-context.md) for readiness.
The three current Phase 2 claims have reviewed Sol/Codex evidence.
See the [claim-to-case index](../../docs/research/phase2-readiness.json).

See [findings](../../docs/phase2-design.md),
[pass criteria](../../docs/business-outcome-criteria.md),
[architecture](../../docs/architecture/shared-core-and-phases.md) and
[running guide](../../docs/running-evals.md).
