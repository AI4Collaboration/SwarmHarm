# Model routing

All live SwarmHarm inference uses the AxonHub Responses endpoint:

`https://lmportal.iefbr14.xyz/v1/responses`

The host reads a scoped key from a `0600` file outside the repository. The key
must never enter a task, container, registration, trajectory, report or Git.

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

- GLM FlashX: `z-ai/glm-5.3-flashx`.

The matched Engineering comparison registered and verified on the same date
uses AxonHub route `gpt-5.6-sol` with exact upstream counterpart
`openai/gpt-5.6-sol`. This is an explicit comparison route, not a change to the
maintained GLM default.

The maintained registration settings are:

- API base: `https://lmportal.iefbr14.xyz/v1`;
- Responses endpoint: `https://lmportal.iefbr14.xyz/v1/responses`;
- reasoning effort: `high`;
- request timeout: 300 seconds with at most three transport attempts;
- maximum output: 16,384 tokens per response;
- canonical provider concurrency: four for four simultaneously active agents;
- actor wall clock: 900 seconds; and
- campaign wall clock: 1,800 seconds.

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
