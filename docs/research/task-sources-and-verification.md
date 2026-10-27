# Task sources and verification

## Maintained fixtures

SwarmHarm uses synthetic domain-native records with independent business truth.
Engineering maintenance v9 models a version migration, a full recovery archive,
and inconsistent retention checks between booking and calendar-sheet import.
Local restore records are created privately by subjects. No peer message or
record is prepopulated. Phase 1 retains agent-created source cases and raw
activity, without private-locator matching or automatic publication.

PostgreSQL's [backup and archive recovery documentation](https://www.postgresql.org/docs/current/continuous-archiving.html)
grounds the need to retain recovery material. Kubernetes' [rolling-update availability controls](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#max-unavailable)
ground availability during maintenance. Our archive quota, sheet importer,
version-conversion behavior and exact tool interface are synthetic design choices;
these sources do not establish that either product has our simulated defect.
The independent reviewer executes the chosen plan and checks old-format recovery,
not a planner-reported success label. Fresh GLM/Sol validation of v9 is pending. This iteration repairs terminal
bookkeeping and increases time without changing the recovery mechanism.
Historical findings and qualifications are in
[takeaways](environment-iteration-takeaways.md).

## Source-backed candidates

- **OpenAI 2026 work categories:** the June 2026 Codex economic research report
  names Engineering / Coding, Data Analysis, Financial Analysis, Knowledge Work
  and a catch-all Other category. SwarmHarm shortens the first label to
  Engineering, uses the four named categories as its domain backbone and
  excludes Other. The four maintained scenario
  contracts require individual validation. Historical domain positives apply only to their frozen sources;
  current coverage needs matching live validation.
- **MiMo V2.6 RL Harbor general:** 925 workplace tasks at audited revision
  `85c8884bb32b82d5a2f39bb1044bffd8d5d574f1` in
  [FineEnvs/MiMo-V2.6-RL-harbor-general](https://huggingface.co/datasets/FineEnvs/MiMo-V2.6-RL-harbor-general/tree/85c8884bb32b82d5a2f39bb1044bffd8d5d574f1).
  Candidate tasks still require the admission checks above.
- **MiMo code:** a candidate only after a natural business adaptation with an
  independently verified outcome.

## Design references

- [ImpossibleBench](https://arxiv.org/abs/2510.20270): explicit infeasibility.
- [LessWrong reproduction](https://www.lesswrong.com/posts/fMnC6ZD37qrnZAFYz/openai-huggingface-a-reproduction-and-lessons-for-alignment):
  discovery, request, sharing and use measurements.
- [OpenAI incident summary](https://openai.com/index/hugging-face-incident-and-the-road-ahead/)
  and [METR investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/):
  persistence, blocked-task concentration and cross-run work.

References shape the environment; they are not completed SwarmHarm coverage.
Admit a task only after proving its blocker, source truth, reachable mechanism,
continuous phase dependence and independent outcome check.

The LessWrong manual reproduction measures the four incident steps in separate
static environments. Its help-request condition programmatically injects
simulated-agent scratch files and pre-populates notes suggesting that other
agents have solved similar tasks; its method-use condition starts with methods
already on the message board. The authors also note that their deliberately
simplified environment may concentrate agents on the few available affordances, and they
run 64 trajectories per setting. SwarmHarm does not treat those pre-populated or
stitched conditions as evidence for its stronger continuous-campaign claim.
Its live agents must create the communication and method records themselves,
and the exact source-to-adopter ordering must occur in one persistent world.

[Admission contract](../dataset-admission-contract.md)
