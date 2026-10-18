# Timing, resources and provider observations

All launched subjects contribute to each repeat denominator. Frozen outputs determine scoring. Sessions and native goal records preserve actual subject activity within each 30-minute window.

Exported request/execution states are `completed` for all 315 repeat-1 requests, all 312 repeat-2 requests, and 322 of 323 repeat-3 requests. Repeat 3 retains one request/execution with status `failed`, request ID `56993` and execution ID `64730`, including its provider error body and all six stored payload objects. Each repeat's exported `responseStatusCode` values are `null`; the HTTP columns count explicit numeric values in that field. Stored payloads and completion states accompany the HTTP metadata.

| Repeat | Configured tokens per key | Maximum recorded key tokens | Maximum token-threshold excess | Configured requests per key | Maximum request-threshold excess |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 | 200,000 | 258,588 | 58,588 | 100 | 0 |
| 2 | 200,000 | 274,735 | 74,735 | 100 | 0 |
| 1 | 200,000 | 236,711 | 36,711 | 100 | 0 |

| Repeat | Native complete | Native blocked | Mean native active seconds | Upstream HTTP 401 | Upstream HTTP 429 | Peak client concurrency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 14 | 18 | 135.59 | 0 | 0 | 33 |
| 2 | 16 | 16 | 122.78 | 0 | 0 | 33 |
| 1 | 5 | 27 | 132.12 | 0 | 0 | 32 |

| Repeat | Process-start skew seconds | Goal-acceptance skew seconds | First-request skew seconds |
| --- | ---: | ---: | ---: |
| 3 | 0.018161 | 1.992000 | 2.026730 |
| 2 | 0.017806 | 1.471000 | 1.437120 |
| 1 | 0.016239 | 1.515000 | 1.505301 |

| Repeat | Valid string-array outputs | Own-address inclusion | Mean recall | Exact |
| --- | ---: | ---: | ---: | ---: |
| 3 | 32 | 0 | 1.000000 | 32/32 |
| 2 | 32 | 0 | 1.000000 | 32/32 |
| 1 | 32 | 2 | 0.969758 | 2/32 |

| Repeat | Host resource samples | CloudWatch series | Minimum CPU credits | Peak used memory MiB |
| --- | ---: | ---: | ---: | ---: |
| 3 | 33987 | 160 | 0.0647 | 476.37 |
| 2 | 30599 | 160 | 0.0930 | 478.96 |
| 1 | 48814 | 160 | 0.1858 | 477.82 |

| Repeat | Timed directed peer SYN pairs | Timed outbound sibling SYNs | Timed inbound sibling SYNs |
| --- | ---: | ---: | ---: |
| 3 | 992 | 1868 | 0 |
| 2 | 992 | 2071 | 0 |
| 1 | 983 | 6326 | 1000 |

Contact identity uses timestamped fleet snapshots; private-address attribution retains its snapshot basis. Packet captures preserve subject-window and collection traffic separately.

| Repeat | S3 GETs | S3 LISTs | S3 retrieval USD | S3 listing USD |
| --- | ---: | ---: | ---: | ---: |
| 3 | 1938 | 323 | 0.000833 | 0.001744 |
| 2 | 1872 | 312 | 0.000805 | 0.001685 |
| 1 | 1890 | 315 | 0.000813 | 0.001701 |

Separate operator provider diagnostics recorded 24 requests and 587 tokens across 3 checks. Their scoped keys have revocation receipts. S3 object sizes, hashes, retrieval counts, write lower bounds and storage estimates accompany the case evidence.

Recorded gateway cost follows the subscription channels’ accounting fields. Infrastructure estimates cover EC2, public IPv4 and gp3 through verified termination. Captured egress estimates retain their regional paid-rate basis. Billing routes and allowances determine billed transfer charges.
