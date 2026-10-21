# Experiments

## Current entry point

[Business cache v3](business-cache-v3/README.md) is the latest completed runner.
Its [21 October report](business-cache-v3/analysis/2026-10-21/COMPLETE_REPORT.md)
verifies six correct experimental reports, 30 publicly copied synthetic records,
and cross-workflow request-method reuse. It does not establish the planned
business-process exploit chain.

Use the [running guide](../docs/running-evals.md) for a new registration, model
checks, collection and review. The next finance/procurement study is not yet built.

## Supporting components

- [Public reader](infra-reader-v1/REPORT.md): durable observation, verified
  receipts and independent replay.
- [Prompt checks](prompt-contract/checks.py): audit actual assembled inputs.
- [Outcome criteria](../docs/business-outcome-criteria.md): distinguish cooperation,
  method adoption and a concrete adverse business effect.

## Historical studies

The [history index](../docs/history-index.md) groups completed, interrupted and
negative results. Every other study family here is historical; its old settings
and launch commands are not the current operating guide.

Each historical family links to its results and an immutable version of its
original documentation. Frozen registrations, source snapshots, native traces
and analyses remain at their original paths. Older source modules are retained
because later runners import them, including transport and response monitoring.
Do not interpret a directory's presence as an active or completed experiment.
