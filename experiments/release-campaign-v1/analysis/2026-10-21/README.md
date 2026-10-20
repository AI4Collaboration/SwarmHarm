# Post-collection review

Created after both collectors ended. These files do not change the frozen
protocol, source, trajectories or endpoint. No model calls are made.

`coverage.py <export-dir>` prints per-function and per-variant coverage. It keeps
read, submission, publication and actual wrong delivery separate. A context's
final answer ends that context even if nothing was published; interrupted and
unstarted contexts are not completed negatives.

`semantic_review.py --sol <Sol-export> --luna <Luna-export>` checks each peer body's
actual writer, hash, version and presence in the next native request. It also
checks one matching numerical-function example after removing comments and
docstrings. Matching code and temporal exposure alone do not prove an exploit
or communication causality.

`manual-review.json` records the separate interpretation of actual requests,
tool results, code and final answers. Private reasoning was not used.
`cleanup.json` records source seals, export checks and resource cleanup.
`manifest.json` hashes these post-collection records separately from the frozen
collector and original evidence exports.

The model exports are `../../results/2026-10-20-sol` and
`../../results/2026-10-20-luna`, relative to this directory. Preserve their
write-once independent reviews; these analysis scripts need no inference access.
