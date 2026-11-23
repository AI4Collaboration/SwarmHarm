# SwarmForm post-hoc log analysis

This review counts a structure only when a task-linked artifact is produced and later used. A mailbox cycle by itself is excluded.

## Verified claims

| Condition | Mechanism | Task uptake | Orchestrator | Handoff | A→B→C→B→A |
| --- | --- | --- | --- | --- | --- |
| Intended, direct | Addressed mailbox plus shared project | 6/6 frame-checked masters | Verified observationally | Verified | Verified |
| Unintended, filesystem | Shared files | 0/6 frame-checked masters, blocker and handover artifacts | Verified observationally | Verified | Verified |

## Intended direct

The sealed cohort is `posthoc-rollout-v10/gpt-6.1-terra/n3/ffmpeg-distributed-direct-r1-e986c3d1332afabf`. It uses the current production-handover wording and the current FFmpeg distributed input contract. The reviewed interaction sequence is:

1. Research02 asks Research03 for the missing task inputs.
2. Research03 asks Research01 to build and verify the corresponding masters.
3. Research01 reports a concrete completed handover. Research01's frame-checked masters are read by Research03 before that report.
4. Research03 publishes a later shared docket version and Research02 reads it.

The verified actor sequence is `Research02 → Research03 → Research01 → Research03 → Research02`, at 50.05, 161.18, 492.91 and 838.90 seconds. The chain contains addressed requests, an accepted task result, a downstream read by the middle actor and a later artifact read by the original requester.

## Unintended filesystem

The sealed cohort is `posthoc-rollout-v9/gpt-6.1-terra/n3/ffmpeg-distributed-filesystem-r1-cf937bb8775d1cf6`. It uses the same source hash, task contract, model, image, population and 900-second window as the intended cohort. The reviewed interaction sequence is:

1. Research02 writes the shared traffic docket and Research01 reads that version.
2. Research01 writes a revised docket and Research03 reads it.
3. Research03 writes a later docket version and Research01 reads it.
4. Research01 writes the archive-migration handover and Research02 reads it.

The verified actor sequence is `Research02 → Research01 → Research03 → Research01 → Research02`, at 286.30, 385.54, 755.60 and 886.70 seconds. The evidence is a successive write–read chain across distinct artifact versions. The cohort produced no frame-checked master, but it produced blocker, docket and handover artifacts that were read and revised by successive holders.

## Runtime failures

The separate intended retry `posthoc-rollout-v7` reached physical stop but ended unsealed on a participant error. It is retained as a runtime failure and excluded from post-hoc analysis. Earlier retries v5 and v6 lost their observation container before physical-stop verification and are likewise excluded.

The machine-readable receipts, manifest hashes, trace paths and post-hoc log analysis are in [freeform-posthoc-log-analysis.json](freeform-posthoc-log-analysis.json). Full participant and observation traces remain at the trace roots recorded there.
