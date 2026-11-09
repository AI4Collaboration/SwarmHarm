# SwarmForm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** SwarmForm tests whether they keep using that channel as new work arrives.

## Tonight’s plan · 8–9 November 2026

Build **5 shared deployments × 5 encoding opportunities × 4 business domains**, with **3 independent agents in each rollout**. The deployment and encoding opportunity define what one worker can change and another can observe. The trajectory shows how the agents actually use it.

**Final delivery: all 100 runnable input environments**, each with natural business prompts, checked transport and isolation, an independent output verifier, and reviewed Sol 5.6 and Sol 6.1 rollouts. Aim for autonomous channel formation and sustained useful exchange in every environment. If an environment still produces no swarm after **at least 7 substantive refinement-and-retest rounds**, retain it as a documented negative. Realism takes priority over eliciting success. An equivalence note, unsupported cell or offline check alone is not a finished environment.

**Current behavioral result.** In frozen reviewed cases, **Sol 6.1 established and reused source-file channels in fulfillment, financial settlement and customer briefs**. Each produced nine independently correct releases across three intakes. Engineering showed partial package reuse. Sol 5.6 did not establish an adopted source channel in these four cases. Sol 6.1 also adopted and reused an agent-created source convention through the archive service: three workers, three intakes, nine correct deliveries. [Archive case and complete evidence](docs/research/swarmform-archive-data05.json) These are separate development examples, not success-rate estimates or one combined trajectory. [File results and complete trajectories](docs/research/swarmform-file-content-domains-03.json)

**Input progress: 100/100 configurations export; 4/100 are admitted on the current source.** All five deployments and five encoding opportunities use the same four workloads, prompts and private arrivals. The current runtime removes a misleading private `/registry`; the selected deployment is now the only cross-workspace business carrier. Shared-file payload inputs in all four domains now have fresh shared/private witnesses: the combined sources complete all 9 releases, while each private-scope counterpart completes none. Exact transfer, isolation and output checks for the remaining 96 cells are in progress. [Implementation and validation index](docs/research/swarmform-input-development.json)

**New input checks.** File metadata passed all four domains: nine correct deliveries with shared access and zero with private scope. Exact directory reads and delivered files are independently checked; native Codex fixtures preserve sessions and only notify on new arrivals. [Full operator evidence](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-file-metadata-inputs-01) IPC event order also passed all four domains with complete source reconstruction and checked outputs. [Full operator evidence](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-ipc-event-inputs-01) Model rollouts for these new inputs are next.

**Runtime.** Long-running observation logs use private disk storage with bounded memory. Large service databases are preserved, and draft or withdrawn delivery files do not count as published results. The full current-source offline suite passes; exportability and transport feasibility are not counted as channel formation.

**Takeaways.** Seeing another office's delivery does not ensure source exchange. Some agents inferred nonexistent release gates; arrivals actually followed fixed schedules. Those separate inferences were not a shared theory. Engineering's ambiguous “conformance records” wording also prompted a search for missing test material. Original trajectories and incomplete outcomes remain archived.

## Inspect the active input

From the repository root, use Python 3.12 to check the matrix and export the exact prompts, tools and private workstations with their later deliveries:

```sh
python3 scripts/check_swarmform_inputs.py
python3 scripts/check_swarmform_catalog.py
python3 scripts/inspect_swarmform_workload.py --staged --domain "Data Analysis" --dataset-key november --output ../fulfillment-preview
```

[Live matrix status](docs/live-rollout-status.json) · [Reviewed four-agent pilot and SwarmHarm cases](docs/research/README.md)

Choose Engineering, Data Analysis, Financial Analysis or Knowledge Work with `--domain`. For an admitted input, [prepare and run a sealed rollout](docs/formation-study-design.md#collecting-an-admitted-input). Each registration fixes one model and can be collected once.
