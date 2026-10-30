# Phase 1: autonomous discovery and communication

Use the common `../run.py` preparation, collection, review and export pipeline.
Four domains share `lab.py`; domain source truth remains in `../scenarios/`.
Historical connected and note-based studies retain their original registrations.

## Current design

The user selected Wendzel et al. 2025 E1 (value), E2.1 (quantity) and E2.2
(position/order), retaining their hierarchy and hybrid rules. The synthetic
isolation defects live in `cache_channels.py`; `channel-taxonomy.json` is
operator-only. See the [design](../../../docs/phase1-publication-design.md).

The new standalone profiles are `cache_value`, `cache_count`, `cache_order`, and
their `_repaired` counterparts. The old `records_shared`/`records_partitioned`
profiles are legacy controls, not evidence of the new isolation construct.
New profiles partition legacy records/notifications and remove the supplied
note/reply helper. Every new profile starts with an empty working cache. Ordinary
source reads refresh the latest source; later live writes are source-attributed.
Counts come from actual entries; ordering controls real eviction.

Prepare with `--study-mode phase1`, `--phase1-channel-profile PROFILE`,
`--scenario SCENARIO`, `--cue-condition agent_initiated_activity`,
`--harness pi-sdk --model-id openai/gpt-5.6-sol --model-alias sol56`.
The four scenarios are `engineering-capacity`, `data-analysis`,
`financial-analysis` and `knowledge-work`. Use the pinned Harbor environment and
existing host-only AxonHub key described in [running evaluations](../../../docs/running-evals.md).
A separate topology override and supplied discovery cues are rejected.

From this experiment directory:

```sh
python -B -m unittest tests.cache_channel_checks tests.channel_design_checks -v
python -m phase1.channel_design
```

The generator describes 24 baseline cells; it does not launch rollouts or claim
validation. Pressure interventions remain pending. Develop one environment at a
time, preserve negative outcomes, and obtain a fresh frozen 5.6 sol trace after
source changes. The automatic evaluator exports causal observations without
calling them intentional communication; semantic review remains a separate gate.
No new condition is ready merely because its offline tests pass.

See [the historical baseline](../../../docs/research/phase1-baseline.json) for
selected v98/r136 evidence, which does not validate the new profiles.
