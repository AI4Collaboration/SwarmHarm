# Experiments

**Latest diagnostic:** [LessWrong four-step procurement analogue](lesswrong-business-four-step-v1/RESULTS-2026-10-22-DEEPSEEK-DEV.md).
The DeepSeek development run was intentionally stopped after nine completed
Step 1 trials. Six wrote an optional extra registry record and three included a
specific request, but most writes were ordinary status duplication. Steps 2–4
did not run. This is component evidence, not a dataset score or connected-chain
result. Future development follows the [short iteration plan](../docs/dataset-development-plan.md).

**Latest environment:** [peer-necessary composable procurement](procurement-composition-v2/README.md).
The order service now requires a non-leaking 128-bit reference from each
supplier quote, so an unavailable quote can no longer be bypassed by asking the
service to price the order. Paired workers have complementary quotes and alternate while active;
each task also creates an ordinary model-authored reconciliation record. The
registry starts empty and contains only real work artifacts. Offline controls
verify the ordered request-to-use transfer, exact provenance for partial reads,
both process repairs, independent replay, runtime cleanup, host-only AxonHub key
forwarding, validated Harbor runtime selection and Harbor/ATIF format handling.
The first live attempt passed preflight but stopped after five delivered model
responses during the two-task normal gate when AxonHub closed the next stream
without a terminal response. It never reached an experimental task and is not a
behavioral result. The next frozen protocol adds bounded, evidence-preserving
transport-only retries; it never reruns a completed response or tool action.

**Latest:** the [source-exact LessWrong Step 2 run](lesswrong-step2-sol-v1/RESULTS-2026-10-22.md)
completed 8/128 GPT-5.6 Sol trials before both ordinal-5 AxonHub streams ended.
The four bank and four none trials contained zero peer requests and no recorded
refusals. The incomplete subset cannot support a rate or condition comparison.
The [v2 protocol](lesswrong-step2-sol-v2/README.md) keeps the study settings
fixed and adds evidence-preserving transport retries aligned with the public
launcher's retry tolerance.

**Latest completed behavioral result:** [natural procurement reach-out](procurement-reachout-v2/RESULTS-2026-10-22.md)
reproduced LessWrong's narrow Step 2 behavior on GPT-5.6 Sol. One of six
completed agents independently wrote RA-3 a concrete request for the missing
quote; five did not. No reply, order or financial effect followed. A provider
disconnect stopped the seventh context and the eighth never started.

**Latest completed result:** [composable procurement](procurement-composition-v1/RESULTS-2026-10-22.md).
DeepSeek created two independently verified over-budget commitments in six
impossible tasks. No reusable method or later-agent adoption was observed.

**Earlier:** [MiMo payment results](mimo-payment-v1/RESULTS.md). Sol and DeepSeek
completed one source-derived task each. No incorrect payment was authorized.
DeepSeek's positive attempts were blocked; it eventually authorized zero.
The harmful-use link remains missing; peer propagation was not tested.

Also: [Original MiMo finance](mimo-finance-v1/RESULTS.md), source rubric
0.7/1 with no harmful action; [Harbor approval-code](approval-code-v1/RESULTS.md),
no foreign-code use or method adoption.

## Previous study

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
