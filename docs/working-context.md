# Working context

## Current state — 4 November

Standalone Phase 2. No active rollout, registration or scheduled task. No website work.
Worktree `swarmharm-claude-claims`, branch `work/claude-claims-20261104`.

The three claims retain reviewed Sol positives; Haiku r263 also reproduces composition.
See the [readiness index](research/phase2-readiness.json). Claude goal comparisons
r268–r271 are closed: neither record loss nor the shared false prerequisite reproduced.
Their repeated native feedback motivated the current runtime repairs.
[Comparison and complete archives](research/claude-goal-comparison.json) preserve
original scores, messages, registration metadata errata and source hashes.
Closed registrations have been removed from the current entry directory after
byte-for-byte archive checks; Git and private Releases retain all original files.

## Maintained harnesses

- **Codex:** native goal, plus a registered two-turn exact-tool-novelty guard.
  Both desktop `0.166.0-alpha.5.1` and stable `0.166.0` repeated tool-free replies
  in the unguarded fixture. Guarded tests verify pause, history and new-state resume.
  The selected desktop binary is unchanged; stable was tested separately.
- **Claude Code:** local CLI 2.1.318 / SDK 0.3.318. Atomic `/goal` task delivery,
  same-model evaluator, and registered two-Stop exact-tool-novelty guard.
- **Pi comparison:** Pi 1.5.0 / separate pi-goal 0.54.15 extension. Native limits
  remain 25 automatic responses and three identical tool-free replies. Version
  compatibility, canonical tool ordering and memory continuity are checked.

The adapters preserve real native feedback and incomplete goals. A changed tool
response counts as new; these guards do not detect all semantic non-progress.
See [running guide](running-evals.md) for exact persistence and routing conditions.
Offline validation: 26 Pi collection checks, 16 native harness checks and six Codex
goal checks on each CLI channel passed. Claude guard tests also cover unchanged
turns, successful completion and same-session resumption.
Audit logs: `../eval-readiness/harness-audit-20261104/` and
`../eval-readiness/claude-goal-20261104/`.

## Next execution

Fresh preparation now defaults to the selected harness goal. Explicit `off` remains
a comparison; skipped-control fixtures cannot collect live. All three adapters
verify complete registered settings; control reuse permits only declared model
selector differences and rechecks each model route.

Behavioral validation of the repaired runtimes is pending. Use fresh registration,
freeze the selected executable, goal condition and source, then collect once.
Keep each claim tied to its own case. Do not reuse closed registrations or
interpret offline fixtures as model evidence.
