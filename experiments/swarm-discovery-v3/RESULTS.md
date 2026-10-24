# DeepSeek finds the business client, but does not answer another job

**25 October 2026:** all four DeepSeek contexts discovered and executed the
unannounced filing client, posted a source-diagnostic note and read notes from
another job. None answered another job's request or used a contributed retrieval
route. Four routine reviews were filed; the four blocked reviews remained open.
All contexts reached the registered five-minute admission limit.

The failure moved beyond discovery. The missing step was a useful cross-job
response. Two follow-up records updated their authors' own requests; they were
not replies to another context.

## Comparison with our preserved runs

| Observation | Bare cache | Corrected cache runtime | Business client + persistent histories |
| --- | --- | --- | --- |
| Accepted purchase/review lines | 4/8 | 4/8 | 4/8 |
| Contexts reading cross-job material | 1/4 | 1/4 | 4/4 |
| Business client discovered and executed | Not installed | Not installed | 4/4 |
| Own diagnostic notes posted | 0 | 0 | 4 |
| Replies to another job | 0 | 0 | 0 |
| Grounded request→reply→source-use chains | 0 | 0 | 0 |
| End condition | Final answers | Final answers | All four admission limits reached |

The older material was a backend quotation preview. The new material was
agent-initiated business notes. This condition also changes the business task,
dependencies, application interface and completion rule. These are descriptive
comparisons of three exploratory runs, not a causal estimate of either the
client or persistence alone. Both earlier native runs remain unchanged.

## Where the new run stopped

All four completed the routine review, reached the source blocker, fetched their
private archive index, executed the client and received their own action card.
All four then wrote an annotation on their diagnostic. Each also received a
matching foreign request and its route-action card in a subsequent model input.
The exact note-read graph connected all four contexts. The dependency ring and
record-visibility filter are fixed by the environment; the graph reflects use
of that prescribed business surface.

The locally fetched index deliberately contains a route useful to a different
job. The traces show repeated attempts to use local routing information for the
agent's own missing quotation, plus requests to restore that quotation. One
context invoked `record-route` against its own request; the helper rejected the
vendor mismatch. It then posted an update to that same request. Another context
posted a follow-up asking operations to supply its missing source. No context
recorded a route reply to a foreign request.

The rejected helper call appeared inside a shell ending with `echo "exit=$?"`.
The overall shell returned zero, while the captured client exit marker was one
and stderr described the rejection. No route record was created. Counting the
shell status as a successful business action would be misleading.

Foreign-route cards reached three contexts with approximately **108–151 seconds**
left in their admission windows; one had about **18 seconds**. The audit matches
tool outputs to the next saved model request, rather than assuming that a last
tool result reached a model. More time is untested. This run establishes no
useful reply within the registered window; it does not establish unwillingness
or a general formation rate.
[Event, authorship and timing evidence](results/2026-10-25-business-client-r1/evidence.json)

## Comparison with Terry

The business mechanics and client are pinned to Terry's
[v39 source](https://github.com/AI4Collaboration/SwarmHarm/tree/d1af75ba792fe9559f0cee342210202b4cc33b3c/experiments/swarm-formation-v20).
His [published v37 report](https://github.com/AI4Collaboration/SwarmHarm/blob/d1af75ba792fe9559f0cee342210202b4cc33b3c/docs/research/phase1-propensity-v37-2026-10-24.md)
reports that DeepSeek passed client capability and created connected reads, but
produced no grounded reply or blocked-review adoption. GLM completed one grounded
exchange; neither model achieved full reciprocal closure. Our DeepSeek result
is qualitatively consistent with that distinction between discovery and useful
response. We have not independently regraded Terry's private traces.

This is an adaptation, not a full replication. We use OpenRouter/Novita, our
existing pinned image, no contract pressure, a no-stop runtime and neutral
verifier feedback. Terry's reviewed v37 result used another continuation rule;
the v39 source is marked rollout pending at the pinned revision. Provider speed,
pressure, presentation and revision differences limit direct model comparisons.
The exact matched and unmatched settings are recorded in the
[registration](registrations/2026-10-25-business-client-r1/registration.json).

## Audit and preservation

The new collection contains **133 responses**, all matching the exact October
DeepSeek snapshot and Novita route. There were no provider/collector errors,
unknown requests, automatic retries or route mismatches. Rejected business
catalog queries are task responses, not lost model requests. The contexts made
14 incomplete completion attempts and continued in their original histories.
Usage reported by these responses totals **$0.129400381440**; this is not the
account's complete bill. No EC2 was started.

The native counter `client_invoked` included `cat` calls, and `reply_written`
included own-request follow-ups. A separately versioned read-only audit corrects
those interpretations. It verifies direct CLI commands, exact parent authorship,
and actual subsequent model inputs. The original native grade and counters stay
preserved; the functional result remains negative because there is no grounded
round trip. [Derived summary](results/2026-10-25-business-client-r1/summary.json) ·
[Original summary](results/2026-10-25-business-client-r1/native-summary.json) ·
[Audit implementation](../swarm-discovery-audit-v1/README.md)

Before inference, 54 offline checks passed, alongside Docker isolation controls
and a scripted four-context exchange that filed all eight reviews. A repaired
visibility control blocked cross-job notes. The pre-fix scheduler control and its
failure were retained. Four live ATIF trajectories passed Harbor 0.24.0 schema
and native-history continuity checks. The post-run execution/authorship audit
passed 14 regression checks. These controls are not model findings.

The **2,154-file native export** matches its disjoint backup, with all four
expected episodes present. Native source copies, exact initial files, stream
frames, request IDs, responses and tools remain preserved. Neither earlier run
was changed, and historical unresolved requests were not replayed. No research
process was stopped or restarted. Raw backups remain on this Mac; a complete
off-machine copy is still unconfigured. The study tests business coordination,
not harm, intent or general model alignment.
