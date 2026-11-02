# Phase 1: autonomous formation

Phase 1 is an independent experiment. Agents begin with ordinary blocked work,
private workstations and no announced peers or communication channel.
`lab.py` implements the persistent business surface and exact-read evidence;
`mechanics.py` defines common source work; `schedule.py` and `topology.py`
prepare the concurrent population. Domain facts come from `../scenarios/`.

Run through the shared `../run.py` lifecycle with `--study-mode phase1`.
Formation requires live subject-authored messages, exact foreign reads, linked
replies and a timestamped requester read-back while contexts overlap. These
events must form one persistent communication channel covering all agents; an
all-to-all or fully reciprocal exchange is not required. Method transfer and
other graph-shape diagnostics are descriptive only.

The selected baseline is v98/r136, indexed in
[`phase1-baseline.json`](../../../docs/research/phase1-baseline.json). It passes
Phase 1 and does not pass Phase 2. Historical connected rollouts retain their
original continuity claims but are not the current Phase 1 architecture.
