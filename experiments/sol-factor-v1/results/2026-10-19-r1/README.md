# Completed Sol factor screen

Read the [English report](../../RESULTS.md) first. All ten worlds completed;
these are exported observations, not new model calls.

- [Semantic review](semantic-review.json): final-use checks for all 20 source
  readers, the single verified peer-method sequence, all 11 peer readers without
  own-cache acquisition, three disclosed wrong-version reuse cases and one
  excluded public-subset candidate. Reviewed final answers have hashes.
- [Summary](summary.json): per-world counts, matched differences and all 60
  workers. Its pending-semantic-review label records the earlier automated export;
  the completed semantic review above resolves it without rewriting that export.
- [Provider summary](provider-summary.json): all 952 native responses, phase and
  model coverage, provider errors and native refusal fields.
- [Independent review](independent-review.json), [policy exposure](policy-exposure.json),
  [actual peer bodies](handoff-evidence.json) and [artifact checks](output-quality.json).
- [Frozen protocol](frozen-protocol.md), [registration](registration.json),
  [seal](registration-seal.json), [input matching](matching-audit.json),
  [calibration](gate.json) and [cleanup](cleanup-summary.json).

Each `cases/<world>/<actor>.json` contains the final answer, structured submission,
source-read events, actual policy exposure, peer evidence and source-world hash.
Analysis sources are included. Full frozen inputs and raw requests remain in the
local study directory; credential-bearing host material is not exported.
