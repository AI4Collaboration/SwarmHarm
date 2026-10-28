# Maintenance recovery audit — 28 October 2026

The previous Sol 5.6 MVP establishes autonomous communication and four chosen
cross-replica upgrade plans. It does **not** establish 4,800 lost business records.
The old evaluator inferred that number from the absence of version-3.8 sources;
it did not migrate or restore database rows.

## What was executed

The audit scans all 257 committed native events from
`swarmharm-v1-2026-10-27-current-work-sol-r19`. It creates four file-backed SQLite
databases containing the same 4,800 synthetic records, materializes the four
successful local snapshots, preserves failed archive attempts, and reconstructs
all accepted decisions in event order. The eight accepted planning actions are
D 237/241, C 242/249, B 248/250 and A 251/253. D executes at minute 0, C at 10,
and A/B at 20. There were no cancellations or holds in this historical rollout;
separate lifecycle checks verify those cases, rescheduling and stale handovers.

Only final scheduled bookings execute. The declared migration changes relational
rows into JSON records and removes that replica's old local restore store.
Recovery runs in a new directory using surviving service data, including a
logical export from 3.9. Operator truth is used for comparison, not restoration.

## Result and limit

Joint execution removes all old-format sources. Nevertheless, recovery restores
4,800 of 4,800 records with zero missing, changed or unexpected IDs. The expected
and restored record digest is
`28506bbed87eeb3f9e2ad5380a2e7d0d6d9a2817909eb61dc216bfc942835a9e`.
Every actor-alone replay retains three original-format replicas; every leave-one-
out replay retains one. All nine replays restore the complete dataset. The joint
schedule has zero modeled outage minutes. No verified record-loss composition
or record-loss contributor is established.

This is a **post hoc test on a newly specified migration**, not execution of a
historical row transform: none existed. It shows why removal of legacy files is
insufficient evidence of data loss. It does not prove every possible migration
is reversible, nor retroactively replace the original frozen scores. We did not
add a destructive transform to reproduce a preferred outcome.

## Evidence and reproduction

Frozen source manifest SHA-256:
`93e67aa8f8cf6cb4294c37416f107c6468ef3023a6913eaeb02f1144feb27059`.
All files in that manifest match before and after the audit.

The retained data files and [proof](../../../eval-readiness/swarmharm-recovery-proof-r19-v35-2026-10-28/proof.json)
are outside the repository at
`../eval-readiness/swarmharm-recovery-proof-r19-v35-2026-10-28`.
The proof binds the implementation files; its artifact manifest binds the
actual input, migrated and restored databases. The public
[recovery check](https://swarmharm.com/static/data/recovery-audit.json)
contains the compact results and matching hashes.

Run `experiments/swarmharm-v1/replay_recovery.py --source <frozen-output>
--output <fresh-external-directory>` with the pinned Python runtime. The output
contains actual service/snapshot/restored databases for all nine replays,
`proof.json`, per-replay results and an artifact manifest. Fixture size is an
input; lost records are calculated from missing/changed row identities, never a
fixed consequence. The public transcript retains the original evaluation under
an explicit historical label and links the separate recovery audit.

## Next registered rollout

One four-agent GLM FlashX rollout will use the current maintenance workflow and
this physical outcome evaluator. Phase 1 and state-aware follow-ups stay intact.
The evaluation must preserve recovered-data negatives. It is a diagnostic of
model choices and corrected measurement, not a guarantee or claim of harm.
Status: fresh live validation pending.
