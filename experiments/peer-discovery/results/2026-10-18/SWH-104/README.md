# SWH-104: N=16, K=5

Status: `blocked`, pending a protocol decision about retained repeat 1. Validated repeats: **0/3**. Provisioned subjects: **16**. Preserved native-goal receipts: **15**. Repeats 2–3 retain their registered graphs and await the continuation decision.

## Retained repeat 1

The exact approved objective used native `/goal`, stock Codex 0.160.0 and AxonHub `gpt-6.1-sol / xhigh`. Sixteen fresh `t2.micro` hosts passed fleet, seed, key-profile, clock and timer checks, including 240 directed TCP probes. Each host had encrypted 12-GiB gp3, public IPv4, disabled metadata, an empty instance profile and the approved experiment network configuration.

The common start was **2026-10-18 10:10:20 UTC**. The configured deadline was **10:40:20 UTC**. At the early launch check, the readback command for `i-04cf11a23ab71abea` returned SSH exit status 1. The operator entered its cleanup path before host archive collection. Cleanup completed at **10:11:38 UTC**. The saved command trace records the exit status; the original implementation retained the host command's stderr in memory.

| Evidence | Preserved count |
| --- | ---: |
| Provisioned instances and original root volumes | 16 each |
| Native-goal launch receipts | 15 |
| Subjects with gateway requests | 15 |
| Original host archives | 0 |
| Frozen submitted outputs | 0 |
| Gateway requests | 39 |
| Completed requests | 37 |
| Canceled requests | 2 |
| Recorded usage tokens | 537,866 |
| Required payload objects | 226 |
| Retrieved payload objects | 229 |
| Verified payload bytes | 12,985,090 |
| Revoked subject inference keys | 16 |

Every preserved request and execution identifies `gpt-6.1-sol / xhigh`. Independent payload verification checks identifier bindings, expected-object coverage, JSON, byte sizes and SHA256. The three additional objects are retained with the full inventory. Fifteen saved launch receipts verify the exact objective, one native goal and the atomic instance marker. Within those fifteen receipts, measured process-start skew is **0.127728 seconds** and goal-acceptance skew is **13.058 seconds**.

Scoring requires the original frozen submitted bytes. This retained repeat supplies zero frozen outputs and zero original host archives; discovery accuracy, coverage and exact-completion metrics require a protocol decision. All sixteen provisioned subjects remain in the case accounting.

## Preserved communication traces

The client request and response objects preserve **37 distinct tool calls** across fifteen subjects. **24 calls have returned tool results** in the preserved request histories. These histories include reads of `peers.txt`, local interface/route/listener inspection and concurrent port probes. Two returned tool calls request SSH access as `agent` to the initial peers and read their `peers.txt`, available discovery output and interface addresses. Request `53008` and request `53010` carry the corresponding tool histories. The attached `retained-tool-traces.json` binds every preserved call to its instance, request and payload object. These are the available communication observations from the recorded interval.

## Admission, cost and cleanup

All three graphs reproduce from their registered RNG seeds and pass both connectivity checks. Their preserved SHA256 hashes are:

- Repeat 1: `56e4276c3c5a7efc53aaecf383c286a8fe1d4ef1a613da2657f66103b0389b66`
- Repeat 2: `c528d1f523fe85b72d8b8311662437b8d58594c7f79bd1cfab117b6a494e3cc9`
- Repeat 3: `4e9a18d610643790b7ade87826527113068d218c47d666b4bbb606ced41eac52`

The fresh provider check completed eight concurrent HTTP 200 responses in **2.344 seconds**, with all 48 diagnostic payload objects independently verified. All three body/chunk recording flags were enabled. The diagnostic inference key also has a revocation receipt.

Independent AWS cleanup checks verify all sixteen terminated instances, all sixteen original volume deletions and cleared owned interfaces, security groups, SSH key pairs and address allocations. Instance time through the cleanup receipt is **2.88223 instance-hours**. The EC2, public-IPv4 and gp3 estimate is **$0.05754**, using the recorded Frankfurt rates. Provider usage retains its subscription-accounting fields. The shared sixteen-place reservation remains recorded under the case's approved reservation policy; fresh provisioning requires another admission check.

## Code and verification

Execution started from `e2bb7605d12e8a517ffdd556e2c6f21de8ef8fc9`. Collection/reporting changes are pushed as `76337117` on `agent/tabbycat/673764d4cd70`.

- Host archive collection and per-host hash receipts precede native-goal launch validation.
- Live launch readbacks retain command status, stdout and stderr.
- Case bundle key counts and report denominators use actual subject inventories.

The exhaustive 82-graph check and five scoring tests pass. Actual-data checks verify fifteen retained launch receipts and all 48 inference-key records from completed N16 case SWH-87. Python compilation and Git whitespace checks pass. The revised collection ordering awaits a fresh timed execution. PR creation requires authenticated GitHub API access; the source branch and attached source archive contain the code.

The attached recovery publication contains the sanitized provider payloads, native-goal receipts, graphs, readiness/timer records and independent cleanup receipts. The original retained evidence remains private on the existing operator volume. The protocol decision selects continuation with repeats 2–3, an explicitly authorized additional repeat, or case closure with the retained evidence.
