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

The current default route verified in both catalogs on **24 October 2026** is:

- GLM FlashX: `z-ai/glm-5.3-flashx`.

Every new registration queries both catalogs again and freezes its exact
identifier. Future model additions must be explicit; they never silently change
the default.

Raw evidence retains the route actually used, but only the current frozen
registration defines maintained routing.
