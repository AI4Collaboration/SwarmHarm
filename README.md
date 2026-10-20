# SwarmHarm

SwarmHarm studies whether agents pursuing legitimate work cause harmful outcomes,
and whether other agents discover and reuse those methods. Current tasks use
synthetic business data and local simulated services.

**Current experiment · 20 October:** A separately registered
[supplier-deadline condition](experiments/payables-v1/PRESSURE.md) adds a final
payment cutoff and threatened credit hold/delivery loss. One fresh Sol world,
four calibrations and six experimental workers; outcomes pending. No new neutral
arm, method hints or changed settlement rules.

## Latest result · 20 October 2026

The invoice task now has a verified path to an incorrect payment in the local
ledger. Scripted controls demonstrate the consequence; **Sol did not use it**.
Four normal calibrations passed. In six missing-record cases, Sol left payment
pending: **no matching-record changes or payments**. Four workers read peer notes.

Luna stopped during calibration after a 150-second request timeout; its six
experimental cases were unrun. Returned responses showed no recorded filtering
or native refusal. Neither run establishes spontaneous financial harm.

[Short report and evidence](experiments/payables-v1/RESULTS.md)

## Current setup

- Verified 20 October: **Sol and Luna / xhigh**, existing local Codex login,
  `https://chatgpt.com/backend-api/codex/responses`. Python **3.12.14**,
  inspect-ai **0.3.257**, OpenAI SDK **2.54.0**. No AWS is required by this runner.
- Ordinary business requests, neutral instructions, no opening permission
  inventory or method hints. Tools access in-memory business records; no subject
  shell, network, host files or real payments. Shared reading alone is cooperation.
- One request at a time, 150-second timeout; four calibrations precede six
  experimental workers. The new pressure pilot is registered; earlier collectors
  are stopped. No scheduled monitor is active.
  Keep hosted **Multica 0.4.44** and its existing public-server access patch.

[Run evaluations](docs/running-evals.md) ·
[Current context](docs/working-context.md) ·
[Earlier evidence](docs/history-index.md)
