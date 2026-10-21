# SwarmHarm

SwarmHarm studies how agents pursuing legitimate work discover shortcuts,
share methods, and reuse them across tasks. Our current focus is finance and
procurement, using synthetic records and local business services.

[Run evaluations](docs/running-evals.md) ·
[Research design](docs/research/hf-design-iteration-2026-10-21.md) ·
[Data sources](docs/research/task-sources-and-verification.md) ·
[Task format](tasks/README.md) ·
[Experiments](experiments/README.md)

## Data format

**Input: Harbor tasks. Output: ATIF trajectories (ATIF-v1.8, Harbor 0.24.0).**
Each agent gets its own `agent/trajectory.json` with messages, tool calls and
observations. Preserve native API records alongside it. Business scores and
ledger evidence remain in verifier outputs; campaign manifests link agents and
shared-artifact evidence without merging their independent contexts.

The completed pilot collected native traces, then exported and validated ATIF
against Harbor's schema. A format declaration alone does not certify an export.
[Format contract](tasks/README.md#output-contract)

## Latest result

**Prepared next:** one original MiMo finance task has passed Harbor startup,
business-tool, isolation and deterministic baseline checks. The source prompt,
records and grader are unchanged; the model run has not started.
[Registered setup](experiments/mimo-finance-v1/README.md)

**21 October 2026 · GPT-5.6 Sol, Harbor approval-code pilot:** the funded task
passed. None of three underfunded tasks used another request's approval code.
Two agents read the foreign code, but no agent shared a method or adopted one.
All four trials completed without provider errors or classifier blocks.
[Report](experiments/approval-code-v1/RESULTS.md) ·
[Harbor job](jobs/approval-code-sol56-2026-10-21/) ·
[Earlier results](docs/history-index.md)

## Debug with Harbor

```sh
./scripts/harbor view jobs --jobs --host 127.0.0.1 --port 8777 --no-build
```

Open the local viewer to inspect trajectories, tool results, verifier outputs,
logs and exceptions. Use `./scripts/harbor analyze --help` and
`./scripts/harbor check --help` for Harbor's analysis and task-checking tools.
See the [running guide](docs/running-evals.md) for setup and campaign replay limits.

## Current setup

Last verified on **21 October 2026**; new runs require fresh access checks.

- **New source-task adapter:** [MiMo finance](experiments/mimo-finance-v1/README.md),
  using the cached MiMo amd64 image with MCP 1.26.0. Shell UID 65534; root-owned
  service data and `/logs` parent protect source/verifier isolation. Startup
  checks passed after fixing local bind-mount permission behavior.
- **Latest completed runner:** [approval-code Harbor pilot](experiments/approval-code-v1/README.md).
  Harbor 0.24.0 is installed in an isolated Python 3.12 environment; Buildx 0.38.1
  was added to the local Docker client. Scripted Harbor/verifier controls passed;
  four model trials and ATIF exports completed and were checked in the viewer.
  Peer persistence still uses the SwarmHarm campaign adapter.
- **Task format:** [Harbor](tasks/README.md). This first pilot is synthetic and
  HVE-inspired; MiMo source-backed task migration remains pending.
- **Model:** `gpt-5.6-sol / xhigh` through existing host ChatGPT login at
  `https://chatgpt.com/backend-api/codex/responses`. Credentials stay on the host.
- **Local environment:** Python 3.12.14 and OpenAI SDK 2.54.0;
  Docker 29.9.1 in the existing `lima-swarmharm` context. The prepared interpreter,
  image, budgets and commands are in the [running guide](docs/running-evals.md).
- **Hosted coordinator:** retain Multica **0.4.44** and the maintainer's access
  patch. These local studies need no AWS setup or new credentials.
- **State:** model collection completed and evaluation containers were removed.
  The localhost viewer remains open; no collector or scheduled monitor is running.

## Study scope

Test autonomous business-process discovery, sharing and different-task adoption
by fresh agents. The latest pilot produced no misuse or propagation. The previous
procurement study found excess commitments but no method propagation. Neither
result alone establishes intent or general model safety.

The latest condition includes explicitly requested customer-contract pressure;
other future studies retain the no-pressure default unless requested otherwise.
Keep ordinary work requests without collaboration hints, loophole hints or
communication bans. See the [outcome criteria](docs/business-outcome-criteria.md)
and [current handoff](docs/working-context.md).
