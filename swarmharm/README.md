# SwarmHarm unified environment

**One continuous reporting workflow, parameterized by access, coupling, verification and observation.** Agents retain their own task, native session and workstation; selected business interfaces are available from the start. Phase 1/2 are outcome labels, not runtime stages.

The [SwarmHarm section of the root README](../README.md#swarmharm) is the maintained scope, nine-cell plan, status and claim/case map. This page describes the implemented runner. SwarmForm's separate channel and structure studies live under `swarmform/`; their completion does not establish SwarmHarm coverage.

## Inputs and evidence

- **Implemented engine:** eight binding presets, including control; four domain source workloads. [Parameters, values and defaults](docs/scenarios-and-parameters.md).
- **Reviewed comparison:** records/resource/grader × Knowledge Work/Engineering × Sol 5.6/6.1; 12 full trajectories, five original claim passes. [Exact cases and artifacts](docs/research/balanced-study-v2-results.json).
- **Nine-cell study:** nine parameterized inputs share this engine. The root README reports current behavior coverage and remaining work; the [local ledger](docs/research/threat-grid-status.json) binds each positive, negative and active rollout to its exact input and full trajectory. Baseline and refined cases keep their original verdicts.

## Reproduction

Use the pinned Python environment from `bash scripts/setup-local`, native Codex and AxonHub. The reporting entry point is `run.py` with `--phase prepare` or `--phase collect`. Preparation takes a fresh output path and registration directory; collection uses those sealed inputs once.

```text
--study-mode unified --component-family unified-delivery
--model-id openai/gpt-6.1-sol --harness codex --goal-mode off --reasoning-effort high
--binding-preset PRESET --world-config CONFIG_PATH --scenario DOMAIN
```

Use the [running guide](../docs/running-evals.md#validate-and-freeze) for complete preparation, sealing, collection and review. The existing reporting runner has four agents. `--comparison-design balanced-headline-v1` preserves the completed comparison; it is not the nine-grid contract.

For the current nine-cell study, use `--threat-cell CELL --source-retention local` instead of manually combining a preset and world. Exact configurations and per-cell criteria are in [threat_grid.py](phase2/threat_grid.py). Source and registrations must be committed locally before collection. No push or upload is required or authorized for this delivery.

A fresh local run from the repository root (after sourcing the setup environment):

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/run.py --phase prepare \
  --study-mode unified --threat-cell infra-compositional --source-retention local \
  --scenario knowledge-work --model-id openai/gpt-6.1-sol --population 4 \
  --harness codex --goal-mode off --reasoning-effort high \
  --output ../infra-compositional-new \
  --registration-dir swarmharm/registrations/infra-compositional-new \
  --key-file /path/to/axonhub.key
```

Commit that registration, then run `swarmharm/launch.py` with the same output,
registration and key arguments. After completion, run `shared/export_atif.py OUTPUT`,
then `swarmharm/review.py --output OUTPUT`. The six propagation/coordination cells
also need `swarmharm/scripts/judge_unified_transcript.py --output OUTPUT --key-file KEY`.
Use fresh paths. The [current ledger](docs/research/threat-grid-status.json) identifies
exact reviewed inputs, source commits and full trajectories. A valid negative is
separate from an observed threat. Reuse offline checks with `--controls-from OUTPUT`
only when preparation verifies identical code, image and native runtime.

Keep iteration short: grid preparation selects current input, native-runtime and evidence checks; it does not rerun retained legacy studies. Reuse sealed checks across unchanged-source registrations and collect only changed cells. Full regression remains an explicit maintenance action.
Each input still needs its own ordinary-path, alternative-path and corrected-binding
check. Do not add timed unpacking, artificial waiting or unchanged-state follow-ups.

## Code map

- `phase2/world_config.py` and `unified_delivery.py`: parameter normalization, tasks, services and bindings.
- `phase2/workload_sources.py` and `delivery_data.py`: domain work and independent expected outputs.
- `phase1/`: reused workstation, shared-record and formation helpers.
- `configs/`: maintained input configurations; `tests/worlds/`: offline fixtures.
- `run.py`, `launch.py`, `review.py`, `../shared/export_atif.py`: one lifecycle and evidence path.
- `../shared/`: shared native adapters and protected capture.

[Outcome review](docs/business-outcome-criteria.md) · [Environment contract](docs/environment-contract.md) · [Registrations](registrations/README.md)
