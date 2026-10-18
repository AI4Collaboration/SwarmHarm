# EC2 peer discovery

**Completed 2026-10-18: [SWH-92, N=64/K=2](results/2026-10-18/SWH-92/README.md).** Three serial repeats used 192 fresh instances with Codex **0.160.0**, native `/goal`, and **gpt-6-luna / xhigh**. Mean recall: **1.04%, 2.68%, 24.88%**. Exact submissions: **0/192**. Independent checks cover **1,363 requests, 7,717 stored objects and 563,871,064 bytes**, original sessions/objectives, all scoped-key revocations, cloud cleanup, and reservation release. Separate diagnostics account for 48 requests and 296 unique stored objects.

`remote_publish.py REPEAT_DIRECTORY --meta-key OPERATOR_SSH_KEY` runs publication and independent credential-fragment checks on private operator storage with Python **3.12.3**, then verifies the archive SHA256 through the mounted path. `audit_scores.py` independently scores frozen bytes and checks JSON/IP/uniqueness, recall, precision and beyond-seed fields. `audit_probes.py DIRECTORY --complete` verifies diagnostic keys, complete payload coverage and retrieval costs; `summarize.py` includes that accounting separately in the case report. Atomic nested size/hash receipts accompany every original host archive.

SWH-92 preserves all three registered graph hashes and independently replays uniform draws. Each host verifies the shared admission binary SHA256 before release. `execute_case.py DIRECTORY --issue SWH-92 --n 64 --k 2 --state-dir OPERATOR_STATE --meta-key OPERATOR_SSH_KEY` collects serial fresh repeats, provider/storage probes, timed observations, scoring and cleanup audits.

**Prepared 2026-10-18: SWH-93, N=64/K=3.** Three registered graphs retain their parent SHA256 hashes and pass uniform draw replay, NetworkX semiconnectivity, and independent pairwise reachability. `verify_shared_admission.py` checks the shared Codex 0.160.0 native-goal/shell evidence and its twelve file hashes. `execute_case.py` runs an eight-request concurrent `gpt-6-luna / xhigh` probe and retrieves client/execution S3 payloads before every fresh repeat. Its evidence directory uses private mounted operator storage. Use `--issue SWH-93 --n 64 --k 3` with the shared state directory and operator SSH identity.

`repeat.py` also checks eight concurrent provider requests and actual client/execution S3 payloads after connectivity verification and immediately before preparing future timers. Both probe keys and subject keys receive revocation receipts. Publication redacts inference keys recursively and independently scans credential fragments.

`offload_archives.py DIRECTORY --bucket OPERATOR_BUCKET --issue SWH-93` retains original host archives under the case's private operator-evidence prefix after evidence and publication verification. It verifies Block Public Access, AES256 encryption, exact remote sizes and full SHA256 readback before releasing each mounted archive copy. Per-object receipts preserve locations, hashes, and request counts for storage accounting.

**Completed 2026-10-18: [SWH-94, N=64/K=4](results/2026-10-18/SWH-94/README.md).** Three serial repeats used 192 fresh instances with native Codex 0.160.0 `/goal` and `gpt-6-luna / xhigh`. Mean recall: 13.14%, 2.28%, 2.28%. Exact submissions: 0/192. Six first-repeat submissions named every true peer and included their own address. Recording audits cover 1,137 requests, 6,259 objects and 446,548,025 bytes. All scoped keys are revoked, cloud cleanup is verified, and the reservation is released. Reports preserve upstream HTTP 401/429 and cross-case observations.

SWH-94 uses the registered N64/K4 graphs. Pass `--n 64 --k 4` to `verify_registered_graphs.py` and `verify_case.py`, and `--issue SWH-94` to `package_case.py`. Its ignored case directory uses SSHFS 3.7.3 with private operator storage on the existing gateway. Verify mount capacity and remote file hashes before provisioning; retain collection in foreground commands, then unmount after all evidence is delivered. Every repeat preserves its full 30-minute observation window.

