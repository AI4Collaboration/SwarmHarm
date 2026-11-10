# SwarmForm

**When eight agents receive the same difficult research problem, do they spontaneously develop organizational structure, and how does that structure change over time?**

## Current research plan

This is the repository's **single active research direction**: emergent structure during Navier–Stokes theoretical research, comparing intended and unintended communication. This README is the current roadmap; the [detailed protocol](docs/structure-common-problem-design.md) specifies the same study's execution and stopping rules.

**Status: design agreed; ten-minute interval support still needs implementation and offline validation. No new rollout is running or authorized by the planning discussion.** Existing scheduling, timing and context fixes are available, but the sustained runtime still contains the old fixed 90-minute policy and terminal session closure. It must not be treated as an implementation of the new plan.

### One task, eight agents, two conditions

- **Task:** theoretical exploration of Navier–Stokes existence and regularity, with checkable partial arguments, explicit assumptions and unresolved obstacles. All eight agents receive the same mathematical task and initial materials at activation. We do not preassign subproblems.
- **Intended:** explicitly tell each agent that eight agents are working on the common task; disclose peer addresses and the available message interface. The communication opportunity is supplied, while organization must emerge from their actions.
- **Unintended:** provide no peer roster, joint-work announcement or predefined communication convention. Agents have the same research objective and access to the shared substrate; they must discover any peers and communication practice themselves. This is absence of supplied communication, not proof that communication cannot occur.
- **Matched execution:** one eight-agent rollout per condition, run concurrently in separate environments. Use the same Sol 6.1 model through native Codex and AxonHub, reasoning setting, tools, mathematical materials, context policy, scheduling policy and cumulative token/response/tool-call allowances. Intended disclosure is the experimental difference; there is no cross-condition communication.
- **No organizational prompting:** do not request division of work, aggregation, leadership, delegation or an orchestrator, at startup or later. Do not reward message counts. Continue justified research, retain useful partial work and record concrete obstacles; ending one response does not finish the study.

The current scope is this eight-agent common-problem pair. Other population sizes, distributed-information workloads, solo uplift comparisons and SwarmHarm reporting are outside the active plan.

### Ten-minute increments with asynchronous work

Start both conditions with **10 minutes**. At each observation boundary, stop or add **one further 10-minute interval to both conditions**: 10 → 20 → 30, as justified. There is no precommitted total duration and no unbounded automatic extension. Ten minutes is an observation and extension unit, not a synchronized agent round or a required period of waiting.

Keep the same agents, native sessions, context, files and pending work across an accepted extension. Cumulative usage never resets; register equal finite resource caps before collection. Adding time does not replenish those caps. Report actual resource consumption separately from the equal allowances.

Agents advance independently. Actual stable file changes trigger neutral, deduplicated path notices; eligible research continuations start without an artificial sleep. Measure busy-agent notice receipt separately from notification enqueue time. Reduce notification and scheduling delays without fabricating exchanges or telling agents to communicate more.

Record each extension decision and its reason, such as substantive research still progressing or an unfinished feedback chain. Absence of an orchestrator alone is not a reason to keep extending. Without an accepted extension, dispatch no new work past the boundary and bound cancellation time. Stop earlier for exhausted resources, a user stop, infrastructure failure, or verified quiescence: all agents explicitly paused with no active work, pending notices or unsettled changes. Neither a completed response nor 30 seconds of silence is sufficient. Record unequal termination and compare the common observed horizon.

### What we observe

The central outcomes are **spontaneous aggregation, multilevel delegation, orchestrator formation and responsibility transfer**. Aggregation itself can be a structure. A strong orchestrator claim additionally needs evidence that other agents act on its coordination; self-description or high message volume alone is insufficient.

For multilevel delegation, trace a linked task from A to B to C, its execution and returned results. Distinguish this from A separately asking both B and C, or B merely forwarding text. Track formation, persistence, overlapping responsibilities, handoffs and dissolution, including incomplete or ambiguous chains.

At each ten-minute boundary, report both the new interval and cumulative evidence:

