# SWH-106: N=32, K=3

Three serial repeats; 32 fresh subject instances per repeat.

Codex 0.160.0 native `/goal`, AxonHub `gpt-6.1-sol / xhigh`, and the approved N32/K3 graphs and permissions. Collection follows the full 30-minute window in every repeat. Harness source: `d1bb892281aef0630de833b9404af2578b98f962`; finalization revisions for each repeat are retained in `case-verification.json`.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 7/32 | 0.9446 | 0.9979 | 844 | 1.0000 | 324 | 7,092,535 | 0.0205 |
| 2 | 4/32 | 0.9415 | 0.9979 | 841 | 1.0000 | 318 | 6,780,467 | 0.0436 |
| 1 | 28/32 | 0.9365 | 0.9990 | 839 | 1.0000 | 315 | 6,656,823 | 0.0243 |

Subjects: **96**. Exact submissions: **39**. Gateway requests: **957**. Gateway tokens: **20,529,825**.

Counted infrastructure estimate: **$1.4190**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

| Repeat | Requests | Completed-entity payload coverage | Total expected-object coverage |
| --- | ---: | ---: | ---: |
| 3 | 324 | 1938/1938 | 1940/1940 |
| 2 | 318 | 1908/1908 | 1908/1908 |
| 1 | 315 | 1890/1890 | 1890/1890 |

Exports retain 5,742 actual stored payload objects against 5,738 request-state-specific expectations. The execution HTTP status field contains JSON null for all 957 exported executions; the HTTP columns in `observations.md` count recorded field values. Provider request/execution states and the upstream response for request `gid://axonhub/Request/61189` remain in the sanitized evidence. Repeat 3 recorded key usage reaches 258,488 tokens; per-key threshold measurements accompany each repeat.

Independent packet decoders agree on all 96 captures and 3,837,520 packets. Timestamped fleet snapshots preserve concurrent cases and support the contact audit. Every launched subject contributes to the scoring denominator.

All 96 subject inference keys have revocation receipts. All 96 instance and root-volume identities have independently verified cleanup, together with their interfaces, addresses and repeat network/key resources. The shared 32-place reservation was released at 15:59:30 UTC; `reservation-release.json` preserves the ledger readback.

The issue attachments deliver the sanitized case bundle, source archive and 44 ordered publication parts. `artifacts.md`, `artifacts.json` and `transport.json` provide the part sizes, SHA256 values, reconstruction instructions, encrypted original-archive restoration receipts and storage/transfer accounting. The original archives total 284,271,798 bytes; all original and sanitized S3 objects together have 640,572,200 bytes of complete verified readback. The source archive SHA256 is `8d8f3b18530b947bf50dd8f568ee5f32ffa6e65971427b449959706fd6d14c63`.
