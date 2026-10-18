# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 4 | 28 | 148.69 | 0 | 0 | 33 |
| 2 | 5 | 27 | 143.22 | 0 | 0 | 33 |
| 1 | 15 | 17 | 128.59 | 0 | 0 | 32 |

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.020528 | 1.370000 | 1.360402 |
| 2 | 0.043610 | 1.233000 | 1.207846 |
| 1 | 0.024328 | 1.419000 | 1.419161 |

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 31 | 2 | 0.944556 | 7/32 |
| 2 | 31 | 2 | 0.941532 | 4/32 |
| 1 | 30 | 1 | 0.936492 | 28/32 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 50723 | 160 | 0.0536 | 472.09 |
| 2 | 48990 | 160 | 0.0000 | 476.64 |
| 1 | 32288 | 160 | 0.0897 | 470.69 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 987 | 7582 | 2800 |
| 2 | 986 | 2699 | 464 |
| 1 | 992 | 4083 | 0 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 1944 | 324 | 0.000836 | 0.001750 |
| 2 | 1908 | 318 | 0.000820 | 0.001717 |
| 1 | 1890 | 315 | 0.000813 | 0.001701 |

Separate operator provider diagnostics recorded 24 requests and 665 tokens across 3 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
