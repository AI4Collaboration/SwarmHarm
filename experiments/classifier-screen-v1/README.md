# Task classifier screen

Status: completed on 19 October 2026. [Results](RESULTS.md) retain original Step 1 and both Step 2 settings and select original Step 3 and Step 4 for removal after confirmed Sol provider safety filters. The separately registered recovery-input correction and all original records are preserved.

The inventory covers 25 current runner families and 316 distinct initial inputs after exact deduplication, including recovery entry points, business tasks and worksheet stages. The model-coverage wrapper reuses fleet tasks. The two protein settings share an initial input and differ after tools run. Historical weather pilots have no current executable runner; unimplemented source candidates and archived code are not counted as runnable tasks.

Each input is checked once on Luna and Sol, reusing matching upstream evidence. Source instructions, role order, task text and tools are preserved. Screening uses high reasoning, one request per model at a time and a five-minute request timeout. Returned tools are never executed. No sandbox, credential or cloud resource is created. A confirmed filter or refusal holds that task; textual matches require context review. Provider errors remain separate.

This is **initial-input screening**, not full-trajectory clearance, every possible runtime state or every configurable ablation. Live peer messages and helper questions are not invented. Passing this screen is not evidence of misalignment or authorization to resume bulk collection.

Evidence is in `../eval-readiness/classifier-screen-2026-10-19`, relative to the repository. Registration fixes scope; packets preserve exact inputs and aliases; outcomes link each observation to a request and response or provider error. Bulk rollouts and the old watcher are stopped. Frozen prompts, budgets, source snapshots and results remain unchanged.

Before admitting a new task, check `experiments/classifier-screen-v1/admit.py --family FAMILY --task TASK`. The [active quarantine](../../data/task-quarantine/active.json) supplements existing study gates; frozen runners are not modified and must not be restarted directly with held tasks.

`build.py` prepares inputs offline with network access disabled. `upstream.py` exports the original Step 4 input using the pinned React wrapper. `run.py` performs one-pass screening; `review.py` exports holds. Seven tests distinguish stream and HTTP filters, native refusals, text candidates, capacity errors and missing-data answers.
