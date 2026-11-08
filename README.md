# SwarmForm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** SwarmForm tests whether they keep using that channel as new work arrives.

## Tonight’s plan · 8–9 November 2026

Build **5 shared deployments × 5 encoding opportunities × 4 business domains**, with **3 independent agents in each rollout**. The deployment and encoding opportunity define what one worker can change and another can observe. The trajectory shows how the agents actually use it.

**Input-ready** means four independently checked workloads, five exercised deployments and an evidence-backed disposition for all 100 candidate cells. **Live validation** requires a reviewed Sol 5.6 and Sol 6.1 rollout for each distinct admitted input. Report channel formation, sustained use and negative outcomes from the traces.

The Data Analysis workload passes offline. The other three workloads and the live matrix are pending. [Tonight’s tasks and acceptance criteria](docs/formation-study-design.md#overnight-work-and-acceptance-criteria) · [Matrix and domain tasks](docs/formation-study-design.md#three-axis-input-matrix) · [Channel taxonomy](docs/swarmform-coverage.md#shared-resource-and-encoding)

## Inspect the active input

From the repository root, use Python 3.12 to check the matrix and export the three private workstations with their later deliveries:

```sh
python3 scripts/check_swarmform_inputs.py
python3 scripts/inspect_swarmform_workload.py --staged --dataset-key november --output ../fulfillment-preview
```

[Live matrix status](docs/live-rollout-status.json) · [Reviewed four-agent pilot and SwarmHarm cases](docs/research/README.md)
