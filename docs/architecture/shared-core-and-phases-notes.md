# Implementation reference: independent experiments

Start with the [visual design](shared-core-and-phases.md).

Design proposal, corrected on 30 October 2026. Original baseline: PR #14,
`ee5114bae85023b2b4a76299f92e6f8b2ec7d864`. The documentation branch now includes
main `f6af6461b`; this PR makes no runtime changes relative to that base.

## Decision and scope

Phase 1 and Phase 2 are independent experiments using one shared execution core
and the existing Pi, Claude and Codex adapters. Phase 2 owns its initial inputs,
runtime behavior and review. Phase 1 does not have to exist or execute for
Phase 2 to prepare, collect, review or export.

This supersedes the earlier connected-default proposal. The target has no
connected study, cross-phase session handoff, formation gate in Phase 2, or
scenario pairing. Existing connected registrations and results retain their
original scope and source revision.

The user requested design first. This update changes documentation only.
Independent execution changes initialization and experiment scope; it is not
merely a file relocation with identical evaluation behavior. Preserve external
interfaces where possible and version the new registration semantics explicitly.

## Dependencies to remove

| Current coupling at PR #14 | Independent replacement |
| --- | --- |
| Collector requires `phase2.depends_on_phase1` and loads the formation reviewer | Generic collector accepts one experiment with its own startup and review |
| Collector constructs `lab.World`, starts Phase 1 work and waits for its gate | Fresh world infrastructure plus the selected experiment's own business state |
| Phase 2 is a `Continuation` activated with a `formation_event` | Phase 2 experiment initialized directly, without a formation event |
| Domain files mix both phases' fixtures and services | Phase-local `scenarios/`; split functions by responsibility |
| Phase 2 reviewers check formation events and prior workstation identities | Review the experiment's own registered population, startup and actions |
| Review/export assumes continuous histories and combines phase results | Common evidence machinery plus the selected experiment's reviewer and scope |
| Preparation and source inventories assume both phases are present | Selected experiment's complete source/input closure plus shared dependencies |

For example, Finance's `ReviewService` belongs to Phase 1; `FundingService`,
starting funding records and settlement replay belong to Phase 2. Phase 2 must
not obtain them through a mixed module that transitively imports Phase 1.

