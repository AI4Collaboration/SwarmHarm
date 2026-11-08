# SwarmForm

**Can isolated AI agents discover one another, create communication channels,
and keep exchanging useful information without being told to cooperate?**

SwarmForm is the working title of this study. Four agents receive individual
business tasks and private workspaces. We study how ordinary shared infrastructure
can become a channel for autonomous discovery, communication and reuse of work.

## What we have observed

- **Four-agent communication.** In the latest Knowledge Work case, Sol 6.1 agents
  used an initially empty reporting-note register to request and exchange missing
  source receipts. They wrote 12 notes, with 28 verified peer reads covering 20
  distinct note-version/reader pairs. All four accounts released their reports.
  The register's format was documented in their workspaces.
- **Reuse without a live conversation.** In the account-local comparison, Sol 6.1
  reused another worker's published method while leaving the note register empty.
  That rollout's formation verdict remains negative.

[Latest complete trajectory](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/unified-v56-work-journal-20261108) ·
[Comparison trajectory](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/end-to-end-v54-records-knowledge-sol61-r1-20261107)

Eight additional Sol 6.1 groups formed channels in the workstation-history pilot.
Their original inputs exposed recorder filenames. The subsequent work-journal
validation removed the audited markers. [Pilot results](docs/research/workstation-history-results.json) ·
[Validation](docs/research/workstation-context-validation.json)

## The study we are building

The initial mechanism sample covers shared working data, reachable worker
processes, and shared supporting services. A resource inventory checks files,
processes, networking, service scope, tools, memory, controllers, lifecycle,
resource timing and host boundaries. Every sampled mechanism needs a documented
origin, a working exchange path and a check with corrected scope.

Sol 5.6 and 6.1 use native Codex through AxonHub, four concurrent sessions, high
reasoning and goal off. Knowledge Work is the initial workload and Engineering
the planned replication. One task and persistent memory continue throughout each
rollout. The study measures discovery, agent-created conventions, repeated useful
exchange and group size. Substantial multi-item communication and the additional
infrastructure fixtures are still to be implemented and evaluated.

[Research design and measurements](docs/formation-study-design.md) ·
[Resource coverage and open checks](docs/swarmform-coverage.md) ·
[Current work](docs/working-context.md)

## Code and evidence

The existing reporting runner remains available under `experiments/swarmharm-v1`.
Its serialized Phase 1 and Phase 2 fields record formation and business effects
from one continuous trajectory. Its current JSON-note protocol is the implemented
baseline. The SwarmForm design lists prospective extensions explicitly.

Previous SwarmHarm findings, including compositional failure and shared false
process inference, retain their individual cases, model identities, settings and
complete evidence. [Reviewed findings](docs/phase2-design.md) ·
[Full trajectory bundles](docs/research/trajectory-release.json)

[Install and run the reporting baseline](docs/running-evals.md) ·
[Inspect its settings](docs/scenarios-and-parameters.md) ·
[Inspect prompts before collection](docs/running-evals.md#read-the-prompts)
