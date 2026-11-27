# Model lineup

**All 11 models passed N=4 native-harness integration on 14 November 2026:**
44 agents, 132 upstream requests, no provider errors or content filters. Each agent
called both tools, reused its own order code and saved a receipt and native records.
[Validation summary](model-lineup-validation.json) ·
[Full records](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/model-lineup-n4-20261114).
This verifies connectivity and record capture, not benchmark outcomes or larger-N throughput.

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

## One endpoint, one key

Our runs use AxonHub. Other operators supply **one OpenAI-compatible API URL and
one key covering all 11 models**; they do not need an AxonHub account or separate
provider keys. The provider must support Chat Completions with function tools and
usage counters. Model availability still depends on that key.

Both study runners select **Codex for OpenAI, Claude Code for Claude, and Pi for
Gemini, Kimi, GLM and DeepSeek**. `bash scripts/setup-defaults` installs all three and prepares both studies.
The host-side adapter translates the native Responses/Messages formats to Chat
Completions. Native harnesses retain their own sessions and instructions. Each
agent's compressed transport records retain both request formats, the upstream
response, returned model ID and request ID. The adapter never changes models or
silently retries with another provider.

Follow the [default-run instructions](../README.md#run-the-default-experiment).
The N=4 API check runs automatically before the full experiment.

Use `OPENAI_API_KEY_FILE` instead of `OPENAI_API_KEY` if preferred. If your provider
names models differently, optional `--model-map models.json` accepts a JSON object
such as `{"sol":"gpt-6.1-sol","haiku":"claude-haiku-5-5"}`. The default still selects
all 11 models; this only maps provider spellings. The lower-level study runners use
`--model` and `--served-model` for optional custom runs.

The standalone `scripts/check-model-lineup` command remains available when only an
API check is needed. Its results are integration evidence, not study outcomes.

Both studies default to N=4,8,16,32. Hold task materials
and per-agent budgets fixed within each study. Goal stays off; each agent retains its own session. High reasoning is
requested and the actual upstream parameter is recorded; this does not imply
equal compute across models. Never relabel historical runs with these new adapters.
[SwarmForm setup](../rollouts/README.md) · [SwarmHarm setup](../swarmharm/README.md).
