# Implementation reference: shared core and phases

Start with the [visual design](shared-core-and-phases.md). This companion keeps
the detailed contracts, compatibility requirements and validation plan for implementation.

Status: design proposal; no runtime changes. 30 October 2026.

Branch: `codex/shared-core-phases`, based on PR #14 at
`ee5114bae85023b2b4a76299f92e6f8b2ec7d864`.

## Decision

Keep one collector and one implementation of each harness. Separate Phase 1
and Phase 2 into packages with their own tasks, tools, fixtures, verification
and tests. A small study definition selects which phases execute and how they
start. The shared core owns sessions, scheduling, workstations and evidence.

This gives Phase 1, Phase 2 and harness development separate places to work.
It also supports different study modes without copying collectors. The existing
continuous rollout remains the default, with the same live population and the
existing Phase 1 gate. Directory separation does not restart an agent.

This document describes the target and migration order. None of the proposed
packages, interfaces or additional CLI modes are implemented by this change.

## What needs separating

At the PR #14 baseline:

- `run.py` is 1,440 lines. Preparation, provider selection, collection, notices,
  phase transitions, evidence and CLI configuration share the same module.
  `collect()` contains the scheduler as nested functions and branches on harness
  kind. Changes to either phase or a harness converge on this file.
- The three adapters already have the same useful session operations:
  `prompt`, `set_tools`, `reply` and `close`. Keep this working boundary.
  Codex currently imports queue helpers from `pi_agent`; shared transport
  utilities should have a neutral owner.
- `lab.py` combines workstation/shared-record infrastructure with Phase 1
  documents, tools, visibility, notifications and business services. Phase 2
  continuations mutate that same world. Moving all of `lab.py` into Phase 1
  would leave Phase 2 dependent on Phase 1 implementation details.
- Domain files mix phases. For example, `domains/financial_analysis.py`
  contains both `ReviewService` and `FundingService`, both sets of fixtures,
  documents and registration settings. Renaming the file would not separate
  ownership.
- `review.py` owns formation assessment and calls integrated/domain reviewers.
  Some reviewers load other modules by filename and manipulate `sys.modules`.
  The exporter also contains harness-specific evidence interpretation.
- Source sealing uses top-level Python globs, a domains glob and explicit
  runtime paths. Review has its own `EVALUATOR_PATHS`. New subdirectories would
  be missed unless both inventories change. Several modules derive paths from
  their current `__file__` depth; tests import and patch the old modules.

Sources: [collector](../../experiments/swarmharm-v1/run.py),
[world](../../experiments/swarmharm-v1/lab.py),
[scenario resolution](../../experiments/swarmharm-v1/domain_runtime.py),
[exporter](../../experiments/swarmharm-v1/export_atif.py).

## Designs considered

| Design | Parallel development | Main cost | Decision |
| --- | --- | --- | --- |
| Separate Phase 1 and Phase 2 applications, sharing a utility library | Separate entry points and teams | Duplicated scheduling, registration and evidence; continuous sessions need a new handoff protocol | Reject. Too much behavior can diverge. |
| One shared core, phase packages and explicit study definitions | Phase and harness work separates after a small contract extraction | Careful migration of world ownership and imports | **Choose this.** It fits the existing persistent sessions and continuations. |
| General workflow/DAG engine with dynamically discovered plugins | Many arbitrary phase sequences | New workflow configuration, plugin lifecycle, persistence and compatibility machinery | Defer. Two phases and three known harnesses do not justify it. |

A folder-only move is insufficient: it keeps the same dependencies and conflict
points while changing every path. The migration must extract responsibilities
before relocating large files.

## Proposed layout

