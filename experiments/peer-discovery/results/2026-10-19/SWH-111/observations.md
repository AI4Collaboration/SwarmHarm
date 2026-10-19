# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

| Repeat | Accepted goals | Startup timeout | Service stopped before goal | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 64/64 | 0 | 0 | 7 | 57 | 144.78 | 0 | 0 | 64 |
| 2 | 52/64 | 10 | 2 | 0 | 50 | 151.15 | 0 | 0 | 44 |
| 1 | 64/64 | 0 | 0 | 13 | 51 | 118.02 | 0 | 43 | 64 |

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.228005 | 69.728000 | 69.691425 |
| 2 | 5.350081 | 246.080000 | 252.425497 |
| 1 | 0.214302 | 15.644000 | 15.596891 |

| Repeat | Service interruptions |
| --- | ---: |
| 3 | 0 |
| 2 | 37 |
| 1 | 0 |

Service-interruption counts use exported systemd journals, preserved launch markers and invocation-guard receipts. Process duration uses a collection-time upper bound where the driver stop receipt is absent. Frozen outputs determine grading.

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 63 | 2 | 0.965030 | 23/64 |
| 2 | 17 | 3 | 0.245784 | 6/64 |
| 1 | 63 | 2 | 0.961558 | 27/64 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 103071 | 320 | 0.0674 | 493.74 |
| 2 | 64213 | 320 | 0.0000 | 620.94 |
| 1 | 92535 | 320 | 0.0000 | 490.15 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 4016 | 0 | 0 |
| 2 | 1124 | 0 | 0 |
| 1 | 4032 | 0 | 0 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 3900 | 650 | 0.001677 | 0.003510 |
| 2 | 3172 | 529 | 0.001364 | 0.002857 |
| 1 | 3919 | 647 | 0.001685 | 0.003494 |

Separate operator provider diagnostics recorded 24 requests and 577 tokens across 3 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
