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
- **Google:** Gemini 4 Carbon (`google/gemini-4-carbon`).
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

## Execution contract

Use AxonHub with the exact served IDs above, same-model fallback only, and record
the actual route and returned model identity. Do not use rolling `latest` aliases
or substitute Flash, Prime, Pro or batch variants. Catalog availability was checked;
no hosted model requests were made for this shortlist.

Compare N=4,8,16 with task materials and per-agent budgets held fixed within each
study. Goal stays off and each agent retains its own session. Use high reasoning
where supported, recording the provider's actual parameter and effective setting;
the label does not imply equal compute across models.

SwarmForm uses its common Chat Completions runner. Native SwarmHarm uses Codex for
OpenAI and Claude Code for Claude; the documented SwarmHarm batch command currently
selects Codex. Its current automatic native-harness selection
does not support Gemini, Kimi, GLM or DeepSeek yet. Validate those adapters and
tool-result/trajectory round trips before collecting that part of the lineup.
Keep harness identity explicit in comparisons rather than attributing its effects
to the model alone. [SwarmForm setup](../rollouts/README.md) ·
[SwarmHarm setup](../swarmharm/README.md).
