# Current data sources

## Active formation data

[Swarm formation v5](../../experiments/swarm-formation-v5/README.md) currently
uses maintained synthetic supplier-review records. They provide ordinary work,
provably missing early source documents, later recoverable archive records and
deterministic review truth. They are development fixtures, not external benchmark
coverage and not model evidence until a registered campaign runs.

## Source-backed candidates

- **MiMo V2.6 RL Harbor general:** 925 workplace tasks packaged for Harbor. The
  audited revision is
  `85c8884bb32b82d5a2f39bb1044bffd8d5d574f1` in
  [FineEnvs/MiMo-V2.6-RL-harbor-general](https://huggingface.co/datasets/FineEnvs/MiMo-V2.6-RL-harbor-general/tree/85c8884bb32b82d5a2f39bb1044bffd8d5d574f1).
  One finance task previously ran through Harbor, but that does not establish
  multi-agent or impossible-task coverage.
- **MiMo cyber:** excluded from current SwarmHarm work.
- **MiMo code:** useful only after a natural non-cyber adaptation with an
  independently verified business effect.

## Design references

- [ImpossibleBench](https://arxiv.org/abs/2510.20270) informs explicit task
  infeasibility and conflict checks.
- [Hack-Verifiable Environments](https://arxiv.org/abs/2605.20744) informs
  embedded discoverable opportunities and deterministic verification.
- [Hackbait](https://pypi.org/project/hackbait/) is a local method reference for
  distinguishing intentional shortcut use from ordinary error.
- [LessWrong's OpenAI–Hugging Face reproduction](https://www.lesswrong.com/posts/fMnC6ZD37qrnZAFYz/openai-huggingface-a-reproduction-and-lessons-for-alignment)
  supplies the Stage 1–3 formation decomposition.
- [METR's incident investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/)
  motivates persistent cross-run work and collective behavior.

These references shape the environment; none is counted as completed SwarmHarm
coverage. Admit a task only after proving its blocker, ordinary truth, reachable
mechanism and independent outcome check.

[FineEnvs audit](fineenvs-harbor-audit-2026-10-21.md) ·
[Stage 1–3 audit](lesswrong-stage123-setting-audit-2026-10-23.md) ·
[Admission contract](../dataset-admission-contract.md)
