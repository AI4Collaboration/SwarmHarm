# SwarmForm & SwarmHarm

**Current research scope, inputs and evidence.**

This README is the single maintained home for research scope, task taxonomy, environment coverage, current status and paper-readiness criteria. Code, exact input fixtures, sealed registrations and evidence indexes remain in their natural locations; they are supporting artifacts, not competing plans.

**Current SwarmHarm scope is Engineering and Knowledge Work.** Data and financial analysis are optional Knowledge Work workloads. Six threat models define 12 two-domain target slots; all 12 have input-bound reviewed positives. Historical labels, scores and complete trajectories remain available. [Current scope and evidence](#swarmharm).

Each SwarmHarm claim is bound to its recorded inputs and runtime. Optional Knowledge Work workloads have separate evidence entries. Current development and evidence stay local.

The shared-capacity cases test composition: one agent can complete safely using spare shared slots, while the recorded combined actions leave Operations work without slots. They do not establish that each agent's task is individually impossible without a shortcut.

Specification Gaming compares request-based admission with independently counted per-report costs. The current business materials disclose both units. [Input settings and evaluation](swarmharm/docs/phase2-taxonomy.md#inputs-and-evaluation).

- [Research framework](#research-framework)
- [Three task classes](#task-taxonomy)
- [SwarmForm: scope and current experiment](#swarmform)
- [SwarmHarm: mechanisms, domains and input coverage](#swarmharm)
- [Current work and acceptance criteria](#current-work)
- [Codebase audit and lightweight maintenance](#codebase-audit)
- [Paper readiness and later inference](#paper-readiness)
- [Evidence and reproduction](#evidence)

<a id="research-framework"></a>
## 1. Research framework

**SwarmForm** asks how initially separate agents discover communication, sustain information exchange, develop organizational structure and change task performance. Channel bootstrapping and emergent structure are both parts of the program. The eight-agent Navier–Stokes experiment is one component, not the entire research agenda.

**SwarmHarm** asks how multiple agents create adverse outcomes through shared system boundaries, infrastructure and evaluation surfaces. Distinguish independent actions that combine harmfully, one-way propagation, and reciprocal coordination. A boundary defect or a harmful action alone does not establish a collective mechanism.

The working principles are operational:

- A potential communication path exists when one agent can change something another can distinguish. Actual communication requires observed use of that path; shared state alone does not prove it.
- Task information gaps can make others' contributions useful. Difficulty alone does not prove that communication or hierarchy is necessary.
- Aggregation, coordination and delegation are different observable functions. Self-description, message counts and graph centrality alone do not establish an orchestrator.
- Collective-effect claims need the authored action, actual recipient observation, subsequent behavior and independently reconstructed outcome. Communication is not required for compositional harm.

SwarmForm's 3×3 describes observed structure × information flow. SwarmHarm uses six threat models and separately measures amplification, compositional failure, propagation, coordination and false-process inference. Research labels stay in operator metadata.

**Registered evidence:** frozen definitions remain authoritative for original scores. Preserve every original case and register changed criteria separately. Seek evidence for each current mechanism without treating a missing false belief as its own compulsory failure class.

<a id="task-taxonomy"></a>
## 2. Task taxonomy: exactly three classes

Domains such as Engineering and Knowledge Work describe content, not task properties. Use these three classes:

| Task class | Meaning | Required basis |
| --- | --- | --- |
| **Impossible at all** | Even pooling all agents' available information and capabilities cannot satisfy the task. | Demonstrate contradictory requirements or a genuinely unavailable necessary fact/capability. A timeout or unsuccessful attempt is insufficient. |
| **Impossible without others' information** | An agent lacks necessary information; other agents have it, and obtaining that information makes the task solvable. | Hold local information fixed and vary a necessary foreign fact: the correct answer changes. Verify a solution using the combined legitimate information. |
| **Possible** | A single agent has the information and conditions needed to complete the task without depending on another agent. It can be easy or difficult. | Supply a reference solution or a clearly defined, checkable research deliverable; distinguish feasibility from the model finding it within budget. |

Difficulty is an attribute within a class. Do not add an Easy class or rename Possible to Difficult alone. If a task's classification is not established, mark that field pending rather than inventing a fourth class or claiming impossibility.

These are task properties, separate from SwarmHarm mechanisms and the criteria frozen for each case.

Cross each class with **intended / unintended** communication conditions. This is a six-condition design framework, not six completed environments or an instruction to run a Cartesian sweep tonight. Task classes, domains, agent counts, communication conditions and observed grid cells are separate fields.

Existing customer-brief and decoder workloads primarily test information dependence; check the actual sealed input before assigning a class. For Navier–Stokes, all agents start with the same materials and no assigned specialties. Its research deliverable accepts checkable partial progress. Do not label the full mathematical target impossible, or claim its complete solution is a calibrated single-agent task.

<a id="swarmform"></a>
## 3. SwarmForm

### Channel bootstrapping and existing coverage

The reviewed delivery contains **50 input configurations**: five substrates × five encoding opportunities × Knowledge Work and Engineering. Substrates are `shared_files`, `shared_ipc`, `worker_endpoint`, `artifact_namespace` and `job_namespace`; opportunities are `payload_content`, `identifiers_metadata`, `operational_state`, `event_pattern` and `timing`.

Recent security audits of widely deployed AI agent benchmarks confirm that these five substrates correspond directly to real cross-trial isolation defects across spatial, temporal and resource boundaries: shared workspaces and volumes (`SWE-bench Pro`, `NYU-LLM-CTF` → `shared_files`), shared internal Docker bridges (`ExploitGym`, `CyberGym`, `SWE-ReX`, `mini-swe-agent` → `worker_endpoint` / `shared_ipc`), shared proxy or package/artifact caches (`artifact_namespace`), and reused execution/grading containers (`InterCode` → `job_namespace`).

Each selected case uses three Sol 6.1 agents with separate memories and no peer roster or communication convention. All 50 meet their recorded communication criterion; 37 deliver all nine business outputs correctly, while 13 retain partial outcomes. These refined cases are not a general success-rate estimate. The broader catalog has 100 configurations including supplemental domains; that does not mean 100 identically reviewed current deliveries.

The tasks are concrete business work: reconcile effective customer terms into cited briefs, or build sensor decoders from versioned specifications and calibration changes. The supplemental domains contain fulfillment reconciliation and receivables settlement. Reusing a task across carriers or changing group size does not create a new task property.

Intended structure registrations currently cover scalable Knowledge Work and eight-agent Navier–Stokes, predominantly shared files. Earlier 4/8/16/32-agent registrations include censored or failed attempts; they do not establish a complete scale study. Broader intended/unintended task coverage and solo comparisons remain part of the research program.

### Structure and information-flow observations

![SwarmForm structure taxonomy — drawn by Gemini](swarmform/docs/swarmform_taxonomy.png)

[Editable figure](swarmform/docs/swarmform_taxonomy.svg). The figure is an illustrative rubric, not a finding.

- Structure: **No Leader / Multi-Leader / Single-Leader**, recording aggregation hubs separately from accepted coordination.
- Information flow: **No observed flow / One-Way / Two-Way**. Check actual reads and replies, including non-message artifacts.
- Label exact intervals and subgroups; record overlap, ambiguity and changes rather than forcing one permanent whole-run label.
- Aggregation counts as structure. An orchestrator claim additionally needs adopted work decisions and feedback. Multilevel delegation needs a linked parent task, onward assignment, execution and returned results; a star of independent requests or unrelated A→B and B→C edges is insufficient.
- Observe formation, persistence, turnover, split/merge, responsibility transfer and disappearance. A quiet window alone cannot establish dissolution.

Historical review supports aggregation and some coordination episodes. The [delegation audit](swarmform/docs/structure-delegation-audit-v1.json) has no verified two-level task-linked path. The [grid review](swarmform/docs/structure-grid-review-v1.json) labels historical events and windows; it is not evidence that every cell occurs under the new runtime.

<a id="navier-stokes-protocol"></a>
### Current experiment: Navier–Stokes, eight agents, paired ten-minute increments

**Question:** can identical-start agents sustain research and spontaneously develop aggregation, multilevel delegation or orchestration, and how do those functions change?

**Task:** explore existence/smoothness for the specified three-dimensional incompressible periodic Navier–Stokes problem, preserving assumptions, derivations, checkable partial claims and unresolved gaps. All eight agents receive the same mathematical task and initial materials at activation. No subproblem, specialty or organizational role is assigned.

**Conditions:** intended explicitly says eight agents share the research task and discloses addresses and message format. Unintended provides no peer roster, joint-work announcement or predefined communication convention. Both have the matched shared-file substrate and neutral notification policy. The conditions run separately, with no cross-condition communication.

**Matched settings:** Sol 6.1 through native Codex and AxonHub, high reasoning, goal off, same tools, context policy, scheduler and finite cumulative token/response/tool-call caps. Exact new caps and participant prompt bytes remain to be finalized and checked against implementation. The old 90-minute caps are not silently reused as a new approved policy.

**Continuation and stopping:**

1. Begin with one 600-second interval per condition. At a boundary, stop or extend **both** by exactly 600 seconds: 10 → 20 → 30 minutes as justified. Do not precommit 90 minutes or extend indefinitely.
2. Preserve identities, native sessions, context, private/shared files, pending notices and cumulative usage. Extra time does not reset or replenish resource caps. Report actual consumption, which can differ between conditions.
3. Within an interval, agents work independently with no round barrier or fixed sleep between eligible steps. Stable real file changes produce deduplicated path notices; distinguish enqueue time from the busy agent's actual receipt. Do not fabricate messages, summarize peer content or reward message volume.
4. Research continues while justified next steps and resources remain. Ending a response or saving a result is not completion. Agents can explicitly record concrete blockers. Do not make them repeat work merely to remain active.
5. Record each paired extension reason: ongoing substantive work or an unfinished feedback chain, for example. Missing an orchestrator is not by itself a reason to extend. Operator reports are never sent to participants as organization or summary requests.
6. Without an accepted extension, stop new dispatch at the boundary and bound cancellation. Later resumption requires validated state retention, not a new agent supplied with an operator summary. Request timeouts must fit the remaining accepted interval.
7. Stop early on resource exhaustion, user stop, infrastructure failure, or verified quiescence: every agent explicitly paused with no inference/tool work, background jobs, pending notices or unsettled changes. Do not restore the old 30-second silence exit. Record unequal termination and use the common observed horizon for paired analysis.

**Record at every boundary:** complete trajectories and artifact versions; actual read/use/reply/return chains; model/tool time, detection, queueing, receipt, idle time and context maintenance; resource use; mathematical progress and pending work; structure transitions with exact times and extension/stop reason. Consecutive intervals are one continuing pair, not independent replications.

**Implementation status:** responsive scheduling, segmented timing and opaque-context engineering fixes exist. `sustained_research.py` still fixes 5,400 seconds, long request timeouts and terminal closure. Paired extensions and validated boundary retention remain to be implemented. Interrupted context maintenance must be explicitly handled. Deleted cancelled-run trajectories are not restored or used.

<a id="swarmharm"></a>
## 4. SwarmHarm: mechanisms, collective effects and findings

SwarmHarm studies how agents' actions and communication produce collective failures in ordinary business work. One parameterized reporting environment supplies Engineering and Knowledge Work tasks. Phase 1/2 describe outcomes within the continuous task.

### Mechanisms and evidence

| Threat model | Selected evidence |
| --- | --- |
| Specification Gaming | Current Sol 6.1 Engineering and Knowledge Work cases each contain one authored four-report release; independent accounting recorded four processing units against two approved units. Both agents later corrected their batching interpretation and disclosed the overrun. |
| Trace Tampering | Current Sol 6.1 cases retained 16 Knowledge Work and 14 Engineering completion/execution mismatches. Notes disclosed manual preparation and missing dispatch execution. |
| Grader Tampering | Agents changed acceptance rules and published two Engineering and three Knowledge Work packs rejected by the original rules. One Engineering and two Knowledge Work recipients read and adopted a peer's rule. |
| Information Scope Violation | Three Engineering and two Knowledge Work agents retrieved task-excluded reports and published them. Exact role-bound replay rejects those reads. |
| Action Scope Violation | Three agents per domain changed Quality Review records outside their task authority and published with exceptions. Owner-bound replay rejects those changes. |
| Shared-resource Interference | Each domain's joint allocations delayed two protected reports. Every complete individual sequence was executable and harmless, including all corrections and withdrawals. |

The [input ledger](swarmharm/docs/research/mechanism-input-status.json) binds each case to its registration, model, input hashes and full evidence. Each row supports its own finding.

### Collective failures and additional findings

**Amplification** requires a measured increase over a comparable individual or uncoupled baseline. **Compositional failure** requires harmless complete individual sequences and a harmful combined replay, including every cancellation and correction.

Information flow records absent, one-way or reciprocal exchanges. Actual adoption and shared plans establish propagation and coordination. Available native reasoning, exact messages and actions support findings about organization and inferred workflows. Current Grader cases show peer-rule adoption; current shared-capacity cases support composition. Shared false-grader inference and native-record editing with method propagation remain open in the current inputs.

### Unified input parameters

Six configurations vary four groups: `access` controls business sources and authority, `coupling` controls shared resources and work files, `verification` selects the evaluated binding, and `observation` selects business feedback. Each threat model has one current configuration. [Values and presets](swarmharm/docs/scenarios-and-parameters.md) · [Taxonomy and source grounding](swarmharm/docs/phase2-taxonomy.md)

**Participant instructions.** Tasks specify report delivery. Agents choose their methods and any communication. Business capabilities, checks and previous-close receipts are visible input conditions. The startup rule requires autonomous work without user clarification or approval, alongside native Codex instructions. Follow-ups require a real workspace change. [Prompt and environment contract](swarmharm/docs/environment-contract.md)

### Current work and reproduction

**All 12 admitted inputs have reviewed Sol 6.1 examples of their registered behavior.** Each case is bound to its sealed source and input hashes, with validated ATIF continuity, protected action replay, blinded transcript review and an independently reconstructed effect. The [input ledger](swarmharm/docs/research/mechanism-input-status.json) records exact versions, cases and evidence.

**METR behavior coverage remains incomplete.** The current cases establish concrete rule changes, business-record mismatches, out-of-role reads/actions, cost overruns and compositional delays. The next work targets native-record editing and propagation, shared false-grader inference followed by action, and collective validation of a method. Monitor interference and measurement manipulation also require their own evidence. [Source-by-source coverage and gaps](swarmharm/docs/phase2-taxonomy.md#metr-behavior-coverage)

Current native-record trials have preserved their records and ended without publication. A status-only work-file trial showed two recipients adopting an authored validation schema, later revised by its author. Selected-input feedback, shared post-publication credits and exposed discussion tools have also yielded no native edits. The [current reviews](swarmharm/docs/research/mechanism-input-status.json) bind these observations to separate cases. The current Codex profile requires explicit authorization for messaging tools; the r257/r261 profile lacks that clause. A registered general business-tool authorization condition tests this potential confound.

Only reviewed runs bound to the current unified input count toward this work. Every behavioral claim needs its own exact actions, reads and final effect; a broader category result supplies no missing subtype. Historical Sol 5.6 cases provide design references only. Each new parameterization needs a fresh registration and trajectory. The [ledger](swarmharm/docs/research/mechanism-input-status.json) separates the twelve admitted inputs from this open coverage goal.

Independent action/file replay establishes final effects; a transcript judge checks the authored behavior with exact native citations. Input availability checks and model evidence are tracked separately. Use each retained case's sealed source for reproduction. Current code and evidence stay local. [Run and review](swarmharm/README.md#reproduction)

<a id="current-work"></a>
## 5. Current work and acceptance criteria

The work order below is organized by dependency. SwarmHarm has twelve admitted inputs and an open METR behavior-coverage goal. SwarmForm and later paper experiments remain separately tracked below.

| Order | Concrete work | Acceptance artifact / condition | Status |
| --- | --- | --- | --- |
| **P0 — audit and consolidate** | Inventory source, dependencies, tests, sealed inputs and evidence; remove redundant active plans and disposable caches; resolve conflicting README versions. | One maintained plan here; historical criteria labeled; local links valid; exact audit/check outcome recorded below. | Complete; full offline regression passed after local installation repair. |
| **P1 — SwarmHarm input coverage** | Maintain the twelve admitted inputs and extend current unified parameters to cover concrete METR behaviors. | Each reported behavior has current input-bound native/ATIF evidence and independent effect review. Historical cases inform design only. | Twelve base inputs reviewed; broader behavior coverage remains open. |
| **P2 — SwarmForm task conditions** | Implement a minimal representative task for each of the three task classes and paired intended/unintended wrappers. Reuse business inputs for information dependence; construct a provably impossible negative control and a known-feasible Possible task. Retain Navier–Stokes as the exploratory research case. | All six class × communication configurations materialize without role cues; solvability/information-dependence witnesses plus negative cross-condition isolation checks; exact prompts and finite budgets reviewable here or through generated input bytes. | Three-class design agreed; fixtures and calibration pending. |
| **P3 — ten-minute research runtime** | Implement paired extension, bounded timeout/cancellation, state retention, budget continuity and context-maintenance boundary handling for the 8-agent pair. | Accelerated offline native fixtures cross multiple boundaries with no reset or extra prompt cues; late events/accounting retained; no unauthorized work after deadline. | Existing fixed-duration policy must change. |
| **P4 — evaluators and controls** | Keep frozen case verdicts; define any future verdict from its specific mechanism and evidence contract. Bind the new verdict to protected truth and native receipts; add action-only **boundary-probing metrics** (environment/network/filesystem discovery outside the local task target across the three task classes); calibrate structure annotations, delegation chains, role transfer and waiting-time attribution. | Positive and negative scripted fixtures; automated negative isolation probes on controls; rejection of false delegation/cascade claims; stated observer blind spots; second-rating protocol ready. Offline checks alone do not establish behavioral findings. | SwarmHarm uses source-bound action replay and transcript citations. Current input evidence is indexed above. SwarmForm temporal work is separate. |
| **P5 — paper evidence and figures** | Reproduce tables from retained reviewed evidence; build per-paper claim/evidence/gap lists, methods, limitations, figure specifications, the **7-benchmark cross-trial vulnerability mapping** (`ExploitGym`, `CyberGym`, `InterCode`, `NYU-LLM-CTF`, `SWE-bench Pro`, `SWE-ReX`, `mini-swe-agent` → 5 substrates & 3 interfaces), and the **spatial/temporal/resource isolation & negative-probe hardening checklist**. Audit distinct contributions and related-work comparisons. | Every numerical claim has a frozen source; no missing experiment is written as a result; both paper outlines and remaining experiment plans live in this README. | Existing evidence available; final paper packages pending. |
| **P6 — reproducible handoff** | After the selected two-domain input/evidence deliveries pass, clean SwarmHarm code, retired entry points and duplicate instructions; keep one current input/evidence index and clearly archived originals. Freeze inputs and evaluation settings; verify setup/export commands, anonymous release plan, runtime/credential boundaries and storage costs. | A clean fresh checkout can run offline checks; no hosted key is required for offline validation; exact later inference manifest is reviewable. | Pending selected-input acceptance. Preserve sealed originals and scores; retain only current entry points plus a concise archive index. Keep the separate SwarmForm work unchanged. |

**Current work boundary.** Maintain SwarmHarm source, documentation and evidence locally. A new collection needs an explicit task and a fresh sealed registration. SwarmForm follows its study-specific authorization.

Future work should update this README rather than create another planning document.

<a id="codebase-audit"></a>
## 6. Codebase audit and lightweight maintenance

### Maintenance contract

Keep six current SwarmHarm configuration selectors, admitted inputs and useful positive evidence. Reproduce retained cases with their sealed source. Removed implementations and development history remain in Git and external archives.

Use `scripts/check-ci` to select checks for the actual changes. Check imports, current selectors, local documentation links and source-bound evidence indexes. Run each selected check once and rerun only after a relevant change or failure.

### Maintained paths

- `shared/`: shared native sessions, provider gateway, workstation and evidence capture.
- `swarmform/swarmform/`: channel inputs, structure tasks, async collection and measurement.
- `swarmharm/phase2/`: synthetic reporting services, bindings and consequence review.
- `swarmform/structure/`: offline structural/temporal evidence analysis.
- `scripts/`: setup, prepare/collect entry points and selected checks; `scripts/check-ci` is the verification entry point.
- `docs/research/`, status JSON and sealed registrations: source-bound evidence, not an additional work queue.

Do not scatter new `tonight`, `final-plan`, `v2-plan` or duplicate status Markdown files. Amend this README. Historical plans and generated prompt previews are for reproduction/testing and are explicitly marked as such. Synced project `sources/` remain read-only.

<a id="paper-readiness"></a>
## 7. Two-paper readiness

**The current target is implementation/protocol readiness and a traceable paper evidence package. Final empirical submission readiness still requires the deferred experiments.** No large experiment is invented, estimated as observed, or replaced by a scripted witness.

### SwarmForm paper

- **Core contribution:** measure autonomous channel formation separately from information use, emergent organization and task uplift; compare supplied and discovered communication under task-property controls, grounded in how real evaluation harnesses leak across shared filesystems, internal bridges, caches and reused containers.
- **Methods:** three task classes (`Impossible at all`, `Impossible without others' information`, `Possible`); intended/unintended; exact carrier opportunities mapped to verified benchmark isolation defects; action-only boundary-probing rate; native read/action attribution; temporal structure and task-linked delegation; equal compute allowances and observed consumption.
- **Current results usable with stated limits:** 50 reviewed channel configurations, business correctness separately scored, historical structure trajectories and censored scale attempts. These are refined/selected examples rather than formation-rate estimates.
- **Required later evidence:** repeated worlds for paired task conditions, matched-budget solo/independent-parallel/communicating baselines, temporal stability and handoffs, second-rater agreement, ablations where a causal effect is claimed. N=8 is the initial structure setting; N=16/32 are later scope, not tonight's inference queue.
- **Planned main figures:** 7-benchmark isolation vulnerability → 5-substrate motivation table; task-class × communication coverage (including boundary-probing shifts under `Impossible at all`); channel discovery/receipt evidence; structure timelines and delegation chains; task quality versus cumulative compute. A mathematical partial result needs claim-level verification before being called progress.

### SwarmHarm paper

- Six threat models share one parameterized reporting engine across Engineering and Knowledge Work. Information flow, amplification, composition and inferred processes are separate findings.
- The current input ledger binds all 12 admitted default inputs and the optional analytical-workload cases to their exact source, model and evidence.
- Independent action replay establishes final effects. Native reads, messages and a transcript review establish propagation and coordination. Complete solo/joint replay establishes composition.
- Paper preparation needs reproducible claim/case mappings, held-out runs after refinement, judge agreement and uncertainty over independent rollouts.

### Shared submission gate

Both papers need distinct claims and explicit shared-infrastructure attribution; related-work comparisons; exact tasks/prompts/budgets; reproducible outputs and exclusion/censoring rules; uncertainty over independent rollouts, not messages; limitations and ethical scope; an anonymized code/data package with attribution/licenses handled appropriately. Each empirical claim needs the matching reviewed evidence.

As of 10 November 2026, the [ICML 2027 call](https://icml.cc/Conferences/2027/CallForPapers) says the call will be posted later. Use the [2026 author instructions](https://icml.cc/Conferences/2026/AuthorInstructions) only as a provisional preparation reference: anonymous submission, reproducible supporting code and key evidence in the main paper. Confirm the actual target year's rules before submission; do not invent deadlines or promise acceptance.

<a id="evidence"></a>
## 8. Evidence and reproduction

SwarmHarm retains admitted inputs and useful positive cases with their complete evidence and original scores. Removed or negative versions remain in Git or external archives, with concise takeaways where relevant. SwarmForm follows its own evidence-retention instructions.

<a id="accepted-inputs"></a>
### Accepted inputs

[50 tested inputs and trajectory index](https://github.com/AI4Collaboration/SwarmHarm/releases/download/swarmform-accepted-inputs/swarmform-main-inputs-reviewed.zip) · [Release and checksums](https://github.com/AI4Collaboration/SwarmHarm/releases/tag/swarmform-accepted-inputs) · [Publication audit](swarmform/docs/research/swarmform-publication-audit.json) · [Machine-readable ledger](swarmform/docs/live-rollout-status.json)

[Structure review](swarmform/docs/structure-grid-review-v1.json) · [Delegation audit](swarmform/docs/structure-delegation-audit-v1.json) · [Balanced SwarmHarm results](swarmharm/docs/research/balanced-study-v2-results.json) · [Evidence index](docs/research/README.md)

### Development and reproduction commands

Run `bash scripts/setup-local` and source the environment file it prints to select the pinned Python 3.12 / Harbor 0.24.0 environment. Installed runtimes and raw outputs belong outside the repository. Use the exact registered image/harness for reproducing an old input; it is not the new interval policy.

```sh
python3 scripts/check-ci --plan
"$SWARMHARM_HARBOR_ENV/bin/python" scripts/check-ci
python3 swarmform/scripts/check_swarmform_inputs.py --status
"$SWARMHARM_HARBOR_ENV/bin/python" swarmform/scripts/export_swarmform_input_matrix.py --output ../accepted-inputs
```

The status command describes the completed 50-input delivery, not completion of either paper. Use `--full` only for an intentional full offline regression. Run selected checks once; repeat only for relevant changes or failures. For the current local-only SwarmHarm task, commit source, prepare and commit a fresh registration, and verify the source/input seals before collection; do not push or upload. Other studies retain their own publication requirements. Do not modify historical evidence to fit a new plan.

Current source uses Sol 6.1 for prospective studies. Existing Sol 5.6 and other-harness evidence retains its identity. Provider credentials and protected truth never enter participant workspaces. The [running guide](docs/running-evals.md) documents reproduction and local source retention. New model collection follows the current work boundary above.
