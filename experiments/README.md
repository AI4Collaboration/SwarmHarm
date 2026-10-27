# Experiments

The maintained study is [swarmharm-v1](swarmharm-v1/). The other directories
here are frozen `ayush`-branch studies; they ran on earlier revisions and do
not define current operation. Studies retired on `main` remain in Git history.

**25 October 2026:** [Reply chronology audit](swarm-discovery-v3/RESULTS.md).
The exact parent version must precede a reply. Sixteen regression checks and a
new read-only regrade leave the discovery and communication findings unchanged.
Audit code: [swarm-discovery-audit-v1](swarm-discovery-audit-v1/README.md).

**25 October 2026:** [Business-client discovery and persistent histories](swarm-discovery-v3/RESULTS.md).
All four contexts discovered the client and read cross-job notes; no cross-job
reply or route adoption followed. Four of eight reviews were filed. Earlier
runs remain preserved.

**25 October 2026:** [Stage 1 diagnosis and runtime correction](swarm-discovery-v2/DIAGNOSIS.md).
Real concurrent-shell controls expose and fix a blocked reply. The registered
repeat retained identical unhinted inputs and again observed no communication.
[Results](swarm-discovery-v2/RESULTS.md). The original pilot
([swarm-discovery-v1](swarm-discovery-v1/RESULTS.md)) stays frozen.

**24 October 2026:** [Connected-office error propagation](error-propagation-v3/RESULTS.md)
and the [back-office recovery procedure](back-office-v1/RECOVERY.md).

## Supporting components

- [Prompt checks](prompt-contract/checks.py): audit actual assembled inputs.
- [Outcome criteria](../docs/business-outcome-criteria.md): distinguish cooperation,
  method adoption and a concrete adverse business effect.
- [Running guide](../docs/running-evals.md) for registered studies.

Frozen registrations, source snapshots, native traces and analyses remain at
their original paths. Do not interpret a directory's presence as an active or
completed experiment.
