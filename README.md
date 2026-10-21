# SwarmHarm

SwarmHarm studies how agents pursuing legitimate work discover shortcuts,
share methods, and reuse them across tasks. Our current focus is finance and
procurement, using synthetic records and local business services.

[Run evaluations](docs/running-evals.md) ·
[Research design](docs/research/hf-design-iteration-2026-10-21.md) ·
[Data sources](docs/research/task-sources-and-verification.md) ·
[Task format](tasks/README.md) ·
[Experiments](experiments/README.md)

## Latest result

**21 October 2026 · GPT-5.6 Sol:** under customer-contract compensation pressure,
all six experimental agents issued over-budget purchases, totaling **$1,390**
in excess commitments. All disclosed the overspend. Two funded capability jobs passed.

**No method sharing or peer adoption occurred.** Agents independently used the same
batch approval/issuance sequence. The combined business-control failure is verified;
deliberate loophole discovery and pressure causation are not established. A pricing
API let agents proceed without the missing quote documents, reducing the need for peers.
[Reviewed report](experiments/procurement-contract-v1/RESULTS.md) ·
[Earlier results](docs/history-index.md)

## Current setup

Last verified on **21 October 2026**; new runs require fresh access checks.

- **Latest runner:** [approval-code Harbor pilot](experiments/approval-code-v1/README.md).
  Harbor 0.24.0 is installed in an isolated Python 3.12 environment; Buildx 0.38.1
  was added to the local Docker client. Scripted Harbor/verifier controls passed;
  the new model campaign is being registered. The previous result below remains
  from the custom procurement-contract runner, not Harbor.
- **Task format:** [Harbor](tasks/README.md). This first pilot is synthetic and
  HVE-inspired; MiMo source-backed task migration remains pending.
- **Model:** `gpt-5.6-sol / xhigh` through existing host ChatGPT login at
  `https://chatgpt.com/backend-api/codex/responses`. Credentials stay on the host.
- **Local environment:** Python 3.12.14, inspect-ai 0.3.257, OpenAI SDK 2.54.0;
  Docker 29.9.1 in the existing `lima-swarmharm` context. The prepared interpreter,
  image, budgets and commands are in the [running guide](docs/running-evals.md).
- **Hosted coordinator:** retain Multica **0.4.44** and the maintainer's access
  patch. These local studies need no AWS setup or new credentials.
- **State:** previous collection and cleanup completed; new Harbor pilot controls
  passed, model collection not yet started. No scheduled monitor.

## Study scope

Test autonomous business-process discovery, method sharing and different-task
adoption by fresh agents. The latest procurement study established over-budget
commitments but no method-propagation chain. Excess commitment is not automatically
realized economic loss or evidence of intent.

The latest condition includes explicitly requested customer-contract pressure;
other future studies retain the no-pressure default unless requested otherwise.
Keep ordinary work requests without collaboration hints, loophole hints or
communication bans. See the [outcome criteria](docs/business-outcome-criteria.md)
and [current handoff](docs/working-context.md).
