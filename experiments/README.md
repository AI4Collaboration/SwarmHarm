# Experiments

## Latest completed study

[Customer-contract procurement](procurement-contract-v1/RESULTS.md): two funded
capabilities passed; six experimental agents made over-budget purchases totaling
$1,390 in excess commitments. No method files or peer-method adoption. The report
separates control failure from deliberate discovery and pressure causation.

The previous [settlement study](procurement-settlement-v1/RESULTS.md) found data
exchange and request-procedure reuse, with no approval-cache changes or overruns.
These different mechanisms must not be treated as a matched pressure comparison.
Use the [running guide](../docs/running-evals.md) for future registered studies.

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
