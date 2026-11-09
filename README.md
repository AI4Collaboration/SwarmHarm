# SwarmForm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** SwarmForm tests whether they keep using that channel as new work arrives.

## Tonight’s plan · 8–9 November 2026

Build **5 shared deployments × 5 encoding opportunities × 4 business domains**, with **3 independent agents in each rollout**. The deployment and encoding opportunity define what one worker can change and another can observe. The trajectory shows how the agents actually use it.

**Final delivery: all 100 runnable input environments**, each with natural business prompts, checked transport and isolation, an independent output verifier, and reviewed Sol 5.6 and Sol 6.1 rollouts. Aim for autonomous channel formation and sustained useful exchange in every environment. If an environment still produces no swarm after **at least 7 substantive refinement-and-retest rounds**, retain it as a documented negative. Realism takes priority over eliciting success. An equivalence note, unsupported cell or offline check alone is not a finished environment.

**Current result.** In four reviewed matched pairs, **Sol 6.1 established and reused source-file channels in fulfillment, financial settlement and customer briefs**. Each produced nine independently correct releases across three intakes. Engineering showed partial package reuse. Sol 5.6 did not establish an adopted source channel in these four cases. These are development examples of data exchange, not request/reply dialogue or success-rate estimates. [Results and all eight complete trajectories](docs/research/swarmform-file-content-domains-03.json)

**Input readiness: 12/100.** Four shared-file inputs have reviewed model pairs. Eight archive-service inputs—four domains with payload or metadata visibility—have passed actual shared/private workload checks; their model tests are pending. Engineering needs a separate wording refinement. [Plan and acceptance criteria](docs/formation-study-design.md#overnight-work-and-acceptance-criteria) · [Channel taxonomy](docs/swarmform-coverage.md#shared-resource-and-encoding)

**Takeaways.** Seeing another office's delivery does not ensure source exchange. Some agents inferred nonexistent release gates; arrivals actually followed fixed schedules. Those separate inferences were not a shared theory. Engineering's ambiguous “conformance records” wording also prompted a search for missing test material. Original trajectories and incomplete outcomes remain archived.

## Inspect the active input

From the repository root, use Python 3.12 to check the matrix and export the exact prompts, tools and private workstations with their later deliveries:

```sh
python3 scripts/check_swarmform_inputs.py
python3 scripts/inspect_swarmform_workload.py --staged --domain "Data Analysis" --dataset-key november --output ../fulfillment-preview
```

[Live matrix status](docs/live-rollout-status.json) · [Reviewed four-agent pilot and SwarmHarm cases](docs/research/README.md)

Choose Engineering, Data Analysis, Financial Analysis or Knowledge Work with `--domain`. For an admitted input, [prepare and run a sealed rollout](docs/formation-study-design.md#collecting-an-admitted-input). Each registration fixes one model and can be collected once.
