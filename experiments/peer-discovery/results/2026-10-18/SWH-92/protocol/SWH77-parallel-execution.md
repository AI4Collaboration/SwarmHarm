Approved execution update for SWH-77, 2026-10-17. Run the 16 cases beginning at N=16 and their three repeats through capacity-based parallel admission: 48 repeats and 2,880 fresh subjects. Preserve Codex 0.160.0, native `/goal`, one subject run per instance, fresh EC2 environments per repeat, exact task inputs, synchronized Unix-timestamp starts, quotas, deadlines, grading, and cleanup.

## Live capacity and packing

Frankfurt readback: 256 Standard On-Demand vCPUs; ten vCPUs of other infrastructure; four active SWH-78 subjects; 242 free subnet addresses; 5,000 regional ENIs with nine currently used; 50 TiB gp3 quota with 208 GiB used; 20 Elastic IPs. Subjects use auto-assigned public IPv4. One ENI and one 12-GiB gp3 volume accompany each subject. Each repeat uses one security group and SSH key pair. Use their tagged readback during cleanup.

The physical subject envelope is **244**. The retained matrix packs **N=16+32+64+128=240** simultaneously, leaving six vCPUs/addresses after earlier subjects complete cleanup. Refresh actual AWS inventory and all resource limits before provisioning. Shared reservations include instances awaiting launch, preflight, and live subjects; preflight teardown precedes counted launches. Keep the sum within the live limits. Check agent/runtime execution slots and AxonHub shared throughput as additional constraints.

The 48 repeat sizes fit **12 equal-duration waves of 240 subjects**, totaling 2,880 subjects. Start SWH-87 at N=16 first, then admit the ready N32,64,128 cases alongside it. Actual dispatch fills available capacity with ready whole cases, prioritizing larger replacements and skipping graphs still sampling. Repeats within each case execute serially. When a case releases its reservation after three repeats and cleanup, fill that capacity immediately with eligible work. Stage numbers identify cases for reporting.

## Shared admission

The shared code is `experiments/peer-discovery-scheduling/admit.py` in the SWH-77 scheduling branch. Every case uses the same operator state directory:

```text
/home/cpt-llm/Playground/cpt-llm-agent-workspace/swarmharm-dd7d0eb4a945/swh-77-2676e12c058c/workdir/.research/shared-admission
```

This operator configuration path identifies the live reservation database. Run the utility from a repository checkout containing the scheduling code:

```bash
python3 experiments/peer-discovery-scheduling/admit.py reserve --state-dir OPERATOR_STATE --issue SWH-96 --n 128
python3 experiments/peer-discovery-scheduling/admit.py status --state-dir OPERATOR_STATE
python3 experiments/peer-discovery-scheduling/admit.py release --state-dir OPERATOR_STATE --issue SWH-96
```

The controller locks a shared SQLite ledger while checking AWS vCPU, subnet-IP, ENI, and gp3 capacity. It accounts for both reserved and already allocated instances. Reservations persist until explicit release. A successful receipt is required before each launch sequence. Each case holds its envelope through its three repeats and cleanup; admission refresh is idempotent. Release verifies EC2 instance and volume readback after the case's complete cleanup receipt. SWH-78's earlier four-host observations have verified archive exports, four key revocations, and cloud cleanup; its reservation is released separately from the retained matrix.

Initial ready cases are SWH-87 (16,5), SWH-91 (32,5), SWH-95 (64,5), and SWH-99 (128,5). All three graphs for each initial ready case are registered in the parent workdir under `.research/graphs-ISSUE_KEY/graph-1.json` through `graph-3.json`, and their hashes accompany the graph artifact. Case operators copy these data files into their own workdirs and preserve hashes.

When graph sampling delays a reserved case, its owner releases the unused reservation and the scheduler admits other ready work. Sampling preparation can proceed concurrently with counted work. Case operators start from shared SWH-78 harness revision `100470a2` and preserve their own issue/case/resource tags. Runtime work and model calls remain observable foreground operations within each dispatched case task.

## AxonHub request and response recording

Verify the live storage policy has `storeRequestBody=true`, `storeResponseBody=true`, and `storeChunks=true` before each repeat. The existing default storage is AxonHub's configured S3 backend. Client requests and each upstream execution have separate request-body, response-body, and stream-chunk objects. Retrieve and validate the actual stored JSON objects and record size plus SHA256, linked to case, repeat, instance, API-key ID, request ID, execution ID, and Codex session ID.

At collection, paginate all request metadata for each counted key. For every recorded completed request, export and hash its three client objects plus the corresponding three objects for every execution from the configured storage. Include response/error status and all observed executions. Verify complete coverage against the request metadata. Publish sanitized evidence and receipts, keeping credential-bearing raw objects private. Record S3 retrieval/storage costs in experiment accounting.

Record simultaneous cases/repeats, gateway memory/CPU/disk, channel identity, latency, quotas, and stream completion so shared-provider contention can be evaluated. Retain observed cross-case traffic and addresses outside each repeat's true-peer set in scoring diagnostics. Give each repeat its own SSH identity and scoped inference keys.

## Dispatch and progress

All 16 retained child descriptions carry this scheduling policy. SWH-78–83 have cancelled status under the user's updated scope. The ten-minute progress timer reads shared reservations, AWS use, active case tasks, graph readiness, and recording receipts. It reserves and promotes backlog cases that fit, and releases delivered reservations after cloud cleanup. Case delivery sets `in_review`; the final comparison begins once every case has delivered results and cleanup. SWH-77 remains `in_progress` through execution.