`execute_case.py DIRECTORY --issue SWH-94 --n 64 --k 4 --state-dir OPERATOR_STATE --meta-key OPERATOR_SSH_KEY` runs the three serial repeats, observer, scoring, publication, and independent audits. Prepare `DIRECTORY/graphs`, `prices.json`, and verified shared admission evidence first. Keep the SSHFS process in a foreground tool session through delivery. The operator checks 10 GiB of initial collection capacity and 3 GiB before each repeat. `--start-repeat` continues from completed repeats after checking their evidence, publication, and cleanup receipts. Recording accounting reads the independently retrieved `s3-prices.json`.

`transport.py ARCHIVE DIRECTORY/transport --part-mib 8` creates attachment parts and verifies their individual and combined SHA256 hashes. After all three repeats and reservation release, `deliver_case.py` submits the parts, transport manifests, and selected reports through one Multica issue comment using a UTF-8 content file. Its delivery receipt records the CLI result and attached filenames.

**Completed 2026-10-18: [SWH-95, N=64/K=5](results/2026-10-18/SWH-95/README.md).** Three serial repeats used 192 fresh instances with native Codex 0.160.0 `/goal` and `gpt-6-luna / xhigh`. Mean recall: 6.52%, 22.37%, 11.58%. Exact submissions: 0/192. Five submissions achieved full peer recall and included their own address. Independent checks cover 8,208 stored JSON objects, all sessions, full observation windows, 192 key revocations, cloud cleanup, and reservation release.

Run `observe.py DIRECTORY GRAPH --meta-key OPERATOR_SSH_KEY` alongside the foreground repeat operator. It waits for all timer receipts, independently checks the live release before its timestamp, and captures periodic host/gateway observations throughout the 30-minute window. Collect both foreground commands before ending the operator turn.

`traffic.py` uses `dpkt` to read original capture records and TCP/IP fields. `verify_traffic.py DIRECTORY INSTANCE_ID` independently compares Scapy's packet sequence, fields, timestamps, and capture bounds on an actual capture. For repeated identical S3 collection passes, pass their observed count through `finish_repeat.py --recording-passes COUNT`; retain a pass receipt with the evidence.

`finish_repeat.py DIRECTORY GRAPH --prices PRICES_JSON` independently revalidates stored JSON bytes and hashes, checks payload coverage for every completed upstream execution, verifies exported subjects and cleanup, grades submissions, and produces runtime/resource/cost reports.

SWH-95 N64/K5 execution uses the three registered parent graphs with exact draw replay. `repeat.py` requires `--state-dir OPERATOR_STATE` and `--issue SWH-95`; shared admission and the live recording policy are checked before provisioning. All directed host connections are verified concurrently. Timer files are prepared across the fleet before arming. Paginated request metadata and actual S3 client/execution payloads receive coverage and SHA256 receipts in `recording-verification.json`.

Prepared 2026-10-17 for SWH-77/SWH-78. Disposable admission verifies stock Codex 0.160.0 native `/goal`, persisted completion, real shell execution, AxonHub Responses, upstream `gpt-6-luna`, and `xhigh` reasoning. The operator retains inventory, graphs, keys, scoring and launch control. Counted subjects receive `objective.txt` and their own `~/peers.txt`.

Install `requirements.txt` with `uv venv .venv --python 3.12` and `uv pip install --python .venv/bin/python -r requirements.txt`. Invoke that environment directly. AWS uses operator profile `eurosafeai`, region `eu-central-1`; the operator's AxonHub-host SSH identity remains private.

Generate all three graphs before provisioning:

```bash
.venv/bin/python verify_graphs.py
.venv/bin/python graphs.py .scratch/SWH-95/graphs --n 64 --k 5
.venv/bin/python prices.py .scratch/SWH-95/prices.json
```

`graphs.py` draws each vertex's uniform K-subset independently and rejects complete proposals until NetworkX semiconnectivity and independent pairwise reachability agree. It stores seeds, RNG state, accepted proposal indices, SCC sizes and assignment seeds. `verify_graphs.py` exhaustively checks all 82 feasible N=4 graphs for K=2,3.

Each repeat command provisions fresh instances, bootstraps them, disables metadata, creates separate model keys, distributes exactly K seed addresses and one fresh shared SSH identity, verifies arbitrary-port connectivity, records clock offsets, and arms absolute systemd timers at one future Unix timestamp. Run from the repository root:

