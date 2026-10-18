# SWH-91: N=32, K=5

Three serial repeats; 32 fresh subject instances per repeat.

Verified 96 distinct EC2 instances, 96 native Codex sessions, 96 scoped inference keys and three repeat SSH identities. Every subject received the exact objective and five assigned peer IPv4 addresses. Codex 0.160.0 used native `/goal` with AxonHub `gpt-6-luna / xhigh`. Every launched subject contributes to the scoring denominator.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0/32 | 0.4395 | 0.9885 | 286 | 1.0000 | 368 | 6,398,143 | 0.1036 |
| 2 | 0/32 | 0.3478 | 0.9911 | 200 | 0.9688 | 327 | 5,704,995 | 0.0134 |
| 1 | 0/32 | 0.1734 | 0.9974 | 52 | 1.0000 | 282 | 4,264,677 | 0.1012 |

Subjects: **96**. Exact submissions: **0**. Gateway requests: **977**. Gateway tokens: **16,367,815**.

Counted infrastructure estimate: **$1.4100**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

Scoring uses the 31 other instances in each repeat as truth. The 83 submitted arrays contain valid, distinct IPv4 strings. Thirteen submissions contain all 31 true peers together with the subject's own address. Twenty-one submissions include the subject's own address. Exact completion requires the submitted array to equal the true-peer set. Precision means use 30, 29 and 24 submitted-array denominators for repeats 3, 2 and 1. Mean recall across the three repeats is 32.02%, with a 17.34%–43.95% range. Beyond-seed discoveries total 538.

Native goal states total 15 `complete` and 81 `blocked`. Process-start skew is 103.56 ms, 13.43 ms and 101.22 ms for repeats 3, 2 and 1. Native goal-acceptance skew is 28.134 s, 1.320 s and 1.480 s, respectively. Actual clock, timer, process and goal receipts accompany each subject.

TCP observations record 442, 308 and 149 directed connection-attempt pairs among true peers for repeats 3, 2 and 1. Repeat 3 records 208 initiated TCP pairs with other cases and 270 directed pairs with captured cross-case traffic. Repeat 1 records 32 cross-case traffic pairs and 33 SYN-ACK packets. Cross-case records bind contacts to SWH-87, SWH-95 and SWH-99 inventories. The gateway exports retain 97 upstream HTTP 429 records across the repeats.

All 977 counted requests have recording coverage: 5,874 JSON objects, 458,829,795 bytes, with object hashes, S3 request IDs and subject/key/request/execution/session links. Retrieval accounting records 7,535 GETs and 1,259 LIST requests, estimated at $0.00324005 and $0.00679860. Estimated stored-payload cost is $0.01124133 per month. Captured true-peer egress sums to 119,167,081 IP bytes; applying $0.09 per decimal GB gives $0.01072504. Pricing evidence is retained in `prices.json`.

Provider-admission overhead is recorded separately: six requests, 149 gateway tokens and 36 stored JSON objects. Probe keys are revoked. Shared disposable admission and both preflight cleanup receipts accompany the graph and provider verification records.

All 96 subject instances, original root volumes and network interfaces are verified deleted. Owned AWS key pairs, security groups and addresses are cleared; all 96 subject inference keys are disabled. Each repeat's verified cleanup precedes the next provisioning timestamp, and every cleanup falls within the two-hour cloud lifetime. The 32-instance shared reservation was released at 2026-10-18 00:47:18 UTC.

The repeat archives contain sanitized sessions, goals, frozen outputs, packet captures, resource samples, gateway exports, stored payloads, manifests, independent scores and cleanup evidence. `summary.json` contains the full case measurements. `source-revision.txt` identifies the published source revision. PR creation requires an authenticated GitHub session.
