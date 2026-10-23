# Formation v9 DeepSeek R1: scheduler diagnostic

## Outcome

This frozen campaign was stopped after the trace confirmed that the runner
executed agents serially. It is a scheduler diagnostic, not evidence for or
against live-fleet formation.

The exact model was `deepseek/deepseek-v4.1-flash-1017` with high reasoning via
AxonHub. The first agent completed 82 responses and 313 tool results before the
second agent entered. The second agent produced 39 recorded responses and 172
tool results before operator interruption. Two planned agents never started.

## Observed evidence

- 75 incidental archive-receipt candidates were preserved.
- No agent manually wrote a peer-directed ask or reply.
- No closed-loop formation chain was observed.
- The collector recorded 123 completed transport attempts with no provider
  errors, filters or native refusals.
- Both started trajectories validate as ATIF-v1.8 and match their native histories.
- Both owned workstations were removed; no persistent container remained.

These counts describe an incomplete serial run. They must not be interpreted as
a model-level negative result. The raw 45 MiB record remains host-only at
`eval-readiness/swarm-formation-v9-deepseek-v41-flash-1017-2026-10-23-r1`.

## Design consequence

Formation v10 keeps the natural tasks and strict provenance gate but starts the
minimum four contexts together and submits their model turns concurrently. A
future pass additionally requires all four chain agents' execution intervals to
overlap.