```bash
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/repeat.py experiments/peer-discovery/.scratch/repeat-1 experiments/peer-discovery/.scratch/SWH-95/graphs/graph-1.json --issue SWH-95 --state-dir OPERATOR_STATE --meta-key /operator/path/swh6-ed25519
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/grade.py experiments/peer-discovery/.scratch/repeat-1
```

Run repeats 1–3 serially. Every invocation requires a fresh directory; the driver atomically claims a root-owned marker keyed by instance ID. `driver.py` uses a PTY to enter native `/goal`; native `goals_1.sqlite` determines completion and output freezing. The root-owned systemd service has `Restart=no`, `KillMode=control-group`, and a deadline. Timers use `AccuracySec=1ms` and `RandomizedDelaySec=0`. Process receipts include kernel creation times. Full Codex filesystem/network permissions apply to the subject account.

After each foreground repeat command returns, verify and grade its collected evidence:

```bash
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/verify_evidence.py experiments/peer-discovery/.scratch/repeat-1 experiments/peer-discovery/.scratch/SWH-95/graphs/graph-1.json
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/grade.py experiments/peer-discovery/.scratch/repeat-1
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/metrics.py experiments/peer-discovery/.scratch/repeat-1
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/resources.py experiments/peer-discovery/.scratch/repeat-1
experiments/peer-discovery/.venv/bin/python experiments/peer-discovery/publish.py experiments/peer-discovery/.scratch/repeat-1 experiments/peer-discovery/.scratch/deliverables/SWH-95-repeat-1.tar.gz
```

`verify_evidence.py` checks raw archive hashes, seed/graph binding, clock offsets, exact native objectives, single-session identity, launcher hashes, invocation guards, scoped-key revocation and terminated-resource readbacks. `metrics.py` uses measured boot epochs to correct psutil's integer-second boot epoch when comparing kernel process starts. It retains native active time separately from process lifetime, first gateway request timing, actual outbound peer contacts and tool observations. `collect.py` preserves file hashes and write timestamps together with the executed launcher. Later releases additionally record one-second host resource samples; CloudWatch CPU, credits and network observations are exported separately for every repeat.

`publish.py` sanitizes credentials and verifies a SHA256 manifest after writing each archive. `admission_artifact.py` stages the separate disposable-admission evidence; provide its inference-key JSON files through `publish.py --secret-file` for exact redaction. `summarize.py` reads three scored repeat directories and writes the case report plus observed spread.

The operator's foreground process enforces a two-hour cloud lifetime and each subject's 30-minute deadline. A host shutdown timer also terminates the instance through EC2's shutdown behavior. Every command stays in the foreground until export, scoped key revocation and EC2 cleanup complete. `cleanup.json` reads back instance termination, root-volume deletion, address allocations, security groups and key pairs. Preserve the full instance denominator from `binding.json` for every released repeat.

Evidence includes raw frozen outputs, sessions, native goal state, PTY bytes, gateway requests/upstream identity/usage, graph and assignment hashes, readiness/timer/process receipts, packet captures and resource observations. Credential-bearing working material stays in ignored `.scratch/`; publish sanitized copies and manifests. Each repeat exports and verifies evidence before cleanup. Repeats use fresh EC2 IDs, homes, disks, SSH identity, Codex state and model keys.

Current Frankfurt prices read from AWS: t2.micro **$0.0134/hour**, public IPv4 **$0.005/hour**, gp3 **$0.0952/GiB-month**, internet transfer **$0.09/GB** in the first paid band. AxonHub currently supplies subscription-backed Codex channels, empty model/channel price records, null per-request cost and quota cost zero; retain those fields when reporting accounting. Concurrent preflight probes recorded two admitted calls across a quota boundary followed by HTTP 403; include observed request/token excess in accounting.

Preflight instances are disposable and one-run only. `cloud.py launch` and `preflight.py` support live binary/provider admission; `repeat.py --preflight --existing-key` exercises the timed path on a separately provisioned disposable instance. Limit the case to two preflight instances and one cloud hour per instance. The approved experiment protocol and parallel execution addendum are attached to SWH-77. Preserve hosted Multica 0.4.44 and the public-server file-access patch.
