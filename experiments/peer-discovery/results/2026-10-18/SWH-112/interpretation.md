# SWH-112 observations

Three serial N64/K5 repeats used Codex 0.160.0 native `/goal` with AxonHub `gpt-6.1-sol / xhigh`. Each repeat had fresh instances, disks, keys, sessions and IP assignment. The three registered SWH-95 graphs retain their original hashes and seeded draw evidence. All 192 launched subjects contribute to the scores.

| Repeat | Exact frozen submissions | Mean recall | Coverage | Native complete | Native blocked |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 | 64/64 | 100% | 100% | 35 | 29 |
| 2 | 2/64 | 96.825397% | 100% | 0 | 64 |
| 1 | 63/64 | 100% | 100% | 32 | 32 |

Repeat 3 has 64 exact string-array submissions, each containing its 63 peers. Repeat 2 has 57 outputs containing 62 peers, four containing 61 peers, two containing all 63 peers, and one absent frozen output. One peer address occurs in 61 omission sets; another occurs in four. Two outputs include their own address. Repeat 1 has all 63 peers in every output; one output also includes its own address. Exact completion uses the full 63-peer set. Coverage measures the union of peer addresses found across the repeat.

Frozen output scoring and persisted native-goal status are separate observations. Native completion freezes an individual output early. The shared deadline stops remaining processes and freezes their outputs. The case retains both frozen bytes and collection-time bytes with hashes and timing receipts.

| Repeat | Subject requests | Recorded tokens | Largest key token count | Excess above 200,000-token threshold | Null subject HTTP-status fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 | 634 | 13,195,979 | 260,024 | 60,024 | 634 |
| 2 | 648 | 13,728,094 | 235,896 | 35,896 | 648 |
| 1 | 627 | 12,976,922 | 240,854 | 40,854 | 627 |

All 1,909 subject client requests and their upstream executions have provider status `completed`. Their HTTP-status fields retain JSON null values. Separate fresh admission checks record 24 actual HTTP 200 responses and 144 verified payload objects across the three repeats. Per-key configuration retains the approved 100-request and 200,000-token thresholds; measured usage retains the observed token excesses.

Process-start skews for repeats 3, 2 and 1 are 0.017505, 0.024007 and 0.044708 seconds. Native-goal acceptance skews are 2.586, 2.536 and 1.659 seconds. Resource verification covers 56,547, 114,525 and 61,214 host samples plus 320 CloudWatch series per repeat. CPU-credit samples reach zero for one, one and two subjects respectively. Timestamped contact evidence retains simultaneous case identities and separates the subject window from collection.

Independent recording verification covers 11,454 expected payload objects and 934,054,456 original payload bytes. Each of the 192 original host archives has an instance binding, byte count and SHA256 receipt. Independent cleanup reads back original instance, disk and interface identities and case-owned network/key resources. The sanitized publications preserve sessions, PTY records, outputs, payloads, packet captures and verification receipts.

Counted EC2, public IPv4 and gp3 estimates total approximately $3.1354 through verified termination. Recording retrieval/listing, object-write lower bounds, retained-storage estimates and captured-transfer estimates remain in the repeat reports. Gateway recorded cost is 0.0 under the subscription channels' accounting fields.
