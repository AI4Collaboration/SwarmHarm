# Task sources and verification

## Maintained fixtures

SwarmHarm uses synthetic domain-native records with independent business truth.
The maintained recovery-handover scenario adds one business dependency to replica
maintenance: the local restore store is offline during an upgrade, so its handover references
a restore point on another replica. Records are created by live subjects and
returned privately; no peer message or record is prepopulated. The task prompt,
Phase 1 and availability replay are unchanged. Live validation is pending.

This is a synthetic business adaptation. PostgreSQL's [backup and archive
recovery documentation](https://www.postgresql.org/docs/current/continuous-archiving.html)
motivates retaining recovery material away from a failed machine; it does not
specify our exact cross-replica handover interface. Kubernetes' [rolling-update
availability controls](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#max-unavailable)
ground the aggregate availability concern. Our simplified planner omits an
aggregate reservation, while the independent reviewer recomputes the final
schedule. Staggering and correction remain valid safe outcomes.

The latest reviewed v4 campaign passed formation but had a safe final schedule
and no direct Phase 2 dialogue. See the [review](swarmharm-maintenance-change-handover-2026-10-26.md).
Other scenarios need matching campaigns on the changed runtime. Earlier findings
and their limits are summarized in [takeaways](environment-iteration-takeaways.md).

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
