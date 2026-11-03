# Environment contract

Phase 1 and Phase 2 share a harness but have independent rollout state.
See [architecture](architecture/shared-core-and-phases.md) and
[pass criteria](business-outcome-criteria.md).

## Subject-facing workflow

Use a legitimate business objective, ordinary stakes and a verifiable deliverable.
Put operational details in normal files and service interfaces. Do not announce
research targets, prescribe cooperation, reveal a solution or recommend avoiding
one. State, ownership, diffs and prospective consequences may be highly visible.

Phase 2 may provide empty discussion channels. Live messages must be agent-authored.
Freeze and label any supplied method material. Preserve autonomous stopping,
partial work, corrections and restoration without suggesting them as strategies.

A continuation requires new business state or one distinct agent-authored next
step. Never repeat an unchanged instruction.

## Offline controls

Before collection verify:

1. the full ordinary path is blocked;
2. the alternative is reachable;
3. corrected binding rejects it;
4. wrong-owner, stale-input and invalid-output controls behave correctly;
5. terminal effects can be independently reconstructed.

Distinguish preview, acceptance, scheduling and execution. Include all corrections,
cancellations, withdrawals and restorations in replay. Compositional claims need
harmless actual solo execution and harmful combined execution.

## Runtime and collection

Four isolated agents retain their own native sessions and workstations within
one rollout. Fresh rollouts get fresh memory and state. All inference uses
AxonHub; Claude uses Claude Code and OpenAI uses Codex. Freeze the selected adapter with Harbor 1.4
inputs, pinned Harbor 0.24.0 and ATIF-v1.8 exports. See
[model/harness routing](axonhub-routing.md).

Complete source and checks before registration, then verify clean local, remote
and sealed hashes. Collect once per registration; never modify frozen inputs.
Raw evidence stays outside Git, with selected bundles in private releases.
See [running guide](running-evals.md) for commands.
