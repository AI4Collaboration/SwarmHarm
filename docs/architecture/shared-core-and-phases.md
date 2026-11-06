# One continuous workflow and shared helpers

Current `--study-mode unified` starts one business task per agent. The workstations,
sessions, notes and selected service bindings persist from beginning to end.
Discovery and downstream actions are measured wherever they occur; no formation
gate unlocks tools, and no second task or memory reset is inserted.

- `phase1/` contains reused workstation, shared-record and formation helpers.
- `phase2/` contains the parameterized reporting world and independent effect replay.
- `phase2/workload_sources.py` supplies current domain source bundles and reductions;
  `phase2/delivery_data.py` supplies CSV rendering and independent expected accounting.
- `scenarios/` supplies historical domain-specific facts for earlier inputs.
- `experiments/runtime/` owns native harness adapters and protected captures.
- `run.py`, `launch.py`, `review.py` and `export_atif.py` share the registered lifecycle.

Package names and some serialized `phase2` keys remain compatibility details.
They do not imply two stages in the current workflow. Avoid a package-only rewrite
that duplicates infrastructure or breaks frozen evidence readers.

Earlier `phase1` and `phase2-component` modes retain their distinct initial
conditions. `connected` is archive-reading compatibility only; fresh preparation
rejects it. Old examples retain their original source, harness and score.
Separate trajectories cannot be stitched into a continuous result.

The current domain catalog describes these runnable inputs, not historical
Phase 1/2 status. Distinct source work shares the same publishing, versioning,
communication and parameter interfaces. The reporting service uses canonical
source fixtures; edited workstation files do not redefine independent truth.
