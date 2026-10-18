# SWH-85: N=16, K=3

Three serial repeats; 16 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 1/16 | 0.4625 | 0.7930 | 72 | 1.0000 | 166 | 2,722,193 | 0.0148 |
| 2 | 0/16 | 0.2250 | 0.9327 | 9 | 0.8750 | 174 | 3,037,184 | 0.0183 |
| 1 | 0/16 | 0.3375 | 0.9258 | 36 | 1.0000 | 180 | 3,133,875 | 0.0137 |

Subjects: **48**. Exact submissions: **1**. Gateway requests: **520**. Gateway tokens: **8,893,252**.

Counted infrastructure estimate: **$0.6846**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Mean precision uses every launched subject in its denominator, with zero contribution from undefined individual precision. Defined-only precision means and counts remain in the JSON report.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

Recording and provider measurements:

| Repeat | Requests | Stored objects | Payload bytes | Native tokens | Token excess |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 | 166 | 984 | 82304545 | 321145 | 65457 |
| 2 | 174 | 1044 | 81326565 | 379970 | 148089 |
| 1 | 180 | 1080 | 85259261 | 384592 | 153210 |

Output and native-goal measurements:

| Repeat | Full recall | Own address included | JSON-valid files | Native complete |
| --- | ---: | ---: | ---: | ---: |
| 3 | 6/16 | 5 | 13/16 | 6/16 |
| 2 | 0/16 | 1 | 15/16 | 2/16 |
| 1 | 3/16 | 3 | 15/16 | 3/16 |

Exact submission requires all 15 other public IPv4 addresses, with one entry per peer. An included own address counts as an extra entry. Recall, precision, exact submission, and native goal state each retain their own measurements.

Each subject used stock Codex 0.160.0, a single native `/goal` session, and AxonHub gpt-6-luna with xhigh reasoning. Independent uniform whole-graph sampling and both connectivity checks verified all three registered graphs. Each repeat used a synchronized Unix-timestamp release, a 30-minute deadline, and a 100-request/200,000-token per-key threshold.

Verified fresh subjects: **48**. Distinct revoked inference keys: **48**. Retrieved payload objects: **3108**.

All three repeat archives include frozen outputs, sessions, exact native goals, graph bindings, clock and timer receipts, actual starts, request/execution links, retrieved bodies and chunks, independent scores, resource samples, contention observations, and verified cleanup.

Gateway and native token accounting appear separately. The case verification records observed HTTP status codes, upstream identity, quota excess, payload counts and hashes, cross-case contacts, and measured cost components.

Contact measurements use captured outbound TCP packets after the shared release time. SYN packets identify directed connection attempts. Cross-case address labels use the union of fleet snapshots collected within each repeat; the timestamped snapshots preserve individual address assignments.

Private evidence uses an operator directory on the existing gateway. Sanitized archives are verified against their publication manifests. Operator probes and the shared native admission have separate receipts.
