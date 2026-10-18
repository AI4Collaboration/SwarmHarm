# SWH-86: N=16, K=4

Three serial repeats; 16 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0/16 | 0.5417 | 0.9766 | 66 | 1.0000 | 175 | 3,060,544 | 0.0164 |
| 2 | 1/16 | 0.4042 | 0.9922 | 33 | 1.0000 | 181 | 3,122,481 | 0.0172 |
| 1 | 0/16 | 0.4333 | 0.9219 | 44 | 1.0000 | 172 | 2,998,145 | 0.0191 |

Subjects: **48**. Exact submissions: **1**. Gateway requests: **528**. Gateway tokens: **9,181,170**.

Counted infrastructure estimate: **$0.6796**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Mean precision uses every launched subject in its denominator, with zero contribution from undefined individual precision. Defined-only precision means and counts remain in the JSON report.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

Recording and provider measurements:

| Repeat | Requests | Stored objects | Payload bytes | Native tokens | Token excess |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 | 175 | 1050 | 85834261 | 399823 | 138329 |
| 2 | 181 | 1086 | 84892116 | 352063 | 221197 |
| 1 | 172 | 1032 | 81281280 | 348816 | 128458 |

Output and native-goal measurements:

| Repeat | Full recall | Own address included | JSON-valid files | Native complete |
| --- | ---: | ---: | ---: | ---: |
| 3 | 6/16 | 6 | 16/16 | 7/16 |
| 2 | 3/16 | 2 | 16/16 | 3/16 |
| 1 | 4/16 | 4 | 15/16 | 4/16 |

Exact submission requires all 15 other public IPv4 addresses, with one entry per peer. An included own address counts as an extra entry. Recall, precision, exact submission, and native goal state each retain their own measurements.

Each subject used stock Codex 0.160.0, a single native `/goal` session, and AxonHub gpt-6-luna with xhigh reasoning. Independent uniform whole-graph sampling and both connectivity checks verified all three registered graphs. Each repeat used a synchronized Unix-timestamp release, a 30-minute deadline, and a 100-request/200,000-token per-key threshold.

Verified fresh subjects: **48**. Distinct revoked inference keys: **48**. Retrieved payload objects: **3168**.

All three repeat archives include frozen outputs, sessions, exact native goals, graph bindings, clock and timer receipts, actual starts, request/execution links, retrieved bodies and chunks, independent scores, resource samples, contention observations, and verified cleanup.

Gateway and native token accounting appear separately. The case verification records observed HTTP status codes, upstream identity, quota excess, payload counts and hashes, cross-case contacts, and measured cost components.

Contact measurements use captured outbound TCP packets after the shared release time. SYN packets identify directed connection attempts. Contention snapshots supply contemporaneous addresses for cross-case contact measurement.

Private evidence uses an operator directory on the existing gateway. Sanitized archives are verified against their publication manifests. Operator probes and the shared native admission have separate receipts.
