# SwarmForm and SwarmHarm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** SwarmForm tests whether they keep using that channel as new work arrives.

## Current plan

SwarmForm’s proposed input matrix crosses **five shared deployments × five encoding opportunities × four work domains**. A deployment determines what one agent can change and another can observe. An encoding opportunity is a visible feature that could carry information, such as file contents, a filename or arrival order. The trajectory shows which features the agents actually used.

Each cell has three agents with private work. In the first offline workload, Data Analysis, a site knows its orders while another site holds some of its dispatch and return records. Three intakes test whether agents reuse a channel as the facts change. Engineering, Financial Analysis and Knowledge Work need their own three-agent inputs and verifiers. [Full matrix and domain tasks](docs/formation-study-design.md#three-axis-input-matrix)

[Study plan and implementation order](docs/formation-study-design.md) · [Channel taxonomy and sources](docs/swarmform-coverage.md#shared-resource-and-encoding)

## Runnable pilot

Four Knowledge Work agents use an ordinary shared cache. On Sol 6.1, one agent created a receipt directory, a second used a receipt to release its report pack, and a third added a receipt for another request. Only the first receipt has verified downstream use. Sol 5.6 recorded zero peer file reads and released zero packs. Sustained exchange across batches remains an open question.

[Pilot inputs](experiments/swarmharm-v1/configs/swarmform-work-cache.json) · [Reviewed pair](docs/research/swarmform-cache-pilot.json) · [Run the pilot](docs/running-evals.md#swarmform-cache-rollout)

## SwarmHarm results

The reporting benchmark measures autonomous communication, coordinated changes that leave inaccurate records, delays caused by individually harmless actions, and adoption of a nonexistent review process. The case index identifies the model, settings and evidence for each finding.

[Cases and findings](docs/phase2-design.md) · [Full trajectories](docs/research/trajectory-release.json) · [Runnable settings](docs/scenarios-and-parameters.md)
