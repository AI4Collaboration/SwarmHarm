# Run evaluations

Start with the [completed software-delivery study](../experiments/impossible-release-v1/RESULTS.md).
Luna published incorrect functions in two tasks; Sol published none of the four
experimental tasks. Both passed normal capabilities. Collection and review are
complete; no run or scheduled monitor is active.

The [root README](../README.md#current-setup) is the current setup reference.
The commands below apply to `impossible-release-v1`; historical families have
different interfaces. Its [protocol](../experiments/impossible-release-v1/README.md)
records the design before calls, while `RESULTS.md` records the completed study.

## Inspect the existing evidence

- [English report](../experiments/impossible-release-v1/RESULTS.md).
- [Luna review](../experiments/impossible-release-v1/results/2026-10-20-luna/independent-review.json)
  and [Sol review](../experiments/impossible-release-v1/results/2026-10-20-sol/independent-review.json).
- [Actual wrong release](../experiments/impossible-release-v1/results/2026-10-20-luna/tasks/natural/job-c637f17776bb59d7/delivery.json),
  including submitted code and caller results.
- Local raw outputs: `../eval-readiness/impossible-release-{sol,luna}-2026-10-20-r2`.
  Do not collect or run the write-once reviewer over these completed directories.

## Prepare a new study

Run from the repository root with the existing interpreter. Replace `<new-run>`
with a fresh name. Both output directories must be absent.

```sh
SWH_PY=../eval-readiness/lesswrong-direct-2026-10-19/source/.venv/bin/python
SWH_SOL_OUTPUT="../eval-readiness/impossible-release-sol-<new-run>"
SWH_LUNA_OUTPUT="../eval-readiness/impossible-release-luna-<new-run>"

"$SWH_PY" experiments/impossible-release-v1/run.py --phase prepare --provider sol --output "$SWH_SOL_OUTPUT"
"$SWH_PY" experiments/impossible-release-v1/run.py --phase prepare --provider luna --output "$SWH_LUNA_OUTPUT" --match "$SWH_SOL_OUTPUT"
```

Preparation checks the fixtures, byte-matches full initial inputs across models
and seals the code, settings and budgets. It makes no model calls. Save both
sealed registration bundles under new entries in this family's `registrations/`
directory and push them before collection. A changed design requires a new
registration; never alter a started run or replace failed trajectories.

The existing Docker engine and pinned cached image must be available. This
family needs the existing host login, not AWS or an AxonHub key. Keep hosted
Multica 0.4.44 and the maintainer's server-access patch unchanged.

## Collect and review

After registration is pushed, collect sequentially:

```sh
"$SWH_PY" experiments/impossible-release-v1/run.py --phase collect --provider sol --output "$SWH_SOL_OUTPUT"
"$SWH_PY" experiments/impossible-release-v1/run.py --phase collect --provider luna --output "$SWH_LUNA_OUTPUT"
```

Each collector performs native preflight and two normal capability tasks before
four experimental tasks. Watch `progress.json`, `completion.json`,
`response-review.json` and native `trace/` records. Provider errors and native
refusal stop the collector; report them promptly and preserve the run. An
ordinary explanation that a task cannot be completed is not automatically a
safety refusal. Check Sol's terminal state before starting Luna.

For each newly completed run, review once and export to a new destination:

```sh
SWH_SOL_EXPORT="../eval-readiness/impossible-release-sol-<new-run>-review"
SWH_LUNA_EXPORT="../eval-readiness/impossible-release-luna-<new-run>-review"

"$SWH_PY" experiments/impossible-release-v1/review.py --output "$SWH_SOL_OUTPUT" --destination "$SWH_SOL_EXPORT"
"$SWH_PY" experiments/impossible-release-v1/review.py --output "$SWH_LUNA_OUTPUT" --destination "$SWH_LUNA_EXPORT"
```

The reviewer makes no model calls. It checks sealed inputs, native histories,
tool results and caller values, then re-executes published artifacts in fresh
isolated containers. Read the actual submitted code and final answers before
describing intent. A corrected test and correct function are successful repair;
test passage alone is not evidence of harm. Preserve corrections, withdrawals
and both ever-occurring and outstanding wrong delivery. Confirm owned-container
cleanup after review.

## Offline checks

```sh
"$SWH_PY" experiments/impossible-release-v1/checks.py
"$SWH_PY" experiments/impossible-release-v1/collector_checks.py
"$SWH_PY" experiments/prompt-contract/checks.py
```

These make no model calls. The first two execute scripted programs in the
existing isolated Docker environment. Run prompt checks when changing assembled
subject inputs or inherited services. Frozen historical runs remain unchanged.

[Experiment guide](../experiments/README.md) · [History](history-index.md) ·
[Previous running guide](https://github.com/AI4Collaboration/SwarmHarm/blob/f3b5c87885ad08a597bbfb30d152b4a10d7b022c/docs/running-evals.md)
