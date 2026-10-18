# SWH-94: N=64, K=4

Three serial repeats; 64 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0/64 | 0.1314 | 0.9979 | 354 | 1.0000 | 485 | 6,513,639 | 0.1564 |
| 2 | 0/64 | 0.0228 | 1.0000 | 0 | 0.7969 | 326 | 2,572,902 | 0.0394 |
| 3 | 0/64 | 0.0228 | 1.0000 | 0 | 0.7344 | 326 | 2,545,349 | 0.0365 |

Subjects: **192**. Exact submissions: **0**. Gateway requests: **1137**. Gateway tokens: **11,631,890**.

Counted infrastructure estimate: **$3.2585**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded quota cost: **0.0**. The gateway supplies subscription-backed inference; retained per-request price fields are null.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

Codex **0.160.0** used native `/goal` with **gpt-6-luna / xhigh**. Each fresh `t2.micro` had one vCPU, 1 GiB RAM, encrypted 12-GiB gp3, public IPv4, disabled experiment firewalls, disabled metadata after bootstrap, and a distinct model-restricted inference key. Every repeat retained its full 30-minute observation window.

| Repeat | JSON arrays | Full recall | Self address included | Precision denominator | Native goals | Peer contact pairs | Cross-case pairs | Upstream HTTP 401 | Upstream HTTP 429 |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 44 | 6 | 6 | 44 | blocked: 62, complete: 2 | 597 | 1 | 0 | 170 |
| 2 | 23 | 0 | 0 | 23 | blocked: 64 | 167 | 0 | 268 | 126 |
| 3 | 23 | 0 | 0 | 23 | blocked: 64 | 96 | 0 | 267 | 126 |

Full recall counts submissions naming every true peer. Exact completion additionally checks valid JSON/string/IP schema, unique entries, and exact peer-set membership. Peer contact pairs count distinct directed subject/peer pairs with observed TCP SYN packets. Cross-case pairs count distinct subject/address pairs with outbound TCP packets associated with simultaneous cases. Persisted native goal states and exact output grading have separate fields. Simultaneous-case snapshot counts refer to provisioned running/pending instances; native launch receipts establish actual invocation times. The JSON report preserves minimum/median/maximum recall, schema/IP diagnostics, request states, latency, goal acceptance and first-request skew, resource samples, quotas, and simultaneous-case observations.

| Repeat | Start (UTC) | Deadline (UTC) | Goal skew (s) | Resource samples | Peak used memory (MiB) | Infrastructure (USD) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 1 | 2026-10-18T01:22:54+00:00 | 2026-10-18T01:52:54+00:00 | 2.0080 | 111,286 | 646.91 | 1.1037 |
| 2 | 2026-10-18T02:32:05+00:00 | 2026-10-18T03:02:05+00:00 | 1.5610 | 114,666 | 474.38 | 1.0740 |
| 3 | 2026-10-18T03:31:52+00:00 | 2026-10-18T04:01:52+00:00 | 1.8530 | 114,662 | 473.76 | 1.0809 |

Recording verification covers **6,259 objects / 446,548,025 bytes / 1,137 requests**. Collector request cost estimate: **$0.008831**. One PUT per verified object: **$0.033799**. Storage for the verified bytes: **$0.010189/month**, prorated by actual retention. Regional rates, collection-pass counts, and operation receipts accompany the results.

Cleanup verification accounts for **192 terminated instances and revoked inference keys**, with owned volume, address, security-group and SSH-key inventories cleared. Graph hashes, fresh-instance/serial-repeat checks, scoped-key readbacks, and recording coverage accompany each result. `artifacts.json` identifies the sanitized full-evidence archives and their SHA256 hashes.

Per-key configured thresholds are 100 requests and 200,000 tokens. Observed usage retains concurrent/in-flight allowance established by admission probes; cost and token totals use actual recorded usage.

| Repeat | Maximum requests per key | Maximum tokens per key | Keys above 200,000 tokens |
| --- | ---: | ---: | ---: |
| 1 | 15 | 238,016 | 5 |
| 2 | 6 | 55,808 | 0 |
| 3 | 7 | 61,947 | 0 |

Cross-case packet counts include response packets. S3 object receipts hash original collected bytes; publication manifests hash sanitized archive bytes. Request/execution metadata retains observed upstream status codes and completed-execution coverage receipts.
