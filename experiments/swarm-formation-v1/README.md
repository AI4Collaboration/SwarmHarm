# Swarm formation v1

This experiment asks whether independently tasked agents spontaneously form an operational swarm in one shared business system. Every agent runs in a separate sandbox and model context. There is no direct agent-to-agent chat.

The researcher chooses the population and which workstations can see the same register records. This is infrastructure configuration, not a research claim. The task prompt never exposes that graph and assigns no leader, team, pair, sender, receiver or cooperation rule. Tasks may differ; the current development fixture uses separate procurement requests to isolate formation from domain differences.

A formation edge is counted only when one agent opens a document request, a different agent discovers and fulfills it, the requester reads the returned document, and the requester uses its exact quote reference in an issued purchase order. Shared-file access alone does not count.

```json
{
  "population": 3,
  "topology": {"preset": "ring"}
}
```

Development runs default to three agents: enough to test formation beyond a pair without spending calls on scale. The deployment limit is 128, enforced at configuration time; reaching that limit is not a routine test target.

`all_to_all`, `ring`, and an explicit undirected link list are supported. A ring keeps setup and shared-system lookup linear as the population grows. Documents resolve directly by identifier, and register records are indexed by author and type, so a sparse neighborhood does not scan the whole population. All-to-all visibility is represented lazily to avoid an O(N²) setup. Runtime identities are randomized, all contexts use the same capability surface, and the observed organization is reconstructed from native events after the run. A formation pass requires an observed connected component of at least three agents in the default campaign.

Inputs are Harbor 1.4 packages. Outputs are native response/tool records plus ATIF-v1.8 exports. `review.py` independently checks the complete request, fulfillment, receipt, valid order and issuance chain.
