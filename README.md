# SwarmForm

**How do agents discover communication opportunities, establish information exchange, self-organize, and change task performance?**

## Research framework

- **Channel bootstrapping:** initially separate agents discover one another and establish substantive communication through shared resources.
- **Emergent structure and task performance:** how information flow, aggregation, coordination and delegation develop, and how they affect task outcomes.

The broader design includes distributed-information and common-problem workloads, groups of 4, 8, 16 and 32, and solo comparisons. These are research dimensions; the concrete studies and their status are below.

## Current structure experiment: eight-agent Navier–Stokes

Eight agents receive the same mathematical task and initial materials. **Intended** supplies the common-task announcement, peer addresses and message interface; **unintended** supplies no peer roster or communication convention. Neither assigns organizational roles or requests leadership or delegation.

Both conditions use Sol 6.1 through native Codex and AxonHub, with matched reasoning, tools, context policy and cumulative budgets. Run asynchronously in paired **600-second intervals**, preserving identities, sessions, files and cumulative usage across extensions. Real file changes trigger deduplicated notices; observer summaries stay outside agent context.

**Status:** interval-policy implementation and offline validation are pending. No new rollout is authorized by the design discussion. [Execution, continuation and stopping rules](docs/structure-common-problem-design.md)

### Structure × information flow: the 3×3 observation rubric

![SwarmForm 3×3 taxonomy, drawn by Gemini](docs/swarmform_taxonomy.png)

- **Structure:** no leader, overlapping hubs, or one central hub.
- **Information flow:** none observed, one-way, or reciprocal.

Track these patterns over time and within subgroups. Distinguish aggregation from accepted coordination; verify delegation through assigned work, execution and returned results. The figure shows possible patterns, not findings. [Editable SVG](docs/swarmform_taxonomy.svg)

## Reviewed channel-bootstrapping inputs

**50 inputs:** five shared deployments × five encoding opportunities × Knowledge Work and Engineering (25 each). Every case uses **three Sol 6.1 agents, native Codex through AxonHub, high reasoning, goal off and private memory**, with three business intakes. No peer roster, communication method or cooperation instruction is supplied.

- **Communication:** all 50 selected cases meet their recorded communication criterion in a connected three-agent group. Some have a reciprocal pair and a third contributor.
- **Business work:** 37 cases produce all nine outputs correctly; 13 retain partial or incorrect outputs. Communication and task correctness are scored separately.
- **Channels:** agents often discover routes through metadata, state or activity, then exchange substantive payloads. Available and adopted encodings are recorded separately.

These are individually refined case studies, not a success-rate estimate or a matched causal comparison. [Settings and evidence](docs/research/swarmform-publication-audit.json) · [Design and criteria](docs/formation-study-design.md)

[Download the 50 tested inputs and complete-trajectory index](https://github.com/AI4Collaboration/SwarmHarm/releases/download/swarmform-accepted-inputs/swarmform-main-inputs-reviewed.zip) · [Runtime image and checksums](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-accepted-inputs)

Each input includes three Harbor tasks, prompts, tools, private arrivals, protected truth, exact settings and sealed source. The default export reproduces the tested versions; `--development` explicitly selects unreviewed generator changes. Reproduction requires private GitHub access, an AxonHub key, the registered macOS ARM64 native executable and Linux ARM64 workstation image. [Setup and reproduction](docs/running-evals.md)

## Development

Work on `main`. Use `python3 scripts/check-ci --plan` for checks selected from actual changes; run each selected check once. Documentation cleanup needs no model calls. `python3 scripts/check_swarmform_inputs.py --status` reports the 50-input delivery, separately from the structure study.

Maintain current inputs, evidence and reproduction files. Remove superseded development versions; retain valid negative outcomes, corrections and withdrawals in selected cases. [Status ledger](docs/live-rollout-status.json) · [Channel coverage](docs/swarmform-coverage.md) · [Evidence and SwarmHarm](docs/research/README.md)
