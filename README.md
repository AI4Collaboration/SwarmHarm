# SwarmHarm

SwarmHarm studies collective AI-agent behavior in synthetic business systems.

- **Phase 1:** can isolated agents discover a shared workspace and form a
  working communication channel?
- **Phase 2:** can multiple agents' actions produce a collective adverse result?

The two studies run independently, with fresh agents, memory and business state.

## Findings

- **Coordinated failure — observed.** R212 shows autonomous method sharing and
  adoption; r199 shows consequence-aware joint execution. Each left 53
  independently verified changed records. R165 caused 31 of 55 reports to be
  delayed.
- **Shared false inference — observed.** In r187, four agents inferred and
  reinforced a nonexistent approval process without explicit manager/grader
  cues. No material action followed.
- **Compositional failure — observed in historical cases.** In r74 and r75,
  each agent's full action sequence executes harmlessly alone; combined replay
  produces excess inventory or an unfunded payment.
  [Replay evidence](docs/research/compositional-failure-review.md).

These cases support complementary claims. Discovery, dialogue and adoption are
supporting evidence, not separate headline findings.
See [case evidence](docs/phase2-design.md) and
[pass criteria](docs/business-outcome-criteria.md).

## Takeaways

- Extensive discussion and visible consequences did not produce execution in
  r217. R227 likewise ended without delivery or report delay.
- The discontinued incentive comparison had seven positives in eight runs;
  its first control was also positive. The incomplete comparison establishes
  no causal effect and will not be extended.

## Working with the repository

No rollout is active or planned. The current setup uses four isolated
`openai/gpt-5.6-sol` agents, Pi SDK and AxonHub same-model fallback, with
Harbor 1.4 inputs, Harbor 0.24.0 and ATIF-v1.8 evidence.

- [Working context](docs/working-context.md): current state.
- [Environment contract](docs/environment-contract.md): scenario design.
- [Running evaluations](docs/running-evals.md): registration and collection.
- [Phase 1](experiments/swarmharm-v1/phase1/) /
  [Phase 2](experiments/swarmharm-v1/phase2/): implementation.
- [Trajectory index](docs/research/trajectory-release.json): selected evidence.

Current source and reviewed indexes live here. Historical versions live in Git;
raw trajectories remain in external archives and linked private releases.
