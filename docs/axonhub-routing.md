# Model routing

All live SwarmHarm inference uses the AxonHub Responses endpoint:

`https://lmportal.iefbr14.xyz/v1/responses`

The host reads a scoped key from a `0600` file outside the repository. A key
must never enter a task, container, registration, trajectory, report or Git.

## Current routing policy

- Existing OpenRouter channels synchronize all models without a model filter and
  are eligible for automatic fallback.
- Eligible OpenAI requests prefer the existing TerryJwy channels. Other eligible
  channels remain fallback routes for the same fixed model identity.
- Session affinity is disabled. AxonHub may retry on ordinary provider failures
  and recognized credit exhaustion, but it must not substitute another model.
- Bare and provider-prefixed aliases may resolve to the same upstream model.
  Registration records the exact requested and upstream identities; collection
  rejects a response with a different model identity.
- Catalog membership does not prove which channel executed a request. Review the
  AxonHub execution record and keep routing interventions separate from behavioral
  evidence.

The selected development model is **`openai/gpt-6.1-sol`**. On 28 October
the user switched all subsequent rollouts to Sol. GLM and DeepSeek are no longer
scheduled comparisons. Historical evidence keeps its original model identity.
Changing the default does not validate the current environment on Sol.

Every fresh registration must query the upstream and authenticated AxonHub
catalogs again. Historical route checks do not validate a current rollout.

## Registration freeze

Before every rollout:

1. finish environment code, documentation and cleanup;
2. query the upstream and authenticated AxonHub model catalogs;
3. record exact model identities and catalog checks in a fresh registration;
4. commit and push the registration;
5. verify a clean worktree, matching local and remote commits, byte-identical
   registration files and sealed source/input hashes; and
6. edit no frozen source after preparation.

The maintained request settings are:

- API base: `https://lmportal.iefbr14.xyz/v1`;
- Responses endpoint: `https://lmportal.iefbr14.xyz/v1/responses`;
- reasoning effort: `high`;
- request timeout: 300 seconds with at most three transport attempts;
- maximum output: 16,384 tokens per response;
- provider concurrency: four for four simultaneously active agents;
- actor wall clock: 3,600 seconds; and
- rollout wall clock: 4,500 seconds.

The registration fixes the model and local request configuration. AxonHub
execution records establish the channel actually used. Provider errors, filters,
refusals, budget limits and behavioral outcomes remain separate evidence.
