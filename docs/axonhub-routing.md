# Model routing

## Current Phase 1 policy

Phase 1 uses `openai/gpt-6.1-sol` and `openai/gpt-6.1-terra` through native
Codex and AxonHub, with high reasoning and goal off. Either model may qualify an
input. No Haiku or direct-API Phase 1 collection is selected.

All model-family harnesses route through AxonHub. OpenAI uses Codex; Anthropic
uses Claude Code when separately selected. A fallback may change the upstream
channel but must preserve the exact registered model identity. OpenRouter is a
fallback, not a different model condition. Catalog membership does not establish
which channel executed a request; retain the AxonHub execution record.

The scoped host key stays in a `0600` file outside the repository. It must never
enter a task, workstation, registration, trajectory, report or Git. Do not create
credentials, change spending limits or globally disable a channel as part of an
experiment.

## Registration freeze

Before a rollout:

1. finish source, input, documentation and offline checks;
2. query the authenticated AxonHub catalog for the exact model;
3. create and commit a fresh registration with model, native harness, reasoning,
   goal condition, budgets, route policy and hashes;
4. push it and verify clean local, remote and sealed commits; and
5. collect the registration once without editing frozen inputs.

After collection, verify the returned model identity and actual upstream channel.
Record provider failures, retries, filters and routing interventions separately
from model behavior. A failed channel does not prove the model unavailable.

Historical registrations retain their original routing and remain reproducible.
They do not define the current policy and are not silently reinterpreted.
