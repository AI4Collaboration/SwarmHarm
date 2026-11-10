# SwarmHarm unified environment

**One continuous reporting workflow, parameterized by access, coupling, verification and observation.** Agents retain their own task, native session and workstation; selected business interfaces are available from the start. Phase 1/2 are outcome labels, not runtime stages.

The [SwarmHarm section of the root README](../../README.md#swarmharm) is the maintained scope, nine-cell plan, status and claim/case map. This page describes the implemented runner. SwarmForm's separate channel and structure studies live under `swarmform/`; their completion does not establish SwarmHarm coverage.

## Inputs and evidence

- **Implemented engine:** eight binding presets, including control; four domain source workloads. [Parameters, values and defaults](../../docs/scenarios-and-parameters.md).
- **Reviewed comparison:** records/resource/grader × Knowledge Work/Engineering × Sol 5.6/6.1; 12 full trajectories, five original claim passes. [Exact cases and artifacts](../../docs/research/balanced-study-v2-results.json).
- **Current target:** nine grid-specific environments and reviewed **Sol 6.1** traces. Historical preset results require a separate grid review; they do not establish nine-cell coverage.

## Reproduction

Use the pinned Python environment from `bash scripts/setup-local`, native Codex and AxonHub. The reporting entry point is `run.py` with `--phase prepare` or `--phase collect`. Preparation takes a fresh output path and registration directory; collection uses those sealed inputs once.

```text
--study-mode unified --component-family unified-delivery
--model-id openai/gpt-6.1-sol --harness codex --goal-mode off --reasoning-effort high
--binding-preset PRESET --world-config CONFIG_PATH --scenario DOMAIN
```

Use the [running guide](../../docs/running-evals.md#validate-and-freeze) for complete preparation, sealing, collection and review. The existing reporting runner has four agents. `--comparison-design balanced-headline-v1` preserves the completed comparison; it is not the nine-grid contract.

## Code map

- `phase2/world_config.py` and `unified_delivery.py`: parameter normalization, tasks, services and bindings.
- `phase2/workload_sources.py` and `delivery_data.py`: domain work and independent expected outputs.
- `phase1/`: reused workstation, shared-record and formation helpers.
- `configs/`: maintained input configurations; `tests/worlds/`: offline fixtures.
- `run.py`, `launch.py`, `review.py`, `export_atif.py`: one lifecycle and evidence path.
- `../runtime/`: shared native adapters and protected capture.

[Outcome review](../../docs/business-outcome-criteria.md) · [Environment contract](../../docs/environment-contract.md) · [Registrations](registrations/README.md)
