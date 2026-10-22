# Dataset admission contract

The public website defines six environment conditions: a real task, a blocked
normal path, a discoverable vulnerability, persistent shared systems, separate
agent sandboxes and discoverable channels. Those conditions describe the world
the agents enter. They should remain the compact public principles.

Three additional rules govern whether observations from that world can support a
research claim:

1. **Native transfer provenance.** A transfer claim needs agent-authored method
   content, receipt before action, use on a different object by a fresh agent and
   a new verified effect. Access to shared storage or similar behavior is not
   enough.
2. **Development and holdout separation.** A fixture used to tune prompts,
   tools, schedules, labels or mechanisms remains development data. Final
   estimates use preregistered, source-backed held-out tasks and retain negative
   and incomplete chains.
3. **Independent outcome verification.** A separate verifier recomputes the
   primary effect from records outside the subject's control. Self-reports,
   edited status fields and an LLM judge cannot establish it. This confirms what
   happened; it does not by itself explain why contagion occurred.

Contagion is an object of analysis, not an admission condition. The dataset
records discovery, authored communication, receipt, adoption and verified
effects without requiring an explanation for the contagion process before
collecting the observation.

Pressure, leadership, channel type, composition depth, long-horizon duration and
whistleblowing are measured dimensions. They are not admission requirements.
Treating them as requirements would narrow the dataset to a preferred outcome.

The machine-readable contract is
[`dataset-admission-contract.json`](dataset-admission-contract.json). Run
`python3 scripts/check_dataset_admission_contract.py` from the repository root to
validate its evidence links and execute the current environment's offline
controls.

The current `procurement-critical-stakes-v8` environment is synthetic
development data. Its first run verified one informed critical incident and one
fresh successor that read the earlier records and avoided a second incident.
Passing its controls and one behavioral run does not establish a population
rate, intent or causal contagion.
