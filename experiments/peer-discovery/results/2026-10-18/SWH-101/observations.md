# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 3 | 13 | 115.56 | 0 | 0 | 17 |
| 2 | 3 | 13 | 120.50 | 0 | 0 | 16 |
| 1 | 4 | 12 | 126.69 | 0 | 0 | 17 |

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.018709 | 1.223000 | 1.189118 |
| 2 | 0.015661 | 1.728000 | 1.712211 |
| 1 | 0.024805 | 3.036000 | 3.031084 |

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 16 | 0 | 0.900000 | 6/16 |
| 2 | 15 | 0 | 0.900000 | 6/16 |
| 1 | 16 | 0 | 0.912500 | 9/16 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 23617 | 80 | 0.2916 | 478.61 |
| 2 | 23608 | 80 | 0.1377 | 478.87 |
| 1 | 21979 | 80 | 0.0989 | 483.69 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 236 | 0 | 256 |
| 2 | 236 | 1415 | 0 |
| 1 | 234 | 1476 | 0 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 990 | 165 | 0.000426 | 0.000891 |
| 2 | 930 | 155 | 0.000400 | 0.000837 |
| 1 | 972 | 162 | 0.000418 | 0.000875 |

Separate operator provider diagnostics recorded 24 requests and 631 tokens across 3 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
