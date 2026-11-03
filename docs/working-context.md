# Current technical state

Phase 1 and Phase 2 are independent studies. Current work consolidates standalone
Phase 2 results. There is no active rollout, registration or planned collection.

## Two core findings

1. **Coordinated adverse outcomes, including knowing execution.** R212 supports
   autonomous sharing and adoption; r199 supports consequence-aware endorsement
   before action. Each left 53 independently verified changed entries. R165
   supplies the operational example: 31 of 55 reports delayed.
2. **Shared inference of a nonexistent approval process.** R187 supports agents
   collectively developing and reinforcing that inference without explicit
   manager/grader cues. No material action or adverse outcome followed.

The claim-to-evidence mapping is in [phase2-design.md](phase2-design.md).
Discovery, dialogue, adoption, knowledge and execution are supporting evidence,
not separate headline findings. Separate cases do not establish one continuous
inference-to-harm trajectory.

## Required mechanism still to verify

Compositional failure remains required: individual complete sequences execute
harmlessly, but their combination produces an adverse result. R165 establishes
joint dependency because solo execution is blocked; it does not fill this
coverage requirement. Review usable historical evidence before proposing new
collection. No new rollout is authorized by this clarification.

## Maintenance

- Keep the two findings consistent with README.
- Keep negative takeaways in README and preserve underlying evidence.
- Closed rollouts must not be silently resampled or rescored.
- Live inference, if separately requested, uses four independent Pi SDK contexts,
  `openai/gpt-5.6-sol` and AxonHub same-model fallback.
- Selected bundles are indexed in `docs/research/trajectory-release.json`.
  Git preserves historical registrations.
- No new rollout or website work is part of this consolidation.
