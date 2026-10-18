## SWH-88 execution

This case runs N=32, K=2 across three serial repeats. Each repeat uses 32 fresh EC2 instances and a 30-minute observation window from its shared future Unix timestamp. The shared harness is based on revision `100470a2`; scheduling uses the SWH-77 locked admission ledger.

Deploy these case scripts into `OPERATOR_STATE/scripts`, the shared harness into `OPERATOR_STATE/operator-code/experiments/peer-discovery`, and the scheduling code into the adjacent `peer-discovery-scheduling` directory. Place the registered graph files in `OPERATOR_STATE/graphs` and preserve their SHA256 values. Operator state remains private.

Run `scripts/prepare.py REPEAT` before each repeat to reproduce graph sampling, check gpt-6-luna/xhigh throughput, retrieve stored client/execution payloads, and revoke the probe key. Reuse the shared native-goal admission after `scripts/source_manifest.py` verifies the executed driver and parsed provider configuration.

Reserve 32 places with `admit.py reserve` against the shared state directory recorded on SWH-88. Verify the receipt, then invoke `repeat.py` with the case graph, `--issue SWH-88`, the operator administration SSH identity, and the verified Codex binary SHA256. The repeat harness refreshes admission, provisions, verifies readiness, arms one-shot timers, observes the full window, exports evidence, revokes keys, and verifies cloud cleanup. Keep this foreground execution owned until it exits.

Use `scripts/status.py REPEAT` during bootstrap and `scripts/observe.py REPEAT` after release to record starts, accepted native goals, output presence, shared-provider contention, hardware, and a live six-object S3 retrieval. `scripts/finalize.py REPEAT` checks exports, independently grades frozen outputs, analyzes packet captures, verifies all stored hashes, collects CloudWatch metrics, and publishes a sanitized archive.

After all three repeat audits, `scripts/release.py` verifies 96 distinct subjects, root volumes, and revoked inference keys, reads back owned network resources, and releases the reservation. `scripts/report.py` assembles the case report. `scripts/bundle.py OPERATOR_STATE` produces checked ZIP transport parts; the reconstruction script and part manifest accompany delivery.
