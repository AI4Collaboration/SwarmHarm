# Postcollection method evidence

`analyze.py` extracts cache reads, source-role status, actual peer-body input exposure, directed chat posts and subsequent private reports from independently reviewed terminal cohorts. It does not contact a model or assign automatic intent, deception, ethical refusal or causal-contagion labels.

```sh
../eval-readiness/hf-campaign-v1-2026-10-17/.venv/bin/python experiments/hf-method-analysis/analyze.py --output PATH_TO_WRITABLE_COPY_OF_REVIEWED_EXPORT
```

Copy the reviewed export to a new writable directory before running this command; never use a sealed result folder as its output. Each output stores the exact analysis source and its hash in `analysis-code/`. V1 retains the earlier analysis version, which required every worker to complete; v2 preserves provider failures and conservatively excludes their tool-body deliveries from inferred processed exposure. This is an analysis change, not a subject-runtime or calibration-gate change. Do not overwrite sealed result folders when reanalyzing; use a separate analysis directory/version.

Cached capability acquired with authorization is not automatically a known authorization bypass. A routine output is not automatically a directed message. A request appearing in an input does not establish the model's motive or attention. These distinctions require the raw traces and the separate operator semantic review.
