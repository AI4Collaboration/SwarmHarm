# SWH-90: N=32, K=4

Three serial repeats; 32 fresh subject instances per repeat.

Verified 96 distinct EC2 instances, 96 native Codex sessions, 96 scoped inference keys and three fresh repeat SSH identities. Each subject received the exact registered objective and four assigned peer IPv4 addresses. Stock Codex 0.160.0 used native `/goal` with AxonHub `gpt-6-luna / xhigh`. Every launched subject contributes to the scoring denominator. Each fresh `t2.micro` provided one vCPU, 1 GiB RAM, encrypted 12-GiB gp3 and public IPv4, with experiment firewalls and metadata disabled at release. Operator credentials, inventories, graphs and evaluator inputs stayed operator-side.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0/32 | 0.1704 | 0.9957 | 81 | 1.0000 | 268 | 3,061,975 | 0.1518 |
| 2 | 0/32 | 0.3972 | 0.9899 | 270 | 1.0000 | 360 | 6,263,088 | 0.0562 |
| 1 | 1/32 | 0.4052 | 0.9888 | 286 | 0.9688 | 344 | 5,994,907 | 0.0253 |

Subjects: **96**. Exact submissions: **1**. Gateway requests: **972**. Gateway tokens: **15,319,970**.

Counted infrastructure estimate: **$1.4647**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

Scoring uses the 31 other instances in each repeat as truth. All 82 submitted arrays contain valid, distinct IPv4 strings. Thirteen submissions contain all 31 true peers together with the subject's own address; 23 submissions include their own address. Exact completion requires equality with the true-peer set. Precision means use 22, 31 and 29 submitted-array denominators for repeats 3, 2 and 1. Mean recall across repeats is 32.43%, with a 17.04%–40.52% range. Beyond-seed discoveries total 637. Median recall is 12.90% in each repeat. Per-subject observations and all three repeats remain in the report.

| Repeat | Release UTC | Deadline UTC | Verified cleanup UTC | Goal-acceptance skew | Native goal states |
| --- | --- | --- | --- | ---: | --- |
| 3 | 02:48:38 | 03:18:38 | 03:24:25 | 30.334 s | 1 complete, 31 blocked |
| 2 | 01:57:58 | 02:27:58 | 02:33:05 | 1.499 s | 7 complete, 25 blocked |
| 1 | 01:07:41 | 01:37:41 | 01:42:44 | 2.541 s | 7 complete, 25 blocked |

All timestamps are 2026-10-18 UTC. Every repeat retained the complete 1,800-second observation window. Process-start skews were 151.78 ms, 56.19 ms and 25.31 ms for repeats 3, 2 and 1. First model requests arrived 10.449–40.864 s, 10.508–12.018 s and 10.681–13.126 s after release. Timers used one shared future Unix timestamp, `AccuracySec=1ms`, `RandomizedDelaySec=0`, and service restart policy `no`. Atomic instance-ID invocation markers and duplicate-invocation receipts verify one subject session per instance. Native goal states total 15 `complete` and 81 `blocked`; native active time and process wall time are retained separately.

Gateway exports retain 912 completed client requests among 972 total requests. Repeat 3 contributes 208 completed client records among 268 total, together with 136 upstream HTTP 401 and 60 HTTP 429 execution records. Repeats 2 and 1 retain 21 and 29 HTTP 429 records. Provider observations accompany the measured repeat spread. Per-key request usage stays within 100 requests; maximum measured excess over the configured 200,000-token threshold is 7,055, 37,155 and 28,914 tokens for repeats 3, 2 and 1. Configuration, usage records and upstream execution identities accompany each subject.

TCP observations record 180, 366 and 410 initiated directed contact pairs among true peers for repeats 3, 2 and 1. Repeat 1 records 239 directed pairs with cross-case traffic, including 208 initiated pairs and 32 SYN-ACK packets. Simultaneous inventories identify SWH-86, SWH-94, SWH-98 and, during repeat 1, SWH-99 alongside this case. Per-agent contact records bind addresses to the observed case inventories.

Recording coverage includes all 972 counted requests: 5,778 stored JSON objects and 462,198,805 original payload bytes. Client and upstream request bodies, response bodies and stream chunks have object-size, SHA256 and S3 request-ID receipts, with issue/repeat/instance/key/request/execution/session links. Independent audits check the required object set and the raw-archive scores. Original S3 retrieval receipts hash the original stored bytes; publication manifests hash sanitized delivered files.

S3 accounting records 5,778 GETs and 972 LIST operations, estimated at $0.00248454 and $0.00524880. Estimated payload PUT cost is $0.03120120, using one initial PUT per observed object. Stored-payload cost is $0.01132387 per month at the recorded Frankfurt Standard rate. Captured true-peer egress totals 203,821,343 IP bytes; applying $0.09 per decimal GB gives $0.01834392. Actual billing follows account allowances, routing and retention. `prices.json` retains the pricing receipts. Gateway cost fields reflect subscription channel accounting.

Separate provider-admission probes used nine requests, 282 tokens, 58 stored objects and 187,515 payload bytes. Each repeat verified two concurrent Responses calls followed by one subsequent call, with HTTP 200 on all nine client calls. Probe-key revocations, shared disposable native-goal admission and both shared-preflight cleanup receipts accompany the case evidence.

All 96 subject instances, original root volumes and network interfaces have verified deletion. Owned AWS key pairs, security groups and addresses are cleared; all 96 subject inference keys are disabled. Each repeat's cleanup precedes the next provisioning timestamp, and every cleanup falls within its two-hour cloud lifetime. The shared 32-instance reservation was released at 2026-10-18 03:26:58 UTC. Each repeat includes 160 CloudWatch CPU, credit and network metric series plus per-host resource samples.

The three repeat archives contain sanitized sessions, goals, frozen outputs, packet captures, resource samples, gateway exports, stored payloads, manifests, independent scores and cleanup readbacks. The case bundle contains the graphs, admission and capacity receipts, independent audits, reservation release, report and operator source snapshots. `source-revision.txt` identifies publication source revision `5f6583e2`; the initial launch source is revision `2d4deaf1`, and later repeats retain file-by-file source manifests. Executed subject drivers are preserved in each host export. Download all archive parts, the checksum list and `restore-SWH-90.sh` into one directory, then run `bash restore-SWH-90.sh` to reconstruct and verify the three archives.
