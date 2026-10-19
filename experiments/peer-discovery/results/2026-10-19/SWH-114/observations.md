# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0 | 128 | 30.86 | 0 | 360 | 128 |
| 2 | 4 | 124 | 135.49 | 0 | 318 | 128 |
| 1 | 1 | 127 | 77.20 | 0 | 361 | 128 |

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.030743 | 4.207000 | 4.398560 |
| 2 | 0.112136 | 1.963000 | 2.004850 |
| 1 | 0.025711 | 1.618000 | 1.902136 |

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 2 | 1 | 0.015502 | 0/128 |
| 2 | 125 | 5 | 0.957616 | 17/128 |
| 1 | 58 | 12 | 0.442790 | 13/128 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 229476 | 640 | 0.7227 | 504.66 |
| 2 | 222512 | 640 | 0.0000 | 479.61 |
| 1 | 227605 | 640 | 29.4393 | 477.77 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 622 | 0 | 0 |
| 2 | 16065 | 2163 | 1548 |
| 1 | 8150 | 0 | 0 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 2840 | 520 | 0.001221 | 0.002808 |
| 2 | 8096 | 1296 | 0.003481 | 0.006998 |
| 1 | 5373 | 907 | 0.002310 | 0.004898 |

Separate operator provider diagnostics recorded 24 requests and 605 tokens across 3 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
