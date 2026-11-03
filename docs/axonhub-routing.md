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

The Phase 1 publication branch implements Claude Code through AxonHub's Messages
API. The maintained Phase 2 trace-integrity environment still uses Pi-specific
record projection and goal handling. Its Claude Code adaptation must pass native
record, continuation, export and outcome checks before a new registration.
Live preparation and launch reject Claude or OpenAI with Pi; missing support is never a reason
to change the requested harness.

Use [working context](working-context.md) for the selected next model and
[running evaluations](running-evals.md) for registration. Old channel weights,
connectivity probes and subscription instructions belong in Git history; they
are not current routing configuration.
