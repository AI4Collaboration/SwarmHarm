# Matched shell-search correction

**27 October 2026:** all eight registered matched trials have finished. Both
stock DeepSeek trials are unscored after shell stalls; both repaired DeepSeek
trials avoided those stalls but formed no verified reply chain. GLM passed the
functional communication gate in all four trials. None of the six scored trials
achieved full reciprocal closure. [Final report](RESULTS.md) ·
[Aggregate evidence](results/2026-10-27-final-r1/summary.json) ·
[Diagnosis and scope](DIAGNOSIS.md).

The [first checkpoint](results/2026-10-27-checkpoint-r1/summary.json) remains
preserved alongside the final results.

The comparison crosses DeepSeek/Novita and GLM Prime/Alibaba with stock versus
finite-root search defaults. There are two repetitions per cell, four concurrent
contexts per trial, and up to two trials at once. Both images derive from the
same pinned parent and differ only in the text-search shim. Initial messages,
workspace files, fixture, plan, business permissions, tools, 15-minute admission
window, 30-second shell wait and neutral continuation remain matched.
No peer/channel hints, pressure or seeded notes are added. These are fresh
contexts; no earlier responses or unresolved commands are replayed.

The wrapper only changes ordinary search defaults. Root recursion skips the
kernel/device mounts; ordinary business folders, finite stdin and explicit paths
remain available. Source and image digests are sealed before collection. GNU
stock behavior is retained in the control image. The old runtime never signals
or cleans up a process, and unknown tools/requests remain preserved and unscored.

```sh
python experiments/swarm-discovery-shell-v1/test_grep.py -v
python experiments/swarm-discovery-shell-v1/test_study.py -v
python experiments/swarm-discovery-shell-v1/validate_shell.py NEW_CONTROL
python experiments/swarm-discovery-shell-v1/validate_business.py fixed NEW_BUSINESS_CONTROL
python experiments/swarm-discovery-shell-v1/run.py prepare --root NEW_SUITE --backup NEW_BACKUP --inputs-from ARCHIVED_V3_RUN
# Publish the exact registrations; use the private credential wrapper to launch once.
python experiments/swarm-discovery-shell-v1/controller.py --root NEW_SUITE --backup NEW_BACKUP
```

The prior parallel suite independently held after exhausting its shared key.
Its state, surviving shells and reservation are left unchanged. This suite uses
the previously authorized private key with a separate locked allowance ledger,
no retries or fallback, local capacity/EOD gates and verified per-trial exports.
Provider-aware audits and ATIF-v1.8 exports use Harbor 0.24.0 and check complete
native history continuity. A grader failure is unknown, never a negative result.
Reports separate unresolved-tool incidence, usable trials, business completion
and grounded exchanges. Two repetitions and a fixed template cannot establish
model-level rates or general alignment. Raw backups remain on this Mac.

To rebuild the images locally, tag the recorded parent digest as
`swarmharm-shell-parent:20261027`, then use a Dockerfile containing
`FROM swarmharm-shell-parent:20261027` and
`COPY --chmod=755 image/grep_fixed.py /usr/local/bin/grep` (or `grep_stock.py`
for the stock arm). Build from this study directory with `--pull=false` and
`--network=none`. The published digests identify the retained local builds; a
rebuild must be registered with its own resulting digest.
