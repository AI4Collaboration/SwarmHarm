# SwarmHarm unified environment

**Inputs tailored to each failure mode, with a shared runner and evidence format.** The current reporting engine exposes access, coupling, verification and observation parameters. Agents retain their task, native session and workstation; selected interfaces are available from the start. Phase 1/2 are outcome labels, not runtime stages.

The [SwarmHarm section of the root README](../README.md#swarmharm) is the maintained scope, mechanism coverage, status and claim/case map. This page describes the implemented runner. SwarmForm's separate channel and structure studies live under `swarmform/`; their completion does not establish SwarmHarm coverage.

## Inputs and evidence

- **Taxonomy:** six mechanisms across task fidelity, evaluation integrity and environment integrity, with collective behavior and cognition annotated separately. The [METR coverage inventory](docs/phase2-taxonomy.md) maps source behaviors and lists implementation/evidence gaps.
- **Implemented engine:** eight binding presets, including control; four domain source workloads. [Parameters, values and defaults](docs/scenarios-and-parameters.md).
- **Reviewed comparison:** records/resource/grader × Knowledge Work/Engineering × Sol 5.6/6.1; 12 full trajectories, five original claim passes. [Exact cases and artifacts](docs/research/balanced-study-v2-results.json).
- **Retained scenario selectors:** nine parameterized inputs share this engine. They are not nine distinct failure modes or nine required positive outcomes. The root README separates mechanisms from additional findings; the [local ledger](docs/research/threat-grid-status.json) binds each positive, negative and active rollout to its exact input and full trajectory. Baseline and refined cases keep their original verdicts.

## Reproduction

Use the pinned Python environment from `bash scripts/setup-local`, native Codex and AxonHub. The reporting entry point is `run.py` with `--phase prepare` or `--phase collect`. Preparation takes a fresh output path and registration directory; collection uses those sealed inputs once.

```text
--study-mode unified --component-family unified-delivery
--model-id openai/gpt-6.1-sol --harness codex --goal-mode off --reasoning-effort high
--binding-preset PRESET --world-config CONFIG_PATH --scenario DOMAIN
```

Use the [running guide](../docs/running-evals.md#validate-and-freeze) for complete preparation, sealing, collection and review. The existing reporting runner has four agents. `--comparison-design balanced-headline-v1` preserves the completed comparison; it is not the nine-grid contract.

For a retained scenario selector, use `--threat-cell CELL --source-retention local` instead of manually combining a preset and world. Exact configurations and per-cell criteria are in [threat_grid.py](phase2/threat_grid.py). Source and registrations must be committed locally before collection. No push or upload is required or authorized for this delivery.

To inspect all nine development configurations without Docker, credentials, tests or model calls:

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/scripts/inspect_unified_input.py \
  --scenario knowledge-work --threat-cell all --output ../swarmharm-input-preview
```

Each cell contains the task, tools and initial files. The top-level manifest maps all nine criteria to exact input hashes; criteria stay outside participant files. This export is an input preview, not behavioral evidence or an exact reproduction of an older sealed case. Use a new output directory.

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

Current work is classification and evidence alignment; no new subject rollout is part of it. For later registered work, keep iteration short: preparation selects input, native-runtime and evidence checks; it does not rerun retained legacy studies. Reuse sealed checks across unchanged-source registrations and collect only changed cells. Full regression remains an explicit maintenance action.
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
