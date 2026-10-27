# Model routing

SwarmHarm inference uses the AxonHub Responses endpoint by default. A
registration may instead freeze a direct OpenRouter route; see
[Direct OpenRouter route](running-evals.md#direct-openrouter-route).

`https://lmportal.iefbr14.xyz/v1/responses`

The host reads a scoped key from a `0600` file outside the repository. The key
must never enter a task, container, registration, trajectory, report or Git.

## Current channels and fallback

Both existing OpenRouter channels are enabled and automatically synchronize
**all models without a filter**, hourly and on manual refresh. Both were refreshed
and reopened to verify their saved settings on 27 October; each displayed 464
supported entries at that check. Future catalog changes are not a model whitelist.
For supported OpenAI models, **TerryJwyethCO** and **TerryJwyappleCO** are enabled
at weight 100. **OpenRouter-Adam-OxRML** has weight 50 and **OpenRouter-Backup**
weight 0. The Apple channel was re-enabled at the user's request. No credential,
spending cap or account permission was changed.

Routing uses **failover by weight**, with session affinity disabled so an old
session cannot override the preferred order. Global automatic retry is enabled,
with up to four cross-channel retries and a 1,000 ms retry delay. Both OpenRouter
channels override same-channel retries
to zero, so eligible failures can move directly to another available channel.
Both additionally match HTTP 402 and the case-insensitive credit messages
`key limit exceeded`, `insufficient credits` and `insufficient balance`.
Default 429/5xx handling remains in place. Other 403 responses are not broadly
reclassified as credit errors. The requested model remains fixed across channels.

The TerryJwy channels accept both bare and `openai/`-prefixed model IDs. Both
OpenRouter channels trim the `openai` prefix as an additional exposed name and
share the same explicit Sol and legacy DeepSeek aliases. Original model IDs stay
visible; aliasing never substitutes a different model.

Host-side diagnostics on 27 October used the normal SwarmHarm Responses transport:

- **#153657**, 07:44:23 UTC: `gpt-5.6-sol` completed on **TerryJwyethCO**.
- **#153658**, 07:44:25 UTC: `openai/gpt-5.6-sol` completed on **TerryJwyappleCO**.
- **#153662**, 07:45:28–30 UTC: full `z-ai/glm-5.3` first hit the Adam channel's
  HTTP 403 key-cap error, then completed on **OpenRouter-Backup** in the same
  request. Execution timestamps verify the fallback sequence.

All returned the requested model identity and `OK` (GLM added a period). These
are routing checks, not behavioral rollouts. Unsupported TerryJwy models remain
eligible for other matching channels. Keep the host-side AxonHub credential;
OpenRouter secrets remain in AxonHub. Inspect executions to establish routing.

Catalog and credit-retry changes overlapped Sol r15. It stopped at 07:32:58 UTC
with a provider key-cap error; its records remain intact. The TerryJwy priority
and alias changes followed termination. Local model IDs, prompts and sealed
source were unchanged; the full upstream configuration was not frozen.

## Route freeze

Before every campaign:

1. finish environment code, documentation and cleanup;
2. query the upstream model catalog;
3. query the authenticated AxonHub `/v1/models` catalog;
4. select the exact AxonHub route and its OpenRouter catalog counterpart;
5. record both IDs and both catalog checks in a fresh registration;
6. edit no frozen source after preparation;
7. commit and push the registration before inference; and
8. reject a response whose returned model identity differs from the frozen ID.

Do not use a drifting `latest` alias or inherit a model ID from a historical run.
Provider errors, filters and refusals remain separate from behavioral results.

The current default route verified in both catalogs on **26 October 2026** is:

- GLM-5.3: `z-ai/glm-5.3` (full model).
- Requested Sol comparison: AxonHub `gpt-5.6-sol`, OpenRouter catalog counterpart
  `openai/gpt-5.6-sol`.

Both exact routes were verified in the authenticated AxonHub catalog and their
OpenRouter endpoint catalogs on 26 October 2026. Historical runs with different model settings are not validation for these routes.

Catalog correspondence does not pin the execution provider. All live calls pass
through AxonHub, but not all execute on OpenRouter. Preserve actual execution
channels and model identities separately from catalog verification.

The maintained registration settings are:

- API base: `https://lmportal.iefbr14.xyz/v1`;
- Responses endpoint: `https://lmportal.iefbr14.xyz/v1/responses`;
- reasoning effort: `high`;
- request timeout: 300 seconds with at most three transport attempts;
- maximum output: 16,384 tokens per response;
- canonical provider concurrency: four for four simultaneously active agents;
- actor wall clock: 3,600 seconds; and
- campaign wall clock: 4,500 seconds.

Every new registration queries both catalogs again and freezes its exact
identifier. Future model additions must be explicit; they never silently change
the default.

Every registration also freezes the AxonHub API base, Responses endpoint,
catalog endpoint, reasoning effort and request budget. Collection reads the API
base from that frozen registration rather than from a second hard-coded value.
The maintained CLI default is Engineering; the other three maintained domains
must still be selected explicitly when preparing their own registrations.

The registration fixes the requested model and local request configuration.
AxonHub execution records establish the channel actually used; record any
service-side routing changes separately from local hashes.
