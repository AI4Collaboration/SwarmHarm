# Independent phases and shared helpers

Phase 1 and Phase 2 are separate experiments and do not share rollout state.
This tree maintains Phase 2 and shared compatibility helpers. The latest Phase 1
results use a [separate source snapshot](../scenarios-and-parameters.md#phase-1)
with direct API execution. That snapshot is evidence provenance, not a change
to this tree’s native-harness policy.

## Current boundary

- `phase1/` owns formation tasks, shared-surface mechanics and Phase 1 review.
- `phase2/` owns collective-outcome inputs, mechanisms and terminal replay.
- `scenarios/` contains ordinary domain facts used by either experiment.
- `experiments/runtime/` owns harness adapters. Claude requires Claude Code
  through AxonHub; OpenAI uses Codex. Phase 2 reads each native record format
  and preserves protected observer captures. See `docs/axonhub-routing.md`.
- `run.py`, `launch.py`, `review.py` and `export_atif.py` provide one registered
  lifecycle.

Each independent rollout gets fresh sessions, workstations, business state and
output. Phase 2 does not load a Phase 1 gate, history or result. Historical
`connected` evidence retains its original continuity contract for archive
reading only. Fresh registration rejects that mode.

## Remaining source dependency

Standalone Phase 2 still imports some implementation helpers from the Phase 1
package. This is a source-packaging dependency, not behavioral rollout
continuity. Do not delete those helpers until an isolation test proves that
Phase 2 can prepare, collect, review and export with the Phase 1 package
unavailable.

The migration order is:

1. define a small phase-independent core interface;
2. move scheduling, workstation and recording helpers into that core;
3. update Phase 2 imports and pass its full offline suite;
4. run one fresh matching live Phase 2 validation;
5. update Phase 1 separately.

Do not copy the collector into two implementations. Shared infrastructure must
remain one code path.

## Claim boundary

A Phase 2 result establishes only its registered Phase 2 condition. Historical
connected claims are interpreted only under their frozen original contract.
Results cannot be stitched across rollout tracks.
