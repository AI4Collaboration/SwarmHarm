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
4. select one exact model ID present in both;
5. record the catalog evidence and exact ID in a fresh registration;
6. edit no frozen source after preparation;
7. commit and push the registration before inference; and
8. reject a response whose returned model identity differs from the frozen ID.

Do not use a drifting `latest` alias or inherit a model ID from a historical run.
Provider errors, filters and refusals remain separate from behavioral results.

The exact routes verified in both catalogs on **23 October 2026** are:

- DeepSeek Flash: `deepseek/deepseek-v4.1-flash-1017`;
- GLM FlashX: `z-ai/glm-5.3-flashx`.

These entries are route evidence, not automatic choices for later campaigns.
Every new registration queries both catalogs again.

Historical output directories retain the route they actually used. They are
evidence only and never define current routing.