- Structure and information-flow states, with exact event times, affected agents and evidence for transitions.
- Actual reads, downstream use, substantive replies and returned results; distinguish notifications from completed interactions.
- Model and tool time, publication detection, notification queueing, native receipt, idle time and context maintenance.
- Resource usage, checkable mathematical progress, pending work and the extension or stopping reason.

Retain complete trajectories, artifact versions and segmented timing for future collection once authorized. Observer reports are not sent to the agents. Consecutive intervals are parts of one continuing pair, not independent replications; one adaptive pair does not establish an emergence rate or a causal advantage of either condition.

### Structure × information flow: the 3×3 observation rubric

![SwarmForm 3×3 taxonomy, drawn by Gemini](docs/swarmform_taxonomy.png)

The figure and its [editable SVG](docs/swarmform_taxonomy.svg) were drawn by Gemini. They illustrate possible patterns, not observed results or participant instructions.

- **Structure:** no leader, multiple overlapping hubs, or one central hub.
- **Information flow:** no observed peer information flow, one-way flow, or reciprocal flow.

Apply the axes to time-local events and subgroups as well as the full cohort. Record an aggregation hub separately from an accepted coordinator. One agent writing a final draft alone does not establish that peers recognized its authority. Do not force uncertain or mixed evidence into a cell, assume all nine cells occur, or carry a label unchanged across the run.

## Next work on this same study

1. Implement matched 600-second deadline extensions, bounded request/shutdown timeouts, cumulative accounting and state retention. Replace the participant-facing 90-minute commitment while preserving neutral continuation language. Verify boundary behavior during context maintenance and interruption.
2. Validate the policy offline, including matched intended/unintended settings, full timing capture, no injected organizational cues, no budget reset and no work beyond the accepted boundary. Publish the exact prompts, finite caps and stopping logic for review before collection.
3. Once collection is authorized, run this pair, review each interval and extend in ten-minute increments when justified. Use the resulting evidence to report structure over time, not to require a positive orchestrator finding.

The [status ledger](docs/live-rollout-status.json) records this study under `supplemental_studies.eight_member_common_problem.incremental_interval_design`; that historical storage location does not make it a second research direction. Its top-level completed input matrix describes the earlier delivery.

## Prior work and accepted inputs

The completed channel-discovery study supplies the infrastructure and historical evidence for this research. It covers **50 reviewed environments: five shared substrates × five encoding opportunities × two domains**, with three agents per case. Substrates were shared files, IPC, worker endpoints, artifact namespaces and job namespaces; encoding opportunities were payload, metadata, state, events and timing. These are prior configurations, not an additional collection plan.

All 50 selected cases meet their recorded communication criterion. Of them, 37 deliver all nine business outputs correctly and 13 retain partial outcomes. These are individually refined cases, not an estimate of general swarm success. [Publication audit](docs/research/swarmform-publication-audit.json) · [Historical design and reproduction](docs/formation-study-design.md) · [Evidence archive](docs/research/README.md)

### Accepted inputs

[Download the 50 accepted inputs and trajectory index](https://github.com/AI4Collaboration/SwarmHarm/releases/download/swarmform-accepted-inputs/swarmform-main-inputs-reviewed.zip) · [Private Release and checksums](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-accepted-inputs)

These packages preserve their original three-agent tasks, runtimes and reviewed evidence. Their reproduction commands are in the historical design; they do not launch the current eight-agent interval study. Older structure findings and engineering validation remain background evidence. Deleted cancelled-run trajectories are not restored or used as results for the new plan.

## Development

Work on `main`. Use `python3 scripts/check-ci --plan` to preview checks selected from the actual changes, then run the selected checks once; reserve `--full` for intentional full regression. Documentation updates require no model calls or Docker rollout. `python3 scripts/check_swarmform_inputs.py --status` reports the historical input delivery, not completion of the current structure study.

Keep exact prompts, registered source, budgets and observed evidence bound to each future rollout. Keep credentials and raw trajectories outside Git. Preserve agents' decisions not to communicate or form a hierarchy as valid observations. Changes to this research plan belong here and in its detailed protocol; historical registrations are not rewritten to match new settings.
