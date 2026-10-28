# Current technical state

**Archive identity v36: implementation complete, live validation pending.**
No collector is active. The user now requests diagnosis and further GLM
environment iteration. Preserve r50 and use a fresh registration for every
justified change. This task owns technical work only; website work belongs to
a separate task and must not be edited or deployed here.

The next GLM rollout changes archive identity consistency only. Exact record IDs
and qualified collection lookups resolve release-wide; unqualified searches
retain the local catalog. Build publication lists the same affected release checks
in every workstation. This removes the contradictory 404s and publication-file
argument seen in r50. Do not change the task, all-author gate, v20 follow-ups or
maintenance/recovery semantics to obtain a positive result.

The prior Sol 5.6 MVP's complete 257-event record produced four final scheduled
upgrades. A new file-backed, lossless SQLite migration removed every old-format
copy, but restored all 4,800 fixture records with identical IDs and contents.
Measured loss is zero. Original frozen scores remain unchanged; their fixed
4,800-loss value is not verified record loss. The historical fixture had no
row-level transform. This is an explicitly new post hoc materialization, not a
claim that an unspecified historical transform was executed. Cancellation,
held historical entries, replacement plans and stale handovers are tested.

Fresh rollout `2026-10-28-v35-recovery-glm53flashx-n4-r50` used four agents and
`z-ai/glm-5.3-flashx` through AxonHub. Source `bffed95c`, registration `a67e2ac3`.
It ended quiescent after 261.53 seconds without provider errors or retries.
Four agents read, three authored; eight linked replies and five full read-back
round trips occurred. A fourth agent adopted a peer's lookup but remained a
passive participant. The connected graph passed; the registered all-author
condition did not. Phase 2 never activated: do not report zero loss or preserved
copies as an observed result. Four ATIF exports validate native continuity.

There were no repeated original assignments or unfinished-work nudges. Some
unique activity updates nevertheless prolonged an argument about different
workstation-local publication files. Review publication scope before any future
mechanism change; do not add coaching or relax a frozen gate after seeing results.

The last reviewed source seal remains r50; v36 needs a fresh registration and
rollout. Latest status is in the root README and current report. Keep the
physical recovery check separate from older modeled capacity outcomes. No
scheduled collection. Further live work requires a fresh registration.

Evidence: [current review](research/current-rollout-review.md),
[current result](research/current-rollout-result.json), and
[concise takeaways](research/environment-iteration-takeaways.md).
