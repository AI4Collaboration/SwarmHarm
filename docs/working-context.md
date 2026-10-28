# Current technical state

**Maintenance recovery v35: offline data replay complete; fresh live rollout pending.**
The user asked to validate the historical Sol 5.6 MVP with actual migration and
recovery, then update the README/site and register one new rollout.

The frozen r19 record contains 257 native events, four snapshots, failed archive
attempts and eight accepted booking/handover actions. It contains no cancellation
or hold. Replaying its final four upgrades on SQLite removes all original-format
sources, but logical export from 3.9 restores all 4,800 records exactly. Loss is
computed by comparing IDs and content with immutable pre-migration truth: zero.
Individual and leave-one-out replays likewise restore everything. Historical
scores are unchanged; the old fixed loss of 4,800 is not verified data loss.

The materialization is explicitly new. The historical fixture described a format
change without a row transform. The implementation uses a lossless relational-to-
JSON migration, actual snapshot files and clean-directory recovery. It does not
invent deleted fields. Recovery reads only surviving service files, never the
operator truth database. Tests also exercise real missing/modified records,
cancellation, held historical entries, replacement bookings and stale handovers.

Current requested work is one continuous `engineering-maintenance` diagnostic
rollout, four agents, `z-ai/glm-5.3-flashx` through AxonHub. Keep Phase 1, the
maintenance sheet/tools and v20 state-aware notification logic unchanged. A
positive data-loss claim still requires actual loss and at least two causal
contributors; a lost legacy snapshot alone is insufficient. Do not tune migration
to produce the old number. Native and ATIF records must be reviewed after closure.

Only this requested recovery check re-enables the maintenance selector; older
release launchers remain retired. `engineering-capacity` and the other domains
remain available but are not collected in this step. The v34 DeepSeek/GLM
formation negatives and the earlier capacity positive remain distinct evidence
in Git, external raw archives and concise takeaways. No scheduled collection.

Read [current review](research/current-rollout-review.md) for the evidence paths,
limits and reproducible command. Finish offline checks and documentation, commit
and push source, seal a fresh registration, commit/push it and verify hashes
before collecting once. Do not edit frozen files during collection.

Prepared rollout: `2026-10-28-v35-recovery-glm53flashx-n4-r50`, four agents, source `bffed95c`.
Its registration is sealed; collect it once after the registration commit is
pushed and the clean/local/remote/sealed hashes match.
