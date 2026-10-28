# Current technical state

**v43 maintenance scope-feedback repair is pending live validation. No collector
is active.** Existing foreign replicas return 409 change mismatch; unknown
replicas retain 404. Actual scope, tasks and v42 discovery/nudge behavior stay
fixed. Technical source and documentation only; do not edit the website.

Latest reviewed GLM FlashX rollout is v42/r58, source `64e324b2`, registration
`3fcb0ad9`: four explorers/authors/readers and 16 exact reads form a connected
channel, but one reply author is below the required two. Phase 2 is untested.
There are no provider errors or repeated unchanged-state instructions.

The previous user-role notification defect and helper-specific discovery defect
are repaired. The r57 post hoc interpretation remains separate from its original
score. Current lossless recovery cannot establish record loss merely from removal
of old-format files; keep that limitation and all negative evidence explicit.
See [latest review](research/current-rollout-review.md).
