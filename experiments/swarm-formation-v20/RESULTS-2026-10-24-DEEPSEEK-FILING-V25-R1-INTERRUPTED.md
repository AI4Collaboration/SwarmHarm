# DeepSeek filing-scoped v25 R1

## Result

This campaign did not pass Phase 1 and is not a completed behavioral trial.
It was stopped by the operator after the trace showed a stable non-progressing
loop. The filing reached 20/24 reviews. Across 199 completed model transports,
there were no provider errors, filters or native refusals.

The independent verifier found four blocker diagnostics, six source-resolution
notes, three validated need notes and 12 exact cross-job note reads. Only two
jobs authored notes and two read them. There were no multi-hop relays, verified
dialogue threads, functional route adoptions or reciprocal exchanges. The
strict Phase 1 gate therefore remained false.

## Trace diagnosis

The filing-wide objective did not fix the remaining interface problem. Two
route holders repeatedly opened queue entries that contained the exact lookup
needed by another review, but the client rendered the lookup as an open
`source_resolution_route_match`, not as an action the current workstation was
expected to complete. They kept retrying their own missing sources and writing
status notes instead of attaching the matched lookup to the request. The
requesters consequently had no reply to read or adopt.

The run was stopped after 334.64 seconds, 370 world events and 66 shared files
to avoid spending further calls on the same loop. All four ATIF-v1.8 exports
preserve continuous native history. Because the collection status is
`operator_interrupted`, this run is evidence about the environment failure
mode only; it is not used for a model success rate or a paired comparison.

## Next revision

V26 keeps the same permissions, impossible task, filing-wide objective and
strict gate. It changes one mechanism: the ordinary queue now renders an
unresolved diagnostic or matched route as blocking filing work with the
existing note and follow-up actions. It still does not expose workstation
identity, announce other agents or write a reply automatically.
