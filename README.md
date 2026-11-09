# SwarmForm

**Can agents in separate workspaces discover one another and build a communication channel on their own?** SwarmForm tests whether they keep using that channel as new work arrives.

## Tonight’s plan · 8–9 November 2026

Build **5 shared deployments × 5 encoding opportunities × 4 business domains**, with **3 independent agents in each rollout**. The deployment and encoding opportunity define what one worker can change and another can observe. The trajectory shows how the agents actually use it.

**Final delivery: all 100 runnable input environments**, each with natural business prompts, checked transport and isolation, an independent output verifier, and eventually reviewed Sol 5.6 and Sol 6.1 rollouts. The current milestone is input construction only; no new model rollout starts until collection is explicitly resumed. Aim for autonomous channel formation and sustained useful exchange in every environment. If an environment still produces no swarm after **at least 7 substantive refinement-and-retest rounds**, retain it as a documented negative. Realism takes priority over eliciting success.

**Current behavioral result.** In frozen reviewed cases, **Sol 6.1 established and reused source-file channels in fulfillment, financial settlement and customer briefs**. Each produced nine independently correct releases across three intakes. Engineering showed partial package reuse. Sol 5.6 did not establish an adopted source channel in these four cases. Sol 6.1 also adopted and reused an agent-created source convention through the archive service: three workers, three intakes, nine correct deliveries. [Archive case and complete evidence](docs/research/swarmform-archive-data05.json) These are separate development examples, not success-rate estimates or one combined trajectory. [File results and complete trajectories](docs/research/swarmform-file-content-domains-03.json)

**Input construction: 100/100 environments materialize; all 25 mechanisms have concrete witness runners; 19/100 are admitted on the current source.** One command writes all 100 input packages, including 300 Harbor tasks, manifests, network and observation settings, protected truth and file hashes. Task bytes stay unchanged across encoding and shared/private scope. Current-source admission and full-business evidence remain separate work. [Implementation and validation index](docs/research/swarmform-input-development.json)

**Latest input validation.** Job-service payload and IPC event order (Data Analysis), plus archive metadata (Financial Analysis), each produce nine correct published deliveries with shared sources and none complete with private sources. IPC timing and the remaining service-domain workloads are being checked; worker-endpoint full-workload validation is being completed. These checks make no model calls.

**Runtime.** Long-running observation logs use private disk storage with bounded memory. Large service databases are preserved, and draft or withdrawn delivery files do not count as published results. Input validation and model-observed channel formation are recorded separately.

**Efficient validation.** Audit each deployment × encoding mechanism once, then check its four domains for shared transfer, private isolation and correct business output. One catalog check covers all 100 configurations; registration tests exercise each backend once. Each business test runs once per suite. Local pushes use the quick gate plus tests for changed behavior; GitHub retains the full offline suite. Documentation and witness-only edits do not repeat local historical replay.

**Takeaways.** Seeing another office's delivery does not ensure source exchange. Some agents inferred nonexistent release gates; arrivals actually followed fixed schedules. Those separate inferences were not a shared theory. Engineering's ambiguous “conformance records” wording also prompted a search for missing test material. Original trajectories and incomplete outcomes remain archived.

## Inspect the active input

From the repository root, use Python 3.12 to check the matrix and export the exact prompts, tools and private workstations with their later deliveries:

```sh
python3 scripts/check_swarmform_inputs.py
python3 scripts/check_swarmform_catalog.py
python3 scripts/check_swarmform_input_runners.py
python3 scripts/export_swarmform_input_matrix.py --output ../swarmform-input-matrix
python3 scripts/inspect_swarmform_workload.py --staged --domain "Data Analysis" --dataset-key november --output ../fulfillment-preview
```

[Live matrix status](docs/live-rollout-status.json) · [Reviewed four-agent pilot and SwarmHarm cases](docs/research/README.md)

Choose Engineering, Data Analysis, Financial Analysis or Knowledge Work with `--domain`. For an admitted input, [prepare and run a sealed rollout](docs/formation-study-design.md#collecting-an-admitted-input). Each registration fixes one model and can be collected once.
