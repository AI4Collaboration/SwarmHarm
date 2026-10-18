# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0 | 128 | 39.18 | 0 | 297 | 129 |
| 2 | 0 | 128 | 38.66 | 0 | 254 | 129 |
| 1 | 0 | 128 | 42.56 | 0 | 283 | 128 |

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.177260 | 7.737000 | 9.519393 |
| 2 | 0.117308 | 2.613000 | 2.604630 |
| 1 | 0.075773 | 1.925000 | 2.065619 |

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 5 | 0 | 0.039001 | 4/128 |
| 2 | 3 | 2 | 0.023253 | 0/128 |
| 1 | 5 | 1 | 0.038816 | 1/128 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 229433 | 640 | 0.2698 | 488.92 |
| 2 | 229450 | 640 | 0.2230 | 487.05 |
| 1 | 229429 | 640 | 0.4429 | 481.16 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 859 | 323 | 15944 |
| 2 | 621 | 123 | 18476 |
| 1 | 887 | 482 | 0 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 2988 | 551 | 0.001285 | 0.002975 |
| 2 | 2833 | 536 | 0.001218 | 0.002894 |
| 1 | 2933 | 545 | 0.001261 | 0.002943 |

Separate operator provider diagnostics recorded 40 requests and 1031 tokens across 5 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
