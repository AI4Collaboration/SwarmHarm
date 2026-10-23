# Run and debug evaluations

Use Harbor task inputs, native model records, validated ATIF-v1.8 trajectories
and separate independent review. Input schema, execution mode and output schema
are distinct claims.

## Runtime

Verified **23 October 2026**:

- Harbor 0.24.0 and Python 3.12.14 in
  `../eval-readiness/harbor-0.24.0`;
- Docker 29.9.1 with the existing `lima-swarmharm` context;
- AxonHub Responses endpoint `https://lmportal.iefbr14.xyz/v1/responses`;
- current explicit DeepSeek Flash snapshot
  `deepseek/deepseek-v4.1-flash-1017`.

Use the existing host-only AxonHub key through `AXONHUB_API_KEY` or
`--key-file`. Never place it in a task, registration, trajectory or repository.
Keep the hosted patched Multica 0.4.44 deployment unchanged. No AWS resource is
needed for the current local study.

## Validate the active environment

From the repository root:

```sh
../eval-readiness/harbor-0.24.0/bin/python -m unittest discover \
  -s experiments/procurement-shared-memory-v1 -p '*checks.py' -v
../eval-readiness/harbor-0.24.0/bin/python experiments/prompt-contract/checks.py
./scripts/check-format-contract experiments/procurement-shared-memory-v1
```

These checks make no model calls. They cover business truth, memory limits,
fresh-context ordering, verifier rejection cases, prompt naturalness, collector
controls, Harbor schema 1.4 and the ATIF-v1.8 contract.

## Freeze a fresh iteration

Every changed environment needs a new output and registration. Preparation
rechecks the OpenRouter and authenticated AxonHub catalogs, writes the exact
three Harbor task packages, captures assembled inputs, runs controls and seals
all hashes.

```sh
PY=../eval-readiness/harbor-0.24.0/bin/python
OUT=../eval-readiness/procurement-shared-memory-v1-<fresh-run-id>
REG=experiments/procurement-shared-memory-v1/registrations/<fresh-run-id>

$PY experiments/procurement-shared-memory-v1/run.py \
  --phase prepare --output "$OUT" --registration-dir "$REG" \
  --key-file <host-only-key-file> \
  --model-id deepseek/deepseek-v4.1-flash-1017 --model-alias deepseek
```

Review the assembled input, commit the environment and registration, and push
the exact commit before inference. Collection refuses to start unless local
`HEAD` equals remote `main` and every frozen hash still matches.

## Run one connected campaign

```sh
$PY experiments/procurement-shared-memory-v1/launch.py \
  --output "$OUT" --registration-dir "$REG" \
  --key-file <host-only-key-file>
```

The launcher starts one independent collector, not a scheduled task. Do not
launch a second collector for the same registration. Monitor `progress.json`,
`controller.log`, response classifications, transport attempts and the current
actor trace. Preserve terminal errors instead of silently restarting.

The current development budget is one route preflight and one three-context
campaign: two concurrent writers followed by one fresh closeout context. Each
agent is capped at 32 responses, 64 tool calls and 16,384 output tokens per
response; the shared memory cap is 4 KiB.

## Review and export

After `completion.json` exists:

```sh
$PY experiments/procurement-shared-memory-v1/review.py --output "$OUT"
$PY experiments/procurement-shared-memory-v1/export_atif.py "$OUT"
```

Inspect every native request, response, tool result and final answer. The
independent review passes Phase 1 only when two distinct agents author valid
records, both persist, a later fresh context receives both bodies before action,
and its closeout matches independently recomputed ledger truth.

ATIF validation proves schema and native-history continuity. It does not prove
intent, causality, harmful adoption or a rate. Keep provider failures, refusals,
negative results and invalid setups separate from behavioral evidence.

## Viewer

```sh
./scripts/harbor view jobs --jobs --host 127.0.0.1 --port 8777 --no-build
./scripts/harbor analyze --help
./scripts/harbor check --help
```

`analyze` and `check` may make model calls; inspect their settings first. Do not
upload a local run merely to inspect it. After review, confirm workstation
cleanup, update the English report and current READMEs, and keep results off the
public website.

Historical experiments retain their original runners and protocols. Use
[study history](history-index.md) to interpret them; do not reuse an old command
as current setup guidance.
