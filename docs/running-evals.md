# Run and debug evaluations

Use Harbor 1.4 task inputs, native model records, validated ATIF-v1.8 exports and
independent review. These are separate evidence layers.

## Runtime

Verified 24 October 2026:

- Harbor 0.24.0 with Python 3.12.14 at
  `../eval-readiness/harbor-0.24.0`;
- Docker 29.9.1 with the existing `lima-swarmharm` context;
- AxonHub Responses endpoint `https://lmportal.iefbr14.xyz/v1/responses`;
- exact routes `deepseek/deepseek-v4.1-flash-1017` and
  `z-ai/glm-5.3-flashx`; and
- optional diagnostic Sol route `gpt-5.6-sol` through AxonHub with upstream
  catalog counterpart `openai/gpt-5.6-sol`.

The paired v45 campaigns are complete and negative on the live-dialogue gate.
Both models formed connected four-agent channels, but neither produced a
targeted route-bearing answer or verified dialogue. Cue strength remains the
registered factor; see the
[v45 paired review](research/formation-v45-paired-live-review-2026-10-25.md).
The active v46 source uses `related_record_affordance`; pass
`--cue-condition` at preparation time to freeze any supported cue level.

Keep the scoped AxonHub key in a host-only `0600` file outside the repository.
Never copy it into a task, registration, trajectory or Git. No AWS resource is
needed for the current local study.

## Validate

```sh
PY=../eval-readiness/harbor-0.24.0/bin/python
$PY -m unittest discover -s experiments/swarm-formation-v20 -p '*checks.py' -v
$PY experiments/prompt-contract/checks.py
./scripts/check-format-contract experiments/swarm-formation-v20
$PY -m unittest discover -s experiments/swarm-cause-harm-v2 -p '*checks.py' -v
./scripts/check-format-contract experiments/swarm-cause-harm-v2
python3 scripts/check_dataset_admission_contract.py
./scripts/check-live-rollout
```

These checks make no model calls. They cover business truth, intended-path
impossibility, persistence, natural assembled inputs, collector controls, verifier
rejection cases, Harbor 1.4 and ATIF-v1.8.

`check-live-rollout` verifies status metadata but does not turn offline checks
into behavioral evidence. Use `--require-confirmed` only after collection and
complete trace review; it fails whenever the maintained frozen source differs
from the latest confirmed registration.

## Freeze a new formation campaign

Finish all code, documentation and cleanup first. Then prepare a fresh output and
registration:

```sh
OUT=../eval-readiness/swarm-formation-v20-<fresh-run-id>
REG=experiments/swarm-formation-v20/registrations/<fresh-run-id>

$PY experiments/swarm-formation-v20/run.py \
  --phase prepare --output "$OUT" --registration-dir "$REG" \
  --key-file <host-only-key-file> \
  --model-id z-ai/glm-5.3-flashx --model-alias glm \
  --population 4 --active-contexts 4 --provider-concurrency 4 \
  --cue-condition related_record_affordance
```

Preparation verifies the exact model in the upstream and authenticated AxonHub
catalogs. When their namespaces differ, pass `--upstream-model-id`; for example,
Sol uses `--model-id gpt-5.6-sol --upstream-model-id openai/gpt-5.6-sol`.
Preparation then assembles one Harbor task per agent, runs offline controls and seals
all source and input hashes. Inspect the assembled inputs, then commit and push
the registration. Canonical formation sets active contexts equal to population:
the collector releases the full population through one start barrier and never
admits replacements in stages. After preparation, edit no frozen file. If anything changes,
discard that unused registration and prepare a fresh one.

`--provider-concurrency` controls only simultaneous AxonHub HTTP requests. It
may be lower than four to respect route limits; all four agent contexts still
enter together, remain active and share live state.

Collection refuses to start unless local HEAD, remote `main`, registration files
and all sealed hashes match:

```sh
$PY experiments/swarm-formation-v20/launch.py \
  --output "$OUT" --registration-dir "$REG" \
  --key-file <host-only-key-file>
```

Run one collector per prepared campaign. Independent registered campaign
directories may collect concurrently; each has its own lock, evidence directory
and world state. Monitor `progress.json`, `controller.log`, response
classifications, transport attempts and actor traces. Preserve terminal failures
instead of silently restarting. An incomplete final receives no continuation
message; the preserved context waits until relevant business state changes.
The campaign ends when the whole filing closes, all contexts become quiescent
or the uniform wall-clock limit is reached. Successful submissions return filed
confirmation synchronously; no artificial sleep is part of the environment.

Canonical runs omit `--topology-file` and freeze topology to `null`. External
researchers may pass a directed visibility graph, but that extension is
non-canonical and is not pooled with SwarmHarm results.

## Review and export

After `completion.json` exists:

```sh
$PY experiments/swarm-formation-v20/review.py --output "$OUT"
$PY experiments/swarm-formation-v20/export_atif.py "$OUT"
```

Inspect every native request, response, tool result and final answer. ATIF
validation proves schema and history continuity; it does not prove intent,
causality, harmful adoption or a population rate. Keep provider failures,
refusals, negative results and invalid setups separate from behavior.

## Cause Harm

Use the same prepare, commit, push, collect, review and export discipline with
`experiments/swarm-cause-harm-v2`. Its primary gate requires a recomputed
collective business effect. Its stronger gate also requires full method receipt,
different-project execution and a new verified effect.

## Viewer

```sh
./scripts/harbor view jobs --jobs --host 127.0.0.1 --port 8777 --no-build
./scripts/harbor analyze --help
./scripts/harbor check --help
```

`analyze` and `check` may make model calls; inspect their settings first. Keep
raw campaign output outside Git and results off the public website.
