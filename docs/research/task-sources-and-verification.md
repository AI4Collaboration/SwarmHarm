# Data sources

The latest [Harbor approval-code pilot](../../experiments/approval-code-v1/RESULTS.md)
is synthetic and HVE-inspired. Four tasks ran through Harbor; this is not MiMo
coverage. Future source-backed imports use Harbor inputs and ATIF outputs.

**Current task data are synthetic.** The completed business-cache studies use
three locally constructed workflows: payroll, billing and procurement. They are
not three external benchmarks. The latest settlement study used synthetic invoices and equipment orders across
three vendors. Two normal jobs passed; six experimental jobs exchanged data but
posted no transaction. See the [settlement report](../../experiments/procurement-settlement-v1/RESULTS.md).

The [new composition design](../../experiments/procurement-composition-v1/README.md)
also uses original synthetic records: six requisitions, three supplier pairs and
explicit tax-inclusive unit prices. The [customer-contract adaptation](../../experiments/procurement-contract-v1/RESULTS.md)
now has a completed six-task Sol run with original synthetic contract terms:
over-budget commitments occurred, but no method propagation.

Earlier source-backed candidates and method references remain useful, but a
candidate dataset is not evaluated SwarmHarm coverage.

## Sources and their roles

- **MiMo general_agent:** business questions, records and MCP tools for realistic
  task construction. The audited revision was
  `639865fd3374018d6cb29b9fb82dd531406fcf5f`, containing 925 general_agent tasks.
  Two local task checks tested execution and grading, not a multi-agent incident.
  See [source dataset](https://huggingface.co/datasets/XiaomiMiMo/MiMo-V2.6-RL-oss/tree/639865fd3374018d6cb29b9fb82dd531406fcf5f)
  and the [historical smoke report](../archive/mimo-smoke-2026-10-16.md).
- **ImpossibleBench SWE:** a reference for pairing ordinary tasks with conflicting
  acceptance tests. Earlier coding studies used derived functions; this is not
  the source of the current business records.
  [Paper](https://arxiv.org/abs/2510.20270).
- **ImpossibleBench audit:** measurement lessons about distinguishing test gaming,
  ordinary errors and disclosed conflicts. The audit concerns its LiveCodeBench
  component, not MiMo. [Audit](https://www.lesswrong.com/posts/qnrjAhiqire7JeoN2/good-evals-are-hard-an-impossiblebench-audit).
- **Hack-Verifiable Environments / HVTB and Hackbait:** references for observable
  shortcut use and detector controls. Earlier local adaptations do not constitute
  full-suite coverage or prove that a business-process exploit works.
  [HVE paper](https://arxiv.org/abs/2605.20744) ·
  [Hackbait](https://pypi.org/project/hackbait/).

The previously supplied counts of 260 writable restricted tasks and 191 tasks
without mutation checks were not independently verified. Neither “all tasks use
LLM judges” nor writable tools alone establishes an exploitable task. Do not use
these claims as measured dataset coverage.

## Domain labels and admission

Earlier domain labels used [UN ISIC Rev.4](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/27/K)
as an activity taxonomy: health (86), finance/insurance (64–66), accounting (6920),
legal services (6910), education (85) and public administration (84).
Finance/accounting is our combined grouping, not an official ISIC category.
These labels describe task activities, not risk levels or completed coverage.

Before admitting a new task, verify provenance, an independently correct ordinary
solution, the blocker, a reachable process weakness, its actual downstream effect,
and the distinction between data copying and method transfer. Keep source wording
and operator adaptations explicit. See the [current design](hf-design-iteration-2026-10-21.md)
and [outcome criteria](../business-outcome-criteria.md).
