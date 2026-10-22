# Harbor tasks

New SwarmHarm dataset tasks use Harbor format. Adopted on 21 October 2026.
The [MiMo finance task](../experiments/mimo-finance-v1/README.md) imports one
original financial-controls task, with source object hashes and adaptations
recorded. The [approval-code pilot](../experiments/approval-code-v1/README.md) now contains
four Harbor 0.24.0 tasks; scripted controls and all four model trials completed.
ATIF exports and Harbor viewer inspection passed. These are
synthetic tasks, not MiMo imports. Historical experiments retain their original
runners and frozen inputs.

Three claims must always remain separate:

1. **Harbor input:** every agent context has a schema-valid task package, and its
   `instruction.md` is the exact runtime user instruction.
2. **Execution:** record whether Harbor ran the trial natively or a registered
   campaign adapter consumed the task. A Harbor package alone does not prove
   native scheduling.
3. **ATIF output:** validate each exported trajectory and its continuity against
   native request, response and tool records. ATIF alone proves neither input nor
   execution format.

Current-format experiments must state these fields in `format-contract.json`,
run `scripts/check-format-contract`, execute their format controls during prepare,
and seal the hashes of every task package before inference.

## Task package

```text
tasks/<task-id>/
  instruction.md
  task.toml
  environment/
    Dockerfile
  tests/
    test.sh
  solution/
    solve.sh
  provenance.json
```

- `instruction.md`: the natural business request, without cooperation hints,
  shortcut hints, evaluator instructions or added behavioral warnings.
- `task.toml`: Harbor configuration, resources and timeouts. Pin the Harbor
  version before validation and use its supported schema.
- `environment/`: business tools and records. Keep credentials, reference
  solutions and independent grading truth out of the agent environment.
- `tests/test.sh`: verify the outcome and write `/logs/verifier/reward.txt`
  or numeric metrics in `/logs/verifier/reward.json`. Store detailed evidence
  separately. Service success responses do not prove business correctness.
- `solution/solve.sh`: optional reference solution for a feasible task. For an
  impossible variant, document infeasibility and keep scripted shortcut checks
  separate; a shortcut is not the legitimate reference solution.
- `provenance.json`: SwarmHarm metadata, not a Harbor configuration field.
  Record source URL, revision, task ID, license, file hashes and adaptations.
  Keep this operator metadata outside the agent workspace.

## Output contract

- One **ATIF-v1.8** `agent/trajectory.json` per agent/trial, validated with Harbor
  **0.24.0**'s `Trajectory` model. Preserve message order, tool arguments,
  call/result IDs and actual observations. Preserve native roles in metadata
  where ATIF has no direct role equivalent; do not fabricate reasoning.
- Native requests, responses and tool events stay alongside ATIF as audit sources.
  Exports record their hashes and check request/history continuity. Preserve
  failed or incomplete calls without fabricating a tool result.
- Harbor `result.json` and verifier `reward.json` record scores. Detailed business
  evidence and independently checked consequences remain separate artifacts.
- The campaign manifest links each independent trial to shared-artifact authors,
  versions, exposure and adoption evidence. Do not mislabel peers as delegated
  subagents or combine their separate contexts into one conversation.

For the current pilot, `experiments/harbor-io/export_atif.py <run-directory>`
performs post-collection export and validation. The frozen collector is unchanged.
Historical experiments are not retroactively claimed to have ATIF outputs.

## Sources and campaign evidence

Prioritize MiMo's non-cyber business tasks and preserve original records and
tools where possible. Record changed blockers, process weaknesses and contract
terms explicitly. HVE and Hackbait inform verifiable mechanisms; adopting their
ideas does not make a task part of their released datasets.

Keep multi-agent scheduling, persistent shared state, model settings and budgets
in a separately frozen campaign manifest. Harbor packaging alone does not
establish cross-trial communication. The campaign adapter must preserve real
peer-authored artifacts across the intended jobs without seeding methods.

Report business completion, adverse consequences and method propagation
separately. Verify discovery, authored method content, actual receipt and use
on a different task from traces and independent records. Reading shared data
alone is not harmful method adoption.

## Before inference

Validate the package against the pinned Harbor schema, build the environment
and exercise the actual verifier. Check a feasible reference outcome where
applicable and confirm that incorrect business outcomes fail independently of
the agent's answer. Preserve source scores separately from SwarmHarm measures.
Verify evaluator isolation in the selected runtime; directory layout alone
does not enforce it.

Verify the exact model route, peer persistence and evidence collection in the
campaign adapter. Freeze and push the configuration before inference. Do not
claim a migrated task or compatible campaign until these checks pass.

Official references: [task format](https://github.com/harbor-framework/docs/blob/main/guides/creating-tasks.mdx)
and [configuration schema](https://github.com/harbor-framework/harbor/blob/main/src/harbor/models/task/config.py).
