# Model routing

Every live model inference uses Pi SDK and the AxonHub Responses endpoint:

`https://lmportal.iefbr14.xyz/v1/responses`

The host reads a scoped key from a `0600` file outside the repository. A key
must never enter a task, container, registration, trajectory, report or Git.
Claude is selected by its AxonHub model ID and uses this same path. Direct
Claude Code, Codex and other subscription authentication cannot be selected for
a new live rollout. Those adapters remain only for offline compatibility tests
and historical evidence decoding. Historical direct-OpenRouter examples keep
their frozen provenance.

## Current routing policy

- **30 October 2026 selection:** use AxonHub's native failover, preferring
  eligible non-OpenRouter channels and retaining OpenRouter as fallback.
  The existing evaluation key uses `SwarmHarm-AxonHub-Fallback`: explicit
  failover, no channel allowlist, no model remapping and inherited disabled
  session affinity. This supersedes the earlier TerryJwy-only restriction.
  Existing Sol routes retain weights 100 for TerryJwyethCO and TerryJwyappleCO,
  50 for OpenRouter-Adam-OxRML and 0 for OpenRouter-Backup. Weights order
  eligible channels; they do not change the requested model.
  The global policy already permits four cross-channel retries and two
  same-channel retries, with a 1,000 ms delay. No global channel was disabled;
  credentials and quota settings were unchanged.
- Existing OpenRouter channels synchronize all models without a model filter and
  are eligible for automatic fallback.
- Eligible Sol requests prefer the existing TerryJwy channels. Other eligible
  channels remain fallback routes for the same fixed model identity.
- Session affinity is disabled. AxonHub may retry on ordinary provider failures
  and recognized credit exhaustion, but it must not substitute another model.
- Bare and provider-prefixed aliases may resolve to the same upstream model.
  Registration records the exact requested and upstream identities; collection
  rejects a response with a different model identity.
- Catalog membership does not prove which channel executed a request. Review the
  AxonHub execution record and keep routing interventions separate from behavioral
  evidence.
- Model provider does not change the harness: OpenAI, Anthropic and every other
  selected live model still run through Pi SDK and AxonHub. AxonHub may fall
  back only among eligible channels serving the same registered model.

The development default is **`openai/gpt-6.1-sol`**. The user also selected
**`openai/gpt-6.1-terra`** and **`openai/gpt-6-luna`** for the completed matched
Knowledge Work comparison, each in its own registration. Other models require
explicit user selection. Historical evidence keeps
its original model identity; changing a default never validates a new route.

Every fresh registration must query the upstream and authenticated AxonHub
catalogs again. Historical route checks do not validate a current rollout.

The 30 October 08:41 UTC connectivity check succeeded with the unchanged Sol
identity. AxonHub request #185988 records appleCO's 401 followed by successful
ethCO execution. This demonstrates native failover between those two channels;
OpenRouter is eligible but was not used in that check. The host-only probe and
UI evidence are stored outside Git. Routing checks are not behavioral results.

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
- request timeout: 300 seconds; Pi allows three retries after the first attempt,
  with provider-SDK retries disabled and every attempt retained;
- maximum output: 16,384 tokens per response;
- provider concurrency: four for four simultaneously active agents;
- actor wall clock: 3,600 seconds; and
- rollout wall clock: 4,500 seconds.

The registration fixes the model and local request configuration. AxonHub
execution records establish the channel actually used. Provider errors, filters,
refusals, budget limits and behavioral outcomes remain separate evidence.
