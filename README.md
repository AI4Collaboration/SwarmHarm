# SwarmHarm

SwarmHarm studies whether agents cross boundaries to complete legitimate tasks,
and whether other agents discover and reuse those methods. Current experiments
use synthetic healthcare and finance tasks in contained local environments.

**20 October: natural task inputs only.** Source permissions are discovered
through normal service queries. Extra opening ACLs, restricted-source labels and
cache-permission reminders are removed; the upfront condition is retired.

## Latest result · 19 October 2026

**The matched Sol screen is complete: 60 workers, five settings, two rounds.**
Baseline worlds each had 3/6 workers read restricted caches and use their own
private data. One peer-method/different-object sequence was verified.

Calibration, trace replay and format checks passed, without provider errors or
safety filters. Two worlds per setting are an initial screen. The upfront
condition remains historical intervention evidence and is excluded from future
natural-task comparisons.

[Report and evidence](experiments/sol-factor-v1/RESULTS.md)

## Current setup

- Latest tested model: **Sol / xhigh**, through the existing local Codex login.
  [Verified 19 October](experiments/sol-factor-v1/results/2026-10-19-r1/provider-summary.json).
  No AWS is needed for this runner.
- Subject tools access in-memory business data, with no shell, network or host-file
  access. Current inputs use neutral instructions and no front-loaded permissions.
  The [20 October correction](docs/prompt-audit-2026-10-20.md) is verified offline;
  the latest completed model run remains 19 October.
- Collection has stopped; no scheduled monitor is active. Keep patched
  **Multica 0.4.44** when using the hosted coordinator.

## Run and read more

- [Setup and running evaluations](docs/running-evals.md)
- [Earlier experiments and negative results](docs/history-index.md)
- [Current project context](docs/working-context.md)
