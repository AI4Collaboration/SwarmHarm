# Parallel peer-discovery admission

SWH-77 uses one shared operator-side SQLite reservation database protected by a Linux file lock. Every case reserves its N-instance envelope before provisioning, holds it through its three repeats and cleanup, and releases it after verified teardown. The envelope includes preflight instances: preflight cleanup precedes the counted repeat. Every repeat gets fresh EC2 instances and one native Codex 0.160.0 `/goal` session per instance.

Each reservation reads live AWS vCPU quota/use, subnet addresses, network-interface quota/use, and gp3 quota/use while holding the lock. It counts both live instances and reserved instances still awaiting launch. Capacity remains reserved across operator exits until explicit release and cloud readback. The same case has one reservation and one running operator task.

Use the shared state directory given in the current SWH-77 issue description and its attached scheduling protocol:

```bash
python3 experiments/peer-discovery-scheduling/admit.py reserve --state-dir OPERATOR_STATE --issue SWH-96 --n 128
python3 experiments/peer-discovery-scheduling/admit.py status --state-dir OPERATOR_STATE
python3 experiments/peer-discovery-scheduling/admit.py release --state-dir OPERATOR_STATE --issue SWH-96
```

Exit status 2 from reservation means the case remains eligible for a later capacity grant. A successful reservation is required before each provisioning sequence; repeat the idempotent reservation to refresh live admission. The case operator verifies a successful receipt before launching. Case operators use their existing foreground run while collecting required results. Scheduled progress checks reserve and dispatch additional cases that fit.

The current envelope is **244 subject instances**: 128+64+32+16+4. AWS readback on 2026-10-17 showed a 256-vCPU Standard On-Demand quota, ten vCPUs of other infrastructure, 246 total lab subnet addresses after accounting for active subjects, 5,000 regional interfaces, and 50 TiB gp3 storage. Two vCPUs/addresses remain available outside the subject envelope. Auto-assigned public IPv4 avoids consuming Elastic IP allocations. Five concurrent repeat security groups remain far below regional resource counts. Re-read live limits at every admission.

The retained matrix starts at N=16 and contains 16 cases, 48 repeats and 2,880 fresh subjects. Start the N16 case first; then fill capacity with ready N32,64,128 cases for 240 subjects. The scheduler fills released capacity with the largest ready whole cases and considers every eligible backlog case. Repeats within a case execute serially. Stage numbers identify cases for reporting. With equal repeat durations, the matrix admits twelve waves of 240 subjects. Actual dispatch follows readiness, live capacity, and provider observations.

Every repeat must verify AxonHub `storeRequestBody`, `storeResponseBody`, and `storeChunks` enabled. Export all paginated client requests and upstream executions, their bodies and stream chunks, keyed by case/repeat/instance/API-key ID and request/session IDs. Retrieve stored body pairs before launch admission and after repeat collection; publish sanitized hashes and counts. Record shared channel contention and actual model latency alongside simultaneous case IDs. The user's ten-minute progress timer monitors capacity, recording completeness, and eligible dispatch.
