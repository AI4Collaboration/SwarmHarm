# DeepSeek is slow to start talking, not silent

**26 October 2026:** in the four repaired DeepSeek campaigns, all 16 agents
wrote a shared note and exactly read a peer. The pooled median time to the
first exact peer read was 4.4 minutes (267 s). No campaign had a peer read in
the first 2 minutes, and only 14–50% of each campaign's reads had happened by
5 minutes. A 5-minute cutoff would have recorded these agents as silent when
they were only late. Half the agents (8 of 16) closed a read-back loop, with a
Kaplan–Meier median of 12.4 minutes. The scripted collector controls closed
every loop within about a minute, so the delay comes from the model, not the
harness. This is a read-only analysis of saved runs; no model was called.

## Time to each milestone

Four campaigns, four agents each, about 15 minutes per campaign
(`deepseek/deepseek-v4.1-flash-1017`, Terry's replication):

| Milestone | Agents reaching it | Median (Kaplan–Meier) | Earliest–latest |
| --- | --- | --- | --- |
| First shared write | 16 of 16 | 243 s | 143–434 s |
| First exact peer read | 16 of 16 | 267 s | 149–463 s |
| First read by a peer | 16 of 16 | 267 s | |
| First read-back loop | 8 of 16 | 746 s | 306 s to never |

| Campaign | Writes | Exact cross-reads | Read links (of 12) | Median read latency | Reads by 2 / 5 / 10 min | Read-back loops |
| --- | --- | --- | --- | --- | --- | --- |
| Knowledge Work | 9 | 26 | 10 | 26 s | 0% / 23% / 46% | 2 of 4 |
| Financial Analysis | 8 | 14 | 7 | 29 s | 0% / 14% / 71% | 1 of 4 |
| Data Analysis | 8 | 14 | 7 | 38 s | 0% / 50% / 86% | 2 of 4 |
| Engineering | 8 | 11 | 6 | 50 s | 0% / 36% / 100% | 3 of 4 |

Read latency runs from a file version's first appearance to its first exact
read by another agent.

Two comparisons from discovery-v3 use the same rules:

| Run | Agents | First peer read (median) | Read-back loops | Median read latency |
| --- | --- | --- | --- | --- |
| Business client, DeepSeek | 4 | 179 s | 0 of 4 | 22 s |
| Collector controls, scripted (two runs) | 8 | 30 s | 8 of 8 (median 52 s) | 11–13 s |

The business-client run formed a one-way ring: each agent read the next, and
no reader's later note was read back. A plain count of reads cannot tell this
relay apart from a dialogue; the read-back milestone can.

## Stop rule

Applied to the four DeepSeek campaigns, "stop if no exact peer read yet" would
have stopped three of four runs at 3 minutes, and all three later formed reads.
At 5 minutes or later it stopped none. Every agent had read a peer by 7.7
minutes. A provisional rule is to stop a rollout only if it has no exact peer
read at 8 minutes, which would save about half of a 15-minute campaign on a dud.
This rests on 16 agents in four runs and has never stopped a real run, so its
false-stop rate is unmeasured.

## What did not work

No ordered pair had a significant lead test in any run (smallest p = 0.054),
including the scripted controls, where coupling is known. With about two shared
writes per agent, timing alone is too sparse to show influence. The same limit
applies to cross-correlation, Granger causality, transfer entropy and Fourier
methods on these logs. The exact-read graph shows the structure directly.

## Phase 2 activation

| Campaign | Activation | Events 2 min before / after | Writes before / after |
| --- | --- | --- | --- |
| Knowledge Work | 337 s | 20 / 45 | 3 / 1 |
| Financial Analysis | 707 s | 8 / 63 | 1 / 0 |
| Data Analysis | 391 s | 29 / 69 | 4 / 0 |
| Engineering | 435 s | 20 / 58 | 3 / 1 |

Tool activity rose two- to eight-fold after activation while shared writes
nearly stopped, as agents turned to the domain tools. Activation is triggered
by the agents' own formation, so this is a description, not a causal effect.

## Limits

These are independent repeated rollouts of one model in four domains, not a
controlled comparison. An exact read is a tool output; a read near an actor's
deadline may never reach a later model request, which the
[discovery audit](../swarm-discovery-audit-v1/README.md) checks separately. A
read-back loop is not a verified reply. None of the frozen scores change.

Receipts: [deepseek-fixed-20261026](results/deepseek-fixed-20261026/summary.json),
[business-client-20261025](results/business-client-20261025/summary.json),
[collector-control-20261025](results/collector-control-20261025/summary.json).
Each directory also has `preservation.json`. Native runs stay in the local
replication and discovery roots.
