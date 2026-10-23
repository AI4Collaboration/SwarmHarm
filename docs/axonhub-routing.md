# Model routing

All live SwarmHarm inference uses the AxonHub Responses endpoint:

`https://lmportal.iefbr14.xyz/v1/responses`

The host reads a scoped key from a `0600` file outside the repository. The key
must never enter a task, container, registration, trajectory, report or Git.

## Route freeze

Before every campaign:

1. query the upstream model catalog;
2. query the authenticated AxonHub `/v1/models` catalog;
3. select one exact model ID present in both;
4. record the catalog evidence and exact ID in a fresh registration;
5. commit and push the registration before inference; and
6. reject a response whose returned model identity differs from the frozen ID.

Do not use a drifting `latest` alias or inherit a model ID from a historical run.
Provider errors, filters and refusals remain separate from behavioral results.

The last verified DeepSeek Flash snapshot on **23 October 2026** was
`deepseek/deepseek-v4.1-flash-1017`. This is historical route evidence, not an
automatic choice for the next campaign. The next DeepSeek and GLM campaigns must
query both catalogs again before registration.

Historical output directories retain the route they actually used. They are
evidence only and never define current routing.
