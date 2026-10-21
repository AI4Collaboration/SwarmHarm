# Reliable public observations

The public reader consumes only a map of public paths and base64 file bytes.
It receives no private workspace, fixture, answer, credential, network or host
mount. It uses the existing pinned image, non-root user, read-only root, dropped
capabilities and bounded temporary storage. The decoder is supplied by the
registered experiment; the business v3 decoder is byte-identical to v2.

`PublicReader.read` creates a fresh consumer only for a new public-byte state.
Its receipt key includes every path/body, image, decoder, wrapper and execution
bound. A successful, checksummed receipt can serve repeated identical states;
per-event provenance distinguishes reuse from a fresh execution. Changed or
deleted files require another receipt. Failed or malformed observations never
become empty successful results. `force_fresh=True` independently repeats a state.

Docker creation, start/attach, execution and cleanup are separate stages. Defaults
are 60 seconds to create, 30 seconds to start/attach, a 10-second in-container
execution watchdog and 15 seconds per control/cleanup command. If attachment
fails after a successful exit, inspect the owned container and recover its exact
completed output from logs. Otherwise allow at most two reader executions for
retryable lifecycle errors, with verified cleanup between them. Decoder failures,
execution watchdogs, invalid output/cache and unconfirmed cleanup stop explicitly.
No model request is retried. Lifecycle stages, timings, failures, receipt hashes,
container state and cleanup verification are durably journaled.

The [business v3 integration](../business-cache-v3/README.md) commits each actual
tool result and public snapshot before running this observer. A persistent
observation error saves the normal tool trace and native tool-output pair, then
holds collection with a pending measurement. An operator interruption is marked
terminal. No failed measurement is reported as zero exposure.

[Repair report](REPORT.md) · [Final evidence](evidence/2026-10-21/verification-final.json).
Run model-free checks with the project interpreter:

```text
python -m unittest discover -s experiments/infra-reader-v1 -p checks.py -v
python -m unittest discover -s experiments/business-cache-v3 -p checks.py -v
python -m unittest discover -s experiments/business-cache-v3 -p collector_checks.py -v
python -m unittest discover -s experiments/business-cache-v3 -p launch_checks.py -v
```

`diagnose.py` and `stress.py` use only historical public bytes and local contained
workstations. Evidence files are write-once; use `stress.py --output <fresh-path>`
for another verification. These are infrastructure controls, not new model trials
or new behavioral findings. Do not edit historical experiment sources or results.
`verify.py --output <fresh-path>` checks the saved final test logs, exact frozen
native inputs/files, historical source hashes, final stress source identity,
actual inference lock and physical container cleanup. It makes no model call.
