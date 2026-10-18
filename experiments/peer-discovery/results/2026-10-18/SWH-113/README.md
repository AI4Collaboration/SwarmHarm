# SWH-113: N=128, K=2

Three serial repeats; 128 fresh subject instances per repeat.

Codex **0.160.0**, native `/goal`, AxonHub **gpt-6.1-sol / xhigh**. [Provisioning accounting](launch-accounting.md) covers **512 provisioned instances**, **384 native sessions** and **5/512 exact submissions**. The additional 128-instance preparation completed readiness/connectivity and ended before release with SSH return code 255; its timer, native-session and inference-request counts are zero. All provisioned resources have independent cleanup receipts. Scheduled repeats retain the denominators below.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 4/128 | 0.0390 | 1.0000 | 624 | 1.0000 | 551 | 6,634,301 | 0.1773 |
| 2 | 0/128 | 0.0233 | 0.9948 | 372 | 0.9922 | 536 | 6,024,284 | 0.1173 |
| 1 | 1/128 | 0.0388 | 0.9984 | 621 | 1.0000 | 545 | 6,526,270 | 0.0758 |

Subjects: **384**. Exact submissions: **5**. Gateway requests: **1632**. Gateway tokens: **19,184,855**.

Counted infrastructure estimate: **$7.0839**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

| Repeat | Requests | Completed-entity payload coverage | Total expected-object coverage |
| --- | ---: | ---: | ---: |
| 3 | 551 | 2568/2568 | 2988/2988 |
| 2 | 536 | 2448/2448 | 2832/2832 |
| 1 | 545 | 2526/2526 | 2933/2933 |

Actual stored objects total **8,754**, including one additional repeat-2 object. The 384 native-goal receipts record `blocked`; frozen output bytes determine the scores above. Provider executions include **834 HTTP 429** and **one HTTP 504**. [Observations](observations.md) retain native active time, host resources, timing, provider quotas and timestamped sibling contacts.

Independent audits verify [case identities](case-audit.json), [preparation identities](preparation-audit.json), [517 disabled keys](key-inventory-verification.json), and [capacity release at 18:16:29 UTC](capacity-release.json). All-provisioned EC2/IPv4/gp3 cost is estimated at **$7.675585**; [artifact accounting](artifacts.md) also records archival operations and transfer estimates.

[Source provenance](source-provenance.json) binds repeats 3/2 to `7f2ac77b2ce34ca774d955f9e24f894d4c80e6e5` and repeat 1 to `1e0c48d5701f73eb83c749c0098fbd0facc092a5`. The issue attachments contain source archives, approved protocols, graph replay evidence, sanitized preparation/case bundles and all three publications as ordered parts.

Repository `summary.json` retains scores and recording totals. Repository `observations.json` retains contact aggregates and capture/context hashes. Full per-contact records accompany the attached case bundle; `full-report-sha256.txt` binds its complete summary, observations and contact reports.
