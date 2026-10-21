# GLM route identity was not verified

**No GLM business experiment was collected.** The first preflight requested
`glm-5.3-flash` but the relay returned a completed response identifying itself as
`abliterated-model-large-v2`. The transport rejected this mismatch before
dispatching its output. Both normal calibration and all twelve experimental
invoices remain untested.
[Native error](results/2026-10-20-preflight-mismatch/preflight-001.error.json) ·
[Coverage](results/2026-10-20-preflight-mismatch/summary.json).

The project catalog had listed the requested model, but that did not establish the
identity of live responses. We have not independently established what model
produced this response or whether the name is a provider alias. This is a route
identity error, not a safety refusal, a behavioral negative result or evidence
about GLM alignment.

The [registration](https://github.com/AI4Collaboration/SwarmHarm/commit/dff6e4f2)
was pushed before the single request. No retry, substitution or infrastructure
change was attempted. The collector exited, the native evidence is preserved,
and no business tool was run. Further behavioral work uses the separately
verified Sol and DeepSeek routes. The existing key copy is retained only for that
registered follow-up; no new key or permissions were created.
