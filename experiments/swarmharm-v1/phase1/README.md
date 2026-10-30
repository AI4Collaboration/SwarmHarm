# Phase 1: autonomous formation

Agents begin with ordinary blocked work, private workstations and no announced
peers or channel. `lab.py` implements the persistent business surface and exact
read evidence; `mechanics.py` defines common source work; `schedule.py` and
`topology.py` prepare the concurrent population. Domain-specific business facts
come from `../scenarios/`.

Run through the shared `../run.py` harness using `--study-mode phase1` to evaluate
formation alone, or `--study-mode connected` to continue the same sessions into
Phase 2. There is no separate transport or collector. Formation criteria remain
unchanged; a standalone result does not establish a Phase 2 outcome.

The selected live baseline remains v98/r136, indexed in
[phase1-baseline.json](../../../docs/research/phase1-baseline.json). This harness
integration needs its own fresh live validation. See
[Running evaluations](../../../docs/running-evals.md) for setup and commands.

## Publication design and channel parameters

The [four-domain design](../../../docs/phase1-publication-design.md) and
[methods draft](../../../docs/phase1-methods.md) distinguish carrier, surface,
documentation, protocol affordances and observed use. `channel-taxonomy.json`
contains the operator-only catalogue. It is never copied into subject files.

For a fresh standalone Phase 1 preparation, the common `run.py` accepts
`--phase1-channel-profile records_shared` or `records_partitioned`.
The first retains ordinary same-filing record exposure. The second uses the
existing visibility controller to remove cross-actor record edges, including
record-derived notices, while retaining self records and ordinary service work.
Both require `--study-mode phase1`, `--cue-condition agent_initiated_activity`
and one of the four maintained scenarios. A separate topology override is
rejected. The selected condition and catalogue bytes are sealed in registration.
The default without this flag preserves existing behavior.

These profiles pass offline contract checks but remain **live rollout pending**.
The record limit is 32 KiB of complete serialized record, not 32 KiB of usable
message payload or measured information capacity. Current helper tools already
supply case/note/reply structure; do not claim protocol invention.

From the experiment directory:

```sh
python -B -m unittest tests.channel_design_checks -v
python -m phase1.channel_design
```

The second command emits an unregistered 36-cell proposal: four domains by three
carriers by three exposure/assistance conditions. Only the eight payload
shared/partitioned cells currently have executable profiles. Proposed namespace,
finite-state and revealed-carrier cells are explicitly unavailable. Timing and
resource signals are extensions. The generator makes no model calls and is not
a collection command. No sample size or rate is invented.

Use the existing preparation, commit/push, seal verification, collection, review
and export workflow for any later live validation. One fresh reviewed rollout
validates an environment revision; it does not supply a success-rate estimate.
