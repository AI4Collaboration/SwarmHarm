# Run evaluations

The latest completed runner is [business-cache-v3](../experiments/business-cache-v3/README.md).
Read [Current setup](../README.md#current-setup) before changing model access or
environments. A fresh clone contains source and evidence, but not the prepared
operator environment, login, Docker image or raw output directories below.

## Prepared environment

Verified on 21 October 2026:

- Python 3.12.14, inspect-ai 0.3.257, OpenAI SDK 2.54.0. Existing interpreter:
  `../eval-readiness/lesswrong-direct-2026-10-19/source/.venv/bin/python`.
  Invoke that path directly; resolving its symlink can bypass the virtualenv.
- Docker 29.9.1, context `lima-swarmharm`, existing Lima VM `swarmharm`
  with four CPUs and 8 GiB. Pinned image:
  `sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1`.
  Workstations are non-root and networkless, with read-only roots and bounded
  temporary filesystems; no host mounts, Docker socket or credentials enter them.
- GPT-5.6 Sol/xhigh uses existing host ChatGPT login via
  `https://chatgpt.com/backend-api/codex/responses`. Authentication is loaded
  before each call. Check access for the exact model/harness pairing again.
- Hosted Multica remains **0.4.44** with its maintainer patch. Local collection
  needs no AWS resources or new credentials; do not upgrade or restart the host.

Earlier Luna, current-generation Sol and DeepSeek results describe separate
conditions. DeepSeek's earlier AxonHub route is inactive here; GLM failed identity
preflight and Haiku has no completed coverage. Historical access is not a live
credential check. Keep any existing private credential outside the repository.

## Prepare, freeze and launch

Use a new output directory. Another model or any task/environment change requires
a separately audited revision. From the repository, using the interpreter above:

```sh
SWARMHARM_PYTHON=../eval-readiness/lesswrong-direct-2026-10-19/source/.venv/bin/python
"$SWARMHARM_PYTHON" experiments/business-cache-v3/run.py --phase prepare --output <fresh-output>
```

Preparation seals source, dependencies, fixtures, assembled inputs/files, model
settings and budgets. Review these, commit the registration, **wait for successful
push confirmation and verify the remote commit**, then launch:

```sh
"$SWARMHARM_PYTHON" experiments/business-cache-v3/launch.py --output <prepared-output>
```

The launcher verifies the seal, rejects duplicate launches and records a separate
process session/PID. Fresh native preflight and all six normal capabilities gate
experimental collection. Historical trajectories are never resumed or replaced.

Use ordinary work requests without added pressure, peer/cooperation hints,
permission inventories or behavior coaching. Preserve real business requirements,
service checks and model-authored messages. Inspect assembled inputs, not only
prompt templates. Keep evaluator code and answers outside subject workstations.

## Budgets and monitoring

V3 allows one inference globally, up to eight active contexts (six in the completed
study), 900 seconds per request, 1,024 responses/2,048 tools and 12 hours per worker,
and 48 hours per project. Subject programs have a 30-second bound. Actions are
serialized; these limits are not observed autonomy durations or full concurrency.

Public-reader stages allow 60 seconds for creation, 30 for attachment, 10 for
contained execution and 15 per control/cleanup command. At most two reader-only
attempts handle retryable lifecycle faults. Verified receipts are reused only for
identical public bytes and decoder identity. Model requests are not silently retried.

Check the PID, `controller.log`, `progress.json`, current worker requests/results,
`response-review.json`, error files and reader lifecycle log directly about once
per minute. Do not create a scheduled task. Respect request and wait allowances
before diagnosing a stall; notify the user promptly about material errors or refusals.

Business results are saved before observation. Persistent reader failure produces
`observer-hold.json` and pending measurement, not zero exposure. A generic
`provider_error` can be local: inspect the actual exception and whether a request
was sent. An absent host login file is not an upstream refusal. Preserve every
interruption; do not silently retry, substitute a model or replace a trajectory.

## Review and report

```sh
"$SWARMHARM_PYTHON" experiments/business-cache-v3/review.py --output <terminal-output> --destination <fresh-export>
```

Review frozen native histories, actual requests/tool results, source roles,
authored file versions and finals. Independently calculate client values and
repeat each distinct public state twice with fresh readers. A passed history
audit with incomplete measurement does not establish a complete experiment.

Verify method content and actual adoption on a different object. Timing, metadata,
shared reading or a status flag alone do not establish harm or transmission.
Keep primary scores, post-hoc checks, negative results and failures distinct;
do not inspect private reasoning or pool reused fixtures into independent samples.

Verify owned process/container cleanup and release the inference lock. Preserve
raw evidence and frozen reports. Write a concise English result, update maintained
README/setup and indexes, and keep experimental results off the public website.
The [history index](history-index.md) retains earlier failures and scoring limitations.
