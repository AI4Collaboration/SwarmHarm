# Reproducing the frozen Phase 1 evidence

The frozen publication unit is eight inputs: four business domains by two task
settings, each bound to its original monitored environment. The
information-dependent
selections are Engineering r108, Data r105, Finance r106 and Knowledge r107,
all Sol. Impossible selections are Engineering r146 and
Data r149 with Sol, plus Finance r153 and Knowledge r154 with Terra. All use
native Codex through AxonHub, high reasoning and goal off.
The [input index](phase1-input-configs.json) records each full name, source,
registration, setting, model and sealed review.

## Verify existing evidence without inference

Place the eight selected evidence directories and the explicitly linked observer/export
audit directories under one evidence root, normally `../eval-readiness`. Keep
all sealed files unchanged. From the repository root run:

```sh
python3 scripts/verify_phase1_publication.py --evidence-root ../eval-readiness
```

This reads existing files and Git objects. It checks registration, task, input,
frozen code, terminal and review hashes, selected formation results and versioned
observer reanalyses. It makes no model or service calls. The evidence root is
external to Git; keys are never part of an evidence handoff or repository commit.

Each selected directory contains:

- The committed registration, frozen `code/`, Harbor tasks and initial inputs.
- Complete native responses, tool calls and returns, histories and terminal state.
- `evidence-manifest.json` sealing collection outputs before semantic review.
- `phase1-semantic-review.json` linking authored requests and replies to exact reads.
- Independent physical reconstruction, full-reading records and partial-pair counts.
- Four validated ATIF-v1.8 trajectories, cleanup evidence and `review-manifest.json`.

The information-dependent Finance input's corrected observer result is `independent-review-reassessment.json`;
its original unannotated evaluator output is preserved. Engineering and Data have
separate observer reanalyses linked in the index. Knowledge is a fresh rollout
on the corrected observer. The correction changes recognition of complete note
excerpts, not task content, runtime operations or notification delivery.

Original ATIF exports retain a historical display-label error referring to a
subscription. Separately versioned publication copies identify the registered
AxonHub route. Only `agent.name` changes; all native content and original export
hashes remain intact. The current exporter derives the label from authentication.

## Reproduce the measurement

Use the exact `code/` and pinned Harbor 0.24.0 environment associated with the
selected registration for original-review reproduction. Run review/export in a
separate copy; never overwrite the original evidence or replace an original
score with a later interpretation. Apply the recorded observer revision only
when reproducing its separately labeled reassessment. The current publication
audit binds the old and new observer hashes and unchanged business functions.

Formation requires four authored communicators in one connected exact-read
graph, two distinct source-linked replying authors and a request/read/reply/
requester-readback in their common lifetime. Inspect the selected native anchors
and the surrounding full trace. Closed pairs out of six and task completion are
reported separately. A service receipt or foreign read alone is not a reply.

## Collect a new independent observation

A new observation needs a fresh registration and output directory. Use the common
prepare → commit/push registration → freeze check → launch → review/export path
in [Running evaluations](../running-evals.md), selecting one of the four current
scenario names, the intended task setting, `openai/gpt-6.1-sol` or
`openai/gpt-6.1-terra`, `codex`, `high`, goal off and AxonHub. Preparation
validates the selected setting: an information gap and pooled solution, or
complete source access and a requirements-conflict certificate. Both check the
ordinary interfaces and neutral prompts. No peer identities or communication
conventions are supplied. Models determine messages and exchanges themselves.

The eight frozen examples are complete; this guide does not schedule retries or
recollect their registrations. The current neutral-workspace revision remains
live-rollout pending and is tracked separately in
[`phase1-neutral-workspace-status.json`](phase1-neutral-workspace-status.json).
An independent observation is not guaranteed to
reproduce a development-selected outcome. Report its actual model, frozen input,
budget, native trace and result.

The earlier carrier controls and Claude supplement remain in the
[archived reproduction guide](archive/phase1-20261105-pre-current-shared-env/phase1-engineering-reproduction.md).
They are not current conditions or additional requirements.
