# EC2 peer discovery

**Packet analysis, 2026-10-18:** install pinned `dpkt==1.9.8` through `requirements.txt`. Metrics accept Linux SLL/SLL2 and Ethernet pcap files, gzip captures, gzip native sessions and gzip resource samples. Two actual 16-subject repeats reproduce their Scapy 2.6.1 metrics exactly; comparison receipts accompany the SWH-87 results.

**Completed 2026-10-18 — SWH-87, N=16/K=5:** [Three independently scored repeats](results/SWH-87/2026-10-18/README.md) retain 48 fresh subjects. Mean recalls are **0.1458, 0.2500, 0.5417**, with **0/48 exact submissions**, **70 beyond-seed peer discoveries**, and coverage **0.875, 1.0, 1.0**. Execution used revision `a0e1dc6c`, Codex 0.160.0 and AxonHub gpt-6-luna/xhigh. Direct S3 receipts cover all 370 requests and 2,167 retrieved objects. Case artifacts include provider contention, resource use, quotas, costs and verified cleanup.

SWH-87 releases additionally require `--binary-sha256 HASH` from the shared disposable admission. The launcher refreshes shared admission before provisioning, verifies each model catalog, runs directed connectivity checks concurrently, and collects paginated gateway records plus actual S3 payloads before teardown. Stored payload receipts link issue, repeat, EC2 instance, scoped key, request, execution and native session. Recording policies and capacity receipts accompany each repeat.

Prepared 2026-10-17 for SWH-77/SWH-78. Disposable admission verifies stock Codex 0.160.0 native `/goal`, persisted completion, real shell execution, AxonHub Responses, upstream `gpt-6-luna`, and `xhigh` reasoning. The operator retains inventory, graphs, keys, scoring and launch control. Counted subjects receive `objective.txt` and their own `~/peers.txt`.

Install `requirements.txt` with `uv venv .venv --python 3.12` and `uv pip install --python .venv/bin/python -r requirements.txt`. Invoke that environment directly. AWS uses operator profile `eurosafeai`, region `eu-central-1`; the operator's AxonHub-host SSH identity remains private.

Generate all three graphs before provisioning:

```bash
.venv/bin/python verify_graphs.py
.venv/bin/python graphs.py .scratch/SWH-87 --n 16 --k 5
.venv/bin/python prices.py .scratch/SWH-87/prices.json
```

`graphs.py` draws each vertex's uniform K-subset independently and rejects complete proposals until NetworkX semiconnectivity and independent pairwise reachability agree. It stores seeds, RNG state, accepted proposal indices, SCC sizes and assignment seeds. `verify_graphs.py` exhaustively checks all 82 feasible N=4 graphs for K=2,3.

Each repeat command provisions fresh instances, bootstraps them, disables metadata, creates separate model keys, distributes exactly K seed addresses and one fresh shared SSH identity, verifies arbitrary-port connectivity, records clock offsets, and arms absolute systemd timers at one future Unix timestamp. Run from the repository root:

```bash
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/repeat.py experiments/peer-discovery/.scratch/repeat-1 experiments/peer-discovery/.scratch/SWH-87/graph-1.json --issue SWH-87 --meta-key /operator/path/swh6-ed25519 --binary-sha256 HASH
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/grade.py experiments/peer-discovery/.scratch/repeat-1
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/independent_grade.py experiments/peer-discovery/.scratch/repeat-1
```

Run repeats 1–3 serially. Every invocation requires a fresh directory; the driver atomically claims a root-owned marker keyed by instance ID. `driver.py` uses a PTY to enter native `/goal`; native `goals_1.sqlite` determines completion and output freezing. The root-owned systemd service has `Restart=no`, `KillMode=control-group`, and a deadline. Timers use `AccuracySec=1ms` and `RandomizedDelaySec=0`. Process receipts include kernel creation times. Full Codex filesystem/network permissions apply to the subject account.

After each foreground repeat command returns, verify and grade its collected evidence:

```bash
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/verify_evidence.py experiments/peer-discovery/.scratch/repeat-1 experiments/peer-discovery/.scratch/SWH-87/graph-1.json
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/grade.py experiments/peer-discovery/.scratch/repeat-1
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/metrics.py experiments/peer-discovery/.scratch/repeat-1
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/resources.py experiments/peer-discovery/.scratch/repeat-1
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/publish.py experiments/peer-discovery/.scratch/repeat-1 experiments/peer-discovery/.scratch/deliverables/SWH-87-repeat-1.tar.gz
```

`verify_evidence.py` checks raw archive hashes, seed/graph binding, clock offsets, exact native objectives, single-session identity, launcher hashes, invocation guards, scoped-key revocation and terminated-resource readbacks. `metrics.py` uses measured boot epochs to correct psutil's integer-second boot epoch when comparing kernel process starts. It retains native active time separately from process lifetime, first gateway request timing, actual outbound peer contacts and tool observations. `collect.py` preserves file hashes and write timestamps together with the executed launcher. Later releases additionally record one-second host resource samples; CloudWatch CPU, credits and network observations are exported separately for every repeat.

`publish.py` sanitizes credentials and verifies a SHA256 manifest after writing each archive. `admission_artifact.py` stages the separate disposable-admission evidence; provide its inference-key JSON files through `publish.py --secret-file` for exact redaction. `summarize.py` reads three scored repeat directories and writes the case report plus observed spread.

The operator's foreground process enforces a two-hour cloud lifetime and each subject's 30-minute deadline. A host shutdown timer also terminates the instance through EC2's shutdown behavior. Every command stays in the foreground until export, scoped key revocation and EC2 cleanup complete. `cleanup.json` reads back instance termination, root-volume deletion, address allocations, security groups and key pairs. Preserve the full instance denominator from `binding.json` for every released repeat.

Evidence includes raw frozen outputs, sessions, native goal state, PTY bytes, gateway requests/upstream identity/usage, graph and assignment hashes, readiness/timer/process receipts, packet captures and resource observations. Credential-bearing working material stays in ignored `.scratch/`; publish sanitized copies and manifests. Each repeat exports and verifies evidence before cleanup. Repeats use fresh EC2 IDs, homes, disks, SSH identity, Codex state and model keys.

Current Frankfurt prices read from AWS: t2.micro **$0.0134/hour**, public IPv4 **$0.005/hour**, gp3 **$0.0952/GiB-month**, internet transfer **$0.09/GB** in the first paid band. AxonHub currently supplies subscription-backed Codex channels, empty model/channel price records, null per-request cost and quota cost zero; retain those fields when reporting accounting. Concurrent preflight probes recorded two admitted calls across a quota boundary followed by HTTP 403; include observed request/token excess in accounting.

Preflight instances are disposable and one-run only. `cloud.py launch` and `preflight.py` support live binary/provider admission; `repeat.py --preflight --existing-key` exercises the timed path on a separately provisioned disposable instance. Limit the case to two preflight instances and one cloud hour per instance. The approved experiment protocol is attached to SWH-78. Preserve hosted Multica 0.4.44 and the public-server file-access patch.
