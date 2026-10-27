# Model routing

All live SwarmHarm inference uses the AxonHub Responses endpoint:

`https://lmportal.iefbr14.xyz/v1/responses`

The host reads a scoped key from a `0600` file outside the repository. The key
must never enter a task, container, registration, trajectory, report or Git.

## Current channels and fallback

Both existing OpenRouter keys are available through AxonHub. The preferred
channel is **OpenRouter-Adam-OxRML** at weight 100. The existing second channel,
now **OpenRouter-Backup**, stays enabled at weight 0 and synchronizes all models
without a filter. On 27 October its saved catalog contained 462 automatically
synchronized entries and two retained manual entries, including full
`z-ai/glm-5.3`. No key, spending cap or account permission was changed.

A host-side diagnostic using the normal SwarmHarm Responses transport completed
with full `z-ai/glm-5.3` and returned `OK` at 07:20:44 UTC on 27 October.
AxonHub request **#153200** shows **OpenRouter-Backup**, the matching upstream
model and a completed response. This confirms a working alternate route; it
is not a behavioral rollout. Its single successful execution used the backup
directly; it does not prove a failed-primary-then-retry sequence within that
request. The earlier backup model list omitted full GLM,
so treating one key's limit as a model-wide outage was incorrect.

AxonHub uses adaptive routing and session affinity. Weight is a preference,
not an exclusive-channel guarantee. Keep the host-side AxonHub credential;
OpenRouter secrets remain in AxonHub. Catalog membership alone does not prove
which key handled a request. Check per-request executions before claiming a
specific retry or failover sequence.

The backup catalog was expanded while Sol r15 was running. Record that routing
intervention in the run review. Local model IDs, prompts and frozen source
were unchanged; do not describe the upstream channel as fixed throughout.

## Route freeze

Before every campaign:

1. finish environment code, documentation and cleanup;
2. query the upstream model catalog;
3. query the authenticated AxonHub `/v1/models` catalog;
4. select the exact AxonHub route and its exact upstream OpenRouter counterpart;
5. record both IDs and both catalog checks in a fresh registration;
6. edit no frozen source after preparation;
7. commit and push the registration before inference; and
8. reject a response whose returned model identity differs from the frozen ID.

Do not use a drifting `latest` alias or inherit a model ID from a historical run.
Provider errors, filters and refusals remain separate from behavioral results.

The current default route verified in both catalogs on **26 October 2026** is:

- GLM-5.3: `z-ai/glm-5.3` (full model).
- Requested Sol comparison: AxonHub `gpt-5.6-sol`, upstream `openai/gpt-5.6-sol`.

Both exact routes were verified in the authenticated AxonHub catalog and their
OpenRouter endpoint catalogs on 26 October 2026. The user explicitly replaced
the FlashX default with GLM-5.3 and requested one Sol comparison. Historical
FlashX results do not validate the new model settings.

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

Raw evidence retains the route actually used, but only the current frozen
registration defines maintained routing.
