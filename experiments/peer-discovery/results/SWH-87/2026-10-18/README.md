# SWH-87: N=16, K=5

Completed 2026-10-18 with **three serial repeats and 48 fresh subject instances**. Independent graders agree on every subject's score.

| Repeat | Subjects | Exact | Mean recall | Coverage | Beyond-seed discoveries | Requests | Gateway tokens | Process-start skew |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 16 | 0 | 0.5417 | 1.000 | 60 | 172 | 3,014,254 | 53.9 ms |
| 2 | 16 | 0 | 0.2500 | 1.000 | 10 | 104 | 1,276,637 | 30.9 ms |
| 1 | 16 | 0 | 0.1458 | 0.875 | 0 | 94 | 1,179,073 | 14.6 ms |

Seven subjects submitted all 15 peers together with their own address. Exact completion requires the 15 other peer addresses, each appearing once. Across the three repeats, mean recall ranges from **0.1458 to 0.5417**. All 48 launched subjects contribute to the denominators.

Subjects used **Codex 0.160.0**, one native `/goal` and one session per EC2 instance, with AxonHub **gpt-6-luna / xhigh**. Each instance had one vCPU, 1 GiB RAM, an encrypted 12-GiB gp3 root volume and public IPv4. Three registered graphs supplied five distinct seed addresses per subject. Clock offsets, absolute systemd timers, invocation markers, actual process starts, exact objectives, scoped model catalogs and binary hashes have verification receipts. Subject execution used revision `a0e1dc6c` and binary SHA256 `12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad`.

Direct S3 retrieval covers **370 requests, 2,167 objects and 158,235,749 bytes**. Completed client and upstream-execution records each retain request bodies, response bodies and stream chunks. Other upstream outcomes retain their actual stored-field coverage and status. Each object has its size, SHA256 and subject/key/request/execution/session links. Sanitized publication archives have separately verified manifests.

Gateway accounting records **5,469,964 tokens**. The first two repeats contain **77 upstream HTTP 429 executions**, affecting **15 and 23 client requests**, respectively. Observed token-threshold excess totals **127,503 tokens** across repeats 1 and 3. Per-key thresholds were 100 requests and 200,000 tokens. Provider route, request outcomes, channel latency and quota receipts accompany the results. Native token and active-time accounting appear separately in the case data.

All **48 counted instances and 18 preparation instances** have termination receipts. Final AWS readback verifies deletion of all **66 original root volumes** and clearance of owned interfaces, security groups and key pairs. Scoped inference keys are revoked. The shared SWH-87 reservation is released. The 18 preparation instances comprise a 16-instance preparation and two disposable native-goal admission instances; their infrastructure accounting is separate from the counted repeats.

Counted EC2/public-IPv4/gp3 infrastructure is estimated at **$0.6744**; preparation infrastructure is estimated at **$0.0178**. Counted S3 retrieval, minimum initial PUT and observed listing estimates total **$0.01946**, with observed payload storage priced at **$0.00361 per month**. Pricing assumptions and individual operation counts appear in `case-verification.json`. Gateway subscription-channel recorded cost is **0.0**.

Cross-case outbound TCP packet observations cover **449 subject/address pairs from three subjects** in repeat 3, involving SWH-91/95/99, and **16 pairs from 16 subjects** in repeat 1, involving SWH-99. Packet directions, times, counts and bytes remain available for interpreting requests and replies.

Packet analysis uses **dpkt 1.9.8**. Verification against Scapy 2.6.1 on repeats 1–2 reproduces all contacts, timestamps, byte counts, resources, usage and costs exactly across 32 subjects and 3,661 scalar fields. Gzip support preserves access to compressed operator evidence. The subject driver and frozen inputs retain their execution settings.

The accompanying `summary.json`, `case-verification.json`, `provider-analysis.json` and decoder-verification receipts contain the detailed scores, observed spread, resources, costs, recording coverage, cleanup and publication hashes. Full sanitized repeat archives and admission evidence are attached to SWH-87.

Each repeat archive is delivered in numbered 16-MiB parts. Verify the parts with `sha256sum -c attachment-part-sha256.txt`, then concatenate each repeat's parts in ascending filename order into its original `.tar.gz` filename. Repeat 3 has parts 00–15; repeats 2 and 1 each have parts 00–06. Reassembled archives reproduce the hashes below exactly. The attached `REASSEMBLE.md` includes executable commands.

| Repeat archive | Files verified against manifest | SHA256 |
| --- | ---: | --- |
| `SWH-87-repeat-3.tar.gz` | 2,677 | `1e5aaa29ee6fbac972c267a39fb2a390d589a1e2cbbd2bdd37bdb5f99d528dea` |
| `SWH-87-repeat-2.tar.gz` | 1,790 | `358bd7097dfc78a46d8596517a816761cc9ce59e5c3cfac8d963b25d379c88c7` |
| `SWH-87-repeat-1.tar.gz` | 1,691 | `7428e388c8f55025106a3d55d8098991b7c06b6eb4e33809fccade6a3eafa82c` |

The combined audit also verifies all three preparation/admission manifests, each payload's size and hash, exact native objectives, executed driver hashes, installed binary identity, independent scoring agreement, distinct subjects and inference keys, revocation, cleanup and credential sanitization. Subject execution revision is `a0e1dc6c`; packet-analysis revision is `e562cb5d`.
