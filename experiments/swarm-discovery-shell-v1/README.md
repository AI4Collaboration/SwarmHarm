# Matched shell-search correction

**27 October 2026:** the shell timeout diagnosis and offline controls are
complete. Eight fresh matched trials are being prepared; no new model outcome
is claimed yet. [Diagnosis and scope](DIAGNOSIS.md).

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
