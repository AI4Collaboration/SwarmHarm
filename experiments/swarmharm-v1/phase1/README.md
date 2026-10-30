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
