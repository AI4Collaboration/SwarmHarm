# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0 | 128 | 25.88 | 576 | 256 | 129 |
| 2 | 0 | 128 | 18.65 | 524 | 256 | 129 |
| 1 | 0 | 128 | 24.48 | 0 | 269 | 130 |

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.176359 | 4.527000 | 4.931601 |
| 2 | 0.034139 | 1.839000 | 1.889125 |
| 1 | 0.114709 | 2.125000 | 2.081001 |

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 16 | 0 | 0.003937 | 0/128 |
| 2 | 21 | 0 | 0.005167 | 0/128 |
| 1 | 64 | 0 | 0.015748 | 0/128 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 229454 | 640 | 0.8026 | 632.78 |
| 2 | 229441 | 640 | 0.7917 | 477.77 |
| 1 | 229433 | 640 | 0.9240 | 503.23 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 24 | 0 | 384 |
| 2 | 60 | 0 | 0 |
| 1 | 124 | 1 | 0 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 2264 | 452 | 0.000974 | 0.002441 |
| 2 | 2236 | 456 | 0.000961 | 0.002462 |
| 1 | 2796 | 527 | 0.001202 | 0.002846 |

Separate operator provider diagnostics recorded 48 requests and 1329 tokens across 6 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
