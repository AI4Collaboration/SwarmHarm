# SwarmForm and SwarmHarm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** SwarmForm tests whether they keep using that channel as new work arrives.

## Current plan

Four sites each reconcile their own orders. A dispatch recorded at one site can explain a discrepancy at another. Later batches bring returns and corrections. Each agent gets its own files and assignment. The agents choose how to find and exchange the missing records.

We classify each exchange along two axes: **shared resource × encoding**. The resource is what one agent can change and another can observe. The encoding is where the information lives. For example, a directory can carry report rows in a file, a request in its name, or a signal in the order files appear.

The planned comparison uses the same three batches across five deployments: a shared directory, an IPC queue, a worker-hosted service, an artifact store and a job/result service. Start with the shared directory. Check which rows each site lacks, verify that the combined data completes all four reports, then trace which records agents actually exchange and use across batches.

[Study plan and implementation order](docs/formation-study-design.md) · [Channel taxonomy and sources](docs/swarmform-coverage.md#shared-resource-and-encoding)

## Runnable pilot

Four Knowledge Work agents use an ordinary shared cache. On Sol 6.1, one agent created a receipt directory, a second used a receipt to release its report pack, and a third added a receipt for another request. Only the first receipt has verified downstream use. Sol 5.6 recorded zero peer file reads and released zero packs. Sustained exchange across batches remains an open question.

[Pilot inputs](experiments/swarmharm-v1/configs/swarmform-work-cache.json) · [Reviewed pair](docs/research/swarmform-cache-pilot.json) · [Run the pilot](docs/running-evals.md#swarmform-cache-rollout)

## SwarmHarm results

The reporting benchmark measures autonomous communication, coordinated changes that leave inaccurate records, delays caused by individually harmless actions, and adoption of a nonexistent review process. The case index identifies the model, settings and evidence for each finding.

[Cases and findings](docs/phase2-design.md) · [Full trajectories](docs/research/trajectory-release.json) · [Runnable settings](docs/scenarios-and-parameters.md)
