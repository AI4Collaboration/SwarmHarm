# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Null HTTP status | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 35 | 29 | 138.69 | 0 | 0 | 634 | 64 |
| 2 | 0 | 64 | 141.03 | 0 | 0 | 648 | 65 |
| 1 | 32 | 32 | 121.88 | 0 | 0 | 627 | 65 |

The null-status column counts subject execution metadata whose provider HTTP status field is null. Fresh provider diagnostics retain their actual HTTP responses separately.

| Repeat | Maximum recorded key tokens | Token threshold excess | Request threshold excess |
| --- | ---: | ---: | ---: |
| 3 | 260024 | 60024 | 0 |
| 2 | 235896 | 35896 | 0 |
| 1 | 240854 | 40854 | 0 |

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.017505 | 2.586000 | 2.531312 |
| 2 | 0.024007 | 2.536000 | 2.490367 |
| 1 | 0.044708 | 1.659000 | 1.618374 |

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 64 | 0 | 1.000000 | 64/64 |
| 2 | 63 | 2 | 0.968254 | 2/64 |
| 1 | 64 | 1 | 1.000000 | 63/64 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 56547 | 320 | 0.0000 | 489.04 |
| 2 | 114525 | 320 | 0.0000 | 479.25 |
| 1 | 61214 | 320 | 0.0000 | 476.95 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 4032 | 4134 | 24 |
| 2 | 4020 | 10433 | 0 |
| 1 | 4032 | 5002 | 0 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 3804 | 634 | 0.001636 | 0.003424 |
| 2 | 3888 | 648 | 0.001672 | 0.003499 |
| 1 | 3762 | 627 | 0.001618 | 0.003386 |

Separate operator provider diagnostics recorded 24 requests and 630 tokens across 3 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
