# SWH-99: N=128, K=5

[Observations and recording qualification](observations.md) · [Evidence artifact index](artifacts.md)

Three serial repeats; 128 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0/128 | 0.0145 | 1.0000 | 0 | 0.8438 | 528 | 5,106,281 | 0.1211 |
| 2 | 0/128 | 0.0447 | 0.9997 | 366 | 1.0000 | 623 | 7,425,358 | 0.1229 |
| 1 | 0/128 | 0.1244 | 0.9989 | 1573 | 0.9922 | 972 | 13,562,913 | 0.1174 |

Subjects: **384**. Exact submissions: **0**. Gateway requests: **2123**. Gateway tokens: **26,094,552**.

Counted infrastructure estimate: **$6.8967**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

| Repeat | Requests | Completed-entity payload coverage | Total expected-object coverage |
| --- | ---: | ---: | ---: |
| 3 | 528 | 2400/2400 | 2784/2784 |
| 2 | 623 | 3060/3060 | 3485/3485 |
| 1 | 972 | 5286/5286 | 5944/5945 |

| Repeat | Native complete | Native blocked | Native active mean (s) | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 | 0 | 128 | 24.33 | 256 | 131 |
| 2 | 3 | 125 | 32.59 | 312 | 130 |
| 1 | 11 | 117 | 58.38 | 567 | 131 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Collection inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 225 | 0 | 0 |
| 2 | 562 | 0 | 1349 |
| 1 | 2111 | 1905 | 0 |

| Repeat | Host samples | CloudWatch series | Minimum sampled CPU credits | Peak host used memory (MiB) |
| --- | ---: | ---: | ---: | ---: |
| 3 | 229441 | 640 | 0.8125 | 494.46 |
| 2 | 224438 | 640 | 0.8704 | 479.11 |
| 1 | 210609 | 640 | 0.2371 | 808.81 |

Repeat 1 coverage audit entry: `2/requests/37242/executions/37534/request_body.json`. Its execution status and request lineage are preserved in the attached metadata and recording receipts.
