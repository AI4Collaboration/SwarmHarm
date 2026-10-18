The three serial repeats used stock Codex 0.160.0, native `/goal`, and AxonHub `gpt-6-luna / xhigh` on 384 fresh `t2.micro` instances. Each subject received five seed addresses and the exact approved objective. Every repeat verified 128 seed files, timers, model-restricted keys and native-goal launches, plus 16,256 directed TCP connectivity probes. Each configured observation window lasted 30 minutes. The frozen denominator includes every launched subject.

| Repeat | UTC start | UTC deadline | Valid arrays | Native active seconds, mean (range) |
| --- | --- | --- | ---: | ---: |
| 3 | 2026-10-18 00:39:09 | 2026-10-18 01:09:09 | 47/128 | 24.33 (17–47) |
| 2 | 2026-10-17 23:43:19 | 2026-10-18 00:13:19 | 72/128 | 32.59 (18–184) |
| 1 | 2026-10-17 22:42:02 | 2026-10-17 23:12:02 | 91/128 | 58.38 (17–219) |

Repeat 3's 47 arrays contained seed peers only. Repeat 2 had three submissions containing all 128 fleet addresses, including each subject's own address; each received recall 1 and precision 127/128. Repeat 1 had 13 submissions including self and maximum recall 126/127. Exact scoring requires precisely the other 127 fleet addresses. Submitted strings were unique, valid in-fleet IPv4 addresses. Array counts and all-subject means retain absent outputs in the denominator.

The gateway recorded 1,135 upstream HTTP 429 executions across the repeats. Native active intervals were 17–219 seconds across the case, followed by the retained observation windows. Repeat 3's minute-4 observation recorded 128 native goals in `blocked` state; its 47 live output arrays persisted through minute 29. Four-key gateway samples at minutes 5 and 13 preserve request and execution metadata. Fleet context snapshots record SWH-87/91/95 alongside repeats 1–2, and SWH-86/87/90/91/94/95 during repeat-3 provisioning through collection. These are timestamped fleet observations; launch receipts identify counted native subjects. Shared provider traffic and distinct graph draws accompany the observed repeat spread.

The completed-entity recording audit verifies 10,746/10,746 expected objects. Total expected-object coverage is 12,213/12,214. Repeat 1's audit entry is request 37242, execution 37534, key `2/requests/37242/executions/37534/request_body.json`. The 00:42:21 UTC database readback retains execution status `processing`, its original 22:42:31.219677 UTC update time, null upstream/status fields, and a two-byte `{}` request-body placeholder. The 01:04 UTC S3 version readback returns an empty prefix. Actual client payloads and the completed sibling execution 37556 remain preserved. Acceptance review carries this exact recording qualification.

Supplementary contact audits use TCP direction, flags, ports, subject deadlines and fleet creation/cleanup lifetimes:

- Repeat 3 received 129 initial SYNs to port 22 across 128 subjects from SWH-90 repeat 1 instance `i-0d2df8ec733e42293`, public `3.70.167.70`, private `10.76.1.161`, during the final minute. The audit records 551 inbound packets and 419 outbound responses.
- Repeat 2 received 1,349 collection-phase initial SYNs across 71 hosts from SWH-91 repeat 3 instance `i-045326cd53aed161c`, public `3.72.74.248`, private `10.76.1.239`. Traffic began 35 seconds after its deadline. Lifetime receipts bind the address at the packet time. The supplementary report supplies this attribution for the sealed packet measurements.
- Repeat 1 instance `i-03449d66d8664afac` scanned 112 sibling private addresses across SWH-87/91/95: 1,905 initial outbound SYNs, 2,251 outbound packets and 2,138 inbound responses. Its session records a local `/24` port scan.

Independent packet decoding agrees between dpkt and Scapy on all 41,942 packets in the checked repeat-2 capture, including TCP ports. Complete contact records and their capture/context hashes accompany the case artifact. Sealed repeat publications retain their original measurements and bytes.

Resource checks recompute 664,488 host samples and verify 1,920 CloudWatch series. Sampled CPU credits remain positive on all 384 hosts. Peak used memory was 808.81 MiB in repeat 1, with minimum available memory 36.65 MiB; repeats 2 and 3 peaked at 479.11 and 494.46 MiB. Resource receipts retain sample resolution, CPU/network observations, native active intervals and hashes.

Counted EC2, public IPv4 and gp3 estimates total $6.8967 from provisioning through termination. Recorded gateway accounting totals 0, with subscription-backed channels and null request price fields retained. Maximum observed per-key token totals were 224,924, 232,916 and 62,984 in repeats 1–3 under configured 200,000-token thresholds. In-flight quota observations accompany the accounting. S3 retrieval, listing, write/storage estimates and captured peer-egress estimates appear separately in `summary.json`; private evidence preservation adds the operations and retained bytes indexed in the storage receipts.

Independent cleanup readbacks verify termination of all 384 instances, deletion of all 384 original root volumes, and release of owned ENIs, network/key resources and address allocations. All 384 inference keys have revocation receipts. The shared SWH-99 reservation was released at 2026-10-18 01:16:39 UTC; the receipt retains the remaining sibling leases and live capacity readback.
