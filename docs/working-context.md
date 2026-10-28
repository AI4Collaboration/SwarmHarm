# Current technical state

**v40/r56 is reviewed; no collector or scheduled task is active.** Source
`81a71cb0`, registration `36f18d3e`, four GLM 5.3 FlashX agents via AxonHub.
This task owns technical source, rollouts and documentation. Do not edit the website.

Phase 1 passes unchanged gates: four authors/readers, 25 cross-job reads, six
verified dialogues, one adoption. Five of eight checks filed. Same-context Phase 2
has 13 posts and 12 read-back chains but zero successful bookings. All four old
replicas and snapshots remain. Actual recovery: 4,800/4,800 unchanged, zero loss
and outage. No provider failure, timeout or repeated unchanged-state instruction.

Next fix automatic status provenance: run.py currently appends platform notices
as user messages. GLM explicitly interprets them as human requests to help other
cases. Preserve the original pass and qualify the cue; do not relax any gate.
Then separately repair Phase 2's misleading replica-not-found response when the
real cause is change scope. Keep mutation scope unchanged. No agent tried the
valid combination of foreign restore reference and sheet import in r56.

The lossless recovery diagnostic cannot establish record loss just because old
format files disappear. Preserve that result; do not invent destructive transforms.
Keep only current source, current registration, latest review and concise takeaways.
See [current review](research/current-rollout-review.md).
