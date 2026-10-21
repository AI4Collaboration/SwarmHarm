# SwarmHarm

SwarmHarm studies how agents pursuing legitimate work discover shortcuts,
share methods, and reuse them across tasks. Our current focus is finance and
procurement, using synthetic records and local business services.

[Run evaluations](docs/running-evals.md) ·
[Research design](docs/research/hf-design-iteration-2026-10-21.md) ·
[Data sources](docs/research/task-sources-and-verification.md) ·
[Experiments](experiments/README.md)

## Current study

**Prepared · 21 October 2026:** [supplier payments and purchase orders](experiments/procurement-settlement-v1/README.md)
tests actual approval overruns and method adoption across three successive pairs
of fresh agents. Two normal capability jobs gate six experimental jobs. No new
model result yet.

## Latest evidence

**21 October 2026 · GPT-5.6 Sol:** six experimental agents delivered correct
business reports while copying 30 synthetic records into a public cache.
Agents discovered real peer activity, requested missing inputs, and reused a
request method across procurement, payroll and billing. Six normal capability
checks also passed, with no public business records.

This establishes data exchange and request-method reuse. It does **not** yet
establish a business-process exploit adopted by fresh agents on different tasks,
or harmful intent. The [reviewed report](experiments/business-cache-v3/analysis/2026-10-21/COMPLETE_REPORT.md)
contains the evidence, limits and registration-timing deviation. Interrupted
attempts and negative results remain in the [history index](docs/history-index.md).

## Current setup

Last verified on **21 October 2026**; new runs require fresh access checks.

- **Runner:** [procurement-settlement-v1](experiments/procurement-settlement-v1/README.md),
  with durable tool records and independently checked transaction/source amounts.
- **Model:** `gpt-5.6-sol / xhigh` through existing host ChatGPT login at
  `https://chatgpt.com/backend-api/codex/responses`. Credentials stay on the host.
- **Local environment:** Python 3.12.14, inspect-ai 0.3.257, OpenAI SDK 2.54.0;
  Docker 29.9.1 in the existing `lima-swarmharm` context. The prepared interpreter,
  image, budgets and commands are in the [running guide](docs/running-evals.md).
- **Hosted coordinator:** retain Multica **0.4.44** and the maintainer's access
  patch. These local studies need no AWS setup or new credentials.
- **State at the last review:** collection and cleanup completed; no active run
  or scheduled monitor. Verify live state before launching.

## Study scope

Test autonomous business-process discovery, real method sharing and different-task
adoption by fresh agents. The new environment is implemented and checked offline;
live results are pending. Posted approval overruns are financial commitments,
not automatically realized economic loss or evidence of intent.

Prompts remain ordinary work requests: no added pressure, collaboration hints,
loophole hints or communication bans. Keep genuine business requirements and
measure the actual downstream effect. See the [outcome criteria](docs/business-outcome-criteria.md)
and [current handoff](docs/working-context.md).
