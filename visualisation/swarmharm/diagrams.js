// This file holds the SwarmHarm reporting baseline diagrams only. Edit them here only.
// Each environment has four diagrams:
// ontology (classDiagram), sequence (sequenceDiagram), object (instances) and conceptual (flowchart).
// Each diagram lists the repository files it uses. Paths start at the repository root.
// Each environment has a summary: one headline sentence and up to three plain-language points.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.DIAGRAMS = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const environments = [
    {
      id: 'reporting_baseline',
      title: 'SwarmHarm reporting baseline',
      summary: { headline: "This baseline runs four AI workers on one reporting task and records whether they coordinate and what effect their combined work has.", points: ["Each worker has its own workstation and session. All of them use one shared business reporting system.", "One run gives two readings: whether the workers formed a channel, and what the final effect was.", "An independent replay rebuilds the final effects, so the results do not depend on what the workers say."] },
      diagrams: [
        {
          kind: 'ontology',
          title: 'Ontology: reporting baseline',
          sources: ['docs/environment-contract.md', 'docs/architecture/shared-core-and-phases.md', 'experiments/swarmharm-v1/phase2/world_config.py', 'docs/business-outcome-criteria.md'],
          mermaid: `classDiagram
  class Rollout {
    one task
    one persistent session
    one shared world
  }
  class WorldConfig {
    access, coupling, verification, observation
  }
  class Workstation {
    private current.jsonl journal
  }
  class ReportingNote {
    agent-authored only
  }
  class SourceReceipt {
    names a request, not an agent
  }
  class Release {
    delivered CSVs
  }
  class Grader {
    completion_basis
  }
  class Replay {
    independent effect reconstruction
  }
  class Trajectory {
    phase1 label
    phase2 label
  }
  Rollout "1" --> "1" WorldConfig
  Rollout "1" --> "4" Workstation
  Workstation --> ReportingNote : writes
  WorldConfig --> SourceReceipt : source_routing
  Workstation --> Release : publishes
  Grader --> Release : checks
  Replay --> Release : reconstructs
  Rollout --> Trajectory : yields
`,
        },
        {
          kind: 'sequence',
          title: 'Sequence: registered rollout lifecycle',
          sources: ['docs/environment-contract.md', 'docs/running-evals.md', 'experiments/swarmharm-v1/run.py', 'experiments/swarmharm-v1/review.py'],
          mermaid: `sequenceDiagram
  participant Op as Operator
  participant R as Run
  participant W as Workstations
  participant S as Reporting service
  participant Rv as Reviewer
  Op->>R: register and seal inputs, verify hashes
  R->>W: start sessions, deliver the autonomous rule once
  loop business work
    W->>S: stage, upload, dispatch, release
    S-->>W: concrete observations and mismatches
  end
  R->>Rv: native records and terminal captures
  Rv->>Rv: replay effects independently
  Rv->>Op: formation and consequence labels from one trajectory
`,
        },
        {
          kind: 'object',
          title: 'Objects: cross-account ring routing',
          sources: ['docs/environment-contract.md', 'experiments/swarmharm-v1/configs/unified-cross-account-source-routing.json'],
          mermaid: `flowchart LR
  cfg["cfg1 : WorldConfig<br/>source_routing = cross_account_ring<br/>completion_basis = contents"]
  a["account1 : Workstation"]
  b["account2 : Workstation"]
  c["account3 : Workstation"]
  d["account4 : Workstation"]
  ra["receipt for account1 : SourceReceipt"]
  rb["receipt for account2 : SourceReceipt"]
  rc["receipt for account3 : SourceReceipt"]
  rd["receipt for account4 : SourceReceipt"]
  cfg --> a
  cfg --> b
  cfg --> c
  cfg --> d
  b --- ra
  c --- rb
  d --- rc
  a --- rd
`,
        },
        {
          kind: 'conceptual',
          title: 'Concept: one trajectory, two labels',
          sources: ['docs/architecture/shared-core-and-phases.md', 'docs/environment-contract.md'],
          mermaid: `flowchart LR
  task["One business task per agent"] --> traj["One trajectory"]
  traj --> p1["Phase 1 label: autonomous formation"]
  traj --> p2["Phase 2 label: registered consequence"]
  p1 -.-> no1["Not a gate for tools or a second task"]
  p2 --> rep["Independent replay of final effects"]
  traj --> neg["Stopping, partial work, corrections and restoration are preserved"]
`,
        },
      ],
    },
  ];

  return { kinds: ['ontology', 'sequence', 'object', 'conceptual'], environments };
});
