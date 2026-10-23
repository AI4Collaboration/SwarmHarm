# Experiments

## Current Phase 1 environment

[Swarm formation v2](swarm-formation-v2/README.md) is the active **Form the
Swarm** design.

Agents arrive in three periods and run in separate sandboxes. The same generic
persistent business cache carries actual exploratory residue, a later
agent-authored request and a different agent's independently discovered method.
There is no direct chat, dedicated request interface or assigned organization.
The minimum development campaign uses six agents; the population remains
configurable up to 128.

V2 has been specified from a source-level audit of LessWrong Stages 1–3. No v2
model inference has run yet.

**V1, preserved negative:** [report](swarm-formation-v1/RESULTS-2026-10-23-DEEPSEEK-R1.md) ·
[review](swarm-formation-v1/results/2026-10-23-deepseek-v41-r1/independent-review.json).
Its three-agent DeepSeek campaign opened requests through a dedicated interface
but produced no cross-agent fulfillment. It does not implement the Stage 1–3
formation sequence and is no longer the active setting.

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
