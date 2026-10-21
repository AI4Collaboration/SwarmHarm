# Stopped capability attempt

**21 October 2026. No experimental job started.** The business task pilot was
stopped because the batch output field `records` was ambiguous: all three batch
workers interpreted it as a collection, while the service expected a count.
The interface rejected those submissions. This is a task specification problem,
not evidence of misalignment, inability to calculate or a negative sharing result.

Four actual reports were delivered correctly before the operator stop. Three
workers had finished; three were interrupted. A request in flight was cancelled,
not retried. No record was recovered by the public-only reader, and no provider
error or safety refusal was recorded among completed responses. All six owned
workstations were removed. No experimental context was admitted.

[The post-hoc cancellation audit](results/2026-10-21-sol56-stopped/independent-review.json)
verified frozen inputs, native histories, executed tools, document availability,
actual delivered values, filesystem provenance and repeated public recovery.
It explicitly records the one request without a response. The raw collector
completion retains `status: running` because its interrupt handler did not set a
terminal label; [the operator stop](results/2026-10-21-sol56-stopped/operator-stop.json),
interrupted states and cleanup establish termination. The raw record is preserved.

[Revision 2](../business-cache-v2/README.md) clarifies only the numeric row-count
and total types before fresh registration and calls. All other subject-facing
inputs, records, formulas and settings remain the same. The revision is a
separate test, not a replacement of this trajectory.
