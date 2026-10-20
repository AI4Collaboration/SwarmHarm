# DeepSeek follow-up · 20 October 2026

**Prepared, not yet run:** the current host has no configured DeepSeek, AxonHub or
OpenRouter API credential. The existing AxonHub browser session is signed out.
An existing credential and its provider endpoint are required before any call.
No DeepSeek behavior result is available.

The wrapper uses the exact Sol registration's world plans, fixtures, tool
definitions and all ten initial inputs, with fresh empty worlds and no reused
model history. It changes only the model/provider setup. Four consistent normal
calibrations must pass before the six conflicting-acceptance workers.

Use an explicit DeepSeek model ID and a provider base URL supporting Responses.
The host reads a key from a named environment variable or a file containing only
the key. Authentication headers are never written to study files. No host Codex
token is sent to this provider. Model IDs and responses are not relabelled.

DeepSeek's current Responses API supports function calls and full-history input;
its returned plain-text reasoning is retained across requests. Request `high`
effort. The direct API treats developer messages as user messages and ignores
the parallel-tool flag and encrypted-content include option; these differences
must be reported. They prevent a claim of identical provider semantics or equal
reasoning compute to Sol/xhigh. [Official compatibility guide](https://api-docs.deepseek.com/guides/responses_api/).

Use the root README's interpreter with `experiments/payables-v1/deepseek.py`:
`--phase prepare --output <new-directory> --model <provider-model-id>` plus
`--base-url <api-base-url>` and either `--key-env <environment-name>` or
`--key-file <host-file>`. Repeat the same arguments with `--phase collect`.
Never put a key in a command argument. Provider errors and refusals stop the
collector, preserve evidence and remain distinct from behavioral results.
