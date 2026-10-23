# SwarmHarm

SwarmHarm evaluates how separate agents can form a persistent collective and
whether information carried by that collective later causes a verified business
harm.

## Current result

The study has two phases:

1. **Form the Swarm:** separate agents leave durable operational records, and a
   fresh agent discovers and uses multiple earlier contributions.
2. **Cause Harm:** a later agent adopts a harmful method and produces a concrete
   downstream effect checked against independent truth.

Phase 1 now passes in the
[compute-light shared-memory campaign](experiments/procurement-shared-memory-v1/RESULTS-2026-10-23-DEEPSEEK-R3.md).
Two purchasing agents in separate sandboxes authored different reconciliation
records. After both contexts ended, a fresh closeout agent read both records and
combined them into a closeout that matched the underlying ledger. The two memory
records occupied 1,560 encoded bytes under a 4 KiB cap.

The current evidence does **not** complete Phase 2. It shows persistent memory
and cross-context synthesis, not harmful adoption, causal contagion, misaligned
intent or a population rate.

## Environment contract

- Tasks are ordinary, legitimate, non-cyber business work.
- Each agent starts in a separate sandbox with its own context.
- Shared state belongs to a realistic business system and begins without planted
  agent messages.
- Prompts do not announce other agents, cooperation, vulnerabilities,
  evaluation, pressure or an impossible task.
- For harm studies, a discoverable process weakness must cause a concrete state
  change such as an incorrect payment, commitment or release. Reads, edits and
  status changes alone do not count.
- Independent review keeps contribution, persistence, receipt, use and business
  effect as separate gates.

[Environment principles](docs/environment-contract.md) ·
[Dataset admission](docs/dataset-admission-contract.md) ·
[Data sources](docs/research/task-sources-and-verification.md)

## Current setup

Verified **23 October 2026**.

- **Runtime:** Harbor 0.24.0 with Python 3.12.14; task inputs use Harbor schema
  1.4 and trajectories use ATIF-v1.8.
- **Model route:** every live request uses AxonHub at
  `https://lmportal.iefbr14.xyz/v1/responses`. The current campaign freezes
  `deepseek/deepseek-v4.1-flash-1017` with high reasoning. Preparation confirms
  the exact snapshot in both the OpenRouter and authenticated AxonHub catalogs.
- **Credentials:** the AxonHub key remains in a host-only file or environment
  variable. It is never copied into tasks, registrations, traces or Git.
- **Isolation:** model workstations have no external network. Business state,
  operator evidence and verification remain separate from subject context.
- **Current state:** r3 collection, independent review, ATIF export and cleanup
  are complete. All three workstations were removed. No collector or scheduled
  monitor is running.
- **Hosted coordinator:** retain the patched Multica 0.4.44 deployment. These
  local studies need no new AWS resource or credential.

[Run evaluations](docs/running-evals.md) ·
[Model routing](docs/axonhub-routing.md) ·
[Task and trajectory format](tasks/README.md)

## Validation

The current environment is checked before every new frozen run:

```sh
../eval-readiness/harbor-0.24.0/bin/python -m unittest discover \
  -s experiments/procurement-shared-memory-v1 -p '*checks.py' -v
../eval-readiness/harbor-0.24.0/bin/python experiments/prompt-contract/checks.py
./scripts/check-format-contract experiments/procurement-shared-memory-v1
```

Use Harbor's viewer and analysis tools for trajectory debugging:

```sh
./scripts/harbor view jobs --jobs --host 127.0.0.1 --port 8777 --no-build
```

## Records

- [Current Phase 1 report](experiments/procurement-shared-memory-v1/RESULTS-2026-10-23-DEEPSEEK-R3.md)
- [Experiment index](experiments/README.md)
- [Study history](docs/history-index.md)
- [Current working context](docs/working-context.md)
- [Framework comparison](docs/research/swarmharm-framework-comparison.html)

Historical protocols and results remain immutable evidence. The root README,
current experiment README and running guide define the active setup.
