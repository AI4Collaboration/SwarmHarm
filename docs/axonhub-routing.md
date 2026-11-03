# Model routing

## Standing user policy — 3 November 2026

OpenAI models use the **Codex harness**. Anthropic Claude models use the
**Claude Code (CC) harness**. **All model API traffic goes through AxonHub**,
including internal model requests made by either harness. This supersedes the
previous Pi default and optional direct-subscription routing for new work.
Claude giftcard remains preferred, with OpenRouter as same-model fallback
inside AxonHub. Do not silently change the model, harness or gateway.

This is a persistent operating requirement, not a claim that both adapters
already support or have validated the gateway route. Implement and validate any
missing adapter support before fresh collection; register the actual harness,
model, gateway and evidence limits. Preserve all historical registrations and
raw traces with their original provenance. Current Phase 1 model selection
remains Haiku 5.5, Engineering only.

AxonHub service root: `https://lmportal.iefbr14.xyz`.
The historical Pi Responses endpoint is
`https://lmportal.iefbr14.xyz/v1/responses`; select the appropriate supported
AxonHub protocol for each native harness rather than assuming every harness
uses Responses.

The host reads a scoped key from a `0600` file outside the repository. A key
must never enter a task, container, registration, trajectory, report or Git.

## Claude gateway adapter — implementation under validation

The registered `claude-code` path with a host `--key-file` uses AxonHub's
Anthropic Messages protocol. Authentication is an isolated child-process bearer
token, with a private temporary Claude configuration directory and no inherited
personal subscription or direct-provider keys. Default model aliases, including
internal small-model selection, are pinned to the requested canonical identity.
The native stream accepts only that canonical ID or its explicitly registered
Anthropic spelling. The raw spelling is retained; a different version is rejected.

The SDK owns its loop and only the registered controller MCP tools can execute
business actions. Its stock Claude Code system preset is a separate harness
condition from historical Pi. Controller projections are checked against native
SDK calls, public text and delivered returns; full provider HTTP context remains
unobservable. Legacy subscription adapters remain for historical reproducibility,
not as an authorized bypass of AxonHub for new work. The Codex gateway path still
needs separate implementation/validation before future OpenAI collection; no
OpenAI rollout is currently selected.

## Haiku selection — 3 November 2026

The user selected Haiku 5.5 for an Engineering-only Phase 1 comparison, with
TerryGiftcard preferred and OpenRouter fallback. The automatic giftcard model
fetch listed a dated Haiku 4.5 but omitted the manually configured 5.5 models;
that list alone does not establish the subscription's actual model eligibility.
The test pins `anthropic/claude-haiku-5.5`; giftcard's manually configured
`claude-haiku-5-5` and canonical alias are configured. Giftcard channel health
requests completed for Sonnet 5.5 (#210228), Haiku 5.5 (#210236) and Opus 5.5
(#210237), with matching returned model IDs and stop completions. These small
channel checks do not validate the Pi tools/reasoning preflight or Phase 1 behavior.
The default health-test model was restored to Sonnet 5.5 after the checks.
Evidence: `../eval-readiness/phase1-claude-channel-tests-20261103-r1/manifest.json`.
No model fallback to 4.5 is authorized by this registration. The prior added
4.5 model/alias is retained separately and has received no test requests.
TerryGiftcard has weight 1, OpenRouter-Backup weight 0. The existing evaluation
profile uses ordered failover with no channel allowlist or model substitution.
No credentials, existing model entries or global weights were changed.
Inspect the actual execution record to distinguish giftcard success from
OpenRouter fallback; catalog or configuration membership alone proves neither.

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
