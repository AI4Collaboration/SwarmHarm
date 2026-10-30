# One shared core. Two separate phases.

**Design only — runtime code is unchanged.**
Branch: `codex/shared-core-phases`, based on PR #14 (`ee5114bae`).

## 1. The structure

Each phase owns its business logic. Both use the **same collector and harness interface**.

```mermaid
flowchart TB
    S["Study + scenario<br/>Choose which phases to execute"] --> C
    P1["phase1/<br/>Tasks · tools · formation checks"] <--> C
    P2["phase2/<br/>Tasks · tools · outcome checks"] <--> C
    C["SHARED CORE<br/>Scheduling · sessions · shared world · evidence"] <--> H
    H["Shared harness interface"] --> PI["Pi"]
    H --> CL["Claude"]
    H --> CX["Codex"]
```

Arrows show runtime interaction, not Python imports. Each rollout selects **one harness**.
Neither phase needs to know which harness it uses.

## 2. Why this design?

```mermaid
flowchart TB
    A["Separate collectors"] --> A1["Duplicate scheduling<br/>and evidence logic"]
    A1 --> A2["Reject"]
    B["Shared core + phase packages"] --> B1["One execution path<br/>Separate places to work"]
    B1 --> B2["CHOSEN"]
    D["General workflow engine"] --> D1["Plugin and workflow machinery<br/>for only two phases"]
    D1 --> D2["Defer"]
```

The current collector mixes these responsibilities in one 1,440-line file.
Changing folder names alone would keep that coupling.

## 3. How a rollout would execute

All modes use the shared core. **Phase 1-only and Phase 2 component modes are future additions on this branch.**

```mermaid
flowchart TB
    M{"Study mode"}
    M -->|connected — existing default| C1["Phase 1"]
    C1 --> G{"Formation gate passes<br/>before termination?"}
    G -->|Yes| D["Finish in-flight work"]
    D --> C2["Phase 2<br/>Same agents and histories"]
    G -->|No| N["Preserve outcome<br/>Phase 2 not assessed"]
    M -->|phase1 — proposed| P1["Phase 1 only"]
    P1 --> R1["Formation result"]
    M -->|phase2-component — proposed| I["Fresh agents<br/>Frozen business inputs"]
    I --> P2["Phase 2 only"]
    P2 --> R2["Conditional outcome<br/>No formation claim"]
```

The harness choice is independent: **Pi, Claude or Codex** follows the selected mode.
Each mode/scenario combination still needs its own validation.

## 4. Separate code, continuous sessions

For a connected rollout, changing phases changes the assignment and available tools.
It does **not** create another population.

```mermaid
sequenceDiagram
    participant P1 as Phase 1
    participant C as Shared core
    participant A as Agent sessions
    participant P2 as Phase 2
    C->>A: Start all agents together
    P1->>C: Initial tasks and tools
    C->>A: Deliver business work
    A-->>C: Native events and tool calls
    C->>P1: Evidence for formation check
    P1-->>C: Passing gate with evidence
    C->>A: Let in-flight work finish
    P2->>C: Continuation tasks and tools
    C->>A: Update tools and deliver new work
    Note over C,A: Same sessions and histories<br/>Same workstations and shared state
    A-->>C: Continue the same rollout
```

If transition setup fails, preserve the partial state and stop. Do not silently
restart sessions or stitch together separate histories.

## 5. Where we work

```text
experiments/
├── runtime/                  ← shared Pi, Claude and Codex adapters
└── swarmharm-v1/
    ├── run.py                ← existing command stays
    ├── launch.py
    ├── review.py
    ├── export_atif.py
    └── swarmharm/
        ├── contracts.py      ← agreed interfaces
        ├── core/             ← collector, shared world, evidence
        ├── studies/          ← connected / phase1 / phase2-component
        ├── phase1/           ← Phase 1 tasks, tools, checks, tests
        ├── phase2/           ← Phase 2 tasks, tools, checks, tests
        ├── domains/          ← genuinely shared business definitions
        └── scenarios.py      ← pairs the phases for each scenario
```

```mermaid
flowchart TB
    I["Agree on interfaces<br/>Extract shared core"] --> P1["Phase 1 work<br/>phase1/"]
    I --> P2["Phase 2 work<br/>phase2/"]
    I --> H["Harness work<br/>runtime/"]
    P1 --> T["Integrate and check compatibility"]
    P2 --> T
    H --> T
    T --> M["Add study modes one at a time"]
    M --> V["Fresh registered live validation"]
```

**Parallel work starts after the interfaces settle.** One owner integrates shared
contract changes. Phase packages do not import each other or provider SDKs.

Concurrent rollouts also stay isolated:

```mermaid
flowchart TB
    SRC["Same shared implementation"] --> A["Rollout A<br/>Frozen checkout A"]
    SRC --> B["Rollout B<br/>Frozen checkout B"]
    A --> AO["Collector A · sessions A<br/>Output A · lock A"]
    B --> BO["Collector B · sessions B<br/>Output B · lock B"]
```

## 6. What must survive the refactor

| Preserve | Check before moving on |
| --- | --- |
| Existing commands, prompts, tools and authentication | Compare with PR #14 fixtures |
| Agent identity and history across phases | Test the transition with all three adapters |
| Native traces and output layout | Keep execution and delivery evidence distinct |
| Frozen registrations and results | New source needs a new registration |
| Imports, tests and source hashes | Include nested packages before moving files |

**First implementation step:** extract the shared interfaces and source inventory.
Then extract the collector; then split phase code. Add new modes afterward.

[Implementation reference](shared-core-and-phases-notes.md) contains the exact
contracts, migration checks and upstream integration notes. Newer `main` has not
been merged. No rollout is launched by this proposal.
