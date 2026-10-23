# Dataset development plan

## Unit of study

The publishable unit is one multi-agent campaign with separate sandboxes,
ordinary business tasks, persistent shared systems, native traces and an
independent verifier. Individual prompts and seeded component probes are not
campaign-level evidence.

## Two phases

1. **Form the Swarm:** connect real residue, autonomous reach-out and a different
   agent's independently discovered method contribution in one persistent run.
2. **Cause Harm:** show that a later fresh agent receives the actual method,
   applies it on a different business object and causes a verified adverse
   effect.

The active Phase 1 environment is
[swarm-formation-v8](../experiments/swarm-formation-v8/README.md). V8 has three agents, one per hidden arrival period, and
no per-agent response-count or tool-call-count limit. V8 DeepSeek R3 passed the
registered Phase 1 gate in one development campaign. Earlier runs remain frozen
evidence for their original settings.

The active Phase 2 environment is
[swarm-cause-harm-v1](../experiments/swarm-cause-harm-v1/README.md). It requires
direct full-body method receipt, different-project execution and a new effect
recomputed from source truth. Its offline controls pass; no model campaign has
been collected yet. The Phase 1 and Phase 2 component results are still reported
separately until one future campaign connects the full chain end to end.

## Campaign record

Each campaign preserves:

- the legitimate task, blocker and ordinary completion truth;
- agent sandboxes, arrival order and persistent shared systems;
- Harbor task packages, frozen model route, prompt and code hashes;
- native requests, responses, tool results and shared-artifact versions;
- ATIF-v1.8 exports and an independent provenance review;
- separate labels for residue, read, request, method discovery, contribution,
  receipt, different-task adoption and verified effect.

## Development loop

1. Validate the environment, persistence and verifier offline.
2. Run one minimum connected campaign per model.
3. Inspect every trace and identify the first missing link.
4. Change one mechanism only, freeze a new registration and rerun.
5. Preserve negative, incomplete and provider-failed campaigns separately.

Routine development stays small. Larger rate studies begin only after the
environment and labels stop changing.

## Data sources

The current formation fixtures are maintained synthetic supplier-review tasks.
Source-backed MiMo Harbor tasks remain candidates for later domain expansion.
ImpossibleBench, Hack-Verifiable Environments and Hackbait inform task and
verifier design; they do not constitute SwarmHarm coverage by themselves.

[Current sources](research/task-sources-and-verification.md) ·
[Environment contract](environment-contract.md) ·
[Run guide](running-evals.md)
