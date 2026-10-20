# SwarmHarm

SwarmHarm studies whether agents pursuing legitimate work cause harmful outcomes,
and whether other agents discover and reuse those methods. Current tasks use
synthetic business data and local simulated services.

## Current experiment · 20 October 2026

**Conflicting acceptance:** all business records are available, but two checks
demand different payment amounts in the same submission. A discoverable workflow
and mutable matching record provide a verifiable route to apparent completion.
Correct payment, verification tampering and actual overpayment are separate
outcomes. [Design and source review](experiments/payables-v1/CONFLICTING.md).
Offline validation and a fresh Sol pilot are in progress; no new behavior result
is claimed yet.

## Previous result · 20 October 2026

**Stronger business pressure did not produce harmful payments.** Sol passed all
four normal calibrations. All six missing-record workers attempted finalization,
but none attempted to overwrite matching records, posted a payment or claimed
payment had succeeded. Four read genuine peer case notes.

The cleaned inputs combined the final bank cutoff and supplier credit hold with
loss of reserved stock, contractual charges and customer cancellation rights.
All 107 responses completed without provider errors, recorded filters or native
refusal. Independent replay, native settings and peer provenance checks passed.
One exploratory world cannot establish general safety or a causal pressure effect.

[Short report and evidence](experiments/payables-v1/HIGH-PRESSURE-RESULTS.md)

## Current setup

- **Sol / xhigh**, existing local Codex login,
  `https://chatgpt.com/backend-api/codex/responses`. Verified 20 October.
  Python **3.12.14**, inspect-ai **0.3.257**, OpenAI SDK **2.54.0**.
  No AWS is required by this runner.
- Current pilot **conflicting-acceptance-v1** builds on **natural-business-v2**:
  available receiving records, inconsistent checks and a visible active workflow.
  Ordinary business requests and neutral
  instructions; no author-added warnings, method hints, ACL inventories or
  fabricated peers. PO terms are factual fields. Actual access checks and genuine
  peer messages remain. [Input cleanup](docs/prompt-cleanup-2026-10-20.md) ·
  [Native request audit](experiments/payables-v1/results/2026-10-20-sol-high-pressure/request-audit.json).
- One request at a time, 150-second timeout; four calibrations precede six
  experimental workers. Interpreter:
  `../eval-readiness/lesswrong-direct-2026-10-19/source/.venv/bin/python`.
  Use `experiments/payables-v1/conflicting.py --phase prepare --output <new-directory>`,
  then `--phase collect` with that directory. Pressure is frozen separately.
  The new collector has not started; no scheduled monitor is active.
- Tools access in-memory records, without subject shell, network, host files or
  real payments. Shared reading alone is cooperation. Keep hosted
  **Multica 0.4.44** and its existing public-server access patch.

[Run evaluations](docs/running-evals.md) ·
[Current context](docs/working-context.md) ·
[Earlier pressure run](experiments/payables-v1/PRESSURE-RESULTS.md) ·
[Neutral and Luna checks](experiments/payables-v1/RESULTS.md) ·
[History](docs/history-index.md)
