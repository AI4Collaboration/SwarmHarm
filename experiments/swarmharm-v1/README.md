# Experiment package

Use `--study-mode unified` for one continuous reporting workflow: autonomous
discovery through business records, communication and downstream actions share
the same task, session and state. Every fresh rollout runs end to end. Phase 1
labels autonomous formation and Phase 2 labels the registered consequence from
the same trajectory; there is no phase transition or formation gate.

Package layout:

- `phase1/`: shared workstation and historical discovery helpers.
- `phase2/`: unified reporting, business notes, actions and outcome review.
- `phase2/workload_sources.py`: current domain source work; `delivery_data.py`: reports and independent truth.
- `scenarios/`: historical domain facts.
- `tests/`: offline contracts.
- `registrations/`: sealed inputs for the current reviewed matrix and its
  end-to-end validations.
- `run.py`, `launch.py`, `review.py`, `export_atif.py`: rollout lifecycle.

Harness adapters are in `../runtime/`. All inference uses AxonHub; Claude uses
Claude Code and OpenAI uses Codex. See [current work](../../docs/working-context.md) for readiness.
Directory and serialized `phase2` names preserve compatibility; they do not
split the current run. Earlier findings retain their original settings.
See the [current balanced results](../../docs/research/balanced-study-v2-results.json).

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
