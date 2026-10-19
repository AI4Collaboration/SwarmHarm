# SWH-111: N=64, K=4

Case-wide verification confirms **192 distinct launched instances and root volumes, 180 distinct accepted native sessions, 195 revoked case-scoped inference keys, verified cloud cleanup and released 64-place capacity**. All 192 original archives and all three sanitized publications passed complete encrypted private-S3 readback.

[Communication observations](communication.md), [timing/resources/provider observations](observations.md), [session review](session-review.json), [case verification](case-verification.json) and [artifact reconstruction/archival receipts](artifacts.md) accompany the scores below. Independent recording verifies **10,987/10,987 required objects**; retained payload inventory contains **10,991 objects**. Independent packet decoding agrees across **192 captures and 7,808,458 packets**.

Repeat 2 retains ten app-server startup timeouts, two services interrupted before goal acceptance and 37 journal-verified service interruptions. Cause attribution remains open. Its full 64-subject denominator and actual 52-session count are preserved.

Three serial repeats; 64 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 23/64 | 0.9650 | 0.9995 | 3639 | 1.0000 | 650 | 13,975,570 | 0.2280 |
| 2 | 6/64 | 0.2458 | 0.9966 | 929 | 1.0000 | 529 | 10,984,583 | 5.3501 |
| 1 | 27/64 | 0.9616 | 0.9995 | 3626 | 1.0000 | 647 | 13,650,545 | 0.2143 |

Subjects: **192**. Exact submissions: **56**. Gateway requests: **1826**. Gateway tokens: **38,610,698**.

Counted infrastructure estimate: **$3.0504**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

| Repeat | Requests | Completed-entity payload coverage | Total expected-object coverage |
| --- | ---: | ---: | ---: |
| 3 | 650 | 3900/3900 | 3900/3900 |
| 2 | 529 | 3168/3168 | 3170/3170 |
| 1 | 647 | 3870/3870 | 3917/3917 |

| Repeat | Accepted native goals | Startup timeout | Service stopped before goal |
| --- | ---: | ---: | ---: |
| 3 | 64/64 | 0 | 0 |
| 2 | 52/64 | 10 | 2 |
| 1 | 64/64 | 0 | 0 |

Recall includes every launched subject. Native-active timing uses accepted goals. Startup-timeout records retain process receipts, the submitted objective and the PTY diagnostic.
