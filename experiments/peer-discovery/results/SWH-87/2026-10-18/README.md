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

Packet analysis uses **dpkt 1.9.8**. Verification against Scapy 2.6.1 on both completed repeats reproduces all contacts, timestamps, byte counts, resources, usage and costs exactly across 32 subjects. Gzip support preserves access to compressed operator evidence. The subject driver and frozen inputs retain their execution settings.

The accompanying `summary.json`, `case-verification.json`, `provider-analysis.json` and decoder-verification receipts contain the detailed scores, observed spread, resources, costs, recording coverage, cleanup and publication hashes. Full sanitized repeat archives and admission evidence are attached to SWH-87.
