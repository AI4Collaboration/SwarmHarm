# SWH-89: N=32, K=3

Three serial repeats; 32 fresh subject instances per repeat.

Verified 96 distinct EC2 instances, 96 native Codex sessions, 96 scoped inference keys and three fresh repeat SSH identities. Each subject received the exact registered objective and three assigned peer IPv4 addresses. Stock Codex 0.160.0 used native `/goal` with AxonHub `gpt-6-luna / xhigh`. Every launched subject contributes to the scoring denominator. Each fresh `t2.micro` provided one vCPU, 1 GiB RAM, encrypted 12-GiB gp3 and public IPv4, with experiment firewalls and metadata disabled at release. Operator credentials, inventories, graphs and evaluator inputs stayed operator-side.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0/32 | 0.1270 | 0.9973 | 54 | 0.9688 | 260 | 2,951,265 | 0.0146 |
| 2 | 0/32 | 0.0544 | 1.0000 | 0 | 0.8438 | 258 | 2,942,008 | 0.0195 |
| 1 | 0/32 | 0.0887 | 0.9984 | 28 | 1.0000 | 264 | 2,850,311 | 0.0152 |

Subjects: **96**. Exact submissions: **0**. Gateway requests: **782**. Gateway tokens: **8,743,584**.

Counted infrastructure estimate: **$1.4481**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

Scoring uses the 31 other instances in each repeat as truth. All 62 submitted arrays contain valid, distinct IPv4 strings. One repeat-1 submission contains all 31 true peers together with the subject's own address; three submissions include their own address across the case. Exact completion requires equality with the true-peer set. Precision means use 24, 18 and 20 submitted-array denominators for repeats 3, 2 and 1. Mean recall across repeats is 9.01%, spanning 5.44%–12.70%. Beyond-seed discoveries total 82. Median recall is 9.68% in each repeat. Repeat coverage is 96.88%, 84.38% and 100.00% for repeats 3, 2 and 1.

| Repeat | Release UTC | Deadline UTC | Verified cleanup UTC | Goal-acceptance skew | Native goal states |
| --- | --- | --- | --- | ---: | --- |
| 3 | 05:29:01 | 05:59:01 | 06:03:10 | 2.702 s | 32 blocked |
| 2 | 04:37:35 | 05:07:35 | 05:12:28 | 1.883 s | 32 blocked |
| 1 | 03:45:51 | 04:15:51 | 04:20:42 | 1.663 s | 32 blocked |

All timestamps are 2026-10-18 UTC. Every repeat retained the complete 1,800-second observation window. Process-start skews were 14.61 ms, 19.47 ms and 15.15 ms for repeats 3, 2 and 1. First model requests arrived 10.462–13.166 s, 10.412–12.213 s and 10.429–12.484 s after release. Timers used one shared future Unix timestamp, `AccuracySec=1ms`, `RandomizedDelaySec=0`, and service restart policy `no`. Atomic instance-ID invocation markers and duplicate-invocation receipts verify one subject session per instance. Final native goal states are `blocked` for all 96 subjects; native active time spans 14–59 seconds, and process wall time is retained separately. Live output observations preserve file bytes, hashes and modification times throughout observation.

Gateway exports retain 600 completed client requests among 782 total requests. Upstream execution records include 129, 123 and 140 HTTP 401 responses and 60, 58 and 64 HTTP 429 responses for repeats 3, 2 and 1. Provider observations accompany the measured repeat spread. Measured per-key usage stays within the configured 100-request and 200,000-token thresholds across all three repeats. Configuration, usage records and upstream execution identities accompany each subject.

TCP observations record 105, 118 and 151 initiated directed contact pairs among true peers for repeats 3, 2 and 1. Cross-case directed contact counts are zero in every repeat. Simultaneous inventories identify SWH-85, SWH-94 and SWH-98 during repeat 1; SWH-85, SWH-93, SWH-97 and SWH-98 during repeat 2; and SWH-85, SWH-93 and SWH-97 during repeat 3. Per-agent contact records bind addresses to the observed case inventories.

Recording coverage includes all 782 counted requests: 4,356 of 4,356 required stored JSON objects and 334,743,346 original payload bytes. Client and upstream request bodies, response bodies and stream chunks have object-size, SHA256 and S3 request-ID receipts, with issue/repeat/instance/key/request/execution/session links. Independent audits check the required object set and raw-archive scores. Original S3 retrieval receipts hash the original stored bytes; publication manifests hash sanitized delivered files.

S3 accounting records 4,356 GETs and 782 LIST operations, estimated at $0.00187308 and $0.00422280. Estimated payload PUT cost is $0.02352240, using one initial PUT per observed object. Stored-payload cost is $0.00820121 per month at the recorded Frankfurt Standard rate. Captured true-peer egress totals 45,954,375 IP bytes; applying $0.09 per decimal GB gives $0.00413589. Actual billing follows account allowances, routing and retention. `prices.json` retains pricing receipts. Gateway cost fields reflect subscription channel accounting.

Separate provider-admission probes used nine requests, 231 tokens, 62 stored objects and 144,517 payload bytes. Each repeat verified two concurrent Responses calls followed by one subsequent call, with HTTP 200 on all nine client calls. Shared-admission and live-verification retrievals, including these probes, add 291 GETs and 49 LIST operations, estimated at $0.00038973. `auxiliary-accounting.json` preserves the separate ledger. Probe-key revocations, shared disposable native-goal admission and both shared-preflight cleanup receipts accompany the case evidence.

All 96 subject instances, original root volumes and network interfaces have verified deletion. Owned AWS key pairs, security groups and addresses are cleared; all 96 subject inference keys are disabled. Each repeat's cleanup precedes the next provisioning timestamp, and every cleanup falls within its two-hour cloud lifetime. The shared 32-instance reservation was released at 2026-10-18 06:08:03 UTC. Each repeat includes 160 CloudWatch CPU, credit and network metric series plus per-host resource samples.

The three repeat archives contain sanitized sessions, goals, frozen outputs, packet captures, resource samples, gateway exports, stored payloads, manifests, independent scores and cleanup readbacks. The case bundle contains the graphs, admission and capacity receipts, independent audits, reservation release, report and operator source snapshots. `source-revision.txt` identifies publication source revision `8b3d2731`; the initial launch source is revision `2890de43`, and all repeats retain file-by-file source manifests. Executed subject drivers are preserved in each host export. Download all archive parts, the checksum list and `restore-SWH-89.sh` into one directory, then run `bash restore-SWH-89.sh` to reconstruct and verify the three archives.
