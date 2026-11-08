# Model and harness routing

For the active SwarmForm matrix use native Codex through **AxonHub** for both Sol models. All supported adapters route live inference through AxonHub, including Claude Code. Direct
provider and subscription inference are not rollout routes.

- **Claude models: Claude Code.** This includes Haiku, Sonnet and Opus.
- **OpenAI models: Codex.** Pi is not a fallback route.
- Use native same-model fallback, preferring eligible non-OpenRouter channels.
  Freeze the exact model ID, gateway, protocol and actual adapter version.
- Read the existing host-only key outside Git. Never copy it into an agent
  workspace, registration or report. Do not change credentials or spending limits.
- Verify catalog availability at preparation and actual routing during execution.
  Catalog membership alone does not establish a successful call.

## Current implementation

Claude Code uses the Agent SDK and AxonHub Messages API. Codex uses its native
app-server and an isolated AxonHub Responses provider. The host key is passed in
the child environment, never written into configuration or agent workstations.
The executable/version, model profile and source hashes are registered.

Claude's advertised cwd maps to `/workspace` inside its isolated business
workstation; briefing file tools resolve the same actor-local alias and relative
paths. Native record appends are journaled immediately and serialized
around tool execution, preserving both authored edits and later SDK entries.
The append journal is outside the subject's writable record view.

Claude MCP tools declare the supported 500,000-character inline text limit to
avoid inaccessible host-file previews for ordinary large reads. Offline tests
exercise 60,000-character output through the real SDK and strict ATIF checks.
Larger or otherwise transformed output still fails exact-delivery validation.
[Claude MCP documentation](https://code.claude.com/docs/en/mcp#raise-the-limit-for-a-specific-tool).

Claude appends the registered autonomous-execution rule and factual unattended,
task-scoped authorization context to its stock system
preset. The business task stays in user input and does not duplicate that rule.
Offline SDK requests verify the actual role; live traces record the preset
configuration without inventing the full internal stock prompt.

Codex preauthorizes only the registered synthetic work MCP server. Native tool
injection features outside the registered tool surface are disabled and frozen
in the registration. Model metadata also freezes direct MCP exposure and standard
Responses transport; otherwise model-level code mode overrides feature flags.
Real-CLI tests assert the outbound tool list and exact structured text results,
auxiliary tool observations and ATIF export. Unknown or truncated results still
fail validation. Claude API failures preserve their native error detail and stop
the affected attempt; a provider failure is not a behavioral negative.

Both adapters preserve one native session per actor. The trace environment reads
their actual record formats and keeps protected observer captures. Offline adapter
checks are separate from live validation; each native adaptation needs a fresh
registered rollout.

See [running evaluations](running-evals.md) for registration and execution.

## Continuation

Current unified registrations use `goal_mode=off`. Codex freezes
`tool_output_token_limit=262144` so its native history can retain both
64,000-byte workstation streams, JSON escaping and the MCP envelope. The
workstation's own output bound is unchanged. Exact delivery is tested through
the real CLI. See the official [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

Codex network-error notifications with `willRetry=true` leave the same native
turn active. The adapter records them and lets Codex reconnect within the
existing response deadline; it sends no new prompt and replays no tools.
Terminal errors still stop collection. Controller response counts do not claim
to count upstream retries. See the official
[app-server error contract](https://learn.chatgpt.com/docs/app-server#errors).