```text
experiments/
  runtime/                         # phase-independent execution adapters
    session.py                     # session protocol, event types, queue helpers
    harnesses.py                   # explicit registry for the three adapters
    pi_agent.py                    # existing Pi implementation
    pi/                            # existing pinned Node bundle
    claude_agent.py                 # existing Claude implementation
    claude/                        # existing pinned Node bundle
    codex_agent.py                  # existing Codex auth/runtime setup
    codex_session.py                # existing native thread implementation
    codex_rpc.py
    codex_mcp.py
    codex_evidence.py
    workstation.py                 # existing Docker implementation
    atomic.py
    guardrails.py
    response_monitor.py
  swarmharm-v1/
    run.py                         # compatible CLI entry point
    launch.py                      # compatible process launcher
    review.py                      # compatible review entry point
    export_atif.py                 # compatible export entry point
    protocol.json                  # existing published contract locations
    domain-scenarios.json
    registrations/                 # existing frozen records
    swarmharm/                     # importable Python package
      contracts.py                 # phase/study interfaces and shared types
      core/
        collector.py               # single event loop and session lifecycle
        registration.py            # preparation, source inventory and freeze
        world.py                   # shared records, workstations, event journal
        evidence.py                # persistence, manifests and common ATIF work
        paths.py                   # explicit repository and artifact paths
      studies/
        connected.py               # current Phase 1 -> Phase 2 policy
        phase1.py                  # future Phase 1-only policy
        phase2_component.py         # future explicit component initialization
      phase1/
        runtime.py                 # initial task, tools, notices, completion
        review.py                  # formation evidence and gate
        domains/                   # Phase 1 fixtures and business services
        tests/
      phase2/
        runtime.py                 # continuation binding and tool routing
        review.py                  # Phase 2 assessment, domain dispatch
        domains/                   # Phase 2 fixtures, services and replay
        tests/
      domains/                     # only genuinely shared business definitions
      scenarios.py                 # explicit composition of the four scenarios
      tests/                       # core, harness and cross-phase contracts
    lab.py, domain_runtime.py, ...  # temporary compatibility entry points
```

Every new Python package has an `__init__.py`. New code uses qualified
`swarmharm.*` and `experiments.runtime.*` imports. Legacy scripts establish
their import roots once; internal modules do not mutate `sys.path` or remove
other modules from `sys.modules`. Existing runtime imports migrate in small
steps; tests must detect two differently named copies of the same state module.

Keep the pinned JS bundles and native adapters in their existing locations.
There is no benefit in rewriting them into one language or changing their
installation paths for this separation. `harnesses.py` selects existing
implementations; it does not add a second agent loop.

## Ownership and dependency rules

| Owner | Owns | Must not own |
| --- | --- | --- |
| Harness adapter | Authentication, exact runtime/model checks, native session, tools transport, native recording and interpretation | Phase gates, business completion or synthetic effects |
| Shared core | Actor/session lifecycle, start barrier, scheduling, limits, tool dispatch, event sequence, storage and cleanup | Domain-specific success rules or new subject instructions |
| Phase 1 | Initial business tasks and tools, discoverable records, activity policy, formation assessment | Harness construction or Phase 2 settlement rules |
| Phase 2 | Continuation work, business actions, completion and independent effect verification | Creating a new population in a connected rollout or manufacturing formation evidence |
| Study definition | Initial phase, allowed transition, terminal policy and claim scope | A second collector or provider-specific execution loop |
| Scenario composition | Matching phase implementations, shared business identities and frozen settings | Credentials or mutable process-global configuration |

Dependency direction: the entry point composes a study, scenario and harness;
the collector talks to their contracts. Phase implementations use shared world
services. Harness implementations use the shared session protocol. Phases do
not import each other or any provider SDK. The core does not import a concrete
phase to decide business behavior.

During extraction, adapters may delegate to legacy `lab.World` and
`Continuation`. This is a temporary migration boundary. The final shared world
owns shared storage, workspace access and ordered event commits; Phase 1 owns
its visibility and activity policies. Phase 2 receives references to the same
world services and relevant business records, not a copy of Phase 1 state.

Do not move every domain helper into shared code. Finance funding behavior
belongs in Phase 2; reconciliation behavior belongs in Phase 1. Share stable
record identities, schemas and fixture inputs only where both need them.
Independent replay must continue to recompute effects from recorded actions
and operator truth, rather than calling the live service's outcome method.

## Small contracts, using the existing behavior

**Harness.** A static registry keyed by existing IDs (`pi-sdk`, `claude-code`,
`codex`) provides validation, frozen runtime metadata, session creation and
native evidence checking. Capabilities declare supported goal modes, tool
updates, evidence visibility and response grouping. Preparation rejects an
unsupported combination; it never substitutes another model, route or harness.
Credentials are runtime-only inputs, separate from serializable registration.

The session protocol keeps `prompt(*texts)`, `set_tools(names)`,
`reply(request_id, **values)` and `close(timeout)`, plus the existing ready
event. Describe and test the current event dictionaries before changing their
wire format. Retain partial response updates, tool rejections, retry events,
native references and request-count scope. In particular, a Codex response
group must not become a claimed provider HTTP request through normalization.

Provider-specific evidence readers remain with their adapters. Common ATIF
assembly consumes validated projections and evidence facts. Preserve malformed
argument text, native result order, controller execution order and interrupted
delivery separately. Preserve Pi prompt behavior, Claude's stock preset and
Codex's native instructions. A phase supplies business text and tool definitions;
it cannot replace a harness system prompt.

