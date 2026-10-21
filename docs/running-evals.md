# Run and debug evaluations

**Use Harbor task inputs, ATIF-v1.8 trajectories and Harbor's viewer/tools.**
Read [Current setup](../README.md#current-setup) before changing model access.
The [approval-code pilot](../experiments/approval-code-v1/RESULTS.md) is the first
completed Harbor run. Older experiments retain their original runners and evidence.

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
Harbor mounts its trial logging directories. Do not assume the older custom
runner's read-only-root/no-mount configuration applies to Harbor.

GPT-5.6 Sol/xhigh uses existing host ChatGPT login at
`https://chatgpt.com/backend-api/codex/responses`. Credentials stay on the host.
Verify the exact model route before each new campaign. Keep hosted Multica 0.4.44
and its maintainer patch unchanged. No new AWS setup is required.

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

The current campaign uses actual Harbor Trial execution with a custom host-side
agent adapter. Its viewer job summary/config are derived from those trial records.
Replaying the multi-agent study requires its registered campaign runner, not the
viewer's generic single-task rerun suggestion. Do not claim compatibility with
native Harbor Job scheduling until shared-state lifecycle and order are verified.

## Collection and export

Each revised study needs fresh outputs and a new registration. Freeze task files,
source revisions, prompts, model settings, dependencies and budgets, then confirm
the registration is pushed before inference. Do not reuse a completed registration
as permission to change inputs or silently replace trajectories.

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

These conversion/package helpers currently support the approval-code pilot's
Sol trace format and registered campaign sequence; they are not universal importers.
Other runners need adapters validated against their native evidence.

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
