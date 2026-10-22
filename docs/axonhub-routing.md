# Model routing

All live SwarmHarm model requests use AxonHub:

`https://lmportal.iefbr14.xyz/v1/responses`

The host supplies `AXONHUB_API_KEY` or a path passed with `--key-file`. The key
is read only by the host transport. It is never copied into a Harbor task,
container, registration, trajectory, report, or source file. A run without a
key fails before sending a request.

Historical output directories preserve the route they actually used. They are
evidence of earlier runs, not current routing instructions and not eligible for
reclassification.

For every new DeepSeek study, read OpenRouter's official `/api/v1/models` catalog
before freezing the registration. Select the newest explicit DeepSeek Flash
snapshot, then confirm that the authenticated AxonHub `/v1/models` catalog
exposes the same exact route. Record that ID and verify that the returned model
matches it. Stop before inference when either catalog is unavailable, ambiguous
or inconsistent. Never register a drifting `latest` alias or change the model
inside a frozen run.

Verified on 22 October 2026, OpenRouter identifies
`deepseek/deepseek-v4.1-flash-1017` as the current explicit DeepSeek Flash
snapshot, and AxonHub exposes the same exact route. The active four-step study
freezes this ID. A later run must check both catalogs again rather than inherit
this value.

The first AxonHub Sol natural procurement run on 21 October 2026 passed both
preflights and the full calibration gate, then stopped at the first natural
request with provider error `429 turn_rate_limit_exceeded`. No retry or
trajectory replacement was made; this is an infrastructure hold, not a model
refusal or behavioral result.
