# Experiments

## Current Phase 1 environment

[Swarm formation v1](swarm-formation-v1/README.md) is the active **Form the
Swarm** environment.

Three independently tasked purchasing agents run in separate sandboxes. They
have no direct chat and receive no leader, team, pair, sender, receiver or
cooperation assignment. The shared business system starts empty. A formation
edge exists only when one agent requests a missing document, another discovers
and supplies it, and the requester uses the exact document in an issued order.

Development defaults to three agents; deployment configuration is capped at
128. Sparse views use indexed local-neighborhood reads rather than population
scans. Persistent records allow 32 KiB each. Private agent histories stay
separate and are sent in full without automatic compaction. Inputs use Harbor
1.4, outputs use ATIF-v1.8, and an independent reviewer reconstructs the observed
graph from native events. The implementation is validated and pushed; no live
formation run has started yet. A dedicated host-only AxonHub key and the exact
DeepSeek Flash route have been verified for the next frozen run.

## Prior mechanism runs

- **R3, current:** [report](procurement-shared-memory-v1/RESULTS-2026-10-23-DEEPSEEK-R3.md) ·
  [registration](procurement-shared-memory-v1/registrations/2026-10-23-deepseek-v41-r3/PROTOCOL.md) ·
  [review](procurement-shared-memory-v1/results/2026-10-23-deepseek-r3/independent-review.json).
  All five shared-memory gates passed. It used 26 business responses, 34 tool results
  and 1,560 encoded memory bytes, with no retry, provider error, filter or
  recorded refusal.
- **R2:** [report](procurement-shared-memory-v1/RESULTS-2026-10-23-DEEPSEEK-R2.md).
  All five gates passed, but an ambiguous reference field caused avoidable
  searches and higher compute.
- **R1:** [preflight failure](procurement-shared-memory-v1/PRESTART-FAILURE-2026-10-23-R1.md).
  The collector rejected a provider-specific empty-argument encoding before any
  business context started. It is infrastructure evidence only.

## Claim boundary

The prior result establishes compact persistent operational memory and verified
cross-context synthesis in one arranged campaign. It is not evidence that agents
spontaneously formed a swarm. No current run establishes spontaneous formation,
harmful method adoption, causal contagion, intent or a rate.

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
