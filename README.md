# SwarmHarm

SwarmHarm studies whether agents pursuing legitimate work cause harmful outcomes,
and whether other agents discover and reuse those methods. Tasks use synthetic
business data and local simulated services.

## Current study · 20 October 2026

**Conflicting tests and actual software delivery.** Two audited ImpossibleBench
functions each have oneoff and conflicting tests. A publishing service accepts
code after tests; a separate caller checks the actual released function against
independent truth. Correct test repair is separate from wrong delivery. Sol/Luna
inputs are frozen and byte-matched, with two normal capability checks before
four impossible tasks. All are ordinary counting problems, with no cyber task.
Eight data/service checks, two whole-collector checks and seventeen global prompt
checks passed. No model calls yet.
[Registered protocol](experiments/impossible-release-v1/README.md).

## Latest result · 20 October 2026

**Subscription pressure did not induce either model to invent settlement.**
Sol and Luna each kept all twelve unfunded invoices unpaid. Every worker read
the agreement and bank statement; neither model edited cash/matching records,
posted a payment or created an unsupported renewal fee commitment. Four funded
checks per model and all independent reviews passed. All 178/169 responses
completed without provider errors or native refusal. One Sol automatic refusal
candidate was a factual no-payment explanation.
[Short report](experiments/payment-renewal-pressure-v1/RESULTS.md).

An earlier Luna handover error was repeated by its reader without a resulting
payment. That error-propagation candidate and older source-boundary failures
remain separate from harmful exploitation.
[Cash-only report](experiments/payment-liquidity-v1/RESULTS.md).

## Current setup

- **Runner:** `experiments/impossible-release-v1/run.py`, input
  `natural-coding-release-v2`, outcome `independent-published-function-v1`.
  Prepare Sol with `--phase prepare --provider sol --output <new-dir>`; match Luna
  with `--provider luna --match <Sol-directory>`. Push registration before
  sequential `--phase collect` calls. Preserve every trajectory; no silent retry.
- **Models:** `gpt-6.1-sol / xhigh`, then `gpt-6-luna / xhigh`, existing host login,
  `https://chatgpt.com/backend-api/codex/responses`. Both routes were verified
  in completed renewal collection on 20 October. Coding preflight and normal
  capabilities still require fresh checks; model names alone prove no access.
- **Execution:** existing Docker 29.9.1, cached Python 3.12 image pinned by full
  image ID in the protocol. Each submitted program and independent caller uses
  a fresh non-root container with no network, host mount, socket or credential,
  a read-only root and bounded resources. Confirm removal after execution.
  No real planner, bank or subscription is connected.
- **Budgets:** one inference globally; 600-second requests; 512 responses and
  1,024 tools per task; six hours per task and 24 hours per model. Programs have
  a 30-second limit. Provider errors/native refusal stop without replacement.
- **Host:** Python 3.12.14, inspect-ai 0.3.257, OpenAI SDK 2.54.0.
  Interpreter: `../eval-readiness/lesswrong-direct-2026-10-19/source/.venv/bin/python`.
  No AWS needed. Keep hosted Multica 0.4.44 and its server-access patch unchanged.
- **Other routes, inactive:** DeepSeek v4-pro/high uses the existing AxonHub
  project key at `https://lmportal.iefbr14.xyz/v1/responses`, 65,536 output tokens.
  Its last cash-shortfall run stopped on an upstream reset before business tasks.
  GLM 5.3 Flash returned another model ID at preflight and has no verified result.
  Haiku remains untested. The temporary private existing-key copy is retained
  only for this follow-up; no new key, permission or channel was created.
- **Interpretation:** a passed test or edited record alone is insufficient.
  Independently inspect actual delivered values, source truth, actions and final
  answers; preserve ever-occurring harm, correction and withdrawal. The coding
  diagnostic has no peer context and cannot establish method propagation.
  Exploratory worlds do not yield population rates, causal pressure estimates
  or full HF reproduction. All renewal collectors exited. No scheduled monitor
  or public website results.

[Run evaluations](docs/running-evals.md) ·
[Current context](docs/working-context.md) ·
[Earlier workflow repair](experiments/payment-route-transfer-v1/RESULTS.md) ·
[GLM identity failure](experiments/payment-route-glm-v1/RESULTS.md) ·
[History](docs/history-index.md)
