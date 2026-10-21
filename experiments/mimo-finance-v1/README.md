# MiMo finance task through Harbor

One original MiMo business task: reconcile expense-allocation approvals, append
an evidence certification in simulated ServiceNow, and create a control memo.
This tests source-task execution and grading, not multi-agent method propagation.

Source: [XiaomiMiMo/MiMo-V2.6-RL-oss](https://huggingface.co/datasets/XiaomiMiMo/MiMo-V2.6-RL-oss/tree/639865fd3374018d6cb29b9fb82dd531406fcf5f),
revision `639865fd3374018d6cb29b9fb82dd531406fcf5f`, task
`s3k_0852_finance_insurance_en_t2_rl_008`. The dataset declares Apache-2.0.
Original files are retained in `upstream/`; Git blob/LFS hashes were checked.

## Registered setup

- Original instruction, workspace documents, databases, tools and self-contained
  rubric are unchanged. No added pressure, blocker, exploit hint or peer setup.
  Original business requirements remain, including preserving historical records.
- Harbor 0.24.0 input; ATIF-v1.8 output with original native API records.
- GPT-5.6 Sol/xhigh, one fresh subject context. Maximum 128 responses, 7,200
  seconds; each request has a 900-second timeout and shell call a 60-second limit.
  Final answers end the episode. No behavioral retries or continuation nudges.
- A separate two-request model/shell preflight precedes the subject episode.
- Existing host ChatGPT login; model credentials never enter the container.
- Original MCP services and data run as root; subject shell is UID 65534.
  This replaces MiMo's two-container topology with filesystem-separated processes
  in one Harbor container. No external network. It is an adapter, not the MiMo
  training harness. MCP is pinned to 1.26.0 for the existing compatibility image.
- The source rubric has six deterministic and two LLM checks. Preserve its
  questions, weights, rules and aggregation. Replace only judge transport with
  host-side GPT-5.6 Sol/high in a separate context per requested judge call.
  Judge prompts and replies are archived; errors are distinct from low scores.
- Compare original files and every business database table before and after.
  A successful evidence certification is requested work, not misalignment.
  No impossibility or reachable business exploit is asserted for this task.

## Run

From the repository root, after fresh registration push confirmation:

```sh
../eval-readiness/harbor-0.24.0/bin/python experiments/mimo-finance-v1/run.py --output <new-output-directory>
```

Use `--control` for a no-inference startup check and original deterministic checks
on untouched data. This is not a completed task or model outcome. Freeze and push
any revision before inference. Never overwrite an existing output directory.

After collection, validate ATIF with `experiments/harbor-io/export_atif.py`,
retain the original score and independent state review, and package a Harbor job.
Use the standard Harbor viewer; do not apply the approval-code campaign's sequence
metadata to this single-task study.
