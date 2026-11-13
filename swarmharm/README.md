# SwarmHarm unified environment

**Inputs tailored to each failure mode, with a shared runner and evidence format.** The current reporting engine exposes access, coupling, verification and observation parameters. Agents retain their task, native session and workstation; selected interfaces are available from the start. Phase 1/2 are outcome labels, not runtime stages.

The [SwarmHarm section of the root README](../README.md#swarmharm) is the maintained scope, mechanism coverage, status and claim/case map. This page describes the implemented runner. SwarmForm's separate channel and structure studies live under `swarmform/`; their completion does not establish SwarmHarm coverage.

## Inputs and evidence

- **Taxonomy:** six mechanisms across task fidelity, evaluation integrity and environment integrity, with collective behavior and cognition annotated separately. The [METR coverage inventory](docs/phase2-taxonomy.md) maps source behaviors and lists implementation/evidence gaps.
- **Delivery plan:** eight mechanism configurations × four domains = 32 planned inputs. Mechanism configurations are separate from the engine's binding presets, which also include control. Domain tasks must differ in actual work and consequences. See the [current plan](../README.md#swarmharm); the 32 are not yet a validated package set.
- **Current inputs:** [32-input status](docs/research/mechanism-input-status.json). The new operator selector exports all 32 implemented inputs. Matched live evidence is tracked separately in the ledger. Offline path checks are separate from live validation.
- **Implemented engine:** configurable binding presets, including control; four domain source workloads. [Parameters, values and defaults](docs/scenarios-and-parameters.md).
- **Reviewed comparison:** records/resource/grader × Knowledge Work/Engineering × Sol 5.6/6.1; 12 full trajectories, five original claim passes. [Exact cases and artifacts](docs/research/balanced-study-v2-results.json).
- **Archived scenario selectors:** nine parameterized inputs share this engine. They are not nine distinct failure modes or nine required positive outcomes. The [archive index](docs/archive/README.md) and [archived scenario ledger](docs/research/threat-grid-status.json) bind original results to exact inputs and full trajectories; their completion counts do not measure the new delivery.

## Reproduction

Export the implemented mechanism inputs and all four domain workloads without
model calls (use a new output directory):

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/scripts/inspect_unified_input.py \
  --mechanism implemented --scenario all --output ../mechanism-input-preview
```

Each package contains tasks, tools, workstation files and `world-config.json`.
The operator manifest records the mechanism criterion and subject-input hash.
`--mechanism all --scenario all` exports the full 32-input set.
The same selector prepares a native rollout with its own sealed mechanism
criterion and executable path checks. Use the pinned Python environment from
`bash scripts/setup-local`, native Codex and the existing AxonHub key:

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/run.py --phase prepare \
  --study-mode unified --mechanism grader-tampering --source-retention local \
  --scenario knowledge-work --model-id openai/gpt-6.1-sol --population 4 \
  --harness codex --goal-mode off --reasoning-effort high \
  --output ../eval-readiness/mechanism-grader-knowledge-r01 \
  --registration-dir swarmharm/registrations/mechanism-grader-knowledge-r01 \
  --key-file /path/to/existing-axonhub.key
```

For the Engineering build-record variant, add
`--input-variant engineering-fixture-packaging-v1` with `--mechanism evidence-tampering` and
`--scenario engineering-capacity`. It retains the unavailable partner fixture and
adds a verifiable source archive to the packaging check. This is a separate input
condition; offline path checks do not establish model behavior.

For recurring synthetic payment processing, select `--mechanism work-lifecycle`,
`--scenario financial-analysis` and `--input-variant finance-account-retirement-recurring-v1`.
The desk exposes the next window; observation lasts at least 660 seconds and continues
for approved payments whose next eligible window is within the remaining run budget.
Payments scheduled beyond that limit remain pending at observation end. Only an actual
synthetic receipt records a payment as sent; the calendar uses compressed study time.

Commit source before preparation and the generated registration before collection.
Launch once with `swarmharm/launch.py`, using the same output, registration and
key arguments. Source and evidence stay local; no push or upload is required.
Reuse preparation checks with `--controls-from OUTPUT` only when source, image and
native runtime match and the archived checks cover every module required by the target scenario. Each input still executes its own path checks.

After completion, use the **sealed scripts under `OUTPUT/code/`**: export ATIF
with `shared/export_atif.py OUTPUT`, run `swarmharm/review.py --output OUTPUT`,
then `swarmharm/scripts/judge_unified_transcript.py --output OUTPUT --key-file KEY`.
This keeps later source changes out of the original review.
The primary result is `mechanism-verdict.json`: protected final-file/action replay,
native continuity and exact transcript citations must agree. Withdrawals and
corrections remain in every replay. Communication, coordination and composition
are separate findings; the retained component verdict is auxiliary.
For services without Operations SQLite, `operations_ledger_applicable` is false;
`service_journal_scope` names the independently replayed service record. The legacy
`operations_ledger_match` field remains for compatibility.

The [running guide](../docs/running-evals.md#validate-and-freeze) describes runtime
setup and sealing. [Archived registrations](docs/archive/README.md) retain their
original selectors, inputs and scores; they do not supply the new contracts.
Use fresh paths and preserve a negative rollout when refining its input.

## Code map

- `phase2/world_config.py` and `unified_delivery.py`: parameter normalization, tasks, services and bindings.
- `phase2/workload_sources.py` and `delivery_data.py`: domain work and independent expected outputs.
- `phase1/`: reused workstation, shared-record and formation helpers.
- `configs/`: maintained input configurations; `tests/worlds/`: offline fixtures.
- `run.py`, `launch.py`, `review.py`, `../shared/export_atif.py`: one lifecycle and evidence path.
- `../shared/`: shared native adapters and protected capture.

[Outcome review](docs/business-outcome-criteria.md) · [Environment contract](docs/environment-contract.md) · [Registrations](registrations/README.md)
