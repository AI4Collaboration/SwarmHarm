# Experiment package

Use `--study-mode unified` for one continuous reporting workflow: autonomous
discovery through business records, communication and downstream actions share
the same task, session and state. There is no phase transition.

Package layout:

- `phase1/`: shared workstation and historical discovery helpers.
- `phase2/`: unified reporting, business notes, actions and outcome review.
- `scenarios/`: domain facts.
- `tests/`: offline contracts.
- `registrations/`: current registration only.
- `run.py`, `launch.py`, `review.py`, `export_atif.py`: rollout lifecycle.

Harness adapters are in `../runtime/`. All inference uses AxonHub; Claude uses
Claude Code and OpenAI uses Codex. See [current work](../../docs/working-context.md) for readiness.
Directory and serialized `phase2` names preserve compatibility; they do not
split the current run. Earlier findings retain their original settings.
See the [current claim and mechanism coverage](../../docs/research/unified-taxonomy-readiness.json).

See [findings](../../docs/phase2-design.md),
[pass criteria](../../docs/business-outcome-criteria.md),
[architecture](../../docs/architecture/shared-core-and-phases.md) and
[running guide](../../docs/running-evals.md).
