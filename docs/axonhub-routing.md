# Model and harness routing

All live inference goes through **AxonHub**, including Claude Code. Direct
provider and subscription inference are not rollout routes.

- **Claude models: Claude Code.** This includes Haiku, Sonnet and Opus. Never
  substitute Pi, even when reproducing a historical Pi case.
- **OpenAI models: Codex.** Historical Sol/Pi cases retain their original
  provenance. Reproductions record model, harness and persistence differences;
  old settings never override this rule.
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
in the registration. Real-CLI offline tests cover exact structured text results,
auxiliary tool observations and ATIF export. Unknown or truncated results still
fail validation. Claude API failures preserve their native error detail and stop
the affected attempt; a provider failure is not a behavioral negative.

Both adapters preserve one native session per actor. The trace environment reads
their actual record formats and keeps protected observer captures. Pi remains
only for archived evidence and offline fixture compatibility. Live CLI selection
and the launcher accept only the native harnesses.

Offline adapter checks are separate from live validation. Each native adaptation
needs a fresh registered rollout; a historical Pi result cannot validate it.

Use [working context](working-context.md) for the selected next model and
[running evaluations](running-evals.md) for registration. Old channel weights,
connectivity probes and subscription instructions belong in Git history; they
are not current routing configuration.
