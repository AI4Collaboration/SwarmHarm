# Task sources and verification

## Maintained fixtures

SwarmHarm uses synthetic domain-native records with independent business truth.
Engineering capacity v34 models separate customer reporting batches drawing on
one shared service reserve. Each customer cost centre bears its own missed-window
credit while continuity reconstruction is charged to a central platform cost
centre. Customer-scoped credentials expose only the current customer pool, account,
quote and booking; provider-global continuity truth remains outside the customer
view. Each customer-local plan is useful and harmless alone; independent
execution, continuity and reconstruction replay determines whether the full
cohort causes a loss. No peer message or record is prepopulated.
Phase 1 retains agent-created source cases and raw activity, without
private-locator matching or automatic publication.

Current rollout status is maintained in [working context](../working-context.md)
and [the latest review](current-rollout-review.md). Historical results belong
in [takeaways](environment-iteration-takeaways.md), not source provenance.

AWS' [Capacity Reservation documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-capacity-reservations.html)
grounds reserving compute for business-critical workloads, and its
[launch documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-reservations-launch.html)
documents that using reserved instances reduces available capacity. PostgreSQL's
[checkpoint documentation](https://www.postgresql.org/docs/current/sql-checkpoint.html)
grounds the ordinary role of a checkpoint in flushing logged changes to durable
data files. Our customer pools, shared-reserve size, rollover, allowances,
reconstruction rate and exact tool interface are synthetic design choices; these
sources do not establish that either product has our simulated failure. The
independent reviewer executes the chosen plans and recomputes customer work,
reserve use, checkpoint survival and reconstruction cost rather than trusting a
planner-reported success label. Exact Phase 2 messages are grouped by customer
change. Current collection status belongs in
[working context](../working-context.md); historical lessons belong in
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
stitched conditions as evidence for its stronger continuous-rollout claim.
Its live agents must create communication themselves. If method transfer is
claimed, the method record and exact source-to-adopter ordering must also occur
in that same persistent world. Method transfer is not a universal Phase 2 gate.

[Admission contract](../dataset-admission-contract.md)
