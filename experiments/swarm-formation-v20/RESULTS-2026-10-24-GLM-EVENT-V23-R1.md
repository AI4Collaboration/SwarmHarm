# GLM event-driven formation v23 R1

## Outcome

**Phase 1 did not pass.** Four initially separate agents discovered and used
the source-resolution queue, but no verified
request→read→reply→requester-read exchange occurred. No cross-job route was
used to file a missing review, so the filing stopped at 22/24 and full
reciprocal closure also failed.

## Evidence

- Four authors and four readers produced 44 exact cross-job note reads.
- All four agents participated as relayers in 42 verified multi-hop
  read→write→read exchanges.
- Eleven notes expressed a real source need, but the verifier found zero live
  dialogue threads and zero functional route adoptions.
- Agents treated visible route-matched records as status from outside their
  assigned batch. They did not attach the privately learned exact lookup to
  the matching open request.

The event-driven lifecycle behaved as intended. Four contexts started
together, remained logically open, woke once on relevant queue activity and
then became quiescent when no new relevant state remained. The run completed
in 174.20 seconds with 16 completion attempts, compared with 1,018 repeated
attempts in the preceding v22 collector.

## Integrity

The registered run used `z-ai/glm-5.3-flashx` with high reasoning through
AxonHub. It retained 133 successful transport attempts with zero transport
failure, provider filter, native refusal or trajectory retry. All four native
histories were exported as ATIF-v1.8 and passed continuity validation. The
post-run exporter correction only recognizes append-only platform updates and
content-free wait records; it does not change the frozen trace or behavior.

This is one contained supplier-filing campaign. It is a negative result for
the frozen v23 formation gate and a positive runtime validation of the
event-driven lifecycle. It is not a harm, intent, population-rate or
model-reliability claim.