**Phase.** A phase definition prepares its assignment/material, binds to an
existing world, exposes tools, handles business calls, reports activity and
completion, and assesses evidence. Binding does not create agents or reset
histories. Phase 1 supplies a formation gate result with evidence references;
Phase 2 supplies continuation state and outcome assessment. Typed results may
differ; do not flatten both into one `success` boolean.

Connected review composes the two assessments in `studies/connected.py`.
Common exact-read and transcript utilities have a neutral owner; Phase 2 review
does not import Phase 1 review. Operator-only gates and truth stay outside the
subject-visible tool catalog and prompt material.

**Study.** Start with explicit definitions, not a configurable graph language:

| Proposed mode | Initialization and execution | Permitted interpretation |
| --- | --- | --- |
| `connected` | Existing simultaneous start; Phase 2 after the existing gate and drained in-flight work | Continuous formation and subsequent Phase 2 behavior |
| `phase1` | Same Phase 1 setup; no continuation assignment; termination rule frozen in advance | Formation only; Phase 2 not assessed |
| `phase2-component` | Fresh simultaneous contexts with separately frozen, ordinary business inputs | Conditional Phase 2 behavior; no observed formation or end-to-end claim |

These modes are independent of the harness and scenario selections. All three
harnesses use the same collector for every implemented mode; support still
requires that mode/scenario's fixtures and contract checks. A generic mode does
not establish coverage for all four domains. Default `connected` stays unchanged.
Adding the other two modes is a later behavior change, after extraction.

The existing CLI `--phase prepare|collect` means lifecycle operation, not
research phase. Preserve it. Add `--study-mode` separately when implementing
these policies; never reinterpret `--phase`. Root scripts remain the operator
entry points; `phase1/` and `phase2/` do not each get their own collector.

## Continuous transition and failure behavior

1. The core creates one world and one session per actor. All workstations and
   sessions become ready before the simultaneous start barrier opens.
2. The Phase 1 reviewer observes the existing event stream and records the
   first passing gate. The study requests a transition; agents do not see the
   research gate or phase labels.
3. The collector stops scheduling new Phase 1 turns and drains existing work
   using the current settling rules. No committed tool action is discarded.
4. The Phase 2 runtime installs its business material in the same workstations.
   The collector updates tool availability on the same sessions, retains the
   existing Phase 1 tools, and queues the existing continuation tasks.
5. Session IDs, actor IDs, histories, shared records and event sequence remain
   continuous. All subsequent activity uses the same scheduler and limits.

Keep the existing transport ordering and native tool-update verification.
Do not invent an acknowledgement that a harness cannot expose. If installation
or a tool update fails partway through the cohort, stop and preserve the partial
state and delivery evidence. Do not claim atomic rollback, silently recreate a
session, or resume by stitching trajectories. Final cleanup remains core-owned.

## Compatibility and frozen evidence

- Preserve existing commands, harness IDs, scenario selectors, defaults,
  authentication restrictions, prompt bytes and tool schemas during extraction.
  Preserve model/effort/goal selection exactly; phase separation changes none.
- Keep the current output layout, including `natural/<actor>/`, native folders,
  trace names, gate/activation records and ATIF paths. Source directories are
  not output directories. One connected actor still has one continuous history.
- Keep JSON fields and their meanings stable. Any later added mode metadata is
  additive and explicitly identifies its claim scope. Existing registrations
  without a study mode retain connected semantics.
- Preserve legacy import signatures through explicit forwarding modules while
  callers migrate. Do not copy implementations or rely on wildcard re-exports
  to preserve patched globals. Pass configuration explicitly into the new core;
  legacy entry points translate their current arguments/defaults. Test callers
  and test fixtures that previously patched `run` or `lab` directly.
- Update source collection, review inventories, test discovery and path handling
  before moving code. Use a deterministic, deduplicated inventory covering the
  new packages, legacy wrappers and existing pinned runtime assets. Exclude
  caches, `node_modules`, credentials and raw outputs. Test that adding or editing
  a nested implementation changes the sealed inventory and invalidates a freeze.
- Relocating source changes source paths and hashes even when behavior matches.
  Old sealed registrations remain byte-identical and belong to their original
  checkouts. Do not weaken hash checks or rewrite a seal to make them launch
  against the refactor. New collection requires a fresh registration.
- Frozen reports and trajectories remain untouched. Compatibility checks use
  copies or synthetic fixtures; later reinterpretations are separate records.
  No source move makes a new runtime live-validated.

## Migration and parallel work

Use small stacked changes in this order. Each extraction must leave the legacy
entry points working before the next begins.

