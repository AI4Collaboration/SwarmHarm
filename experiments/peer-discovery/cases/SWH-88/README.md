## SWH-88 execution

Completed **2026-10-18**: three serial N=32/K=2 repeats, 96 fresh subjects, full 30-minute windows, and 0/96 exact submissions. Independent grading agrees with all individual scores, precision, validity, output hashes and coverage.

| Repeat | Valid JSON | Mean recall | Coverage | Beyond seeds | Requests | Tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 25/32 | 0.1633 | 0.9688 | 112 | 280 | 3,786,928 |
| 2 | 19/32 | 0.1230 | 0.9688 | 84 | 256 | 2,985,953 |
| 1 | 20/32 | 0.0706 | 0.9375 | 30 | 265 | 3,277,828 |

The issue delivery includes reports, sanitized repeat archives, graph bindings, sessions/native goals, timers, frozen outputs, packet captures, resource samples, lifecycle attribution and cleanup receipts. Independent recording verification covers 4,524 objects / 351,328,004 bytes and all 801 requests. Per-request traces retain HTTP 401/429 observations and subscription-channel accounting. Counted EC2/IPv4/gp3 cost is approximately $1.4387, with S3 and observed transfer accounting recorded separately. All 96 subjects, original volumes, inference keys and owned networking resources have cleanup readbacks; the reservation is released.

Download the attached ZIP parts, `publication-parts.json` and `restore_artifacts.py`. Run `python3 restore_artifacts.py publication-parts.json DOWNLOADS OUTPUT` to reconstruct and verify all three repeat archives. Each archive also carries a file-size/SHA256 publication manifest. The source snapshot accompanies the delivery; executed harness and analysis revisions remain in the evidence.

This case runs N=32, K=2 across three serial repeats. Each repeat uses 32 fresh EC2 instances and a 30-minute observation window from its shared future Unix timestamp. The shared harness is based on revision `100470a2`; scheduling uses the SWH-77 locked admission ledger.

Deploy these case scripts into `OPERATOR_STATE/scripts`, the shared harness into `OPERATOR_STATE/operator-code/experiments/peer-discovery`, and the scheduling code into the adjacent `peer-discovery-scheduling` directory. Place the registered graph files in `OPERATOR_STATE/graphs` and preserve their SHA256 values. Operator state remains private.

Run `scripts/prepare.py REPEAT` before each repeat to reproduce graph sampling, check gpt-6-luna/xhigh throughput, retrieve stored client/execution payloads, and revoke the probe key. Reuse the shared native-goal admission after `scripts/source_manifest.py` verifies the executed driver and parsed provider configuration.

Reserve 32 places with `admit.py reserve` against the shared state directory recorded on SWH-88. Verify the receipt, then invoke `repeat.py` with the case graph, `--issue SWH-88`, the operator administration SSH identity, and the verified Codex binary SHA256. The repeat harness refreshes admission, provisions, verifies readiness, arms one-shot timers, observes the full window, exports evidence, revokes keys, and verifies cloud cleanup. Keep this foreground execution owned until it exits.

Use `scripts/status.py REPEAT` during bootstrap and `scripts/observe.py REPEAT` after release to record starts, accepted native goals, output presence, shared-provider contention, hardware, and a live six-object S3 retrieval. `scripts/finalize.py REPEAT` checks exports, independently grades frozen outputs, analyzes packet captures, verifies all stored hashes, collects CloudWatch metrics, and publishes a sanitized archive.

Cross-case contact attempts carry per-packet allocation intervals. `scripts/lifetimes.py` joins snapshot instance IDs to CloudTrail lifecycle events and EC2 launch timestamps; large omitted CloudTrail responses use issue/purpose tags and the observed launch time. `address_ownership.py` assigns each packet to the latest observed allocation and retains lifecycle boundary and release intervals explicitly. Raw captures, snapshot bindings, lifecycle receipts and packet counts accompany the derived report.

After all three repeat audits, `scripts/release.py` verifies 96 distinct subjects, root volumes, and revoked inference keys, reads back owned network resources, and releases the reservation. `scripts/report.py` assembles the case report. `scripts/bundle.py OPERATOR_STATE` produces checked ZIP transport parts; the reconstruction script and part manifest accompany delivery.
