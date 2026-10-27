# Read-only timing and influence analysis

This analysis measures when each agent first reaches a communication milestone
and who reads whom. It reads saved worlds only. It calls no model and leaves
frozen source, original scores and native traces unchanged.

A read is the world's own exact match, as in `read_evidence` of the
swarmharm-v1 protocol on `main`: a complete record (`full_body_output_matches`)
or a unique complete message body (`message_body_output_matches`), bound to
another actor's file version and author. Older worlds have only the first kind. Shared writes follow the
`swarmharm-v1` review rule on `main` (`review.writes()`): a successful bash
call, authored by the actor, not under `/registry/cache/.activity/`. Timestamps come from `at`; untimed
discovery-v3 `final_output` markers take the previous event's time.

Four milestones are recorded for each actor: first shared write, first exact
read of a peer, first exact read by a peer, and first read-back loop. A
read-back loop means the actor exactly read peer P, later wrote a new shared
version, and P then exactly read that version. It does not need a parent
reference, so it is weaker than the audit's cross-job reply. An actor that
never reaches a milestone is censored at its last event, and pooled medians use
Kaplan–Meier estimates.

For each ordered pair the analysis also reports the number of exact reads and
a lead test: how many of B's writes fall within 15 s after one of A's, compared
with B's timeline circularly shifted over the campaign. The stop-rule table asks
which runs would have been cut if a run with no exact peer read by a cutoff
were stopped there. Phase 2 activity before and after activation is reported
descriptively.

```sh
python experiments/swarm-timing-v1/test_timing.py -v
python experiments/swarm-timing-v1/timing.py NEW_OUTPUT_DIRECTORY NATIVE_RUN [NATIVE_RUN ...]
```

A native run holds either `natural/world.json` (swarmharm-v1) or
`trial/world/state.json` (discovery-v3). Several runs are pooled. Eleven checks
cover detection of known coupling, message-body reads, false alarms on independent timelines, a
relay ring without read-back, self-reads and failed writes, censoring, the stop
rule, both layouts and native preservation. The output directory must be new.
It receives `summary.json` with the analysis source hash, `preservation.json`
with one digest of each native run's file hashes before and after analysis,
and a disjoint verified backup. Only `summary.json` and `preservation.json`
are committed under `results/`; native runs stay local.

Results: [RESULTS.md](RESULTS.md). Design and blocked work:
[swarm-timing-design-2026-10-26.md](../../docs/research/swarm-timing-design-2026-10-26.md).
