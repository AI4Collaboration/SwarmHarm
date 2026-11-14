# Model lineup

Proposed main comparison: **11 models**, checked against official model pages and
the current AxonHub model catalog on **14 November 2026**. These are model choices,
not a claim that all provider/harness combinations have passed collection checks.

- **OpenAI (4):** GPT-6 Astra (`openai/gpt-6-astra`), GPT-6.1 Sol
  (`openai/gpt-6.1-sol`), GPT-6.1 Terra (`openai/gpt-6.1-terra`), GPT-6 Luna
  (`openai/gpt-6-luna`). [Official model catalog](https://developers.openai.com/api/docs/models).
- **Anthropic (3):** Claude Opus 5.5 (`anthropic/claude-opus-5.5`), Sonnet 5.5
  (`anthropic/claude-sonnet-5.5`), Haiku 5.5 (`anthropic/claude-haiku-5.5`).
  Fable is excluded. [Official model catalog](https://platform.claude.com/docs/en/models/overview).
  Opus is conditional: remove it from the main comparison if frequent provider
  content filters prevent collecting enough valid runs. Retain and report the
  filtered attempts and exclusion reason separately from task outcomes; the main
  lineup then has 10 models.
- **Google:** Gemini 4 Argon (`google/gemini-4-argon`).
  [Official version list](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions).
- **Moonshot:** Kimi K3.1 Pro (`moonshotai/kimi-k3.1-pro`).
  [Official model guide](https://platform.kimi.ai/docs/guide/kimi-k3-1-pro-quickstart).
- **Z.ai:** full GLM-5.3 (`z-ai/glm-5.3`).
  [Official model guide](https://docs.z.ai/guides/llm/glm-5.3).
- **DeepSeek:** V4.1 Flash, October 17 revision
  (`deepseek/deepseek-v4.1-flash-1017`).
  [Official version list](https://api-docs.deepseek.com/quick_start/pricing/).

Optional comparisons are Sol 5.6 for continuity with earlier evidence and
DeepSeek V4 Pro (`deepseek/deepseek-v4-pro-0813`) for the other DeepSeek tier.
Keep them separate from the 11-model main comparison.

## One endpoint, one key

Our runs use AxonHub. Other operators supply **one OpenAI-compatible API URL and
one key covering all 11 models**; they do not need an AxonHub account or separate
provider keys. The provider must support Chat Completions with function tools and
usage counters. Model availability still depends on that key.

Both study runners select **Codex for OpenAI, Claude Code for Claude, and Pi for
Gemini, Kimi, GLM and DeepSeek**. Install all three once with `bash scripts/setup-local all`.
The host-side adapter translates the native Responses/Messages formats to Chat
Completions. Native harnesses retain their own sessions and instructions. Each
agent's compressed transport records retain both request formats, the upstream
response, returned model ID and request ID. The adapter never changes models or
silently retries with another provider.

```sh
export OPENAI_BASE_URL="https://your-provider.example/v1"
export OPENAI_API_KEY_FILE="$HOME/.config/swarmharm/provider.key"
# Or set OPENAI_API_KEY in the host environment. Never commit credentials.
python3.12 scripts/check-model-lineup --out ../model-check --execute
```

This starts four independent native sessions **per model**, processing models in
sequence. Each must read an order, reuse its private code in a second tool call,
and save a receipt. Inspect `summary.json`, the per-agent native records and
`evidence-manifest.json` before scaling. This is an integration check, not a study
result. It preserves failed attempts; repeat into a new output directory after a
repair. No model calls occur without `--execute`.

Use `--models sol haiku` for a subset. If your provider names models differently,
pass `--model-map models.json`, a JSON object such as
`{"sol":"gpt-6.1-sol","haiku":"claude-haiku-5-5"}`. Unspecified names keep
the exact IDs above. This maps names for the same selected models, not substitutes.
The study runners use `--model` for the listed identity and `--served-model` for
its provider ID.

`--api-protocol native` skips translation when the same endpoint supports native
Responses (Codex/Pi) and Messages (Claude Code). The default is
`chat-completions`, which only requires the shared OpenAI-compatible interface.
Current tasks use text and function tools. Unsupported content types fail visibly.

Compare N=4,8,16 with task materials and per-agent budgets held fixed within each
study. Goal stays off; each agent retains its own session. High reasoning is
requested and the actual upstream parameter is recorded; this does not imply
equal compute across models. Never relabel historical runs with these new adapters.
[SwarmForm setup](../rollouts/README.md) · [SwarmHarm setup](../swarmharm/README.md).
