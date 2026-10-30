# Current technical state

## Active work

Aman’s PR #14 is integrated through the common registered harness pipeline.
Phase 1, Phase 2 and shared execution code are separate. All 374 local checks
have passed, including 30 native adapter checks; prompt, format and dataset
contracts pass. These use local scripted providers and do not validate model
behavior. The user authorized the merge and useful changes from other PRs.
Do not edit the website or recreate the deleted scheduled task.

All three study modes use `experiments/swarmharm-v1/run.py` and the same collector:
`phase1`, `connected`, and `phase2-component`. Phase modules live in `phase1/`
and `phase2/`; common domain definitions live in `scenarios/`; SDK adapters live
in `experiments/runtime/`. Pi SDK through AxonHub is the current default.
Claude Code and Codex subscription adapters are explicit optional conditions;
no new subscription model has been selected for live work. The merged runtime
is **live rollout pending**, even where earlier source had positive results.

Four concurrent contexts remain canonical. Sol 6.1 is the development baseline;
Sol 5.6 is authorized for the independent component work. Keep the existing
`SwarmHarm-AxonHub-Fallback` profile, eligible non-OpenRouter channels first and
same-model native fallback. Do not globally disable channels. Catalog membership
does not establish the actual execution channel; record provenance where exposed.

The latest r144 rollout is closed and fully reviewed; no collector is running.
Source `6cfab28d`, registration `2f582c76`. Its negative lesson is in README
Takeaways. Full raw evidence, twelve byte-matching registration files and review
remain outside Git at `../eval-readiness/knowledge-work-v104-r144-review/`.
Do not repeat the trajectory. r143’s complete review is likewise external at
`../eval-readiness/knowledge-work-v103-r143-review/`.

## Evidence and interpretation

- Phase 1 baseline: Knowledge v98/r136, source `3dfff613`, registration `99bde55d`.
  Four Sol 6.1 contexts; 27 exact cross-job reads, six linked replies from four
  authors and four live round trips. See `research/phase1-baseline.json`.
- Independent Phase 2 positive: Knowledge v103/r142, source `8ab42d58`, registration
  `e27102d8`. Four final files contain four distinct out-of-audience records.
  Supplied methods are assistance. No Phase 1 or prior knowing harmful agreement
  was established. See `research/phase2-component-positive.json`.
- Selected connected positives: Knowledge r122, Engineering r65, Data r74,
  Finance r75. See `research/current-rollout-result.json` and its English review.
- Aman’s Pi/Sol Finance r8 is a separate harness-positive index at
  `research/current-finance-pi-sol-result.json`. Preserve its direct-OpenRouter
  provenance and native-evidence limits; do not relabel it AxonHub validation.

All historical scores and source hashes stay unchanged. None validates the new
integrated runtime. Negative lessons belong in README Takeaways; full records
remain in external archives and Git. The stronger knowing joint-harm objective
remains unmet. Do not infer understanding from access, or joint harmful agreement
from ordinary assembly, prepared materials, private-channel availability or goals.

## Next action

Prioritize independent Phase 2 acceptance-workflow development. The parallel
prototype at `../eval-readiness/phase2-next-development/` provides a real current-
order amendment lifecycle: propose, submit, view and withdraw. A submitted request
is not approval. Test the existing import binding against this lifecycle, preserve
cancellations, and recompute delivered omissions against the approved requirements.
The prototype is offline only and must be integrated into native reconstruction
before any live registration. It changes one business mechanism; no shortcut or
cooperation instruction is added.

Other PRs were inspected: #13’s incomplete-response filter fix is ported with
a focused check; its full branch restores the retired transport and old
registrations and remains unmerged. The
other open PRs are historical/draft studies or target the `ayush` branch, not
current main. Do not merge those trees wholesale.

After source and controls are ready, prepare a fresh minimal registered rollout. Use exact registered harness/model settings. Review all native input,
authored messages, exact reads, actions, ATIF continuity and independently
executed final content. Preserve safe partial work and corrections. No unchanged
instruction repetition and no new pass gates for Phase 2 dialogue.
