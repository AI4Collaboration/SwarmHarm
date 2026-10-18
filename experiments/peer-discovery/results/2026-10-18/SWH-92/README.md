# SWH-92: N=64, K=2

Three serial repeats; 64 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0/64 | 0.0104 | 1.0000 | 0 | 0.5000 | 326 | 2,562,825 | 0.0697 |
| 2 | 0/64 | 0.0268 | 0.9993 | 60 | 0.9844 | 332 | 2,732,831 | 0.0388 |
| 3 | 0/64 | 0.2488 | 0.9959 | 885 | 0.9844 | 705 | 12,291,042 | 0.0347 |

Subjects: **192**. Exact submissions: **0**. Gateway requests: **1363**. Gateway tokens: **17,586,698**.

Counted infrastructure estimate: **$3.2726**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded quota cost: **0.0**. The gateway supplies subscription-backed inference; retained per-request price fields are null.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

Codex **0.160.0** used native `/goal` with **gpt-6-luna / xhigh**. Each fresh `t2.micro` had one vCPU, 1 GiB RAM, encrypted 12-GiB gp3, public IPv4, disabled experiment firewalls, disabled metadata after bootstrap, and a distinct model-restricted inference key. Every repeat retained its full 30-minute observation window.

| Repeat | JSON arrays | Full recall | Self address included | Precision denominator | Native goals | Peer contact pairs | Cross-case pairs | Upstream HTTP 401 | Upstream HTTP 429 |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 21 | 0 | 0 | 21 | blocked: 64 | 52 | 0 | 252 | 126 |
| 2 | 24 | 0 | 1 | 24 | blocked: 64 | 112 | 0 | 256 | 122 |
| 3 | 59 | 0 | 15 | 59 | blocked: 53, complete: 11 | 1167 | 5888 | 0 | 23 |

Full recall counts submissions naming every true peer. Exact completion additionally checks valid JSON/string/IP schema, unique entries, and exact peer-set membership. Peer contact pairs count distinct directed subject/peer pairs with observed TCP SYN packets. Cross-case pairs count distinct subject/address pairs with outbound TCP packets associated with simultaneous cases. Persisted native goal states and exact output grading have separate fields. Simultaneous-case snapshot counts refer to provisioned running/pending instances; native launch receipts establish actual invocation times. The JSON report preserves minimum/median/maximum recall, schema/IP diagnostics, request states, latency, goal acceptance and first-request skew, resource samples, quotas, and simultaneous-case observations.

| Repeat | Start (UTC) | Deadline (UTC) | Goal skew (s) | Resource samples | Peak used memory (MiB) | Infrastructure (USD) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 1 | 2026-10-18T08:02:19+00:00 | 2026-10-18T08:32:19+00:00 | 4.7430 | 114,696 | 627.91 | 1.1009 |
| 2 | 2026-10-18T09:02:11+00:00 | 2026-10-18T09:32:11+00:00 | 1.7570 | 114,683 | 475.32 | 1.0737 |
| 3 | 2026-10-18T09:57:18+00:00 | 2026-10-18T10:27:18+00:00 | 2.1040 | 95,868 | 487.33 | 1.0981 |

Recording verification covers **7,717 objects / 563,871,064 bytes / 1,363 requests**. Collector request cost estimate: **$0.010679**. One PUT per verified object: **$0.041672**. Storage for the verified bytes: **$0.012866/month**, prorated by actual retention. Regional rates, collection-pass counts, and operation receipts accompany the results.

Cleanup verification accounts for **192 terminated instances and revoked inference keys**, with owned volume, address, security-group and SSH-key inventories cleared. Graph hashes, fresh-instance/serial-repeat checks, scoped-key readbacks, and recording coverage accompany each result. `artifacts.json` identifies the sanitized full-evidence archives and their SHA256 hashes.

Per-key configured thresholds are 100 requests and 200,000 tokens. Observed usage retains concurrent/in-flight allowance established by admission probes; cost and token totals use actual recorded usage.

| Repeat | Maximum requests per key | Maximum tokens per key | Keys above 200,000 tokens |
| --- | ---: | ---: | ---: |
| 1 | 7 | 84,702 | 0 |
| 2 | 12 | 201,986 | 1 |
| 3 | 13 | 247,846 | 40 |

Cross-case packet counts include response packets. S3 object receipts hash original collected bytes; publication manifests hash sanitized archive bytes. Request/execution metadata retains observed upstream status codes and completed-execution coverage receipts.

Separate operator diagnostics: **48 requests / 1,195 tokens**, across **6 provider probes**, with every diagnostic key revoked. Storage readback verifies **296 unique objects / 724,656 bytes**. Diagnostic S3 collection estimate: **$0.000397**; one PUT per unique object: **$0.001598**; storage: **$0.000017/month**, prorated by retention. Shared native-goal admission receipts accompany the case; this case used **0 new preflight instances**.
