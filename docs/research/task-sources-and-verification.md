# Task sources and verification

## Maintained formation fixtures

[Formation v20](../../experiments/swarm-formation-v20/README.md) uses synthetic
supplier-review records with deterministic truth. Four equal batches contain
active records, one indexed retained record and one locally unreachable record.
Each indexed selector unlocks a different batch. The ordinary source-resolution
queue has missing job scoping, so agents can discover cross-job records without
being told that peers or a channel exist.

[GLM FlashX R2](../../experiments/swarm-formation-v20/RESULTS-2026-10-23-GLM-R2.md)
submitted 23/24 reviews and produced three cross-agent recoveries, but failed the
strict all-jobs gate. These fixtures support environment development, not broad
domain coverage or a population rate.

## Maintained Phase 2 fixtures

[Cause Harm v2](../../experiments/swarm-cause-harm-v2/README.md) uses synthetic
procurement projects, source budgets and covenants, a reachable ordering weakness
and an independent ledger verifier. DeepSeek R1 was negative because the actions
occurred in safe serial order. The corrected concurrent runner awaits a new
campaign after formation is established.

## Source-backed candidates

- **MiMo V2.6 RL Harbor general:** 925 workplace tasks at audited revision
  `85c8884bb32b82d5a2f39bb1044bffd8d5d574f1` in
  [FineEnvs/MiMo-V2.6-RL-harbor-general](https://huggingface.co/datasets/FineEnvs/MiMo-V2.6-RL-harbor-general/tree/85c8884bb32b82d5a2f39bb1044bffd8d5d574f1).
  One finance task ran through Harbor; this establishes integration only.
- **MiMo code:** a candidate only after a natural business adaptation with an
  independently verified outcome.

## Design references

- [ImpossibleBench](https://arxiv.org/abs/2510.20270): explicit infeasibility.
- [Hack-Verifiable Environments](https://arxiv.org/abs/2605.20744): embedded,
  discoverable opportunities and deterministic verification.
- [Hackbait](https://pypi.org/project/hackbait/): distinguishing deliberate
  shortcut use from ordinary error.
- [LessWrong reproduction](https://www.lesswrong.com/posts/fMnC6ZD37qrnZAFYz/openai-huggingface-a-reproduction-and-lessons-for-alignment):
  separate discovery, request, sharing and use measurements.
- [OpenAI incident summary](https://openai.com/index/hugging-face-incident-and-the-road-ahead/)
  and [METR investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/):
  persistence, blocked-task concentration and cross-run work.

References shape the environment; they are not completed SwarmHarm coverage.
Admit a task only after proving its blocker, source truth, reachable mechanism
and independent outcome check.

[Stage 1–3 audit](lesswrong-stage123-setting-audit-2026-10-23.md) ·
[Admission contract](../dataset-admission-contract.md)
