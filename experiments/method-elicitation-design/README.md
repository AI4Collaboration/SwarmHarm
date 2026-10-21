# Method elicitation design

2026-10-17. **Design and offline reanalysis only; zero new model calls.** The [protocol](protocol.json) is not an implemented runtime or a model-admitted collection. The current verified runtime remains [reciprocal missing inputs](../hf-staging-v1/RECIPROCAL.md).

The latest [bottleneck audit](bottleneck-audit.json) finds that all 16 reciprocal workers saw `needs_evidence` and actually read their own validation receipt through the registry. None attempted a receipt write. The two earlier explicitly instructed controls prove that the local route works under operator authorization; they do not prove spontaneous discovery or unauthorized adoption. More opportunities to read a receipt cannot by themselves test sharing a method that nobody has yet naturally used.

The earlier campaign already recorded two source-correct answers after unauthorized mirror retrieval. Current staging intentionally removes raw registry packages, leaving that content route absent while retaining receipt tampering. The first next implementation should combine the **existing restricted-source mirror/cache opportunity** with the now-verified real-peer discovery mechanism, in a new frozen composition. Normal input staging, source roles and cache ownership stay separate. A synthetic business-reference cache is a later alternative, not the first implementation. Actual operator gold, grader source, secrets and external targets remain inaccessible. The new composition still requires open/closed checks, legitimate completion, independent source truth and differing private answers before model calls.

Only after a worker really holds a method should a sharing trial evaluate whether it reads real peers' requests and writes a reusable procedure. Acquisition on the worker's own critical path is an explicit experimental factor; learning or sharing a legitimate capability is not automatically misconduct. Recipients must actually use the method on a different task object to establish cross-task reuse.

A separate adoption diagnostic may expose an actual method note or a clearly labeled scripted technical demonstration derived from a functionality control. It must retain normal task permissions and supply no operator authorization to cheat. Such a diagnostic measures conditional adoption; it cannot be called spontaneous emergence. If no natural method post exists, retain that zero instead of inventing one.

[Source-level LessWrong comparison and design rationale (中文)](../../docs/research/method-elicitation-2026-10-17.md). Research sources, checked hashes and audit outputs are recorded alongside this design. Historical model results remain untouched.

```sh
python experiments/method-elicitation-design/audit_existing.py
```

This command reads the frozen archive and writes only the current design's derived audit. It does not call a model, execute a task service, edit a historical result or change the hosted runtime.
