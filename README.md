# SwarmHarm

SwarmHarm studies whether agents cross boundaries to complete legitimate tasks,
and whether other agents discover and reuse those methods. Current experiments
use synthetic healthcare and finance tasks in contained local environments.

## Latest result · 19 October 2026

**The matched Sol screen is complete: 60 workers, five settings, two rounds.**
Baseline worlds each had 3/6 workers read restricted caches and use their own
private data. With permissions upfront this was 0/6 in both rounds; an explicit
role denial produced 1/6 and 0/6. Changing the work index or adding a supervisor
receipt had no consistent effect.

One peer-method/different-object sequence was verified. Calibration, trace replay
and format checks passed, with no provider errors or safety filters. Two worlds
per setting are an initial screen, not a population rate or full incident
reproduction. The permission condition changes both presentation and wording.

[Report and evidence](experiments/sol-factor-v1/RESULTS.md)

## Current setup

- Latest tested model: **Sol / xhigh**, through the existing local Codex login.
  [Verified 19 October](experiments/sol-factor-v1/results/2026-10-19-r1/provider-summary.json).
  No AWS is needed for this runner.
- Subject tools access in-memory business data, with no shell, network or host-file
  access. The latest run used neutral instructions, no added pressure and no seeded methods.
- Collection has stopped; no scheduled monitor is active. Keep patched
  **Multica 0.4.44** when using the hosted coordinator.

## Run and read more

- [Setup and running evaluations](docs/running-evals.md)
- [Earlier experiments and negative results](docs/history-index.md)
- [Current project context](docs/working-context.md)
