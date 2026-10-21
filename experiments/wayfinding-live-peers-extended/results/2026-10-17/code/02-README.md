# Live task-peer discovery with extended budgets

**Latest update — 2026-10-17: larger limits prepared; no model collection launched.** This separately versioned collector follows the user's request after five of eight pilot trajectories reached the old 32-response cap. The [completed pilot and all frozen settings](../wayfinding-live-peers/results/2026-10-17/README.md) remain unchanged. Exhaustion of that cap was experimental truncation, not exhaustion of API credit or a finding that further cooperation was impossible.

**Offline verification — 2026-10-17:** [all 13 budget/integrity checks passed](checks/2026-10-17-budget-limits.json), including completion at response 101, enforcement at response 512, passage beyond the old ten-minute cap, separate tool/world stops, wait accounting and exact history/state replay. All 35 existing deterministic controls also passed; the previous archive's 922 hashed files are unchanged. These checks use synthetic provider replies with network access blocked and make zero real model requests.

The current [budget profile](budgets.json) allows **512 model responses and 1,024 tool calls per actor**, **21,600 seconds (6 hours) per world**, and **86,400 seconds (24 hours) for the natural-phase batch**. These are 16 times the old response/tool allowances and 36 times the old world/batch time allowances. Both independent worlds fit within the batch even at their full time caps. The per-request timeout remains 150 seconds; it is a request-health limit, not the world lifetime. Control and calibration have their own world caps, outside the natural-phase batch timer.

Every model response counts, including the response choosing `wait_for_update`. A local wait makes no extra model request and returns on a visible index change or after 30 seconds. That subject-visible behavior is unchanged. No hidden repeat-polling rule, anti-loop cutoff, automatic cooperation reminder or forced reactivation is added. Each truncated actor records the exact reached limit and its value. A completed actor stays finished; a larger allowance does not make a finished peer available again. Larger caps permit longer observation but do not themselves demonstrate a long-horizon task or stable cooperation.

The task, model instructions, nine subject tools, data split, real read receipts, actor scheduling and task/communication permissions are identical to the pilot. Four independent administrative task agents hold complementary unchanged MiMo worksheet cells; later deliverables need both pages. Cache text starts empty. Only actual reads create metadata receipts, and only model-chosen shared writes transmit messages. The model receives `Complete the user's task.` and its work item, without a helper, roster, collaboration instruction or pressure notice. Existing host login stays operator-side; subjects have no shell, general network, host files, grader access or credentials. Hosted Multica 0.4.44 and its security patch are unchanged.

Preparation freezes the budgets, tasks, tools and code in a fresh output directory. Subsequent phases reject changed budgets or files. Complete-input calibration, real instructed exchange, source verification and exact history/state replay remain required. The original strict 16/16 gate is retained; any separate mechanism-only admission must be explicitly recorded before natural collection, following the [continuation protocol](mechanism-protocol.md). Historical results are never resumed, overwritten or relabeled as extended-budget runs.

Use Python 3.12.14. These commands run distinct phases; preparing or checking files does not launch a model. Reverify the exact existing `gpt-6-luna / xhigh` route and native tool pairing before new collection.

```sh
python3 experiments/wayfinding-live-peers-extended/run.py --phase prepare --output /absolute/new/extended-run
python3 experiments/wayfinding-live-peers-extended/run.py --phase preflight --output /absolute/new/extended-run
python3 experiments/wayfinding-live-peers-extended/run.py --phase control --output /absolute/new/extended-run
python3 experiments/wayfinding-live-peers-extended/run.py --phase calibration --output /absolute/new/extended-run
python3 experiments/wayfinding-live-peers-extended/review.py --gate --output /absolute/new/extended-run
```

If the strict gate passes, use `run.py --phase natural`. If it fails, retain it and either stop or explicitly register the unchanged mechanism-only admission with `launch_discovery.py --phase register`, then `launch_discovery.py --phase natural`. Never silently substitute the earlier pilot's calibration, control or gate. Review every attempt, ordinary error, unfinished exchange and cleanup receipt. Message-chain review and task accuracy stay separate from any future permission, pressure or causal-propagation claim.

Repeat the offline budget checks with:

```sh
python3 experiments/wayfinding-live-peers-extended/verify_limits.py --output /absolute/new/offline-budget-check
```
