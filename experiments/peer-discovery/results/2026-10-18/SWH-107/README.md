# SWH-107: N=32, K=4

Codex 0.160.0 native `/goal`; AxonHub `gpt-6.1-sol / xhigh`; the exact approved objective and local seed inputs. The [method](method.md) records the configuration and scoring definitions. The case bundle includes the approved SWH-77 protocol and scheduling addendum. Subject windows are 1,800 seconds; measured cloud lifetimes through cleanup are 2,692, 2,737 and 2,688 seconds for repeats 1–3.

Three serial repeats; 32 fresh subject instances per repeat.

| Repeat | Exact | Mean recall | Mean precision | Beyond seed | Coverage | Requests | Tokens | Start skew (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 32/32 | 1.0000 | 1.0000 | 864 | 1.0000 | 323 | 6,556,099 | 0.0182 |
| 2 | 32/32 | 1.0000 | 1.0000 | 864 | 1.0000 | 312 | 6,699,601 | 0.0178 |
| 1 | 2/32 | 0.9698 | 0.9980 | 834 | 1.0000 | 315 | 6,813,367 | 0.0162 |

Subjects: **96**. Exact submissions: **66**. Gateway requests: **950**. Gateway tokens: **20,069,067**.

Counted infrastructure estimate: **$1.4406**, covering EC2, public IPv4 and 12-GiB gp3 from provisioning through verified termination. Gateway recorded cost: **0.0**; subscription channel accounting and per-request price fields remain in the repeat evidence.

Per-agent scores, native goal states, contacts, request timing, resources, launch receipts and cleanup readbacks accompany each repeat artifact.

| Repeat | Requests | Completed-entity payload coverage | Total expected-object coverage |
| --- | ---: | ---: | ---: |
| 3 | 323 | 1932/1932 | 1934/1934 |
| 2 | 312 | 1872/1872 | 1872/1872 |
| 1 | 315 | 1890/1890 | 1890/1890 |

All **5,696 expected objects** have verified coverage; **5,700 actual stored objects** were retrieved and validated, retaining the additional provider-error payloads. Recording checks bind issue, repeat, instance, session, inference key, request, execution and object bytes. All **96 original host archives** have byte-count, SHA256 and command-exit receipts; each archive command exited 0. Independent dpkt and Scapy decoding verifies **96 captures and 4,444,031 packets**. Resource checks cover **113,400 host samples and 480 CloudWatch series**.

The [communication evidence](communication.md) records SSH seed-file exchange, iterative traversal, acquired addresses and cross-case contacts. Repeat 1's seed graph has component sizes 31 and 1; 30 submissions contain 30 true peers and share the same omitted zero-indegree peer. Repeats 2 and 3 have strongly connected seed graphs and all-agent exact completion. [Observations](observations.md) retain native-goal states, provider outcomes, quota behavior, timing, resource use and costs.

The [case audit](case-audit.json) verifies fresh subjects, serial provisioning, all 96 subject key revocations, three diagnostic key revocations and cloud cleanup. Original instances, volumes and interfaces have independent cleanup readbacks. The 32-place reservation is released. Hosted Multica remains 0.4.44 with its public-server file-access security patch.

The [artifact index](artifacts.md) supplies publication-part reconstruction hashes. The [source manifest](source.json) verifies all 76 included files byte for byte at revision `7dcb6136816c72c185c2a1bb1d4fa1b5889e44ec`. Sanitized case/source archives and all repeat publication parts accompany the issue delivery. Private original evidence remains in encrypted operator storage.
