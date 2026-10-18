# SWH-93: N=64, K=3

Three serial fresh repeats launched 192 subjects. Cleanup verifies 192 terminated instances and revoked keys; the shared reservation is released.

| Repeat | Subjects | Retained host archives | Exact submissions | Mean recall | Requests | Tokens |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| 3 | 64 | 64/64 | 0/64 | 0.021577 | 337 | 2,771,687 |
| 2 | 64 | 23/64 | pending complete exports | pending complete exports | 324 | 2,565,682 |
| 1 | 64 | 64/64 | 0/64 | 0.018601 | 324 | 2,549,124 |

Repeat 2 retains 64 verified launch/session bindings, 23 original host archives, 15 process-stop receipts, all gateway metadata and verified stored payloads. Its retained service journals record stop/restart events during the observation window. The original 64 instances and volumes have completed verified deletion. Complete grading depends on a protocol decision covering the 41 outstanding original exports and the retained lifecycle-receipt coverage. Its partial audit preserves every launched subject and the scores derived from collected output bytes.

Repeats 1 and 3 have complete independent export, session, objective, scoring, recording, resource and cleanup checks. Their scores remain available individually. The complete case score is pending repeat 2 evidence.

Recorded usage: **985 requests / 7,886,493 tokens**. Counted EC2/IPv4/gp3 infrastructure estimate: **$3.2065**. Regional S3 and shared operator-storage rates and operation receipts accompany the evidence. [AWS EBS pricing](https://aws.amazon.com/ebs/pricing/).

Independent recording audits verify **5,203 objects / 355,195,123 bytes** across all three repeats, including required client/execution request bodies and completed response/chunk coverage.

Sanitized repeat archives are split into attachment parts. Concatenate each repeat’s numbered parts in order and verify the resulting SHA256 against its transport manifest. `artifacts.json` records archive sizes and hashes.

Code revision: `4fc388d2a5ecb085183c8d4413ad0a3439c7d9d3`.

Separate preparation evidence verifies cleanup of **64 instances and 64 scoped keys** before subject timer arming. Preparation infrastructure estimate: **$0.2582**. Counted subjects remain **192**, and total case instance cleanup accounts for **256** instances.

Observed upstream HTTP 401/429 execution counts: repeat 3: 262/126; repeat 2: 257/124; repeat 1: 273/124.

| Fully audited repeat | JSON arrays | Coverage | Mean precision of submitted arrays | Beyond-seed discoveries | Goal skew (s) | Maximum tokens/key |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 29 | 0.750000 | 1.000000 | 0 | 3.863000 | 214,324 |
| 1 | 25 | 0.687500 | 1.000000 | 0 | 1.757000 | 65,517 |

Configured per-key thresholds are 100 requests and 200,000 tokens. Repeat 3 records one key at 214,324 tokens. Admission probes preserve concurrent/in-flight allowance measurements. Usage and cost accounting use actual gateway records. All 64 persisted native goals in each repeat have status `blocked`; output grading uses the collected output bytes.
