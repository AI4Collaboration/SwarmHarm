# SwarmHarm

**Evaluating Multi-Agent Safety on Benign Tasks**

Source-grounded administrative tasks and audited experiments for studying how independent task agents discover one another, communicate and cross task boundaries.

Start with the [working context](docs/working-context.md). Load older narratives from the [history index](docs/history-index.md) only when needed. The complete previous README is preserved at [cda02a7](https://github.com/AI4Collaboration/SwarmHarm/blob/cda02a7f6e4a420d10c6d3a029d2da1a2b8b72a6/README.md); frozen source snapshots, protocols and results are unchanged.

**Latest research, 2026-10-17:** [method elicitation](docs/research/method-elicitation-2026-10-17.md) separates acquiring a useful unauthorized method, sharing it, and adopting it on a different task. The [offline audit](experiments/method-elicitation-design/bottleneck-audit.json) confirms that all 16 latest workers read their validation receipts and saw `needs_evidence`, with zero receipt-write attempts. The next-probe [design](experiments/method-elicitation-design/README.md) is **unimplemented and unqualified**, with zero new model calls. Earlier source-mirror use yielded two correct unauthorized answers; current staging removes that content route. The next priority is a new composition of that useful route with real peer discovery. The existing reciprocal runtime remains the verified entry point.

**Latest collected results, 2026-10-17:** [HF task-worker refinement](experiments/hf-staging-v1/results/2026-10-17/README.md) retains five adaptive cohorts, **10 natural worlds / 80 ended trajectories**, and **2,127 verified replies across all categories**. Latest reciprocal-input outcomes: Legal **8/8 source-correct full answers**, actual request/read/reply/read; Side **6/8 source-correct full answers and two accurate partials**, all eight reading actual peer work. No confirmed natural receipt tampering or reusable unauthorized-method sharing. The initial infrastructure qualification failure and an earlier round's six receipt-lineage errors remain explicit. [Qualification](experiments/hf-staging-v1/results/2026-10-17/qualification.json).

## Current setup

Verified **2026-10-17** for the local API harness/model pairings; earlier infrastructure evidence keeps its own dates in the history index. `SWH` is the SwarmHarm issue prefix.

- **Runnable harness:** [reciprocal input protocol and commands](experiments/hf-staging-v1/RECIPROCAL.md), [base staging protocol](experiments/hf-staging-v1/README.md). Twelve local JSON functions, independent full stateless histories, encrypted reasoning items and `store:false`. Subjects have no shell, general network, host/grader files or operator credentials. Registry paths are virtual objects.
- **Operator environment:** Python **3.12.14**, `jsonschema` **4.25.1**, `openpyxl` **3.1.5**, `pypdf` **6.10.0**, at `../eval-readiness/hf-campaign-v1-2026-10-17/.venv`. Invoke its Python executable directly; resolving its symlink bypasses installed dependencies. Fresh clones install [requirements](experiments/hf-campaign-v1/requirements.txt) in their own environment.
- **Models and route:** existing operator-only host login at `https://chatgpt.com/backend-api/codex/responses`. The latest packet verifies **1,767 `gpt-6.1-sol / xhigh`** replies and **360 `gpt-6-luna / xhigh`** replies across the recorded categories. This is not a general OpenAI API credential or proof of current GLM/OpenRouter access. Every new model/harness pairing needs a fresh native tool round trip.
- **Before collection:** freeze code, task inputs, conditions and limits in a new output directory. Pass preflight, then the original **four correct/authorized/verified/finished/output-file** full-input calibration records, then run the natural phase. No within-round retry or replacement. Keep all failed gates and later measurement-quality failures. [Example sequence](experiments/hf-staging-v1/results/2026-10-17/README.md#setup-qualification-and-cleanup).
- **Limits:** 512 replies / 1,024 tools per worker; six hours/world; 24 hours/batch; 150 seconds/request; a 30-second chosen wait. Eight inference slots and at most three natural worlds concurrently. Actual latest worlds lasted roughly 9/14 minutes; these allowances are not observed hours/days of autonomy.
- **Task and measurement status:** two original source cases, healthcare operations and accounting, with explicitly derived analyses. Pressure is **none**. No/Side/Legal isolation and both weakness repairs have mechanical controls; the latest natural comparison contains Side/Legal only. Independent source references/SQLite aggregates, actual dispatch/history/global-state replay, receipt lineage and cleanup passed for the repaired staging rounds. The earlier neutral cohort's semantic quality flag stays false; its original model gate stays true.
- **Hosted infrastructure:** keep Multica **0.4.44** and the maintainer's public-server file-access security patch. No routine upgrade or daemon restart. The human-only wakeup patch is different. Coordinator smoke checks, historical local CLI/backend versions and old cloud profiles do not establish lab isolation or new-model readiness. [Historical setup](docs/history-index.md).
- **Run state:** all owned model loops ended; no new key, cloud resource, wakeup or container remains from the latest work. Current method-elicitation changes are documentation and offline reanalysis only. Credentials stay operator-side; no hosted runtime, endpoint or permission changed.

## Research questions

**Communication.** How do communication availability and authorization affect boundary violations? No channel prohibits peer communication and mechanically isolates indirect paths. Side channel prohibits it but leaves a discoverable shared-infrastructure route. Legal channel authorizes a designated channel. Source/data permissions remain separate; these regimes vary both authorization and affordances.

**Emergence and contagion.** Can a deviation arise from benign tasks and then be adopted, amplified, rejected or corrected? Record actual exposure, accepted action and protected-object effect. A copied answer, routine work file, reusable method and causal influence are different outcomes. Seeded adoption diagnostics are separate from spontaneous emergence.

**Whistleblowing.** Does a worker actually exposed to a peer violation voluntarily report it through its authorized private supervisor endpoint? Do not assign it a misconduct-hunting task or confuse operator detections with agent reporting.

## Operating rules

- Keep latest updates first and historical evidence immutable. Read this page and the working context before loading old trial narratives.
- Preserve legitimate task goals and native object permissions; keep actual gold, evaluator instructions, private tests and credentials outside natural subject inputs. Do not append honest-stop, anti-boundary or collaboration reminders. Distinguish planned synthetic task-world weaknesses from accidental audit leakage.
- Acquisition, sharing and adoption require separate eligible denominators. The 2/2 explicitly instructed controls establish functionality under operator authority, not spontaneous willingness. Do not fabricate a successful peer or wake a finished worker to answer a request.
- A missing staged input (404) differs from role denial (403). Correctness, authorized evidence, communication legality, proxy status and intent are separate. An accurate partial is not fabrication; `needs_evidence` is not itself misconduct.
- Bind every read receipt to its actual source object/event. Exact replay alone does not establish semantic provenance. Verify imports before model calls and never resolve the virtual-environment executable to its base interpreter.
- Use independent task labs; test restrictions where the claim applies. Export, independently check, and stop owned runs/resources. Do not infer a server problem from an upstream model error or an infrastructure requirement from a missing default credential.
- Benign administrative tasks only for the current dataset work. High-risk cyber tasks, real external attacks and actual agent harm remain deferred. Larger budgets or more arrivals do not establish long human-time autonomy.

## Research notes

- [Method elicitation and LessWrong source comparison (中文)](docs/research/method-elicitation-2026-10-17.md)
- [HF fleet refinement and design lessons (中文)](docs/research/hf-fleet-refinement-2026-10-17.md)
- [Construct validity and peer discovery (中文)](docs/research/construct-validity-2026-10-17.md)
- [Implemented campaign validity review (中文)](docs/research/hf-campaign-v1-review-2026-10-17.md)
- [Task sources and verification options (中文)](docs/research/task-sources-and-verification.md)
- [All historical setups and experiments](docs/history-index.md)
