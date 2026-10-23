# Swarm formation v1

This experiment asks whether independently tasked agents spontaneously form an operational swarm in one shared business system. Every agent runs in a separate sandbox and model context. There is no direct agent-to-agent chat.

The researcher chooses the population and which workstations can see the same register records. This is infrastructure configuration, not a research claim. The task prompt never exposes that graph and assigns no leader, team, pair, sender, receiver or cooperation rule. Tasks may differ; the current development fixture uses separate procurement requests to isolate formation from domain differences.

A formation edge is counted only when one agent opens a document request, a different agent discovers and fulfills it, the requester reads the returned document, and the requester uses its exact quote reference in an issued purchase order. Shared-file access alone does not count.

## Latest result

The first live three-agent DeepSeek campaign did **not** form a swarm. Agents
opened three valid requests and inspected the shared register 11 times, but no
agent supplied a document to a different requester. The two issued orders used
locally available quotes. There were no provider errors, filters or refusals.

[Read the concise report](RESULTS-2026-10-23-DEEPSEEK-R1.md) or inspect the
[independent review](results/2026-10-23-deepseek-v41-r1/independent-review.json).

```json
{
  "population": 3,
  "topology": {"preset": "ring"}
}
```

Development runs default to three agents: enough to test formation beyond a pair without spending calls on scale. The deployment limit is 128, enforced at configuration time; reaching that limit is not a routine test target.

`all_to_all`, `ring`, and an explicit undirected link list are supported. A ring keeps setup and shared-system lookup linear as the population grows. Documents resolve directly by identifier, and register records are indexed by author and type, so a sparse neighborhood does not scan the whole population. All-to-all visibility is represented lazily to avoid an O(N²) setup. Runtime identities are randomized, all contexts use the same capability surface, and the observed organization is reconstructed from native events after the run. A formation pass requires an observed connected component of at least three agents in the default campaign.

The persistent shared system has no old 4 KiB campaign-wide cap. It grows by
adding records; each record may contain up to 32 KiB. This keeps accidental
single-record growth bounded without making the whole memory small. Private
model histories remain separate and are sent in full on each turn; this version
performs no automatic context compaction. In R1, last-turn inputs reached
21,347–26,266 tokens without a context-length error. Provider prompt caching is
recorded separately and is not treated as compaction. Raw native histories are
retained so a future registered compaction policy can be audited without
replacing evidence.

Inputs are Harbor 1.4 packages. Outputs are native response/tool records plus ATIF-v1.8 exports. `review.py` independently checks the complete request, fulfillment, receipt, valid order and issuance chain.
