# Working context

## Current state — 4 November

Standalone Phase 2. Preparing one matched four-preset comparison; no collector has
started. No scheduled task or website work. Worktree `swarmharm-unified-phase2`,
branch `work/unified-phase2-20261104`.

The user authorized a unified reporting task with three backend binding presets
and a correctly bound control, followed by one four-agent Sol rollout per preset.
Use Sol 5.6 / Codex native goal through AxonHub, unchanged budgets and initial
subject materials. `phase2/unified_delivery.py` implements the business model;
`tests/unified_delivery_checks.py` checks matched inputs, one-factor reachability,
blocked ordinary completion, corrections and independently inspected final files.
The new resource condition is allocation-purpose binding and the record condition
uses an editable business register. Neither substitutes for the earlier external
service or native-record cases. Keep all prior positive evidence unchanged.

The three claims retain reviewed Sol positives; Haiku r263 also reproduces composition.
See the [readiness index](research/phase2-readiness.json). Claude goal comparisons
r268–r271 are closed: neither record loss nor the shared false prerequisite reproduced.
Their repeated native feedback motivated the current runtime repairs.
[Comparison and complete archives](research/claude-goal-comparison.json) preserve
original scores, messages, registration metadata errata and source hashes.
Closed registrations have been removed from the current entry directory after
byte-for-byte archive checks; Git and private Releases retain all original files.

Phase 1 results are indexed separately in [phase1-results.json](research/phase1-results.json),
with their own direct-API source snapshot. They do not change this tree’s native
Phase 2 execution policy. See [scenario parameters](scenarios-and-parameters.md).

## Maintained harnesses

- **Codex:** native goal, plus a registered two-turn exact-tool-novelty guard.
  Both desktop `0.166.0-alpha.5.1` and stable `0.166.0` repeated tool-free replies
  in the unguarded fixture. Guarded tests verify pause, history and new-state resume.
  Existing host selection is unchanged; fresh setup selects pinned stable explicitly.
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

## Reproducible setup

`scripts/setup-local` installs locked Python/Node dependencies and builds the pinned
workstation image. `scripts/check-installation` checks all adapters and actual
isolated file/tool delivery without hosted inference. A clean macOS arm64 copy
passed setup and a real isolated file/tool round trip. The full offline sweep ran
546 checks and exposed one malformed-tool-argument capture defect; it is repaired.
All 50 affected harness regression checks then passed. A clean stable-Codex setup
completed 51 harness checks: 45 passed and six optional historical-CLI checks
were skipped. npm Codex
launchers now resolve to the native executable for hashing and record capture.
Linux/Alliance execution remains platform-specific validation.
Six separately sealed Phase 1 runs are now in the private
[Phase 1 Release](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/phase1-results-20261104).
Historical record cases r190/r199/r207/r212 retain original evidence and separately
labeled reviews in the [record evidence Release](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/historical-record-evidence-20261104).

## Next execution

Fresh preparation now defaults to the selected harness goal. Explicit `off` remains
a comparison; skipped-control fixtures cannot collect live. All three adapters
verify complete registered settings; control reuse permits only declared model
selector differences and rechecks each model route.

Behavioral validation of the repaired runtimes is pending. Use fresh registration,
freeze the selected executable, goal condition and source, then collect once.
Keep each claim tied to its own case. Do not reuse closed registrations or
interpret offline fixtures as model evidence.
