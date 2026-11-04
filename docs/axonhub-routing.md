# Model and harness routing

All live inference goes through **AxonHub**, including Claude Code. Direct
provider and subscription inference are not rollout routes.

- **Claude models: Claude Code.** This includes Haiku, Sonnet and Opus. Never
  substitute Pi, even when reproducing a historical Pi case.
- **OpenAI models: Codex.** Historical Sol/Pi cases retain their original
  provenance. Reproductions record model, harness and persistence differences;
  the explicit 3 November Sol 5.6 Pi comparison is separately registered with
  `--harness pi-sdk --pi-comparison`. It never changes default routing.
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
their actual record formats and keeps protected observer captures. The explicitly
authorized Sol 5.6 Pi comparison uses the same host-only AxonHub route and full
registration checks. No provider-family fallback chooses Pi automatically.

Offline adapter checks are separate from live validation. Each native adaptation
needs a fresh registered rollout; a historical Pi result cannot validate it.

Use [working context](working-context.md) for current readiness and
[running evaluations](running-evals.md) for registration. Old channel weights,
connectivity probes and subscription instructions belong in Git history; they
are not current routing configuration.

## Goal conditions

Codex `codex_goal` activates the original business objective through native
`thread/goal/set` during the initial task turn. The CLI owns continuation,
`get_goal`/`update_goal` and terminal states; the controller adds no continuation
prompt. The registered progress guard may pause unchanged turns; new business
input resumes guard-paused goals. Native state and automatic inputs are preserved.
Business completion is checked separately. A blocked Codex goal currently stays blocked;
Pi's registered changed-business-state resume remains a disclosed difference.
Pi `goal_command` retains its pinned extension limits, described in the
[running guide](running-evals.md).
The adapters' goal mechanisms are compared, not claimed identical.

Codex freezes `tool_output_token_limit=262144` so its history can retain both
64,000-byte workstation streams, JSON escaping and the MCP envelope. The
workstation's own output bound is unchanged. Exact delivery is tested through
the real CLI, including goal continuation and ATIF. See the official
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

Claude `claude_goal` sends the unchanged task and declared context in one native
`/goal` command. Both worker and evaluator use the registered AxonHub model.
A live tool-and-goal preflight must record a native met verdict before subjects
start. Native goal feedback and terminal attachments are preserved; evaluator
errors hold the attempt. Time-based check-ins are disabled and the controller
adds no unchanged-state prompts. A registered Stop guard parks consecutive unproductive turns; native impossible stopping remains
part of Claude Code, and does not count as business completion. See the official
[/goal documentation](https://code.claude.com/docs/en/goal).
