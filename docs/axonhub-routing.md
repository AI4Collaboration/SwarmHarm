# Model routing

## Standing user policy — 3 November 2026

All future model calls use **direct AxonHub APIs**, without Claude Code, Codex
or Pi harnesses. Do not inherit their presets, skills or confirmation rules.
This explicitly supersedes the earlier family-specific harness requirement.
Claude giftcard remains preferred, with OpenRouter fallback for the same model.

Current Phase 1 selection is Sol 6.1 and Haiku 5.5 across all four maintained
scenarios. Either model passing the current environment's formation criterion is
sufficient. Use one prepare/collect/review pipeline and retain exact requests,
responses, tool execution and source seals. Direct transport has fully reviewed passing Sol6.1 observations in all four
Phase1 scenarios (r72-r75). Historical adapters below describe old evidence.

On4 November the user additionally selected Sonnet for comparison. Use exact
`anthropic/claude-sonnet-5.5`, verified in both authenticated AxonHub and upstream
catalogs, on the current Engineering scenario. This is separate model coverage;
keep the completed either-Sol-or-Haiku readiness judgment intact.

AxonHub service root: `https://lmportal.iefbr14.xyz`.
Responses endpoint: `https://lmportal.iefbr14.xyz/v1/responses`.

The host reads a scoped key from a `0600` file outside the repository. A key
must never enter a task, container, registration, trajectory, report or Git.

## Anthropic direct-history compatibility — 4 November 2026

New Anthropic registrations declare `text-before-tool-calls-v1`. Within each
assistant response, all non-call items precede the unchanged function-call list
before actual tool results are appended. No prompt, result, call or assistant
text is dropped. Raw provider responses keep their original order. Controller
history and ATIF independently preserve the declared projection; registrations
without the field retain their original replay. OpenAI ordering is unchanged.
R76 exposed a gateway conversion HTTP400 on calls followed by assistant text;
one separately sealed diagnostic using the same content with grouped order
succeeded. This is transport compatibility, not evidence of communication.

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

Sonnet r77 live verification (4 November): all129 requests completed, including
127 subject responses and2 preflights, with0 transport errors. Registered
text-before-tool-calls grouping preserved the full native content and passed
all four ATIF continuity checks. R76's earlier HTTP400 and the separate
same-content diagnostic remain preserved. Exact selected model was
anthropic/claude-sonnet-5.5; one Engineering comparison, no harness.