Sources at the original baseline:
[collector](https://github.com/AI4Collaboration/SwarmHarm/blob/ee5114bae/experiments/swarmharm-v1/run.py),
[world](https://github.com/AI4Collaboration/SwarmHarm/blob/ee5114bae/experiments/swarmharm-v1/lab.py),
[Finance continuation](https://github.com/AI4Collaboration/SwarmHarm/blob/ee5114bae/experiments/swarmharm-v1/domains/financial_analysis_continuation.py),
[Finance reviewer](https://github.com/AI4Collaboration/SwarmHarm/blob/ee5114bae/experiments/swarmharm-v1/domains/financial_analysis_integrated_review.py),
[exporter](https://github.com/AI4Collaboration/SwarmHarm/blob/ee5114bae/experiments/swarmharm-v1/export_atif.py).

## Ownership and interfaces

| Owner | Responsibilities |
| --- | --- |
| Experiment | Starting records, actor assignments, tasks, tools, business services, notices, completion, review and tests |
| Core | Configuration, registration, workstations, simultaneous start, scheduler, limits, tool dispatch, event recording and cleanup |
| Harness | Authentication, exact model/runtime checks, native sessions, tool transport and native evidence |
| Evidence layer | Artifact persistence, manifests and ATIF assembly from validated native evidence |

The entry point loads exactly one experiment and selects one harness. Each
experiment chooses its own scenario locally. There is no global registry pairing
Phase 1 and Phase 2 scenarios.

The common experiment protocol covers five responsibilities:

1. Prepare immutable initial inputs and scenario registration fields.
2. Create business services over a fresh core world instance.
3. Provide actor tasks, workspace documents and initial tool availability.
4. Handle tools, business-state changes, notifications and completion.
5. Review recorded evidence and independently check effects.

Preparation requires no model inference. Install tools and starting records
before releasing the simultaneous start barrier. The protocol has no
`activate(formation_event)` operation.

World infrastructure owns workspace access, shared-record storage and ordered
event commits. Visibility and notification policy belong to the experiment.
Each rollout has its own world instance; records may be shared among its agents,
but no state or session is implicitly shared between experiments.

The core depends on the protocol, not concrete phase modules. Phase packages
cannot import each other or provider SDKs. Extract neutral parsing/recording
utilities only when needed. Do not recreate a shared business `domains/` layer
that hides a dependency on another experiment.

## Phase 2 initial state and review

Each Phase 2 scenario defines all starting business records it needs, such as
funding facilities, allocations, capacity, customer orders or source documents.
These fixtures have their own provenance, hashes and registered visibility.
Do not generate them by executing Phase 1 services, synthesizing its gate or
replaying a previous model trajectory.

Starting state must preserve the intended business problem. Keep safe incomplete
behavior and verify the ordinary completion scope and specific synthetic defect.
Do not remove business records or feed agents a solution to eliminate a startup
dependency. Changed initial state needs fresh prompt, mechanics and live validation.

Phase 2 review checks its own registered population, observed actions,
communication where relevant, and independently recomputed business effects.
There is no formation-pass prerequisite. A standalone Phase 2 result does not
establish prior autonomous formation. Preserve deliberate action, causality,
execution and delivery distinctions. Replay uses recorded actions and operator
truth, including corrections, holds, cancellations and rescheduling, rather than
the live service's outcome method.

## Shared harness behavior

Keep existing adapters and pinned Node bundles in their current locations.
A static registry keyed by `pi-sdk`, `claude-code` and `codex` selects the
implementation. Extract neutral queue helpers instead of importing them from
Pi into Codex. No new agent loop or language rewrite is needed.

Retain `prompt`, `set_tools`, `reply`, `close` and ready-event behavior. Phase 2
starts with its registered tools available; it needs no cross-phase tool update.
Validate model, effort and goal support without substitution. Credentials remain
runtime-only and outside serialized artifacts.

Preserve Pi prompt behavior, Claude's stock preset and Codex's native instructions.
Neither experiment replaces system instructions. Keep partial responses, retries,
rejected calls, native references and request-count scope. Codex response groups
do not establish visibility into provider HTTP requests.

Evidence readers remain harness-specific. Common export retains malformed
arguments, native result order, controller execution order and interrupted
delivery separately. Startup failures preserve evidence and clean up only that
rollout's resources; no silent session replacement.

## Compatibility without a connected architecture

- Keep script locations and applicable harness/scenario IDs. Proposed selection
  is `--experiment phase1|phase2`; retain `--phase prepare|collect` for lifecycle.
  These new options are not implemented. New preparation explicitly selects an
  experiment; collection reads the choice from its sealed registration.
- Independent registrations need a schema revision and experiment identity.
  Never reinterpret an old connected registration as Phase 2-only. Historical
  collection uses its original checkout; unsupported schemas fail clearly.
- During migration, keep old entry points working until replacements are
  verified. Forwarding wrappers must not copy loops or eagerly import the other
  experiment. The final core has no connected coordinator.
- Preserve trace, tool-record and ATIF formats where their meanings apply.
  Each actor has one history within its rollout. New reports must not claim
  continuity from Phase 1 or fill in a fake passing gate.
- Frozen registrations, trajectories and scores remain byte-identical. New
  source or initialization requires new hashes and registration. Historical
  reports keep their original scope; later analyses are separate records.

## Source sealing and isolation tests

Replace fixed-depth paths and incomplete globs before moving files. Freeze the
selected experiment's sources, fixtures and tests plus the core, selected harness
and all actual dependencies. Include nested packages and pinned assets. A global
manifest must not make Phase 1 necessary just to prepare Phase 2. Check that new
or changed nested dependencies invalidate an old freeze. Exclude credentials,
raw output, caches and installed dependencies.

Use qualified imports and explicit path objects. Remove internal
`sys.path`/`sys.modules` manipulation incrementally. Test import order, legacy
signatures, configuration forwarding and fixtures that patched module globals.
Discover each experiment's checks independently, reusing shared adapter checks.

**Acceptance test:** with Phase 1 unavailable, Phase 2 preparation, local fixture
collection, review and export succeed without importing its code, reading its
artifacts or checking its result. Repeat symmetrically for Phase 1. This covers
transitive dependencies as well as direct imports.

## Implementation and parallel work

| Step | Deliverable | Required check |
| --- | --- | --- |
| 1 | Common experiment/session contracts, paths and source inventory | No assumption that both experiments exist |
| 2 | Neutral world infrastructure and collector extraction | Existing deterministic fixture prompts, actions and evidence agree |
| 3 | First independent Phase 2 scenario, startup and review | Full offline lifecycle works with Phase 1 unavailable |
| 4 | Independent Phase 1 package | Symmetric isolation check; formation semantics preserved |
| 5 | Remaining scenario migrations, individually | Own initial-state, prompt, mechanics and replay checks |
| 6 | Fresh selected live validation | Matching registration and complete trace review |

After contracts settle, Phase 1, Phase 2 and harness work proceed on separate
branches. Phase 2 does not wait for Step 4 to become usable. One owner integrates
shared interface changes before dependent branches rebase.

Concurrent rollouts use separate processes, clean frozen checkouts, sessions,
workstations, credentials contexts, outputs and per-output locks. Commit and push
matching registrations before collection. No project-wide lock or process-global
mutable model selection; account/provider limits still apply.

PR #14's recorded baseline is 327 controls and 12 prompt checks, not rerun for
this documentation update. Implementation adds phase-isolation, fresh-start,
all-three-harness fixture, collector isolation, cleanup and source-tamper checks.
Retain replay lifecycle checks, Harbor 0.24.0, ATIF-v1.8, prompt and dataset
admission validation. Update scope contracts explicitly for independence instead
of disabling those checks.

Offline checks do not establish live coverage. Each changed scenario remains
`live rollout pending` until matching selected live evidence is reviewed. This
proposal selects no model, new rollout or broad collection matrix.

## Upstream and project rules

The latest user clarification supersedes the continuous-only architecture
direction for this design. Natural-task, evidence, credential and independent
effect requirements still apply. Update registration, protocol and admission
schemas together during implementation; none may hide a Phase 1 prerequisite.

PR #14 has merged. Main `f6af6461b` now contains `phase1/`, `phase2/`, shared
`scenarios/` and standalone modes using the registered harness pipeline. The
documentation branch includes that revision, with no runtime difference from it.
The dependency inventory above describes the original PR #14 baseline and must
be re-audited against current main before implementation; some steps may already
be complete. Existing standalone support does not prove the stronger acceptance
test that preparation, collection, review and export work with Phase 1 unavailable.

Build on the existing separation. Map its files to these responsibilities before
adding packages or moving them again. Preserve current fixtures, harnesses,
registrations and active rollout evidence; do not replace upstream implementation
with the old collector. Connected support currently remains in main; its removal
or deprecation is a later implementation decision, not part of this design PR.
