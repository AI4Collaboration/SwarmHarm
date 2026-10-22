# Run and debug evaluations

**Use Harbor task inputs, ATIF-v1.8 trajectories and Harbor's viewer/tools.**
Treat input schema, execution mode and output schema as three separate claims.
All live model requests must follow the [AxonHub routing policy](axonhub-routing.md).
Read [Current setup](../README.md#current-setup) before changing model access.
The [peer-necessary procurement environment](../experiments/procurement-composition-v2/README.md)
is the next campaign version. It requires the reference contained in each quote,
removing v1's service-price shortcut, and records actual peer quote exposure and
later use. Every task also records a normal model-authored reconciliation in the
persistent project register, giving later work an authentic artifact without a
peer or method prompt. Its offline controls pass; it has no model results yet.
The [procurement reach-out pilot](../experiments/procurement-reachout-v2/RESULTS-2026-10-22.md)
used the registered campaign adapter and reproduced one spontaneous peer request
in six completed GPT-5.6 Sol contexts. It ended on a provider disconnect. The
following [source-exact LessWrong Step 2 study](../experiments/lesswrong-step2-sol-v1/RESULTS-2026-10-22.md)
retained the public Inspect task implementation and registered 64 bank and 64
none trials. It stopped after eight completions when both ordinal-5 provider
streams failed. Do not pool the incomplete subset into a rate estimate or
silently resume it. This is a fidelity test of one communication mechanism, not
a Harbor dataset or a test of business harm. The separately registered
[v2 protocol](../experiments/lesswrong-step2-sol-v2/README.md) adds bounded
transport-only retries, preserves every failed request and never reruns a
trajectory.
The latest [composable procurement run](../experiments/procurement-composition-v1/RESULTS-2026-10-22.md)
completed on DeepSeek through AxonHub. It produced two verified over-budget
commitments in six impossible tasks, but no authored method or later-agent
adoption. The condition had no added pressure.
The latest [natural procurement check](../experiments/procurement-settlement-v1/RESULTS-2026-10-22.md)
completed on Luna and DeepSeek; Sol was provider-held before its experimental
phase. The condition had no added pressure.
The latest [MiMo payment pilot](../experiments/mimo-payment-v1/RESULTS.md) completed
on Sol and DeepSeek. Its [frozen protocol](../experiments/mimo-payment-v1/README.md)
uses a deterministic authorization verifier. The earlier MiMo finance task uses
a separate source-rubric judge. Do not mix their scores.
The [MiMo finance adapter](../experiments/mimo-finance-v1/README.md) runs an
original business task with native MCP tools and the original self-contained
rubric. The [approval-code pilot](../experiments/approval-code-v1/RESULTS.md) uses
synthetic tasks. Older experiments retain their original runners and evidence.

## Environment

Verified on 21 October 2026: Harbor **0.24.0**, Python 3.12.14 and OpenAI SDK
2.54.0 in `../eval-readiness/harbor-0.24.0`; installed dependencies are pinned in
[dependencies.txt](../experiments/approval-code-v1/dependencies.txt). The
`scripts/harbor` wrapper checks the Harbor version. Set `SWARMHARM_HARBOR_ENV`
if this environment is installed elsewhere. A fresh clone does not include it.

```sh
uv venv --python 3.12 ../eval-readiness/harbor-0.24.0
uv pip install --python ../eval-readiness/harbor-0.24.0/bin/python -r experiments/approval-code-v1/dependencies.txt
./scripts/harbor --version
```

Docker 29.9.1 uses existing `lima-swarmharm`; Buildx 0.38.1 is now installed.
The pilot's base image is pinned in its registration. Subjects run as UID 65534,
with no external network; the local purchase service and ledger run as root.
The MiMo adapter uses the cached amd64 MiMo compatibility image with MCP 1.26.0.
It protects `/logs` itself as root-only: on this local Docker mount, changing
permissions on a mounted child alone did not prevent subject access. Judge
credentials remain on the host, and judge requests occur after the subject ends.
Harbor mounts its trial logging directories. Do not assume the older custom
runner's read-only-root/no-mount configuration applies to Harbor.

Every live model, including GPT-5.6 Sol/xhigh, must use the AxonHub Responses
endpoint `https://lmportal.iefbr14.xyz/v1/responses`. Provide the existing
host-only key through `AXONHUB_API_KEY` or `--key-file`; the key must never enter
a task container, registration, trajectory, or repository. Verify the exact
AxonHub model route before each new campaign. Keep hosted Multica 0.4.44
and its maintainer patch unchanged. No new AWS setup is required.

The natural procurement runner accepts `--model-id` and `--model-alias` only when
preparing a fresh registration. Collection reads the frozen model from that
registration:

```sh
python experiments/procurement-settlement-v1/run.py \
  --phase prepare --output jobs/<fresh-id> --key-file <host-only-key-file> \
  --model-id deepseek/deepseek-v4.1-flash-1017 --model-alias deepseek_v41
python experiments/procurement-settlement-v1/run.py \
  --phase collect --output jobs/<fresh-id> --key-file <host-only-key-file>
```

## Inspect and debug

From the repository root:

```sh
./scripts/harbor view jobs --jobs --host 127.0.0.1 --port 8777 --no-build
./scripts/harbor view tasks/approval-code --tasks --host 127.0.0.1 --port 8778 --no-build
./scripts/harbor trial --help
./scripts/harbor analyze --help
./scripts/harbor check --help
```

Use the viewer's Trajectory, Agent, Verifier, Config, Log and Exception tabs.
`analyze` and `check` can involve model calls; inspect their configuration before
running them. Do not upload jobs or sign into hosted services just to inspect locally.

Some single-task pilots use native Harbor Trial execution. The current
multi-agent procurement campaign instead consumes schema-validated Harbor task
packages through a registered host-side campaign adapter. Replaying it requires
that adapter because generic Harbor Job scheduling has not been shown to preserve
separate workstations, paired admission, fresh waves and persistent shared state.
Do not describe schema-valid inputs or viewer-compatible outputs as native Harbor
execution.

## Collection and export

Each revised study needs fresh outputs and a new registration. Freeze task files,
source revisions, prompts, model settings, dependencies and budgets, then confirm
the registration is pushed before inference. Do not reuse a completed registration
as permission to change inputs or silently replace trajectories.

Before preparing any current-format campaign, add a machine-readable
`format-contract.json` and executable format controls, then run:

```sh
./scripts/check-format-contract
```

With no argument, this checks every registered current-format experiment. Pass a
specific experiment path to check only that experiment. The guard executes the
experiment's format controls; it does not merely inspect the JSON declaration.
The collector must also run those controls during preparation, seal every Harbor
task-package hash, use each package's instruction as the runtime user input, and
block collection if any hash changes. ATIF validation happens after collection;
it cannot retroactively prove the input or execution format.

The [pilot runner](../experiments/approval-code-v1/README.md) uses one funded gate
and three fresh sequential contexts. Its limits are 128 responses/7,200 seconds
per context, 900 seconds per request and 30 seconds per shell call. Final answers
end a context. The registry starts empty; only actual agent files persist.
These ceilings are not observed autonomy durations.

After terminal collection, using the pinned environment's Python:

```sh
python experiments/harbor-io/export_atif.py <raw-run>
python experiments/approval-code-v1/review.py <raw-run>
python experiments/harbor-io/package_job.py <raw-run> jobs/<new-job-id>
```

The ATIF exporter supports the current Sol native traces with shell or MCP calls.
The package helper above records the approval-code campaign sequence; for MiMo,
use `experiments/mimo-finance-v1/finish.py <raw-run> jobs/<new-job-id>`.
Other runners need adapters validated against their native evidence.

For the current composable procurement campaign, use its experiment-specific
review and exporter so the independent ledger replay and paired lifecycle are
preserved:

```sh
python experiments/procurement-composition-v2/review.py --output jobs/<job-id>
python experiments/procurement-composition-v2/export_atif.py jobs/<job-id>
```

The pilot review checks the observed negative case and deliberately stops if
shared artifacts require a richer semantic review. It is not a general adoption
detector. Future conditions need corresponding independent business verifiers.

Keep native traces and original scores. ATIF conversion validates schema and
native call/result continuity; it does not infer private reasoning. Separate
business completion, adverse consequences and method propagation. Keep failures,
negative results and scripted controls distinct. Monitor direct progress/error
files about once per minute without scheduled tasks, and preserve interruptions.
After review, remove evaluation containers, release the inference lock, update the
English report and README, and keep experiment results off the public website.
