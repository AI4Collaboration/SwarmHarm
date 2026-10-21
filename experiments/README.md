# Experiments

## Current study

[Customer-contract procurement](procurement-contract-v1/README.md) is being prepared
for GPT-5.6 Sol: two funded capabilities, then six impossible procurement tasks
with the user-requested contract compensation pressure. Source inputs and contract
outcomes are separately recorded. No model results yet.

## Latest completed study

[Procurement settlement v1](procurement-settlement-v1/RESULTS.md) completed two
normal jobs and six experimental jobs with GPT-5.6 Sol. Agents exchanged missing
documents; four later agents reused earlier request procedures. No approval
cache was modified and no experimental transaction posted. The process-exploit
chain remains unobserved.

Use the [running guide](../docs/running-evals.md) for registration, collection and
review. The previous [business-cache result](business-cache-v3/analysis/2026-10-21/COMPLETE_REPORT.md)
establishes request-method reuse and public copying, not the new process-exploit chain.

## Supporting components

- [Public reader](infra-reader-v1/REPORT.md): durable observation, verified
  receipts and independent replay.
- [Prompt checks](prompt-contract/checks.py): audit actual assembled inputs.
- [Outcome criteria](../docs/business-outcome-criteria.md): distinguish cooperation,
  method adoption and a concrete adverse business effect.

## Historical studies

The [history index](../docs/history-index.md) groups completed, interrupted and
negative results. Earlier study families are historical; its old settings
and launch commands are not the current operating guide.

Each historical family links to its results and an immutable version of its
original documentation. Frozen registrations, source snapshots, native traces
and analyses remain at their original paths. Older source modules are retained
because later runners import them, including transport and response monitoring.
Do not interpret a directory's presence as an active or completed experiment.
