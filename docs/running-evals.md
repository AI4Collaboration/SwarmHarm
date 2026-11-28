# Run and retain experiments

The [direct SwarmForm API runner](../README.md#swarmform-with-your-own-api) builds FFmpeg and the checksum-pinned ProgramBench executables on first collection. Its Python environment and image ID are cached under `../eval-readiness` (override with `SWARMHARM_READINESS`). To prepare or rebuild them separately, run `bash scripts/setup-defaults swarmform-api`. Setup needs internet access for the public build inputs. A local endpoint without authentication can leave `OPENAI_API_KEY` unset. Existing output directories resume with the same plan.

The [registered lineup runner](../README.md#registered-lineup) runs Terra 6.1 for SwarmForm and all 11 models for SwarmHarm. Both use N=4/8/16/32 with one repeat. After `bash scripts/setup-defaults`, set
one `OPENAI_BASE_URL` and `OPENAI_API_KEY`, then run `python3.12 scripts/run-evals --execute`.
It performs the N=4 API check first and saves everything under `../swarm-runs/`.

- `api-check/`: startup, tool-result reuse and native-record checks for all 11 models.
- `swarmform/terra/`: 480 cohorts (30 active software tasks × 4 communication settings × 4 populations). Run `navier-stokes-3d-possible` separately with `--tasks navier-stokes-3d-possible` (1800s default horizon; the 30 software tasks default to 600s at N=4/8 and 1200s at N=16/32, overridable via `--cohort-seconds`).
- `swarmharm/<model>/`: 48 cohorts per model, 528 across the lineup.
- Root `plan.json` and `index.json`: frozen default settings and model/study progress.

Within each model/study directory, the batch stores its own plan, index and cohort
logs. Cohorts run sequentially by default, with concurrent participants; SwarmForm also accepts `--concurrency K` and `--max-concurrent-agents M` (for example `--concurrency 8 --max-concurrent-agents 32`) plus optional `--archive` to compact completed cohorts automatically. The same command
preserves completed and partial attempts; `--out` selects a fresh root for a new run.
Native harnesses require a key; a placeholder is sufficient for an unauthenticated
local server. No separate Claude or OpenAI credential is needed.

## Trajectory storage

Keep results on a volume with room for native requests, tool outputs, workspace
snapshots and ATIF exports. Use one output root per study/model/repeat plan.
The default sweeps create 7,200 Terra trajectories for SwarmForm (480 cohorts) and 720 per model
for SwarmHarm (528 cohorts), totaling 15,120 study trajectories.
Storage depends on conversation length and files produced; measure a first N=4
cohort before reserving space for the full batch.

- `plan.json`: exact cohort settings and source identity.
- `index.json`: status, output path, model, N and recorded size for each attempt.
- Per-cohort directories: registration, raw records, outcome/review and evidence manifest.
- Per-cohort `.log`: host runner output, outside the immutable evidence directory.

SwarmForm compresses event streams as `.jsonl.gz` and stores workspace/process
changes incrementally during collection. SwarmHarm keeps
native formats for validation and refreshes large aggregate snapshots at most once
per second. Both retain every captured request and action. After capture and review,
compress a cohort without losing its directory layout:

```sh
python3.12 scripts/archive-trajectories /absolute/external/cohort-directory
# Optional: delete the raw copy only after the archive has been verified.
python3.12 scripts/archive-trajectories /absolute/external/another-cohort --remove-source
```

The tool checks the stop receipt and required traces for current SwarmForm runs, or the original evidence manifest for sealed runs. It archives every file, rereads and hashes the
archive, and writes a sibling `.archive.json` containing a full file index and archive
SHA-256. It never overwrites an existing archive. Keep the default sibling location
so the batch runner recognizes an archived attempt. To read it again:

```sh
mkdir /absolute/external/restored-cohort
tar -xzf /absolute/external/cohort-directory.tar.gz -C /absolute/external/restored-cohort
```

Do not put trajectories in Git. Publish reviewed bundles and their indexes through
a data store or Release when requested. Original scores and frozen source stay with
historical cases. The earlier SwarmForm channel study published its native input packages and image checksums separately. [Historical release](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-accepted-inputs) · [Current SwarmForm inputs](../swarmform/inputs.json)

## Resume and inspect

Repeat the same SwarmForm command and output root to verify and skip completed cohorts. A sealed, physically stopped attempt interrupted by the operator or provider can resume in a numbered sibling directory. Transient provider failures honor the recorded retry time. The original attempt remains available for inspection. A changed plan needs a fresh output root. Evaluate task outcomes and coordination from the collected logs.

For a SwarmForm capture failure, correct the host storage problem and use the
retained resources listed in `recovery.json`. Export to a fresh directory:

```sh
python3.12 rollouts/recover.py --run /absolute/external/incomplete-cohort \
  --out /absolute/external/recovered-evidence
```

Recovery preserves the original attempt and does not restart model calls.

Use `python3.12 scripts/check-ci --plan` and the pinned Python 3.12 environment for
necessary code checks. Setup and software fixtures do not require a hosted API key.
