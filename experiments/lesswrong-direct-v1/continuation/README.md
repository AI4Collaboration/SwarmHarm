# Continue the ordinary-task cells

**Current status: paused on 19 October 2026 at the user's request for task-wide classifier screening.** The collector and its watcher are stopped. The progress index records nine new scored trials plus 48 carried results; unfinished work remains separate. Evidence is preserved in `operator-stop-for-classifier-screen.json`. The three ordinary settings are retained; Step 3 and Step 4 are now in the [to-delete collection](../../../data/task-quarantine/2026-10-19/README.md). The description below records the continuation's original plan.

The blanket stop after Sol's Step 3 filter was too broad. This continuation resumes only the original workbook and two protein-data settings on Luna and Sol. It leaves the held cyber tasks for separate review and does not retry their blocked requests.

The six ordinary-task cells already have eight scored trials each. This phase registers only slots 9–64 in each cell: **336 additional attempts**, carrying the original 48 results toward 384 ordinary-task attempts. It does not complete the full 640-attempt study. No historical trial is replaced or renumbered.

Task text, personas, seeds, tool definitions, time/turn limits, models, endpoint and the disclosed Sol judge remain unchanged. The new registration links the stopped study and verifies its original source and helper hashes. Source files are referenced unchanged; new evidence is written to a separate output directory.

The scheduling change is explicit: run one epoch per model in a pair, then rotate settings. This allows an errored model-setting to be held while independent work continues. Returned refusals remain outcomes and are reported. A provider or infrastructure error holds only its affected cell; no automatic retry, model substitution or prompt rewrite occurs. Local containment failures still stop execution.

Native tools and Docker checks passed again before this continuation started. Its preserved output is `work/eval-readiness/lesswrong-direct-benign-continuation-2026-10-19`. The progress index separates historical and new results. Refusal monitoring covered responses and provider error files while collection was active; that monitor is now stopped. No scheduled task was created.

Use the pinned source environment to prepare and collect in a new output directory:

```sh
$PYTHON experiments/lesswrong-direct-v1/continuation/run.py --parent "$PARENT" --output "$CONTINUATION" --prepare
$PYTHON experiments/lesswrong-direct-v1/preflight.py --output "$CONTINUATION"
$PYTHON experiments/lesswrong-direct-v1/run.py --output "$CONTINUATION" --smoke
$PYTHON experiments/lesswrong-direct-v1/continuation/run.py --parent "$PARENT" --output "$CONTINUATION"
```

The current script requires the six parent cells to contain the preserved slots 1–8. Do not use it to restart an already-started continuation. See the [refusal review queue](../../../data/refusal-review/2026-10-19/README.md) before preparing later task revisions.
