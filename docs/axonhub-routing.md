# Model routing

All live SwarmHarm inference uses the AxonHub Responses endpoint:

`https://lmportal.iefbr14.xyz/v1/responses`

The host reads a scoped key from a `0600` file outside the repository. A key
must never enter a task, container, registration, trajectory, report or Git.

## Current routing policy

- **29 October 2026 test selection:** use only existing TerryJwy OpenAI channels
  for today's tests. Fallback may stay within that group, with the model fixed.
  This user selection overrides the general fallback policy below for these
  tests. The existing evaluation key now uses the saved profile
  `SwarmHarm-TerryJwy-OpenAI`, allowing only `TerryJwyethCO` and
  `TerryJwyappleCO`. Both upstream catalogs exposed Sol 6.1, Terra 6.1 and
  Luna 6; Terra was added to both channel model lists on 29 October before
  registration. No credential, spending cap, model substitution or other
  channel setting was changed. Inspect actual execution provenance as well.
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

The development default is **`openai/gpt-6.1-sol`**. The user also selected
**`openai/gpt-6.1-terra`** and **`openai/gpt-6-luna`** for the current matched
Knowledge Work comparison, each in its own registration. Other models require
explicit user selection. Historical evidence keeps
its original model identity; changing a default never validates a new route.

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
- request timeout: 300 seconds with one client POST attempt; unknown outcomes are retained without resending;
- maximum output: 16,384 tokens per response;
- provider concurrency: four for four simultaneously active agents;
- actor wall clock: 3,600 seconds; and
- rollout wall clock: 4,500 seconds.

The registration fixes the model and local request configuration. AxonHub
execution records establish the channel actually used. Provider errors, filters,
refusals, budget limits and behavioral outcomes remain separate evidence.
