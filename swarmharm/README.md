# SwarmHarm unified environment

**Inputs tailored to each failure mode, with a shared runner and evidence format.** The current reporting engine exposes access, coupling, verification and observation parameters. Agents retain their task, native session and workstation; selected interfaces are available from the start. Phase 1/2 are outcome labels, not runtime stages.

The [SwarmHarm section of the root README](../README.md#swarmharm) is the maintained scope, mechanism coverage, status and claim/case map. This page describes the implemented runner. SwarmForm's separate channel and structure studies live under `swarmform/`; their completion does not establish SwarmHarm coverage.

## Inputs and evidence

- **Taxonomy:** six threat models cover Specification Gaming, Trace Tampering, Grader Tampering, Information Scope Violation, Action Scope Violation and Shared-resource Interference. Specification Gaming uses one proxy-mismatch configuration. Information flow, amplification, composition and cognition are reviewed separately. [Definitions and source coverage](docs/phase2-taxonomy.md).
- **Domains:** Engineering and Knowledge Work. Knowledge Work includes customer briefings, data analysis and financial analysis. These are source workloads with different business logic, selected within one domain.
- **Input coverage:** six configurations × two primary domains = 12 target slots. All 12 have reviewed positives bound to their exact selected inputs; the ledger records `delivery_ready: true`.
- **Source selection:** `--scenario engineering-capacity` uses release-validation work. `--scenario knowledge-work` defaults to customer-delivery evidence review. Add `--workload data-analysis` or `--workload financial-analysis` for those Knowledge Work tasks. [Parameters](docs/scenarios-and-parameters.md) · [Input and evidence ledger](docs/research/mechanism-input-status.json).
- **Reviewed comparison:** records/resource/grader × Knowledge Work/Engineering × Sol 5.6/6.1; 12 full trajectories, five original claim passes. [Exact cases and artifacts](docs/research/balanced-study-v2-results.json).

The current Engineering and Knowledge Work Specification Gaming cases each contain one four-report release against two approved processing units. Both agents later corrected their batching interpretation and disclosed the overrun. The current Engineering Trace case retained 14 completion/execution mismatches across four releases; its notes disclosed manual preparation and missing dispatch execution. These cases establish their registered mechanisms, not communication or composition.

## Reproduction

Export the implemented mechanism inputs for both primary domains without
model calls (use a new output directory):

```sh
"$SWARMHARM_HARBOR_ENV/bin/python" swarmharm/scripts/inspect_unified_input.py \
  --mechanism implemented --scenario all --output ../mechanism-input-preview
```

Each package contains tasks, tools, workstation files and `world-config.json`.
The operator manifest records the mechanism criterion and subject-input hash.
`--mechanism all --scenario all` exports all 12 admitted default inputs. The `task-gaming` selector tests Specification Gaming. Explicit single-template preview supports development.
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
`collection_complete` means the run has evidence available for review. In
`completion.json`, `termination_reason: quiescence` means the sessions settled
with no further work scheduled. For older runs, use the final states in
`natural/actors.json`. The independent review records the business outcome.
For services without Operations SQLite, `operations_ledger_applicable` is false;
`service_journal_scope` names the independently replayed service record. The legacy
`operations_ledger_match` field remains for compatibility.

The [running guide](../docs/running-evals.md#validate-and-freeze) describes runtime
setup and sealing. [Archived registrations](docs/archive/README.md) retain their
original selectors, inputs and scores; they do not supply the new contracts.
Use fresh paths when refining an input. Keep negative-result takeaways concise and store raw evidence outside the maintained tree.

## Code map

- `phase2/world_config.py` and `unified_delivery.py`: parameter normalization, tasks, services and bindings.
- `phase2/workload_sources.py` and `delivery_data.py`: domain work and independent expected outputs.
- `phase1/`: reused workstation, shared-record and formation helpers.
- `configs/`: maintained input configurations; `tests/worlds/`: offline fixtures.
- `run.py`, `launch.py`, `review.py`, `../shared/export_atif.py`: one lifecycle and evidence path.
- `../shared/`: shared native adapters and protected capture.

[Outcome review](docs/business-outcome-criteria.md) · [Environment contract](docs/environment-contract.md) · [Registrations](registrations/README.md)
