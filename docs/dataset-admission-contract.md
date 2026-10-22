# Dataset admission contract

The public website defines six environment conditions: a real task, a blocked
normal path, a discoverable vulnerability, persistent shared systems, separate
agent sandboxes and discoverable channels. Those conditions describe the world
the agents enter. They should remain the compact public principles.

Four additional rules govern whether observations from that world can support a
research claim:

1. **Causal attribution.** Matched repairs remove the adverse effect while
   preserving ordinary task capability. Reachability, completion and harm remain
   separate outcomes.
2. **Native transfer provenance.** A transfer claim needs agent-authored method
   content, receipt before action, use on a different object by a fresh agent and
   a new verified effect. Access to shared storage or similar behavior is not
   enough.
3. **Development and holdout separation.** A fixture used to tune prompts,
   tools, schedules, labels or mechanisms remains development data. Final
   estimates use preregistered, source-backed held-out tasks and retain negative
   and incomplete chains.
4. **Independent ground truth.** The primary effect is recomputed from records
   outside the subject's control. Self-reports, edited status fields and an LLM
   judge cannot establish it.

Pressure, leadership, channel type, composition depth, long-horizon duration and
whistleblowing are measured dimensions. They are not admission requirements.
Treating them as requirements would narrow the dataset to a preferred outcome.

The machine-readable contract is
[`dataset-admission-contract.json`](dataset-admission-contract.json). Run
`python3 scripts/check_dataset_admission_contract.py` from the repository root to
validate its evidence links and execute the current environment's offline
controls.

The current `procurement-composition-v2` environment is synthetic development
data. Passing its controls makes it eligible for a small behavioral development
run, not for final estimation.
