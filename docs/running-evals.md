# Run and retain experiments

Choose the study first. Both runners use independent workspaces and external
trajectory directories, but their API protocols differ.

- **SwarmForm:** [Chat Completions setup, six tasks and four communication conditions](../rollouts/README.md).
- **SwarmHarm:** [native Codex, streaming Responses, six threat models and two domains](../swarmharm/README.md).

Start with N=4, then 8 and 16. Each cohort runs concurrently; the batch runs cohorts
sequentially. Keep the same model deployment and budgets when comparing N. Check
`plan.json` before launching and watch `index.json` for the active or finished cohort.
No-key local servers work with SwarmForm; SwarmHarm's native adapter requires a key
file (a placeholder is sufficient if the local server ignores authorization).

## Trajectory storage

Keep results on a volume with room for native requests, tool outputs, workspace
snapshots and ATIF exports. Use one output root per study/model/repeat plan.
A full 4/8/16 sweep creates 672 SwarmForm or 336 SwarmHarm agent trajectories.
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
python3 scripts/archive-trajectories /absolute/external/cohort-directory
# Optional: delete the raw copy only after the archive has been verified.
python3 scripts/archive-trajectories /absolute/external/another-cohort --remove-source
```

The tool checks the evidence manifest, archives every file, rereads and hashes the
archive, and writes a sibling `.archive.json` containing a full file index and archive
SHA-256. It never overwrites an existing archive. Keep the default sibling location
so the batch runner recognizes an archived attempt. To read it again:

```sh
mkdir /absolute/external/restored-cohort
tar -xzf /absolute/external/cohort-directory.tar.gz -C /absolute/external/restored-cohort
```

Do not put trajectories in Git. Publish reviewed bundles and their indexes through
a data store or Release when requested. Original scores and frozen source stay with
historical cases. [Accepted input Release](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-accepted-inputs)
contains the completed native SwarmForm input packages and image checksums.

## Resume and inspect

Rerun the identical batch command to skip existing attempts. Incomplete attempts are
reported, not replaced. Complete missing review from a cohort's frozen code; use a
new output root when intentionally collecting another attempt. A completed capture
is not a successful research outcome: inspect the independent outcome and semantic
review required by the claim.

For a SwarmForm capture failure, correct the host storage problem and use the
retained resources listed in `recovery.json`. Export to a fresh directory:

```sh
python3 rollouts/recover.py --run /absolute/external/incomplete-cohort \
  --out /absolute/external/recovered-evidence
```

Recovery preserves the original attempt and does not restart model calls.

Use `python3 scripts/check-ci --plan` and the pinned Python 3.12 environment for
necessary code checks. Setup and software fixtures do not require a hosted API key.
