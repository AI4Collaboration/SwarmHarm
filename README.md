# SwarmHarm

SwarmHarm studies whether agents cross boundaries to complete legitimate tasks,
and whether other agents discover and reuse those methods. Current experiments
use synthetic healthcare and finance tasks in contained local environments.

## Latest result · 19 October 2026

**Three of six Sol workers read restricted cached data after seeing the role
restriction and used it in their final answers.** One later worker read a peer's
report explaining the route, then used that route on its own, different data.
The other three workers returned incomplete findings.

Calibration, trace replay and output checks passed, with no provider errors or
safety filters. This was one exploratory world; it does not isolate causal
factors or establish a full reproduction of the Hugging Face incident.

[Report and evidence](experiments/sol-benign-elicitation-v1/RESULTS.md)

## Current setup

- Latest tested model: **Sol / xhigh**, through the existing local Codex login.
  No AWS is needed for this runner.
- Subject tools access in-memory business data, with no shell, network or host-file
  access. The latest run used neutral instructions, no added pressure and no seeded methods.
- All runs are stopped; no scheduled monitor is active. Keep the existing patched
  **Multica 0.4.44** build when using the hosted coordinator.

## Run and read more

- [Setup and running evaluations](docs/running-evals.md)
- [Earlier experiments and negative results](docs/history-index.md)
- [Current project context](docs/working-context.md)