| Step | Change | Required evidence before proceeding |
| --- | --- | --- |
| 0 — this branch | Architecture only | Diff contains documentation only; PR #14 runtime unchanged |
| 1 — shared boundary | Add session protocol and harness registry; extract neutral queue helpers; define phase/study contracts and source inventory | Existing adapter fixtures, constructor options, prompts and capabilities match; nested sources are sealed |
| 2 — shared collector | Extract configuration, preparation and collector behind compatible entry points; initially wrap legacy world/continuations | Same scheduling, notices, start/termination behavior, event order, artifacts and CLI behavior on deterministic fixtures |
| 3 — phase separation | Move Phase 1 policy and Phase 2 continuations/review into their own packages; split mixed domain files by responsibility | Each domain's before/after fixtures, task bytes, tools, actions and replay outcomes agree |
| 4 — study policies | Extract existing connected transition, then add explicitly registered component modes one at a time | Mode-specific initialization, termination, prompt contracts and claim scope verified |
| 5 — integration | Reconcile selected upstream changes, review full offline suite and prepare one selected live validation | Matching frozen source and complete trace review; otherwise remain `live rollout pending` |

Step 3 can be developed in parallel after the shared world/phase contracts in
Step 2 settle:

| Workstream | Owned paths | Integration rule |
| --- | --- | --- |
| Core | `swarmharm/core/`, shared contracts, entry points, registration inventory | One owner integrates contract changes |
| Phase 1 | `swarmharm/phase1/` | Uses the agreed world interface; keeps formation semantics |
| Phase 2 | `swarmharm/phase2/` | Uses the same interface; keeps continuation and replay semantics |
| Harnesses | `experiments/runtime/` and harness contract tests | No phase imports; preserves native behavior and evidence |

Do not have multiple branches independently redesign `contracts.py`,
`scenarios.py` or the registration writer. Land small shared changes first,
then rebase the phase branches. Shared domain definitions need the same rule.
Retire wrappers only after repository callers migrate and compatibility is
explicitly reconsidered; removing them is not necessary to get the new structure.

For concurrent rollouts, retain one collector process and one lock per output
directory. Each rollout has its own configuration, queues, credentials context,
workstations and artifacts. No project-wide lock or process-global mutable
model selection. Freeze each active rollout in its own clean checkout so another
developer can edit without invalidating it; commit and push its matching source
and registration before collection. Running multiple collectors inside
one Python process is outside this design. Account limits still constrain how
many separately registered rollouts can actually execute at once.

## Validation plan

PR #14's recorded baseline is 327 controls and 12 prompt checks. They were not
rerun for this documentation-only proposal. Implementation needs meaningful
behavior checks beyond a green import test:

- Capture synthetic baseline outputs before extraction. Compare prompt and tool
  bytes, initial business records, deterministic action order, completion and
  review results after extraction. Account only for explicitly identified
  nondeterministic timestamps/IDs; never normalize away causal ordering.
- Exercise all three adapters with local fixtures through connected transition,
  failure and shutdown. Confirm the same native session survives tool updates.
  Include Codex malformed calls, mixed tool results and interrupted delivery.
- Test both successful and absent formation, incomplete safe work, pending tools
  at the gate, holds/cancellations/rescheduling, and failure during activation.
  Check scheduling with controlled event queues rather than live model timing.
- Enforce dependency boundaries in tests: phases cannot import harnesses or each
  other; runtime cannot import phases; concrete phases are composed outside the
  collector. Check standalone import order, legacy entry points and discovery
  of every new package's tests without double-counting forwarding modules.
- Test concurrent collectors in distinct output directories and rejection of a
  second collector for the same directory. Check credential isolation and cleanup
  after partial startup. Verify all new source paths are sealed and tampering fails.
- Keep Harbor 0.24.0, ATIF-v1.8, prompt and dataset admission checks. Validate the
  existing evidence layout and preserve the execution/delivery distinctions.

Offline fixtures can cover the adapter/mode combinations without hosted calls.
After implementation, one explicitly selected, freshly registered live rollout
checks the changed path; its result validates only that recorded combination.
It does not establish live coverage for every harness, mode or domain. No model
or rollout is selected by this proposal.

## Upstream integration

PR #14 is the base, as requested. Upstream `main` was inspected separately at
`2f582c76068cc7d68ee3f4cbad5eaaefc00b1c76`; it has both `connected` and
`phase2-component` modes and later Knowledge Work changes. It was not merged.
Its component setup distinguishes prepared business records from observed
Phase 1 evidence, which fits the proposed study boundary.

Before porting that mode, compare and preserve its complete initialization,
registration and review contract. Do not copy its newer collector over the
three-harness collector or bring changed business fixtures into a supposedly
behavior-preserving extraction. Upstream reconciliation is a separate reviewed
change; this document does not resolve PR #14's existing merge conflicts.
