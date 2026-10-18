# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 1 | 127 | 38.98 | 736 | 326 | 129 |
| 2 | 0 | 128 | 22.99 | 515 | 253 | 130 |
| 1 | 0 | 128 | 22.89 | 523 | 256 | 130 |

| Repeat | Maximum recorded key tokens | Maximum excess over 200,000-token threshold | Maximum excess over 100-request threshold |
| --- | ---: | ---: | ---: |
| 3 | 209263 | 9263 | 0 |
| 2 | 218401 | 18401 | 0 |
| 1 | 25395 | 0 | 0 |

The native-goal records contain one `complete` goal in repeat 3. Independent output scoring records maximum recall of 126/127 peers and one submission containing its own address; exact completion is 0/128 in every repeat.

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.103901 | 21.193000 | 21.435635 |
| 2 | 0.094570 | 11.298000 | 11.301672 |
| 1 | 0.039194 | 4.166000 | 4.160812 |

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 50 | 1 | 0.016794 | 0/128 |
| 2 | 27 | 0 | 0.004983 | 0/128 |
| 1 | 13 | 0 | 0.002399 | 0/128 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 227669 | 640 | 0.3232 | 479.17 |
| 2 | 229420 | 640 | 0.5708 | 479.63 |
| 1 | 229448 | 640 | 0.8137 | 508.85 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 237 | 0 | 0 |
| 2 | 143 | 0 | 0 |
| 1 | 15 | 0 | 0 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 3788 | 726 | 0.001629 | 0.003920 |
| 2 | 2287 | 464 | 0.000983 | 0.002506 |
| 1 | 2061 | 427 | 0.000886 | 0.002306 |

Separate operator provider diagnostics recorded 48 requests and 1228 tokens across 6 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
