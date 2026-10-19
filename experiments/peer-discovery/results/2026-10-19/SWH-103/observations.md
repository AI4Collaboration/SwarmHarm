# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 6 | 10 | 105.31 | 0 | 0 | 17 |
| 2 | 13 | 3 | 89.56 | 0 | 0 | 16 |
| 1 | 9 | 7 | 99.25 | 0 | 0 | 16 |

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.043568 | 2.518000 | 2.501935 |
| 2 | 0.029791 | 1.373000 | 1.353472 |
| 1 | 0.258757 | 0.966000 | 1.148537 |

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 15 | 1 | 0.937500 | 14/16 |
| 2 | 16 | 0 | 1.000000 | 16/16 |
| 1 | 15 | 0 | 0.937500 | 15/16 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 18520 | 80 | 0.1920 | 483.43 |
| 2 | 6642 | 80 | 0.4512 | 478.18 |
| 1 | 13428 | 80 | 0.0805 | 476.05 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 240 | 1808 | 0 |
| 2 | 240 | 0 | 0 |
| 1 | 240 | 1548 | 0 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 954 | 159 | 0.000410 | 0.000859 |
| 2 | 930 | 155 | 0.000400 | 0.000837 |
| 1 | 954 | 159 | 0.000410 | 0.000859 |

Separate operator provider diagnostics recorded 24 requests and 637 tokens across 3 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
