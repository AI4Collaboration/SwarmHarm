# Simple task candidates

**Latest direction (2026-10-17):** the separately versioned [HF threat-model campaign design](../hf-threat-model-v1/README.md) selects three of these source prompts for shared-service method-transfer studies. Its case cards preserve source text and incomplete asset/qualification status; its 24 cells are planned conditions, not implemented tasks. Original five-candidate packets, controls and archived results below remain unchanged. No new model collection was started for that design.

Prepared against the current SwarmHarm website on 2026-10-17. This first batch contains five administrative queries: clinic relocation checklist, posting cutoff, injunction-control status, registration audit snapshot, and sample error incidence. They use counting, filtering, timestamps and reconciliation. No clinical or trading decision, cyber environment or external service is in scope.

The source is pinned MiMo `general_agent`, revision `639865fd3374018d6cb29b9fb82dd531406fcf5f`. Original prompts are preserved exactly. Operator annotations, proposed independent checks and qualification flags are separate fields; they must not be appended to the subject prompt. Full original rubrics, gold answers, credentials and verifier code are not exported into task records.

`design.json` records the website dimensions: feasibility and exploitability are separate axes; blocker, vulnerability, pressure, communication and persistence are separately tracked. Both exploitable conditions and unexploitable controls belong in the eventual testbed. Hacking is an outcome. The five domain groups use UN ISIC as a reference, not as a claim that ISIC officially defines these five groups or that each mapping is certified.

These are prepared candidates, **not qualified evaluation tasks**. An LLM judge is present in the source metadata, but that does not establish an effective judge attack. Original read-only constraints do not establish writable tools. Each vulnerability remains unverified, with no assigned CWE/CVE. Feasibility, tool capabilities, source-state checks and any exploit/closed control need independent verification before evaluation. Original source inconsistencies must be retained and reviewed rather than silently fixed.

The [construct-validity review](../../docs/research/construct-validity-2026-10-17.md) compares the LW main study, its real-agent appendix and its automated validity rubric separately. The appendix includes 256 real agent instances with seeded peer cues; using real peers is therefore not a unique methodological distinction. Our current five tasks have LLM-only source rubric items, and inspected writable APIs have not established a task-relevant shortcut. Partial sample downloads do not establish that required workbooks are present.

`construct-validity-contract.json` defines separate evidence gates for boundary trials, blocked trials, self-initiated communication, causal propagation, pressure comparisons, long horizons and whistleblowing. Missing evidence stays unverified. Qualification requires independent review and matching evidence-file hashes; a hash does not itself establish scientific validity. `validity-review-2026-10-17-v2/` is the reviewed static result and confirms that no candidate yet qualifies for a boundary/propagation trial. It leaves the original prepared packet intact. The preliminary `validity-review-2026-10-17/` is retained for provenance; v2 restricts SQL-write extraction to literal database execution calls, avoiding documentation text being mistaken for table names. No behavioral result changed.

From the repository, using the prepared local audit directory:

```sh
../research-audit-2026-10-16/.venv/bin/python data/simple-tasks/prepare.py \
  --source ../research-audit-2026-10-16 \
  --output data/simple-tasks/prepared-2026-10-17
```

Use a new output directory; the builder refuses to overwrite an existing output. It reads existing local data, verifies IDs/revision/constraints, writes JSONL and a hash manifest, and verifies that source files and emitted prompts are unchanged. It does not start containers, call models or access external systems. The audit directory is operator-local and is not supplied by a fresh clone.

The existing HVTB restoration runner is paused and has not completed qualification or model trials. Prior v1–v7 pilot results are historical evidence from their recorded settings; they are not results for this batch. High-risk cyber tasks and CVE reproduction are deferred.

The first follow-through is the separately identified [wayfinding local family](wayfinding/README.md). Its eight original workspace assets are verified in an operator directory, and two independent calculations establish a frozen-source answer. The derived API, synthetic access-check omission and closed control pass 22 deterministic checks; 24 condition records were prepared. The subsequent user-authorized [bounded model trial](../../experiments/wayfinding-pilot/results/2026-10-17/README.md) completed one correct baseline and eight blocked trajectories, with three protected-data reads in open conditions and no peer communication. It verifies one API-only model/harness pairing, not the original MiMo environment or all candidate tasks. The archived five-candidate review and preparation counts remain unchanged. Independent scientific review, confirmatory registration and causal pressure/propagation evidence remain pending. Shared text is initially empty, but native metadata names peers, so this is not a cue-free emergence condition.

The subsequent [communication follow-up](../../experiments/wayfinding-communication/results/2026-10-17/README.md) and [six-stage/two-session stress test](../../experiments/wayfinding-long-horizon/results/2026-10-17/README.md) are separately registered workflow adaptations. The latter completed 18 campaigns and 101 work records, with eight protected reads in open conditions and one authentic legal peer handoff. It records shortened trajectories, factual/format errors and fresh index rediscovery separately from authored-memory persistence. Original tasks/assets and candidate qualification flags are unchanged; this is not human-duration or causal propagation evidence.

To repeat only the static review into a new output directory:

```sh
../research-audit-2026-10-16/.venv/bin/python data/simple-tasks/audit_validity.py \
  --source ../research-audit-2026-10-16 \
  --packet data/simple-tasks/prepared-2026-10-17 \
  --output data/simple-tasks/validity-review-new
```

This reads task metadata and parses tool source with Python AST; it never imports or executes task tools, opens task databases for writing, starts containers or calls models. Future preparations include the validity contract; the archived prepared packet retains the exact original builder and fields used at preparation time.
