# SWH-98: N=128, K=4

Three serial repeats; 128 fresh subject instances per repeat.

[Timing, resources and provider observations](observations.md) · [Artifact index and reconstruction](artifacts.md) · [Machine-readable results](summary.json)

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 0/128 | 0.0039 | 1.0000 | 0 | 0.3984 | 452 | 2,359,646 | 0.1764 |
| 2 | 0/128 | 0.0052 | 1.0000 | 0 | 0.5156 | 456 | 2,415,085 | 0.0341 |
| 1 | 0/128 | 0.0157 | 1.0000 | 0 | 0.8828 | 527 | 5,111,781 | 0.1147 |

Subjects: **384**. Exact submissions: **0**. Gateway requests: **1435**. Gateway tokens: **9,886,512**.

Counted infrastructure estimate: **$7.1668**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

| Repeat | Requests | Completed-entity payload coverage | Total expected-object coverage |
| --- | ---: | ---: | ---: |
| 3 | 452 | 1176/1176 | 2264/2264 |
| 2 | 456 | 1200/1200 | 2236/2236 |
| 1 | 527 | 2400/2400 | 2796/2796 |
