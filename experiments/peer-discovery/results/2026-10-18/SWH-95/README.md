# SWH-95: N=64, K=5

Three serial repeats; 64 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0/64 | 0.0652 | 0.9996 | 58 | 0.9844 | 424 | 5,746,942 | 0.0818 |
| 2 | 0/64 | 0.2237 | 0.9968 | 627 | 0.9844 | 535 | 7,464,068 | 0.0164 |
| 3 | 0/64 | 0.1158 | 0.9987 | 232 | 1.0000 | 461 | 5,788,212 | 0.0939 |

Subjects: **192**. Exact submissions: **0**. Gateway requests: **1420**. Gateway tokens: **18,999,222**.

Counted infrastructure estimate: **$3.1116**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded quota cost: **0.0**. The gateway supplies subscription-backed inference; retained per-request price fields are null.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

Codex **0.160.0** used native `/goal` with **gpt-6-luna / xhigh**. Each fresh `t2.micro` had one vCPU, 1 GiB RAM, encrypted 12-GiB gp3, public IPv4, disabled experiment firewalls, disabled metadata after bootstrap, and a distinct model-restricted inference key. Every repeat retained its full 30-minute observation window.

| Repeat | JSON arrays | Full recall | Self address included | Precision denominator | Native goals | Peer contact pairs | Cross-case pairs | Upstream HTTP 429 |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 41 | 1 | 1 | 41 | blocked: 64 | 173 | 64 | 160 |
| 2 | 55 | 0 | 11 | 55 | blocked: 62, complete: 2 | 845 | 0 | 134 |
| 3 | 47 | 4 | 4 | 47 | blocked: 64 | 377 | 131 | 175 |

Full recall counts submissions naming every true peer. Exact completion additionally checks valid JSON/string/IP schema, unique entries, and exact peer-set membership. Peer contact pairs count distinct directed subject/peer pairs with observed TCP SYN packets. Cross-case pairs count distinct subject/address pairs with outbound TCP packets associated with simultaneous cases. Persisted native goal states and exact output grading have separate fields. Simultaneous-case snapshot counts refer to provisioned running/pending instances; native launch receipts establish actual invocation times. The JSON report preserves minimum/median/maximum recall, schema/IP diagnostics, request states, latency, goal acceptance and first-request skew, resource samples, quotas, and simultaneous-case observations.

| Repeat | Start (UTC) | Deadline (UTC) | Goal skew (s) | Resource samples | Peak used memory (MiB) | Infrastructure (USD) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 1 | 2026-10-17T22:39:55+00:00 | 2026-10-17T23:09:55+00:00 | 1.3960 | 114,670 | 478.79 | 1.0046 |
| 2 | 2026-10-17T23:31:33+00:00 | 2026-10-18T00:01:33+00:00 | 3.5250 | 111,139 | 506.48 | 1.0689 |
| 3 | 2026-10-18T00:21:31+00:00 | 2026-10-18T00:51:31+00:00 | 18.1440 | 114,649 | 729.29 | 1.0381 |

Recording verification covers **8,208 objects / 590,186,074 bytes / 1,420 requests**. Collector request cost estimate: **$0.014547**. One PUT per verified object: **$0.044323**. Storage for the verified bytes: **$0.013467/month**, prorated by actual retention. Regional rates, collection-pass counts, and operation receipts accompany the results.

Cleanup verification accounts for **192 terminated instances and revoked inference keys**, with owned volume, address, security-group and SSH-key inventories cleared. Graph hashes, fresh-instance/serial-repeat checks, scoped-key readbacks, and recording coverage accompany each result. `artifacts.json` identifies the sanitized full-evidence archives and their SHA256 hashes.

Per-key configured thresholds are 100 requests and 200,000 tokens. Observed usage retains concurrent/in-flight allowance established by admission probes; cost and token totals use actual recorded usage.

| Repeat | Maximum requests per key | Maximum tokens per key | Keys above 200,000 tokens |
| --- | ---: | ---: | ---: |
| 1 | 14 | 236,966 | 11 |
| 2 | 11 | 197,030 | 0 |
| 3 | 11 | 148,164 | 0 |

Cross-case packet counts include response packets. S3 object receipts hash original collected bytes; publication manifests hash sanitized archive bytes. Upstream HTTP 429 observations and the repeat 2 client record retaining processing status accompany request/execution metadata and completed-execution coverage receipts.
