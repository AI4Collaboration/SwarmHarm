# Experiments

## Current Phase 1 environment

[Procurement shared memory v1](procurement-shared-memory-v1/README.md) is the
active **Form the Swarm** component.

Two purchasing agents work in separate sandboxes on different supplier lines.
Each creates one compact reconciliation in the project register. Only after both
contexts end does a fresh closeout agent start. It must find, read and combine
both records in a different business task. The task does not name other agents
or ask for cooperation.

The environment uses three agent contexts, a 4 KiB memory cap, no added
pressure, Harbor 1.4 inputs, ATIF-v1.8 outputs and an independent provenance and
ledger reviewer.

## Runs

- **R3, current:** [report](procurement-shared-memory-v1/RESULTS-2026-10-23-DEEPSEEK-R3.md) ·
  [registration](procurement-shared-memory-v1/registrations/2026-10-23-deepseek-v41-r3/PROTOCOL.md) ·
  [review](procurement-shared-memory-v1/results/2026-10-23-deepseek-r3/independent-review.json).
  All five Phase 1 gates passed. It used 26 business responses, 34 tool results
  and 1,560 encoded memory bytes, with no retry, provider error, filter or
  recorded refusal.
- **R2:** [report](procurement-shared-memory-v1/RESULTS-2026-10-23-DEEPSEEK-R2.md).
  All five gates passed, but an ambiguous reference field caused avoidable
  searches and higher compute.
- **R1:** [preflight failure](procurement-shared-memory-v1/PRESTART-FAILURE-2026-10-23-R1.md).
  The collector rejected a provider-specific empty-argument encoding before any
  business context started. It is infrastructure evidence only.

## Claim boundary

The current result establishes compact persistent operational memory and
verified cross-context synthesis in one connected campaign. The closeout work
order naturally required supporting register records, so this is not evidence
that agents spontaneously invented a communication channel. No current run
establishes harmful method adoption, causal contagion, intent or a rate.

## Maintained components

The contained [product world](offline-product-world-v1/README.md), source-backed
[finance task](mimo-settlement-v2/README.md),
[legal-services task](mimo-legal-execution-v1/README.md) and procurement
environments remain candidate components for **Cause Harm**. Their outcomes and
limitations are indexed in [study history](../docs/history-index.md).

## Evidence rules

- A task directory's presence does not imply that it ran or passed.
- Frozen registrations, provider failures, invalid setups, negative results and
  behavioral evidence stay separate.
- Historical files remain unchanged. Current instructions live in the root
  README, the active experiment README and the running guide.
- New development uses at most two component trials or one minimum connected
  campaign per iteration, reviews every trace and changes one mechanism at a
  time.

[Running guide](../docs/running-evals.md) ·
[Format contract](../tasks/README.md) ·
[Prompt audit](prompt-contract/checks.py) ·
[Business outcome criteria](../docs/business-outcome-criteria.md)
